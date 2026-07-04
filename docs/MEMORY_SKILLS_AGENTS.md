# ClaudeFather: Memory, Skills, Agents & Teams -- architecture + best practices

How a ClaudeFather organizes the four things that make an agent capable: **what it always knows** (memory /
CLAUDE.md), **what it can pull in on demand** (skills), **who it can hand work to** (agents), and **how
those agents coordinate** (teams). Synthesized from the official Claude Code docs + Anthropic's agent
engineering posts (sources at the end). The goal: thoughtful, intuitive to use + maintain, and -- the
load-bearing theme -- **set up so agents actually KNOW the capabilities exist.**

---

## 0. The mental model -- four building blocks, and when to use each

| Block | What it is | Loaded | Use it for | ClaudeFather home |
|-------|-----------|--------|-----------|-----------------|
| **Memory** (CLAUDE.md) | Always-on instructions | EVERY turn (project root + ancestors); subdir CLAUDE.md loads on-demand | The constitution: build/test commands, conventions, hard rules, where things are | the module CLAUDE.md tree |
| **Skill** | A procedure/knowledge bundle (`SKILL.md` + files/scripts) | metadata always in context; full body only when invoked | A repeatable workflow or reference too big to keep always-on (deploy steps, a checklist, a format spec) | `skills/` module (NEW) |
| **Subagent** | An isolated worker with its own context window | spawned on demand; returns a summary | High-volume / parallel / tool-restricted work that would flood the main context (review, research, audit) | `agents/` (roster) |
| **Team** | Several agents that talk to each other | spawned together | Work where the workers must share findings + coordinate (not just report back) | team configs |

**The decision guide (memorize this):**
- Need Claude to *always* remember it? -> **CLAUDE.md** (but keep it lean -- see sec 1).
- A reusable *procedure or big reference* you don't want in context until needed? -> **Skill**.
- Want a *one-off command* you trigger? -> slash command / user-invocable skill.
- Need to *talk to an external system* (API, DB)? -> **MCP tool**.
- A self-contained chunk of work that makes *verbose output* or needs *restricted tools*? -> **Subagent**.
- Workers that must *coordinate with each other*? -> **Team**.

> Anthropic's #1 rule, quoted: *"find the simplest solution possible, and only increase complexity when
> needed."* Multi-agent uses ~15x the tokens of a chat; reserve it for high-value, parallelizable work.

---

## 1. Memory -- the CLAUDE.md tree

### The hierarchy (all concatenated into context; closer-to-cwd wins on conflict)
1. **Managed/enterprise** (`/Library/Application Support/ClaudeCode/CLAUDE.md`) -- org policy, can't be excluded.
2. **User/global** (`~/.claude/CLAUDE.md`) -- your prefs across every project.
3. **Project** (`./CLAUDE.md` or `./.claude/CLAUDE.md`) -- team-shared, committed.
4. **Subdirectory** (`./sub/CLAUDE.md`) -- **lazy: loads only when Claude reads files in that subtree.**
5. **Local** (`./CLAUDE.local.md`) -- personal, gitignored, loads after CLAUDE.md at that level.

`@path` imports inline another file (recurses up to 5 levels; relative to the importing file; `~` ok).
`.claude/rules/*.md` with `paths:` frontmatter load only when matching files are touched (path-scoping).

### The rule that matters most: KEEP IT LEAN
Everything in an always-loaded CLAUDE.md costs tokens every single turn, and the model reliably follows
only so many instructions. Official guidance: **target < ~200 lines** for an always-on file; push detail
DOWN into subdir CLAUDE.mds (lazy), `.claude/rules/` (path-scoped), or separate docs pulled via `@import`.

> **Finding from this research (action item):** the project root CLAUDE.md is ~2,500 lines --
> ~12x the recommended ceiling, in context every turn. It should be cut to a lean index that `@imports` /
> links the HARD RULES and pillar detail, with the heavy content living in pillar CLAUDE.mds (already
> lazy) + `.claude/rules/`. This is a real token tax on every session. (Separate cleanup task.)

