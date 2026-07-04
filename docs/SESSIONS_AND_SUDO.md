# Sessions tab + running sudo / interactive commands

How agents and the operator share terminals in a ClaudeFather, and how to run commands an agent CANNOT
run itself (sudo, password prompts, anything interactive).

## The Sessions tab
Every ClaudeFather console has a **Sessions** lens. It lists the live terminal sessions **scoped to this
project** (sessions whose working dir is under this project's root; the org/overseer shows all). Each
session is a real tmux session rendered as a live, usable terminal **inline** (the focused "big" one).

- **Open a session inline** (default): click it / "▶ open" / "Talk to ...". It opens in the Sessions tab.
- **Open in a new browser tab**: only the **↗ arrow** on a session does that. Nothing else opens new tabs.
- **＋ New**: launch a new Claude session in this project.
- **🔑 Admin shell**: open this project's plain interactive shell (see below).
- End/handoff (⏏) or force-kill (✕) per session.

## Why an agent can't run sudo
Agents run through a tool with **no TTY**. They cannot type a sudo password or answer an interactive
prompt (`[y/N]`, a password field, an `ssh` host-key prompt, etc.). So the agent must hand the command
to a **real terminal the operator drives** -- that's the Admin shell.

## The Admin shell (per project)
"🔑 Admin shell" in the Sessions tab opens (or resumes) a **plain login shell** named `admin-<project>`
(e.g. `admin-acme`, `admin-widgets`), cwd = the project root. Because it lives in the project dir,
it shows up in THIS console's Sessions tab. It is a normal interactive terminal -- sudo password entry,
prompts, `gcloud auth login`, etc. all work here.

## The protocol (agent + operator)
**Agent side -- use the robust primitive, do NOT hand-roll `tmux send-keys`.** Stage the command with one
API call:
```
POST /api/admin-stage  {"text": "sudo launchctl kickstart -k system/com.example.thing"}
# e.g. curl -s -X POST -H "Cookie: cc_auth=<PIN>" -H "Content-Type: application/json" \
#        -d '{"text":"<cmd>"}' http://localhost:<port>/api/admin-stage
```
This is reliable where raw `send-keys` is not -- it (1) resolves the **canonical** admin session for this
project (so you never guess `admin-home-assistant` vs `admin-homeassistant`), creating it if needed; (2)
drops tmux **copy-mode** first, so a scrolled/selected pane doesn't silently swallow the keys; (3) sends the
**literal** text with NO Enter; (4) reads the pane back and returns `{"staged": true}` only when the line is
**confirmed** present. If `staged` is false, the pane was busy -- check the Sessions tab and retry; don't
assume it landed. To actually RUN it for the operator (rare -- normally THEY press Enter), pass `"run": true`.

Then tell the operator: *"I staged `<command>` in the Admin shell -- open it in the Sessions tab, review,
press Enter, and enter your password."*

> **Why not raw `tmux send-keys`?** Two failure modes bit us (2026-06-29): the admin session slug isn't the
> same as the `cc-<node>` server slug, so a hand-derived name targets a session the operator isn't viewing;
> and a pane in copy-mode returns "not in a mode" and eats the keystrokes with no error. `/api/admin-stage`
> handles both. (Discoverability fallback: `/api/sessions` flags the admin session with `is_admin:true`, and
> `/api/admin-shell` returns its canonical name. cc.config `admin_session` can pin a custom name.)

**Operator side** -- click **🔑 Admin shell** (or the flagged `admin-...` session) in the Sessions tab. The
staged command is at the prompt. Read it, press **Enter**, type your password if asked. Output is right
there; the agent reads it back from the `admin-stage` response (`pane_tail`) or `capture-pane`.

## Rules
- The agent NEVER appends Enter to a sudo/destructive staged command (don't pass `run:true`) -- the operator
  presses Enter. This is the human-in-the-loop checkpoint for privileged actions.
- One admin shell per project (canonical `admin-<slug>`); resolve it via the API, never by guessing.
- Don't stage secrets in plaintext that get logged; for credentials, let the interactive prompt collect them.
- For a command the operator should run in THEIR own login (e.g. an interactive cloud auth), the operator can
  also just type `! <command>` into the Claude prompt, which runs it in their session.

## TL;DR
Agent: `POST /api/admin-stage {"text":"<cmd>"}` -> check `staged:true` -> tell the operator.
Operator: Sessions tab -> 🔑 Admin shell -> review -> Enter -> password.
