"""音色库的预置朗读文本。

为什么需要它
------------
复刻音色时要同时提供「参考音频」和「参考文本」，二者在上游的分工是：

* **声纹来自音频**：``CosyVoiceFrontEnd._extract_spk_embedding()`` 只用 ``prompt_wav``
  计算 fbank，再经 campplus 得到 192 维说话人向量；文本完全不参与。
* **参考文本用于音-文对齐**：``prompt_text`` 会被 tokenize 后作为 LLM 的文本侧提示，
  与音频侧的 speech token 对齐。**文本与音频内容不一致会直接破坏对齐，明显拉低相似度**。

因此"预置文本"的正确形态是**朗读稿**：让用户照着念，文本与音频天然逐字一致。
若用户上传的是一段已有录音，则必须填该录音的真实内容，**不能**套用预置文本。

文本选取原则
------------
1. 纯文字，不含数字/拉丁字母/特殊符号 —— 避免文本正则化把"2024"改写成"二零二四"
   之后与音频对不上；
2. 长度适中（朗读约 6~9 秒）：太短声纹样本不足，太长会让上游在"合成文本远短于
   参考文本"时给出质量警告，用户念起来也累；
3. 覆盖较广的声母/韵母/声调与连读，语句自然，便于念出正常语调。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoicePreset:
    language: str
    text: str
    target_seconds: float
    note: str = "照着朗读即可保证文本与音频逐字一致"


_GENERIC_NOTE = "照着朗读即可保证文本与音频逐字一致"

VOICE_PRESETS: dict[str, VoicePreset] = {
    "中文": VoicePreset(
        language="中文",
        text="大家好，欢迎使用语音合成系统。今天的天气很不错，我们一起去公园散步吧。",
        target_seconds=7.0,
        note=_GENERIC_NOTE,
    ),
    "英语": VoicePreset(
        language="英语",
        text=(
            "Hello, welcome to the voice cloning system. "
            "The weather is really nice today, so let us take a walk in the park together."
        ),
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
    "日语": VoicePreset(
        language="日语",
        text="こんにちは、音声合成システムへようこそ。今日はとても良い天気ですね、一緒に公園を散歩しましょう。",
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
    "韩语": VoicePreset(
        language="韩语",
        text="안녕하세요, 음성 합성 시스템에 오신 것을 환영합니다. 오늘 날씨가 정말 좋네요, 함께 공원을 산책해요.",
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
    "粤语": VoicePreset(
        language="粤语",
        text="你好，歡迎使用語音合成系統。今日天氣好好，不如一齊去公園行下啦。",
        target_seconds=7.0,
        note=_GENERIC_NOTE,
    ),
    "德语": VoicePreset(
        language="德语",
        text=(
            "Hallo und willkommen beim Sprachsynthesesystem. "
            "Das Wetter ist heute wirklich schön, gehen wir zusammen im Park spazieren."
        ),
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
    "法语": VoicePreset(
        language="法语",
        text=(
            "Bonjour et bienvenue dans le système de synthèse vocale. "
            "Il fait très beau aujourd'hui, allons nous promener ensemble dans le parc."
        ),
        target_seconds=8.5,
        note=_GENERIC_NOTE,
    ),
    "西班牙语": VoicePreset(
        language="西班牙语",
        text=(
            "Hola y bienvenido al sistema de síntesis de voz. "
            "Hoy hace muy buen tiempo, vamos a dar un paseo juntos por el parque."
        ),
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
    "意大利语": VoicePreset(
        language="意大利语",
        text=(
            "Ciao e benvenuto nel sistema di sintesi vocale. "
            "Oggi il tempo è davvero bello, andiamo insieme a fare una passeggiata nel parco."
        ),
        target_seconds=8.5,
        note=_GENERIC_NOTE,
    ),
    "俄语": VoicePreset(
        language="俄语",
        text=(
            "Здравствуйте и добро пожаловать в систему синтеза речи. "
            "Сегодня отличная погода, давайте вместе прогуляемся по парку."
        ),
        target_seconds=8.0,
        note=_GENERIC_NOTE,
    ),
}

# 「其他」等没有预置稿的语言：给出编写建议而不是硬塞一段不对应语言的文本
FALLBACK_NOTE = (
    "该语言暂无预置稿，请填写与参考音频完全一致的内容；"
    "建议选一段 6~9 秒、语句自然的文字照着朗读"
)


def preset_payload() -> list[dict]:
    """返回给前端的预置稿列表。"""
    return [
        {
            "language": preset.language,
            "text": preset.text,
            "target_seconds": preset.target_seconds,
            "note": preset.note,
        }
        for preset in VOICE_PRESETS.values()
    ]


def get_preset(language: str) -> VoicePreset | None:
    return VOICE_PRESETS.get(language)
