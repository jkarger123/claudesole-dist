# ClaudeFather -- AGENT INSTALL GUIDE (read this fully, then act)

You are a Claude Code agent installing **ClaudeFather** -- a portable, brand/project-agnostic AI project
control center (a dashboard + scoped agents you run a whole project or company from). You were pointed at
this install package. This file is your complete playbook. ASCII only in everything you write. Ask the
operator the few decisions marked **ASK**; do everything else yourself and report.

## 0. What ClaudeFather is (so you understand what you're installing)
- A stdlib-Python web app: `command-center/server.py` (the dashboard + lenses + a terminal + session
  launcher), tmux-supervised, config-driven via `cc.config.json`.
- **Framework is generic; config is per-deployment.** The whole framework could go public without leaking a
  secret. Per-deployment values (project path, brand, secrets, storage choice) live in `cc.config.json`,
  the encrypted vault, and gitignored files.
- Capabilities are directories: an **agent-tool** is `agents/<slug>/` (a CLAUDE.md charter + tools/run.py)
  that auto-appears as a dashboard lens + a talkable agent. **Extensions** (Marketplace) are installable
  add-ons. **Ralph loops** are self-terminating autonomous agent loops.
- Deeper references in this package: `docs/HARDENING.md`, `docs/UPDATES.md`, `docs/CREDENTIALS.md`,
  `docs/PACKAGING.md`, `extensions/AUTHORING.md`, `docs/CHANGELOG.md`. Read them if unsure.

---

## 1. ASK FIRST: which INSTALL MODE?

This is the most important decision in this file and it is easy to get wrong. **Do not skip it.**

| | **APPLIANCE** (default for anyone outside the authoring fleet) | **DEVELOPER** |
|---|---|---|
| Who | a customer / external operator running a box they own | us, on a machine where we author framework code |
| Core | `/Library/ClaudeFather/core`, root-owned, **read-only to the runtime user** | in place, owned by the installing user, writable |
| Runtime user | dedicated non-admin `cfrun` (no shell, hidden) | the installing user |
| Updates | privileged healer applies **signed** updates every 30 min; unverified BLOCKED | `cc-update.sh` when you choose |
| Edition | `appliance` -- core-mutating ops refuse, integrity self-heals | `authoring` on a source node |
| Licensing | hardware-bound signed license | n/a |
| Installer | `cf-appliance-install.sh` (section 4A) | `cc-init.sh` (section 4B) |

**If the operator is not part of the authoring fleet, the answer is APPLIANCE.** The developer path leaves
every framework file writable by the operator and their agents; it exists for authoring, not for shipping.
If you are unsure, ASK -- and default to appliance.

Also ASK: the **brand** (display name, e.g. "Acme"), and for the developer path the **storage mode**
(section 6).

---

## 2. Prerequisites -- run the preflight, do not eyeball it

Dependencies are DECLARED in `claudefather.deps.json` and verified by `cf-preflight`. Run it; do not
hand-check with `command -v`.

```
cd <path-to-unzipped>/claudefather
export CC_HOME="$(pwd)"
bash install.sh                 # actions (chmod, dirs, scanners, cryptography) THEN runs cf-preflight as a gate
bash cf-preflight --appliance   # for an appliance install, also checks the cfrun + root interpreters
```

`install.sh` exits nonzero if a required dependency is missing. **Do not proceed past a failing preflight** --
every downstream symptom ("the agent is broken", "secrets won't save") traces back to it.

Two prerequisites deserve special attention:

- **`claude` (Claude Code) must be installed AND authenticated.** Every chief, agent, Ralph loop and the
  Front Desk concierge shells out to it. Without auth the dashboard boots green and **every agent fails on
  first launch**. Verify for real before launching: `claude -p 'reply OK'` must print `OK`.
- **`cryptography` must be importable by EVERY interpreter that needs it**, not just the one on your PATH.
  On an appliance that means the runtime user (`cfrun`) and `root`, which are different interpreters with
  different site-packages. `pip install --user` by the admin is invisible to both. `cf-preflight --appliance`
  checks each one; if it reports UNKNOWN because it needs a sudo password, **actually run the command it
  prints** rather than assuming.

**macOS-first; Linux runs the server too** (supervise with `install/templates/claudefather.service.template`,
use `storage_mode: github`). macOS-only features degrade gracefully, never crash boot: Claude account
switching (Keychain), the `icloud` storage modes, launchd supervision, power/thermal vitals, and the
hardened appliance installer itself.

