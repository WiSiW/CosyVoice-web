"""模型生命周期管理。

对外只暴露一个 :class:`ModelManager`，负责：

* 懒加载 / 手动加载 / 卸载模型；
* 记录运行状态供 ``/system/info`` 返回；
* 串行化推理调用（上游 model.tts 不是线程安全的）。

本模块**没有任何模拟推理路径**：模型加载失败时状态置为 ``error`` 并保留原因，
调用方（HTTP 层）据此返回明确错误，绝不会退回"假音频"。
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

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def status(self) -> dict[str, Any]:
        backend = self._backend
        return {
            "state": self._state,
            "kind": getattr(backend, "kind", None),
            "device": self._detect_device(),
            "family": getattr(backend, "family", None),
            "sample_rate": getattr(backend, "sample_rate", None),
            "note": getattr(backend, "note", None),
            "model_dir": self._settings.resolved_model_dir,
            "model_source": self._settings.model_source,
            "error": self._error,
            "loaded_at": self._loaded_at,
            "load_seconds": self._load_seconds,
            "inference_queue": self._inference_waiting,
        }

    def modes_payload(self, *, custom_voice_count: int = 0) -> list[dict]:
        if not self.is_ready:
            # 模型未加载：音色列表未知，不做可用性推断
            return mode_specs_payload(None, speakers=None)
        return mode_specs_payload(
            getattr(self._backend, "family", None),
            speakers=self.list_speakers(),
            custom_voice_count=custom_voice_count,
        )

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
        # 已经失败过就不要在每次请求里反复重试（可能很慢甚至触发下载），
        # 直接把错误原因返回给调用方，由用户显式点击"加载模型"重试。
        if self._state == "error":
            raise ModelNotReadyError(self._not_ready_message())
        if self._state == "unloaded":
            self.load()
        return self.backend

    # ------------------------------------------------------------ 构造后端
    def _build_backend(self):
        """构建真实推理后端。

        这里不捕获异常：加载失败必须让调用方看到真实原因，
        由 :meth:`load` 统一记录为 ``error`` 状态。
        """
        settings = self._settings
        from app.core.cosyvoice_backend import CosyVoiceBackend

        return CosyVoiceBackend(
            repo_dir=settings.resolved_cosyvoice_repo,
            model_dir=settings.resolved_model_dir,
            load_jit=settings.load_jit,
            load_trt=settings.load_trt,
            load_vllm=settings.load_vllm,
            fp16=settings.fp16,
        )

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

    def has_speaker(self, spk_id: str) -> bool:
        if not self.is_ready:
            return False
        try:
            return bool(self._backend.has_speaker(spk_id))
        except Exception as exc:
            logger.warning("检查音色失败 %s: %s", spk_id, exc)
            return False

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

    def extract_speaker_embedding(self, prompt_wav_path: str):
        backend = self.ensure_ready()
        with self.inference_guard():
            return backend.extract_speaker_embedding(prompt_wav_path)

    def list_speaker_embeddings(self) -> dict[str, Any]:
        if not self.is_ready:
            return {}
        return dict(self._backend.list_speaker_embeddings())

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
