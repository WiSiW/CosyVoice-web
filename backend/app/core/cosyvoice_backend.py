"""CosyVoice 官方推理后端的封装。

上游用法参考 https://github.com/QwenAudio/CosyVoice ：

    from cosyvoice.cli.cosyvoice import AutoModel
    model = AutoModel(model_dir='pretrained_models/CosyVoice2-0.5B')
    for chunk in model.inference_zero_shot(text, prompt_text, prompt_wav):
        ...

本模块负责：注入 sys.path、按模型类型过滤构造参数、把上游的
``{'tts_speech': tensor}`` 生成器统一成 ``np.ndarray``。
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from app.core.errors import UnsupportedModeError
from app.core.logging_config import silence_known_third_party_noise
from app.core.types import SynthParams
from app.services.modes import MODE_SPECS, get_spec

logger = logging.getLogger("app.model")


class CosyVoiceBackend:
    """真实模型后端。"""

    kind = "cosyvoice"

    def __init__(
        self,
        *,
        repo_dir: Path,
        model_dir: str,
        load_jit: bool = False,
        load_trt: bool = False,
        load_vllm: bool = False,
        fp16: bool = False,
        trt_concurrent: int = 1,
    ) -> None:
        self.repo_dir = repo_dir
        # 注意顺序：必须在 _prepare_sys_path() 之前解析模型路径。
        # 该方法会 chdir 到上游仓库目录，之后相对路径就不可靠了。
        model_path = self._resolve_model_path(model_dir)

        self._prepare_sys_path(repo_dir)

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2, CosyVoice3
        except ImportError as exc:  # pragma: no cover - 依赖缺失时给出可读提示
            raise RuntimeError(
                "无法导入 cosyvoice 包。请先执行 `bash scripts/setup_cosyvoice.sh` "
                "克隆官方仓库与子模块，并安装其依赖（CosyVoice/requirements.txt）。"
                f" 原始错误: {exc}"
            ) from exc

        # cosyvoice 的导入会连带 import transformers，而后者会把自己的 handler
        # 挂到 `transformers` logger 上（propagate=False）。这里再挂一次过滤器，
        # 否则它的告警会绕过 setup_logging 里配置的 console handler。
        silence_known_third_party_noise()

        model_cls = self._detect_model_class(model_path, CosyVoice, CosyVoice2, CosyVoice3)

        kwargs: dict[str, Any] = {
            "load_jit": load_jit,
            "load_trt": load_trt,
            "load_vllm": load_vllm,
            "fp16": fp16,
            "trt_concurrent": trt_concurrent,
        }
        accepted = set(inspect.signature(model_cls.__init__).parameters)
        filtered = {key: value for key, value in kwargs.items() if key in accepted}

        logger.info("加载 CosyVoice 模型: %s (%s)", model_path, model_cls.__name__)
        self._model = model_cls(model_dir=str(model_path), **filtered)
        self.model_dir = str(model_path)
        self.family = model_cls.__name__
        self.sample_rate = int(getattr(self._model, "sample_rate", 22050))
        logger.info("模型加载完成: family=%s sample_rate=%s", self.family, self.sample_rate)

    # ---------------------------------------------------------------- 初始化
    @staticmethod
    def _prepare_sys_path(repo_dir: Path) -> None:
        """把 CosyVoice 仓库与 Matcha-TTS 子模块加入 import 路径。"""
        if not repo_dir.exists():
            raise RuntimeError(
                f"CosyVoice 仓库不存在: {repo_dir}。请执行 `bash scripts/setup_cosyvoice.sh`，"
                "或在 .env 中设置 CV_COSYVOICE_REPO。"
            )
        matcha = repo_dir / "third_party" / "Matcha-TTS"
        for candidate in (matcha, repo_dir):
            path = str(candidate)
            if candidate.exists() and path not in sys.path:
                sys.path.insert(0, path)
        # 上游代码假定工作目录位于仓库内（相对路径读取 asset / tokenizer 资源）
        os.chdir(repo_dir)

    @staticmethod
    def _resolve_model_path(model_dir: str) -> Path:
        """返回模型目录的绝对路径。

        ``model_dir`` 已经过 ``Settings.resolved_model_dir`` 规范化：
        要么是绝对路径，要么是 ModelScope 仓库 id。
        """
        path = Path(model_dir).expanduser()

        if path.exists():
            if not (path / "cosyvoice.yaml").exists() and not list(path.glob("cosyvoice*.yaml")):
                raise RuntimeError(
                    f"模型目录 {path} 存在，但没有找到 cosyvoice*.yaml 配置文件，"
                    "可能权重没有下载完整。请重新执行 `bash scripts/setup_cosyvoice.sh`。"
                )
            return path.resolve()

        # 绝对路径但不存在 —— 说明权重根本没下载，不要当成仓库 id 去 snapshot_download，
        # 否则 ModelScope 会抛出一堆看不懂的错误（历史上就踩过这个坑）。
        if path.is_absolute():
            raise RuntimeError(
                f"本地模型目录不存在: {path}\n"
                "请任选一种方式修复：\n"
                "  1) 下载官方权重（推荐）: bash scripts/setup_cosyvoice.sh\n"
                "  2) 在 backend/.env 中把 CV_MODEL_DIR 指向已有的权重目录\n"
                "  3) 改成 ModelScope 仓库 id，例如 CV_MODEL_DIR=iic/CosyVoice2-0.5B（首次启动会自动下载）"
            )

        from modelscope import snapshot_download  # 延迟导入

        logger.info("本地未找到模型，从 ModelScope 下载: %s", model_dir)
        try:
            downloaded = snapshot_download(model_dir)
        except Exception as exc:
            raise RuntimeError(
                f"从 ModelScope 下载模型 {model_dir} 失败: {exc}\n"
                "请检查网络，或改用本地权重目录（CV_MODEL_DIR=/abs/path/to/model）。"
            ) from exc
        return Path(downloaded).resolve()

    @staticmethod
    def _detect_model_class(
        model_path: Path,
        cosyvoice_cls: type,
        cosyvoice2_cls: type,
        cosyvoice3_cls: type,
    ) -> type:
        if (model_path / "cosyvoice.yaml").exists():
            return cosyvoice_cls
        if (model_path / "cosyvoice2.yaml").exists():
            return cosyvoice2_cls
        if (model_path / "cosyvoice3.yaml").exists():
            return cosyvoice3_cls
        raise RuntimeError(f"{model_path} 下未找到 cosyvoice*.yaml，无法识别模型类型")

    # ------------------------------------------------------------ 能力查询
    def list_speakers(self) -> list[str]:
        try:
            return list(self._model.list_available_spks())
        except Exception as exc:  # pragma: no cover - 取决于模型内容
            logger.warning("读取预训练音色失败: %s", exc)
            return []

    def supports(self, mode: str) -> bool:
        spec = MODE_SPECS.get(mode)
        if spec is None:
            return False
        if spec.required_family is not None and spec.required_family != self.family:
            return False
        # 预训练音色需要模型自带 spk2info（CosyVoice2/3 的 spk2info 为空），
        # 否则 frontend_sft 会直接 KeyError。这里提前拦下并给出可读错误。
        if mode == "sft" and not self.list_speakers():
            return False
        return True

    # ------------------------------------------------------------ 音色注册
    def add_zero_shot_speaker(self, prompt_text: str, prompt_wav_path: str, spk_id: str) -> bool:
        return bool(self._model.add_zero_shot_spk(prompt_text, self._prompt_path(prompt_wav_path), spk_id))

    def remove_speaker(self, spk_id: str) -> None:
        spk2info = getattr(self._model.frontend, "spk2info", None)
        if isinstance(spk2info, dict):
            spk2info.pop(spk_id, None)

    def save_speakers(self) -> None:
        try:
            self._model.save_spkinfo()
        except Exception as exc:  # pragma: no cover - 只读模型目录时可能失败
            logger.warning("保存 spk2info 失败（可忽略）: %s", exc)

    # ---------------------------------------------------------------- 推理
    def synthesize(self, params: SynthParams) -> Iterator[np.ndarray]:
        spec = get_spec(params.mode)
        if spec is None:
            raise UnsupportedModeError(f"未知模式: {params.mode}")
        if not self.supports(params.mode):
            raise UnsupportedModeError(
                f"当前模型 {self.family} 不支持「{spec.label}」模式。{spec.note}".strip()
            )

        model = self._model
        common = {
            "stream": params.stream,
            "speed": params.speed,
            "text_frontend": params.text_frontend,
        }

        if params.mode == "sft":
            generator = model.inference_sft(params.tts_text, params.spk_id, **common)
        elif params.mode == "zero_shot":
            generator = model.inference_zero_shot(
                params.tts_text,
                params.prompt_text,
                self._prompt_arg(params),
                zero_shot_spk_id=params.zero_shot_spk_id,
                **common,
            )
        elif params.mode == "cross_lingual":
            generator = model.inference_cross_lingual(
                params.tts_text,
                self._prompt_arg(params),
                zero_shot_spk_id=params.zero_shot_spk_id,
                **common,
            )
        elif params.mode == "instruct2":
            generator = model.inference_instruct2(
                params.tts_text,
                params.instruct_text,
                self._prompt_arg(params),
                zero_shot_spk_id=params.zero_shot_spk_id,
                **common,
            )
        elif params.mode == "instruct":
            generator = model.inference_instruct(
                params.tts_text, params.spk_id, params.instruct_text, **common
            )
        elif params.mode == "vc":
            generator = model.inference_vc(
                self._prompt_path(params.source_wav_path), self._prompt_path(params.prompt_wav_path)
            )
        else:  # pragma: no cover - 由 get_spec 兜底
            raise UnsupportedModeError(f"未实现的模式: {params.mode}")

        for output in generator:
            speech = output["tts_speech"]
            yield self._to_numpy(speech)

    # ---------------------------------------------------------------- 工具
    def _prompt_arg(self, params: SynthParams) -> str:
        """给上游的 ``prompt_wav`` 位置参数。

        使用已注册音色（``zero_shot_spk_id`` 非空）时，音色特征已经缓存在
        ``spk2info`` 里，上游约定这里传空字符串 —— 例如官方 example.py：

            cosyvoice.inference_zero_shot(text, '', '', zero_shot_spk_id='my_spk')

        如果这里仍然去解析参考音频路径，会因为拿不到路径而抛"缺少参考音频"，
        导致"从音色库选音色合成"整条链路不可用。
        """
        if params.zero_shot_spk_id:
            return ""
        return self._prompt_path(params.prompt_wav_path)

    @staticmethod
    def _prompt_path(path: str | None) -> str:
        """校验并返回参考音频的**文件路径**。

        注意：这里必须传路径，不能像旧版那样先用 ``load_wav`` 读成 tensor 再传。
        当前上游的 ``CosyVoiceFrontEnd`` 会在 ``_extract_speech_feat``(24kHz)、
        ``_extract_speech_token``(16kHz)、``_extract_spk_embedding``(16kHz)
        里各自按不同目标采样率重新调用一次 ``load_wav()``，
        传 tensor 进去会直接抛 ``TypeError: Invalid file: tensor(...)``。
        （上游 ``runtime/python/fastapi/server.py`` 还是旧写法，不要照抄。）
        """
        if not path:
            raise UnsupportedModeError("缺少参考音频")
        prompt = Path(path).expanduser()
        if not prompt.exists():
            raise UnsupportedModeError(f"参考音频不存在: {prompt}")
        return str(prompt)

    @staticmethod
    def _to_numpy(speech) -> np.ndarray:  # noqa: ANN001 - torch.Tensor
        if hasattr(speech, "detach"):
            speech = speech.detach().cpu()
        if hasattr(speech, "numpy"):
            speech = speech.numpy()
        array = np.asarray(speech, dtype=np.float32)
        return np.ascontiguousarray(array.reshape(-1))
