#!/usr/bin/env python3
"""TIMECODE PREVIEW -- burn a big running timestamp onto a clip so the user can scrub to the EXACT frame of an
impact and read the millisecond. They tell us "the land is at 2.13s", we feed that time in verbatim (exact=True)
and the flash fires dead-on -- no motion-guessing. This is the "let me see high-res times" tool.

    timecode.py <clip> <out.mp4>
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "bin")
FFMPEG = os.path.join(BIN, "ffmpeg") if os.path.exists(os.path.join(BIN, "ffmpeg")) else "ffmpeg"
FONT = next((f for f in ["/System/Library/Fonts/Supplemental/Impact.ttf",
                         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if os.path.exists(f)), None)


def stamp(clip, out):
    ff = ("fontfile='%s':" % FONT) if FONT else ""
    # big seconds.milliseconds top-center + a per-frame number, high-contrast, updates every frame
    vf = ("drawtext=%stext='%%{pts\\:hms}':fontcolor=yellow:fontsize=76:x=(w-tw)/2:y=40:"
          "box=1:boxcolor=black@0.75:boxborderw=16," % ff +
          "drawtext=%stext='%%{eif\\:t\\:d}.%%{eif\\:mod(trunc(t*100),100)\\:d\\:2} s':fontcolor=white:fontsize=52:"
          "x=(w-tw)/2:y=140:box=1:boxcolor=black@0.6:boxborderw=10" % ff)
    r = subprocess.run([FFMPEG, "-y", "-i", clip, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", out], capture_output=True, text=True)
    return {"ok": os.path.exists(out), "out": out, "error": (r.stderr or "")[-200:] if not os.path.exists(out) else None}


if __name__ == "__main__":
    import json
    if len(sys.argv) < 3: print("usage: timecode.py <clip> <out.mp4>"); sys.exit(1)
    print(json.dumps(stamp(sys.argv[1], sys.argv[2]), indent=2))
