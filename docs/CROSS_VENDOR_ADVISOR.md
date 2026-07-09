# Cross-Vendor Advisor — "Third-party review"

*An independent **external GPT** (Codex on the ChatGPT subscription — a **different AI vendor** than the agent
that did the work) reviews a Claude agent's finished work against its goal and returns a skeptical, structured
second opinion. Claude always holds the pen; the reviewer has eyes, not hands.*

**Status:** SHIPPED, fleet-wide, v0.99.181 (interactive) + v0.99.182 (Ralph loop-finish integration).
**Owner surface:** ClaudeFather core — `command-center/` (engine + server + dashboard) and `ralph_runner.py`.
**Provenance:** derived from the OmniAgent / **Omnigent** analysis — see [§9 Provenance](#9-provenance--where-the-cheatsheet-data-comes-from).

---

## 1. What it is (and what it deliberately is NOT)

**Is:** on demand (or at a Ralph loop's completion), an independent GPT reads the finished deliverable + the
stated goal, judges it **skeptically**, and returns `{verdict, blocking[], nonblocking[], next_task_guidance}`.
The value is a *different vendor's model* catching what Claude's own model rubber-stamped. You watch it work
live, then choose whether to inject its opinion back into Claude.

**Is NOT:**
- ❌ **Not an editor.** Report-only. Codex `exec` runs in a **read-only sandbox** natively — it can read the
  repo/diff but cannot write, open a PR, or merge. "Eyes, no hands" is enforced by the harness, not just the prompt.
- ❌ **Not a manager Claude obeys.** Guidance is labeled *external advice*; Claude adjudicates. This avoids the
  "blind boss" failure mode.
- ❌ **Not always-on / not per-step.** Interactive = summoned by a button. Ralph = fires only at **task-completion
  boundaries**, never per iteration. Keeps call volume Plus-safe.
- ❌ **Not a dependency.** It **fails open**: if Codex is rate-limited/down/misconfigured, the review returns
  `skipped` and the Claude work proceeds unblocked. A broken advisor never blocks a session or a Ralph loop.

---

## 2. Substrate (why this is cheap)

- Codex CLI (`~/.npm-global/bin/codex`, user-owned, no sudo), logged in via **device-auth** to a ChatGPT
  account → `~/.codex/auth.json` in **OAuth/subscription mode** (no API key). Plan: **Plus**. Model: **gpt-5.5**.
- Verified live: the call draws from the **subscription backend, not metered `api.openai.com`**. (Unlike Claude's
  `setup-token`, which silently drops to API mode, Codex device-auth genuinely uses the subscription.)
- **Implication:** the partner has *eyes* (repo read access) at *flat-rate* cost. Plus is fine for advisory
  volume; **Pro ($200)** is the no-integration-change upgrade path when volume or multi-user demand grows.

---

## 3. Architecture (three layers)

```
                 ┌───────────────────────────── the ENGINE ─────────────────────────────┐
  interactive ──▶│ command-center/cc-advise  (wraps `codex exec`, read-only sandbox,     │
  (any session)  │   fail-open, budget-guarded, secret-clean; --stream = live/visible,   │◀── Ralph loop-finish
                 │   --payload = assembled context, --result-file = structured verdict)   │    (ralph_runner.py)
                 └───────────────────────────────────────────────────────────────────────┘
        ▲                                                                         ▲
        │ /api/advise-start → tmux tab `advise-<session>` (WATCHABLE, streams)     │ _advisor_gate() at is_complete()
        │ /api/advise-result ← polls the result file                              │  → review + steer the next pass
        ▼                                                                         ▼
   Dashboard panel (pane/focus/grid headers + /term)                        review card → notify session
   live terminal embed + verdict + Inject + toggles                         advisor.md audit + prompt.txt steer
```

### 3.1 The engine — `command-center/cc-advise`
A stdlib-Python CLI that wraps `codex exec` with the fixed **reviewer instructions** (§4). Key flags:

| Flag | Purpose |
|---|---|
| `--payload <file\|->` | A **pre-assembled context blob** (the server/runner builds it). `-` reads stdin. |
| `--goal/--deliverable/--summary` | The original **file-based** mode (standalone / manual use). |
| `--repo <dir>` | Repo root the reviewer may READ (passed to `codex -C`, read-only sandbox). |
| `--stream` | **Transparent mode:** inherit stdout/stderr so codex's work is **visible live** in a tmux tab. |
| `--result-file <path>` | Write the structured verdict JSON here (atomic) — what a caller polls for. |
| `--verify` | **Rigor mode:** force the reviewer to OPEN files and independently re-check load-bearing FACT claims. |
| `--mode review_and_steer\|review_only` | Whether to produce `next_task_guidance`. |
| `--budget-file` / `--max-calls-per-day` | Daily call cap (Plus-safe; default 40). |
| `--json` | Print the raw JSON verdict to stdout (non-stream callers). |

Behaviour: checks Codex is present **before** spending budget → budget guard → assembles the codex prompt →
runs `codex exec --ephemeral -s read-only --output-schema … -o <last.json>` → reads the structured verdict →
writes `--result-file` → prints. **Fail-open everywhere** (missing codex / budget hit / call error / no
structured output → `{"verdict":"skipped", "reason":…}` and exit 0). **Secret-clean:** never emits raw codex
stderr (only a boolean "stderr present"); auth stays in `~/.codex/auth.json`.

### 3.2 Interactive flow — "Third-party review" button in every session
On-demand review of a live session's recent work.

- **Surface:** a 🔵 button in **every** session header — the workspace pane (`paneHead`), focus view
  (`bigHead`), grid/list tiles (`sessTile`), **and** the standalone full-screen `/term` page (self-contained modal).
- **One-click auto-context:** the server assembles the session's context **git-aware** — the files git says
  CHANGED (uncommitted + recent commits) + recent commit subjects + the recent conversation, passing the git
  repo root so the reviewer can open them. (Critically NOT raw mtime — a live node's dir churns `_*.json` STATE
  files that hide the real changes; a real review once BLOCKed "can't find the claimed changes" because of this.)
- **Transparent by construction:** the review runs in a watchable `advise-<session>` **tmux tab** (streaming
  codex's real output), which the panel **embeds** — you watch the reviewer read the repo, reason, and produce
  the verdict in real time. No black box.
- **Result:** verdict badge + opinion, a manual **Inject into Claude** gate, an **auto-inject** toggle (delivers
  via the compact-lock-guarded session injector), and a **verify** toggle. Both toggles are shown BEFORE the run
  (explicit **Start review** button reads the current verify choice), and persist per session.

### 3.3 Ralph loop-finish flow — review + steer the next pass
Opt-in per loop. When a Ralph loop **completes** (all checklist boxes checked), an external review fires before
the loop is finalized.

- **Trigger:** `_advisor_gate()` in `ralph_runner.py`, called at `is_complete()`. Config-gated by a `loop.json`
  `advisor` block — **absent = feature off, zero behaviour change.**
- **Transparent:** runs `cc-advise --stream` inside the loop's own tmux tab, so the review is visible there too.
- **Two outputs:**
  1. **Surfaces to the operator** — a review summary is delivered to the loop's notify session
     (`/api/ralph-notify` kind `advisor_review`), and the full review is appended to **`advisor.md`** in the loop dir.
  2. **Steers the next pass** (`review_and_steer` mode) — on a `revise`/`block` verdict, the labeled guidance is
     prepended to `prompt.txt` (between `<!-- CC:ADVISOR BEGIN/END -->` markers) and a `- [ ]` re-open item is
     appended to `progress.md`, so the loop runs **another bounded pass** to address the reviewer. Rounds are
     capped (`max_rounds`, default 2) so it always converges. `ship` / cap-reached / `review_only` → finalize.
- **Effect:** the external GPT becomes a **quality gate** on Ralph — a loop can't declare "done" until the
  cross-vendor reviewer is satisfied (or the round cap is hit, with the operator notified each round).

### 3.4 Campaign flow — GPT as DIRECTOR of a chain of loops
The reviewer promoted to a **director**: a perpetual **plan → build → run → review** cycle toward a north-star
goal, run full-auto with an operator intercept window. Runner: `campaign_runner.py` in tmux `campaign-<name>`.

```
   north-star goal
        │
        ▼
  ┌─▶ DIRECTOR (external GPT, cc-advise --mode direct_next, VISIBLE) ── decides: next loop  OR  campaign DONE
  │        │ next_loop {goal, checklist, rationale}
  │        ▼
  │   INTERCEPT WINDOW (timer) ── operator MAY edit / launch-now / pause / halt;  no action → auto-launch
  │        │
  │        ▼
  │   BUILD + RUN ── a Claude agent executes it (a real Ralph loop, its own live tab) → completion
  │        │
  └────────┘  (round++, until DONE / round-cap / halt)
```

- **Director** (`cc-advise --mode direct_next`): reads the north-star goal + prior-loop history + the finished
  loop's output (opens the repo) and returns `{status: continue|done, assessment, next_loop:{goal,checklist,
  rationale}, done_reason}`. It **plans**; it never edits (read-only sandbox).
- **Intercept window**: the proposed next loop is written to `pending.json` with a deadline and surfaced in the
  **Campaigns lens** with a live countdown. The operator can **edit** the goal, **launch now**, **pause**, or
  **halt** — but if nobody acts before the deadline, it **auto-launches** (full-auto with a human escape hatch).
- **Build + run**: the runner creates a real Ralph loop (`_camp-<name>-r<N>`, hidden from the Ralph lens by the
  `_` prefix, watchable from Campaigns) from the directive's checklist and runs it to completion — a Claude agent
  does the actual building, visible in its own live tab.
- **Guardrails**: a hard **`max_rounds`** cap (always terminates), the director can declare **DONE**, and
  **halt/pause anytime** (kill switch, mid-loop safe). **Fail-SAFE** (unlike the per-review advisor's fail-open):
  if the director can't decide, the campaign **pauses for the operator** rather than barrelling on. No unattended
  runaway — the round cap + Plus daily cap bound total spend.
- **Provenance:** this is the fullest realization so far of Omnigent's Tier-1 *Executor/meta-harness* idea — two
  different-vendor models pushing one goal forward together (GPT steering, Claude doing).

---

## 4. The reviewer instructions (why it's good, not sycophantic)

A fixed, adversarial template passed to `codex exec` (see `cc-advise` `REVIEWER`):

> You are an independent senior engineer from a **DIFFERENT AI vendor** than the agent that produced the work.
> A Claude agent just finished a task and summarized it. Review the finished work against the stated goal —
> skeptically. Assume the author's own model rubber-stamped its own work; your value is catching what it missed.
> You may READ the material (and files under the repo root). You must **NOT** edit, write code, or open a PR.
> Return ONLY the JSON: `verdict` (ship|revise|block), `blocking[{issue,location,why}]`,
> `nonblocking[]`, `next_task_guidance`. Cite `file:line`. Don't pad; don't invent problems.

`--verify` appends a **VERIFICATION MANDATE**: open the actual files, recompute derived counts, re-read the
referenced records; any load-bearing FACT you can't substantiate from a file is a BLOCKING issue. A clean
"ship" is warranted only if you actually opened the files.

---

## 5. API + config reference

### Endpoints (`server.py`)
| Route | Method | Purpose |
|---|---|---|
| `/api/advise-start` | POST `{session_id, verify?}` | Launch the watchable reviewer tab; returns `{tab}`. Non-blocking. |
| `/api/advise-result` | GET `?name=` | Poll: `{ready, verdict, opinion, injected, autoinject, tab}`. |
| `/api/advise-inject` | POST `{session_id, text}` | Manually inject a review into the session (guarded injector). |
| `/api/advise-toggle` | POST `{session_id, key, value}` | Persist per-session `autoinject` / `verify`. |
| `/api/advise-state` | GET `?name=` | Current per-session prefs + last result. |
| `/api/advise` | POST `{session_id, verify?}` | **Synchronous** review (blocks for the verdict) — for API/Ralph callers. |
| `/api/ralph-advisor` | POST `{name, on, mode?, verify?, max_rounds?}` | Turn the loop-finish review on/off for a loop. |
| `/api/ralph-notify` (kind `advisor_review`) | POST | The runner surfaces a completed loop review to the operator. |
| `/api/campaign-create` | POST `{name, goal, cwd?, max_rounds?, intercept_secs?}` | Create a GPT-directed campaign. |
| `/api/campaign-launch` | POST `{name}` | Start the campaign runner (tmux `campaign-<name>`). |
| `/api/campaigns` / `/api/campaign` | GET | List campaigns / one campaign's detail (config, pending, director log). |
| `/api/campaign-control` | POST `{name, action}` | pause / resume / halt / delete. |
| `/api/campaign-intercept` | POST `{name, action, directive?}` | Act on the pending next-loop directive: `go` (launch now, honoring an edit) / `skip` (pause to re-plan). |
| `/api/campaign-notify` (kinds done/ended/attention) | POST | The runner pings the chief on human-relevant campaign events. |

### `loop.json` advisor block (Ralph)
```json
"advisor": {
  "enabled": true,
  "mode": "review_and_steer",   // or "review_only"
  "verify": false,               // rigor mode (slower / more tokens)
  "max_rounds": 2                // cap on steer re-open passes (always converges)
}
```
Set it via the Ralph lens toggle (`🔵 review: on/off` on each loop card), `POST /api/ralph-advisor`, the
`advisor` param to `ralph_create`, or by hand-editing `loop.json`. **Absent = off.**

### Per-session state (`STATE_DIR/_advise.json`)
`{sessions:{<name>:{autoinject, verify, last:{verdict,opinion,rf_ts}, injected_ts}}}`. Budget in
`_advise_budget.json` (daily cap). Ralph loop state in `<loopdir>/advisor.json` (`{rounds, last_verdict}`).

---

## 6. Guardrails

| Guard | Rule |
|---|---|
| **Pen-holder** | Claude always. Guidance is labeled external advice; never auto-applied to code. |
| **Report-only** | Codex read-only sandbox — no writes/PRs/merges. Enforced by the harness. |
| **Independence** | The reviewer gets the artifact + goal (+ recent conversation), NOT Claude's reasoning transcript. |
| **Anti-sycophancy** | Adversarial reviewer prompt (§4); a different vendor by design. |
| **Fail-open** | Codex down/rate-limited/absent → `skipped`; the session/loop proceeds unblocked. |
| **Volume** | Interactive = on demand; Ralph = 1 review per completion (× bounded rounds). Daily cap (default 40). |
| **Secret-clean** | Auth in `~/.codex/auth.json`; tokens never echoed; raw reviewer stderr never surfaced. |
| **Transparent** | The review runs in a WATCHABLE tmux tab (streamed), embedded in the panel / visible in the Ralph tab. |
| **Provenance stamp** | Every injected block + operator card is stamped `🔵 GPT ADVISOR (external)`. |
| **Convergence (Ralph)** | Steer re-opens are capped by `max_rounds` so a loop always finalizes. |

---

## 7. File touch-points (where everything lives)

- **`command-center/cc-advise`** — the engine (graduated from `conceptsandideas/OmniAgent/working/`).
- **`command-center/server.py`** — interactive backend (`advise_start`/`advise_result`/`advise_inject`/
  `advise_set_pref`/`advise_state`/`advise_run` + the git-aware context helpers `_advise_assemble`/
  `_advise_changed_files`/`_advise_repo_root`), the routes, the dashboard panel (`adviseOpen`/`adviseLaunch`/
  `advisePoll`/`_adviseRenderResult`) in the `PAGE` string, the `/term` self-contained modal in `TERM_PAGE`,
  and the Ralph pieces (`ralph_advisor_set`, `ralph_notify` kind `advisor_review`, the Ralph-lens toggle).
- **`command-center/ralph_runner.py`** — `_advisor_gate()` (the loop-finish hook) + its wiring at `is_complete()`.
- **`command-center/campaign_runner.py`** — the GPT-directed campaign orchestrator (director → intercept →
  build+run → repeat). Server side: `campaign_*` functions + `/api/campaign-*` routes + the **Campaigns lens**
  (`loadCampaigns`/`campaignCard` + the intercept panel). Engine: `cc-advise --mode direct_next` (the director
  prompt + `DIRECTOR_SCHEMA`). Campaign state: `data/campaigns/<name>/` (`campaign.json`, `pending.json`,
  `director.md`, `run.log`); its loops: `data/ralph/_camp-<name>-r<N>/`.
- **`~/.codex/auth.json`** — the Codex subscription login (per-node; *later:* migrate into the credential vault).
- **This doc** — `docs/CROSS_VENDOR_ADVISOR.md`. Original spec: `conceptsandideas/OmniAgent/deliverables/
  CROSS_VENDOR_ADVISOR_SPEC.md`.

---

## 8. Roadmap / build order

1. ✅ **v1 — interactive "Third-party review"** in any session (watchable, Inject + auto-inject + verify). SHIPPED.
2. ✅ **Ralph loop-finish auto-review + next-task steer.** SHIPPED.
3. ✅ **Campaigns — GPT as DIRECTOR** of a chain of loops (plan → intercept → build → repeat). SHIPPED (§3.4).
4. **Ralph per-iteration review + pause/modify** — opt-in per loop, tighter budget gate (Plus-aware).
5. **Provider-agnostic partner abstraction** — Gemini / local behind the same seam (the real Omnigent *Executor*
   pillar); optional debate-to-converge and eyes-on-manager modes. Upgrade to Pro when volume warrants.
6. **Vault migration** — move the Codex login into the per-install credential vault for fleet sharing/rotation.
7. **Campaign polish** — richer intercept editing (full checklist edit), per-campaign budget cap, a campaign
   history/timeline view, resume-after-restart of a running campaign.

---

## 9. Provenance — where the "cheatsheet data" comes from

This entire feature is the **first thing built** out of a deep-dive analysis of **OmniAgent**, whose real project
name is **Omnigent** (`omnigent-ai/omnigent`, Databricks OSS, Apache-2.0, ~315k LOC, alpha) — a *meta-harness*
over ~12–23 agent runtimes and any model provider. A full clone is kept on the SSD at
the authoring node's `data/research/omnigent`. The analysis lives in **`conceptsandideas/OmniAgent/`** (on the
Mission Control / authoring checkout):

- **`deliverables/OMNIGENT_VS_CLAUDEFATHER_ANALYSIS.md`** — the strategy writeup: a side-by-side comparison of
  Omnigent vs ClaudeFather + a **ranked "steal-list" (Tier 1–3)** of what to graft, what NOT to adopt, and the
  recommended sequence. **The cheatsheet.** The Tier-1 item — *Omnigent's multi-vendor **Executor** seam* (it can
  run a task on a different vendor's model) — is exactly what became this cross-vendor review.
- **`deliverables/OMNIGENT_SUBSYSTEM_BRIEFS.md`** — implementation-grade reference for five Omnigent subsystems
  with `file:line` anchors (so a future build doesn't re-investigate). §A/§E are the relevant ones here.
- **`deliverables/CROSS_VENDOR_ADVISOR_SPEC.md`** — the locked design spec for THIS feature (esp. §7b, the v1
  decisions). This system doc is the shipped-reality companion to that spec.
- **`working/cc-advise`** — the original Phase-1 standalone spike (now graduated into `command-center/cc-advise`).

**The lineage in one line:** Omnigent proved a meta-harness can route work across vendors; we took the narrowest,
highest-value slice of that — *a different vendor's model as an independent reviewer* — and grafted it onto
ClaudeFather's existing session + Ralph + mesh machinery, keeping it advisory, Plus-cheap, and fail-open. The
adversarial-independence rule (reviewer gets the artifact, not the author's reasoning) mirrors Omnigent's **Polly**
cross-review discipline. Three more Tier-1 Omnigent ideas remain on the steal-list (see the analysis doc): a
3-verdict ALLOW/DENY/ASK policy engine, disposable cloud-sandbox compute, and a secretless credential proxy.

> **Key engineering lesson (filed platform-wide):** black-box synchronous AI calls are wrong on this platform.
> Visible AI work belongs in a **live tmux tab you can watch** (the Ralph live-tab pattern). Every advisor call —
> interactive and Ralph — streams into a watchable tab for exactly this reason.
