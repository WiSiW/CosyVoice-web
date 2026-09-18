from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.model_manager import ModelManager
from app.main import create_app
from tests.stub_backend import StubBackend


def make_wav_bytes(seconds: float = 3.0, sample_rate: int = 16000, freq: float = 220.0) -> bytes:
    """生成一段正弦波 WAV，作为测试用参考音频。"""
    t = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    samples = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        cosyvoice_repo=tmp_path / "CosyVoice",
        log_level="WARNING",
    )


@pytest.fixture()
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    """注入测试桩后端，使 HTTP 层无需 GPU 与模型权重即可被覆盖。

    应用本身没有任何模拟推理路径，这里替换的是 ModelManager 的内部工厂方法。
    """
    monkeypatch.setattr(ModelManager, "_build_backend", lambda self: StubBackend())
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def wav_bytes() -> bytes:
    return make_wav_bytes()
