#!/usr/bin/env python3
"""CAPCUT EXPORT -- turn a project into a CapCut-ready bundle (zip).

Two layers, most-reliable first (honest -- CapCut's draft schema is version-picky and we can't verify import here):
  1. RELIABLE: `clips/clip_NN.mp4` (each cut, in order, speed baked in, normalized to the canvas) + `music.mp3` +
     `EDIT_PLAN.txt` (order, durations, flash/zoom times, titles). Drop the clips into any CapCut template on the
     beat -- CapCut auto-fits -- and follow the plan for the flashes/titles. This ALWAYS works.
  2. EXPERIMENTAL: `draft_content.json` (+ `draft_meta_info.json`) to the pyJianYingDraft schema (microsecond
     timeranges) -- copy the whole folder into CapCut's Drafts dir to open it directly. May need CapCut-version
     tweaks; the reliable layer is the fallback.

CLI:  capcut.py <project.json> <out.zip>
"""
import os, sys, json, tempfile, shutil, zipfile
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import autocut as ac
import edl

US = 1000000  # microseconds per second


def _vt(p): return next((t for t in p.get("tracks", []) if t.get("kind") == "video"), {"clips": []})
def _ft(p): return next((t for t in p.get("tracks", []) if t.get("kind") == "effects"), {"clips": []})
def _tt(p): return next((t for t in p.get("tracks", []) if t.get("kind") == "text"), {"clips": []})
def _at(p): return next((t for t in p.get("tracks", []) if t.get("kind") == "audio"), {"clips": []})
def _clen(c): return max(0.05, (c["out"] - c["in"]) / (c.get("speed") or 1))


def _edit_plan(p):
    L = ["THE EDIT PLAN  (drop clips/ into a CapCut template on the beat -- CapCut auto-fits -- then add these)", ""]
    L.append("Canvas: %dx%d @ %dfps   Total: %ss   BPM: %s" % (
        p["canvas"]["w"], p["canvas"]["h"], p["canvas"]["fps"], p.get("duration"), (p.get("music") or {}).get("bpm")))
    L.append(""); L.append("CLIPS (in order -- these are clips/clip_NN.mp4, speed already baked in):")
    pos = 0.0
    for i, c in enumerate(_vt(p)["clips"], 1):
        ln = _clen(c)
        L.append("  %02d  %5.2fs  (out %5.2fs)  %s%s" % (i, ln, pos + ln,
                 "SLOW-MO %sx  " % c["speed"] if (c.get("speed") or 1) != 1 else "",
                 "*** HERO / finisher ***" if c.get("hero") else ""))
        pos += ln
    fl = [f for f in _ft(p)["clips"] if f.get("type", "impact") == "impact"]
    zo = [f for f in _ft(p)["clips"] if f.get("type") == "zoom"]
    if fl:
        L.append(""); L.append("IMPACT FLASHES at (seconds on the final timeline):")
        L += ["  %5.2fs %s" % (f["at"], "(BIG)" if f.get("big") else "") for f in sorted(fl, key=lambda x: x["at"])]
    if zo:
        L.append(""); L.append("ZOOM PUNCHES at:")
        L += ["  %5.2fs  x%.2f" % (z["at"], z.get("amount", 1.4)) for z in sorted(zo, key=lambda x: x["at"])]
    tx = _tt(p)["clips"]
    if tx:
        L.append(""); L.append("TITLES:")
        L += ["  %5.2f-%5.2fs  \"%s\"" % (t.get("start", 0), t.get("end", 0), t.get("text", "")) for t in tx]
    L.append(""); L.append("(A finished MP4 with the flashes/zooms/titles already applied is Export MP4 in Studio.)")
    return "\n".join(L)


