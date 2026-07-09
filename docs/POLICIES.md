# Per-Action Policy Engine (ALLOW / DENY / ASK)

*ClaudeFather's mechanism for governing what agents may DO — the replacement for prose "HARD RULE" instructions.
Deep-audit 2026-07-09 graft **G1** (adapted from OmniAgent's fail-closed policy engine). Read this before
touching `cc_policy.py`, `policy_hook.py`, the `/api/policy-evaluate` route, or the launch hook-settings.*

## Why this exists
Every ClaudeFather agent session runs `claude --dangerously-skip-permissions`, and the residual safety prompts
are auto-approved. The *only* thing that stopped an agent from force-pushing, running `git add -A` on the dirty
tree, `rm -rf`-ing, or changing an auth token was a **paragraph of prose** in the brief that the model might or
might not obey. This engine turns those rules into a **mechanism**: a real gate on every tool call, fail-closed,
auditable — the platform's #1 architectural gap (per the audit, the one area OmniAgent decisively beat us) closed.

## How it works
```
Claude tool call ──PreToolUse hook──► policy_hook.py ──POST /api/policy-evaluate──► cc_policy.evaluate()
                                          (fail-open)                                   │ ALLOW / DENY / ASK
   permissionDecision ◄───────────────────┴──────────────────────── {permissionDecision} ┘  + audit log
```
- **`cc_policy.py`** — the pure-stdlib engine. A *policy* is `(tool, tool_input, ctx) -> Verdict | None` (`None` =
  abstain). `evaluate()` runs every registered policy and takes the **strictest** result: any **DENY**
  short-circuits, else any **ASK** parks it for a human, else **ALLOW**. **Fail-closed** — an exception inside a
  policy becomes ASK, never a silent ALLOW. Only builtins in `POLICY_REGISTRY` run (an allowlist — a compromised
  extension can't inject a weakening policy). Run `python3 command-center/cc_policy.py --selftest` (17/17).
- **`policy_hook.py`** — a Claude Code **PreToolUse** hook. Thin + **bulletproof fail-open**: any error, timeout,
  or unreachable server → `allow`. A hook bug must never block an agent. It carries a per-session `CC_POLICY_CTX`.
- **`/api/policy-evaluate`** (server) — evaluates, writes the audit log, returns the permission decision.
- **`_policy_audit.log`** (in STATE_DIR) — one JSON line per tool call. View: `GET /api/policy-audit`.

## The 5 builtins
| Policy | Fires on | Verdict |
|---|---|---|
| `blast_radius` | force-push, `git reset --hard`, `git clean -f`, **`git add -A`/`.`**, `rm -rf /~`, fork bomb, `mkfs`/`dd of=/dev/`, `tmux kill-server` | **DENY** |
| `credential_guard` | edits/commands touching `auth_token`/`mesh_token`/vault/`core-sign`/`superadmin` (the PIN rule) | **ASK** |
| `read_only_os` | a `read_only` agent (reviewer/auditor/scout) tries to Write/Edit or run a mutating shell command | **DENY** |
| `ask_on_os_tools` | `sudo`/`launchctl`/`systemctl`/`defaults write`/`pmset`/`killall`/… (unless `trust_os`) | **ASK** |
| `spawn_bounds` | agent fan-out past `spawn_cap`, or one command launching many headless agents | **DENY**/**ASK** |

## OPT-IN, OFF BY DEFAULT
This is a **guardrail an operator turns ON only when they want it** — e.g. handing the console to a non-technical
end-user. A power user or a fleet node gets **UNLIMITED, untouched tool use**: it is not a blanket limiter and it
is not on unless you ask for it.

`cc.config.json` `policy_enforce` (default **`"off"`**):
- **`"off"`** (default) — **the PreToolUse hook is NOT wired into ANY session at all.** Zero calls, zero overhead,
  zero interference. Every tool call runs exactly as if this feature didn't exist.
- **`"log"`** — evaluate + record the would-be verdict, but ALWAYS allow. Nothing is ever blocked; you watch the
  log to see what *would* be denied. The safe way to trial it before enforcing.
- **`"on"`** — actually enforce (DENY blocks the tool, ASK prompts). The 5 rules target only genuinely dangerous
  actions (`rm -rf`, force-push, credential edits, unbounded spawns) — never normal reads/edits/commands.

**To turn it on** (only if you want guardrails): set `policy_enforce: "log"` in `cc.config.json` and restart; watch
`GET /api/policy-audit` (or `_policy_audit.log`); if there are no false-DENYs on legitimate work, set it to `"on"`.
Roll back instantly to `"log"` or `"off"`. (Staged-rollout pattern, like `MESH_ENFORCE`.) When `off`, none of the
launch paths (chief / scoped agents / Ralph) even reference the hook.

## Per-session context (`CC_POLICY_CTX`)
A launch can hand the hook a JSON profile via the `CC_POLICY_CTX` env var; the hook forwards it and the engine
merges it into `ctx`. Recognised keys: `read_only` (bool — reviewers/auditors), `trust_os` (bool — allow OS
tools without ASK), `spawn_count`/`spawn_cap` (ints). Example: launch a code-reviewer with
`CC_POLICY_CTX='{"read_only":true}'` and its Writes/mutations are denied while its reads pass.

## Launch coverage
The PreToolUse hook is wired via the Claude Code `--settings` file:
- **Chief of Staff** — `chief_open()` writes `_mesh_hook_settings.json` (PreToolUse **+** the mesh Stop hook).
- **Scoped agents** — `agent_open()` splices `--settings _policy_hook_settings.json` (`_ensure_policy_settings()`).
- **Ralph loops** — `ralph_launch` passes `CC_POLICY_SETTINGS` to `ralph_runner.py`, which adds `--settings` to
  each iteration's headless `claude` call.
- **Remaining (tracked follow-ups):** `launch()` (studio-target branch only — `--settings` to a local path breaks
  over `ssh` for windows targets), Teams, and resume/fork.

## Add a policy
1. Write `def my_policy(tool, tool_input, ctx) -> Verdict | None` in `cc_policy.py` (narrow + evidence-based;
   false DENYs erode trust).
2. Register it in `POLICY_REGISTRY`.
3. Add a self-test case in `__main__` and run `--selftest`.
Official-signed extension modules may later export their own `POLICY_REGISTRY` (allowlist-gated) — not yet wired.

## Files
- `command-center/cc_policy.py` — the engine (+ `--selftest`).
- `command-center/policy_hook.py` — the fail-open PreToolUse hook.
- `command-center/server.py` — `policy_evaluate()`, `_ensure_policy_settings()`, `/api/policy-evaluate`,
  `/api/policy-audit`, `POLICY_ENFORCE`, the chief/agent hook-settings.
- STATE_DIR/`_policy_audit.log` — the trace.

## Not yet built (roadmap)
Full launch coverage (above); an **ASK-parking UI** (a human approves/denies a parked ASK from the dashboard,
day-long window) so ASK works for headless agents; making `_autoapprove_scan` policy-consulting; cost policies
(graft G2) as `cc_policy` rules over `usage_payload()`; plain-English/LLM policies (graft G9).
