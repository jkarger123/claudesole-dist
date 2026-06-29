# Morning Brief — setup agent brief

You are setting up the **Morning Brief** extension for this operator. Goal: a daily, voice-read brief of
their day ready ~an hour before they start.

Do this:
1. Confirm the data sources available on this node (Google calendar/gmail via google-workspace, Granola,
   Slack, Tasks). The brief works with whatever is present — don't block on a missing one.
2. Ask the operator their usual **start time** and how much **lead** they want (default 60 min). Set it in the
   Brief lens config (`POST /api/brief-config {open_time, lead_minutes}`) — this also creates/reschedules the
   run routine automatically.
3. Confirm which **sources** to include and the **voice** choice (provider + a female voice id like `nova`
   for OpenAI). If they want the most natural voice, have them add `ELEVENLABS_API_KEY` via the secure field
   (never paste a key into chat).
4. If their VoiceMatch writing profile isn't built yet, suggest building it (the brief is written in their
   voice when it exists).
5. Generate a test brief (`POST /api/brief-generate`) and confirm a brief + audio appears in the Brief lens.

Hard rules: the brief is READ-ONLY (summarize only — never send mail / edit calendar / complete tasks).
Voice always plays in the operator's BROWSER, never the server's speakers. Keys live in the vault only —
never echo them.
