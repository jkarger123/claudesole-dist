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

## The flow (self-completing — the operator shouldn't need Mission Control)
The wizard checkbox **"Make it permanent & join the mesh"** (default on) means **Create & start** finishes
the node end-to-end; the operator's only remaining job is to open it and run its **Setup agent**.
1. **Preview** — wizard "Preview plan" / `--dry-run`: shows exactly what will be created. Confirm.
2. **Create** — builds the bundle. (📦 "Create (no start)" stops here.) The new dashboard `auth_token` is
   shown once (store it — a brand-new node's initial credential, not a change to an existing one).
3. **Start** — 🚀 brings it up on the **brain tmux server** (required for SSD/TCC access; bare launchd EPERMs
   on `/Volumes/...`) and verifies the port answers `401` (alive + auth on).
4. **Persist (automatic, same-user)** — `instance_provision()` installs the per-user LaunchAgent server-side
   (`launchctl bootstrap gui/<uid>`) so it survives reboot. For a **cross-user** host (e.g. AFP on
   `sarahaios`) it can't (a per-user agent needs that user's login session) → it reports the one command to
   run as that user (pre-type into the Admin shell per `SESSIONS_AND_SUDO.md`).
5. **Mesh + remote access (automatic)** — the new node is published on the **tailnet** via
   `tailscale serve --https=<port> http://127.0.0.1:<port>` (same as the other nodes), and that
   `https://<tailnet-host>:<port>` URL is registered in the Portfolio registry + `peers.json`. Without this a
   node sits at `127.0.0.1:<port>` — reachable only ON the host machine, so the Portfolio link would fail from
   a phone/laptop. Falls back to local-only (with a warning) if tailscale isn't present.
6. **Setup agent** — open the new instance and run **Agents → setup**: a guided walkthrough that configures
   the project (purpose → CLAUDE.md scaffold from a pasted spec → agents → extensions → first goals), then
   hands off to the instance's Chief of Staff. This is where a node goes from "running" to "useful."

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
