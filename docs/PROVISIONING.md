# Provisioning — "Add a ClaudeFather"

How a brand-new ClaudeFather instance is born: from the **➕ Add a ClaudeFather** button in the overseer
Portfolio lens, to a self-contained, running node. This is the canonical, supported way to stand up a new
instance — do not hand-craft a bundle.

## The shape we provision: a self-contained, portable bundle
Every new instance is **one movable folder** (its own `CC_HOME`) holding everything it needs:

```
claudefather-<id>/
  command-center/        # the full engine (server.py + helpers) — its OWN copy
  agents/  extensions/  presets/  docs/  install/  bin/  data/
  cc.config.json         # THIS node: port, instance_id, role, brand, secrets   (chmod 600)
  peers.json             # mesh peers (the family)                              (chmod 600)
  superadmin.pub         # the owner's PUBLIC key (verify-only; never the private key)
  launchd/com.claudefather.<id>.plist   # staged, not loaded (operator installs it)
  project/               # the project this node operates on (inside the bundle = portable)
  deliverables/          # files the node produces (deliverables_root points here)
  claudesole.manifest.json  VERSION
```

Because the project and deliverables live **inside** the bundle and the supervisor finds its own
`command-center`, you can pick the whole folder up, drop it on a dedicated drive or a new server, and
re-run the launch line with the new path. Nothing is hardcoded to the original location.

## The pieces
- **Engine — `cc-newinstance.sh`** (framework root). The deterministic builder. The agent and the UI both
  drive *this*; it owns the layout so every node stays portable + updatable.
- **Agent — `agents/provision/CLAUDE.md`**. The "fluent" brain: turns a design plan (plain language or a
  form) into the right `cc-newinstance.sh` invocation, runs the approval gates, joins the mesh, verifies.
- **UI — Portfolio → ➕ Add a ClaudeFather** (overseer only). Wizard: Preview plan → Stage bundle →
  Stage & launch. Backed by `POST /api/instance-provision` (`instance_provision()` in server.py).
- **Supervisor — `command-center/cc-instance-supervise.sh`**. The launchd entrypoint; derives its own
  bundle dir so a relocated bundle runs its own `server.py`.

## What the engine does (and does NOT do)
On `cc-newinstance.sh --id <id> --dest <dir> [flags]`:
1. Validates id (sanitized to `A-Za-z0-9_-`), dest (must be empty), preset, and a free port (auto ≥ 8800).
2. Copies every `framework_paths` entry from the source install into the bundle (preserve paths excluded
   by construction — no secrets/state copied).
3. Writes `cc.config.json`: name/brand/role/preset/port/instance_id, `deliverables_root` inside the bundle,
   a **fresh** dashboard `auth_token`, and the **family `mesh_token`** carried from the parent (so the node
   joins this family's mesh). chmod 600.
4. Seeds `peers.json` from the family, ships `superadmin.pub` (verify-only).
5. Stages a launchd plist (does **not** load it), makes a starter `project/CLAUDE.md`, and registers the node
   in the parent's `_instances.json` so it appears in Portfolio.

It **never** starts the server, loads launchd, or registers itself into other nodes' peers — those are the
operator-approved steps (printed at the end; `--json` also emits a machine-readable summary).

### Flags
`--id` (req) · `--dest` (req) · `--name` · `--brand` · `--preset project|overseer` · `--port` ·
`--storage github|icloud|icloud+github` · `--agents a,b,c` · `--project-root` · `--user` ·
`--json` (machine summary) · `--dry-run` (plan only, writes nothing).

## The flow, with approval gates
1. **Preview** — wizard "Preview plan" / `--dry-run`: shows exactly what will be created. Confirm.
2. **Stage** — builds the bundle. Still nothing running. The new dashboard `auth_token` is shown once
   (store it — it's a brand-new node's initial credential, not a change to an existing one).
3. **Launch** (gate) — brings it up on the **brain tmux server** (required for SSD/TCC access; bare launchd
   EPERMs on `/Volumes/...`) and verifies the port answers `401` (alive + auth on).
4. **Persist** (gate, operator's hands) — a per-user LaunchAgent only runs when that user has a live login
   session. Install it **as the hosting user**:
   `cp <bundle>/launchd/com.claudefather.<id>.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.claudefather.<id>.plist`
   (Agents have no TTY → pre-type into the Admin shell per `SESSIONS_AND_SUDO.md`.)
5. **Mesh** (gate) — to let the *other* nodes reach the newcomer, append
   `{"id":"<id>","url":"<tailnet-or-127.0.0.1:port>"}` to each family node's `peers.json`.

## Security invariants
- New node carries the **family** mesh token and gets a **fresh** auth token. The fresh token is printed
  once; the family/mesh token is **never** echoed.
- Only `superadmin.pub` ships — the MC-only Ed25519 **private** key never enters a bundle.
- Never change an **existing** node's `auth_token`/`mesh_token` during provisioning.
- Default bundles to the **SSD**, never the near-full internal disk.
- The endpoint is **overseer-only** (`role == "org"`); project nodes return 403.

## Extending it
If a need can't be expressed as a `cc-newinstance.sh` flag, extend **that script** (a framework change —
via CCR if you're on a tenant). Never scaffold instance files by hand; that breaks portability + cc-update.
