"""领域异常与统一的异常处理器。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """业务异常，携带 HTTP 状态码与稳定的错误码。"""

    def __init__(self, message: str, *, code: str = "app_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ModelNotReadyError(AppError):
    def __init__(self, message: str = "模型尚未加载完成，请稍后重试或先调用 /system/load") -> None:
        super().__init__(message, code="model_not_ready", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class UnsupportedModeError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsupported_mode", status_code=status.HTTP_409_CONFLICT)


class VoiceNotFoundError(AppError):
    def __init__(self, voice_id: str) -> None:
        super().__init__(f"音色不存在: {voice_id}", code="voice_not_found", status_code=status.HTTP_404_NOT_FOUND)


class InvalidAudioError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_audio", status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


def _payload(code: str, message: str, detail: object | None = None) -> dict:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail  # type: ignore[index]
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_payload("validation_error", "请求参数校验失败", exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_payload("http_error", str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("internal_error", "服务内部错误，请查看后端日志"),
        )
