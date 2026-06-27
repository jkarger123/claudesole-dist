# ClaudeFather — Enterprise Upgrade System (design + operations)

Status: **shipped v0.68.0** (2026-06-27). This is the authoritative spec for how framework code reaches every
node. Companion: `CLAUDE.md` (this folder, the quick contract); root `CLAUDE.md` → "SHIP AN UPDATE TO THE
WHOLE FLEET" (the release ritual). Engine: `command-center/server.py`.

---

## 1. Goals

1. **Convergence is automatic and inevitable.** Every node reaches the latest published framework with no
   human remembering to push to it. This includes nodes Mission Control doesn't actively think about, and
   nodes that don't exist yet.
2. **Newly-provisioned nodes self-converge** from first boot — no post-install update step.
3. **Source-of-truth is protected.** The authoring checkout is never overwritten by an update.
4. **No surprise interruptions.** Auto-restart waits for an idle moment; cross-user nodes restart themselves.
5. **Detection is wired to action.** "Who's behind" has a button that fixes it.
6. **Stdlib + config-driven + secret-clean** — fits the packaged-product north star; no new deps.

## 2. Topology

```
                 authoring (SOURCE — never self-updates)
   ┌─────────────────────────────────────────────────────────┐
   │  /Users/hptuner/hptuners-control  (git: claudesole-core) │
   │   ├─ hpcc (8799)  ├─ overseer/MC (8800)  ├─ carsearch    │  ← share one CC_HOME; all detected as source
   └───────────────┬─────────────────────────────────────────┘
                   │  ship: push core + push PUBLIC dist mirror
                   ▼
        GitHub: jkarger123/claudesole-dist  (PUBLIC)   ◄── canonical "latest"
                   │                         ▲
        local clone │ (MC's mirror for       │ raw manifest probe + git clone --depth 1
        /Users/Shared/claudefather-dist)     │
                   │                         │
   ┌───────────────┴──────────┐   ┌──────────┴───────────────┐
   │ AFP (sarahaios, 8850/8851)│   │ shopos (8802→9802)        │   … and every future tenant
   │  PULL self-update (A)     │   │  PULL self-update (A)     │
   │  + MC PUSH backstop (B)   │   │  + MC PUSH backstop (B)   │
   └───────────────────────────┘   └───────────────────────────┘
```

- **Tenants pull from the PUBLIC dist git URL directly** (path A) — so a tenant's freshness never depends on
  anyone having refreshed the local mirror.
- **MC's local mirror** is used only by the PUSH path (B) for cross-user `cc_update` (where handing a local
  dir to `superadmin cc_update` is cheaper than each tenant cloning). `fleet_converge` `git pull`s it first.

## 3. Path A — PULL (the guarantee)

```
boot ── wait 150s ──┐
                    ▼
        _autoupdate_loop  ── every auto_update_check_min (def 30) ──► _autoupdate_tick
                                                                         │
   _is_update_source()? ── yes ─► skip (authoring checkout / dist mirror)│
        │ no                                                             │
   auto_update == false? ── yes ─► skip                                  │
        │ no                                                             │
   latest = raw manifest version from public dist (no clone)            │
   behind = semver(latest) > semver(local)?                             │
        │ no  ─► "current"                                              │
        │ yes                                                            │
   overlay ONCE: cc-update.sh <git-url>  (git clone --depth 1, framework_paths only)
        │ fail ─► log, leave running, retry next tick                    │
        │ ok                                                             │
   restart:  quiescent (no busy pane)  OR  staged > 2h (grace) ─► _self_restart (os.execv)
             else ─► stay staged, retry next tick (don't interrupt work)
```

Key properties:
- **Idempotent & version-gated** — re-running does nothing once current; overlay happens once per target version.
- **Self-restart is the safe path even for AFP** — the node re-execs *itself*; MC never touches another user's process.
- **Quiescence guard** — `_local_quiescent()` is false if any session shows "esc to interrupt". Grace backstop
  guarantees convergence within ~2h even on a perpetually-busy node.

