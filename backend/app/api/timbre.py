"""页面音频音色识别接口。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import Settings
from app.core.errors import AppError, InvalidAudioError
from app.deps import settings_dep, timbre_service_dep
from app.schemas import TimbreIdentificationOut, TimbreStatusOut
from app.services.timbre import TimbreIdentificationService
from app.utils.audio import ALLOWED_EXTENSIONS, validate_audio_file

router = APIRouter(prefix="/timbre", tags=["timbre"])


@router.get("/status", response_model=TimbreStatusOut, summary="音色识别服务状态")
def status(
    service: TimbreIdentificationService = Depends(timbre_service_dep),
) -> TimbreStatusOut:
    return TimbreStatusOut(**service.status())


@router.post("/identify", response_model=TimbreIdentificationOut, summary="识别音频音色")
async def identify(
    audio: UploadFile = File(..., description="待识别音频，建议 2~20 秒清晰人声"),
    limit: int = Form(5, ge=1, le=20),
    threshold: float | None = Form(None, ge=0.0, le=1.0),
    settings: Settings = Depends(settings_dep),
    service: TimbreIdentificationService = Depends(timbre_service_dep),
) -> TimbreIdentificationOut:
    payload = await audio.read()
    if not payload:
        raise InvalidAudioError("上传的音频为空")
    if len(payload) > settings.max_upload_bytes:
        raise AppError(
            f"音频过大（{len(payload) / 1024 / 1024:.1f}MB），上限 {settings.max_upload_mb}MB",
            code="file_too_large",
            status_code=413,
        )

    suffix = Path(audio.filename or "").suffix.lower() or ".wav"
    if suffix not in ALLOWED_EXTENSIONS:
        raise InvalidAudioError(
            f"不支持的音频格式 {suffix}，可选：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    path = settings.tmp_dir / f"timbre_{uuid.uuid4().hex[:10]}{suffix}"
    try:
        path.write_bytes(payload)
        validate_audio_file(
            path,
            filename=audio.filename,
            min_seconds=settings.min_identify_seconds,
            max_seconds=settings.max_identify_seconds,
        )
        result = await run_in_threadpool(
            service.identify,
            path,
            limit=limit,
            threshold=threshold,
        )
    finally:
        path.unlink(missing_ok=True)

    return TimbreIdentificationOut(**result)
