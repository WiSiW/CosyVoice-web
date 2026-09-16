"""HTTP 层的数据契约（OpenAPI 文档由这些模型生成）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """所有响应模型的基类，放开 pydantic 的 ``model_`` 保留前缀。"""

    model_config = ConfigDict(protected_namespaces=())


class HealthOut(ApiModel):
    status: str = Field(examples=["ok"])
    app: str
    version: str
    model_state: str = Field(description="unloaded / loading / ready / error")


class ModelStatusOut(ApiModel):
    state: str
    kind: str | None = None
    family: str | None = None
    sample_rate: int | None = None
    note: str | None = None
    model_dir: str
    model_source: str
    mock: bool
    error: str | None = None
    loaded_at: str | None = None
    load_seconds: float | None = None
    inference_queue: int = 0


class SystemInfoOut(ApiModel):
    app: str
    version: str
    api_prefix: str
    model: ModelStatusOut
    speakers: list[str]
    voices: int
    limits: dict[str, Any]
    languages: list[str]


class ModeOut(ApiModel):
    id: str
    label: str
    description: str
    fields: list[str]
    field_labels: dict[str, str]
    supports_stream: bool
    supports_speed: bool
    required_family: str | None = None
    note: str = ""
    available: bool


class VoiceAudioOut(ApiModel):
    filename: str
    original_filename: str | None = None
    duration: float
    sample_rate: int
    channels: int
    format: str
    size: int


class VoiceOut(ApiModel):
    id: str
    name: str
    description: str = ""
    prompt_text: str = ""
    language: str = "中文"
    source: str = "upload"
    created_at: str
    updated_at: str
    audio: VoiceAudioOut
    registered: bool = False
    builtin: bool = False
    runtime_spk_id: str | None = None


class VoiceUpdateIn(ApiModel):
    name: str | None = None
    description: str | None = None
    prompt_text: str | None = None
    language: str | None = None


class SynthesisMeta(ApiModel):
    audio_id: str
    mode: str
    sample_rate: int
    duration: float
    rtf: float | None = None
    channel: str = Field(default="wav", description="wav=完整音频文件, pcm=流式 int16 PCM")
    url: str | None = None


class AudioItemOut(ApiModel):
    audio_id: str
    url: str
    created_at: str
    size: int
    filename: str


class ErrorOut(ApiModel):
    error: dict[str, Any]
