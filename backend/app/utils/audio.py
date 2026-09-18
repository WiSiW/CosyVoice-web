"""音频读写工具。

这里刻意只依赖标准库 ``wave`` + ``numpy`` + ``soundfile``，
不引入 torch，避免 Web 层被推理依赖绑死。
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.errors import InvalidAudioError

WAV_EXTENSIONS = {".wav", ".wave"}
COMPRESSED_EXTENSIONS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm"}
ALLOWED_EXTENSIONS = WAV_EXTENSIONS | COMPRESSED_EXTENSIONS

_INT16_MAX = 32767.0


@dataclass(slots=True)
class AudioInfo:
    duration: float
    sample_rate: int
    channels: int
    format: str
    frames: int


def float_to_pcm16(samples: np.ndarray) -> bytes:
    """float32 [-1, 1] -> little-endian int16 PCM 字节流。"""
    flat = np.asarray(samples, dtype=np.float32).reshape(-1)
    clipped = np.clip(flat, -1.0, 1.0)
    return (clipped * _INT16_MAX).astype("<i2").tobytes()


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """把 int16 PCM 包装成合法的 WAV 文件字节流（无需第三方库）。"""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def samples_to_wav_bytes(samples: np.ndarray, sample_rate: int, channels: int = 1) -> bytes:
    return pcm16_to_wav_bytes(float_to_pcm16(samples), sample_rate, channels)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int, channels: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(samples_to_wav_bytes(samples, sample_rate, channels))
    return path


def probe_audio(path: str | Path) -> AudioInfo:
    """读取音频元信息，优先使用 soundfile，失败后回退到标准库 wave。"""
    path = Path(path)
    info = _probe_with_soundfile(path) or _probe_with_wave(path)
    if info is None:
        raise InvalidAudioError(f"无法解析音频文件: {path.name}，请上传 WAV/MP3/FLAC/M4A 等常见格式")
    return info


def _probe_with_soundfile(path: Path) -> AudioInfo | None:
    try:
        import soundfile as sf  # 延迟导入，便于在缺依赖时给出更好的回退
    except Exception:  # pragma: no cover - 环境相关
        return None
    try:
        info = sf.info(str(path))
    except Exception:
        return None
    if info.samplerate <= 0 or info.frames <= 0:
        return None
    return AudioInfo(
        duration=info.frames / float(info.samplerate),
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        format=(info.format or path.suffix.lstrip(".")).lower(),
        frames=int(info.frames),
    )


def _probe_with_wave(path: Path) -> AudioInfo | None:
    if path.suffix.lower() not in WAV_EXTENSIONS:
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate <= 0 or frames <= 0:
                return None
            return AudioInfo(
                duration=frames / float(rate),
                sample_rate=rate,
                channels=handle.getnchannels(),
                format="wav",
                frames=frames,
            )
    except Exception:
        return None


def validate_audio_file(
    path: str | Path,
    *,
    max_seconds: float | None = None,
    min_seconds: float | None = None,
    filename: str | None = None,
) -> AudioInfo:
    """校验上传的参考音频，返回其元信息。"""
    path = Path(path)
    display_name = filename or path.name
    suffix = Path(display_name).suffix.lower()
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise InvalidAudioError(
            f"不支持的音频格式 {suffix}，可选：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    info = probe_audio(path)
    if max_seconds is not None and info.duration > max_seconds:
        raise InvalidAudioError(
            f"参考音频过长（{info.duration:.1f}s），请控制在 {max_seconds:.0f}s 以内"
        )
    if min_seconds is not None and info.duration < min_seconds:
        raise InvalidAudioError(
            f"参考音频过短（{info.duration:.2f}s），请至少提供 {min_seconds:.1f}s 的音频"
        )
    return info


def humanize_duration(seconds: float) -> str:
    minutes, remain = divmod(int(round(seconds)), 60)
    return f"{minutes}分{remain}秒" if minutes else f"{remain}秒"
