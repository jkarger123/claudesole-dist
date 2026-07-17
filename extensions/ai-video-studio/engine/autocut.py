#!/usr/bin/env python3
"""AUTOCUT -- the intelligent, beat-synced cutter (the core of the tool).

Give it source clips + a song. It:
  1. BEAT-DETECTS the song (beats.py) -> the cut points ("follows the sound").
  2. MOTION-DETECTS each clip -> the money moments (peak-action timestamps + a score).
  3. ASSEMBLES: lays the moments onto the beat grid so every cut lands on a beat; the single biggest moment (the
     "finisher") is placed on a STRONG beat in SLOW-MO; money moment sits at the START of each segment (so it also
     survives CapCut's "pull the first N seconds" auto-fit).
  4. Renders a clean beat-synced cut (NO cartoon overlays -- the pro template/song brings the polish), OR with
     --clips-only, exports each cut segment as its own file to drop into a CapCut template.

Pure orchestration over ffmpeg + the stdlib beat detector -- self-contained, no numpy/AI-API needed, works on
real footage of anyone (no generative model -> no child block)."""
import os, sys, json, subprocess, tempfile, re, collections

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import beats as beatmod

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "bin")
FFMPEG = os.path.join(BIN, "ffmpeg") if os.path.exists(os.path.join(BIN, "ffmpeg")) else "ffmpeg"
FFPROBE = os.path.join(BIN, "ffprobe") if os.path.exists(os.path.join(BIN, "ffprobe")) else "ffprobe"
W, H, FPS = 1080, 1920, 30                                  # DEFAULT canvas = portrait 9:16 (backward-compatible)
def _nf(w, h):                                              # fill-and-crop normalize filter for a w x h canvas
    return "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (w, h, w, h, FPS)
NF = _nf(W, H)                                              # kept for any external import; engine now uses _nf(w,h)


def _run(args): return subprocess.run(args, capture_output=True, text=True)
def _dur(path):
    r = _run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try: return float(r.stdout.strip())
    except Exception: return 0.0


def _dims(path):
    r = _run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
              "-of", "csv=p=0", path])
    try:
        w, h = r.stdout.strip().split(",")[:2]; return int(w), int(h)
    except Exception:
        return 0, 0


def canvas_for(aspect, clips=None):
    """Resolve the output canvas (w, h) from an aspect choice.
      '16:9'/'landscape' -> 1920x1080 ; '9:16'/'portrait' -> 1080x1920.
      'auto'/None/'' -> VOTE by the source clips' own dimensions (landscape if more clips are wider than tall);
      a tie or unknown falls back to portrait (the app's Reels/TikTok default)."""
    a = (aspect or "auto").strip().lower()
    if a in ("16:9", "169", "landscape", "wide"): return 1920, 1080
    if a in ("9:16", "916", "portrait", "tall"): return 1080, 1920
    land = port = 0
    for c in (clips or []):
        w, h = _dims(c)
        if w and h:
            if w > h: land += 1
            elif h > w: port += 1
    return (1920, 1080) if land > port else (1080, 1920)


def motion_peaks(clip, topn=4, min_gap=2.5):
    """Peak-motion timestamps = frame-to-frame difference brightness (tblend difference -> signalstats YAVG),
    averaged per second; return the top windows (well separated) as [(t, score0to1), ...]."""
    tf = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    _run([FFMPEG, "-i", clip, "-vf",
          "scale=320:-1,tblend=all_mode=difference,signalstats,metadata=print:file=%s" % tf, "-an", "-f", "null", "-"])
    t, cur = collections.defaultdict(list), None
    try:
        for line in open(tf):
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m: cur = float(m.group(1))
            m = re.search(r"YAVG=([0-9.]+)", line)
            if m and cur is not None: t[int(cur)].append(float(m.group(1)))
    except Exception: pass
    finally:
        try: os.remove(tf)
        except Exception: pass
    if not t: return []
    persec = {s: sum(v) / len(v) for s, v in t.items()}
    mx = max(persec.values()) or 1.0
    ranked = sorted(persec.items(), key=lambda kv: -kv[1])
    picks = []
    for s, v in ranked:
        if all(abs(s - p[0]) >= min_gap for p in picks):
            picks.append((float(s), v / mx))
        if len(picks) >= topn: break
    return picks


