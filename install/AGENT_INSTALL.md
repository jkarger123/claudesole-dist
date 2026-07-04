# ClaudeFather -- AGENT INSTALL GUIDE (read this fully, then act)

You are a Claude Code agent installing **ClaudeFather** -- a portable, brand/project-agnostic AI project
control center (a dashboard + scoped agents you run a whole project or company from). You were pointed at
this install package. This file is your complete playbook: follow it to **start a new project** OR **migrate
an existing project** into ClaudeFather. ASCII only in everything you write. Ask the operator the few
decisions marked ASK; do everything else yourself and report.

## 0. What ClaudeFather is (so you understand what you're installing)
- A stdlib-Python web app: `command-center/server.py` (the dashboard + lenses + a terminal + session
  launcher), tmux-supervised, config-driven via `cc.config.json`.
- **Framework is generic; config is per-project.** The whole framework could go public without leaking a
  secret. Per-deployment values (project path, brand, secrets, storage choice) live in `cc.config.json` +
  gitignored files.
- Capabilities are directories: an **agent-tool** is `agents/<slug>/` (a CLAUDE.md charter + tools/run.py)
  that auto-appears as a dashboard lens + a talkable agent. **Extensions** (Marketplace) are installable
  add-ons (Google, Slack, GitHub, Postgres, Sentry, Telegram, ...). **Ralph loops** are self-terminating
  autonomous agent loops.
- Deeper references in this package: `docs/PACKAGING.md`, `docs/CONTROL_CENTER_BLUEPRINT.md`,
  `docs/MEMORY_SKILLS_AGENTS.md`, `extensions/AUTHORING.md`, `docs/CHANGELOG.md`. Read them if unsure.

## 1. Prerequisites (check first; report what's missing)
- `python3` (3.8+) -- required. `tmux` -- required (the dashboard runs in a tmux session).
- `git` + (optional) `gh` -- for the GitHub backup storage mode.
- `node` -- optional (only for some extensions + JS lint). `zip`/`unzip` -- to handle this package.
- macOS or Linux. On macOS, Homebrew tmux at `/opt/homebrew/bin/tmux` is typical.

## 2. Set CC_HOME = this unzipped framework directory
The unzipped `claudefather/` directory IS the framework home. From inside it:
```
cd <path-to-unzipped>/claudefather
export CC_HOME="$(pwd)"
bash install.sh          # chmod scripts, make data/ bin/, install scanners if possible, print next steps
```
Everything below uses `$CC_HOME`. (You may instead copy this dir to a permanent location first, e.g.
`~/claudefather`, then set CC_HOME there.)

