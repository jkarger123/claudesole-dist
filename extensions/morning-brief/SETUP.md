# Morning Brief — setup

## What
A scheduled, voice-read brief of the operator's day + what's coming over the next week or two, synthesized
from their own data (calendar, inbox, tasks, calls, Slack) by Claude on the subscription, ready ~an hour
before they start and playable in their browser.

## Why
Start the day already oriented: the 2-3 things that matter, what's coming, and any prep — in the operator's
own writing voice, read aloud in a natural voice, without them lifting a finger.

## How
A scheduled routine (auto-created from the Brief lens config) runs `cc-brief`, which calls
`/api/brief-generate`. The engine (`command-center/morning_brief.py`) gathers a CITED slice from the selected
sources, has a headless `claude -p` (subscription, no metered key) write 2-3 spoken paragraphs in the
operator's VoiceMatch style, renders it to natural speech (OpenAI `tts-1-hd` or ElevenLabs), and stores it.
The Brief lens plays the audio in the operator's BROWSER (never the server's speakers).

## Prerequisites
- For data: whichever sources you want — Google (calendar/gmail) via the google-workspace extension, Granola,
  Slack, and/or the built-in Tasks. The brief degrades gracefully: it uses whatever is available.
- For voice (optional): an `OPENAI_API_KEY` in the vault (natural `tts-1-hd` voices), OR an
  `ELEVENLABS_API_KEY` for the most natural voice. With neither, it falls back to the OS voice; voice can also
  be turned off.

## Setup steps
1. Install this extension (Marketplace → Morning Brief → Install). The Brief lens appears.
2. Open the **Brief** lens → Settings:
   - **Start time** + **lead** (e.g. 9:00am, 60 → runs at 8:00). This sets the run schedule.
   - **Horizon** (how many days "coming up" looks ahead).
   - **Sources** — tick the ones to feed it (calendar / gmail / tasks / granola / slack).
   - **Voice** — on/off, provider (elevenlabs / openai / say), and autoplay. Use a female voice id like
     `nova` (OpenAI) if desired.
3. (Optional, best voice) add an `ELEVENLABS_API_KEY` via the Vault lens / secure field.
4. (Optional, best writing match) make sure the operator's VoiceMatch profile is built (it's used so the brief
   sounds like them).

## Verify
- In the Brief lens, click **⟳ Generate now**. After ~30-60s a brief appears with an audio player.
- Confirm the schedule line reads the expected run time (e.g. "runs 08:00 on weekdays").

## Usage
Each morning the brief is generated automatically before start time and waits in the Brief lens; open the
console and press play (browsers require one click before audio). Past briefs are kept in the lens history.

## Best practices
- Keep the source list tight at first (calendar + gmail + tasks + granola) and add more once it feels right.
- Voice plays in the viewer's browser on their device — generation never makes sound on the server.
- The brief is read-only: it never sends mail, changes a calendar, or completes a task; it only summarizes.
