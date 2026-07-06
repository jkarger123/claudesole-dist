#!/usr/bin/env python3
"""MUSIC SOURCE -- resolve the user's chosen song to a local audio file.

Accepts:
  - a local audio/video file path (mp3/m4a/wav/mov/...) -> used as-is
  - a YouTube (or any yt-dlp-supported) URL          -> audio extracted to mp3
  - any direct http(s) audio URL                     -> downloaded

Uses the bundled yt-dlp + ffmpeg (both in ../bin), so it's self-contained. `section` (e.g. "30-55") grabs just
that slice of a long song -- handy so we only pull the chorus/drop we want to cut to."""
import os, re, glob, subprocess, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "bin")
YTDLP = os.path.join(BIN, "yt-dlp")
FFMPEG = os.path.join(BIN, "ffmpeg") if os.path.exists(os.path.join(BIN, "ffmpeg")) else "ffmpeg"


def is_url(s): return bool(re.match(r"https?://", (s or "").strip()))


def _parse_section(section):
    """'3:11-3:25' or '30-55' -> (start_sec, end_sec)."""
    def t(x):
        x = x.strip()
        if ":" in x:
            p = [float(y) for y in x.split(":")]
            return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]
        return float(x)
    a, b = section.split("-", 1)
    return t(a), t(b)


def get_music(source, out_dir=None, section=None):
    source = (source or "").strip()
    if not source: return {"ok": False, "error": "no music source given"}
    if not is_url(source):
        if os.path.exists(source): return {"ok": True, "path": source, "source": "file"}
        return {"ok": False, "error": "file not found: %s" % source}
    if not os.path.exists(YTDLP): return {"ok": False, "error": "yt-dlp not installed (bin/yt-dlp)"}
    out_dir = out_dir or tempfile.mkdtemp()
    tmpl = os.path.join(out_dir, "music.%(ext)s")
    base = [YTDLP, "-x", "--audio-format", "mp3", "--ffmpeg-location", BIN, "--no-playlist", "-o", tmpl, source]

    def _run(cmd): return subprocess.run(cmd, capture_output=True, text=True)
    def _hit():
        h = glob.glob(os.path.join(out_dir, "music.mp3")); return h[0] if h else None

    last = ""
    # 1) FAST path: yt-dlp downloads just the section (ffmpeg range-fetches the signed URL). YouTube 403s these
    #    intermittently -> try twice before falling back.
    if section:
        for _ in range(2):
            r = _run(base + ["--download-sections", "*%s" % section, "--force-keyframes-at-cuts"])
            if _hit(): return {"ok": True, "path": _hit(), "source": "youtube"}
            last = (r.stderr or r.stdout or "")
    # 2) ROBUST fallback: full audio via yt-dlp's own downloader (survives the range-fetch 403), then trim locally.
    for _ in range(2):
        r = _run(base)
        if _hit(): break
        last = (r.stderr or r.stdout or "")
    full = _hit()
    if not full: return {"ok": False, "error": (last or "audio extract failed")[-240:]}
    if section:
        try:
            s, e = _parse_section(section)
            cut = os.path.join(out_dir, "music_cut.mp3")
            _run([FFMPEG, "-y", "-ss", "%.3f" % s, "-i", full, "-t", "%.3f" % max(0.5, e - s), cut])
            if os.path.exists(cut) and os.path.getsize(cut) > 1000:
                return {"ok": True, "path": cut, "source": "youtube"}
        except Exception: pass
    return {"ok": True, "path": full, "source": "youtube"}


if __name__ == "__main__":
    import sys, json
    src = sys.argv[1] if len(sys.argv) > 1 else ""
    sec = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(get_music(src, section=sec), indent=2))
