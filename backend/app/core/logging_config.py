"""统一日志配置。"""

from __future__ import annotations

import logging
import logging.config
import sys

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


def setup_logging(level: str = "INFO") -> None:
    """应用日志配置，``level`` 作用于本应用与根 logger。"""
    level = level.upper()
    _CONFIG["loggers"]["app"]["level"] = level  # type: ignore[index]
    _CONFIG["root"]["level"] = level  # type: ignore[index]
    logging.config.dictConfig(_CONFIG)
    logging.getLogger("app").info("日志级别设置为 %s", level)
