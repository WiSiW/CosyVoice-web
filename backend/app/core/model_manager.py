"""模型生命周期管理。

对外只暴露一个 :class:`ModelManager`，负责：

* 懒加载 / 手动加载 / 卸载真实模型；
* 在缺少依赖或显式开启 Mock 时自动降级为 :class:`MockBackend`；
* 记录运行状态供 ``/system/info`` 返回；
* 串行化推理调用（上游 model.tts 不是线程安全的）。
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.config import Settings
from app.core.errors import ModelNotReadyError
from app.core.mock_backend import MockBackend
from app.core.types import SynthParams
from app.services.modes import mode_specs_payload

logger = logging.getLogger("app.model")


class ModelManager:
    """线程安全的模型管理器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._backend: Any | None = None
        self._state: str = "unloaded"
        self._error: str | None = None
        self._loaded_at: str | None = None
        self._load_seconds: float | None = None
        self._lock = threading.RLock()
        # 推理串行化：同一时刻只允许一个合成任务占用 GPU
        self._inference_lock = threading.BoundedSemaphore(1)
        self._inference_waiting = 0

    # ------------------------------------------------------------ 状态查询
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state == "ready" and self._backend is not None

    @property
    def sample_rate(self) -> int:
        return int(getattr(self._backend, "sample_rate", 22050))

    @property
    def backend(self) -> Any:
        if not self.is_ready:
            raise ModelNotReadyError(self._not_ready_message())
        return self._backend

    def _not_ready_message(self) -> str:
        if self._state == "error":
            return f"模型加载失败: {self._error}"
        if self._state == "loading":
            return "模型正在加载中，请稍候重试"
        return "模型尚未加载，请先调用 POST /api/v1/system/load"

    def status(self) -> dict[str, Any]:
        backend = self._backend
        return {
            "state": self._state,
            "kind": getattr(backend, "kind", None),
            "family": getattr(backend, "family", None),
            "sample_rate": getattr(backend, "sample_rate", None),
            "note": getattr(backend, "note", None),
            "model_dir": self._settings.model_dir,
            "model_source": self._settings.model_source,
            "mock": self._state == "ready" and getattr(backend, "kind", None) == "mock",
            "error": self._error,
            "loaded_at": self._loaded_at,
            "load_seconds": self._load_seconds,
            "inference_queue": self._inference_waiting,
        }

    def modes_payload(self) -> list[dict]:
        if not self.is_ready:
            return mode_specs_payload(None)
        backend = self._backend
        # Mock 后端不区分配置，所有模式都按可用返回，方便前端联调
        family = None if getattr(backend, "kind", None) == "mock" else getattr(backend, "family", None)
        return mode_specs_payload(family)

    # ------------------------------------------------------------ 加载控制
    def load(self, *, force: bool = False) -> dict[str, Any]:
        """同步加载模型；重复调用是幂等的。"""
        with self._lock:
            if self._state == "ready" and not force:
                return self.status()

            self._state = "loading"
            self._error = None
            started = time.perf_counter()
            try:
                self._backend = self._build_backend()
                self._state = "ready"
                self._loaded_at = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                self._backend = None
                self._state = "error"
                self._error = str(exc)
                logger.exception("模型加载失败")
            finally:
                self._load_seconds = round(time.perf_counter() - started, 3)
            logger.info("模型状态: %s (%.2fs)", self._state, self._load_seconds or 0.0)
            return self.status()

    def unload(self) -> dict[str, Any]:
        with self._lock:
            self._backend = None
            self._state = "unloaded"
            self._error = None
            self._loaded_at = None
            self._load_seconds = None
        import gc

        gc.collect()
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        logger.info("模型已卸载")
        return self.status()

    def ensure_ready(self) -> Any:
        """确保模型可用；未加载时按需加载。"""
        if self.is_ready:
            return self._backend
        if self._state in ("unloaded", "error"):
            self.load(force=self._state == "error")
        return self.backend

    # ------------------------------------------------------------ 构造后端
    def _build_backend(self):
        settings = self._settings
        if settings.mock:
            logger.warning("CV_MOCK=true，使用 Mock 后端（不加载真实模型）")
            return MockBackend()

        try:
            from app.core.cosyvoice_backend import CosyVoiceBackend

            return CosyVoiceBackend(
                repo_dir=settings.resolved_cosyvoice_repo,
                model_dir=settings.model_dir,
                load_jit=settings.load_jit,
                load_trt=settings.load_trt,
                load_vllm=settings.load_vllm,
                fp16=settings.fp16,
            )
        except Exception as exc:
            if settings.mock:
                raise
            logger.error("真实模型加载失败，自动降级为 Mock 后端: %s", exc)
            return MockBackend(note=f"真实模型不可用，已降级: {exc}")

    # ------------------------------------------------------------ 推理串行化
    @contextmanager
    def inference_guard(self) -> Iterator[None]:
        self._inference_waiting += 1
        acquired = self._inference_lock.acquire()
        self._inference_waiting -= 1
        try:
            yield
        finally:
            if acquired:
                self._inference_lock.release()

    # ------------------------------------------------------------ 能力委托
    def list_speakers(self) -> list[str]:
        if not self.is_ready:
            return []
        try:
            return list(self._backend.list_speakers())
        except Exception as exc:
            logger.warning("获取预训练音色失败: %s", exc)
            return []

    def supports(self, mode: str) -> bool:
        if not self.is_ready:
            return True
        return bool(self._backend.supports(mode))

    def synthesize(self, params: SynthParams) -> Iterator:
        backend = self.ensure_ready()
        with self.inference_guard():
            yield from backend.synthesize(params)

    def add_zero_shot_speaker(self, prompt_text: str, prompt_wav_path: str, spk_id: str) -> bool:
        backend = self.ensure_ready()
        return bool(backend.add_zero_shot_speaker(prompt_text, prompt_wav_path, spk_id))

    def remove_speaker(self, spk_id: str) -> None:
        if not self.is_ready:
            return
        try:
            self._backend.remove_speaker(spk_id)
        except Exception as exc:
            logger.warning("移除音色失败 %s: %s", spk_id, exc)

    def save_speakers(self) -> None:
        if not self.is_ready:
            return
        try:
            self._backend.save_speakers()
        except Exception as exc:
            logger.warning("保存音色失败: %s", exc)
