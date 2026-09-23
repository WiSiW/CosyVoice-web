"""自定义音色库接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings
from app.core.errors import AppError, InvalidAudioError
from app.core.model_manager import ModelManager
from app.deps import manager_dep, settings_dep, voice_store_dep
from app.schemas import VoiceOut, VoiceUpdateIn
from app.services.voice_presets import FALLBACK_NOTE, preset_payload
from app.services.voice_store import LANGUAGES, VoiceStore, runtime_spk_id

router = APIRouter(prefix="/voices", tags=["voices"])


def _to_out(meta: dict[str, Any], manager: ModelManager) -> VoiceOut:
    spk_id = runtime_spk_id(meta["id"])
    return VoiceOut(
        **meta,
        registered=manager.is_ready and spk_id in manager.list_speakers(),
        builtin=False,
        runtime_spk_id=spk_id,
    )


@router.get("/languages", response_model=list[str], summary="可选语言列表")
def languages() -> list[str]:
    return LANGUAGES


@router.get("/presets", summary="各语种的预置朗读稿")
def presets() -> dict:
    """新建音色时可一键填入的参考文本（按语种）。

    参考文本必须与参考音频逐字一致，因此这里的文本是**朗读稿**：
    用户照着念即可天然保证一致。声纹本身来自音频（campplus 说话人向量），
    文本不参与声纹提取。
    """
    return {"presets": preset_payload(), "fallback_note": FALLBACK_NOTE}


@router.get("", response_model=list[VoiceOut], summary="音色列表")
def list_voices(
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> list[VoiceOut]:
    return [_to_out(meta, manager) for meta in store.list()]


@router.post("", response_model=VoiceOut, status_code=201, summary="新建音色（上传或录制参考音频）")
async def create_voice(
    name: str = Form(..., description="音色名称"),
    audio: UploadFile = File(..., description="参考音频，建议 3~30 秒清晰人声"),
    prompt_text: str = Form("", description="参考音频对应的文本，用于 3s 极速复刻"),
    description: str = Form(""),
    language: str = Form("中文"),
    source: str = Form("upload", description="upload / record"),
    auto_register: bool = Form(False, description="创建后是否立即注册到推理运行时"),
    settings: Settings = Depends(settings_dep),
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> VoiceOut:
    payload = await audio.read()
    if not payload:
        raise InvalidAudioError("上传的音频为空")
    if len(payload) > settings.max_upload_bytes:
        raise AppError(
            f"音频过大（{len(payload) / 1024 / 1024:.1f}MB），上限 {settings.max_upload_mb}MB",
            code="file_too_large",
            status_code=413,
        )

    meta = store.create(
        name=name,
        audio_bytes=payload,
        original_filename=audio.filename or "prompt.wav",
        prompt_text=prompt_text,
        description=description,
        language=language if language in LANGUAGES else "其他",
        source=source if source in {"upload", "record"} else "upload",
    )

    if auto_register and meta.get("prompt_text"):
        try:
            store.register(meta["id"], manager)
        except Exception as exc:  # 注册失败不影响音色保存
            raise AppError(f"音色已保存，但注册到运行时失败: {exc}", code="register_failed") from exc

    return _to_out(meta, manager)


@router.get("/{voice_id}", response_model=VoiceOut, summary="音色详情")
def get_voice(
    voice_id: str,
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> VoiceOut:
    return _to_out(store.get(voice_id), manager)


@router.patch("/{voice_id}", response_model=VoiceOut, summary="更新音色信息")
def update_voice(
    voice_id: str,
    payload: VoiceUpdateIn,
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> VoiceOut:
    meta = store.update(voice_id, **payload.model_dump(exclude_none=True))
    return _to_out(meta, manager)


@router.delete("/{voice_id}", status_code=204, summary="删除音色")
def delete_voice(
    voice_id: str,
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
):
    store.unregister(voice_id, manager)
    store.delete(voice_id)
    manager.save_speakers()


@router.get("/{voice_id}/audio", summary="获取音色参考音频")
def voice_audio(
    voice_id: str,
    store: VoiceStore = Depends(voice_store_dep),
) -> FileResponse:
    path = store.prompt_path(voice_id)
    return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}.wav")


@router.post("/{voice_id}/register", response_model=VoiceOut, summary="注册音色到推理运行时")
def register_voice(
    voice_id: str,
    manager: ModelManager = Depends(manager_dep),
    store: VoiceStore = Depends(voice_store_dep),
) -> VoiceOut:
    try:
        store.register(voice_id, manager)
    except InvalidAudioError:
        raise
    except Exception as exc:
        raise AppError(f"注册音色失败: {exc}", code="register_failed") from exc
    manager.save_speakers()
    return _to_out(store.get(voice_id), manager)
