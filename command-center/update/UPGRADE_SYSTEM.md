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
   │  <CC_HOME> (authoring checkout)   (git: claudesole-core) │
   │   ├─ hpcc (8799)  ├─ overseer/MC (8800)  ├─ acme         │  ← share one CC_HOME; all detected as source
   └───────────────┬─────────────────────────────────────────┘
                   │  ship: push core + push PUBLIC dist mirror
                   ▼
        GitHub: <you>/claudesole-dist  (PUBLIC)        ◄── canonical "latest"
                   │                         ▲
        local clone │ (MC's mirror for       │ raw manifest probe + git clone --depth 1
        /Users/Shared/claudefather-dist)     │
                   │                         │
   ┌───────────────┴──────────┐   ┌──────────┴───────────────┐
   │ acme (userA, 8850/8851)   │   │ tenant (8802→9802)        │   … and every future tenant
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
- **Self-restart is the safe path even for a cross-user tenant** — the node re-execs *itself*; MC never touches another user's process.
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

`_is_update_source()` is **portable and host-agnostic**, checked most-explicit first:
1. `cc.config update_role == "source"` — the documented way; set it on ANY authoring node, any host.
2. a `.cc-source` marker file in `CC_HOME` — git-independent (survives non-repo / downloaded checkouts).
3. `CC_HOME` IS the dist mirror dir.
4. `git -C CC_HOME remote -v` mentions the private authoring repo (`CORE_AUTHORING_REPO`) — dev-fleet convenience.

Our three local nodes are marked **both** ways (`update_role:"source"` in each cc.config **and** a `.cc-source`
marker) so protection never depends on the git heuristic. `fleet_converge` additionally skips any node whose
`home == CC_HOME`. **A fresh/downloaded tenant matches NONE of these → it correctly self-updates.** Tenants
(`acme`, `tenant`) carry no `update_role` and no marker → they self-update normally.

## 6. Bootstrap note (one-time, by design)

The self-updater is *new code*. A node already running OLD code (`tenant` @ 0.28, `acme` @ 0.67 pre-this-release)
has no self-updater yet, so it can't self-converge to the release that first contains it. That first hop is
done once via PUSH (`Update all behind` / `fleet_converge`). After a node is on a self-updater-bearing
version, path A keeps it current forever. **This is the only time a human-initiated push is required**, and
it's a single fleet-wide action, not per-node.

## 6b. White-label / private-fleet portability (packaged-product checklist)

The update identity lives in **one place** — three constants at the top of `server.py`:
`OFFICIAL_DIST_GIT`, `OFFICIAL_DIST_DIR`, `CORE_AUTHORING_REPO`. Everything else is config. To run a fleet
that updates from **your own** dist instead of the canonical one, set per node (no code edits):

- `update_source` — a git URL on **any host** (GitHub/GitLab raw-probe auto-derived; any other host falls
  back to a shallow-clone version check) **or a local/shared-mount directory path** (manifest read directly).
- `update_manifest_url` — optional explicit raw-manifest URL for hosts we don't auto-derive.
- `dist_dir` — the MC-side local mirror used by the PUSH path.
- `auto_update: false` — for a fleet that wants operator-gated (not auto) updates; converge then via the
  Fleet-drift button / `POST /api/fleet-update`.
- Mark your authoring node with `update_role: "source"` (or a `.cc-source` file). Never set it on a tenant.

A downloaded ClaudeFather with **zero config** behaves correctly: tenant, auto-updates from the canonical
dist, self-restarts when idle. No path, repo name, port, or account in the update engine is hardcoded
outside those three named constants.

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
| Cross-user restart (a tenant on another user) | self-restart via superadmin `restart`, never tmux/`restart:true` |
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
