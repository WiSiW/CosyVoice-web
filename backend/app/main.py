"""FastAPI 应用入口。

启动方式::

    uvicorn app.main:app --reload --port 8000     # 开发
    python -m app.main --model-dir iic/CosyVoice2-0.5B
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.model_manager import ModelManager
from app.services.timbre import TimbreIdentificationService
from app.services.tts_service import TTSService
from app.services.voice_store import VoiceStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    settings.ensure_directories()

    manager = ModelManager(settings)
    store = VoiceStore(settings)
    service = TTSService(settings, manager)
    timbre_service = TimbreIdentificationService(settings, manager, store)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        import logging

        logger = logging.getLogger("app")
        logger.info("%s v%s 启动", settings.app_name, settings.app_version)
        logger.info("模型目录: %s", settings.resolved_model_dir)
        if settings.preload_model:
            await run_in_threadpool(manager.load)
            if manager.is_ready:
                registered = await run_in_threadpool(store.register_all, manager)
                logger.info("预加载完成，已注册自定义音色 %d 个", registered)
        yield
        logger.info("服务关闭")

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "基于 [CosyVoice](https://github.com/QwenAudio/CosyVoice) 的语音合成服务："
            "预训练音色、3s 极速复刻、跨语种复刻、自然语言控制与音色转换。"
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.state.settings = settings
    application.state.model_manager = manager
    application.state.voice_store = store
    application.state.tts_service = service
    application.state.timbre_service = timbre_service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Audio-Id", "X-Sample-Rate", "X-Duration", "X-Audio-Url", "X-Voice-Id"],
    )

    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_prefix)

    @application.get("/", tags=["health"], summary="服务首页")
    def index() -> dict[str, object]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "api": settings.api_prefix,
            "model_state": manager.state,
        }

    return application


app = create_app()


def _apply_cli_overrides(args: argparse.Namespace) -> None:
    if args.model_dir:
        os.environ["CV_MODEL_DIR"] = args.model_dir
    if args.repo:
        os.environ["CV_COSYVOICE_REPO"] = args.repo
    if args.preload:
        os.environ["CV_PRELOAD_MODEL"] = "true"
    get_settings.cache_clear()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CosyVoice Web 后端")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--model-dir", default=None, help="本地模型目录或 ModelScope repo id")
    parser.add_argument("--repo", default=None, help="CosyVoice 仓库路径")
    parser.add_argument("--preload", action="store_true", help="启动时立即加载模型")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    args = parse_args(argv)
    _apply_cli_overrides(args)
    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port

    if args.reload:
        # reload 需要以 import string 方式启动
        os.environ.setdefault("UVICORN_HOST", host)
        uvicorn.run("app.main:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(create_app(settings), host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
