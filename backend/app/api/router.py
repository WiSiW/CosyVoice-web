"""聚合所有子路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health, system, tts, voices

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(voices.router)
api_router.include_router(tts.router)