def _seg(clip, start, out_len, dest, slow=1.0, w=W, h=H):
    """Cut [start .. start+out_len] (money moment at the START), normalized to the w x h canvas, optional slow-mo."""
    src_len = out_len / slow if slow != 1.0 else out_len
    vf = "%s,%s" % (("setpts=%.3f*PTS" % slow) if slow != 1.0 else "setpts=PTS", _nf(w, h))
    _run([FFMPEG, "-y", "-ss", "%.3f" % max(0, start), "-i", clip, "-t", "%.3f" % src_len, "-an",
          "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), dest])


def _peak_offset(path):
    """Timestamp (within this segment) of MAX frame-to-frame motion = the actual moment of impact/land. So the
    flash fires ON the hit, not at the cut's start."""
    tf = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    _run([FFMPEG, "-i", path, "-vf",
          "scale=240:-1,tblend=all_mode=difference,signalstats,metadata=print:file=%s" % tf, "-an", "-f", "null", "-"])
    best_t, best_v, cur = 0.0, -1.0, 0.0
    try:
        for line in open(tf):
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m: cur = float(m.group(1))
            m = re.search(r"YAVG=([0-9.]+)", line)
            if m and float(m.group(1)) > best_v: best_v = float(m.group(1)); best_t = cur
    except Exception: pass
    finally:
        try: os.remove(tf)
        except Exception: pass
    return best_t


def _precise_impact(clip, t0, half=0.5):
    """The EXACT max-motion timestamp in the source near t0 (the real land frame) -- so we don't rely on the
    rough hand-picked time. Returns a source-clip timestamp."""
    ss = max(0.0, float(t0) - half)
    tf = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    _run([FFMPEG, "-ss", "%.3f" % ss, "-i", clip, "-t", "%.3f" % (2 * half),
          "-vf", "scale=240:-1,tblend=all_mode=difference,signalstats,metadata=print:file=%s" % tf, "-an", "-f", "null", "-"])
    best_t, best_v, cur = float(t0), -1.0, ss
    try:
        for line in open(tf):
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m: cur = ss + float(m.group(1))
            m = re.search(r"YAVG=([0-9.]+)", line)
            if m and float(m.group(1)) > best_v: best_v = float(m.group(1)); best_t = cur
    except Exception: pass
    finally:
        try: os.remove(tf)
        except Exception: pass
    return best_t


def _impact_fx(path, big=True, at=0.0, w=W, h=H):
    """Bake a DRAMATIC pro-wrestling IMPACT hit, timed to `at` (the detected land frame within the segment):
      - a HARD full-white FLASH (2-3 frames of pure white) + a bright afterglow that decays,
      - a big screen SHAKE (~0.45s, strong amplitude) starting on the hit.
    Pure ffmpeg, canvas-agnostic (works for portrait OR landscape). `big=False` = a lighter non-finisher landing."""
    amp = 28 if big else 18                                 # shake amplitude (px)
    flash = 0.10 if big else 0.06                           # hard full-white duration (s)
    glow = 0.9 if big else 0.6                              # afterglow brightness
    over_w = (w + 160) if big else (w + 120)                # overscan width (bigger = more shake room)
    over_h = int(round(over_w * h / w))                     # keep the canvas aspect while overscanning
    a = max(0.0, float(at))
    tmp = path + ".fx.mp4"
    vf = (
        "scale=%d:%d," % (over_w, over_h) +                 # overscan for shake headroom (canvas aspect kept)
        "crop=%d:%d:" % (w, h) +                            # STATIC output dims (only x/y offsets vary -> valid)
        "x='(iw-%d)/2 + if(between(t,%.3f,%.3f), %d*sin((t-%.3f)*66)*max(0,1-(t-%.3f)/0.45), 0)':"
        % (w, a, a + 0.45, amp, a, a) +
        "y='(ih-%d)/2 + if(between(t,%.3f,%.3f), %d*sin((t-%.3f)*84)*max(0,1-(t-%.3f)/0.45), 0)',"
        % (h, a, a + 0.45, amp, a, a) +
        "drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='between(t,%.3f,%.3f)'," % (a, a + flash) +
        "eq=brightness='if(gte(t,%.3f), max(0,%.2f-5*(t-%.3f)), 0)':eval=frame" % (a, glow, a)
    )
    r = _run([FFMPEG, "-y", "-i", path, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
              "-pix_fmt", "yuv420p", "-r", str(FPS), tmp])
    if os.path.exists(tmp) and _dur(tmp) > 0.05: os.replace(tmp, path)


def apply_flashes(video, out, flashes, w=W, h=H):
    """Apply the impact FX (white flash + shake + afterglow) at EXACT OUTPUT timestamps on the finished cut. The
    user reads the land times off the timecoded edit and gives them here -> pixel-precise, full control. Canvas
    dims (w,h) default portrait but MUST match the video for a landscape edit. `flashes` = [{"t": s, "big": bool}]."""
    if not flashes:
        if video != out: _run([FFMPEG, "-y", "-i", video, "-c", "copy", out])
        return {"ok": True, "out": out, "n": 0}
    over_w = w + 160
    over_h = int(round(over_w * h / w))
    xt, yt, fen, gl = [], [], [], []
    for fl in flashes:
        T = float(fl["t"]); big = bool(fl.get("big"))
        amp = 30 if big else 20; fdur = 0.10 if big else 0.06; glow = 0.95 if big else 0.65
        xt.append("if(between(t,%.3f,%.3f),%d*sin((t-%.3f)*66)*max(0,1-(t-%.3f)/0.45),0)" % (T, T + 0.45, amp, T, T))
        yt.append("if(between(t,%.3f,%.3f),%d*sin((t-%.3f)*84)*max(0,1-(t-%.3f)/0.45),0)" % (T, T + 0.45, amp, T, T))
        fen.append("between(t,%.3f,%.3f)" % (T, T + fdur))
        gl.append("if(gte(t,%.3f),max(0,%.2f-5*(t-%.3f)),0)" % (T, glow, T))
    xexpr = "(iw-%d)/2 + " % w + " + ".join(xt)
    yexpr = "(ih-%d)/2 + " % h + " + ".join(yt)
    gexpr = gl[0]
    for g in gl[1:]: gexpr = "max(%s,%s)" % (gexpr, g)
    vf = ("scale=%d:%d,crop=%d:%d:x='%s':y='%s',"
          "drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='gt(%s,0)',"
          "eq=brightness='%s':eval=frame") % (over_w, over_h, w, h, xexpr, yexpr, "+".join(fen), gexpr)
    dst = out if out != video else out + ".fx.mp4"        # never read+write the SAME file with ffmpeg
    r = _run([FFMPEG, "-y", "-i", video, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
              "-pix_fmt", "yuv420p", "-c:a", "copy", dst])
    ok = os.path.exists(dst) and _dur(dst) > 0.05
    if ok and dst != out: os.replace(dst, out)
    return {"ok": ok, "out": out, "n": len(flashes), "at": [round(f["t"], 2) for f in flashes],
            "error": None if ok else (r.stderr or "")[-200:]}


def build_project(clips, music, beats_per_cut=1, shot_plan=None, lead=0.25, hero_speed=0.417, w=W, h=H):
    """AUTO-BUILD: beat-detect + motion-detect + sequence -> emit the shared PROJECT JSON (the source of truth the
    manual timeline + edl.render + the CapCut exporter all consume). Same logic as build() but produces an EDL
    instead of rendering. speed FACTOR convention: <1 = slow-mo (hero ~0.417 = 2.4x slower)."""
    b = beatmod.analyze(music)
    if not b.get("ok"): return {"ok": False, "error": "beat detect: " + b.get("error", "?")}
    grid = [x["t"] for x in b["beats"]]
    if len(grid) < 4: return {"ok": False, "error": "not enough beats"}
    bpc = max(1, int(beats_per_cut))
    if shot_plan:
        sequence = [dict(s) for s in shot_plan]; mode = "ai"
    else:
        moments = []
        for c in clips:
            for (t, sc) in motion_peaks(c): moments.append({"clip": c, "t": t, "score": sc})
        if not moments: return {"ok": False, "error": "no motion moments found"}
        moments.sort(key=lambda m: -m["score"])
        hero = dict(moments[0], hero=True); rest = moments[1:] or [dict(moments[0])]
        mode = "deterministic"
    last = len(grid) - 1
    if mode == "ai":
        N = len(sequence)
        bounds = [min(last, int(round(k * last / N))) for k in range(N + 1)]
        slots = list(zip(bounds[:-1], bounds[1:]))
    else:
        # Target a cut LENGTH by pace (decouple from raw beat density) -- keeps cuts landing on beats but stops the
        # 0.5s machine-gun when the tempo detector doubles. Still snaps every cut boundary to a beat.
        target = {1: 0.55, 2: 0.95, 4: 1.7}.get(bpc, 0.95)
        slots, i = [], 0
        while i < last and len(slots) < 40:
            j = i + 1
            while j < last and (grid[j] - grid[i]) < target: j += 1
            slots.append((i, j)); i = j
        n = len(slots)
        sequence = [dict(rest[k % len(rest)]) for k in range(n)]
        if n: sequence[min(n - 1, int(n * 0.66))] = hero      # the finisher lands ~2/3 through, in slow-mo

    sources, sidmap = {}, {}
    def sid(path):
        if path not in sidmap:
            k = "src%d" % len(sidmap); sidmap[path] = k; sources[k] = {"kind": "video", "path": path}
        return sidmap[path]
    durc = {}
    def _durc(p): return durc.setdefault(p, _dur(p))
    vclips, fxclips, out_pos = [], [], 0.0
    for shot, (a, e) in zip(sequence, slots):
        if e <= a: continue
        slot_len = grid[e] - grid[a]
        is_hero = bool(shot.get("hero")); is_impact = bool(is_hero or shot.get("impact"))
        speed = float(shot.get("speed", hero_speed if is_hero else 1.0))
        if is_impact:
            ti = float(shot["t"]) if shot.get("exact") else _precise_impact(shot["clip"], float(shot["t"]))
            in_t = max(0.0, ti - lead)
        else:
            in_t = max(0.0, float(shot["t"]) - 0.15)
        window = slot_len * speed                 # how much SOURCE this slot needs
        sd = _durc(shot["clip"])                  # clamp so in+window never runs past the source end (no short/frozen cut)
        if sd > window: in_t = max(0.0, min(in_t, sd - window - 0.03))
        vclips.append({"source": sid(shot["clip"]), "in": round(in_t, 3), "out": round(in_t + window, 3),
                       "start": round(out_pos, 3), "speed": round(speed, 3), "hero": is_hero, "volume": 0.0})
        if is_impact:
            fxclips.append({"at": round(out_pos + lead / speed, 3), "type": "impact", "big": is_hero})
        out_pos += slot_len
    if not vclips: return {"ok": False, "error": "no clips built"}
    sources["music"] = {"kind": "audio", "path": music}
    project = {"version": 1, "canvas": {"w": w, "h": h, "fps": FPS}, "duration": round(out_pos, 2), "mode": mode,
               "sources": sources,
               "tracks": [{"id": "v1", "kind": "video", "clips": vclips},
                          {"id": "fx1", "kind": "effects", "clips": fxclips},
                          {"id": "txt1", "kind": "text", "clips": []},
                          {"id": "a1", "kind": "audio", "clips": [{"source": "music", "in": 0.0,
                           "out": round(out_pos, 2), "start": 0.0, "volume": 1.0}]}],
               "music": {"bpm": b.get("bpm"), "beat_period_sec": b.get("beat_period_sec"),
                         "beats": grid, "hit_beats": b.get("hit_beats", [])}}
    return {"ok": True, "project": project}


def build(clips, music, out, clips_only=False, max_secs=None, beats_per_cut=1, shot_plan=None, effects=True, w=W, h=H):
    b = beatmod.analyze(music)
    if not b.get("ok"): return {"ok": False, "error": "beat detect: " + b.get("error", "?")}
    grid = [x["t"] for x in b["beats"]]
    if len(grid) < 4: return {"ok": False, "error": "not enough beats"}
    bpc = max(1, int(beats_per_cut))       # beats per cut: 1=frantic, 2=punchy, 4=cinematic

    # ---- SHOT SEQUENCE: AI mode (an explicit ordered plan from a vision model / Claude -- moments chosen by
    #      MEANING) vs DETERMINISTIC (motion-energy heuristic -- "most pixels moved", no understanding, no AI). ----
    if shot_plan:
        sequence = [dict(s) for s in shot_plan]           # AI: play the moments exactly, in the given order
        mode = "ai"
    else:
        moments = []
        for c in clips:
            for (t, sc) in motion_peaks(c):
                moments.append({"clip": c, "t": t, "score": sc})
        if not moments: return {"ok": False, "error": "no motion moments found"}
        moments.sort(key=lambda m: -m["score"])
        hero = dict(moments[0], hero=True)                # biggest MOTION = finisher (crude vs AI's understanding)
        rest = moments[1:] or [dict(moments[0])]
        n = max(len(rest), len(grid) // bpc + 2)
        sequence = [dict(rest[k % len(rest)]) for k in range(n)]
        sequence.insert(int(len(sequence) * 0.66), hero)  # drop the hero ~2/3 through
        mode = "deterministic"

    work = os.path.join(tempfile.mkdtemp(), "seg")
    os.makedirs(work, exist_ok=True)
    last = len(grid) - 1

    # decide each shot's (start_beat, end_beat) slot -- every cut lands on a beat either way:
    if mode == "ai":
        # AI: distribute the chosen shots EVENLY across the whole section so they fill it (robust to tempo octave)
        N = len(sequence)
        bounds = [min(last, int(round(k * last / N))) for k in range(N + 1)]
        slots = list(zip(bounds[:-1], bounds[1:]))
    else:
        # deterministic: consecutive bpc-beat slots, hero gets one extra beat
        slots, i = [], 0
        for shot in sequence:
            if i >= last: break
            span = min((bpc + 1) if shot.get("hero") else bpc, last - i)
            if span < 1: break
            slots.append((i, i + span)); i += span
        sequence = sequence[:len(slots)]

    segs, plan = [], []
    for shot, (a, e) in zip(sequence, slots):
        if e <= a: continue
        if max_secs and grid[a] >= max_secs: break
        slot_len = grid[e] - grid[a]
        is_hero = bool(shot.get("hero"))
        is_impact = bool(is_hero or shot.get("impact"))
        slow = float(shot.get("slow", 2.2 if is_hero else 1.0))
        lead = 0.25                                        # run-up shown before the land
        if is_impact:
            # exact=True -> trust the user's hand-scrubbed time verbatim; else auto-detect the land near the hint
            ti = float(shot["t"]) if shot.get("exact") else _precise_impact(shot["clip"], float(shot["t"]))
            start = max(0.0, ti - lead)
            fx_at = lead * slow                            # where that land sits in the OUTPUT segment (slow-aware)
        else:
            start = max(0.0, float(shot["t"]) - 0.15)
            fx_at = 0.0
        dest = os.path.join(work, "s%03d.mp4" % len(segs))
        _seg(shot["clip"], start, slot_len, dest, slow=slow, w=w, h=h)
        if effects and is_impact and _dur(dest) > 0.05:   # flash fires ON the land
            _impact_fx(dest, big=is_hero, at=fx_at, w=w, h=h)
        if _dur(dest) > 0.05:
            segs.append(dest); plan.append({"beat": round(grid[a], 2), "clip": os.path.basename(shot["clip"]),
                                            "at": round(float(shot["t"]), 1), "len": round(slot_len, 2),
                                            "slow_mo": slow != 1.0, "hero": is_hero, "impact": is_impact})

    if not segs: return {"ok": False, "error": "no segments built"}

    if clips_only:
        outs = []
        for k, s in enumerate(segs):
            d = out.replace(".mp4", "") + "_%02d.mp4" % (k + 1)
            os.replace(s, d) if os.path.exists(s) else None
            outs.append(d)
        return {"ok": True, "clips": outs, "n": len(outs), "bpm": b["bpm"], "mode": mode, "plan": plan}

    # concat segments -> add the song -> render (clean, no overlays)
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join("file '%s'\n" % s for s in segs))
    silent = os.path.join(work, "silent.mp4")
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])
    vlen = _dur(silent)
    _run([FFMPEG, "-y", "-i", silent, "-i", music, "-filter_complex",
          "[1:a]atrim=0:%.2f,aresample=48000,aformat=channel_layouts=stereo,volume=1.0[a]" % vlen,
          "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-shortest", out])
    return {"ok": True, "output": out, "duration": round(vlen, 2), "bpm": b["bpm"], "mode": mode,
            "n_cuts": len(segs), "plan": plan}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clips-only", action="store_true")
    ap.add_argument("--max-secs", type=float, default=None)
    ap.add_argument("clips", nargs="+")
    a = ap.parse_args()
    print(json.dumps(build(a.clips, a.music, a.out, clips_only=a.clips_only, max_secs=a.max_secs), indent=2))