---

## 3. ASK: NEW project or MIGRATE an existing one?

- **NEW** -> after the install completes, section 7 scaffolds it.
- **MIGRATE an existing project/codebase** -> section 8. **Read it carefully** -- it has safety rules for
  not breaking the live thing you are migrating.

---

## 4A. APPLIANCE install (the hardened, shippable path)

Full architecture + honest threat model: `docs/HARDENING.md`. Bring-up detail: `docs/APPLIANCE_BRINGUP.md`.

1. Get the bundle onto the box (this package, or `git clone` the public dist).
2. Run the hardened installer as an admin, with sudo:
   ```
   sudo bash cf-appliance-install.sh            # add --immutable for chflags(schg) on core
   ```
   Optionally pass activation so the box licenses itself on first boot:
   ```
   sudo CF_ACTIVATION_URL="https://<vendor-mission-control>" CF_ACTIVATION_CODE="CF-XXXX-XXXX-XXXX-XXXX" \
     bash cf-appliance-install.sh
   ```
   It creates the non-admin `cfrun` user, copies the framework to a root-owned read-only core, installs
   `cryptography` system-wide for the pinned interpreter **and verifies it as both root and cfrun**, writes
   an `edition: appliance` config with `update_verify: enforce` + `vault_keychain: true`, installs the
   runtime + healer LaunchDaemons, and then **asserts the hardening actually holds**.
3. **Read the installer's final block.** It prints the **LOGIN PIN once** -- it is not recoverable from the
   UI. Write it down before you continue. It also tells you whether licensing ended up ENFORCED or SOFT.
4. If it printed `APPLIANCE NOT READY`, fix the failed assertions before handing the box over. In
   particular this must FAIL (permission denied):
   ```
   sudo -u cfrun touch /Library/ClaudeFather/core/command-center/server.py
   ```
   If that command SUCCEEDS, the core is not protected and the box must not ship.
5. Licensing. If you did not pass activation, the installer left `license_enforce` off deliberately (turning
   it on with no way to activate would lock the box out with no path forward). To license it later:
   `GET /api/license` on the box for its `fingerprint` -> `POST /api/license-issue {fingerprint, customer,
   days}` on Mission Control -> `POST /api/license-install` on the box -> set `license_enforce: true`.
6. Go to section 5 (verify), then 7/8 (the project).

**Never** hand-edit framework files on an appliance -- the healer reverts them within 30 minutes and the
edit is recorded as integrity drift. Customer code belongs in the writable `custom/` sandbox.

## 4B. DEVELOPER install (authoring machines only)

1. ASK the operator for the project root (an existing dir to operate on; create one if needed).
2. `CC_HOME="$CC_HOME" bash cc-init.sh <project_root> "<project_name>" "<brand>" "<storage_mode>"`
   Writes `cc.config.json` including a minted login token and an explicit update posture; makes
   `agents/ bin/ data/`; installs scanners; creates a starter project CLAUDE.md if absent; installs the
   pre-commit secret gate if it is a git repo; runs a first security scan. **It prints the PIN -- capture it.**
3. Pick a port (default 8799) and a tmux session name; set both in `cc.config.json`.
4. Start it:
   ```
   CC_CONFIG="$CC_HOME/cc.config.json" TMUX_TMPDIR=/tmp tmux new-session -d -s <session> \
     "cd $CC_HOME && python3 command-center/server.py"
   ```
   For always-on, fill in the `__PLACEHOLDERS__` in `install/templates/` (launchd on macOS, systemd on Linux).
5. Go to section 5.

---

## 5. Verify (both paths)

```
curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/     # must be 200
curl -s http://localhost:<port>/api/health                          # appliance: "edition":"appliance"
```
Open the URL in a browser and log in with the PIN. Then check the **Doctor** panel and resolve anything red
before declaring done -- Doctor is where a missing dependency, a disabled vault, an unlicensed appliance, or
a dead update healer will surface.

---

## 6. Storage mode (developer path; ASK)
- `github` -- local + git push to GitHub (mixed-OS default).
- `icloud` -- deployment + project under an iCloud-synced folder (pure-Apple setups).
- `icloud+github` -- both.
For an iCloud mode, the project must actually live under `~/Library/Mobile Documents/com~apple~CloudDocs/...`.
An appliance keeps its writable state under the runtime root instead; leave this alone there.

---

