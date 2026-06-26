# ClaudeFather — VISION (the north star)

> Read alongside **`docs/PRODUCT_PRINCIPLES.md`** (the "how we build" contract). This doc is the "what we're
> building and why." Every feature gets checked against both.

## The dream, in one line

**An all-knowing business partner that lives where you work — with more complete context than you have
yourself — that hands you (and your agents) the *perfect* slice of that context for whatever you're doing,
the instant you're doing it, and proves where every piece came from.** Your data; your machine; your Jedi.

A person sits down at any computer they own, connects to their always-on Mac, and the system is already
caught up: it knows the client they're about to call, the thread it's about, the last decision, the open
items, their own voice — and it has positioned the right working context *before they ask*. Nothing was
briefed. Nothing was navigated to. Nothing left their machine.

---

## 1. The thesis: context is the moat — but "more context" is the trap

ClaudeFather started from one real observation: **Claude Code gets dramatically better when it has the right
`CLAUDE.md` context, and the deep-folder-tree trick (more specific context as you descend) works — but it's
brutal for a human to keep navigating to the right place to get the right edge of context.** Context is the
secret sauce; assembling it by hand doesn't scale.

The 2025–2026 research sharpens this into the central design law of the whole product:

> **Completeness lives in a STORE. The working window an agent sees is a small, ruthlessly-curated SLICE,
> assembled on demand.**

Why the literal version of the dream ("give the AI full context of everything") is wrong — it makes the model
*worse*:

- **Context rot is architectural, not a capability gap.** Chroma tested 18 frontier models; *every one*
  degrades as input grows — accuracy can drop 30–50% well before the advertised window, and even a *single*
  distractor measurably hurts. It's a property of transformer attention, not something training fixes.
- **Effective context ≪ advertised.** For real multi-fact work, usable context sits around **200–400K
  tokens**, not the 1M on the box.
- **Lost-in-the-middle is real and persists in 2026.** Models use the **beginning and end** best, the middle
  worst — mid-placement can cost 20+ points. Below ~50% fill it's a U-curve; above ~50% it collapses to pure
  end-bias.
- Anthropic's own framing: context engineering is finding **"the smallest possible set of high-signal tokens
  that maximize the likelihood of a desired outcome"** — an *attention budget* every token depletes.

So the moat is **not capture** (everyone can capture). The moat is the **router**: the thing that, for the
current task, assembles the *right* small slice — ranked, deduped, budgeted, edge-placed, and cited. Almost
nobody has built a great one for *personal/agency life*. That is the product.

---

## 2. Principles (extends PRODUCT_PRINCIPLES.md)

1. **Perfect context, not maximum context.** Curate to a budget; high-signal at the edges; cite everything.
   Completeness in the store, lean in the window.
