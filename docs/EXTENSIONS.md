# ClaudeFather — the Extension System (canonical reference)

This is the end-to-end reference for how ClaudeFather extensions are defined, authorized, installed, run, and
sandboxed. It is the source of truth for "what is an extension, what can it do, and what is allowed to run."
Authoring standard (build-to-this): `../extensions/AUTHORING.md`. Engine: `../command-center/server.py`
(extension section). Catalog: `../extensions/`. Per-deployment install state + secrets are PRESERVE/gitignored.

## 1. What an extension is
A directory `extensions/<id>/` whose `extension.json` declares a capability the operator can install from the
Marketplace lens. One promise: install it, a setup agent walks the operator through everything, and agents on
that node learn how to use it — but ONLY where it is installed (per-node-clean).

## 2. Categories
- **integration** — an MCP server / external service (ships `mcp.json`; install merges into `.mcp.json`).
- **agent-tool** — a scoped agent (`payload/agents/<id>/`; install copies to `AGENTS_DIR/<id>/`).
- **skill** — a Claude Code skill (`payload/SKILL.md` → `<scope>/.claude/skills/`).
- **theme** — a `data-theme` palette (cosmetic; no data/secrets).
- **agency / lens** — a dashboard lens configured via `cc.config` (e.g. granola → Calls).
- **(forward) programmatic** — pure code via `functions{}` with declared `inputs[]`/`outputs[]` (no agent).

## 3. The `extension.json` schema (every field)
Required: `id` (==dir, `[a-z0-9-]`), `name`, `category`, `version`, `icon`, `summary`, `description`,
`setup_doc`, `default_category`.
Common: `provides[]` (informational capability tags), `requires[]` ({key,label} secrets the user must supply),
`setup_agent` (bool), `agent_doc` (AGENT.md), `draggables[]` ({kind,label,note}), `lens` ({id,label,icon} — the
OBJECT is what surfaces a nav tab; `provides:["lens:x"]` is informational only), `functions{}` (server-side
compute), `tier`/`pricing`/`publisher` (paid gate), `launch_group`/`launch_points[]`, `byok` (per-account keys).
Forward-looking (programmatic): `inputs[]`, `outputs[]` (§7).
`default_category` ∈ {Google, Workspace, Agency, Team, Integrations, System} — which collapsed nav folder the
lens lands in (surfaced via `_ext_lenses().category`).

## 4. Authorization — only official or approved-custom extensions run
The guarantee: a tenant/appliance can never load an extension we didn't ship (or the operator didn't approve).
`_ext_authorized(id)` → `official` | `custom` | `None`:
- **official** — the extension's `extension.json` is in the MC-**signed** `core.sig.json` (verified on every
  node against `superadmin.pub`; forging needs the MC private key, which lives only at Mission Control). An
  AUTHORING node trusts its own catalog (it signs before shipping).
- **custom** — under `custom/extensions/<id>/` on a **developer-type** node AND in `custom/_approved.json`
  (operator-approved). Runs only in the restricted sandbox runtime; clearly marked unofficial.
- **None (unauthorized)** — refused at install; skipped by every loader (lens, agent-context, functions); a rogue
  dir under `extensions/` is **quarantined** (moved to `_quarantine/`, reversible, never deleted) on an appliance
  and raised in Doctor. This is the only place "non-core" tools are blocked from running.
Enforcement points: `extension_install`, `_ext_lenses`, `_ext_agent_context`, `_ext_fn_run`, the integrity loop
(`_ext_quarantine_rogue`), and Doctor (`_ext_unauthorized`). The Marketplace shows each item's `authorized` state.

## 5. The custom sandbox (where users build) — developer-type only
- Location: `custom/extensions/<id>/` under `DEPLOY_ROOT` (writable on a read-only-core appliance; PRESERVE;
  NEVER signed or shipped). It is the ONLY place non-official tools may live.
- Scope: **programmatic functions only** — sandboxed `functions{}` with declared `inputs[]`/`outputs[]`. No
  lens / agent-tool / MCP, no core secrets. (Restricted runtime: only declared secrets, timeout + CPU/file/mem
  limits, path-confined entry, audited.)
- Gate: the operator must **approve** a custom extension before it runs (recorded in `custom/_approved.json`);
  only `type:developer` nodes may build/run custom extensions. (Approval flow + runtime: Ship B.)

## 6. Standardized installs — `type` and `edition`
Every install is identical except two axes + which extensions are installed:
- **`type`** (cc.config `type`): `agency` (official-only + the Clients/Tools tree) | `developer` (may build +
  run approved custom extensions). Default `agency`.
- **`edition`** (authority, separate): `authoring` (Mission Control — signs core, mints grants/licenses) |
  `appliance` (shipped node — read-only core, self-heals, enforces authorization + license).

## 7. Programmatic I/O — the deliverable contract (forward-looking)
`inputs[]` declares what the extension consumes; `outputs[]` declares what it produces and WHERE it goes. The
platform renders the input form, runs the function, and routes the deliverable.
- input `type`: file | files | text | number | select | boolean | secret | session | extension; with
  `accept`/`from`(upload|deliverable|drive|vault|basket)/`required`/`options`.
- output `type` (OPEN, extensible registry — we are the official builder of new destinations):
  `deliverable` (file in `deliverables/`) · `inline` (render in its lens) · `download` · `email` · `telegram` ·
  `slack` (outward — ALWAYS review-gated via the action queue, never auto-sends) · `agent` (drop the file into a
  live Claude session, like a Basket item) · `extension` (chain into another extension's input — programmatic
  pipelines) · `webhook` · `tree` (write into the project tree) · `vault`.
The FIELDS are standard now so extensions are built forward-compatible; the routing ENGINE lands in Ship B.

## 8. Lifecycle
Install → `_ext_wire_mcp` (integration) / `_ext_apply_payload` (agent-tool, skill, theme) → `_ext_register_routine`
(if declared) → `_ext_declare_secrets` (reserve vault slots). Uninstall is reversible (MCP entries removed;
payloads archived to `_archive/`; accounts/keys never touched). Setup = a guided `claude` agent briefed by SETUP.md.

## 9. Audit posture (how to verify conformance + cleanliness)
- Catalog conformance: every `extension.json` has the required fields + `SETUP.md` + `AGENT.md` (theme/skill
  exempt) + a real `lens` object wherever it provides a lens + `default_category`.
- A node is clean iff: its `extensions/` matches the signed dist (core integrity `clean`), its installed list is
  all `_ext_authorized`, and Doctor reports no `extensions` issues. Run Doctor (`/api/doctor`) and
  `GET /api/extensions` (`unauthorized` block) to confirm.
