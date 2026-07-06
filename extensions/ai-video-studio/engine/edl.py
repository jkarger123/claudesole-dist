#!/usr/bin/env python3
"""EDL RENDERER -- compile a project JSON (the single source of truth) into an MP4.

One project document is shared by four consumers: the AI auto-build WRITES it (autocut.build_project), the manual
timeline editor READS/EDITS it, THIS module RENDERS it, and the CapCut exporter maps it. Everything is in seconds
on the OUTPUT timeline (the currency apply_flashes + drawtext enable= already speak).

Project shape (P1 subset; extends to text/zoom/multitrack later):
  {
    "canvas": {"w":1080,"h":1920,"fps":30},
    "duration": 12.8,
    "sources": {"<id>": {"kind":"video|audio","path":"<abs or rel>"}, ...},
    "tracks": [
      {"kind":"video",   "clips":[{"source","in","out","start","speed","hero","volume"}...]},
      {"kind":"effects", "clips":[{"at","type":"impact|zoom","big","amount","dur"}...]},
      {"kind":"text",    "clips":[{"start","end","text","style":{...}}...]},
      {"kind":"audio",   "clips":[{"source","in","out","start","volume"}...]}
    ]
  }

Reuses the low-level ffmpeg helpers + apply_flashes from autocut.py (no circular import: autocut lazy-imports edl)."""
import os, tempfile
import autocut as ac