2. **Sovereign per user.** The atom is one person + their ClaudeFather, with their private context graph on
   their (or their org's) machine. Their Jedi knows *them* deeply.
3. **Federated, never pooled.** Collaboration is an upper layer that shares **derived, consented,
   provenance-tagged slices** — never raw context, never a central index. The boundary is a *positive grant*
   (push), not a *negative filter* (mirror-and-hope) — which inverts the entire enterprise-AI failure mode.
4. **You own your context, with receipts.** Local-first, self-hosted, user-owned; every answer and every
   captured signal is auditable back to its source. This is the brand spine.
5. **Provenance-bound capability.** What an agent is allowed to *do* is bound to *where the information came
   from*. Untrusted/unconsented content is data, never instructions, and can never reach a consequential
   action.
6. **Context follows intent, not location.** The right edge comes to you; you never navigate to it.
7. **Self-hosted single-authority** (honest naming): one always-on Mac (mini/Studio) is the source of truth;
   any device you own is a thin client over the tailnet. We deliberately trade network-optional offline
   editing (so we skip CRDTs entirely) for ownership + privacy + simplicity.
8. **Stdlib-first, deterministic where it matters.** SQLite + FTS5 + recursive CTEs do ~80% of the job with
   zero deps; conflict/freshness resolution is deterministic code, not an LLM prompt; embeddings/rerank are
   optional drop-in upgrades behind flags.

---

## 3. The architecture (seven layers)

```
 ┌─ CAPTURE / EVENT BUS ─────────────────────────────────────────────────────┐
 │ every surface emits normalized EVENTS (email, calendar, files, calls,      │
 │ sessions, web, notes, screen*) — each stamped with source + trust + time   │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ CONTEXT STORE (the memory) ───▼───────────────────────────────────────────┐
 │ append-only EVENT LOG (source of truth)  →  projections:                    │
 │   • bi-temporal ENTITY/EDGE GRAPH (people/projects/clients/threads/files)   │
 │   • MEMORY TIERS: core blocks · semantic profile · procedural rules ·       │
 │                   episodic timeline · voice exemplars                        │
 │   • FTS index. provenance + trust on EVERY row.                              │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ THE ROUTER (the moat) ────────▼───────────────────────────────────────────┐
 │ assemble(subject, query, budget, task) → retrieve (lexical+graph+dense?) →  │
 │ fuse → rank (relevance×recency×trust) → dedup(MMR) → budget → EDGE-PLACE →  │
 │ CITED bundle. Completeness in the store; a small slice out.                  │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ FOCUS / INTENT + SESSION HOMING (the Jedi mechanic) ──▼────────────────────┐
 │ infer the current SUBJECT from signals → re-home the working session        │
 │ (cwd + CLAUDE.md stack + loaded memory + git branch) → the place finds you  │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ AGENT FABRIC (the shotgun rider) ─▼───────────────────────────────────────┐
 │ ambient agents watch the event stream (notify/question/review) + on-demand  │
 │ agents; all pull context ONLY through the router; an Agent Inbox to steer    │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ TRUST / CAPABILITY PLANE ─────▼───────────────────────────────────────────┐
 │ provenance flows capture→store→router→action; capability bound to source;   │
 │ dual-LLM (planner/quarantine); break a lethal-trifecta leg by construction  │
 └───────────────────────────────┬───────────────────────────────────────────┘
 ┌─ THE COMBINE LAYER (federation) ▼──────────────────────────────────────────┐
 │ sovereign user nodes + an overseer; PROJECT SPACES hold REFERENCES to       │
 │ consented, signed, redacted user-SLICES — never raw context                 │
 └────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Capture / event bus
Every surface emits a normalized event `{ts (occurred), ingested, kind, source, trust, actor, subject,
title, body, refs, ext_id}`. Idempotent on `(source, ext_id)` so backfills never duplicate. We already
produce most of these (Gmail, Calendar, Drive, Granola, sessions, deliverables); new surfaces are cheap to
add. **Read the macOS Accessibility tree, not screenshots** — AX text is ~100× cheaper than OCR and ~100%
accurate; pixels are a last resort (tier 3).

### 3.2 The context store (event log + bi-temporal graph + memory tiers)
**Event-sourced**: one append-only log is the source of truth; entities, edges, memory tiers, and the FTS
index are **projections** that can be dropped and rebuilt by replaying the log (free time-travel, audit,
corruption-repair). All in one SQLite file (WAL, single writer = the always-on Mac).

- **Bi-temporal edges** (Graphiti/Zep model): four timestamps — `valid_at`/`invalid_at` (real-world) and
  `created_at`/`expired_at` (system) — so we can answer "what was true *when*" and correct facts without
  destroying history. **Conflict rule: invalidate, never delete** (set the old edge's `invalid_at` = the new
  edge's `valid_at`). **Resolve freshness in deterministic code (`max(valid_at)`), never in the LLM** — the
  research shows a ~50-line deterministic resolver beats every off-the-shelf memory system by 50–87 points on
  "which fact is current."
- **Entity resolution** (the same person from email/calendar/Drive/transcript → one entity): two-tier —
  deterministic high-confidence keys (email, attendee id, owner email) first; Jaro-Winkler fuzzy (≥~0.85) for
  the rest; LLM only on blocking survivors. **Transcript speakers** resolve against *that meeting's attendee
  list* (collapses an open-vocabulary problem to 3–8 candidates). Merge non-destructively (`aliases[]`,
  `source_ids{}`) so it's reversible.
- **Memory tiers** (Letta + LangMem vocabulary): **core blocks** (small, labeled, char-limited, always
  in-context — `persona`, `human`, `project:*`); **semantic profile** (preferences/expertise, updated in
  place); **procedural rules** (behavior); **episodic timeline** (the event log); **voice exemplars**
  (curated, *diverse*, per-format — prefer explicit style rules over imitation for casual voice).
- **Provenance + trust on every row** (W3C PROV-flavored: `wasAttributedTo`, `wasDerivedFrom`,
  `wasGeneratedBy`), plus an `observation|assertion|untrusted` integrity label — the security primitive.

### 3.3 The router (the moat)
Pipeline: **candidate generation (over-fetch) → fuse → rank → diversify/place**.
- **Hybrid retrieval**: SQLite **FTS5/BM25** (exact terms — filenames, IDs, ECU terms, people) + 1–2-hop
  **graph neighborhood** of the subject (LazyGraphRAG-style, query-time only, JSON/CTE adjacency — no graph
  DB) + optional **dense embeddings** (Voyage `voyage-3.5-lite`, brute-force cosine cached — there's no scale
  need for a vector DB at one-user volume).
- **Fuse with Reciprocal Rank Fusion (k=60)** — ranks not scores, so incompatible scales (BM25 ~0–15 vs
  cosine ~0.7–0.95) don't fight. (v1 uses a transparent weighted sum; RRF is the upgrade.)
- **Score = relevance × recency × trust.** Recency = exponential half-life decay (per task type), or buckets
  so a canonical-but-old doc can still win. Trust = the per-source prior.
- **Diversify + budget with MMR (λ≈0.7)** — don't pack near-duplicates; greedy knapsack to the token budget.
- **Summary ladder (L0 full / L1 paragraph / L2 gist)** — top items go in verbatim, mid as summaries, tail as
  cited stubs. Keep verbatim what the task manipulates (code, IDs, the active file, the literal ask);
  summarize resolved discussion/background.
- **Edge-placement**: highest-signal first AND last, weakest in the middle; the user's query at the very
  bottom (Anthropic: query-at-end ≈ +30%). Wrap items in tagged blocks.
- **Cite everything**: return a manifest (marker → source, span, score, why-included). Build this from day
  one — retrofitting citations is misery.
- **`task_type` presets** (qa/edit/plan/chat/debug/research) set budget fraction, weights, half-life,
  rerank-on/off — cheap config that makes the router feel smart per task.
- Optional, behind flags: HyDE/multi-query expansion; a **rerank API** (Voyage `rerank-2.5`) over the top ~50
  (biggest quality jump after hybrid); Anthropic **context-editing** (`context-management-2025-06-27`, +39%
  quality / −84% tokens) when the router feeds a Claude API loop.

### 3.4 Focus / intent + session homing — see §4.

### 3.5 Agent fabric
Ambient agents subscribe to the event bus and act with the three HITL gates — **notify / question / review** —
surfaced through an **Agent Inbox** (email-like UI for many concurrent agents) so the operator steers instead
of drowns. Every agent pulls context only through the router. On-demand agents (chiefs, scoped agents) use the
same path. Orchestrator-worker (overseer spawns workers that coordinate *through* it) for the heavy jobs.

### 3.6 Trust / capability plane — see §7.

### 3.7 The combine layer (federation) — see §5.

---

## 4. The killer mechanic: context follows intent, not location

Today Claude Code's context is a function of **where you are** (cwd → it walks up loading every `CLAUDE.md`).
Elegant, but it puts the burden on the human to stand in the right folder. We invert it:

1. **Focus/intent signal.** Continuously infer (or one-tap declare) the current *subject* (this client /
   project / thread) from cheap signals: frontmost app (`lsappinfo`, no permission), window title + selected
   text (Accessibility), active browser URL/title (AppleScript), recent files (`mdfind`), the calendar, what
   was just typed. A **3-stage cascade**: rules (URL host / bundle id / path) → embeddings k-NN over known
   subjects → small LLM only on ambiguity. Segment the noisy stream into stable episodes with **debounce +
   hysteresis + ~750ms min-dwell**; capture on events (app switch, typing pause), not a clock.
2. **The router assembles the edge** for that subject (the relevant `CLAUDE.md` layers **plus** the live
   thread, last call, open tasks, top past sessions, deliverables) — the perfect small slice.
3. **Session homing.** Keep the active session aligned to the subject — set **cwd** (the highest-leverage
   single action for Claude Code, since everything cascades from it), switch git branch/worktree, stash the
   prior subject's work, load the **DOI-ranked** (Mylyn: recency × frequency) context. **The place finds you.**
   - *Probabilistic-with-override*: it will mispredict; show an ambient "now on: X" cue + one-tap pin/correct.
     Never silent-and-irreversible.
   - **Sharp edge (already in our memory):** auto-memory is **path-keyed**, so moving cwd orphans transcripts.
     A homing move **must re-key/re-align memory** or it severs continuity.

And the `CLAUDE.md`-tree insight, solved structurally: we already auto-maintain a module/tree map. We **invert
the relationship — the graph becomes the source of truth, and `CLAUDE.md` files become one projection** the
system writes and keeps current. You stop hand-curating deep trees; the system maintains them *and* supersedes
them with the live edge. The folder tree was a clever proxy for "specificity by location"; the graph + router
is the real thing it approximated.

The number to lead with: interrupted knowledge work takes **~23 minutes to resume** (Mark, UCI). The homing
engine's job is to delete that 23 minutes.

---

## 5. The combine layer: sovereign user + federated projects

Build **single-user first**; design the combine layer as the upper tier from day one. An agency = N sovereign
Jedis + a federation layer. You don't sell "a business account"; you sell *every employee their own partner*
plus *compounding collective intelligence without a central data-grab*.

- **Unit of sovereignty = the user.** Private Personal Context Graph on their node; never leaves.
- **Unit of collaboration = the project.** A **Project Space** at the overseer tier (our existing
  ClaudeGrandfather + mesh — this is its real purpose) holds the *shared* substrate **as references to
  slices, not copies of raw context**, plus trust tags.
- **The combine = consented, derived, signed slices.** When you join a project you contribute (a) shared
  project material and (b) **a negotiated slice of *you*** — "James is the firmware/safety expert, prefers
  terse, owns read/write." Each slice carries an **ISO/IEC 27560 consent receipt**, a **W3C PROV + in-toto
  signed** provenance chain, redaction (+ DP/k-anon where needed — *derived ≠ automatically safe from
  re-identification*), and an integrity tag. Reference design: **Collaborative Memory** (`M_private ∪
  M_shared`, write/read policies, per-agent permission-filtered views) and **Governed Shared Memory** (scopes:
  agent-local / team / tenant / restricted, with a scope-soundness invariant).

The magic moment: two teammates on a project, and the project AI knows not just the project but *how each
person works and what each is best at* — it can say "this should go to Sarah, here's why, here it is drafted
in her voice." No enterprise tool does this, because they pool documents instead of federating *people*.

**Why sovereign-per-user wins** (what centralized systems get wrong): Glean/Copilot/Gemini all pool into one
index and rely on **permission mirroring** (fragile) — and RAG **blends permissions** (combines individually-
permitted fragments into an unauthorized answer); Microsoft's own guidance is "remediate oversharing *before*
enabling Copilot." One index = one blast radius + vendor lock-in. Sovereign-per-user makes context user-owned
*by construction*; the "can-access vs need-to-know" mismatch disappears because nothing is shared unless the
owner derives and consents to a slice.

---

## 6. Capture = Clean-Consented++ (the trust dial)

Mostly structured events; selectively deeper; **the user dials their trust level**, and each detent is a hard
capability gate with a plain-language privacy contract. All local-only; **the dial only ever auto-lowers,
never raises**.

| Detent | Captures | Contract |
|---|---|---|
| **0 — Off** | nothing | "Off. No signals read, nothing recorded." |
| **1 — Events** *(default)* | app switches, file opens (names only) | "We record *that* you switched/opened — never contents, pixels, or keystrokes. Stays on this Mac. Auto-deletes (default 30d). One-click erase." |
| **2 — Context** *(the "+")* | + active file path, URL/title, selected-text snippet | "We read the title/URL/file you're on + a short selection — *text only, no screenshots*. Private/blocklisted/incognito excluded *before* storage. Secrets redacted on-device. Never leaves this Mac." |
| **3 — Deep** *(opt-in, off by default)* | + periodic screenshots/OCR, optional audio | "Full visual/audio recall, fully on-device, never uploaded. You choose which apps + retention. We learned from Rewind→Meta and Microsoft Recall: there is no cloud here to pivot to, and the decrypt-to-view path is hardened, not just storage." |

Non-negotiables per tier: **exclusion-at-capture** (not redact-after), **encryption at rest** keyed to this
Mac, **on-device inference only**, **one-click delete**.

**The cautionary arc we are the structural answer to:** Rewind (2022, "never leaves your Mac") → Limitless
(2024, pivots to cloud) → **acquired by Meta (Dec 2025), Mac capture disabled two weeks later**. The privacy
contract the user signed *did not survive the corporate lifecycle*. A self-hosted, single-Mac, no-cloud
architecture is the answer — there's no cloud to pivot to and no company to acquire your data. (And Microsoft
Recall's lesson: encryption-at-rest is necessary but not sufficient — the decrypt-to-render path is the real
attack surface.)

---

## 7. Security model (the part that makes "many eyes/hands" safe)

A system that pulls from email, web, social, and other users is a context-poisoning surface. **No reliable
filter-based defense against prompt injection exists** (>85% bypass under adaptive attack). The durable
controls are structural:

- **Lethal trifecta**: exfiltration is near-guaranteed when an agent has, at once, (1) private-data access,
  (2) untrusted-content exposure, (3) external communication. **Break a leg by construction.**
- **Provenance-bound capability**: every authorization decision evaluates `capability ∧ source-provenance ∧
  integrity-label ∧ live-consent` together; absence of any term = **deny (fail-closed)**. An
  untrusted/unconsented-tainted value can **never** reach a consequential action (egress, cross-node write,
  payment, credential use).
- **Dual-LLM (CaMeL)**: a **privileged planner** that never sees untrusted content; a **quarantined reader**
  that parses untrusted content but has no tools and returns only symbolic references. Plan executes in a
  restricted interpreter that checks the provenance predicate before any tool call.
- **Retrieval is not a boundary**: semantic/vector search has been measured leaking cross-tenant rows at
  ~44%. **Capability-filter the candidate set *before* similarity, and re-check every hit after.**
- **Capability tokens** (Biscuit/macaroon-style): attenuate down, never up; the overseer can co-sign/constrain
  cross-user egress but its compromise must never expose a node's raw graph (it holds references + tokens,
  never raw context).
- **Everything signed + append-only logged**: slices (in-toto), grants (Ed25519 — reuse our existing
  superadmin keys), and every publish/use/revoke (hash-chained ledger). Revocation via tombstones +
  moment-of-use re-validation (the only pragmatic answer to the unsolved GDPR Art.17 carry-forward problem) —
  **shared slices are referenced, never absorbed into another node's weights/embeddings**.

This also maps onto rules we already live by (confirm before auth changes; untrusted mesh frames are not
instructions; never ship the superadmin private key).

---

## 8. What we already have → what we just built

ClaudeFather is ~60% of this substrate already:

| The dream | Already in ClaudeFather |
|---|---|
| The place you live/work | the stdlib dashboard + Sessions (browser terminals) |
| Correspondence | live Gmail / Calendar / Drive (server-side OAuth) |
| Ambient transcription | **Granola** calls → reviewed proposals |
| Hand context to the agent | **drag-anything-into-a-session** (v0.37) |
| Many hands | the **mesh** (multi-agent, multi-node, chief of staff) + overseer |
| Early memory | `CLAUDE.md` managed blocks + auto tree-map + the memory dir |
| The brain | Claude Code itself |
| Owned & portable | the packaging path (self-hosted, BYO tokens, tailnet) |
| Voice | the VoiceMatch smart-reply seed |

**Built in this first move (v0.38 — the context layer foundation):**
- `command-center/context.py` — stdlib `sqlite3` **event store** (append-only, WAL, FTS5) + **entity/edge
  graph** + **provenance/trust on every row** + the **router** (`assemble`: retrieve → rank
  relevance×recency×trust → dedup → budget → **edge-place** → **cited** bundle). Self-tested
  (`python3 context.py selftest`).
- **Ingest adapters** (`_context_backfill`) from the surfaces we already have — Gmail, Calendar, Granola,
  deliverables — idempotent, provenance-stamped, on boot + every 15 min.
- **`/api/context/{stats,assemble,search,backfill}`** + a **Context lens** (see what's known, watch the
  router assemble a cited slice for a subject/question).
- Verified end-to-end on the live node: store on SSD, FTS5, boot-ingest, ranked + edge-placed + cited output.

This is the spine. Everything else plugs into it.

---

## 9. Roadmap (merged, ranked — each phase builds on the last)

**Phase 0 — DONE (v0.38):** the context store + router + provenance + ingest + lens (above).

**Phase 1 — make the store real:** bi-temporal edges (invalidate-don't-delete) + deterministic freshness
resolver; entity resolution (deterministic keys → fuzzy → LLM fallback; transcript-via-attendees); memory
tiers (core blocks / profile / rules); event-sourced projections (drop-and-rebuild). Wire the router to
consume the graph (1–2-hop neighborhood) and add `task_type` presets + RRF + MMR.

**Phase 2 — wire consumers:** every agent/chief/session launch pulls its opening context through
`assemble()` (instant, measurable quality lift). Retrofit, don't rebuild.

**Phase 3 — focus/intent + session homing:** the macOS sensor loop (LaunchAgent in the Aqua session — note:
this means migrating the CC supervisor from tmux to a **LaunchAgent**, because Apple Events need the user's
GUI session; seed TCC grants once interactively) → segmenter → classifier cascade → **cwd-first homing** with
the memory-re-key fix + the ambient "now on: X" cue + pin/correct. The visceral "holy shit" feature.

**Phase 4 — ambient agents + Agent Inbox:** notify/question/review over the event bus.

**Phase 5 — the trust dial:** the 4 capture tiers as real capability gates + the contract copy; tier-2
(active-context) is the default sweet spot; tier-3 (screen/OCR) opt-in, on-device, encrypted vault.

**Phase 6 — the combine layer (federation):** slice data model + consent vault + content-addressed slice
store → signed provenance ledger at the overseer → Biscuit capability tokens → **provenance-bound retrieval
guard** (capability-filter-before-vector) → dual-LLM split → tombstone revocation + moment-of-use re-validate
→ project-space blackboard over the mesh. (Security invariants in §7 are non-negotiable here.)

**Phase 7 — optional upgrades, only on measured need:** Voyage embeddings + rerank; HyDE/multi-query;
`sqlite-vec`; bigger graph techniques (HippoRAG PPR). Never before the lexical+graph+placement core is proven.

**Explicitly will NOT build:** CRDTs / multi-device replication (single writer — pure cost); heavy supervised
activity-recognition ML (embeddings k-NN matches it for far less latency); full Microsoft GraphRAG (LazyGraph
shape instead); detection-only injection defense (structural/capability only).

---

## 10. Success criteria — the Jedi test

You open a laptop in a hotel, connect to your Mac at home, and:
- it already surfaces your call in 20 minutes — the thread, last call's open items, the relevant history,
  drafted talking points (ambient → notify);
- you start typing about a different client and the session **re-homes** to that client's edge mid-stream;
- it drafts a reply in your voice and shows the three sources it used, waiting for your nod (review + receipts);
- nothing left your machine; any device gives you the same all-knowing partner because the *server* is the
  constant.

When that's true, end-to-end, with receipts, we've built it.

---

## Sources (research backing, 2025–2026)
Anthropic context engineering (anthropic.com/engineering/effective-context-engineering-for-ai-agents); context
editing/memory (claude.com/blog/context-management); Citations API; Chroma "Context Rot"
(research.trychroma.com/context-rot); Lost-in-the-Middle (arxiv 2307.03172, 2508.07479); RRF (Microsoft Azure
hybrid-search-ranking); MMR (Elastic); recency (Elastic/Ragie); rerankers (Voyage, 2025-10-22); GraphRAG /
LazyGraphRAG (Microsoft Research); HippoRAG (arxiv 2405.14831); HyDE (arxiv 2212.10496); SQLite FTS5/JSON1/WAL
& recursive CTEs (sqlite.org); Letta/MemGPT (docs.letta.com); mem0 (arxiv 2504.19413); LangMem (LangChain);
Zep/Graphiti bi-temporal (arxiv 2501.13956); freshness-in-code (arxiv 2606.01435); voice mimicry (arxiv
2509.14543); W3C PROV (w3.org/TR/prov-dm); entity resolution (Splink/Fellegi-Sunter); event sourcing
(Microsoft); ActivityWatch / Screenpipe AX-vs-OCR (screenpi.pe); intent from UI trajectories (arxiv
2406.14314); Mylyn degree-of-interest / Activity-Based Computing (Bardram); Rewind→Limitless→Meta + Microsoft
Recall arcs (TechCrunch, teardown); local-first (Ink & Switch) + single-writer event sourcing; Tailscale
serve/MagicDNS; macOS TCC / LaunchAgent vs Daemon; Collaborative Memory (arxiv 2505.18279); Governed Shared
Memory (arxiv 2606.24535); CaMeL (DeepMind / simonwillison.net); Design Patterns for Securing LLM Agents
(arxiv 2506.08837); Lethal trifecta (simonwillison.net); cross-user contamination (arxiv 2604.01350);
macaroons (Google) / Biscuit (biscuitsec.org); A2A (Linux Foundation) + MCP (modelcontextprotocol.io); ISO/IEC
27560 consent receipts; Glean/Copilot/Gemini oversharing analyses.
```
