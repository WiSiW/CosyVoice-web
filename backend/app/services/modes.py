"""合成模式元数据。

前端通过 ``GET /api/v1/tts/modes`` 拿到这份描述后动态渲染表单，
后端校验与推理分发也复用同一份定义，避免前后端字段漂移。
"""

from __future__ import annotations

from app.core.types import ModeSpec

MODE_SPECS: dict[str, ModeSpec] = {
    "sft": ModeSpec(
        id="sft",
        label="预训练音色",
        description="使用模型内置的预训练说话人，输入文本即可合成。",
        fields=["text", "speaker"],
        required_family=None,
    ),
    "zero_shot": ModeSpec(
        id="zero_shot",
        label="3s 极速复刻",
        description="上传 3~30 秒参考音频，并填写与音频一致的参考文本，即可复刻音色。",
        fields=["text", "prompt_text", "prompt_audio"],
        required_family=None,
    ),
    "cross_lingual": ModeSpec(
        id="cross_lingual",
        label="跨语种复刻",
        description="只上传参考音频，无需参考文本，可跨语种合成目标文本。",
        fields=["text", "prompt_audio"],
        required_family=None,
    ),
    "instruct2": ModeSpec(
        id="instruct2",
        label="自然语言控制",
        description="用自然语言指令控制方言、情感、语速、音量等风格（CosyVoice 2.0 / 3.0）。",
        fields=["text", "instruct_text", "prompt_audio"],
        required_family=None,
        note="指令需以 <|endofprompt|> 结尾，例如：用四川话说这句话<|endofprompt|>",
    ),
    "instruct": ModeSpec(
        id="instruct",
        label="自然语言控制 (1.0)",
        description="基于预训练音色 + 指令文本的风格控制（仅 CosyVoice 1.0 Instruct 模型）。",
        fields=["text", "speaker", "instruct_text"],
        required_family="CosyVoice",
        note="需要 CosyVoice-300M-Instruct 模型",
    ),
    "vc": ModeSpec(
        id="vc",
        label="音色转换",
        description="把一段源音频的音色转换成目标参考音频的音色（仅 CosyVoice 1.0）。",
        fields=["source_audio", "prompt_audio"],
        supports_stream=False,
        supports_speed=False,
        required_family="CosyVoice",
        note="需要 CosyVoice-300M (25hz) 模型",
    ),
}

# 字段 -> 前端渲染语义
FIELD_LABELS: dict[str, str] = {
    "text": "合成文本",
    "speaker": "预训练音色",
    "prompt_text": "参考文本",
    "prompt_audio": "参考音频",
    "source_audio": "源音频",
    "instruct_text": "指令文本",
}


NO_PRESET_SPEAKER_NOTE = (
    "当前模型没有内置预训练音色（spk2info 为空）。"
    "CosyVoice2 / CosyVoice3 系列都没有预置音色，请改用「3s 极速复刻」上传一段参考音频，"
    "或换成 iic/CosyVoice-300M-SFT 模型。"
)

LIBRARY_VOICE_NOTE = "当前模型没有内置预训练音色，可使用音色库中的自定义音色。"


def mode_specs_payload(
    family: str | None = None,
    speakers: list[str] | None = None,
    custom_voice_count: int = 0,
) -> list[dict]:
    """返回给前端的模式列表，附带当前模型下的可用性。

    ``speakers`` 为 ``None`` 表示"模型尚未加载、音色列表未知"，
    此时不做预训练音色的可用性判断，避免误禁用。
    """
    payload: list[dict] = []
    for spec in MODE_SPECS.values():
        available = spec.required_family is None or spec.required_family == family
        note = spec.note

        if spec.id == "sft" and speakers is not None:
            has_preset = bool(speakers)
            has_custom = custom_voice_count > 0
            if not has_preset and not has_custom:
                available = False
                note = NO_PRESET_SPEAKER_NOTE
            elif not has_preset:
                note = LIBRARY_VOICE_NOTE

        payload.append(
            {
                "id": spec.id,
                "label": spec.label,
                "description": spec.description,
                "fields": spec.fields,
                "field_labels": {name: FIELD_LABELS.get(name, name) for name in spec.fields},
                "supports_stream": spec.supports_stream,
                "supports_speed": spec.supports_speed,
                "required_family": spec.required_family,
                "note": note,
                "available": available,
            }
        )
    return payload


def get_spec(mode: str) -> ModeSpec | None:
    return MODE_SPECS.get(mode)