FFMPEG, FFPROBE = ac.FFMPEG, ac.FFPROBE
FONT = next((f for f in ["/System/Library/Fonts/Supplemental/Impact.ttf",
                         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if os.path.exists(f)), None)


def _tracks(project, kind):
    return [c for t in project.get("tracks", []) if t.get("kind") == kind for c in t.get("clips", [])]


def _segment(src_path, in_t, out_t, speed, w, h, fps, dest, proxy=False):
    """Cut [in..out] of a source, apply speed (speed<1 => slow-mo), normalize to the canvas. Output length =
    (out-in)/speed. `proxy` = a fast small preview encode."""
    src_len = max(0.05, float(out_t) - float(in_t))
    sp = float(speed) if speed else 1.0                    # speed FACTOR: <1 = slow-mo (output longer)
    ow = 480 if proxy else w
    oh = int(ow * h / w)
    nf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (ow, oh, ow, oh, fps)
    # setpts multiplier = 1/speed  (speed 0.5 -> setpts 2*PTS -> 2x slower). output len = src_len / speed.
    vf = ("setpts=%.4f*PTS," % (1.0 / sp) if sp != 1.0 else "setpts=PTS,") + nf
    preset = "ultrafast" if proxy else "veryfast"
    ac._run([FFMPEG, "-y", "-ss", "%.3f" % max(0, float(in_t)), "-i", src_path, "-t", "%.3f" % src_len, "-an",
             "-vf", vf, "-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(fps), dest])
    return ac._dur(dest)


def _drawtext_chain(text_clips):
    """Build one drawtext filter chain: each text clip shown only during [start,end] (enable=between)."""
    parts = []
    for c in text_clips:
        s = (c.get("style") or {})
        txt = str(c.get("text", "")).replace("'", "").replace(":", "\\:")
        size = int(s.get("size", 80)); color = s.get("color", "white")
        y = s.get("y", 0.12); ypx = "(h*%s)" % y if isinstance(y, (int, float)) else "(h-th)/2"
        box = ":box=1:boxcolor=%s:boxborderw=14" % (s.get("boxcolor", "black@0.55")) if s.get("box", True) else ""
        ff = "fontfile='%s':" % FONT if FONT else ""
        parts.append("drawtext=%stext='%s':fontcolor=%s:fontsize=%d:x=(w-tw)/2:y=%s%s:enable='between(t,%.3f,%.3f)'"
                     % (ff, txt, color, size, ypx, box, float(c.get("start", 0)), float(c.get("end", 0))))
    return ",".join(parts)


def render(project, out, progress_cb=None, proxy=False):
    """Render the project JSON to `out` (MP4). Returns {ok, output, duration, n_cuts, error?}."""
    canvas = project.get("canvas") or {"w": 1080, "h": 1920, "fps": 30}
    w, h, fps = int(canvas.get("w", 1080)), int(canvas.get("h", 1920)), int(canvas.get("fps", 30))
    srcs = project.get("sources") or {}
    vclips = sorted(_tracks(project, "video"), key=lambda c: float(c.get("start", 0)))
    if not vclips: return {"ok": False, "error": "no video clips"}

    work = tempfile.mkdtemp()
    segs = []
    for i, c in enumerate(vclips):
        sp = srcs.get(c.get("source"), {}).get("path")
        if not sp or not os.path.exists(sp): continue
        dest = os.path.join(work, "s%03d.mp4" % i)
        if _segment(sp, c.get("in", 0), c.get("out", 1), c.get("speed", 1.0), w, h, fps, dest, proxy=proxy) > 0.04:
            segs.append(dest)
        if progress_cb: progress_cb(int(55 * (i + 1) / len(vclips)), "cutting")
    if not segs: return {"ok": False, "error": "no segments built"}

    # concat
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join("file '%s'\n" % s for s in segs))
    body = os.path.join(work, "body.mp4")
    ac._run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", body])
    vlen = ac._dur(body)
    if progress_cb: progress_cb(65, "assembling")

    # text overlays
    tclips = _tracks(project, "text")
    if tclips and not proxy:
        chain = _drawtext_chain(tclips)
        if chain:
            txtd = os.path.join(work, "txt.mp4")
            ac._run([FFMPEG, "-y", "-i", body, "-vf", chain, "-c:v", "libx264", "-preset", "veryfast",
                     "-pix_fmt", "yuv420p", txtd])
            if ac._dur(txtd) > 0.04: body = txtd
    if progress_cb: progress_cb(75, "text")

    # effects lane -> apply_flashes at exact output timestamps (impacts); zoom handled inline by apply_flashes' sibling
    flashes = [{"t": float(e["at"]), "big": bool(e.get("big"))}
               for e in _tracks(project, "effects") if e.get("type", "impact") == "impact"]
    if flashes and not proxy:
        fxd = os.path.join(work, "fx.mp4")
        ac.apply_flashes(body, fxd, flashes)
        if ac._dur(fxd) > 0.04: body = fxd
    if progress_cb: progress_cb(85, "effects")

    # audio: music clip -> trim/delay/mux
    aclip = next((c for c in _tracks(project, "audio") if srcs.get(c.get("source"), {}).get("path")), None)
    if aclip:
        mp = srcs[aclip["source"]]["path"]
        af = ("[1:a]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS,adelay=%d|%d,aresample=48000,"
              "aformat=channel_layouts=stereo,volume=%.2f[a]"
              % (float(aclip.get("in", 0)), float(aclip.get("in", 0)) + vlen,
                 int(float(aclip.get("start", 0)) * 1000), int(float(aclip.get("start", 0)) * 1000),
                 float(aclip.get("volume", 1.0))))
        ac._run([FFMPEG, "-y", "-i", body, "-i", mp, "-filter_complex", af, "-map", "0:v", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-shortest", out])
    else:
        ac._run([FFMPEG, "-y", "-i", body, "-c", "copy", out])
    if progress_cb: progress_cb(100, "done")
    return {"ok": os.path.exists(out) and ac._dur(out) > 0.05, "output": out,
            "duration": round(ac._dur(out), 2), "n_cuts": len(segs)}


if __name__ == "__main__":
    import sys, json
    a = [x for x in sys.argv[1:] if x != "--proxy"]
    proxy = "--proxy" in sys.argv
    if len(a) < 2: print("usage: edl.py <project.json> <out.mp4> [--proxy]"); sys.exit(1)
    print(json.dumps(render(json.load(open(a[0])), a[1], proxy=proxy), indent=2))