## 3. ASK the operator: NEW project or MIGRATE an existing one?
- **NEW** -> go to section 4A.
- **MIGRATE an existing project/codebase into ClaudeFather** -> go to section 4B (READ IT CAREFULLY -- it has
  safety rules for not breaking the live thing you're migrating).
Also ASK: the **brand** (display name, e.g. "Acme"), and the **storage mode** (section 5).

## 4A. NEW project
1. ASK the operator for the project root (an existing dir to operate on; create one if needed).
2. `CC_HOME="$CC_HOME" bash cc-init.sh <project_root> "<project_name>" "<brand>" "<storage_mode>"`
   (writes `cc.config.json`, makes `agents/ bin/ data/`, installs scanners, creates a starter project
   CLAUDE.md if absent, installs the pre-commit secret gate if it's a git repo, runs a first security scan).
3. Go to section 6 (start + verify).

## 4B. MIGRATE an existing project (the safety-first playbook)
This is how an existing system (its code, services, data) becomes a ClaudeFather-operated project WITHOUT
breaking the live original. Mirrors a proven real-world migration.
1. **Read the original READ-ONLY first.** Map it: where it lives, its stack, services, entry points, what's
   live. Do NOT modify the original during discovery. If it runs under a different OS account or is live in
   production, treat it as untouchable ground truth.
2. ASK: migrate **in place** (operate the project where it is) or **relocate a copy** (recommended if the
   original is on an off-limits account / internal disk). If relocating: copy to the new home EXCLUDING
   `node_modules`, virtualenvs, `.git`, and caches; never modify the original.
3. **Secrets:** grep the (copied) tree for hardcoded credentials (API keys, tokens, connection strings,
   private keys). Extract every one into a gitignored env file (e.g. `.env.claudefather` or the project's
   `.env`), replace in code with env references, and write a rotation ledger of what was exposed. NEVER
   commit a secret; NEVER push until the tree is secret-clean (use `bin/gitleaks` if present).
4. **Fresh git** (so no secret history ships): if relocated, `git init` the copy; commit only after the
   secret scan is clean; push to a PRIVATE remote.
5. `CC_HOME="$CC_HOME" bash cc-init.sh <project_root> "<name>" "<brand>" "<storage_mode>"` on the (copied)
   project.
6. Write/refine the project's root `CLAUDE.md` as a lean index (what it is, where things live, hard rules).
   Folders with their own CLAUDE.md become modules the dashboard indexes.
7. Go to section 6.

## 5. Storage mode (ASK -- how files are kept safe + available)
Set `storage_mode` in `cc.config.json` (cc-init's 4th arg):
- `github` -- local + git push to GitHub (mixed-OS / PC default).
- `icloud` -- the deployment + project live under an iCloud-synced folder, so files are on every Apple
  device automatically (pure-Apple setups). The backup agent verifies the iCloud path instead of git.
- `icloud+github` -- both (iCloud for cross-device + GitHub for versioned off-site backup). Best for a
  pure-Apple operator who also wants version history.
For an iCloud mode, put the project (and optionally this framework) UNDER the iCloud-synced folder
(`~/Library/Mobile Documents/com~apple~CloudDocs/...`) so it actually syncs.

## 6. Start + supervise + verify
1. Pick a port (default 8799; use another if taken). Set it in `cc.config.json` ("port": N).
2. Start: `CC_CONFIG="$CC_HOME/cc.config.json" TMUX_TMPDIR=/tmp tmux new-session -d -s claudefather \
   "cd $CC_HOME && python3 command-center/server.py"`  (or use the supervisor `command-center/cc-supervise.sh`).
3. For always-on: install a launchd (macOS) / systemd (Linux) unit that runs the server; see
   `command-center/cc-instance-supervise.sh` for the supervised pattern.
4. **Verify:** `curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/` must be `200`. Open that
   URL in a browser -> you should see the dashboard with the project's lenses.

## 7. Optional: register under an overseer (Mission Control)
If the operator runs a multi-project ClaudeFather "overseer", add this deployment to the overseer's
`instances/overseer/state/_instances.json` (id, url, port, role: project) so it shows in the Portfolio. For a
remote machine, expose this instance over Tailscale (`tailscale serve --https=<port>`) and register the
tailnet URL.

## 8. Operate + keep updated
- Talk to the **Chief of Staff** from the dashboard; use the **Agents**, **Marketplace** (install
  extensions: Google/Slack/GitHub/etc., each with a guided setup agent), **Projects**, **Ralph Loops**,
  **Backup**, **Security** lenses.
- **Future updates:** `cc-update.sh <upstream>` overlays new framework versions (from a newer package dir or
  the framework git URL) WITHOUT touching this deployment's config/data/secrets. `docs/CHANGELOG.md` +
  `claudesole.manifest.json` version tell you if you're behind.

## 9. Hard rules (do not violate)
- ASCII only in every file you write. Secrets ONLY in gitignored files; never commit/echo a full secret.
- During a migration, NEVER modify the live original; read-only until you're working on a copy.
- Read-first / least-privilege for every extension you wire. Removals reversible (archive, don't delete).
- The framework is generic -- never hardcode this project's paths into framework files; per-project values
  go in `cc.config.json`.

Report to the operator when the dashboard is up (the URL), what mode you ran, the storage mode, and any
secrets that need rotation.
