# The Skill Authoring Platform

The fleet's system for **building, scoping, discovering, and distributing Claude Code Skills** — built on the
*real* Claude Code skill mechanism, not a parallel one. This is the reference; the module home + agent charter
live in `skill-authoring/` (`CLAUDE.md` + `AGENT.md`).

> **The core idea.** A skill is a `SKILL.md` folder. The folder name is the `/command`. The `description` is
> the *only* thing the model sees until the skill is invoked (progressive disclosure). So a skill's whole
> discoverability rides on one line, and the platform's job is to make skills **easy to build, impossible to
> forget, and never in your way when they're irrelevant.**

---

## 1. What a skill actually is

A folder `<skills-dir>/<name>/SKILL.md` — YAML frontmatter + a markdown body.

```markdown
---
name: deploy-staging                 # optional; defaults to the folder name
description: >                        # THE TRIGGER — what it does + when to use it, with real keywords
  Deploy the app to staging and smoke-test it. Use when asked to push to staging or verify a staging build.
when_to_use: "after a PR merges to main"   # appended to the description
allowed-tools: Bash(git*), Bash(*deploy*)  # pre-approve exactly what the steps need
disable-model-invocation: true       # side-effect skills → human-only /cmd (model can't auto-fire it)
argument-hint: "[environment]"
paths: "deploy/**,infra/**"           # only activate when working in matching files (directory scoping)
---

## Steps
1. ...
```

- **Folder name → `/command`** (`deploy-staging/` → `/deploy-staging`).
- **Body loads only on invoke**, then persists for the session — keep it lean (< ~500 lines); link heavy
  reference to sibling files (`See [reference.md](reference.md)`), which load on demand.
