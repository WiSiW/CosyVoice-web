from __future__ import annotations

import io
import wave

import pytest

from tests.conftest import make_wav_bytes


def make_silence(seconds: float = 3.0, sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


def test_timbre_status_reports_library_size(client):
    response = client.get("/api/v1/timbre/status")
    assert response.status_code == 200
    assert response.json()["voice_count"] == 0
    assert response.json()["min_seconds"] == 2.0


def test_identify_returns_features_with_empty_library(client):
    files = {"audio": ("page.wav", make_wav_bytes(3.0, freq=220.0), "audio/wav")}
    response = client.post("/api/v1/timbre/identify", files=files)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["matched"] is False
    assert body["matches"] == []
    assert body["features"]["label"]
    assert body["features"]["pitch_hz"] == pytest.approx(220.0, abs=15.0)
    assert body["disclaimer"]


def test_identify_matches_same_audio_in_voice_library(client):
    payload = make_wav_bytes(3.0, freq=180.0)
    created = client.post(
        "/api/v1/voices",
        data={"name": "页面音色", "prompt_text": "参考文本"},
        files={"audio": ("prompt.wav", payload, "audio/wav")},
    )
    assert created.status_code == 201, created.text
    voice_id = created.json()["id"]

    response = client.post(
        "/api/v1/timbre/identify",
        files={"audio": ("page.wav", payload, "audio/wav")},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["matched"] is True
    assert body["best_match"]["voice_id"] == voice_id
    assert body["best_match"]["score"] == pytest.approx(100.0, abs=0.1)


def test_identify_rejects_short_audio(client):
    response = client.post(
        "/api/v1/timbre/identify",
        files={"audio": ("short.wav", make_wav_bytes(0.5), "audio/wav")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_audio"


def test_identify_skips_matching_for_silence(client):
    response = client.post(
        "/api/v1/timbre/identify",
        files={"audio": ("silence.wav", make_silence(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] is False
    assert body["matches"] == []
    assert "未检测到" in body["note"]