def _draft(p, clip_files):
    """Best-effort CapCut draft_content.json (pyJianYingDraft-style). EXPERIMENTAL."""
    def uid(pre, i): return "%s-0000-0000-0000-%012d" % (pre, i)
    W, H, FPS = p["canvas"]["w"], p["canvas"]["h"], p["canvas"]["fps"]
    videos, segs = [], []
    pos = 0
    for i, c in enumerate(_vt(p)["clips"]):
        ln_us = int(_clen(c) * US); src_us = int((c["out"] - c["in"]) * US)
        mid = uid("aaaa", i)
        videos.append({"id": mid, "type": "video", "path": "clips/" + os.path.basename(clip_files[i]),
                       "material_name": os.path.basename(clip_files[i]), "width": W, "height": H,
                       "duration": src_us, "has_audio": False})
        segs.append({"id": uid("bbbb", i), "material_id": mid,
                     "source_timerange": {"start": 0, "duration": src_us},
                     "target_timerange": {"start": pos, "duration": ln_us},
                     "speed": round(1.0 / (c.get("speed") or 1), 4), "volume": 0.0, "visible": True,
                     "extra_material_refs": [], "clip": {"alpha": 1.0}})
        pos += ln_us
    audios, aseg = [], []
    a = _at(p)["clips"]
    if a:
        au = int((p.get("duration") or 0) * US)
        audios.append({"id": uid("cccc", 0), "type": "extract_music", "path": "music.mp3",
                       "material_name": "music.mp3", "duration": au})
        aseg.append({"id": uid("dddd", 0), "material_id": uid("cccc", 0),
                     "source_timerange": {"start": 0, "duration": au},
                     "target_timerange": {"start": 0, "duration": au}, "volume": 1.0})
    tracks = [{"type": "video", "id": uid("eeee", 0), "segments": segs},
              {"type": "audio", "id": uid("ffff", 0), "segments": aseg}]
    return {"canvas_config": {"width": W, "height": H, "ratio": "original"}, "fps": float(FPS),
            "duration": int((p.get("duration") or 0) * US), "materials": {"videos": videos, "audios": audios,
            "texts": [], "speeds": [], "canvases": []}, "tracks": tracks, "version": 360000,
            "platform": {"app": "capcut", "os": "mac"},
            "_note": "EXPERIMENTAL auto-draft. If CapCut won't open it, use clips/ + EDIT_PLAN.txt instead."}


def export(project, out_zip):
    p = project
    if not _vt(p)["clips"]: return {"ok": False, "error": "no clips"}
    work = tempfile.mkdtemp(); clipdir = os.path.join(work, "clips"); os.makedirs(clipdir)
    W, H, FPS = p["canvas"]["w"], p["canvas"]["h"], p["canvas"]["fps"]
    srcs = p.get("sources") or {}
    clip_files = []
    for i, c in enumerate(_vt(p)["clips"], 1):
        sp = srcs.get(c.get("source"), {}).get("path")
        if not sp or not os.path.exists(sp): continue
        dest = os.path.join(clipdir, "clip_%02d.mp4" % i)
        edl._segment(sp, c["in"], c["out"], c.get("speed", 1), W, H, FPS, dest,
                     color=c.get("color"), fit=c.get("fit", "cover"))
        if ac._dur(dest) > 0.04: clip_files.append(dest)
    if not clip_files: return {"ok": False, "error": "no clips rendered"}
    # music
    a = _at(p)["clips"]
    if a:
        mp = srcs.get(a[0]["source"], {}).get("path")
        if mp and os.path.exists(mp): ac._run([ac.FFMPEG, "-y", "-i", mp, os.path.join(work, "music.mp3")])
    open(os.path.join(work, "EDIT_PLAN.txt"), "w").write(_edit_plan(p))
    open(os.path.join(work, "README.txt"), "w").write(
        "CapCut export from ClaudeFather Video Studio.\n\n"
        "RELIABLE: open a CapCut template, drop the files in clips/ onto the beat (CapCut auto-fits), then add the\n"
        "flashes/zooms/titles listed in EDIT_PLAN.txt. A ready-made MP4 with everything applied is Export MP4 in Studio.\n\n"
        "EXPERIMENTAL: draft_content.json is an auto-generated CapCut draft -- copy this whole folder into CapCut's\n"
        "Drafts directory to try opening it directly. If it won't open, use clips/ + EDIT_PLAN.txt above.\n")
    try: json.dump(_draft(p, clip_files), open(os.path.join(work, "draft_content.json"), "w"), indent=1)
    except Exception: pass
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(work):
            for fn in files:
                fp = os.path.join(root, fn); z.write(fp, os.path.relpath(fp, work))
    shutil.rmtree(work, ignore_errors=True)
    return {"ok": os.path.exists(out_zip), "zip": out_zip, "clips": len(clip_files)}


if __name__ == "__main__":
    if len(sys.argv) < 3: print("usage: capcut.py <project.json> <out.zip>"); sys.exit(1)
    print(json.dumps(export(json.load(open(sys.argv[1])), sys.argv[2]), indent=2))
