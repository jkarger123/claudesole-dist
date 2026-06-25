# presets/ — role lens/agent bundles (ClaudeFather vs ClaudeGrandfather tiers)

This dir holds the **preset bundles** that decide which nav lenses (and which agent roster)
a Command Center instance runs, based on its tier. One JSON per preset; the server reads the
file named `<PRESET>.json` and the frontend filters the nav to that lens list.

## What this IS
A preset = a named bundle of `{ role, description, agents[], lenses[] }`. It expresses the
two deployment **tiers** of the platform:

- **`project.json` — ClaudeFather (`role: "project"`)** — operates ONE project: its modules,
  sessions, security, backup, usage, ideas, routines, etc. The full operator surface (~24 lenses).
- **`overseer.json` — ClaudeGrandfather (`role: "org"`)** — a pure **overseer / portfolio** of
  child ClaudeFathers. Aggregates status/cost/security across projects and drills into each; does
  NOT operate a single project. Leaner lens set, headed by the **Portfolio** lens. Mission Control
  is the canonical overseer (it is also the platform authority — see root CLAUDE.md).

## How it WORKS (the selection + filter path, all in `command-center/server.py`)
1. `ROLE = CC.get("role") or "project"` — from the instance's `cc.config.json` (`"project"` | `"org"`).
2. `PRESET = CC.get("preset") or ROLE` — preset defaults to the role, but can be overridden
   per-instance to run a custom bundle without changing the role.
3. `render_page()` loads `presets/<PRESET>.json`, pulls `.lenses`, and injects it as
   `window.CC.lenses` (alongside `role`, `preset`, etc.). Missing/invalid file → `lenses=null` → no filtering.
4. Frontend `applyPreset()` (in the embedded PAGE, ~line 12195): hides any nav button whose
   `data-l` is NOT in `window.CC.lenses`, then lands on `lenses[0]` (Portfolio for an overseer,
   Sessions for a project).
5. `SCOPE_SESSIONS` derives from role too: `CC.get("scope_sessions", ROLE != "org")` — projects
   see only their own sessions; an org sees the whole box unless it opts back in.

## Lenses that escape the preset list (self-show/hide independently in `applyPreset()`)
The preset list is the BASE, but several lenses are toggled by capability flags, overriding it:
- `agency` / `calls` — only when `window.CC.agency` (agency-shaped tree).
- `pipeline` — only when a pipeline manifest is present (`window.CC.pipeline`).
- `gmail` / `calendar` / `drive` — only when the google-workspace extension has a token (`window.CC.google`).
- `accounts` — only when the Claude account wallet is enabled (`window.CC.accountWallet`).
- `tasks` — always on (built-in feature, intentionally NOT in any preset list).
- `portfolio` — force-hidden unless `role==='org'` (ClaudeGrandfather only), even if listed.

## Key files / where things live
- `presets/project.json` — ClaudeFather bundle (role `project`).
- `presets/overseer.json` — ClaudeGrandfather bundle (role `org`).
- `command-center/server.py`:
  - `ROLE` / `PRESET` / `SCOPE_SESSIONS` resolution (~L46–51).
  - `render_page()` loads the preset + injects `window.CC.lenses` (~L128–132).
  - `applyPreset()` nav filter + capability overrides (~L12195–12207).
  - `FW_FINGERPRINT_FILES` lists both preset JSONs as **framework files** (~L6189).
- Per-instance config: each deployment's `cc.config.json` (sets `role` / optional `preset` / `scope_sessions`).

## Hard rules / gotchas
- **These are FRAMEWORK files** (in `FW_FINGERPRINT_FILES`). Per the platform governance, nodes do
  NOT edit framework files locally — change them at Mission Control and ship via dist + `cc-update`,
  or route a Core Change Request (Propose Change lens). Editing here on a node shows as "drifted".
- A lens listed in a preset still won't render if there's no nav button with that `data-l`, and a
  capability-gated lens (agency/pipeline/google/accounts/portfolio) ignores the preset list per the
  overrides above. To actually surface such a lens you need both the preset entry AND the flag.
- `preset` is decoupled from `role`: setting `preset` to a non-existent file silently yields no
  filtering (all built nav buttons show). Keep `<PRESET>.json` present.
- `lenses[0]` is the LANDING lens — order matters (overseer leads with `portfolio`, project with `sessions`).
- The `agents[]` arrays describe the role's intended scoped agent-tools; the live Agents lens is
  filesystem-driven (`agents/` dirs), so keep these in sync conceptually but the dir is the source of truth.

## How to extend
1. **New lens for a tier:** add its `data-l` string to the relevant preset's `lenses[]` (and ensure
   a nav button + handler exist in the PAGE). Then restart via the claudesole-restart flow.
2. **New preset/tier:** add `presets/<name>.json` with `{role, description, agents, lenses}`, add it
   to `FW_FINGERPRINT_FILES`, and set `"preset": "<name>"` in a node's `cc.config.json`.
3. **Capability-gated lens** (should self-hide): wire it in `applyPreset()` like agency/google rather
   than relying solely on the preset list.
4. Do all of the above as a framework change at Mission Control / via CCR, then ship — don't hand-edit on a node.
