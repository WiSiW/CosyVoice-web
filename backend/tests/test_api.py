"""HTTP 层端到端接口测试（使用 tests/stub_backend.py 的测试桩）。"""

from __future__ import annotations

import wave

import numpy as np

from tests.conftest import make_wav_bytes


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_system_info_reports_model_state(client):
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"]["state"] in {"unloaded", "ready"}
    assert body["model"]["family"] == "CosyVoice2"
    modes = client.get("/api/v1/system/modes").json()
    assert {mode["id"] for mode in modes} >= {"sft", "zero_shot", "cross_lingual", "instruct2"}


def test_create_and_list_voice(client):
    files = {"audio": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    data = {"name": "测试音色", "prompt_text": "你好世界", "language": "中文"}
    resp = client.post("/api/v1/voices", data=data, files=files)
    assert resp.status_code == 201, resp.text
    voice = resp.json()
    assert voice["name"] == "测试音色"
    assert voice["audio"]["duration"] > 2

    listed = client.get("/api/v1/voices").json()
    assert len(listed) == 1
    assert listed[0]["id"] == voice["id"]

    audio = client.get(f"/api/v1/voices/{voice['id']}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"

    assert client.delete(f"/api/v1/voices/{voice['id']}").status_code == 204
    assert client.get("/api/v1/voices").json() == []


def test_create_voice_rejects_short_audio(client):
    files = {"audio": ("prompt.wav", make_wav_bytes(0.2), "audio/wav")}
    resp = client.post("/api/v1/voices", data={"name": "太短"}, files=files)
    assert resp.status_code == 422


def test_synthesize_zero_shot_returns_wav(client):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    data = {
        "mode": "zero_shot",
        "tts_text": "你好，这是一段测试文本。",
        "prompt_text": "希望你以后能够做的比我还好呦。",
        "speed": "1.0",
    }
    resp = client.post("/api/v1/tts/synthesize", data=data, files=files)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "audio/wav"
    assert float(resp.headers["x-duration"]) > 0

    payload = resp.content
    assert payload[:4] == b"RIFF"
    # WAV 头部之后应当有真实的采样点
    assert len(payload) > 44


def test_synthesize_requires_prompt_text(client):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    resp = client.post(
        "/api/v1/tts/synthesize",
        data={"mode": "zero_shot", "tts_text": "测试"},
        files=files,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "missing_prompt_text"


def test_synthesize_rejects_unknown_mode(client):
    resp = client.post("/api/v1/tts/synthesize", data={"mode": "nope", "tts_text": "测试"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "unsupported_mode"


def test_stream_returns_pcm_chunks(client):
    resp = client.post(
        "/api/v1/tts/stream",
        data={"mode": "sft", "tts_text": "流式合成测试", "spk_id": "中文女"},
    )
    assert resp.status_code == 200
    assert resp.headers["x-sample-format"] == "int16"
    sample_rate = int(resp.headers["x-sample-rate"])
    samples = np.frombuffer(resp.content, dtype="<i2")
    assert samples.size > sample_rate * 0.4  # 至少 0.4 秒音频
    assert np.abs(samples).max() > 100


def test_instruct2_appends_endofprompt(client):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    resp = client.post(
        "/api/v1/tts/synthesize",
        data={
            "mode": "instruct2",
            "tts_text": "他展现了非凡的勇气。",
            "instruct_text": "用四川话说这句话",
        },
        files=files,
    )
    assert resp.status_code == 200


def test_history_lists_generated_audio(client):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    first = client.post(
        "/api/v1/tts/synthesize",
        data={"mode": "zero_shot", "tts_text": "历史记录测试", "prompt_text": "参考文本"},
        files=files,
    )
    audio_id = first.headers["x-audio-id"]
    history = client.get("/api/v1/tts/history").json()
    assert any(item["audio_id"] == audio_id for item in history)

    audio = client.get(f"/api/v1/tts/audio/{audio_id}")
    assert audio.status_code == 200
    with wave.open(__import__("io").BytesIO(audio.content), "rb") as handle:
        assert handle.getframerate() > 0

    assert client.delete(f"/api/v1/tts/audio/{audio_id}").status_code == 204
    assert client.get(f"/api/v1/tts/audio/{audio_id}").status_code == 404
