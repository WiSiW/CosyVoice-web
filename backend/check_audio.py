#!/usr/bin/env python3
"""快速判断一个 wav 是人声还是单频音调。

用法::

    .venv/bin/python check_audio.py ../data/outputs/xxx.wav

原理：语音的频谱由大量谐波与共振峰构成，显著谱峰数量在上千量级；
单一音调（例如误用的模拟后端输出）只有十几个峰。
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np


def analyze(path: Path) -> None:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
        samples = np.frombuffer(handle.readframes(frames), dtype="<i2").astype(np.float32) / 32768.0

    if samples.size == 0:
        print("空音频")
        return

    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    peak_count = int(
        (
            (spectrum[1:-1] > spectrum[:-2])
            & (spectrum[1:-1] > spectrum[2:])
            & (spectrum[1:-1] > 0.05 * spectrum.max())
        ).sum()
    )
    rms = float(np.sqrt(np.mean(samples**2)))
    duration = samples.size / sample_rate

    print(f"文件      : {path}")
    print(f"采样率    : {sample_rate} Hz")
    print(f"时长      : {duration:.2f} s")
    print(f"RMS       : {rms:.4f}  (接近 0 说明是静音)")
    print(f"显著谱峰  : {peak_count}")
    if rms < 0.001:
        print("结论      : 静音或近乎静音")
    elif peak_count > 1000:
        print("结论      : 含丰富谐波结构，符合人声特征")
    else:
        print("结论      : 频谱过于集中，可能不是人声（例如单频音调）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    analyze(Path(sys.argv[1]))
