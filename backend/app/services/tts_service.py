"""语音合成服务：参数校验 + 调用模型 + 结果落盘。"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from app.config import Settings
from app.core.errors import AppError, UnsupportedModeError
from app.core.types import SynthParams
from app.services.modes import get_spec
from app.utils.audio import samples_to_wav_bytes

logger = logging.getLogger("app.tts")

MAX_TEXT_LENGTH = 2000
ENDOFPROMPT = "<|endofprompt|>"


@dataclass(slots=True)
class SynthesisResult:
    audio_id: str
    sample_rate: int
    duration: float
    path: Path | None
    mode: str

    @property
    def url(self) -> str | None:
        return f"/api/v1/tts/audio/{self.audio_id}" if self.path else None


class TTSService:
    def __init__(self, settings: Settings, model_manager) -> None:  # noqa: ANN001
        self._settings = settings
        self._manager = model_manager

    # ---------------------------------------------------------------- 校验
    def build_params(
        self,
        *,
        mode: str,
        tts_text: str = "",
        spk_id: str = "",
        prompt_text: str = "",
        instruct_text: str = "",
        prompt_wav_path: str | None = None,
        source_wav_path: str | None = None,
        zero_shot_spk_id: str = "",
        speed: float = 1.0,
        stream: bool = True,
        text_frontend: bool = True,
        seed: int | None = None,
    ) -> SynthParams:
        spec = get_spec(mode)
        if spec is None:
            raise UnsupportedModeError(f"未知的合成模式: {mode}")
        if not self._manager.supports(mode):
            raise UnsupportedModeError(f"当前模型不支持「{spec.label}」模式。{spec.note}".strip())

        tts_text = (tts_text or "").strip()
        uses_text = "text" in spec.fields
        uses_registered_voice = bool(zero_shot_spk_id)

        if uses_text:
            if not tts_text:
                raise AppError("请输入需要合成的文本", code="missing_text", status_code=422)
            if len(tts_text) > MAX_TEXT_LENGTH:
                raise AppError(
                    f"文本过长（{len(tts_text)} 字），请拆分后分段合成（上限 {MAX_TEXT_LENGTH} 字）",
                    code="text_too_long",
                    status_code=422,
                )

        if "speaker" in spec.fields and not spk_id.strip():
            raise AppError("请选择预训练音色", code="missing_speaker", status_code=422)

        if "prompt_text" in spec.fields and not uses_registered_voice and not prompt_text.strip():
            raise AppError(
                "请输入参考文本（需与参考音频内容一致）", code="missing_prompt_text", status_code=422
            )

        if "prompt_audio" in spec.fields and not uses_registered_voice and not prompt_wav_path:
            raise AppError("请上传或录制参考音频", code="missing_prompt_audio", status_code=422)

        if "source_audio" in spec.fields and not source_wav_path:
            raise AppError("请上传需要转换的源音频", code="missing_source_audio", status_code=422)

        instruct_text = (instruct_text or "").strip()
        if "instruct_text" in spec.fields:
            if not instruct_text:
                raise AppError("请输入风格指令文本", code="missing_instruct_text", status_code=422)
            # CosyVoice 2.0/3.0 要求指令以 <|endofprompt|> 结尾，这里自动补齐，减少误用
            if mode == "instruct2" and not instruct_text.endswith(ENDOFPROMPT):
                instruct_text = f"{instruct_text}{ENDOFPROMPT}"

        if mode == "zero_shot" and not uses_registered_voice and prompt_wav_path:
            # 参考文本远长于待合成文本时上游会给出质量警告，这里提前提示
            pass

        speed_value = float(speed or self._settings.default_speed)
        speed_value = max(self._settings.min_speed, min(self._settings.max_speed, speed_value))

        return SynthParams(
            mode=mode,  # type: ignore[arg-type]
            tts_text=tts_text,
            spk_id=spk_id.strip(),
            prompt_text=prompt_text.strip(),
            instruct_text=instruct_text,
            prompt_wav_path=prompt_wav_path,
            source_wav_path=source_wav_path,
            zero_shot_spk_id=zero_shot_spk_id.strip(),
            speed=round(speed_value, 2),
            stream=stream,
            text_frontend=text_frontend,
            seed=seed,
        )

    # ------------------------------------------------------------ 一次性合成
    def synthesize_wav(self, params: SynthParams, *, persist: bool = True) -> tuple[bytes, SynthesisResult]:
        started = time.perf_counter()
        chunks = [chunk for chunk in self._manager.synthesize(params) if chunk.size]
        if not chunks:
            raise AppError("模型没有返回音频，请检查输入参数", code="empty_audio", status_code=500)

        samples = np.concatenate(chunks).astype(np.float32)
        sample_rate = self._manager.sample_rate
        wav_bytes = samples_to_wav_bytes(samples, sample_rate)
        duration = float(samples.shape[0]) / sample_rate

        result = SynthesisResult(
            audio_id=uuid.uuid4().hex[:16],
            sample_rate=sample_rate,
            duration=round(duration, 3),
            path=None,
            mode=params.mode,
        )
        if persist:
            result.path = self._persist(result.audio_id, wav_bytes)

        logger.info(
            "合成完成 mode=%s 时长=%.2fs 耗时=%.2fs (RTF %.2f)",
            params.mode,
            duration,
            time.perf_counter() - started,
            (time.perf_counter() - started) / max(duration, 1e-6),
        )
        return wav_bytes, result

    # ---------------------------------------------------------------- 流式
    def stream_pcm(self, params: SynthParams, audio_id: str | None = None) -> Iterator[bytes]:
        """流式返回 int16 PCM，结束后把完整音频落盘。"""
        from app.utils.audio import float_to_pcm16

        collected: list[np.ndarray] = []
        for chunk in self._manager.synthesize(params):
            if chunk.size == 0:
                continue
            collected.append(chunk)
            yield float_to_pcm16(chunk)

        if not collected:
            return
        sample_rate = self._manager.sample_rate
        samples = np.concatenate(collected).astype(np.float32)
        self._persist(audio_id or uuid.uuid4().hex[:16], samples_to_wav_bytes(samples, sample_rate))

    # ---------------------------------------------------------------- 落盘
    def _persist(self, audio_id: str, wav_bytes: bytes) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self._settings.outputs_dir / f"{stamp}_{audio_id}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav_bytes)
        self._cleanup_outputs()
        return path

    def _cleanup_outputs(self) -> None:
        limit = self._settings.max_history_files
        files = sorted(self._settings.outputs_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        for path in files[: max(0, len(files) - limit)]:
            try:
                path.unlink()
            except OSError:
                pass

    def audio_path(self, audio_id: str) -> Path:
        safe = "".join(ch for ch in audio_id if ch.isalnum())
        if not safe or safe != audio_id:
            raise AppError("非法的音频 id", code="invalid_audio_id", status_code=400)
        matches = list(self._settings.outputs_dir.glob(f"*_{safe}.wav"))
        if not matches:
            raise AppError("音频不存在或已被清理", code="audio_not_found", status_code=404)
        return matches[0]
