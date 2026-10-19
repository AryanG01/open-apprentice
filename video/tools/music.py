"""A licence-free music bed, generated here (no samples, no third-party audio): a slow pad over A minor - F - C - G with a
soft arpeggio and a sub pulse. Writes public/music.wav.   .venv/bin/python tools/music.py [seconds]"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR, BPM = 44100, 92
ROOT = Path(__file__).resolve().parents[1]
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 55, 64], [55, 59, 62]]  # Am F C G (midi)


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x: np.ndarray, a: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # ponytail: one-pole filter in Python; ~3 s for 3 min, fine for a one-off render
        acc += a * (v - acc)
        y[i] = acc
    return y


def render(seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    bar = 4 * 60 / BPM
    out = np.zeros(n)
    for k in range(int(seconds / bar) + 1):
        chord = CHORDS[k % 4]
        s, e = int(k * bar * SR), min(n, int((k + 1) * bar * SR))
        if s >= n:
            break
        seg = t[s:e] - t[s]
        env = np.minimum(1, seg / 1.2) * np.minimum(1, (bar - seg) / 0.8)
        for m in chord:  # detuned saw-ish pad
            for d in (-0.08, 0.08):
                ph = 2 * np.pi * hz(m + d) * seg
                out[s:e] += 0.05 * env * (np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph))
        out[s:e] += 0.09 * env * np.sin(2 * np.pi * hz(chord[0] - 24) * seg)  # sub
        step = 60 / BPM / 2
        for j in range(8):  # eighth-note arpeggio
            a0 = int((k * bar + j * step) * SR)
            if a0 >= n:
                break
            a1 = min(n, a0 + int(0.35 * SR))
            tt = (np.arange(a1 - a0)) / SR
            note = chord[j % 3] + 12
            out[a0:a1] += 0.035 * np.exp(-tt * 7) * np.sin(2 * np.pi * hz(note) * tt)
    out = lowpass(out, 0.25)
    fade = np.minimum(1, np.minimum(t / 2.0, (seconds - t) / 3.0))
    out *= fade / (np.max(np.abs(out)) + 1e-9) * 0.5
    return np.stack([out, np.roll(out, 300)], axis=1)  # tiny stereo offset


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 190
    (ROOT / "public").mkdir(exist_ok=True)
    sf.write(ROOT / "public/music.wav", render(secs), SR)
    print(f"public/music.wav: {secs:.0f}s")
