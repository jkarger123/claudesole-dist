# Video Studio — how an agent builds a video for a user

You can produce a FINISHED video for a user with this tool. It is an **analytical** editor (no generative model):
it runs on the node's bundled `bin/ffmpeg` + `bin/yt-dlp`, needs **no API key**, and works on **real footage,
photos, and music** (including real people/kids — nothing is regenerated).

## Fastest path — one command makes a beat-synced video
Engine lives in `extensions/ai-video-studio/engine/`:

    cd extensions/ai-video-studio/engine
    python3 studio.py --music "<song file OR YouTube/track URL>" [--section 3:11-3:25] --pace punchy \
        --out /abs/path/out.mp4  clip1.mov clip2.mov photo.jpg ...

- `--music`: a local audio file OR a YouTube/http URL (audio auto-extracted; `--section mm:ss-mm:ss` = just that slice).
- `--pace`: `frantic` | `punchy` | `cinematic` (how many beats per cut).
- positional args: absolute paths to the user's clips (**images work too** — held ~5s each).
- It beat-detects the song, motion-detects the clips, cuts every cut onto a beat, slow-mos the finisher, and prints
  JSON `{ok, output, duration}`. The MP4 at `--out` is the deliverable — write it into a module `deliverables/`
  dir (SSD) so it shows in the operator's Files lens.
- Extras: `--clips-only` (export cut segments for a CapCut template), `--timecode` (burn a running timer for
  calibration), `--flash-at "2.5,8.9" --big-flash-at "4.0"` (white-flash impacts at exact OUTPUT seconds).

## Full control — the project/EDL model
Everything is ONE project JSON (all times = seconds on the OUTPUT timeline) that `engine/edl.py`
`render(project, out)` compiles to an MP4. Build/modify the dict for arbitrary edits:

    {canvas:{w,h,fps}, duration, sources:{id:{kind:"video|image|audio", path}},
     tracks:[ {kind:"video",   clips:[{source,in,out,start,speed,color:{b,c,s},fit:"cover|contain"}]},
              {kind:"overlay", clips:[{source,in,out,start,transform:{scale,x,y}}]},   // picture-in-picture
              {kind:"effects", clips:[{at,type:"impact|zoom",big,amount,dur}]},
              {kind:"text",    clips:[{start,end,text,style:{size,y,box}}]},
              {kind:"audio",   clips:[{source,in,out,start,volume}]} ]}

- `speed` is a factor: `<1` = slow-mo (output longer). `in/out` trim the source; `start` = position on output.
- Manual (no beat-cut) project: `python3 project.py manual out.json <cache_dir> [--music M] clip1 clip2 …`
  (each clip full length; images default to 5s). Then edit the JSON and `python3 edl.py out.json final.mp4`.
- CapCut bundle (cut clips + edit-plan + draft): `python3 capcut.py project.json out.zip`.

## The human UI
Operators get a `/studio` lens — an in-dashboard timeline editor (trim, split, crop, color, audio, titles, PiP,
beat auto-cut, export). As an agent you normally drive the CLI/engine directly and deliver the finished MP4.

## Rules
- ANALYTICAL only. Do not route real people (esp. children) through a generative video/image model — they get
  policy-blocked and it's a line we don't cross. This tool never regenerates anyone.
- Needs the node's `bin/` ffmpeg + ffprobe + yt-dlp (the server auto-installs them on first render; for direct CLI
  use, confirm `bin/` exists — see the studio extension). Default big outputs to the SSD. Never echo secrets.
