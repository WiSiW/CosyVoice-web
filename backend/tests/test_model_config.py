"""模型目录解析 + "加载失败必须如实报错" 的回归测试。

背景：曾经因为把不存在的本地路径当成 ModelScope 仓库 id 去下载，并在异常时
静默降级为模拟后端，导致用户拿到的是蜂鸣音却毫无察觉。现已彻底移除模拟后端，
本文件锁定下面两条不变量：

1. ``CV_MODEL_DIR`` 的两种写法（本地路径 / ModelScope 仓库 id）必须被正确区分；
2. 模型加载失败时状态必须是 ``error`` 并携带可读原因，调用方拿到明确错误，
   绝不会有任何"假音频"兜底。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import BACKEND_DIR, Settings
from app.core.errors import ModelNotReadyError
from app.core.model_manager import ModelManager


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        data_dir=tmp_path / "data",
        cosyvoice_repo=tmp_path / "CosyVoice",
        log_level="WARNING",
    )
    base.update(overrides)
    return Settings(**base)


# ------------------------------------------------------------ 目录解析
def test_repo_id_is_kept_as_is(tmp_path):
    settings = make_settings(tmp_path, model_dir="iic/CosyVoice2-0.5B")
    assert settings.resolved_model_dir == "iic/CosyVoice2-0.5B"
    assert settings.model_source == "remote"


def test_relative_path_resolves_against_backend_dir(tmp_path):
    settings = make_settings(tmp_path, model_dir="../CosyVoice/pretrained_models/CosyVoice2-0.5B")
    resolved = Path(settings.resolved_model_dir)
    assert resolved.is_absolute()
    assert resolved.name == "CosyVoice2-0.5B"
    assert resolved == (BACKEND_DIR / "../CosyVoice/pretrained_models/CosyVoice2-0.5B").resolve()
    assert settings.model_source == "local"


def test_existing_directory_is_recognised_as_path(tmp_path):
    model_dir = tmp_path / "my-model"
    model_dir.mkdir()
    settings = make_settings(tmp_path, model_dir=str(model_dir))
    assert settings.resolved_model_dir == str(model_dir)


def test_repo_relative_dir_is_resolved_to_cosyvoice_repo(tmp_path):
    """上游示例写法 pretrained_models/xxx 应相对 CosyVoice 仓库解析。"""
    repo = tmp_path / "CosyVoice"
    (repo / "pretrained_models" / "CosyVoice2-0.5B").mkdir(parents=True)
    settings = make_settings(tmp_path, cosyvoice_repo=repo, model_dir="pretrained_models/CosyVoice2-0.5B")
    assert Path(settings.resolved_model_dir) == (repo / "pretrained_models" / "CosyVoice2-0.5B").resolve()


def test_ambiguous_two_level_name_falls_back_to_repo_id(tmp_path):
    """两段式且本地不存在时按 ModelScope 仓库 id 处理（与 namespace/name 同形）。"""
    settings = make_settings(tmp_path, model_dir="someorg/somemodel")
    assert settings.resolved_model_dir == "someorg/somemodel"
    assert settings.model_source == "remote"


# --------------------------------------------- 加载失败必须如实报错（不降级）
def test_missing_model_dir_reports_error(tmp_path):
    settings = make_settings(tmp_path, model_dir=str(tmp_path / "not-downloaded"))
    manager = ModelManager(settings)

    status = manager.load()
    assert status["state"] == "error"
    assert status["kind"] is None
    assert "不存在" in (status["error"] or "")
    assert "setup_cosyvoice.sh" in (status["error"] or "")


def test_missing_model_dir_never_falls_back_to_fake_audio(tmp_path):
    """失败后不得出现任何可用的后端句柄，调用方必须收到明确异常。"""
    settings = make_settings(tmp_path, model_dir=str(tmp_path / "not-downloaded"))
    manager = ModelManager(settings)
    manager.load()

    assert manager.is_ready is False
    with pytest.raises(ModelNotReadyError) as excinfo:
        manager.ensure_ready()
    assert "不存在" in str(excinfo.value)

    # 合成入口同样必须直接报错，而不是产出音频
    with pytest.raises(ModelNotReadyError):
        list(manager.synthesize(_dummy_params()))


def test_model_manager_exposes_no_mock_switch(tmp_path):
    """确认配置与状态里都不再存在任何 mock 开关/标记。"""
    settings = make_settings(tmp_path, model_dir=str(tmp_path / "not-downloaded"))
    manager = ModelManager(settings)
    status = manager.load()

    assert not hasattr(settings, "mock")
    assert not hasattr(settings, "mock_fallback")
    assert "mock" not in status


def _dummy_params():
    from app.core.types import SynthParams

    return SynthParams(mode="zero_shot", tts_text="测试")
