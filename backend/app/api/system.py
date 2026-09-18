"""服务信息与模型生命周期接口。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.config import Settings
from app.core.model_manager import ModelManager
from app.deps import manager_dep, settings_dep, voice_store_dep
from app.schemas import ModeOut, ModelStatusOut, SystemInfoOut
from app.services.modes import mode_specs_payload
from app.services.voice_store import LANGUAGES, VoiceStore

logger = logging.getLogger("app.system")

router = APIRouter(tags=["system"])


@router.get("/system/info", response_model=SystemInfoOut, summary="服务与模型信息")
def system_info(
    settings: Settings = Depends(settings_dep),
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> SystemInfoOut:
    voices = store.list()
    return SystemInfoOut(
        app=settings.app_name,
        version=settings.app_version,
        api_prefix=settings.api_prefix,
        model=ModelStatusOut(**manager.status()),
        speakers=manager.list_speakers(),
        voices=len(voices),
        limits={
            "max_upload_mb": settings.max_upload_mb,
            "max_prompt_seconds": settings.max_prompt_seconds,
            "min_prompt_seconds": settings.min_prompt_seconds,
            "max_text_length": 2000,
            "speed": {"min": settings.min_speed, "max": settings.max_speed},
        },
        languages=LANGUAGES,
    )


@router.get("/system/modes", response_model=list[ModeOut], summary="可用合成模式")
def list_modes(manager: ModelManager = Depends(manager_dep)) -> list[ModeOut]:
    payload = manager.modes_payload()
    return [ModeOut(**item) for item in payload]


@router.post("/system/load", response_model=ModelStatusOut, summary="加载模型（阻塞直到完成）")
async def load_model(
    force: bool = False,
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> ModelStatusOut:
    status = await run_in_threadpool(manager.load, force=force)
    if status["state"] == "ready":
        registered = await run_in_threadpool(store.register_all, manager)
        logger.info("模型就绪，已重新注册自定义音色 %d 个", registered)
    return ModelStatusOut(**status)


@router.post("/system/unload", response_model=ModelStatusOut, summary="卸载模型并释放显存")
async def unload_model(manager: ModelManager = Depends(manager_dep)) -> ModelStatusOut:
    status = await run_in_threadpool(manager.unload)
    return ModelStatusOut(**status)


@router.get("/system/speakers", response_model=list[str], summary="模型内置音色列表")
def list_speakers(manager: ModelManager = Depends(manager_dep)) -> list[str]:
    return manager.list_speakers()
