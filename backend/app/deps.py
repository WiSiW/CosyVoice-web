"""FastAPI 依赖注入。

所有依赖都从 ``app.state`` 取实例，保证 ``create_app(settings)`` 注入的
配置在整个应用内一致（而不是回退到全局缓存的默认配置）。
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.core.model_manager import ModelManager
from app.services.timbre import TimbreIdentificationService
from app.services.tts_service import TTSService
from app.services.voice_store import VoiceStore


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def manager_dep(request: Request) -> ModelManager:
    return request.app.state.model_manager


def voice_store_dep(request: Request) -> VoiceStore:
    return request.app.state.voice_store


def tts_service_dep(request: Request) -> TTSService:
    return request.app.state.tts_service


def timbre_service_dep(request: Request) -> TimbreIdentificationService:
    return request.app.state.timbre_service
