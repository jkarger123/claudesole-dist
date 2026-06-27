# Update / Upgrade subsystem — the fleet's anti-drift backbone

This folder is the **home + documentation of how a ClaudeFather node gets new framework code**, reliably,
without a human having to remember to push to each node. If you are about to touch how updates propagate,
read this first, then `UPGRADE_SYSTEM.md` (the full design + rationale).

> **The one-line contract:** every tenant node converges to the latest published framework **on its own**.
> Nobody has to notice, remember, or hand-push. New nodes inherit this the moment they boot. shipping a
> release is "push the dist"; the fleet pulls itself current.

## Why this exists (the failure it kills)

Updates used to be 100% push-by-hand from Mission Control: ship core → sync the public dist mirror → push
the mirror → `superadmin-send cc_update` + `restart` to **each node, named individually**. Any node not
named in that ritual silently rotted. `shopos` sat **39 minor versions behind (0.28 vs 0.67)** for exactly
this reason — it was reachable and healthy, just never *named*. Detection existed (the Fleet-drift lens knew
shopos was behind) but was **decoupled from action** — knowing didn't fix anything.

## The two convergence paths (both idempotent, both version-gated)

The code lives in `../server.py` (search `AUTO-UPDATE: the anti-drift backbone's ACTION half`). This folder
documents it; it doesn't contain the engine (engine stays in the single stdlib server so it ships as one unit).

### (A) PULL — every tenant self-updates  ← *this is the guarantee*
- `_autoupdate_loop()` runs on every node: ~150s after boot, then every `auto_update_check_min` (default 30) min.
- `_autoupdate_tick()`: probe the canonical latest version (raw manifest from the **public dist git repo**,
  no clone) → if this node's manifest version is older → overlay the latest framework with
  `cc-update.sh <git-url>` (a real `git clone --depth 1`, so freshness never depends on a local mirror) →
  self-restart **when quiescent** (no session mid-turn), or force after a 2h grace so an always-busy node
  still converges.
- **Source nodes self-skip** (`_is_update_source()`): the authoring checkout (git remote → `claudesole-core`)
  and the dist mirror itself never self-update — that would overwrite in-progress edits with the published copy.

### (B) PUSH — Mission Control converges the fleet  ← *operator override + backstop*
- `fleet_converge(force=False)`: refresh the local dist mirror (`git pull`), then for every **behind** tenant
  (or all, if `force`) drive `superadmin cc_update` (from the fresh mirror) + a **separate** safe `restart`.
- Co-located source nodes (same `CC_HOME` as MC) are always skipped — a push can never clobber the checkout.
- `_fleet_converge_loop()`: MC-only periodic sweep (default 3h) that catches any node that couldn't self-update
  (offline at release, self-update disabled). Belt-and-suspenders on top of path A.
- UI: **Change Requests lens → 🛰 Fleet drift → "⬆ Update all behind" / "⟳ Force all"**. This is detection
  finally wired to action.

## Config knobs (cc.config.json — all optional, safe defaults)

| key | default | meaning |
|---|---|---|
| `auto_update` | `true` | tenant self-update on/off |
| `auto_update_check_min` | `30` | minutes between self-checks |
| `auto_update_restart` | `true` | self-restart to apply, vs. stage-and-wait |
| `auto_update_restart_grace` | `7200` | seconds before a busy node force-restarts to converge |
| `update_source` | public dist git URL | where this node pulls framework from |
| `update_manifest_url` | derived from `update_source` | cheap "latest version" probe |
| `update_role` | (auto) | set `"source"` to force a node to never self-update |
| `fleet_auto_converge` | `true` | MC backstop sweep on/off |
| `fleet_converge_min` | `180` | minutes between MC sweeps |

## APIs

- `GET /api/update-status` — this node's posture (version, latest, behind?, source?, last check, msg).
- `POST /api/update-now` — force this node to self-check + self-update immediately.
- `POST /api/autoupdate {on}` — toggle this node's self-update (persists to cc.config, live).
- `POST /api/fleet-update {force}` — **MC**: converge the whole fleet now.
- `GET /api/ccr-drift` — the per-node version/drift report the UI + converger read.
- Log: `<state>/_autoupdate.log` (applies, restarts, MC converges, errors).

## Invariants — do not break these (each caused or would cause a real outage)

1. **Source nodes NEVER self-update or get pushed to.** The authoring checkout is the source of truth; pulling
   the published copy over it destroys uncommitted work. Detection is portable + host-agnostic (cc.config
   `update_role:"source"` → `.cc-source` marker → is-the-dist-dir → git-remote heuristic), and `fleet_converge`
   also skips any node sharing MC's `CC_HOME`. A fresh/downloaded tenant matches none → it self-updates.
2. **Restart for OTHER-user nodes is the SEPARATE `restart` superadmin action**, never `cc_update` with
   `restart:true`. AFP runs as user `sarahaios`; MC must not tmux-kill it. `fleet_converge` always does the
   two-call form.
3. **Self-restart only when quiescent** (or after the grace backstop) — never interrupt an agent mid-turn.
4. **`cc-update.sh` overlays FRAMEWORK paths only** (manifest `framework_paths`); `preserve_paths`
   (cc.config/secrets/peers/state) are never touched. Self-update relies on this — it must stay true.
5. **The manifest `version` is the only truth.** The legacy `VERSION` file is written only at package time and
   lies (AFP shows 0.2.0). Compare manifest versions, nothing else.
6. **Adding a new node = zero update wiring.** If it boots the framework with `auto_update` defaulting on, it
   converges itself. Don't reintroduce a hand-maintained per-node push list as the *primary* mechanism.

## Releasing (what shipping a version now means)

Author at Mission Control → bump manifest + CHANGELOG → restart local nodes → push core → **push the public
dist mirror**. That last push is the whole job: within `auto_update_check_min`, every tenant pulls itself
current and restarts when idle. For an immediate converge, hit **Update all behind** (or `POST /api/fleet-update`).
Full step-by-step incl. the cross-user AFP specifics: root `CLAUDE.md` → "SHIP AN UPDATE TO THE WHOLE FLEET".
