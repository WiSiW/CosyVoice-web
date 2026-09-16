"""健康检查与就绪探针。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.core.model_manager import ModelManager
from app.deps import manager_dep, settings_dep
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, summary="健康检查")
def health(
    settings: Settings = Depends(settings_dep),
    manager: ModelManager = Depends(manager_dep),
) -> HealthOut:
    return HealthOut(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        model_state=manager.state,
    )


@router.get("/ready", summary="就绪探针（模型可用才返回 200）")
def ready(manager: ModelManager = Depends(manager_dep)) -> dict[str, str]:
    return {"status": "ready" if manager.is_ready else "not_ready", "model_state": manager.state}
