#!/usr/bin/env python3
"""BEAT DETECTION -- "the edit follows the sound."

Given any audio/video file (a song, or a CapCut template's exported clip), find the TEMPO and the timestamp of
every beat. Those beat times are the CUT POINTS: a hype edit lands its cuts on the beat, so once we know the
beats we know where each clip should start/end. Pure stdlib (wave/struct/math) + ffmpeg for decode -- no numpy,
no librosa -- so it ships self-contained with the extension.

Method (classic onset-envelope beat tracking):
  1. decode to mono 22050 Hz PCM (ffmpeg)
  2. short-time energy envelope (hop ~11 ms)
  3. onset function = rectified positive energy difference (where new sound hits)
  4. tempo = autocorrelation peak of the onset function in the 60-200 BPM lag range
  5. beat phase = the offset that maximizes onset energy on the tempo grid
  6. emit beat timestamps (seconds) + BPM
"""
import os, sys, wave, struct, math, subprocess, tempfile, json

SR = 22050
HOP = 256                      # ~11.6 ms per frame
FFMPEG = os.environ.get("CC_FFMPEG") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))), "bin", "ffmpeg")
if not os.path.exists(FFMPEG): FFMPEG = "ffmpeg"


def _decode(path):
    """ffmpeg -> mono 22050 Hz 16-bit PCM WAV -> list of float samples in [-1,1]."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run([FFMPEG, "-y", "-i", path, "-ac", "1", "-ar", str(SR), "-vn", tmp],
                   capture_output=True)
    w = wave.open(tmp, "rb"); n = w.getnframes(); raw = w.readframes(n); w.close()
    try: os.remove(tmp)
    except Exception: pass
    if not raw: return []
    ints = struct.unpack("<%dh" % (len(raw) // 2), raw[: (len(raw) // 2) * 2])
    return [s / 32768.0 for s in ints]


def _onset_env(samples):
    """Energy per hop -> rectified first difference = onset strength envelope."""
    energy = []
    for i in range(0, len(samples) - HOP, HOP):
        e = 0.0
        for j in range(i, i + HOP): e += samples[j] * samples[j]
        energy.append(math.sqrt(e / HOP))
    onset = [0.0]
    for k in range(1, len(energy)):
        onset.append(max(0.0, energy[k] - energy[k - 1]))
    return onset


def _tempo(onset):
    """Autocorrelate the onset envelope, pick the strongest lag (60-220 BPM), then OCTAVE-CORRECT toward the
    faster pulse -- a periodic signal autocorrelates just as strongly at 2x/3x the true period (half/third-time),
    so we step down to the fastest lag that's still ~as strong. Fixes the 150->75 BPM half-time trap."""
    hop_sec = HOP / SR
    lo = max(2, int((60.0 / 220.0) / hop_sec))     # up to 220 BPM
    hi = int((60.0 / 60.0) / hop_sec)              # down to 60 BPM
    ac = {}
    for lag in range(lo, min(hi, len(onset) - 1)):
        s = 0.0
        for i in range(lag, len(onset)): s += onset[i] * onset[i - lag]
        ac[lag] = s
    if not ac: return lo
    cand = max(ac, key=ac.get)
    while cand // 2 >= lo:                          # prefer the faster pulse if it's nearly as strong
        h = cand // 2
        near = max(ac.get(h - 1, 0), ac.get(h, 0), ac.get(h + 1, 0))
        if near >= 0.60 * ac[cand]: cand = h
        else: break
    return cand


def _beats(onset, period):
    """Pick the phase (0..period) that maximizes onset energy on the tempo grid, then emit (frame, strength)."""
    best_phase, best = 0, -1.0
    for phase in range(period):
        s = 0.0; i = phase
        while i < len(onset): s += onset[i]; i += period
        if s > best: best, best_phase = s, phase
    out = []; i = best_phase
    while i < len(onset): out.append((i, onset[i])); i += period
    return out


def analyze(path):
    samples = _decode(path)
    if not samples: return {"ok": False, "error": "no audio decoded"}
    onset = _onset_env(samples)
    if len(onset) < 8: return {"ok": False, "error": "audio too short"}
    period = _tempo(onset)
    hop_sec = HOP / SR
    bpm = round(60.0 / (period * hop_sec), 1)
    raw = _beats(onset, period)
    mx = max((s for _, s in raw), default=1.0) or 1.0
    beats = [{"t": round(f * hop_sec, 3), "strength": round(s / mx, 2)} for f, s in raw]
    # the STRONGEST beats = the hits/drops -> where the biggest action (the slam) should land
    strong = sorted(beats, key=lambda b: -b["strength"])[:max(1, len(beats) // 6)]
    return {"ok": True, "bpm": bpm, "beat_period_sec": round(period * hop_sec, 3),
            "n_beats": len(beats), "duration": round(len(samples) / SR, 2),
            "beats": beats, "hit_beats": sorted(b["t"] for b in strong)}


if __name__ == "__main__":
    if len(sys.argv) < 2: print("usage: beats.py <audio-or-video-file>"); sys.exit(1)
    print(json.dumps(analyze(sys.argv[1]), indent=2))
