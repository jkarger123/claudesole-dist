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


def _segment(src_path, in_t, out_t, speed, w, h, fps, dest, proxy=False, color=None, fit="cover", is_image=False):
    """Cut [in..out] of a source, apply speed (speed<1 => slow-mo), CROP/FIT to the canvas, and optional COLOR
    correction. Output length = (out-in)/speed. `fit`: cover (fill+crop) | contain (fit+letterbox). is_image: hold
    the still for the duration (a photo on the timeline)."""
    sp = float(speed) if speed else 1.0                    # speed FACTOR: <1 = slow-mo (output longer)
    out_dur = max(0.05, (float(out_t) - float(in_t)) / (sp if not is_image else 1.0))
    ow = 480 if proxy else w
    oh = int(ow * h / w)
    if fit == "contain":
        nf = ("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,"
              "setsar=1,fps=%d" % (ow, oh, ow, oh, fps))
    else:                                                  # cover: fill the frame, crop the overflow (= crop-to-9:16)
        nf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (ow, oh, ow, oh, fps)
    chain = ([] if is_image else [("setpts=%.4f*PTS" % (1.0 / sp)) if sp != 1.0 else "setpts=PTS"]) + [nf]
    if color:                                              # color correction: brightness / contrast / saturation
        b = float(color.get("b", 0)); c = float(color.get("c", 1)); s = float(color.get("s", 1))
        if abs(b) > 0.001 or abs(c - 1) > 0.001 or abs(s - 1) > 0.001:
            chain.append("eq=brightness=%.3f:contrast=%.3f:saturation=%.3f" % (b, c, s))
    vf = ",".join(chain)
    preset = "ultrafast" if proxy else "veryfast"
    if is_image:                                           # hold a still for out_dur (loop the single frame)
        ac._run([FFMPEG, "-y", "-loop", "1", "-t", "%.3f" % out_dur, "-i", src_path, "-an", "-vf", vf,
                 "-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(fps), dest])
    else:
        ac._run([FFMPEG, "-y", "-ss", "%.3f" % max(0, float(in_t)), "-i", src_path, "-t", "%.3f" % (out_dur * sp),
                 "-an", "-vf", vf, "-c:v", "libx264", "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(fps), dest])
    return ac._dur(dest)


def _pip_segment(src_path, in_t, out_t, speed, tw, fps, dest):
    """A picture-in-picture segment: trim + speed, scaled to `tw` wide (aspect kept) -- to overlay on the base."""
    src_len = max(0.05, float(out_t) - float(in_t)); sp = float(speed) if speed else 1.0
    vf = ("setpts=%.4f*PTS," % (1.0 / sp) if sp != 1.0 else "setpts=PTS,") + \
         "scale=%d:-2:force_original_aspect_ratio=decrease,fps=%d" % (tw, fps)
    ac._run([FFMPEG, "-y", "-ss", "%.3f" % max(0, float(in_t)), "-i", src_path, "-t", "%.3f" % src_len, "-an",
             "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(fps), dest])
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


def apply_zooms(video, out, zooms, w, h):
    """Zoom-PUNCH at exact output timestamps: scale up (eval=frame -> time-varying) then fixed crop back to canvas.
    One pass -- Z is the sum of every zoom window (triangular bump around each `at`). Never read+write same file."""
    dst = out if out != video else out + ".zm.mp4"
    Z = "1"
    for z in zooms:
        amt = float(z.get("amount", 1.35)); at = float(z.get("at", 0)); half = max(0.12, float(z.get("dur", 0.5)) / 2)
        Z += "+%.3f*max(0,1-abs(t-%.3f)/%.3f)" % (amt - 1.0, at, half)   # quotes below protect the commas
    vf = "scale=w='%d*(%s)':h='%d*(%s)':eval=frame,crop=%d:%d,setsar=1" % (w, Z, h, Z, w, h)
    ac._run([FFMPEG, "-y", "-i", video, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", dst])
    if ac._dur(dst) > 0.04:
        if dst != out: os.replace(dst, out)
        return True
    return False


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
        if _segment(sp, c.get("in", 0), c.get("out", 1), c.get("speed", 1.0), w, h, fps, dest, proxy=proxy,
                    color=c.get("color"), fit=c.get("fit", "cover"),
                    is_image=(srcs.get(c.get("source"), {}).get("kind") == "image")) > 0.04:
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

    # PiP / overlay tracks -> composite onto the base with filter_complex overlay (each at its start, scaled+placed)
    ovs = [o for o in _tracks(project, "overlay") if srcs.get(o.get("source"), {}).get("path")]
    if ovs and not proxy:
        inputs = ["-i", body]; fc = []; last = "0:v"; n = 0
        for oc in ovs:
            tr = oc.get("transform") or {}; scale = float(tr.get("scale", 0.4))
            seg = os.path.join(work, "ov%03d.mp4" % n)
            if _pip_segment(srcs[oc["source"]]["path"], oc.get("in", 0), oc.get("out", 1), oc.get("speed", 1),
                            max(80, int(w * scale)), fps, seg) <= 0.04: continue
            n += 1; inputs += ["-i", seg]
            x = int(float(tr.get("x", 0.05)) * w); y = int(float(tr.get("y", 0.05)) * h)
            st = float(oc.get("start", 0)); en = st + (oc.get("out", 1) - oc.get("in", 0)) / (oc.get("speed", 1) or 1)
            fc.append("[%s][%d:v]overlay=%d:%d:enable='between(t,%.3f,%.3f)'[v%d]" % (last, n, x, y, st, en, n))
            last = "v%d" % n
        if n:
            ovd = os.path.join(work, "ov.mp4")
            ac._run([FFMPEG, "-y"] + inputs + ["-filter_complex", ",".join(fc), "-map", "[%s]" % last,
                     "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", ovd])
            if ac._dur(ovd) > 0.04: body = ovd
    if progress_cb: progress_cb(72, "overlays")

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
    zooms = [e for e in _tracks(project, "effects") if e.get("type") == "zoom"]
    if zooms and not proxy:
        zd = os.path.join(work, "zoom.mp4")
        if apply_zooms(body, zd, zooms, w, h): body = zd
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
