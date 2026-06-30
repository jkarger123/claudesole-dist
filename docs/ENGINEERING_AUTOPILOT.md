# Engineering Autopilot — the discipline system

**Goal:** make the platform itself do the disciplined things a senior engineer does — so an operator with no
understanding of (or concern for) their codebase still ends up with correct structure, the right context loaded,
deliverables filed where they belong, work routed to the right home, and tidy deduped records of everything done
and learned. An inheritor opens any folder and sees what looks like meticulous engineering. The whole system is
**Assisted** (watch → propose → one-click confirm), **transparent**, and **opt-out** — never silent magic, only
two genuinely *hard* gates (the preship UI lint and signed-core integrity).

Two intertwined jobs: **(1) control exactly what context each agent receives** (right knowledge, never bloat),
and **(2) automate the engineer-grade habits**. Both live in `command-center/server.py`; deeper background in
`docs/CONTEXT_ENGINEERING.md`, `docs/CONTEXT_STRATEGY.md`, `docs/DESIGN_SYSTEM.md`.

---

## Part 1 — Controlling the context payload (what every agent receives)

Principle: **the Menu, the Scout, the Vault** — a tiny always-on map, a cheap pass that surfaces what's relevant,
full content only on demand. Never preload-everything (rot); never go-look-everywhere (the agent won't know to).

- **The map — always on, can't drift.** A cascading `CLAUDE.md` tree generated from the live filesystem:
  `CC:TREEMAP` (full module map in the root doc), `CC:CHILDREN` (each folder lists its sub-tools), `CC:NOTES`
  (per-module learnings). `regen_treemap()` / `regen_children()`; every level auto-loads root → any agent knows
  *what exists and where*.
- **Retrieval over preload.** `context.py` (event store + entity graph keyed by person/client/subject) →
  `context.assemble()` returns a **cited, budgeted, time-decayed** slice about the subject on demand. Anthropic's
  external-memory pattern. Fed by `_context_backfill` (calls/email/calendar/clips/notes/tasks/ideas + each
  extension's `context_source` hook).
- **The Scout.** `context.scout()` — a cheap, freshness-biased pass that surfaces *relevant pointers the agent
  was NOT handed* (the email/file/call just out of view) as pointers, deduped against the brief's own citations.
  Solves "the agent doesn't know what it doesn't know."
- **Role-scoped briefs.** Chief (`_system_brief`) = fullest (system map + secrets contract + recent-across-the-op
  + available-tools tier). Scoped agent-tool (`agent_open`) = charter + files + roster (lean). Plain session
  (`launch` → `_launch_sys_context`) = the tree IS the context. A node never hears about a tool it doesn't have.
- **Tiered tool awareness.** Enabled extensions → full `AGENT.md` (`_ext_agent_context`); available-but-off → a
  one-line pointer, Chief-only (`_ext_available_brief`).
- **Budget discipline.** Index-not-dump: `doctor()` flags any `CLAUDE.md` over ~200 *authored* lines
  (`_authored_lines` strips the managed map) → "slim to pointers."
- **Injection.** At launch everything rides in via `--append-system-prompt` (a system block, no forced turn):
  `_files_brief` + `_extend_brief` + `_launch_context_brief(subject)` + `_scout_brief`.
- **Visible + auditable.** `context_package()` (`/api/context-package`, the Context-lens inspector) + the 📦
  payload chip on each session show the exact token weight of everything beyond your message, by component.
- **Stays clean over time.** The self-curating records (Part 2) keep retrievable knowledge deduped + high-signal,
  so the payload doesn't degrade as the codebase grows.

---

## Part 2 — Automating the engineer-grade habits

| Habit | Mechanism (code) |
|---|---|
| Correct **folder structure** | module map + a "new folder must get a `CLAUDE.md`" brief (`_NEW_FOLDER_BRIEF`); promote-a-tool-down governance; transfers create the home if none fits (`module_add`) |
| **Right context** loaded | auto-brief + Scout at every launch (`_launch_sys_context`) — no agent starts blank |
| **File things where they belong** | output routing (`_files_brief` — deliverables under the module the work belongs to, not cwd); learnings file to the correct folder with anti-taint |
| Work in the **right place / agent** | server-side **warm transfer**: `_drift_sweep()` watches every scoped conversation and `handoff_propose()`s a move when it drifts off-lane (route via `route()`/`_llm_route()`); you one-click confirm; "Keep it here" (`handoff_decline(suppress=True)`) stops re-asking |
| **Keep records** of work/learnings | close → handoff + resume pointer (`close_session`); abandon → distill durable decisions into the folder (`_distill_harvest` via `claude -p`) |
| **Don't repeat / don't forget** | idle conversations auto-archive, resumable, never deleted (`reconcile_once`/`_archive_session`/`resume_archived`); many convos in a folder converge on one shared record |
| **Housekeeping, no bloat** | hourly `_housekeeping_once()`/`_housekeeping_loop()`: regen map, `doctor()`, retire idle, **self-curate records** (`_curate_notes_once` — dedupe/merge/resolve-`[CONFLICT?]`, backed up to `_notes_curate_backup.jsonl`); plus `module_note` dedup-on-write |
| Long sessions don't blow the window | graceful auto-compaction (write handoff → `/compact` → re-read) |
| New features stay **consistent** | the design-system linter (`ui_lint.py`) in the **preship gate** — a one-off dialog/color/badge/emoji *fails the ship* |
| Tamper-proof core | signed integrity manifest + self-heal (`core_verify`) on appliances |

The lifecycle these share: a conversation is an ephemeral *meeting*; a folder's `CLAUDE.md` + `CC:NOTES` are the
durable *records*. Meetings file their minutes to the folder; the folder's records are curated to stay tight.

---

## Part 3 — The posture that makes it land

- **Watch-and-propose, not force.** The platform observes (drift, idle, bloat, payload) and **proposes**; you
  confirm with one click. Only the safety gates are hard (preship lint, core integrity).
- **Transparent.** The drift prompt pops up plainly ("this belongs in X — move it?", `hoShowAlert`); the
  **housekeeping digest** (`housekeeping_digest()`, `/api/housekeeping-digest`, the Transfers-lens card) shows
  what each pass did (watched / proposed / retired / records tightened / map regen); the payload chip shows what's
  loaded. `/api/housekeeping-run` runs a pass on demand.
- **Opt-out, and it sticks.** One toggle per behavior (Context tab → `context_settings`, persisted to
  `cc.config.json`): `context_brief`, `context_ingest`, `scout`, `handoff`, `reconcile`, `smart`, `housekeeping`,
  `autocompact` — all **on by default**, all **obeyed**. Decline a suggestion → it won't nag.
- **Free.** "Smart" judgment calls use the node's Claude subscription (`_claude_text` → `claude -p`),
  deterministic-first — the model only fires on genuinely ambiguous cases, so it sips the window rarely.

**Net:** the average user operates at senior-engineer level without the vigilance — the platform does the work and
only asks for a click.
