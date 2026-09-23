"""语音合成接口。

* ``POST /tts/synthesize`` —— 一次性返回完整 WAV 文件；
* ``POST /tts/stream``     —— 以 int16 PCM 分片流式返回，便于前端边收边播；
* ``GET  /tts/history``    —— 最近生成结果列表。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import Settings
from app.core.errors import AppError, InvalidAudioError
from app.core.model_manager import ModelManager
from app.core.types import SynthParams
from app.deps import manager_dep, settings_dep, tts_service_dep, voice_store_dep
from app.schemas import AudioItemOut
from app.services.tts_service import TTSService
from app.services.voice_store import VoiceStore, runtime_spk_id
from app.utils.audio import ALLOWED_EXTENSIONS, validate_audio_file

logger = logging.getLogger("app.tts")

router = APIRouter(prefix="/tts", tags=["tts"])


# --------------------------------------------------------------------- 工具
async def _store_upload(
    upload: UploadFile | None,
    settings: Settings,
    prefix: str,
    *,
    required: bool = False,
) -> Path | None:
    """把上传的参考音频写入临时目录并做基础校验。"""
    if upload is None or not (upload.filename or "").strip():
        if required:
            raise AppError(f"缺少 {prefix} 音频文件", code="missing_audio", status_code=422)
        return None

    data = await upload.read()
    if not data:
        raise InvalidAudioError("上传的音频内容为空")
    if len(data) > settings.max_upload_bytes:
        raise AppError(
            f"音频过大（{len(data) / 1024 / 1024:.1f}MB），上限 {settings.max_upload_mb}MB",
            code="file_too_large",
            status_code=413,
        )

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise InvalidAudioError(
            f"不支持的音频格式 {suffix or '(未知)'}，可选：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    path = settings.tmp_dir / f"{prefix}_{uuid.uuid4().hex[:10]}{suffix}"
    path.write_bytes(data)
    validate_audio_file(
        path,
        filename=upload.filename,
        max_seconds=settings.max_prompt_seconds,
        min_seconds=settings.min_prompt_seconds,
    )
    return path


def _resolve_runtime_spk(voice_id: str, store: VoiceStore, manager: ModelManager) -> str:
    """把自定义音色 id 解析为运行时 spk id，必要时即时注册。"""
    voice_id = (voice_id or "").strip()
    if not voice_id:
        return ""
    if not store.exists(voice_id):
        raise AppError(f"音色不存在: {voice_id}", code="voice_not_found", status_code=404)
    spk_id = runtime_spk_id(voice_id)
    if manager.is_ready and spk_id not in manager.list_speakers():
        try:
            store.register(voice_id, manager)
        except Exception as exc:
            raise AppError(f"音色注册失败: {exc}", code="register_failed") from exc
    return spk_id


def _cleanup(paths: list[Path | None]) -> None:
    for path in paths:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:  # pragma: no cover
                pass


async def _prepare(
    *,
    mode: str,
    tts_text: str,
    spk_id: str,
    prompt_text: str,
    instruct_text: str,
    voice_id: str,
    voice_name: str,
    save_voice: bool,
    speed: float,
    seed: int | None,
    text_frontend: bool,
    stream: bool,
    prompt_wav: UploadFile | None,
    source_wav: UploadFile | None,
    settings: Settings,
    manager: ModelManager,
    store: VoiceStore,
    service: TTSService,
) -> tuple[SynthParams, list[Path | None], dict | None]:
    prompt_path = await _store_upload(prompt_wav, settings, "prompt")
    source_path = await _store_upload(source_wav, settings, "source")
    temp_files = [prompt_path, source_path]

    runtime_spk = _resolve_runtime_spk(voice_id, store, manager)
    saved_voice: dict | None = None
    # 用哪份参考音频做本次合成：默认用临时文件；若同时保存进音色库，则改用已注册的音色，
    # 避免对同一段音频重复提取特征（省一次 speech_token / mel / campplus 计算）。
    prompt_for_synth = str(prompt_path) if prompt_path else None

    if (
        not runtime_spk
        and save_voice
        and prompt_path is not None
        and mode == "zero_shot"
        and prompt_text.strip()
    ):
        saved_voice = store.create(
            name=voice_name.strip() or f"复刻音色 {datetime.now().strftime('%m%d-%H%M%S')}",
            audio_bytes=prompt_path.read_bytes(),
            original_filename=(prompt_wav.filename if prompt_wav and prompt_wav.filename else prompt_path.name),
            prompt_text=prompt_text,
            description="由「3s 极速复刻」页面自动保存",
            language="中文",
            source="upload",
        )
        try:
            store.register(saved_voice["id"], manager)
            runtime_spk = runtime_spk_id(saved_voice["id"])
            prompt_for_synth = None  # 已注册的音色内含全部提示特征
        except Exception as exc:  # 注册失败不影响本次合成，音色仍已保存
            logger.warning("音色 %s 已保存但注册失败: %s", saved_voice["id"], exc)

    if not runtime_spk:
        runtime_spk = spk_id if mode in {"sft", "instruct"} else ""

    params = service.build_params(
        mode=mode,
        tts_text=tts_text,
        spk_id=spk_id,
        prompt_text=prompt_text,
        instruct_text=instruct_text,
        prompt_wav_path=prompt_for_synth,
        source_wav_path=str(source_path) if source_path else None,
        zero_shot_spk_id=runtime_spk if mode in {"zero_shot", "cross_lingual", "instruct2"} else "",
        speed=speed,
        stream=stream,
        text_frontend=text_frontend,
        seed=seed,
    )
    return params, temp_files, saved_voice


# ------------------------------------------------------------------ 接口
@router.post("/synthesize", summary="合成语音，返回完整 WAV 文件")
async def synthesize(
    mode: str = Form("zero_shot", description="sft / zero_shot / cross_lingual / instruct2 / instruct / vc"),
    tts_text: str = Form(""),
    spk_id: str = Form(""),
    prompt_text: str = Form(""),
    instruct_text: str = Form(""),
    voice_id: str = Form("", description="音色库中的自定义音色 id"),
    save_voice: bool = Form(False, description="同时把本次上传的参考音频保存进音色库"),
    voice_name: str = Form("", description="保存音色时使用的名称，留空自动生成"),
    speed: float = Form(1.0),
    seed: int | None = Form(None),
    text_frontend: bool = Form(True),
    prompt_wav: UploadFile | None = File(None),
    source_wav: UploadFile | None = File(None),
    settings: Settings = Depends(settings_dep),
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
    service: TTSService = Depends(tts_service_dep),
) -> Response:
    params, temp_files, saved_voice = await _prepare(
        mode=mode,
        tts_text=tts_text,
        spk_id=spk_id,
        prompt_text=prompt_text,
        instruct_text=instruct_text,
        voice_id=voice_id,
        voice_name=voice_name,
        save_voice=save_voice,
        speed=speed,
        seed=seed,
        text_frontend=text_frontend,
        stream=False,
        prompt_wav=prompt_wav,
        source_wav=source_wav,
        settings=settings,
        manager=manager,
        store=store,
        service=service,
    )
    try:
        wav_bytes, result = service.synthesize_wav(params)
    finally:
        _cleanup(temp_files)

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Audio-Id": result.audio_id,
            "X-Sample-Rate": str(result.sample_rate),
            "X-Duration": str(result.duration),
            "X-Audio-Url": result.url or "",
            "X-Voice-Id": (saved_voice or {}).get("id", ""),
            "Content-Disposition": f'inline; filename="{result.audio_id}.wav"',
        },
    )


@router.post("/stream", summary="流式合成，返回 int16 PCM 分片")
async def synthesize_stream(
    mode: str = Form("zero_shot"),
    tts_text: str = Form(""),
    spk_id: str = Form(""),
    prompt_text: str = Form(""),
    instruct_text: str = Form(""),
    voice_id: str = Form(""),
    save_voice: bool = Form(False, description="同时把本次上传的参考音频保存进音色库"),
    voice_name: str = Form("", description="保存音色时使用的名称，留空自动生成"),
    speed: float = Form(1.0),
    seed: int | None = Form(None),
    text_frontend: bool = Form(True),
    prompt_wav: UploadFile | None = File(None),
    source_wav: UploadFile | None = File(None),
    settings: Settings = Depends(settings_dep),
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
    service: TTSService = Depends(tts_service_dep),
) -> StreamingResponse:
    params, temp_files, saved_voice = await _prepare(
        mode=mode,
        tts_text=tts_text,
        spk_id=spk_id,
        prompt_text=prompt_text,
        instruct_text=instruct_text,
        voice_id=voice_id,
        voice_name=voice_name,
        save_voice=save_voice,
        speed=speed,
        seed=seed,
        text_frontend=text_frontend,
        stream=True,
        prompt_wav=prompt_wav,
        source_wav=source_wav,
        settings=settings,
        manager=manager,
        store=store,
        service=service,
    )

    audio_id = uuid.uuid4().hex[:16]

    def generator() -> Iterator[bytes]:
        try:
            yield from service.stream_pcm(params, audio_id=audio_id)
        finally:
            _cleanup(temp_files)

    return StreamingResponse(
        generator(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Id": audio_id,
            "X-Audio-Url": f"/api/v1/tts/audio/{audio_id}",
            "X-Voice-Id": (saved_voice or {}).get("id", ""),
            "X-Sample-Rate": str(manager.sample_rate),
            "X-Channels": "1",
            "X-Sample-Format": "int16",
            "X-Mode": mode,
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=list[AudioItemOut], summary="历史生成记录")
def history(
    limit: int = Query(50, ge=1, le=500),
    settings: Settings = Depends(settings_dep),
) -> list[AudioItemOut]:
    files = sorted(settings.outputs_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    items: list[AudioItemOut] = []
    for path in files[:limit]:
        stat = path.stat()
        audio_id = path.stem.rsplit("_", 1)[-1]
        items.append(
            AudioItemOut(
                audio_id=audio_id,
                url=f"/api/v1/tts/audio/{audio_id}",
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                size=stat.st_size,
                filename=path.name,
            )
        )
    return items


@router.delete("/history", summary="清空全部生成记录（同时删除服务端音频文件）")
def clear_history(
    service: TTSService = Depends(tts_service_dep),
) -> dict[str, int]:
    return {"deleted": service.clear_history()}


@router.get("/audio/{audio_id}", summary="下载/播放历史音频")
def get_audio(
    audio_id: str,
    service: TTSService = Depends(tts_service_dep),
) -> FileResponse:
    path = service.audio_path(audio_id)
    return FileResponse(path, media_type="audio/wav", filename=f"{audio_id}.wav")


@router.delete("/audio/{audio_id}", status_code=204, summary="删除历史音频")
def delete_audio(
    audio_id: str,
    service: TTSService = Depends(tts_service_dep),
):
    service.audio_path(audio_id).unlink(missing_ok=True)
