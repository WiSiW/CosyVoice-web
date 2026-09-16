"""跨层共享的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Literal

import numpy as np

ModeId = Literal["sft", "zero_shot", "cross_lingual", "instruct", "instruct2", "vc", "vc2"]
PcmArray = np.ndarray  # float32, 取值范围 [-1, 1]，形状 (T,)


@dataclass(slots=True)
class SynthParams:
    """一次语音合成请求所需的全部参数。"""

    mode: ModeId
    tts_text: str = ""
    # 预训练音色 id 或已注册的 zero-shot 音色 id
    spk_id: str = ""
    prompt_text: str = ""
    instruct_text: str = ""
    # 本地音频文件路径
    prompt_wav_path: str | None = None
    source_wav_path: str | None = None
    zero_shot_spk_id: str = ""
    speed: float = 1.0
    stream: bool = True
    text_frontend: bool = True
    seed: int | None = None

    def __post_init__(self) -> None:
        self.tts_text = self.tts_text.strip()
        self.prompt_text = self.prompt_text.strip()
        self.instruct_text = self.instruct_text.strip()


@dataclass(slots=True)
class AudioChunk:
    """流式返回的音频分片。"""

    samples: PcmArray
    sample_rate: int


@dataclass(slots=True)
class ModeSpec:
    """描述一种合成模式，供前端动态渲染表单。"""

    id: str
    label: str
    description: str
    # 需要前端提供的字段：text / speaker / prompt_text / prompt_audio / source_audio / instruct_text
    fields: list[str] = field(default_factory=list)
    supports_stream: bool = True
    supports_speed: bool = True
    # 需要的模型族，None 表示任意模型都支持
    required_family: str | None = None
    note: str = ""
