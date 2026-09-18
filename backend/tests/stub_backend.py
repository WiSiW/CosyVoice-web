"""仅用于测试的桩后端（test double）。

⚠️ 重要说明
-----------
本文件位于 ``tests/`` 目录，**不会**被打包进应用，运行时的代码路径中
**不存在任何**"加载失败就返回模拟音频"的逻辑 —— 模型加载失败一律报错。

它存在的唯一目的，是让 HTTP 层（路由、参数校验、流式分片、结果落盘、
历史记录、音色 CRUD）能够在没有 GPU 和模型权重的 CI 环境里被完整覆盖。
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from app.core.types import SynthParams
from app.services.modes import MODE_SPECS

SAMPLE_RATE = 22050
DEFAULT_SPEAKERS = ["中文女", "英文女"]


class StubBackend:
    """确定性的最小后端实现，接口与 CosyVoiceBackend 保持一致。"""

    kind = "stub"
    note = "测试桩后端（不会出现在运行时）"

    def __init__(self, family: str = "CosyVoice2", speakers: list[str] | None = None) -> None:
        self.family = family
        self.sample_rate = SAMPLE_RATE
        self._speakers = list(DEFAULT_SPEAKERS if speakers is None else speakers)
        self._registered: dict[str, str] = {}

    # ------------------------------------------------------------ 能力查询
    def list_speakers(self) -> list[str]:
        return [*self._speakers, *sorted(self._registered)]

    def supports(self, mode: str) -> bool:
        if mode not in MODE_SPECS:
            return False
        if mode == "sft":
            return bool(self.list_speakers())
        return True

    # ------------------------------------------------------------ 音色注册
    def add_zero_shot_speaker(self, prompt_text: str, prompt_wav_path: str, spk_id: str) -> bool:
        self._registered[spk_id] = prompt_wav_path
        return True

    def remove_speaker(self, spk_id: str) -> None:
        self._registered.pop(spk_id, None)

    def save_speakers(self) -> None:
        return None

    # ---------------------------------------------------------------- 推理
    def synthesize(self, params: SynthParams) -> Iterator[np.ndarray]:
        """产出 1 秒、3 个分片的确定性波形，用于验证流式与落盘链路。"""
        total = SAMPLE_RATE
        t = np.arange(total, dtype=np.float32) / SAMPLE_RATE
        wave = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        step = total // 3
        for start in range(0, total, step):
            yield np.ascontiguousarray(wave[start : start + step])
