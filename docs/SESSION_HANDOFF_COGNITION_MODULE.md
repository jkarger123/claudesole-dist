# Capstone -- the ClaudeFather Cognition module (Memory / Skills / Agents / Teams)

What got built so a ClaudeFather organizes the four things that make an agent capable, makes them
discoverable, and keeps them tested + portable. Design spec: `docs/MEMORY_SKILLS_AGENTS.md`.

## What's built (all live, tested, portable)
- **Skills** (the new module): `skills_list / skill_body / skill_create / skill_delete / skill_open` +
  `/api/skills`,`/api/skill`,`/api/skill-create`,`/api/skill-delete`,`/api/skill-open`. A **Skills lens**
  (roster by scope + invocation; per-skill **lint** badge; View SKILL.md inline; **+ New skill** scaffolds
  + opens to author; Edit; **Delete** = reversible archive). Reads the REAL Claude Code dirs
  (`~/.claude/skills` + `<project>/.claude/skills`) so what you see/create is actually loaded by sessions.
- **Agents**: `agent_create` (scaffolds charter + `tools/run.py`) + `agent_delete` (reversible archive) +
  the existing agent-tool roster + **Agents lens** (+ New / Delete / Run / Details / Talk). Plus Claude Code
  **subagent defs** in `~/.claude/agents/`: security-auditor, deploy-checker, incident-scanner, cost-reporter,
  code-reviewer -- so the ORCHESTRATOR can auto-delegate, not just the human.
- **Roster + discoverability**: `roster_text()` injected into every chief/agent launch brief (a
  `CAPABILITIES --` line) so the model knows what it can reach for; `/api/roster`, `/api/subagents`,
  `description_audit()`, `roster_md()`, `ROSTER.md`, `AUDIT.md`, an **Audit lens**, and the **roster-audit**
  skill (flags weak/missing/generic descriptions).
- **Teams**: `/api/team-create`,`/api/team-run`,`/api/teams` (rung-4 coordinate-with-each-other pattern;
  rung-3 fan-out is the existing Workflow tool).
- **Memory hygiene**: the `claude-md-lint` skill (finds oversized CLAUDE.mds) + `docs/ROOT_CLAUDE_SLIMDOWN_PLAN.md`
  (the gated plan to slim the 2,500-line hptuners root -- human-approved cutover, not auto-applied).
- **Seed skills**: `backup-and-push`, `claudesole-restart`, `claude-md-lint`, `roster-audit` (user) +
  `deploy-text2tune-frontend` (hptuners project).

## How to extend
- **Add a skill**: Skills lens -> + New skill (or drop `<scope>/.claude/skills/<name>/SKILL.md`). The
  `description` is the trigger -- say WHAT it does + WHEN to use it. Keep SKILL.md lean; link sibling files.
- **Add an agent-tool**: Agents lens -> + New agent-tool (scaffolds charter + `tools/run.py` on the common
  report schema). Edit `checks()` to add real read-only checks.
- **Add a delegatable subagent**: drop `~/.claude/agents/<name>.md` (name + description required; the
  description drives auto-delegation). Reuse an agent-tool charter as the system prompt.

## How it's tested
- `tests/test_cognition.py` -- 98 stdlib-unittest tests (GREEN): frontmatter parser, report schema, name
  sanitization, create/delete, roster output, import-safety. Run: `python3 -m unittest -q tests.test_cognition`.
- **Ralph `verify.py`** gates each loop iteration: Python ast + the test suite + the 3 instances at 200 +
  **`node --check` of the served frontend JS** (added after a mis-escaped quote broke the whole dashboard --
  Python+200 alone can't catch a JS error).

## How it propagates (portability -- PROVEN)
`cc-update.sh <upstream>` (target = `CC_HOME`) copies the manifest's `framework_paths` into a deployment and
NEVER touches `preserve_paths` (per-deployment config/state/reports) -- splicing back each file's CC:NOTES.
Verified: a fresh target received server.py (with the Skills/Agents module), the lenses, docs, presets, and
agent charters+tools; per-deployment state did NOT leak; propagated server.py parses clean.

## Lessons baked in (so this doesn't recur)
- **Loop circuit-breaker** (`ralph_runner.py`): auto-halt after `STALL_LIMIT` (default 12) iterations that
  check 0 new boxes -- a non-converging loop can no longer burn tokens forever. (This module's own loop spun
  ~700 iterations before this existed, trapped by a self-defeating doc==live test-count assertion, since removed.)
- **Brittle self-tests are a trap**: never assert a doc must EXACTLY equal a live count -- it guarantees drift.
- **verify gates must check the JS**, not just Python + HTTP 200.
- **tmux window-size** is one-size-per-pane shared across clients: `smallest` so a phone sharing a session
  with a desktop fits (restores full width when the phone tab closes).

## Remaining (human-gated)
- The root-CLAUDE.md slim-down CUTOVER (plan ready in `docs/ROOT_CLAUDE_SLIMDOWN_PLAN.md`; do it as its own
  focused pass, one rule at a time, with approval).
