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

import pytest

from app.core.cosyvoice_backend import CosyVoiceBackend
from app.core.errors import UnsupportedModeError
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