### How ClaudeFather already does this well -- and the gap
ClaudeFather's **module = a folder with a CLAUDE.md** is exactly the subdir-CLAUDE.md pattern, and the
auto-maintained `<!-- CC:CHILDREN -->` index + `<!-- CC:NOTES -->` learnings region are a clean
implementation of "lean parent that points at children + a place to file durable learnings." Keep that.
**Gap:** nothing enforces the lean-ness; the root docs have grown huge. Add a lint (sec 6).

### DO / DON'T
- DO: put build/test/deploy commands + the few hard rules + "where things are" at the project root.
- DO: keep each level short; link or `@import` instead of pasting; one fact in one place.
- DO: use subdir CLAUDE.md for directory-specific rules (they're free until you work there).
- DON'T: paste runbooks, full designs, or long reference into an always-on CLAUDE.md -> that's a Skill.
- DON'T: duplicate the same rule across levels (conflicting copies rot); DON'T put secrets in committed CLAUDE.md.

---

## 2. Skills -- the new ClaudeFather module

### What a skill is (and isn't)
A **skill** is a `SKILL.md` (YAML frontmatter + markdown body) in its own folder, optionally bundling
reference files + scripts. Its **description** sits in context always (~cheap); the **full body loads only
when invoked** -- "progressive disclosure." That's the key difference from CLAUDE.md: a skill lets you keep
a 500-line procedure or a big format spec available *without paying for it every turn*.

- **Skill vs subagent:** skill runs *in the current conversation* (stays after first use); subagent runs
  in an *isolated context* and returns a summary. Skill = reusable workflow/knowledge; subagent = offload
  verbose/parallel work.
- **Skill vs slash command:** a command is a one-shot prompt; a skill can be auto-invoked by Claude when
  the description matches, OR locked to manual (`disable-model-invocation: true`) for side-effect flows.
- **Skill vs MCP:** MCP adds *tools* (talk to external systems); a skill adds *instructions/procedures*.

### THE mechanism: the `description` is the trigger
Claude only sees each skill's `description` until it decides to use it. So the description is not a label
-- it's advertising copy that must say **what it does + exactly when to use it**, including the trigger
phrases a user would actually say. Weak description = the skill is invisible. (Same truth for agents/tools.)

### Where skills live + precedence
`~/.claude/skills/<name>/SKILL.md` (personal) | `.claude/skills/<name>/` (project, commit it) | plugin
`skills/` | nested `.claude/skills/` in a subtree. Name clash: Enterprise > Personal > Project > Nested.
The **folder name becomes the `/command`**; the `name:` field is display-only.

### SKILL.md template (annotated)
```yaml
---
name: deploy-frontend                 # optional display name (folder name drives the /command)
description: >                         # LOAD-BEARING. What it does + WHEN to use it (put the key case first).
  Deploy the site frontend to R2. Use when asked to deploy/ship/publish the site or push index.html.
disable-model-invocation: true        # side-effect flow -> only the human runs it (/deploy-frontend)
argument-hint: "[tier]"               # autocomplete hint
allowed-tools: Bash(npx wrangler*), Bash(curl*)   # pre-approve only what it needs (be specific)
---

## Steps
1. Build: `python3 build_frontend.py build index.html`
2. PUT to R2 via the worker binding (NEVER `wrangler r2 object put`):
   !`echo "curl -X PUT https://api.example.com/api/debug-r2 ..."`
3. Verify: open the deploy URL, hard-refresh.

See [reference.md](reference.md) for the full tier matrix.   # heavy detail stays out of SKILL.md
```
Authoring DO/DON'T: keep `SKILL.md` < ~500 lines (push detail to sibling files); description states *when*;
lock side-effect skills to manual; pre-approve only specific tools; test in a FRESH session (authoring
context masks gaps).

### The ClaudeFather `skills/` module (what to build -- sec 6 has the plan)
A first-class `skills/` module mirroring `agents/`: each skill is a folder, auto-discovered, surfaced in a
**Skills lens** (like the Agents lens), with a one-line registry so humans AND the orchestrator can see the
roster. ClaudeFather skills should be the home for the repeatable ops we keep re-explaining (deploy flows,
the backup/commit ritual, the pre-flash gate steps, "how to add a market config", etc.).

---

## 3. Agents -- building the roster

### Definition + precedence (Claude Code subagents)
A subagent is a markdown file (`name` + `description` required; optional `tools`, `model`, `permissionMode`,
`memory`, `skills`, `isolation`, ...). Body = its system prompt. Scopes, highest wins on name clash:
managed > `--agents` flag > `.claude/agents/` (project, commit it) > `~/.claude/agents/` (user) > plugin.
`tools` omitted = inherits all; restrict it. `model` defaults to `inherit`; route cheap work to Haiku.

### Delegation = description-matching
The orchestrator auto-delegates when the task matches an agent's `description` ("use proactively" biases
toward it). It runs in its own context window and returns only a summary -- that's the whole point
(keeps the main context clean). `/agents` lists the roster; `@agent-name` forces a specific one.

