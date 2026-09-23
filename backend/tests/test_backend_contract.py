"""与上游 CosyVoice API 的契约回归测试。

这里锁住两个曾经踩坑的点：

1. ``prompt_wav`` 必须传**文件路径**。
   当前上游的 ``CosyVoiceFrontEnd`` 会在 ``_extract_speech_feat``(24kHz)、
   ``_extract_speech_token``(16kHz)、``_extract_spk_embedding``(16kHz)
   里各自重新调用一次 ``load_wav()``，传预先加载好的 tensor 会抛
   ``TypeError: Invalid file: tensor(...)``。
   （上游 ``runtime/python/fastapi/server.py`` 仍是旧写法，不能照抄。）

2. 没有内置预训练音色的模型（CosyVoice2 / CosyVoice3）必须把
   ``sft`` 模式标记为不可用，否则 ``frontend_sft`` 会 KeyError。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.cosyvoice_backend import CosyVoiceBackend
from app.core.errors import UnsupportedModeError
from app.core.types import SynthParams
from app.services.modes import mode_specs_payload


def _modes(family, speakers):
    return {item["id"]: item for item in mode_specs_payload(family, speakers=speakers)}


# --------------------------------------------------- prompt_wav 必须是路径
def test_prompt_path_returns_plain_path(tmp_path: Path):
    prompt = tmp_path / "prompt.wav"
    prompt.write_bytes(b"RIFF....WAVE")

    result = CosyVoiceBackend._prompt_path(str(prompt))

    assert isinstance(result, str), "必须返回路径字符串，不能是 tensor / 数组"
    assert result == str(prompt)


def test_prompt_path_rejects_missing_file(tmp_path: Path):
    with pytest.raises(UnsupportedModeError):
        CosyVoiceBackend._prompt_path(str(tmp_path / "not-exists.wav"))


def test_prompt_path_rejects_empty_value():
    with pytest.raises(UnsupportedModeError):
        CosyVoiceBackend._prompt_path(None)
    with pytest.raises(UnsupportedModeError):
        CosyVoiceBackend._prompt_path("")


# ------------------------------------------------- 预训练音色的可用性判定
def test_sft_disabled_when_model_has_no_preset_speakers():
    modes = _modes("CosyVoice2", speakers=[])
    assert modes["sft"]["available"] is False
    assert "spk2info" in modes["sft"]["note"]
    # 其他模式不受影响
    assert modes["zero_shot"]["available"] is True
    assert modes["cross_lingual"]["available"] is True


def test_sft_available_when_preset_speakers_exist():
    modes = _modes("CosyVoice", speakers=["中文女"])
    assert modes["sft"]["available"] is True


def test_sft_not_disabled_while_model_is_unloaded():
    """音色列表未知时不应误禁用（模型还没加载）。"""
    modes = _modes(None, speakers=None)
    assert modes["sft"]["available"] is True


def test_v1_only_modes_follow_model_family():
    cosyvoice2 = _modes("CosyVoice2", speakers=[])
    assert cosyvoice2["instruct"]["available"] is False
    assert cosyvoice2["instruct2"]["available"] is True
    assert cosyvoice2["vc"]["available"] is False

    cosyvoice1 = _modes("CosyVoice", speakers=["中文女"])
    assert cosyvoice1["instruct"]["available"] is True
    assert cosyvoice1["vc"]["available"] is True


# ------------------------------- 使用"已注册音色"时的参数传递（真实后端路径）
class _RecordingModel:
    """记录上游被调用时收到的参数，用于验证参数编组。"""

    sample_rate = 24000

    def __init__(self, speakers=("vo_abc",)):
        self.calls: dict[str, tuple] = {}
        self._speakers = list(speakers)

    def list_available_spks(self):
        return self._speakers

    def _yield(self):
        return iter([{"tts_speech": np.zeros((1, 2400), dtype=np.float32)}])

    def inference_zero_shot(self, tts_text, prompt_text, prompt_wav, **kwargs):
        self.calls["zero_shot"] = (tts_text, prompt_text, prompt_wav, kwargs)
        return self._yield()

    def inference_cross_lingual(self, tts_text, prompt_wav, **kwargs):
        self.calls["cross_lingual"] = (tts_text, prompt_wav, kwargs)
        return self._yield()

    def inference_instruct2(self, tts_text, instruct_text, prompt_wav, **kwargs):
        self.calls["instruct2"] = (tts_text, instruct_text, prompt_wav, kwargs)
        return self._yield()


def _backend_with(model):
    backend = object.__new__(CosyVoiceBackend)
    backend._model = model
    backend.family = "CosyVoice2"
    backend.sample_rate = 24000
    backend.model_dir = "/tmp"
    return backend


@pytest.mark.parametrize("mode", ["zero_shot", "cross_lingual", "instruct2"])
def test_registered_voice_passes_empty_prompt_wav(mode):
    """用已注册音色时不能再要求参考音频路径，必须传空字符串。

    曾经这里无条件解析路径，导致"从音色库选音色合成"直接报
    「缺少参考音频」，整条音色库链路不可用。
    """
    model = _RecordingModel()
    backend = _backend_with(model)

    params = SynthParams(
        mode=mode,
        tts_text="你好",
        prompt_text="参考文本",
        instruct_text="用四川话说",
        prompt_wav_path=None,          # 没有上传参考音频
        zero_shot_spk_id="vo_abc",     # 改用音色库里的音色
    )
    list(backend.synthesize(params))

    call = model.calls[mode]
    assert call[-1]["zero_shot_spk_id"] == "vo_abc"
    # 各模式下 prompt_wav 的位置不同，但都必须是空字符串
    prompt_wav = call[2] if mode != "cross_lingual" else call[1]
    assert prompt_wav == "", f"{mode} 应传空字符串，实际收到 {prompt_wav!r}"


def test_zero_shot_without_registered_voice_still_requires_prompt(tmp_path):
    """没有注册音色时，缺少参考音频仍然要报错。"""
    prompt = tmp_path / "p.wav"
    prompt.write_bytes(b"RIFF")
    model = _RecordingModel()
    backend = _backend_with(model)

    with pytest.raises(UnsupportedModeError):
        list(backend.synthesize(SynthParams(mode="zero_shot", tts_text="你好", prompt_wav_path=None)))

    # 传了路径则正常透传
    list(backend.synthesize(SynthParams(mode="zero_shot", tts_text="你好", prompt_wav_path=str(prompt))))
    assert model.calls["zero_shot"][2] == str(prompt)
