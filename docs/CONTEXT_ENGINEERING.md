# ClaudeFather — Context Engineering (how agents get exactly what they need, no more)

The discipline of giving every agent the right context at the right time — enough to act, little enough to stay
fast and cheap. This documents the model, the SOTA principles it embodies, and the invariants that keep it
efficient as projects grow. Goal: any project inside a ClaudeFather instance reads as "amazingly laid out" even
when the operator never consciously organized it.

## The model (layered, retrieval-first)
1. **Cascading CLAUDE.md tree** — the spine.
   - `CC:CHILDREN` (each folder's CLAUDE.md auto-lists its DIRECT sub-tools + one-line summaries; `regen_children`).
   - `CC:TREEMAP` (the ROOT CLAUDE.md carries the FULL recursive map, capped ~160 lines; `regen_treemap`). Since a
     session at ANY depth auto-loads the root, every level inherits a compact "what exists + where" without
     loading every doc. Source of truth = the live filesystem, so it can't drift.
   - `CC:NOTES` (append-only, per-module learnings — durable knowledge lands in the module it belongs to).
   - Each layer therefore knows its children, and the root knows the whole tree → orientation from anywhere.
2. **Budget discipline** — Doctor flags any CLAUDE.md over **220 lines** ("slim to an index + pointers") and flags
   a deep doc carrying a managed block it shouldn't. CLAUDE.md is an INDEX that points to detail, never a dump.
3. **Retrieval over preload** — the CONTEXT LAYER (`/api/context/assemble`, `/api/context/brief` "catch me up")
   assembles a CITED slice for a subject on demand, instead of front-loading everything. Completeness lives in
   the store; only a curated slice enters the window.
4. **Per-node-clean tool awareness** — agents are told about the tools that ACTUALLY exist here, tiered:
   - **ENABLED** extensions → full `AGENT.md` usage docs (`_ext_agent_context`; capped 1600 chars × 20).
   - **AVAILABLE but not enabled** → a tiny id+summary pointer so the assistant knows the capability exists and
     can offer to enable it, WITHOUT paying for docs it can't use (`_ext_available_brief`; Chief-only).
   - A node never hears about an extension it doesn't have (a node without Skimlinks gets zero Skimlinks context).
5. **Self-organizing structure** — launch into an undocumented folder and the agent MUST create a CLAUDE.md (H1
   title + one plain sentence) so the folder becomes a recognized, previewable layer (`_NEW_FOLDER_BRIEF`).
6. **Right-place output** — agents place deliverables under the module the work BELONGS to (found via the root
   Module map), not merely where they were launched; new tools/areas get their own CLAUDE.md + CC:NOTES
   (`_files_brief`). So even an agent started in the wrong place leaves a clean, navigable tree.

## What gets injected, where (the briefs — kept minimal + targeted)
- **Chief of Staff** (`_system_brief`): system map + runtime + secrets/secure-fields + `_files_brief` (placement) +
  `_extend_brief` (locked core / how to extend) + ENABLED tool docs + the tiny AVAILABLE tier. The general
  assistant gets the fullest picture.
- **Scoped agent-tools** (`agent_open`): their own charter (CLAUDE.md) + `_files_brief` + `_extend_brief` + the
  roster. Lean: NOT the marketplace-available tier (a focused tool doesn't need the whole catalog).
- **Plain project sessions** (`launch`): open into the project and read CLAUDE.md (which carries the treemap) +
  the per-folder children — i.e., the tree IS the context; no heavy inline brief.

## SOTA principles this embodies
- **Progressive disclosure**: a MAP everywhere + detail on demand (open the specific CLAUDE.md/AGENT.md), never a
  full dump. - **Just-in-time retrieval**: the context router assembles per-subject. - **Right-sized by role**:
  the Chief gets breadth, scoped agents get depth-on-their-job. - **Provenance + stable anchors**: managed
  CC:BEGIN/END regions, cited slices. - **Self-maintaining**: the map regenerates from the filesystem; budgets
  are enforced by Doctor. - **Locality of knowledge**: learnings file to the module they concern (CC:NOTES), so
  context stays where it's relevant instead of bloating a global doc.

## Invariants (keep these true)
- CLAUDE.md = index, not dump (≤220 lines; Doctor enforces). Detail lives in sub-docs / deliverables / the store.
- Inject by RELEVANCE + ROLE: don't add to a brief unless an agent in that role needs it for the task at hand.
  Prefer a pointer ("X exists / read Y") over inlining content.
- Per-node-clean: never tell an agent about a tool/extension this node doesn't have enabled.
- New structure is self-describing: every meaningful folder has a CLAUDE.md (title + one-line summary); durable
  learnings go to that module's CC:NOTES.
- The map is generated, never hand-maintained (CC:CHILDREN/CC:TREEMAP regenerate from the filesystem).

## Audit / how to check efficiency
- `GET /api/doctor` → over-budget docs, managed-block drift, components missing a CLAUDE.md.
- The root CLAUDE.md's CC:TREEMAP should be current + within the line cap (it self-regenerates; `regen_treemap`).
- A new module should appear in its parent's CC:CHILDREN + the root CC:TREEMAP automatically after it gets a
  CLAUDE.md. If briefs grow, ask: does every agent in this role need this for the task? If not, make it a pointer.
