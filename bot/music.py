"""Original background music for the Reels, synthesized from scratch (no samples, no copyrighted material).

    python -m bot.music            # (re)writes assets/music/*.m4a

Each track is a mellow lo-fi loop: soft electric-piano chords, a warm pad, a round bass, swung hats,
a gentle kick/snare and a little vinyl crackle. Needs numpy (only for making the tracks; the daily
job just uses the finished .m4a files).
"""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"
SR = 44100

# name, bpm, key offset (semitones from C), chords (MIDI notes), swing, seed
TRACKS = [
    ("seoul-morning", 86, 0, [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]], 0.58, 1),
    ("han-river", 78, 2, [[50, 53, 57, 60], [55, 59, 62, 65], [48, 52, 55, 59], [45, 48, 52, 55]], 0.6, 2),
    ("olive-glow", 94, -3, [[48, 52, 55, 59], [45, 48, 52, 55], [53, 57, 60, 64], [55, 59, 62, 65]], 0.55, 3),
    ("night-routine", 72, 5, [[45, 48, 52, 55], [50, 53, 57, 60], [43, 47, 50, 53], [48, 52, 55, 59]], 0.62, 4),
]


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def make_track(bpm: int, key: int, chords: list[list[int]], swing: float, seed: int, bars: int = 16):
    import numpy as np
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = beat * 4
    n = int(SR * bar * bars) + SR * 2
    out = np.zeros((n, 2))

    def add(sig, start, pan=0.0, gain=1.0):
        i = int(start * SR)
        j = min(n, i + len(sig))
        if i >= n:
            return
        left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        out[i:j, 0] += sig[: j - i] * gain * left
        out[i:j, 1] += sig[: j - i] * gain * right

    def env(length, a=0.01, d=0.3, s=0.6, r=0.4):
        m = int(length * SR)
        e = np.ones(m) * s
        ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
        e[:ai] = np.linspace(0, 1, max(ai, 1))
        e[ai:ai + di] = np.linspace(1, s, len(e[ai:ai + di]))
        if ri:
            e[-ri:] *= np.linspace(1, 0, len(e[-ri:]))
        return e

    def epiano(freq, length, vel):
        m = int(length * SR)
        tt = np.arange(m) / SR
        dec = np.exp(-tt * 2.2)
        tone = np.sin(2 * np.pi * freq * tt) + 0.35 * np.sin(2 * np.pi * freq * 2 * tt) * np.exp(-tt * 6) \
            + 0.12 * np.sin(2 * np.pi * freq * 3.01 * tt) * np.exp(-tt * 9)
        trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * tt)
        e = np.minimum(1, tt / 0.006)
        return tone * dec * trem * e * vel

    def pad(freqs, length):
        m = int(length * SR)
        tt = np.arange(m) / SR
        sig = np.zeros(m)
        for f in freqs:
            for det in (-0.12, 0.0, 0.13):
                sig += np.sin(2 * np.pi * f * (1 + det / 100) * tt + rng.uniform(0, 6.28))
        return sig / (len(freqs) * 3) * env(length, a=0.8, d=0.5, s=0.9, r=0.9)

    # --- pre-rendered drums
    kt = np.arange(int(0.45 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 * kt + (110 / 18) * (1 - np.exp(-kt * 18)))) * np.exp(-kt * 7.5)
    st = np.arange(int(0.25 * SR)) / SR
    noise = rng.standard_normal(len(st))
    snare = (np.convolve(noise, np.ones(6) / 6, mode="same") - np.convolve(noise, np.ones(40) / 40, mode="same")) \
        * np.exp(-st * 22) * 0.7 + np.sin(2 * np.pi * 185 * st) * np.exp(-st * 30) * 0.4
    ht = np.arange(int(0.06 * SR)) / SR
    hn = rng.standard_normal(len(ht))
    hat = (hn - np.convolve(hn, np.ones(4) / 4, mode="same")) * np.exp(-ht * 70)

    def swung(b, sub):  # beat index b, eighth subdivision sub (0/1)
        return (b + (swing if sub else 0)) * beat

    for bi in range(bars):
        ch = [c + key for c in chords[bi % len(chords)]]
        t0 = bi * bar
        # pad
        add(pad([_hz(c) for c in ch], bar + 0.6), t0, gain=0.10)
        # e-piano: chord on 1, lighter re-hits on the "and" of 2 and on 4
        for when, vel in ((0, 0.9), (1 + swing, 0.5), (3, 0.6)):
            for k, c in enumerate(ch):
                add(epiano(_hz(c + 12), 1.6, vel * rng.uniform(0.85, 1.0)), t0 + when * beat + k * 0.012,
                    pan=(k - 1.5) * 0.25, gain=0.07)
        # simple melody fragments on some bars
        if bi % 4 in (1, 3):
            notes = [ch[3] + 12, ch[2] + 12, ch[1] + 12 + 2]
            for k, m in enumerate(notes):
                add(epiano(_hz(m + 12), 0.9, 0.55), t0 + (2 + k * 0.5 + (swing - 0.5) * (k % 2)) * beat, pan=0.3, gain=0.05)
        # bass
        root = ch[0] - 12
        while root > 40:
            root -= 12
        for when, length in ((0, 1.4), (2.5 if bi % 2 else 2, 1.2)):
            m = int(length * beat * SR)
            tt = np.arange(m) / SR
            b = (np.sin(2 * np.pi * _hz(root) * tt) + 0.2 * np.sin(2 * np.pi * _hz(root) * 2 * tt)) * np.exp(-tt * 1.8)
            b *= np.minimum(1, tt / 0.01)
            add(b, t0 + when * beat, gain=0.28)
        # drums (start quietly on the first bar)
        dg = 0.55 if bi == 0 else 1.0
        for b in range(4):
            if b in (0, 2) or (b == 3 and bi % 4 == 3):
                add(kick, t0 + swung(b if b != 3 else 3, 1 if b == 3 else 0), gain=0.42 * dg)
            if b in (1, 3):
                add(snare, t0 + b * beat, pan=0.05, gain=0.20 * dg)
            for sub in (0, 1):
                add(hat, t0 + swung(b, sub), pan=0.35, gain=(0.09 if sub else 0.12) * rng.uniform(0.7, 1.0) * dg)
    # vinyl crackle + hiss
    crackle = np.zeros(n)
    idx = rng.integers(0, n, size=int(n / SR * 9))
    crackle[idx] = rng.uniform(-1, 1, size=len(idx))
    crackle = np.convolve(crackle, np.exp(-np.arange(60) / 8), mode="same") * 0.05
    hiss = rng.standard_normal(n) * 0.004
    out[:, 0] += crackle + hiss
    out[:, 1] += np.roll(crackle, 37) + hiss
    # warm it up: gentle low-pass on the mix (vectorized one-pole via lfilter if available)
    try:
        from scipy.signal import lfilter
        a = np.exp(-2 * np.pi * 7000 / SR)
        out = lfilter([1 - a], [1, -a], out, axis=0)
    except Exception:
        pass
    out = np.tanh(out * 1.6) / np.tanh(1.6)
    out /= np.max(np.abs(out)) + 1e-9
    out *= 0.89
    return out[: int(SR * bar * bars)]


def write_track(name: str, data, ffmpeg: str) -> Path:
    import numpy as np
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / f"{name}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        target = MUSIC_DIR / f"{name}.m4a"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "128k", str(target)], check=True)
    return target


def main() -> None:
    from .reels import ffmpeg_path
    ff = ffmpeg_path()
    for name, bpm, key, chords, swing, seed in TRACKS:
        path = write_track(name, make_track(bpm, key, chords, swing, seed), ff)
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
