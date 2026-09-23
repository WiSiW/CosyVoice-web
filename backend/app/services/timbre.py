"""页面音频的音色特征提取与音色库匹配。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import Settings
from app.core.model_manager import ModelManager
from app.services.voice_store import VoiceStore

logger = logging.getLogger("app.timbre")


@dataclass(slots=True)
class TimbreFeatures:
    pitch_hz: float | None
    pitch_low_hz: float | None
    pitch_high_hz: float | None
    voiced_ratio: float
    spectral_centroid_hz: float
    rms_db: float
    label: str


def _read_mono(path: Path, target_sample_rate: int = 16000) -> tuple[np.ndarray, int]:
    """读取音频并转成目标采样率的单声道 float32。"""
    import soundfile as sf

    samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = np.mean(samples, axis=1, dtype=np.float32)
    mono = np.nan_to_num(mono, copy=False)
    if sample_rate == target_sample_rate:
        return np.ascontiguousarray(mono), target_sample_rate

    target_length = max(1, int(round(mono.size * target_sample_rate / sample_rate)))
    source_positions = np.linspace(0.0, mono.size - 1, num=mono.size, dtype=np.float64)
    target_positions = np.linspace(0.0, mono.size - 1, num=target_length, dtype=np.float64)
    resampled = np.interp(target_positions, source_positions, mono).astype(np.float32)
    return np.ascontiguousarray(resampled), target_sample_rate


def _frame_signal(samples: np.ndarray, frame_size: int, hop_size: int) -> np.ndarray:
    if samples.size < frame_size:
        padded = np.pad(samples, (0, frame_size - samples.size))
        return padded.reshape(1, -1)
    frame_count = 1 + (samples.size - frame_size) // hop_size
    shape = (frame_count, frame_size)
    strides = (samples.strides[0] * hop_size, samples.strides[0])
    return np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides).copy()


def _estimate_pitch(samples: np.ndarray, sample_rate: int) -> tuple[list[float], np.ndarray]:
    frame_size = max(32, int(sample_rate * 0.04))
    hop_size = max(16, int(sample_rate * 0.02))
    frames = _frame_signal(samples, frame_size, hop_size)
    if frames.size == 0:
        return [], np.array([], dtype=np.float32)

    rms = np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)
    if rms.size == 0:
        return [], rms

    noise_floor = float(np.percentile(rms, 20))
    # 连续语音没有真正的静音帧，阈值必须低于底噪分位数；否则整段音频都会被跳过。
    threshold = max(noise_floor * 0.85, float(np.max(rms)) * 0.12, 1e-4)
    min_lag = max(2, int(sample_rate / 500))
    max_lag = min(frame_size - 2, int(sample_rate / 70))
    pitches: list[float] = []

    for frame, level in zip(frames, rms, strict=True):
        if level < threshold:
            continue
        centered = frame - float(np.mean(frame))
        spectrum = np.fft.rfft(centered, n=frame_size * 2)
        autocorrelation = np.fft.irfft(np.square(np.abs(spectrum)), n=frame_size * 2)
        if autocorrelation[0] <= 0:
            continue
        autocorrelation = autocorrelation[: max_lag + 1] / autocorrelation[0]
        region = autocorrelation[min_lag : max_lag + 1]
        if region.size == 0:
            continue
        peak_offset = int(np.argmax(region))
        peak = float(region[peak_offset])
        if peak < 0.35:
            continue
        lag = min_lag + peak_offset
        pitches.append(sample_rate / lag)

    return pitches, rms


def _spectral_centroid(samples: np.ndarray, sample_rate: int) -> float:
    frame_size = max(64, int(sample_rate * 0.04))
    hop_size = max(32, int(sample_rate * 0.02))
    frames = _frame_signal(samples, frame_size, hop_size)
    if frames.size == 0:
        return 0.0

    window = np.hanning(frame_size).astype(np.float32)
    spectra = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    energy = np.sum(spectra, axis=1)
    usable = energy > max(float(np.max(energy)) * 0.05, 1e-12)
    if not np.any(usable):
        return 0.0

    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    weighted = np.sum(spectra[usable] * frequencies, axis=1)
    return float(np.mean(weighted / np.maximum(energy[usable], 1e-12)))


def extract_timbre_features(path: Path) -> TimbreFeatures:
    samples, sample_rate = _read_mono(path)
    if samples.size == 0:
        return TimbreFeatures(None, None, None, 0.0, 0.0, -120.0, "未检测到有效音频")

    rms = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    rms_db = round(20.0 * float(np.log10(max(rms, 1e-6))), 2)
    pitches, frame_rms = _estimate_pitch(samples, sample_rate)
    voiced_ratio = len(pitches) / max(1, int(frame_rms.size))

    if pitches:
        pitch_values = np.asarray(pitches, dtype=np.float32)
        pitch_hz = round(float(np.median(pitch_values)), 1)
        pitch_low = round(float(np.percentile(pitch_values, 10)), 1)
        pitch_high = round(float(np.percentile(pitch_values, 90)), 1)
    else:
        pitch_hz = pitch_low = pitch_high = None

    centroid = round(_spectral_centroid(samples, sample_rate), 1)
    label = _timbre_label(pitch_hz, centroid, voiced_ratio, rms_db)
    return TimbreFeatures(
        pitch_hz=pitch_hz,
        pitch_low_hz=pitch_low,
        pitch_high_hz=pitch_high,
        voiced_ratio=round(voiced_ratio, 3),
        spectral_centroid_hz=centroid,
        rms_db=rms_db,
        label=label,
    )


def _timbre_label(
    pitch_hz: float | None,
    spectral_centroid_hz: float,
    voiced_ratio: float,
    rms_db: float,
) -> str:
    if rms_db < -55:
        return "音量过低"
    if pitch_hz is None or voiced_ratio < 0.08:
        return "未检测到稳定人声"

    if pitch_hz < 120:
        pitch_label = "低沉"
    elif pitch_hz < 165:
        pitch_label = "中低"
    elif pitch_hz < 210:
        pitch_label = "中性"
    elif pitch_hz < 260:
        pitch_label = "偏高"
    else:
        pitch_label = "高亮"

    if spectral_centroid_hz < 1600:
        tone_label = "温暖"
    elif spectral_centroid_hz > 2800:
        tone_label = "明亮"
    else:
        tone_label = "均衡"
    return f"{pitch_label} · {tone_label}"


def _normalize(vector: np.ndarray) -> np.ndarray:
    flat = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(flat))
    if not np.isfinite(norm) or norm <= 1e-8:
        raise ValueError("声纹向量无效")
    return flat / norm


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    size = min(left.size, right.size)
    if size == 0:
        return -1.0
    return float(np.dot(left[:size], right[:size]))


class TimbreIdentificationService:
    """缓存音色库声纹，并把查询音频与候选音色做余弦相似度匹配。"""

    def __init__(self, settings: Settings, manager: ModelManager, store: VoiceStore) -> None:
        self._settings = settings
        self._manager = manager
        self._store = store
        self._cache: dict[str, tuple[tuple[int, int], np.ndarray]] = {}
        self._lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        return {
            "ready": self._manager.is_ready,
            "model_state": self._manager.state,
            "voice_count": len(self._store.list()),
            "min_seconds": self._settings.min_identify_seconds,
            "max_seconds": self._settings.max_identify_seconds,
            "match_threshold": self._settings.voice_match_threshold,
        }

    def identify(
        self,
        path: Path,
        *,
        limit: int = 5,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        features = extract_timbre_features(path)
        effective_threshold = (
            self._settings.voice_match_threshold if threshold is None else float(threshold)
        )
        if features.pitch_hz is None or features.voiced_ratio < 0.08 or features.rms_db < -55:
            return {
                "matched": False,
                "best_match": None,
                "matches": [],
                "features": _features_payload(features),
                "threshold": effective_threshold,
                "note": "未检测到足够清晰的人声，未进行音色库匹配。",
                "disclaimer": "结果来自本地音色库的声学相似度匹配，不等同于身份认证。",
            }

        query = self._extract_embedding(path)

        matches: list[dict[str, Any]] = []
        for meta in self._store.list():
            try:
                candidate = self._library_embedding(meta)
            except Exception as exc:
                logger.warning("音色 %s 声纹提取失败: %s", meta.get("id"), exc)
                continue
            matches.append(self._match_payload(meta, candidate, query, kind="library"))

        for name, candidate in self._builtin_embeddings().items():
            meta = {
                "id": name,
                "name": name,
                "language": "",
                "registered": True,
            }
            matches.append(self._match_payload(meta, candidate, query, kind="builtin"))

        matches.sort(key=lambda item: item["score"], reverse=True)
        matches = matches[: max(1, limit)]
        best = matches[0] if matches else None
        matched = bool(best and best["score"] >= effective_threshold * 100.0)
        note = ""
        if not matches:
            note = "音色库为空，当前仅返回声学特征。"
        elif not matched:
            note = "最高分未达到命中阈值，可参考最接近的候选音色。"

        return {
            "matched": matched,
            "best_match": best,
            "matches": matches,
            "features": _features_payload(features),
            "threshold": effective_threshold,
            "note": note,
            "disclaimer": "结果来自本地音色库的声学相似度匹配，不等同于身份认证。",
        }

    def _extract_embedding(self, path: Path) -> np.ndarray:
        return _normalize(self._manager.extract_speaker_embedding(str(path)))

    def _library_embedding(self, meta: dict[str, Any]) -> np.ndarray:
        voice_id = str(meta["id"])
        path = self._store.prompt_path(voice_id)
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cache_key = f"library:{voice_id}:{self._model_cache_token()}"

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] == signature:
                return cached[1]

        embedding = self._extract_embedding(path)
        with self._lock:
            self._cache[cache_key] = (signature, embedding)
        return embedding

    def _model_cache_token(self) -> str:
        status = self._manager.status()
        return "|".join(
            str(status.get(key) or "")
            for key in ("model_dir", "family", "loaded_at")
        )

    def _builtin_embeddings(self) -> dict[str, np.ndarray]:
        if not self._manager.is_ready:
            return {}
        try:
            raw = self._manager.list_speaker_embeddings()
        except Exception as exc:
            logger.warning("读取内置音色声纹失败: %s", exc)
            return {}

        embeddings: dict[str, np.ndarray] = {}
        for name, vector in raw.items():
            try:
                embeddings[name] = _normalize(vector)
            except Exception:
                continue
        return embeddings

    @staticmethod
    def _match_payload(
        meta: dict[str, Any],
        candidate: np.ndarray,
        query: np.ndarray,
        *,
        kind: str,
    ) -> dict[str, Any]:
        similarity = _cosine_similarity(query, candidate)
        return {
            "voice_id": str(meta["id"]),
            "name": str(meta.get("name") or meta["id"]),
            "kind": kind,
            "score": round(max(0.0, similarity) * 100.0, 2),
            "similarity": round(similarity, 4),
            "language": str(meta.get("language") or ""),
            "registered": bool(meta.get("registered", kind == "builtin")),
        }


def _features_payload(features: TimbreFeatures) -> dict[str, Any]:
    return {
        "pitch_hz": features.pitch_hz,
        "pitch_low_hz": features.pitch_low_hz,
        "pitch_high_hz": features.pitch_high_hz,
        "voiced_ratio": features.voiced_ratio,
        "spectral_centroid_hz": features.spectral_centroid_hz,
        "rms_db": features.rms_db,
        "label": features.label,
    }
