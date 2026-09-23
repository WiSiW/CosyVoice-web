#!/usr/bin/env python3
"""快速判断合成结果是人声、静音还是频谱异常的音频。

用法::

    .venv/bin/python check_audio.py ../data/outputs/xxx.wav

判据说明
--------
先做简单的帧级 VAD（25ms 窗 / 10ms 跳，阈值取最大帧能量的 10%），
再只在"有声帧"上统计两个指标：

* **谱峰密度（个/秒）**：语音由基频谐波 + 共振峰构成，频谱里
  局部极大值非常密集，实测真实语音约 950~1200 个/秒；而单频音调
  只有几个，即使用噪声也很难超过 400。阈值取 600。
* **前 5 个峰的能量的占比**：语音能量分散，通常 < 0.5；单频音调
  高度集中，通常 > 0.6。

注意：不要用"整个文件的总谱峰数"来判断 —— 它与音频时长强相关，
短句会被误判（这是本脚本早期版本的一个缺陷）。
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

WINDOW_SECONDS = 0.025
HOP_SECONDS = 0.010
VOICED_THRESHOLD_RATIO = 0.1
MIN_RMS = 0.01
PEAK_DENSITY_THRESHOLD = 600.0


def analyze(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
        samples = np.frombuffer(handle.readframes(frames), dtype="<i2").astype(np.float32) / 32768.0

    duration = samples.size / sample_rate
    print(f"文件      : {path}")
    print(f"采样率    : {sample_rate} Hz")
    print(f"时长      : {duration:.2f} s")

    if samples.size == 0:
        print("结论      : 空音频")
        return 1

    rms = float(np.sqrt(np.mean(samples**2)))
    print(f"RMS       : {rms:.4f}")
    if rms < 0.001:
        print("结论      : 静音或近乎静音")
        return 1

    win = max(int(sample_rate * WINDOW_SECONDS), 8)
    hop = max(int(sample_rate * HOP_SECONDS), 1)
    chunks = [samples[i : i + win] for i in range(0, max(samples.size - win, 1), hop)]
    energies = np.array([np.sqrt(np.mean(chunk**2)) for chunk in chunks])
    threshold = max(MIN_RMS, VOICED_THRESHOLD_RATIO * float(energies.max()))
    voiced = [chunk for chunk, energy in zip(chunks, energies) if energy > threshold]
    voiced_seconds = len(voiced) * hop / sample_rate

    print(f"有声时长  : {voiced_seconds:.2f} s（占 {voiced_seconds / max(duration, 1e-9) * 100:.0f}%）")
    if voiced_seconds < 0.1:
        print("结论      : 几乎没有检测到有效声音")
        return 1

    peak_count = 0
    top5_ratios = []
    for chunk in voiced:
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size)))
        peak_count += int(
            (
                (spectrum[1:-1] > spectrum[:-2])
                & (spectrum[1:-1] > spectrum[2:])
                & (spectrum[1:-1] > 0.05 * spectrum.max())
            ).sum()
        )
        ordered = np.sort(spectrum)
        top5_ratios.append(float(ordered[-5:].sum() / max(spectrum.sum(), 1e-9)))

    density = peak_count / voiced_seconds
    top5 = float(np.mean(top5_ratios))
    print(f"谱峰密度  : {density:.0f} 个/秒（阈值 {PEAK_DENSITY_THRESHOLD:.0f}）")
    print(f"前5峰占比 : {top5:.3f}")

    if density >= PEAK_DENSITY_THRESHOLD:
        print("结论      : 含丰富谐波结构，符合人声特征")
        return 0
    print("结论      : 频谱过于集中，可能不是人声（例如单频音调）")
    return 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(analyze(Path(sys.argv[1])))
