# Video Studio — Setup

## What
A built-in video editor for ClaudeFather. It turns raw clips + a song into a beat-synced hype cut and renders an MP4 you can download or drop into a session. It opens as a dedicated **Studio** page (`/studio`), tuned for both phone and desktop.

## Why
Pro-looking montages (a kid's highlight reel, a product teaser, an event recap) normally mean CapCut and a lot of manual trimming. Studio does the tedious part — beat-syncing cuts to the music and finding the money moments — in one tap, on your own footage, without uploading anyone's face to a generative AI.

## How
It runs on a bundled static **ffmpeg** (no system install, no API key). It decodes the song, detects the beat grid, scores each clip for motion (the "money moments"), lays the moments onto the beat so every cut lands on a beat, slow-mos the finisher, and fires impact flashes on the big hits. Rendering happens in a background job so the page stays responsive; the finished MP4 lands in the **Files** lens.

## Prerequisites
- None required. The static `ffmpeg`/`ffprobe`/`yt-dlp` binaries ship in the node's `bin/` (node-local).
- Optional: a YouTube-reachable network if you want to pull music from a link (otherwise upload an audio file).
- Optional (future): generative/voiceover providers unlock if their keys are in the vault — the core auto-build never needs one.

## Setup steps
1. Install the extension from the Marketplace. Nothing to configure — it's keyless.
2. A **Studio** tab appears in your nav (under Team). It opens the `/studio` page.

## Verify
1. Open **Studio** (or go to `/studio`).
2. Add one or more video clips, paste a YouTube link (or upload a track), pick a pace, and press **Auto-build**.
3. Watch the progress bar; when it finishes, the MP4 plays in the page and appears in **Files**.

## Usage
- **Clips:** tap to add (or drag in) phone videos. Put the best action anywhere — it finds it.
- **Music:** paste a YouTube link and optionally a section (e.g. `3:11-3:25`) to grab just the drop, or upload an audio file.
- **Pace:** Frantic (a cut every beat), Punchy (every 2nd), Cinematic (every 4th).
- The render lands in **Files** — download it or drag it into a session.

## Best practices
- Shoot/keep clips a few seconds longer than you need; Studio trims to the beat.
- For a clean beat lock, pick a song with an obvious pulse and use a `section` at the drop.
- **Shape (landscape or portrait):** Studio auto-detects the orientation from the clips you add (landscape 16:9 vs portrait 9:16) and sets the **Shape** toggle for you — tap it to override. Portrait is great for Reels/TikTok/Shorts; landscape for YouTube/TV.