### Designing the roster (the rules that keep it from rotting)
- **One agent, one job.** Focused beats general; overlap causes silent duplicated work.
- **`name`: lowercase-hyphen, UNIQUE across the whole tree** (Claude Code silently keeps one of two clashes).
- **Convention:** `<domain>-<role>` (e.g. `fm-pipeline-research`, `patches-gate-auditor`, `security-reviewer`).
  Group into subfolders (`agents/review/`, `agents/research/`) for human browsability -- folders don't
  change invocation, only readability (except plugins, where the subpath IS part of the id).
- **Least tools + cheapest adequate model** per agent.
- **Document boundaries IN the body** ("you are read-only; if asked to write, refuse and explain").

### ClaudeFather's two senses of "agent" -- reconcile them
ClaudeFather already has `agents/<slug>/` "**agent-tools**" (security, backup, deploy, ...): a scoped dir +
CLAUDE.md charter + `tools/` + a report, surfaced in the **Agents lens**, opened as a tmux session. That's
a *product* concept (a persistent capability you talk to). Claude Code **subagents** are a *delegation*
concept (an ephemeral worker the model spawns). They're complementary:
- Keep ClaudeFather agent-tools as the **human-facing roster** (the Agents lens, the "Talk to X" button).
- ALSO ship matching Claude Code subagent definitions (in `.claude/agents/`) so the *orchestrator* can
  auto-delegate to the same roles headlessly. One role, two surfaces -- reuse the charter as the system prompt.

---

## 4. Teams + orchestration -- the complexity ladder

Climb ONE rung at a time, only when an eval shows the current rung falls short (cost rises fast):

1. **Single agent + tools** (augmented LLM) -- usually enough.
2. **Prompt chaining / routing** -- when the task cleanly decomposes or splits into categories.
3. **Orchestrator + subagents** (workers report back) -- when you can't predict the subtasks; parallel research/review.
4. **Team** (workers coordinate with each other) -- ONLY when they must share findings + challenge each other.

Quoted tradeoffs: agents ~4x tokens vs chat, multi-agent ~15x; a multi-agent research system beat single-
agent Opus by 90% on Anthropic's eval *but* only pays off on high-value, parallelizable, context-exceeding
tasks. For "sequential tasks, same-file edits, or many dependencies," a single session/subagents win.
Teams: start 3-5 ("three focused teammates often outperform five scattered ones"); each teammate owns a
distinct lens + a distinct set of files; give each an objective, output format, tool guidance, boundaries.

> ClaudeFather already HAS an orchestration primitive that fits rung 3 perfectly: the **Workflow** tool
> (deterministic fan-out: parallel/pipeline of subagents with schemas). Treat Workflows as the codified
> orchestrator-worker pattern; reserve true "teams" for the rare coordinate-with-each-other case.

---

## 5. Discoverability -- making capabilities KNOWN (the through-line)

The orchestrator only ever sees **descriptions** at selection time. Everything below is in service of
"the agent knows the tool/skill/agent exists and when to use it."

