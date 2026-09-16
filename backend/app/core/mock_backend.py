"""Mock 推理后端。

在没有 GPU、尚未下载权重、或前端只需要联调接口时可以完全替代真实模型：
接口行为、分片节奏、采样率字段都与真实后端保持一致，只是音频内容是
按文本长度合成的“类语音”音调，便于验证播放链路。
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator

import numpy as np

from app.core.types import SynthParams
from app.services.modes import MODE_SPECS

SAMPLE_RATE = 22050
_CHUNK_SECONDS = 0.2

_PRESET_SPEAKERS = [
    "中文女",
    "中文男",
    "英文女",
    "英文男",
    "日语男",
    "粤语女",
    "韩语女",
]


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100000


class MockBackend:
    """生成确定性、可播放的合成音频。"""

    kind = "mock"
    family = "mock"

    def __init__(self, note: str = "Mock 模式：未加载真实模型") -> None:
        self.note = note
        self.sample_rate = SAMPLE_RATE
        self._registered: dict[str, str] = {}

    # ------------------------------------------------------------ 能力查询
    def list_speakers(self) -> list[str]:
        return [*_PRESET_SPEAKERS, *sorted(self._registered)]

    def supports(self, mode: str) -> bool:
        return mode in MODE_SPECS

    # ------------------------------------------------------------ 音色注册
    def add_zero_shot_speaker(self, prompt_text: str, prompt_wav_path: str, spk_id: str) -> bool:
        self._registered[spk_id] = prompt_wav_path
        return True

    def remove_speaker(self, spk_id: str) -> None:
        self._registered.pop(spk_id, None)

    def save_speakers(self) -> None:  # 与真实后端保持接口一致
        return None

    # ---------------------------------------------------------------- 推理
    def synthesize(self, params: SynthParams) -> Iterator[np.ndarray]:
        text = params.tts_text or params.instruct_text or "mock audio"
        voice_key = params.spk_id or params.zero_shot_spk_id or (params.prompt_wav_path or "default")
        seed = params.seed if params.seed is not None else _stable_seed(params.mode, voice_key, text)

        # 语速影响时长：speed=2.0 时约缩短一半
        base = 0.22 * max(len(text), 1) / max(params.speed, 0.1)
        duration = float(np.clip(base, 0.6, 15.0))
        total = int(SAMPLE_RATE * duration)
        chunk_size = int(SAMPLE_RATE * _CHUNK_SECONDS)

        t = np.arange(total, dtype=np.float32) / SAMPLE_RATE
        rng = np.random.default_rng(seed)

        # 基频按音色偏移，叠加轻微颤动模拟语调起伏
        base_freq = 110.0 + (seed % 90)
        vibrato = 1.0 + 0.02 * np.sin(2 * math.pi * 4.5 * t)
        phase = 2 * math.pi * base_freq * np.cumsum(vibrato) / SAMPLE_RATE
        tone = (
            0.55 * np.sin(phase)
            + 0.22 * np.sin(2 * phase + 0.4)
            + 0.12 * np.sin(3 * phase + 1.1)
        )

        # 以字为单位做包络，产生“说话”的断续感
        syllable = 0.1 * max(len(text), 1) / max(params.speed, 0.1)
        envelope = 0.5 + 0.5 * np.sin(2 * math.pi * t / max(syllable, 1e-3))
        fade = np.minimum(1.0, np.minimum(t, np.maximum(duration - t, 0.0)) / 0.05)
        audio = (tone * envelope * fade * 0.35).astype(np.float32)
        audio += (rng.standard_normal(total).astype(np.float32) * 0.002 * fade).astype(np.float32)

        for start in range(0, total, chunk_size):
            yield np.ascontiguousarray(audio[start : start + chunk_size], dtype=np.float32)