## 7. NEW project -- get them to real work fast
Do not leave them at a blank dashboard.
1. Open the **Setup agent** (Agents -> setup): purpose -> project charter -> brand -> agent roster ->
   Marketplace -> first goals.
2. Or run `cc-onboard scaffold` to build the project shell directly.
3. Capture the first 1-3 real tasks so the box opens to a to-do list, not an empty screen.

## 8. MIGRATE an existing project (safety-first)
1. **Read the original READ-ONLY first.** Map it: where it lives, stack, services, entry points, what is
   live. Do NOT modify the original during discovery. If it runs under a different OS account or is live in
   production, treat it as untouchable ground truth.
2. ASK: operate **in place**, or **relocate a copy** (recommended if the original is on an off-limits
   account or a full disk). If relocating, exclude `node_modules`, virtualenvs, `.git`, caches.
3. **Secrets:** grep the copied tree for hardcoded credentials. Move every one into the **vault** (Vault
   lens, or `cc-secure request`), replace with `_deploy_env(...)` reads, and write a rotation ledger of what
   was exposed. Never commit a secret; never push until the tree is secret-clean (`bin/gitleaks`).
4. **Fresh git** if relocated, so no secret history ships. Commit only after a clean scan; push to a PRIVATE remote.
5. Run `cc-onboard adopt` -- it fans out cheap parallel readers over the tree and produces a lean root
   CLAUDE.md, per-folder CLAUDE.mds, the module map, a Doctor-clean config, and secrets in the vault, then
   hands off to the Chief of Staff. This is far better than hand-writing the structure.

---

## 9. Remote access (only if they want it) -- and the trap that breaks the server

The dashboard is reachable at `http://localhost:<port>/` on the box with no extra setup. Tailscale is only
needed to reach it from a phone or another laptop, and it is **their own tailnet**, not ours.

```
tailscale serve --bg --https=<port+1000> http://127.0.0.1:<port>
```

**The +1000 offset is mandatory, not cosmetic.** The server binds `0.0.0.0:<port>`, which already includes
the tailnet IP. Serving on the SAME port number is `EADDRINUSE` and **the server will not start**. Offset by
1000 (8800 -> 9800) as the rest of the fleet does.

Do NOT put a customer on our tailnet, and do not attempt managed enrollment under our Mission Control for a
first external box -- outbound license activation is the only contact needed.

---

## 10. macOS steps no installer can perform (walk the operator through these)

1. **Full Disk Access on the tmux binary** -- required only if the project or data lives on an EXTERNAL
   volume (`/Volumes/...`); the internal disk never EPERMs. System Settings -> Privacy & Security -> Full
   Disk Access -> add the tmux binary. **`brew upgrade tmux` changes its signature and silently voids the
   grant** -- consider `brew pin tmux`. ASK whether their project will live on an external drive; if yes,
   walk this now and verify, because the failure is invisible until something is unreadable.
2. **Power posture -- an explicit CHOICE, the two goals genuinely conflict. ASK:**
   - *Secure* (recommended for an appliance): FileVault ON + `vault_keychain: true`. Protects vault
     ciphertext in a stolen-disk scenario; a power cut needs one human unlock before the box returns.
   - *Resilient*: FileVault OFF + auto-login ON. Survives a power cut unattended; weaker at-rest protection.
3. **Accessibility** -- only for the optional focus/context capture. Leave off for a first install.
4. **Notifications** -- nothing to grant. The framework does not use system notifications; they are
   in-dashboard. Only the optional desktop app would need a grant.

---

## 11. Hard rules (do not violate)
- ASCII only in every file you write.
- **Secrets go in the VAULT, never in chat, never in a committed file.** Use `cc-secure request "<label>"
  vault:<KEY>` -- it pops a dashboard modal and the value routes browser -> server -> vault, never through
  you or the transcript. Never ask the operator to paste a secret into the conversation.
- **Never change an existing `auth_token` / `mesh_token`** without confirming the exact value first -- a
  wrong value is a lockout.
- During a migration, NEVER modify the live original; read-only until you are working on a copy.
- Read-first / least-privilege for every extension you wire. Removals reversible (archive, don't delete).
- The framework is generic -- never hardcode this deployment's paths into framework files.
- On an appliance: never edit core, never disable the healer, never flip `edition` to authoring. If
  something genuinely needs a framework change, file a CCR (Propose Change) -- it is built once upstream
  and shipped signed.

**Report to the operator when done:** the URL, the PIN (once), the install mode, licensing status, the
storage mode, anything Doctor still flags, and any secrets that need rotation.