1. **Descriptions are the interface.** For every tool, skill, and agent: one or two sentences -- *what it
   does, when to use it, when NOT, inputs, outputs.* Distinct from its neighbors. This is the single
   highest-leverage maintenance task; ambiguous descriptions are why agents duplicate or misfire.
2. **Keep a human index in sync with the model-facing descriptions.** ClaudeFather's `CC:CHILDREN` (modules),
   the **Agents lens** + `/api/agents`, and a new `ROSTER.md` / **Skills lens** are the human analog of the
   descriptions the model reads. Index line shape: `name | when-to-use | tools | model`.
3. **Surface the roster to the orchestrator, not just the human.** A session's CLAUDE.md (or a small
   injected block) should point at "the skills/agents available here and when to reach for them" so the
   model is primed -- the ClaudeFather launch briefs already do this for the admin-shell/sudo protocol;
   extend that to "here is your roster."
4. **Audit + anti-rot (Anthropic's tool-tester pattern).** Periodically run each agent/skill on a canonical
   task and rewrite stale/ambiguous descriptions (Anthropic saw a 40% speedup doing this). Prune/merge
   agents whose descriptions overlap. Keep a ~20-query golden set per important agent; judge with a rubric;
   spot-check by hand.

---

## 6. What ClaudeFather has vs what to build

| Capability | Have | Build |
|-----------|------|-------|
| Module CLAUDE.md tree + auto CC:CHILDREN/CC:NOTES | YES | a **lean-lint** -- DONE (`claude-md-lint` skill) |
| Agent-tools roster + Agents lens + `/api/agents` | YES | matching **`.claude/agents/` subagent defs** + a `ROSTER.md` -- DONE (`subagents_list`, `/api/subagents`, `roster_md`) |
| Skills | YES | the **`skills/` module** -- DONE: per-skill folders, `/api/skills`, a **Skills lens**, create/delete flows |
| Teams | YES | the **`teams/` module** -- DONE: `teams_list/team_body`, `/api/teams`, a **Teams lens**, a seeded review-team |
| Orchestration | YES (Workflow tool) | document Workflows as the rung-3 pattern; reserve teams for rung-4 -- DONE (sec 4) |
| Discoverability to the model | YES | "your roster" block in launch briefs + the audit/anti-rot routine -- DONE (`roster_text`, `description_audit`, `audit_run`) |

### Build status (shipped as of 2026-06-21; 98 tests GREEN, dashboard :8799/:8800/:8801 all 200)
1. **Skills module** -- DONE. `skills_list/skill_body/skill_create/skill_open/skill_delete` + `/api/skills`,
   `/api/skill`,`/api/skill-create`,`/api/skill-open`,`/api/skill-delete`; **Skills lens** (roster by scope +
   invocation, view SKILL.md inline, + New skill that scaffolds + opens to author, Edit, reversible Delete
   that `shutil.move`s to `_archive` -- never `rm`). Reads the REAL Claude Code dirs (`~/.claude/skills` user
   + `<project>/.claude/skills`) so what you see/create is actually loaded by the project's sessions. Seeded:
   `backup-and-push`, `claudesole-restart`, `claude-md-lint` (user), `deploy-frontend` (project).
   `skills_list` also attaches a per-skill `lint` list (`_skill_lint`: no description / thin description < 20
   chars / `name != dir` / no body) surfaced as a `warning` badge + a `lint:` line in the lens, so weak
   metadata that silently kills discoverability is visible at a glance.
2. **Agents (subagent defs + scaffolder)** -- DONE. `agent_create` scaffolds a new agent-tool (charter +
   `tools/run.py` + common report schema); `subagents_list` + `/api/subagents` discover the `.claude/agents/
   *.md` subagent defs (`security-auditor,deploy-checker,incident-scanner`) that reuse the agent-tool
   charters so the orchestrator can auto-delegate. Extend with the same pattern for more roles.
3. **Roster injection** -- DONE. `roster_text()` lists the skills + agent-tools + teams available in THIS
   ClaudeFather and is injected into the chief + agent launch briefs (a `CAPABILITIES -- ...` line) so the
   model knows what to reach for. (The model also natively sees skill/subagent descriptions.)
4. **Teams (rung 4)** -- DONE. `teams_list/team_body` discover `teams/<slug>/TEAM.md` coordinating rosters
   (distinct lens + files per member, pipe-parsed via `_parse_team_members`); `/api/teams`,`/api/team` + a
   **Teams lens** (👥); seeded `review-team` (correctness/security/portability -- 3 distinct lenses + files
   that reconcile, not just report). `team_create` + `/api/team-create` + a **＋ New team** button scaffold a
   new `teams/<slug>/TEAM.md` (frontmatter + 3-member starter roster) on demand -- the create flow that
   brings Teams to parity with Skills (`skill_create`) and Agents (`agent_create`), so every block now has
   one. `team_run` + `/api/team-run` + a **▶ Run team** button on each team CONVENE it: resolve the live
   roster (`team_body`) and launch a fresh claude session pre-loaded with the coordinate-then-reconcile
   protocol (each member reviews its own lens + files, members exchange + flag conflicts, the lead writes ONE
   reconciled verdict to `data/team-runs/`), which closes the "teams are view-only" gap -- teams are now
   actionable like skills (`skill_open`) and the audit (`audit_run`), not just browsable. Surfaced to the
   model via `roster_text`.
5. **ROSTER.md (human index synced to model-facing descriptions)** -- DONE. `roster_md/roster_write` render
   four sections (skills + agent-tools + subagent defs + teams) from the LIVE discovery fns, row shape
   `name | when-to-use | tools | model` -- the when-to-use column IS the description the orchestrator sees, so
   the human index cannot silently drift. `/api/roster` regenerates + writes `ROSTER.md` on demand, surfaced
   to humans via a **↻ Regenerate ROSTER.md** button in the Audit lens (`rosterRegen`) -- ROSTER.md and
   AUDIT.md are sibling auto-generated artifacts, so the anti-rot lens is their shared regen surface (before
   it, regen was curl-only -- the sec-5 discoverability rot this module forbids).
6. **Audit / anti-rot (Anthropic's tool-tester pattern)** -- DONE, both halves.
   - *Static:* `description_audit/audit_write` + `/api/audit` write `AUDIT.md` -- pull every model-facing
     description across all four blocks from the LIVE discovery and flag the ones to rewrite (missing /
     too-short < 40 chars / no-when-cue) plus OVERLAPPING pairs (Jaccard >= 0.42 -> merge or disambiguate).
   - *Live:* `audit_run` + `/api/audit-run` -- a session launcher that resolves ONE capability and pre-loads
     a fresh claude with a per-block CANONICAL TASK + a 4-point rubric (trigger-fidelity / does-what-it-says
     / usable-output / boundary), writing PASS/REVISE + a sharper rewrite to `data/audit-runs/` (SSD).
   - *UI:* the **Audit lens** (🔬) is the human surface for both halves -- it renders `description_audit()`
     (a RAG header + every description with its flags, flagged first, + overlap pairs) and puts a **▶ Live
     audit-run** button on each capability that drives `/api/audit-run`. Re-run regenerates `AUDIT.md`.
     Before it, the routine had no discoverable entry point (sec 5 -- a capability only humans can find via a
     curl is a capability that rots). `loadAudit`/`auditRun` in the served page, guarded by the `AuditLens` test.
7. **(Later) root CLAUDE.md slim-down** -- cut the project root from ~2,500 lines to a lean index +
   `@imports`/rules; move HARD RULES into `.claude/rules/` path-scoped. (Separate task; run `/claude-md-lint`.)

---

## Sources
- Claude Code Memory: https://code.claude.com/docs/en/memory
- Agent Skills: https://code.claude.com/docs/en/skills
- Subagents: https://code.claude.com/docs/en/sub-agents
- Agent teams: https://code.claude.com/docs/en/agent-teams
- Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Claude Code best practices: https://www.anthropic.com/engineering/claude-code-best-practices

<!-- CC:NOTES -->
