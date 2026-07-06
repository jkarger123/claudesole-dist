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


def _probe_source(cache_dir, path):
    """Probe one video source (dims + duration) + make its filmstrip. Returns the sources[] entry dict."""
    sid = "src_" + str(abs(hash(path)) % 10**8)
    dur = round(ac._dur(path), 3); w, h = _dims(path)
    s = {"kind": "video", "path": path, "dur": dur, "w": w, "h": h}
    os.makedirs(cache_dir, exist_ok=True)
    spr = os.path.join(cache_dir, "strip_%s.jpg" % sid)
    fs = filmstrip(path, spr)
    if fs: s["thumb"] = spr; s["strip"] = fs
    return sid, s


def manual(out_json, cache_dir, clips, music_source=None, section=None):
    """MANUAL project: lay each clip on the timeline at FULL length in order (no beat-cutting). Optional music."""
    os.makedirs(cache_dir, exist_ok=True)
    sources, sidmap, vclips, pos = {}, {}, [], 0.0
    for c in clips:
        if not os.path.exists(c): continue
        if c not in sidmap:
            sid, s = _probe_source(cache_dir, c); sidmap[c] = sid; sources[sid] = s
        sid = sidmap[c]; dur = sources[sid]["dur"] or 3.0
        vclips.append({"source": sid, "in": 0.0, "out": round(dur, 3), "start": round(pos, 3),
                       "speed": 1.0, "volume": 0.0})
        pos += dur
    if not vclips: return {"ok": False, "error": "no usable clips"}
    tracks = [{"id": "v1", "kind": "video", "clips": vclips},
              {"id": "fx1", "kind": "effects", "clips": []},
              {"id": "txt1", "kind": "text", "clips": []},
              {"id": "ov1", "kind": "overlay", "clips": []}]
    music = {}
    if music_source:
        r = resolve_audio(cache_dir, music_source, section=section)
        if r.get("ok"):
            sources["music"] = {"kind": "audio", "path": r["path"], "dur": r["dur"], "wave": r["wave"]}
            tracks.append({"id": "a1", "kind": "audio", "clips": [{"source": "music", "in": 0.0,
                           "out": round(pos, 2), "start": 0.0, "volume": 1.0}]})
    if "music" not in sources:
        tracks.append({"id": "a1", "kind": "audio", "clips": []})
    project = {"version": 1, "canvas": {"w": ac.W, "h": ac.H, "fps": ac.FPS}, "duration": round(pos, 2),
               "mode": "manual", "sources": sources, "tracks": tracks, "music": music}
    with open(out_json, "w") as f: json.dump(project, f, indent=2)
    return {"ok": True, "project": project, "path": out_json}


def resolve_audio(cache_dir, source, section=None):
    """Resolve an audio source (uploaded file OR YouTube/URL) -> a cached mp3 + waveform (add/replace the track)."""
    m = musicmod.get_music(source, section=section)
    if not m.get("ok"): return {"ok": False, "error": m.get("error")}
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, "audio_%s.mp3" % (abs(hash(source)) % 10**8))
    try:
        ac._run([FFMPEG, "-y", "-i", m["path"], "-c", "copy", dest])
        mp = dest if (os.path.exists(dest) and os.path.getsize(dest) > 500) else m["path"]
    except Exception:
        mp = m["path"]
    return {"ok": True, "path": mp, "dur": round(ac._dur(mp), 3), "wave": waveform(mp), "source": m.get("source")}


def add_clip(cache_dir, path):
    """Probe + filmstrip one new clip added inside the editor -> {ok, id, source}."""
    if not os.path.exists(path): return {"ok": False, "error": "file not found"}
    sid, s = _probe_source(cache_dir, path)
    return {"ok": True, "id": sid, "source": s}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "manual":
        out_json, cache_dir = a[1], a[2]; rest = a[3:]; music = section = None; clips = []
        i = 0
        while i < len(rest):
            if rest[i] == "--music": music = rest[i + 1]; i += 2
            elif rest[i] == "--section": section = rest[i + 1]; i += 2
            else: clips.append(rest[i]); i += 1
        print(json.dumps(manual(out_json, cache_dir, clips, music_source=music, section=section)))
    elif a and a[0] == "resolve":
        sec = a[3] if len(a) > 3 else None
        print(json.dumps(resolve_audio(a[1], a[2], section=sec)))
    elif a and a[0] == "addclip":
        print(json.dumps(add_clip(a[1], a[2])))
    elif a and a[0] == "thumbs":
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
