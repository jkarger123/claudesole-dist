# ClaudeFather -- install package

A portable AI project control center: a dashboard + scoped agents you run a whole project or company from
with Claude Code. This package installs a NEW project or MIGRATES an existing one in.

## The easy way (let Claude Code do it)
1. Unzip this package.
2. Open a Claude Code session in the unzipped `claudefather/` folder.
3. Tell it: **"Read AGENT_INSTALL.md and install ClaudeFather."** For a migration, add
   **"...migrating <path or description of the existing project>."**
4. It runs the preflight, asks you the few real decisions (install mode, brand, project), installs,
   verifies, and reports the URL + your login PIN.

## Two install modes -- pick deliberately
- **Appliance (recommended for anyone running their own box).** Hardened: the framework core is installed
  root-owned and **read-only to a dedicated non-admin runtime user**, so neither you nor an agent can
  modify it by accident. Signed updates are applied automatically by a privileged helper, and the core
  self-heals if it is ever changed. `sudo bash cf-appliance-install.sh`
- **Developer.** Everything in place and writable, updated when you choose. For machines where the
  framework itself is being authored.

If you are not developing ClaudeFather itself, you want **appliance**.

## Check your machine first
```
cd claudefather
export CC_HOME="$(pwd)"
bash install.sh                 # sets up, installs dependencies, then verifies them and stops if any are missing
bash cf-preflight --appliance   # dependency + permission report for a hardened install
```
`claudefather.deps.json` declares everything the product needs; `cf-preflight` is what checks it. If the
preflight fails, fix it before going further -- almost every confusing later symptom starts here.

## Requirements
`python3` (3.8+), `tmux`, `git`, and **Claude Code (`claude`), installed and logged in** -- it is the engine
every agent runs on. One Python package: `cryptography`. Optional: `node`, `tailscale` (remote access),
`gh` (GitHub storage mode).

## Manual way (developer mode)
```
cd claudefather && export CC_HOME="$(pwd)"
bash install.sh
bash cc-init.sh <project_root> "<name>" "<brand>" "<github|icloud|icloud+github>"
CC_CONFIG="$CC_HOME/cc.config.json" TMUX_TMPDIR=/tmp tmux new-session -d -s claudefather \
  "cd $CC_HOME && python3 command-center/server.py"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/    # expect 200, then open it in a browser
```

## After it's up
Log in with the PIN the installer printed, then open **Doctor** and clear anything red. Point the **Setup
agent** (or `cc-onboard adopt` for existing code) at your project.

## More
Full agent playbook: `AGENT_INSTALL.md`. Hardening + threat model: `docs/HARDENING.md`. Updates + signature
trust: `docs/UPDATES.md`. Credentials: `docs/CREDENTIALS.md`. Version: see `VERSION`.