- **Optional scripts** live next to `SKILL.md` and are called from the body (don't inline a large script).
- Full frontmatter field list + precedence: `docs/MEMORY_SKILLS_AGENTS.md` (§2) and Anthropic's Agent Skills docs.

## 2. The three scopes (native — nothing invented)

Scope = **which directory the `SKILL.md` lives in.** Claude Code discovers and precedence-orders them for you.

| Scope | Lives in | Who sees it | Propagates to the fleet? |
|---|---|---|---|
| **project** (`here`) | `<project>/.claude/skills/<name>/` | that project only (+ `paths:` sub-scoping) | no |
| **node** *(default)* | `~/.claude/skills/<name>/` | every project on that node | no |
| **fleet** | a signed `category:"skill"` extension → copied to `~/.claude/skills/<id>/` on install | every node | **yes** (via `core.sig.json` + `cc-update`) |

**"Don't overwhelm me with irrelevant skills" is solved by the mechanism itself:** project skills only appear
in their project; `paths:` gates activation to matching files; the dashboard picker groups **here / node /
fleet**. New skills default to **node** so nobody gets flooded with another node's tools. You promote up
deliberately, when a skill has earned it.

---

## 3. The surfaces

### Skills lens (dashboard)
Lists every real skill with its scope/origin badge, invocation mode, lint flags, `/command`, and allowed-tools.
- **＋ New skill** → scaffolds a `SKILL.md` and opens a Claude session in the folder to author it.
- **Find candidates** → runs the transcript miner (§5) and shows a **Suggestions** queue.
- Per-card: **View · Edit · Promote → · Delete** (delete is reversible → `_archive/`).

### Per-session skills picker (Sessions)
Every session pane header has a **✦ chip** next to the model chip. Click it → a picker grouped **This project
/ This node / Fleet** with a live filter. Choosing a skill **stages** its `/command` into that session's
terminal (no Enter) so you add arguments and review before running. This is the "intelligent dropdown": it's
genuinely context-grouped, not a flat list.

### `/skill-builder` (the no-brainer builder)
A skill any agent or person can invoke: describe a workflow in plain language and it drafts a well-formed
`SKILL.md` (sharp description, lean body, right frontmatter, right scope) and lints it. Shipped fleet-wide as a
`category:"skill"` extension so every node can build skills.

### `cc-skill` (CLI, on PATH)
Operates directly on the skill dirs (works even with the dashboard down). Node-local by default.
```
cc-skill list [--json]                      # skills grouped by scope, with lint flags
cc-skill new <name> [--scope node|project] [--desc "WHAT it does + WHEN to use it"]
cc-skill show <name>                        # print the SKILL.md
cc-skill scope <name> <node|project>        # move between node and project scope (reversible)
cc-skill lint [name]                        # the silent discoverability killers (thin desc, name!=dir, no body)
cc-skill scan [--days N] [--min-sessions K] [--out FILE] [--ai]   # mine transcripts (see §5)
cc-skill promote <name>                     # package a node skill as a fleet skill-extension
cc-skill rm <name>                          # reversible archive
```

---

## 4. Authoring workflow (design → build → test → ship)

1. **Design** — one line: WHAT it does + WHEN to use it (this becomes the `description`, the whole trigger).
   Pick scope (node default). Side effects? → `disable-model-invocation: true`.
2. **Scaffold** — `cc-skill new <name> ...`, or `/skill-builder` to draft the whole thing from a description.
3. **Build** — lean numbered steps, real commands, `allowed-tools` scoped tight, heavy reference linked out.
4. **Test** — `cc-skill lint <name>`, then actually invoke `/<name>` with the phrasing a real user would type
   and confirm it fires on the right requests (and not the wrong ones).
5. **Ship** — node/project skills are already live (the file *is* the deployment); fleet skills → §6.

**Rules that matter:** the description is the product (keywords, use-case first); lean bodies (recurring token
cost once loaded); lock the dangerous ones (`disable-model-invocation`); reuse before you fork (`cc-skill list`).

---

## 5. Auto-detection — "this repeated procedure should be a skill"

`command-center/skill_scan.py` mines this node's session transcripts (`~/.claude/projects/<slug>/*.jsonl`) for
**repeated distinctive-tool procedures** worth capturing as a skill. The signal model:

- **Inline script bodies are opaque** — `python3 -c "..."`, heredocs, `bash -c '...'`, `node -e` collapse to a
  single `<lang>-inline` token; we never split a script's contents into fake "steps."
- **Actions carry their distinctiveness** — multiplexer tools keep their subcommand (`git-push`,
  `tmux-kill-session`, `gh-pr`), curl/ssh keep their target (`curl:/api/x`, `ssh:build-box`), scripts keep
  their basename (`py:deploy.py`, `sh:release.sh`).
- **A candidate must contain ≥ 2 distinct *specific* actions** — so shell idioms (`tail|grep`, `for;do;done`,
  a lone `python3`) never qualify; only real, named, multi-tool procedures do.
- **Deduped by tool-identity** — single-command and two-step variants that share the same distinctive tools
  collapse into one candidate. Ranked by distinct-session recurrence, lightly boosted by cross-project spread.

Only normalized *action signatures* leave the tool — never raw command text, args, or paths — so no
secrets/paths leak into the candidate list.

**Two channels (both):**
- **Passive (default on):** the `skill_scan` daemon refreshes a cache when it goes stale, so the Skills-lens
  **Suggestions** queue is always fresh. Each candidate has **Build skill** (scaffold + author) and **Dismiss**.
- **Active (opt-in):** on a strong *new* candidate (≥ 8 sessions, not seen/dismissed) the platform fires ONE
  operator notification, deduped across co-located instances so the fleet never multi-pings.

**Config** — per-node `cc.config.json`:
```json
"skill_suggestions": { "auto": true, "interval_hours": 24, "notify": false }
```
`auto:false` disables the daemon entirely; `notify:true` turns on the active nudge (off by default).

---

## 6. Distribution — shipping a skill to the whole fleet

Standalone `~/.claude/skills/` entries do **not** propagate. To ship a skill fleet-wide:

1. **Package** — `cc-skill promote <name>` (or the Skills-lens **Promote →** button) copies the skill into
   `extensions/<name>/` as a `category:"skill"` extension (`extension.json` + `payload/SKILL.md`). Reversible.
2. **Neutralize** — a fleet skill must be tenant-neutral (no `~/<node>-control/...` paths). Preship's clean-core
   gate enforces this.
3. **Sign + ship** — from **Mission Control**, the deliberate fleet-ship step (`docs/MISSION_CONTROL.md`): bump
   `claudesole.manifest.json` version, `POST /api/core-sign`, push the public dist mirror → the fleet
   auto-converges. From a **tenant** node, `promote` instead files a CCR to Mission Control.

On install, `_ext_apply_payload` copies `payload/SKILL.md` into `~/.claude/skills/<id>/` — the exact place the
Skills lens and every session already read from. The two systems are unified.

---

## 7. Under the hood (file + route reference)

**`command-center/server.py`**
- `_skills_dirs()`, `_parse_frontmatter()`, `_skill_lint()`, `skills_list()` (tags `origin` here/node/fleet +
  `disable_model`), `skill_body()`, `skill_create()`, `skill_open()`, `skill_delete()`.
- `skill_inject(name, command, run)` — stage a `/command` into a session pane (mirrors `session_set_model`).
- `skill_suggestions()` / `skill_suggestions_refresh()` (background scan) / `skill_suggestion_dismiss()` /
  `skill_promote()`.
- `_skill_scan_loop()` — the supervised daemon (registered via `_daemon`); `_skill_notify_new()` (deduped via
  `command-center/_skill_notify_marker.json`).
- Frontend: `loadSkills()` + `skillSuggHTML/skillScan/skillScaffold/skillDismiss/skillPromote`; per-session
  `skillChip/skPick/skInject/skFilter` (reuse the `.mdl-menu` classes).

**Routes:** `GET /api/skills` · `GET /api/skill` · `GET /api/skill-suggestions` · `POST /api/skill-create` ·
`/api/skill-open` · `/api/skill-delete` · `/api/skill-inject` · `/api/skill-promote` ·
`/api/skill-suggestions-refresh` · `/api/skill-suggestion-dismiss`.

**Other files:** `command-center/skill_scan.py` (miner) · `command-center/cc-skill` (CLI) ·
`extensions/skill-builder/` (the fleet builder skill) · `skill-authoring/` (module home + `AGENT.md` charter).

---

## 8. TL;DR for agents

- Doing a multi-step procedure a human will want repeated? **Offer to make it a skill** (`/skill-builder`).
- Building one? **Node scope by default.** Only `promote` when it's genuinely fleet-useful.
- The **description is the product** — it's the whole discoverability surface. Sharpen it, `cc-skill lint` it.
- Side-effect skills get `disable-model-invocation: true`.
- Want to see what you already repeat enough to deserve a skill? `cc-skill scan`.
