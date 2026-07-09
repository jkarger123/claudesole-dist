# The Front Desk

*The entry point that puts you in the RIGHT scope with a clean context — the "turn vibe coders into context
engineers" differentiator, moved from suggest-and-clean-up-after to force-at-the-moment-of-intent. Deep-audit
Phase 1.3. Read before touching `front_desk`/`front_desk_open`, `/api/frontdesk`, `cc-front`, or the Start box.*

## The problem it solves
The burden of "start in the right folder" sits on the user at the exact moment they're least willing to carry
it — so they dump everything into one session (root, or whatever's on top), and the context-discipline system
spends its energy *correcting* pollution after the fact (the hourly drift sweep, a proposal buried in a
Transfers tab). The Front Desk inverts that: the first thing you interact with routes your goal to its proper
home and opens a session **there**, with the goal already seeded. Because it's the *smoothest* way to start,
discipline becomes the path of least resistance.

## Front Desk vs Chief of Staff (the boundary — keep it clean)
Both are always-open agents, so users (and agents) must understand the difference. The business metaphor:

| | **Front Desk** | **Chief of Staff** | **Departments** (scoped agents/sessions) |
|---|---|---|---|
| Role | Receptionist | Senior manager / owner | The people doing the work |
| You use it to… | **start** — get placed in the right department | **escalate** — cross-department, structural, or fleet/platform matters | **do the actual work** |
| How often | every time you begin something | occasionally, only when it spans departments | most of your time |

- **The Front Desk** places you; it does not do the work and it is not your manager. If someone raises a
  *cross-department / structural / escalation* matter at the desk, it points them to the Chief — it does not force
  it into a department.
- **The Chief of Staff** is the senior manager: you do **not** check in with it for normal day-to-day work (that
  happens in the department). It handles what spans the whole business — fleet/platform decisions, structural
  changes, problems crossing departments.
- **Departments** (scoped agents / project sessions) do their own work. When something is *not their lane*
  (cross-department, structural, platform/framework), they **escalate** rather than muscle through: a warm
  transfer (`cc-handoff propose`), `cc-escalate` to the Chief / Mission Control, or a **Core Change Request** for a
  framework change. This keeps each scope's memory clean and avoids duplicated work.

This boundary is encoded in the Front Desk help text, the concierge brief (rule 6), and every scoped-agent brief.

## Three-speed cascade (never a gate)
The design rule: the front desk must be **faster** than bypassing it.
- **Speed 1 — the Start box (0 tokens, <1s).** Type what you're doing; a free `route()` call shows a scope chip
  (`→ extensions/airtable · 82%`); press Enter → launched there with your goal as the opening turn. For a
  confident route this *is* the whole front desk.
- **Speed 2 — the Concierge (cheap model, 1–3 turns).** Low confidence / needs-a-new-home → an ephemeral
  triage agent converses (≤2 questions), then hot-swaps you into the right scope (or creates one).
- **Speed 3 — escape hatch (0 friction).** The old picker one click away; a `<known-rel>: <goal>` path prefix
  launches straight there; power users are never gatekept.

## Backend (built)
- **`front_desk(body)`** — `{text, rel}` = the operator accepted a scope chip → `launch("studio", …, rel=rel,
  seed=text)` (rel="" = project root). `{text}` alone → `route()` it; **confident (≥0.6) → launch straight
  there**; else → the concierge.
- **`front_desk_open(text)`** — spawns the ephemeral cheap-model concierge (`_FRONTDOOR_BRIEF`), greeting the
  operator with the router's best guesses already filled in; tagged `_smeta kind=frontdesk` (ephemeral).
- **`POST /api/frontdesk`** `{text, rel?}` → the above. **`cc-front "<goal>"`** — the CLI (agents + humans).
- Reuses the existing router (`route()`/`_llm_route()`/`_scope_candidates()` — *the CLAUDE.md discipline IS the
  routing index*), `launch(rel=, seed=)`, and (via the concierge's `cc-handoff`) `handoff_propose/accept` +
  `module_add` for new-home creation.

## Verified
`POST /api/frontdesk {text:"fix the airtable sync duplicates", rel:"extensions/airtable"}` launched a session
whose cwd is `extensions/airtable` with the goal seeded; a vague goal spun up the concierge. Both confirmed live.

## Not yet built (the roadmap tail — Phase 1.3 M1–M6)
- **The Start box UI** (M4) — replace `▶ New session` with `▶ Start` + a live route chip (`GET /api/route` as you
  type) → Enter posts `/api/frontdesk {text, rel}`. Keep the old picker behind "Choose a place instead".
- **M1 agent-completable accept** — `cc-handoff go` (gated by `pkt.by=="frontdesk"`) so the concierge's in-chat
  "yes" completes the move without a second click in the Transfers tab.
- **M2 UI-follows-the-swap** — the sessions poll jumps the browser to the destination when a frontdesk handoff
  delivers; offer-archive the concierge tab.
- **M6 greenfield fork** — if the intake reveals a whole new PROJECT (not a module), the concierge offers
  `cc-onboard scaffold` instead of `module_add`.
- Default-entry rollout: make `▶ Start` the default + first-run landing (a `frontdesk` toggle in
  `context_settings`), with the escape hatches above; give the Chief `cc-handoff go` too so triage-via-Chief
  completes.

## Files
- `command-center/server.py` — `front_desk`, `front_desk_open`, `_FRONTDOOR_BRIEF`, `/api/frontdesk`.
- `command-center/cc-front` — the CLI.
- `command-center/cc-route` / `cc-handoff` / `cc-onboard` — the machinery the concierge drives.
