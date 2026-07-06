#!/usr/bin/env python3
"""PROJECT BUILD + MEDIA CACHE -- the timeline editor's data layer.

Turns clips + a song into a SAVED, editable project JSON (the same shape edl.render consumes), and generates the
cheap visual assets the timeline UI draws: a filmstrip sprite per video source + a waveform JSON for the music.
Everything the manual timeline needs to render a legible, editable EDL without re-running ffmpeg on every gesture.

CLI:  project.py emit  <out.json> <cache_dir> <music> [--section S] [--pace P] [--plan plan.json] clip1 clip2 ...
      project.py thumbs <src> <dest_sprite.jpg> [n]
"""
import os, sys, json, subprocess, tempfile, struct, math

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import autocut as ac
import music as musicmod

FFMPEG, FFPROBE = ac.FFMPEG, ac.FFPROBE
SPRITE_N = 12          # frames per filmstrip
SPRITE_H = 120         # sprite tile height (px)


def _dims(path):
    r = ac._run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", path])
    try:
        w, h = r.stdout.strip().split(",")[:2]; return int(w), int(h)
    except Exception:
        return 0, 0


def filmstrip(src, dest, n=SPRITE_N):
    """A horizontal N-frame sprite of the WHOLE source (evenly sampled) -> the timeline paints a slice per clip."""
    dur = ac._dur(src) or 0.1
    tw = int(SPRITE_H * 9 / 16)                                # 9:16 tiles
    fps = max(0.01, n / dur)
    vf = "fps=%.4f,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,tile=%dx1" % (
        fps, tw, SPRITE_H, tw, SPRITE_H, n)
    ac._run([FFMPEG, "-y", "-i", src, "-vf", vf, "-frames:v", "1", "-q:v", "4", dest])
    return {"path": dest, "n": n, "tile_w": tw, "tile_h": SPRITE_H, "dur": round(dur, 3)} if os.path.exists(dest) else None


def waveform(audio, buckets=500):
    """Down-sample the track to mono PCM and return `buckets` normalized RMS peaks (0..1) for the music lane."""
    try:
        r = subprocess.run([FFMPEG, "-v", "error", "-i", audio, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                           capture_output=True)
        raw = r.stdout
        if not raw: return []
        n = len(raw) // 2
        samples = struct.unpack("<%dh" % n, raw[:n * 2])
        if not samples: return []
        step = max(1, n // buckets)
        out = []
        for i in range(0, n, step):
            chunk = samples[i:i + step]
            if not chunk: break
            rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
            out.append(rms)
        mx = max(out) or 1.0
        return [round(v / mx, 3) for v in out]
    except Exception:
        return []


def emit(out_json, cache_dir, music_source, clips, section=None, pace="punchy", shot_plan=None):
    """Build a SAVED project + its media cache. Returns {ok, project} (also writes out_json)."""
    m = musicmod.get_music(music_source, section=section)
    if not m.get("ok"): return {"ok": False, "stage": "music", "error": m.get("error")}
    bpc = {"frantic": 1, "punchy": 2, "cinematic": 4}.get(pace, 2)
    r = ac.build_project(clips, m["path"], beats_per_cut=bpc, shot_plan=shot_plan)
    if not r.get("ok"): return r
    proj = r["project"]
    os.makedirs(cache_dir, exist_ok=True)
    # copy the resolved music into the cache so the project is self-contained (yt-dlp temp dirs get reaped)
    music_dest = os.path.join(cache_dir, "music.mp3")
    try:
        if os.path.abspath(m["path"]) != os.path.abspath(music_dest):
            ac._run([FFMPEG, "-y", "-i", m["path"], "-c", "copy", music_dest])
        if os.path.exists(music_dest): proj["sources"]["music"]["path"] = music_dest
    except Exception: pass
    # per-source assets: dims + filmstrip (video) / waveform (music)
    for sid, s in proj["sources"].items():
        p = s.get("path")
        if not p or not os.path.exists(p): continue
        if s.get("kind") == "video":
            w, h = _dims(p); s["w"], s["h"] = w, h; s["dur"] = round(ac._dur(p), 3)
            spr = os.path.join(cache_dir, "strip_%s.jpg" % sid)
            fs = filmstrip(p, spr)
            if fs: s["thumb"] = spr; s["strip"] = fs
        elif s.get("kind") == "audio":
            s["dur"] = round(ac._dur(p), 3); s["wave"] = waveform(p)
    proj["saved"] = os.path.basename(out_json)
    with open(out_json, "w") as f: json.dump(proj, f, indent=2)
    return {"ok": True, "project": proj, "path": out_json, "music_source": m.get("source")}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "thumbs":
        n = int(a[3]) if len(a) > 3 else SPRITE_N
        print(json.dumps(filmstrip(a[1], a[2], n)))
    elif a and a[0] == "emit":
        out_json, cache_dir, music = a[1], a[2], a[3]
        rest = a[4:]; section = pace = plan = None; clips = []
        i = 0
        while i < len(rest):
            if rest[i] == "--section": section = rest[i + 1]; i += 2
            elif rest[i] == "--pace": pace = rest[i + 1]; i += 2
            elif rest[i] == "--plan": plan = rest[i + 1]; i += 2
            else: clips.append(rest[i]); i += 1
        sp = json.load(open(plan)) if plan and os.path.exists(plan) else None
        print(json.dumps(emit(out_json, cache_dir, music, clips, section=section, pace=(pace or "punchy"), shot_plan=sp)))
    else:
        print("usage: project.py emit <out.json> <cache_dir> <music> [--section S] [--pace P] clips... | thumbs <src> <dest> [n]")
        sys.exit(1)
