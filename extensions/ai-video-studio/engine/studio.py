#!/usr/bin/env python3
"""AI VIDEO STUDIO -- top-level orchestrator (the tool's one entry point).

    studio.py --music <song-file-OR-youtube-url> [--section 30-55] --out out.mp4 [--pace punchy] clip1 clip2 ...

Pipeline: resolve the music (file or YouTube -> local audio) -> autocut (beat-detect the song + motion-detect the
clips + cut every cut onto a beat + slow-mo the finisher) -> final MP4. The user only supplies clips + a song."""
import os, sys, json, argparse

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import music as musicmod
import autocut as autocutmod
import timecode as timecodemod

# pace = how many beats per cut (1 = frantic, 2 = punchy, 4 = cinematic)
PACE = {"frantic": 1, "punchy": 2, "cinematic": 4}


def make(clips, music_source, out, section=None, pace="punchy", clips_only=False, max_secs=None,
         mode="deterministic", plan_file=None, effects=True, timecode=False, flash_at=None, big_flash_at=None,
         aspect=None):
    """mode='deterministic' -> the engine's motion-energy auto-select (fast, free, no AI usage).
       mode='ai'            -> use a vision-model/Claude-authored shot plan (moments chosen by MEANING). Pass the
                               plan as a JSON list of {clip, t, hero?, slow?} via plan_file (or shot_plan= in code)."""
    m = musicmod.get_music(music_source, section=section)
    if not m.get("ok"): return {"ok": False, "stage": "music", "error": m.get("error")}
    shot_plan = None
    if mode == "ai":
        if not plan_file or not os.path.exists(plan_file):
            return {"ok": False, "stage": "plan", "error": "ai mode needs a shot plan JSON (--plan). "
                    "The AI/vision layer authors it by watching the clips and choosing moments by meaning."}
        shot_plan = json.load(open(plan_file))
    # if the user is giving exact OUTPUT flash times, turn OFF the auto per-segment flash and apply theirs instead
    operator_flash = bool(flash_at or big_flash_at)
    cw, ch = autocutmod.canvas_for(aspect, clips)          # '16:9'|'9:16'|auto (auto = vote by the clips)
    res = autocutmod.build(clips, m["path"], out, clips_only=clips_only, max_secs=max_secs,
                           beats_per_cut=PACE.get(pace, 2), shot_plan=shot_plan,
                           effects=(effects and not operator_flash), w=cw, h=ch)
    if not res.get("ok"): return res
    res["canvas"] = {"w": cw, "h": ch}
    if operator_flash:
        flashes = [{"t": t, "big": False} for t in (flash_at or [])] + [{"t": t, "big": True} for t in (big_flash_at or [])]
        res["flashes"] = autocutmod.apply_flashes(out, out, flashes, cw, ch)
    if timecode:                                            # burn a running timer onto the FINAL cut for calibration
        tc = out.replace(".mp4", "_TC.mp4"); timecodemod.stamp(out, tc); res["timecoded"] = tc
    res["music_source"] = m.get("source")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", required=True, help="song file path OR a YouTube/http URL")
    ap.add_argument("--section", default=None, help="slice of a long song, e.g. 30-55")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace", default="punchy", choices=list(PACE))
    ap.add_argument("--aspect", default="auto", help="16:9 (landscape) | 9:16 (portrait) | auto (pick from the clips)")
    ap.add_argument("--mode", default="deterministic", choices=["deterministic", "ai"],
                    help="deterministic = motion-energy (free); ai = a vision-model/Claude shot plan (--plan)")
    ap.add_argument("--plan", default=None, help="AI shot plan JSON: [{clip,t,hero?,slow?}, ...]")
    ap.add_argument("--clips-only", action="store_true", help="export cut segments for a CapCut template")
    ap.add_argument("--no-fx", action="store_true", help="disable the auto impact flash/shake")
    ap.add_argument("--timecode", action="store_true", help="also output a copy with a running timer burned in (calibration)")
    ap.add_argument("--flash-at", default="", help="apply flashes at these OUTPUT times (comma sep secs), e.g. 3.1,7.4")
    ap.add_argument("--big-flash-at", default="", help="big flashes at these OUTPUT times (the finisher)")
    ap.add_argument("--max-secs", type=float, default=None)
    ap.add_argument("clips", nargs="+")
    a = ap.parse_args()
    fa = [float(x) for x in a.flash_at.split(",") if x.strip()]
    bfa = [float(x) for x in a.big_flash_at.split(",") if x.strip()]
    print(json.dumps(make(a.clips, a.music, a.out, section=a.section, pace=a.pace, mode=a.mode,
                          plan_file=a.plan, clips_only=a.clips_only, max_secs=a.max_secs,
                          effects=not a.no_fx, timecode=a.timecode, flash_at=fa, big_flash_at=bfa,
                          aspect=a.aspect), indent=2))
