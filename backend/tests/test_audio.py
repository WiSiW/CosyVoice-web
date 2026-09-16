from __future__ import annotations

import wave

import numpy as np
import pytest

from app.core.errors import InvalidAudioError
from app.utils.audio import (
    float_to_pcm16,
    probe_audio,
    pcm16_to_wav_bytes,
    samples_to_wav_bytes,
    validate_audio_file,
)
from tests.conftest import make_wav_bytes


def test_pcm16_round_trip(tmp_path):
    wav = make_wav_bytes(seconds=1.0)
    path = tmp_path / "a.wav"
    path.write_bytes(wav)
    info = probe_audio(path)
    assert info.sample_rate == 16000
    assert info.channels == 1
    assert info.duration == pytest.approx(1.0, abs=0.01)


def test_float_to_pcm16_clips():
    samples = np.array([2.0, -2.0, 0.5], dtype=np.float32)
    pcm = float_to_pcm16(samples)
    values = np.frombuffer(pcm, dtype="<i2")
    assert values[0] == 32767
    assert values[1] == -32767
    assert 16000 < values[2] < 17000


def test_samples_to_wav_bytes_is_readable(tmp_path):
    samples = np.sin(np.linspace(0, 20, 8000)).astype(np.float32)
    data = samples_to_wav_bytes(samples, 16000)
    path = tmp_path / "b.wav"
    path.write_bytes(data)
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == 16000
        assert handle.getnframes() == 8000


def test_pcm16_to_wav_bytes_header():
    data = pcm16_to_wav_bytes(b"\x00\x00" * 100, 22050)
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"


def test_validate_audio_rejects_long_prompt(tmp_path):
    path = tmp_path / "long.wav"
    path.write_bytes(make_wav_bytes(seconds=12))
    with pytest.raises(InvalidAudioError):
        validate_audio_file(path, max_seconds=10)


def test_validate_audio_rejects_bad_extension(tmp_path):
    path = tmp_path / "x.txt"
    path.write_bytes(b"not audio")
    with pytest.raises(InvalidAudioError):
        validate_audio_file(path, filename="x.txt")
