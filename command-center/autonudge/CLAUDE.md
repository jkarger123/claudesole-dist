# Auto-nudge — keep an agent going without babysitting it

**My job:** when a Claude session keeps stopping to ask "want me to keep going?", auto-send a canned push (e.g.
"complete solution, no shortcuts, get it right before we move on") into the session **every time it stops**, so it
keeps working. Opt-in, per-session, runs until you turn it off — **you are the only brake** (owner's choice:
fire every turn-end, always nudge, never wait).

## How it works
Same mechanism as the API-error watchdog (`../cc-session-watchdog.py`): a loop watches OPTED-IN tmux sessions and,
when one is IDLE at a turn-end (no `esc to interrupt` / spinner), it `tmux send-keys` your message into the input box
and presses Enter. It fires **once per distinct turn-end** (a pane-content signature) with a ~10s anti-double-fire
cooldown. Nothing else in the platform is touched — pure terminal injection.

## Two ways to arm a session (they share one store: `~/.cc-autonudge.json`)
1. **Dashboard toggle** — open a session's terminal in the **Sessions** lens → the **Auto-nudge** button in the
   ⋯ (more) menu. Click it: a plain **on/off toggle** that arms the session with the DEFAULT message (your own "no
   shortcuts" wording); the button shows `Auto-nudge: ON (n)` and the status line confirms. Click again to turn off.
   To set a CUSTOM per-session message, use the CLI `cc-autonudge msg <session> "..."` (the terminal page has no
   styled-dialog `promptM`, so the toggle stays dialog-free). Backend: `autonudge_session()` + `/api/autonudge-session`;
   frontend `anbtn` + `anPaint/anState/toggleAn` on `TERM_PAGE`, mirroring the Telegram/Slack toggles. GOTCHA: the
   toolbar strips protected-session buttons by their onclick (gracefulEnd/killSess), NOT by title substring -- an
   earlier title-"end" match had eaten this button on chief/ralph sessions.
2. **CLI** — `cc-autonudge` (symlinked onto PATH):
   - `cc-autonudge arm <session> [message]` — arm (omit message → the default "no shortcuts" push)
   - `cc-autonudge off <session>` · `cc-autonudge msg <session> "..."` · `cc-autonudge list`
   - `cc-autonudge run [--dry]` (one pass) · `cc-autonudge loop [--dry]` (continuous ~8s)

Either way it writes `~/.cc-autonudge.json`; the loop reads it each pass, so a dashboard toggle and the CLI stay in
sync and the loop picks up changes live.

## Files
- `cc-autonudge.py` — the tool (arm/off/msg/list/run/loop + the idle-detect + send-keys logic). Symlinked to
  `/opt/homebrew/bin/cc-autonudge`.
- `com.claudefather.autonudge.plist` — launchd job running `cc-autonudge loop` (durability). Bootstrap it like the
  lifeline: `cp com.claudefather.autonudge.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u)
  ~/Library/LaunchAgents/com.claudefather.autonudge.plist`. Until then the loop runs in the tmux session `autonudge`.
- The default message (owner's own wording) is `DEFAULT_MSG` in the script AND `_AUTONUDGE_DEFAULT` in `server.py` —
  keep them in sync.

## Safety
- **Opt-in only** — nudges ONLY sessions you explicitly arm.
- **Idle-only** — never types while the agent is working (`esc to interrupt` / an active spinner = skip).
- **Once per turn-end** + cooldown — can't spam or double-fire.
- **You are the brake** — no auto-stop; `cc-autonudge list` shows what's armed, `off` / the toggle stops it.
- It runs the agent with whatever permissions that session already has — arming a `--dangerously-skip-permissions`
  session means it acts unsupervised, so the message itself should tell it to self-check and stop when truly done.

## Gotchas
- The dashboard button lives in **`TERM_PAGE`** (the terminal page), not the main `PAGE`. The preship PAGE-JS gate
  was widened (2026-07-04) to node-check EVERY HTML string constant, so a JS break in the terminal page is caught too.
- Scripts `unset TMUX` / use the TMUX binary path directly (a var named `TMUX` collides with tmux's socket env var).
- Local to this Mac; ships to the fleet when the freeze lifts (add `cc-autonudge.py` to `framework_paths`, template
  the plist, and the `server.py` toggle already travels with the engine).
