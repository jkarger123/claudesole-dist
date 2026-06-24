# Root CLAUDE.md slim-down plan (PROPOSAL -- human-gated; do NOT auto-apply)

The hptuners project root `CLAUDE.md` (`/Volumes/Samsung990PRO/hptuners/CLAUDE.md`) is ~2,500 lines and is
loaded into context **every single turn** of every hptuners session -- ~12x the official ~200-line ceiling.
That is a real, permanent token tax. Run `/claude-md-lint` to see the live size.

This is a PLAN only. The cutover edits a load-bearing doc, so they happen **only on your explicit approval**
(and ideally one section at a time, verified). Nothing here has been applied.

## Target shape (lean index, < ~200 lines)
Keep at the root, as a terse index:
- One-paragraph "what this is / where you are" (project vs runtime vs Windows-dispatch).
- Build/test/deploy entry commands + the fleet (Studio / T490 / T480).
- The SHORT list of the few always-true hard rules (1-2 lines each) + a pointer to the full text.
- The "looking for X -> pillar" jump table (it's already useful + compact).
- `@import`s / links to the detail (below).

## Where the heavy content moves (and why it's safe)
1. **The HARD RULE deep-dives** (ASCII-only; lis_base signed-16; VLE encoder/silicon; Mongoose Write
   Entire; v5 runtime; Channels E/U/L/P/I) -- these are the bulk. Move each into
   `.claude/rules/<rule>.md` with `paths:` frontmatter so they load ONLY when Claude touches the relevant
   pillar (e.g. `patches/**` for the brick-gate rules). Keep a 1-line summary + link at root.
   - Net effect: a session working in `text2tune/` no longer pays for 1,500 lines of patches brick-gate rules.
2. **Pillar status tables / per-pillar detail** -- already belongs in each pillar's `CLAUDE.md` (lazy-loaded
   when you work in that pillar). Root keeps only the pillar list + one-line status each.
3. **The HYBRID pipeline / migration narratives / OPSEC term tables** -- move to dedicated docs
   (`docs/HYBRID_EDITOR_PIPELINE.md` already exists; OPSEC -> `docs/OPSEC.md`) and `@import` or link them.
4. **The "looking for X" + rollback + remote-machine sections** -- keep (compact + high-value), or move
   rollback/remote to `docs/` and link.

## Sequenced cutover (each step independently revertible; gate each)
1. Extract ONE rule (e.g. the v1 lis_base rule) to `.claude/rules/patches-brick-gate.md` with
   `paths: ["patches/**"]`; replace the root block with a 2-line summary + link. Verify a `patches/` session
   still sees it and a `text2tune/` session no longer loads it. (A sample extracted rule file ships with
   this plan as proof-of-shape: see below.)
2. Repeat per hard-rule block.
3. Move pillar-detail blocks into the pillar CLAUDE.mds (verify each pillar still reads correctly).
4. Re-run `/claude-md-lint`; confirm root < ~200 lines.

## Proof-of-shape: a sample extracted rule
A path-scoped rule file looks like this (this is the SHAPE the brick-gate rules would take):

```markdown
---
paths: ["patches/**", "read_write/bench/**"]
---
# Pre-flash gate is load-bearing (v1 EA-overflow / v2 VLE / v3 Mongoose / v5 runtime / Channels E-U-L-P-I)
- NEVER bypass the gate or add a --gate-exempt flag. NEVER default the BDM-ack flag to True.
- Full deep-dives: patches/CLAUDE.md + the brick-postmortem capstones.
```

## Risk / why gated
The root CLAUDE.md is the single most load-bearing doc in the tree; many sessions + the brain depend on its
exact rules being in context. Path-scoping is correct but means a session OUTSIDE a scoped path no longer
sees that rule -- which is the point (those rules only matter inside those paths), but it must be verified
per rule. Hence: human-approved, one section at a time. Recommend doing it as its own small Ralph loop or
a focused session, NOT inline with other work.
