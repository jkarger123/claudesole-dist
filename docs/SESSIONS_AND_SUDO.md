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
(e.g. `admin-carsearch`, `admin-hptuners`), cwd = the project root. Because it lives in the project dir,
it shows up in THIS console's Sessions tab. It is a normal interactive terminal -- sudo password entry,
prompts, `gcloud auth login`, etc. all work here.

## The protocol (agent + operator)
**Agent side** -- never run sudo/interactive directly. Stage it for the operator:
```
# ensure the per-project admin shell exists (cwd = the project root):
tmux new-session -d -s admin-<project> -c /path/to/project   # no-op if it already exists
# PRE-TYPE the command WITHOUT pressing Enter, so the operator can review it first:
tmux send-keys -t admin-<project> 'sudo launchctl kickstart -k system/com.example.thing'
# (do NOT append Enter / C-m)
```
Then tell the operator: *"I staged `<command>` in the Admin shell -- open it in the Sessions tab, review,
press Enter, and enter your password."*

**Operator side** -- click **🔑 Admin shell** (or the `admin-<project>` session) in the Sessions tab. The
staged command is sitting at the prompt. Read it, press **Enter**, type your password if asked. Output is
right there; the agent can read it back with `tmux capture-pane -t admin-<project> -p`.

## Rules
- The agent NEVER appends Enter to a sudo/destructive staged command -- the operator presses Enter. This is
  the human-in-the-loop checkpoint for privileged actions.
- One admin shell per project (named `admin-<project>`) so names don't collide on the shared tmux server
  and each shows only in its own console.
- Don't stage secrets in plaintext that get logged; for credentials, let the interactive prompt collect them.
- For a command the operator should run in THEIR own login (e.g. an interactive cloud auth), the operator can
  also just type `! <command>` into the Claude prompt, which runs it in their session.

## TL;DR
Agent: `tmux send-keys -t admin-<project> '<cmd>'` (no Enter) -> tell the operator.
Operator: Sessions tab -> 🔑 Admin shell -> review -> Enter -> password.
