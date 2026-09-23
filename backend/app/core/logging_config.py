"""统一日志配置。

除了设置格式与级别，这里还会屏蔽几条**第三方库的已知无害告警**，
避免它们淹没真正的错误（每一条都说明了为什么可以安全忽略）。
"""

from __future__ import annotations

import logging
import logging.config
import sys
import warnings

_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": sys.stdout,
        }
    },
    "loggers": {
        "app": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "matplotlib": {"level": "WARNING"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

# ---------------------------------------------------------------------------
# 已知无害告警清单（按消息内容匹配）
#
# 1. transformers 的 sliding window 误报
#    Qwen2 的警告条件是 `if config.sliding_window and attn_impl != "flash_attention_2"`，
#    漏看了 `use_sliding_window`。而真正构造注意力时是
#        if self.config.use_sliding_window and ...: sliding_window = config.sliding_window
#    CosyVoice2 的 CosyVoice-BlankEN/config.json 里 use_sliding_window=False
#    （sliding_window 只是个 32768 的默认值），所以实际走的就是全注意力，
#    掩码没有丢失，警告属于误报。
#    参考：transformers/models/qwen2/modeling_qwen2.py 第 176-182 行 vs 第 239 行。
#
# 2. lightning 2.2.4 内部仍在使用 pkg_resources（上游锁定版本，已用 setuptools<81 满足）。
# 3. diffusers 0.29.0 内部使用了已弃用的 LoRACompatibleLinear（上游锁定版本）。
# 4. torch 2.2.2 仍保留 nn.utils.weight_norm，上游 HiFiGAN / flow 代码在用它。
# ---------------------------------------------------------------------------
SUPPRESSED_MESSAGES: tuple[str, ...] = (
    "Sliding Window Attention is enabled but not implemented",
    "pkg_resources is deprecated as an API",
    "LoRACompatibleLinear",
    "torch.nn.utils.weight_norm is deprecated",
)

SUPPRESSED_WARNING_REGEXES: tuple[str, ...] = (
    r".*pkg_resources is deprecated.*",
    r".*LoRACompatibleLinear.*",
    r".*torch\.nn\.utils\.weight_norm is deprecated.*",
)


def _ensure_filter(handler: logging.Handler) -> None:
    if not any(isinstance(item, _DropMessages) for item in handler.filters):
        handler.addFilter(_DropMessages(SUPPRESSED_MESSAGES))


def _route_transformers_logs_through_root() -> None:
    """把 transformers 的日志接到本项目统一的 handler 上。

    transformers 会在 ``transformers`` logger 上挂一个自己的 StreamHandler，
    并把 ``propagate`` 设为 ``False``（见其 utils/logging.py 的
    ``_configure_library_root_logger``），后果有两个：

    1. 它的日志格式与项目其它日志不一致；
    2. 挂在 root handler 上的过滤器对它**无效** —— handler 过滤器只作用于
       自己这个 handler，不会跨 handler 生效。

    这里摘掉它的私有 handler 并打开传播，让它走我们的 console handler。
    函数是幂等的，可以在 transformers 被 import 之后再调用一次。

    用 ``sys.modules`` 判断而不是 import，避免在启动阶段就把 transformers
    （及其 torch 依赖）提前拉进来。
    """
    if "transformers.utils.logging" not in sys.modules:
        return
    logger = logging.getLogger("transformers")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.propagate = True
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.WARNING)


class _DropMessages(logging.Filter):
    """按消息内容丢弃已知无害的告警。"""

    def __init__(self, needles: tuple[str, ...]) -> None:
        super().__init__()
        self._needles = needles

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 格式化失败时不要吞掉日志
            return True
        return not any(needle in message for needle in self._needles)


def silence_known_third_party_noise() -> None:
    """屏蔽第三方库的已知无害告警（在 setup_logging 之后调用）。"""
    for regex in SUPPRESSED_WARNING_REGEXES:
        warnings.filterwarnings("ignore", message=regex)

    # 把过滤器挂在 handler 上：这样无论告警从哪个 logger 冒出来
    # （例如 transformers.models.qwen2.*）都能被拦下，且不受模块路径变动影响。
    for handler in logging.getLogger().handlers:
        _ensure_filter(handler)

    _route_transformers_logs_through_root()


def setup_logging(level: str = "INFO") -> None:
    """应用日志配置，``level`` 作用于本应用与根 logger。"""
    level = level.upper()
    _CONFIG["loggers"]["app"]["level"] = level  # type: ignore[index]
    _CONFIG["root"]["level"] = level  # type: ignore[index]
    logging.config.dictConfig(_CONFIG)
    silence_known_third_party_noise()
    logging.getLogger("app").info("日志级别设置为 %s", level)
