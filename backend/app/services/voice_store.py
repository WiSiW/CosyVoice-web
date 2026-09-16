"""自定义音色库。

存储结构::

    data/voices/<voice_id>/meta.json
    data/voices/<voice_id>/prompt.wav

音色创建后会被注册进推理运行时（``spk2info``），
注册 id 统一加 ``vo_`` 前缀，避免与预训练音色 id 冲突。
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.core.errors import InvalidAudioError, VoiceNotFoundError
from app.utils.audio import validate_audio_file

logger = logging.getLogger("app.voices")

RUNTIME_PREFIX = "vo_"
META_FILENAME = "meta.json"
AUDIO_FILENAME = "prompt.wav"

LANGUAGES = [
    "中文",
    "英语",
    "日语",
    "韩语",
    "粤语",
    "德语",
    "法语",
    "西班牙语",
    "意大利语",
    "俄语",
    "其他",
]


def runtime_spk_id(voice_id: str) -> str:
    return f"{RUNTIME_PREFIX}{voice_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceStore:
    """基于文件系统的音色仓库。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = settings.voices_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- 查询
    def list(self) -> list[dict[str, Any]]:
        voices = [self._read_meta(path) for path in self._root.glob(f"*/{META_FILENAME}")]
        voices = [voice for voice in voices if voice]
        voices.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return voices

    def get(self, voice_id: str) -> dict[str, Any]:
        meta_path = self._dir(voice_id) / META_FILENAME
        if not meta_path.exists():
            raise VoiceNotFoundError(voice_id)
        meta = self._read_meta(meta_path)
        if meta is None:
            raise VoiceNotFoundError(voice_id)
        return meta

    def prompt_path(self, voice_id: str) -> Path:
        self.get(voice_id)
        path = self._dir(voice_id) / AUDIO_FILENAME
        if not path.exists():
            raise VoiceNotFoundError(voice_id)
        return path

    def exists(self, voice_id: str) -> bool:
        try:
            self.get(voice_id)
        except VoiceNotFoundError:
            return False
        return True

    # ---------------------------------------------------------------- 创建
    def create(
        self,
        *,
        name: str,
        audio_bytes: bytes,
        original_filename: str,
        prompt_text: str = "",
        description: str = "",
        language: str = "中文",
        source: str = "upload",
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise InvalidAudioError("音色名称不能为空")
        if not audio_bytes:
            raise InvalidAudioError("参考音频为空，请重新上传或录制")

        voice_id = uuid.uuid4().hex[:12]
        target_dir = self._dir(voice_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        audio_path = target_dir / AUDIO_FILENAME

        try:
            audio_path.write_bytes(audio_bytes)
            info = validate_audio_file(
                audio_path,
                filename=original_filename,
                max_seconds=self._settings.max_prompt_seconds,
                min_seconds=self._settings.min_prompt_seconds,
            )
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

        meta = {
            "id": voice_id,
            "name": name,
            "description": description.strip(),
            "prompt_text": prompt_text.strip(),
            "language": language,
            "source": source,
            "created_at": _now(),
            "updated_at": _now(),
            "audio": {
                "filename": AUDIO_FILENAME,
                "original_filename": original_filename,
                "duration": round(info.duration, 3),
                "sample_rate": info.sample_rate,
                "channels": info.channels,
                "format": info.format,
                "size": len(audio_bytes),
            },
        }
        self._write_meta(meta)
        logger.info("创建音色 %s (%s)", voice_id, name)
        return meta

    # ---------------------------------------------------------------- 更新
    def update(self, voice_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            meta = self.get(voice_id)
            for key in ("name", "description", "prompt_text", "language"):
                if key in fields and fields[key] is not None:
                    meta[key] = str(fields[key]).strip()
            if not meta["name"]:
                raise InvalidAudioError("音色名称不能为空")
            meta["updated_at"] = _now()
            self._write_meta(meta)
        return meta

    # ---------------------------------------------------------------- 删除
    def delete(self, voice_id: str) -> None:
        with self._lock:
            directory = self._dir(voice_id)
            if not directory.exists():
                raise VoiceNotFoundError(voice_id)
            shutil.rmtree(directory, ignore_errors=True)
        logger.info("删除音色 %s", voice_id)

    # -------------------------------------------------------- 与运行时交互
    def register(self, voice_id: str, model_manager) -> bool:  # noqa: ANN001
        meta = self.get(voice_id)
        prompt_text = meta.get("prompt_text") or ""
        if not prompt_text:
            raise InvalidAudioError("注册到运行时需要提供参考文本，请先补充「参考文本」")
        ok = model_manager.add_zero_shot_speaker(
            prompt_text, str(self.prompt_path(voice_id)), runtime_spk_id(voice_id)
        )
        if ok:
            logger.info("音色 %s 已注册到运行时", voice_id)
        return ok

    def unregister(self, voice_id: str, model_manager) -> None:  # noqa: ANN001
        model_manager.remove_speaker(runtime_spk_id(voice_id))

    def register_all(self, model_manager) -> int:  # noqa: ANN001
        """把库内音色批量注册进运行时，返回成功数量。"""
        count = 0
        for meta in self.list():
            try:
                if self.register(meta["id"], model_manager):
                    count += 1
            except Exception as exc:
                logger.warning("音色 %s 注册失败: %s", meta.get("id"), exc)
        return count

    # ---------------------------------------------------------------- 内部
    def _dir(self, voice_id: str) -> Path:
        safe = "".join(ch for ch in voice_id if ch.isalnum() or ch in "-_")
        if safe != voice_id or not safe:
            raise VoiceNotFoundError(voice_id)
        return self._root / safe

    def _read_meta(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception as exc:
            logger.warning("读取音色元数据失败 %s: %s", path, exc)
            return None

    def _write_meta(self, meta: dict[str, Any]) -> None:
        target = self._dir(meta["id"]) / META_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