## 4. Path B — PUSH (override + backstop)

`fleet_converge(force)`:
1. `git -C <mirror> pull --ff-only` — never ship stale.
2. `drift_report()` → for each node:
   - skip self, skip co-located **source** nodes (`home == CC_HOME`), skip unreachable.
   - skip `current`/`ahead` unless `force`.
   - `superadmin cc_update {upstream: mirror}` → on success, **separate** `superadmin restart`.
3. Returns `{mirror, ran:[{id,from,update,restart,error}], skipped:[{id,why}]}`.

Triggers:
- **UI**: Change Requests lens → 🛰 Fleet drift → **⬆ Update all behind** / **⟳ Force all**.
- **API**: `POST /api/fleet-update {force}`.
- **Loop**: `_fleet_converge_loop()` (MC/source only, default every 3h) — catches nodes offline at release.

## 5. Source-node protection (why a push/pull can't eat the checkout)

`_is_update_source()` returns true when ANY of:
- `cc.config update_role == "source"` (explicit), or
- `CC_HOME` is the dist mirror dir, or
- `git -C CC_HOME remote -v` mentions `claudesole-core` (the private authoring repo) or `hptuners-autonomous`.

The three local nodes share `/Users/hptuner/hptuners-control` (remote = claudesole-core) → all auto-detected
as source → they never self-update, and `fleet_converge` skips them via the `home == CC_HOME` test. Tenants
(AFP, shopos) are not that repo → they self-update normally.

## 6. Bootstrap note (one-time, by design)

The self-updater is *new code*. A node already running OLD code (shopos @ 0.28, AFP @ 0.67 pre-this-release)
has no self-updater yet, so it can't self-converge to the release that first contains it. That first hop is
done once via PUSH (`Update all behind` / `fleet_converge`). After a node is on a self-updater-bearing
version, path A keeps it current forever. **This is the only time a human-initiated push is required**, and
it's a single fleet-wide action, not per-node.

## 7. Adding a node (the zero-wiring promise)

A provisioned node ships with `auto_update` defaulting on and `update_source` defaulting to the public dist.
On first boot it probes, finds itself at-or-behind, and converges. The only registry that still needs the
node is `peers.json` on MC — and that's only for the PUSH backstop + drift visibility, **not** for the node
to keep itself current. Do **not** rebuild a hand-maintained per-node push list as the primary mechanism.

## 8. Failure modes & how the design absorbs them

| failure | absorbed by |
|---|---|
| Operator forgets a node | Path A: it self-updates regardless |
| New node nobody registered | Path A: converges on its own boot |
| Local mirror stale | Path A clones the public repo directly; Path B `git pull`s before pushing |
| Node offline at release | Path A next tick + Path B backstop sweep |
| Node always busy | grace-window force restart (≤2h) |
| Cross-user restart (AFP) | self-restart via superadmin `restart`, never tmux/`restart:true` |
| Auto-update would eat dev edits | source-node detection (two independent guards) |
| `VERSION` file lies | manifest version is the only comparison |

## 9. Verification

```
# this node's posture
curl -s -H "Cookie: cc_auth=3673" http://localhost:8800/api/update-status | python3 -m json.tool
# fleet drift (who's behind)
curl -s -H "Cookie: cc_auth=3673" http://localhost:8800/api/ccr-drift | python3 -m json.tool
# force a tenant to self-check now (run on that node)
curl -s -X POST -H "Cookie: cc_auth=3673" http://localhost:8802/api/update-now
# MC: converge the fleet
curl -s -X POST -H "Cookie: cc_auth=3673" -H "Content-Type: application/json" -d '{}' http://localhost:8800/api/fleet-update
# log
tail -f <state>/_autoupdate.log
```

A converged fleet: every node in `/api/ccr-drift` shows `current` (or `ahead`/`drifted` for source nodes
between a build and the next dist stage).
