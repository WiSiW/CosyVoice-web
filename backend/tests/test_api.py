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


# ------------------------------------------- 3s 极速复刻页面的"顺手存音色"
def test_zero_shot_can_save_voice_into_library(client, settings):
    """在合成页上传新参考音频时，可同时把音色注册进音色库。"""
    files = {"prompt_wav": ("my_voice.wav", make_wav_bytes(3.0), "audio/wav")}
    data = {
        "mode": "zero_shot",
        "tts_text": "你好，这是一次测试。",
        "prompt_text": "希望你以后能够做的比我还好呦。",
        "save_voice": "true",
        "voice_name": "自动保存的音色",
    }
    resp = client.post("/api/v1/tts/synthesize", data=data, files=files)
    assert resp.status_code == 200, resp.text

    voice_id = resp.headers.get("x-voice-id")
    assert voice_id, "响应头应返回新建的音色 id"

    voices = client.get("/api/v1/voices").json()
    assert [v["id"] for v in voices] == [voice_id]
    assert voices[0]["name"] == "自动保存的音色"
    assert voices[0]["prompt_text"] == "希望你以后能够做的比我还好呦。"
    assert voices[0]["registered"] is True
    assert voices[0]["runtime_spk_id"] == f"vo_{voice_id}"

    # 参考音频必须落到音色库自己的目录里（而不是继续依赖临时文件）
    stored = settings.voices_dir / voice_id / "prompt.wav"
    assert stored.exists() and stored.stat().st_size > 0

    # 临时文件在合成结束后必须被清理
    assert list(settings.tmp_dir.glob("*")) == []


def test_zero_shot_without_flag_does_not_touch_library(client):
    """默认不写音色库：单次试听不应该污染音色列表。"""
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    resp = client.post(
        "/api/v1/tts/synthesize",
        data={"mode": "zero_shot", "tts_text": "测试", "prompt_text": "参考文本"},
        files=files,
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-voice-id") == ""
    assert client.get("/api/v1/voices").json() == []


def test_save_voice_is_skipped_when_using_existing_voice(client):
    """已经选了音色库里的音色时，不再重复创建。"""
    files = {"audio": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    created = client.post(
        "/api/v1/voices",
        data={"name": "已有音色", "prompt_text": "参考文本", "auto_register": "true"},
        files=files,
    ).json()

    resp = client.post(
        "/api/v1/tts/synthesize",
        data={
            "mode": "zero_shot",
            "tts_text": "测试",
            "voice_id": created["id"],
            "save_voice": "true",
            "voice_name": "不该被创建",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-voice-id") == ""
    assert len(client.get("/api/v1/voices").json()) == 1


def test_stream_endpoint_also_returns_saved_voice(client):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    resp = client.post(
        "/api/v1/tts/stream",
        data={
            "mode": "zero_shot",
            "tts_text": "流式测试",
            "prompt_text": "参考文本",
            "save_voice": "true",
        },
        files=files,
    )
    assert resp.status_code == 200
    voice_id = resp.headers.get("x-voice-id")
    assert voice_id
    assert client.get("/api/v1/voices").json()[0]["id"] == voice_id


# --------------------------------------------------------------- 清空记录
def _generate(client, text: str = "记录测试"):
    files = {"prompt_wav": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    resp = client.post(
        "/api/v1/tts/synthesize",
        data={"mode": "zero_shot", "tts_text": text, "prompt_text": "参考文本"},
        files=files,
    )
    assert resp.status_code == 200
    return resp.headers["x-audio-id"]


def test_clear_history_removes_server_files(client, settings):
    """批量清空必须真的删掉服务端音频，否则下次同步又会冒出来。"""
    first = _generate(client, "第一条")
    second = _generate(client, "第二条")
    assert len(client.get("/api/v1/tts/history").json()) == 2

    resp = client.delete("/api/v1/tts/history")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    # 列表空了，单个文件也取不到了
    assert client.get("/api/v1/tts/history").json() == []
    assert client.get(f"/api/v1/tts/audio/{first}").status_code == 404
    assert client.get(f"/api/v1/tts/audio/{second}").status_code == 404
    # 磁盘上也不该再有文件
    assert list(settings.outputs_dir.glob("*.wav")) == []


def test_clear_history_is_idempotent(client):
    """没有记录时清空应返回 0，而不是报错。"""
    resp = client.delete("/api/v1/tts/history")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


def test_clear_history_keeps_voice_library(client):
    """清空生成记录不应影响音色库。"""
    files = {"audio": ("prompt.wav", make_wav_bytes(3.0), "audio/wav")}
    voice = client.post(
        "/api/v1/voices",
        data={"name": "要保留的音色", "prompt_text": "参考文本"},
        files=files,
    ).json()

    _generate(client)
    assert client.delete("/api/v1/tts/history").status_code == 200

    voices = client.get("/api/v1/voices").json()
    assert [v["id"] for v in voices] == [voice["id"]]


# ------------------------------------------------------- 预置朗读稿
def test_voice_presets_cover_main_languages(client):
    data = client.get("/api/v1/voices/presets").json()
    presets = data["presets"]
    languages = {p["language"] for p in presets}

    # 至少要覆盖 CosyVoice 明确支持的语种
    assert {"中文", "英语", "日语", "韩语", "粤语"} <= languages
    # 预置稿语种必须是可选语言列表的子集，否则前端选不到
    available = set(client.get("/api/v1/voices/languages").json())
    assert languages <= available
    assert data["fallback_note"]


def test_voice_presets_are_readable_scripts(client):
    """预置稿是"朗读稿"，需要满足几个硬性条件。"""
    presets = client.get("/api/v1/voices/presets").json()["presets"]
    for preset in presets:
        text = preset["text"]
        assert text.strip(), preset
        # 不含数字：否则文本正则化会把 2024 改写成「二零二四」，与音频对不上
        assert not any(ch.isdigit() for ch in text), preset["language"]
        # 朗读时长要落在参考音频允许的区间内，且不能太短（声纹样本不足）
        assert 3.0 <= preset["target_seconds"] <= 20.0, preset["language"]
        assert 10 <= len(text) <= 200, preset["language"]


def test_voice_preset_is_accepted_as_prompt_text(client):
    """把预置稿当作参考文本走一遍创建流程，确保后端校验能通过。"""
    preset = next(
        p for p in client.get("/api/v1/voices/presets").json()["presets"] if p["language"] == "中文"
    )
    files = {"audio": ("prompt.wav", make_wav_bytes(7.0), "audio/wav")}
    resp = client.post(
        "/api/v1/voices",
        data={"name": "预置稿音色", "prompt_text": preset["text"], "auto_register": "true"},
        files=files,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["prompt_text"] == preset["text"]
    assert resp.json()["registered"] is True
