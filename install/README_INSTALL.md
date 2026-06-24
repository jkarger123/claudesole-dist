# ClaudeFather -- install package

A portable AI project control center: a dashboard + scoped agents you run a whole project or company from
with Claude Code. This package installs a NEW project or MIGRATES an existing one in.

## The easy way (let Claude Code do it)
1. Unzip this package.
2. Open a Claude Code session in the unzipped `claudefather/` folder.
3. Tell it: **"Read AGENT_INSTALL.md and install ClaudeFather."** For a migration, add
   **"...migrating <path or description of the existing project>."**
4. It follows `AGENT_INSTALL.md`: checks prerequisites, runs `cc-init`, sets the storage mode, starts +
   verifies the dashboard, and reports the URL.

## The manual way
```
cd claudefather
export CC_HOME="$(pwd)"
bash install.sh
bash cc-init.sh <project_root> "<name>" "<brand>" "<github|icloud|icloud+github>"
CC_CONFIG="$CC_HOME/cc.config.json" TMUX_TMPDIR=/tmp tmux new-session -d -s claudefather \
  "cd $CC_HOME && python3 command-center/server.py"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/    # expect 200, then open it in a browser
```

## Requirements
python3 (3.8+) + tmux required. Optional: git/gh (GitHub storage mode), node (some extensions).

## More
Full agent playbook: `AGENT_INSTALL.md`. References: `docs/PACKAGING.md`,
`docs/CONTROL_CENTER_BLUEPRINT.md`, `extensions/AUTHORING.md`. Version: see `VERSION`.
