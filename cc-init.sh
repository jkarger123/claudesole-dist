#!/usr/bin/env bash
# cc init -- point the control center at a project (the "drop any project in" flow).
# Usage: cc-init.sh <project_root> [project_name] [brand]
#        cc-init.sh                 (re-init / refresh from the existing cc.config.json)
# Framework (server.py, agents/, bin/) is generic; this wires it to ONE project via cc.config.json.
set -uo pipefail
CC_HOME="${CC_HOME:-$HOME/hptuners-control}"
CFG="$CC_HOME/cc.config.json"
SEC="$CC_HOME/agents/security/tools"
ROOT="${1:-}"; NAME="${2:-}"; BRAND="${3:-}"; STORAGE="${4:-}"   # STORAGE: github | icloud | icloud+github

if [ -z "$ROOT" ]; then
  [ -f "$CFG" ] || { echo "usage: cc-init.sh <project_root> [project_name] [brand]"; exit 1; }
  ROOT=$(python3 -c "import json;print(json.load(open('$CFG')).get('project_root',''))")
fi
ROOT="${ROOT/#\~/$HOME}"
[ -d "$ROOT" ] || { echo "project_root does not exist: $ROOT"; exit 1; }
[ -z "$NAME" ] && NAME=$(basename "$ROOT")
if [ -z "$BRAND" ] && [ -f "$CFG" ]; then BRAND=$(python3 -c "import json;print(json.load(open('$CFG')).get('brand',''))" 2>/dev/null); fi
[ -z "$BRAND" ] && BRAND="$NAME"

echo "== cc init =="
echo "  project_name: $NAME"
echo "  project_root: $ROOT"
echo "  brand:        $BRAND"
echo "  framework:    $CC_HOME"

# 1) framework dirs
mkdir -p "$CC_HOME/agents" "$CC_HOME/bin" "$CC_HOME/data"

# 2) write/merge config (preserve agents list + chief_brief if already present)
python3 - "$CFG" "$NAME" "$ROOT" "$BRAND" "$STORAGE" <<'PY'
import json,sys,os
cfg,name,root,brand,storage=sys.argv[1:6]
d=json.load(open(cfg)) if os.path.exists(cfg) else {}
d["project_name"]=name; d["project_root"]=root; d["brand"]=brand
if storage: d["storage_mode"]=storage
d.setdefault("storage_mode","github")
d.setdefault("framework","command-center")
d.setdefault("agents",["security","backup","usage","ideas","routines"])
d.setdefault("chief_brief","You are my Chief of Staff, operating from the top level. Read CLAUDE.md, give me a one-line status of the operation, and stand by.")
json.dump(d,open(cfg,"w"),indent=2)
print("  wrote",cfg)
PY

# 3) scanners (only if missing)
if [ -x "$CC_HOME/bin/gitleaks" ]; then echo "  scanners: present"; else
  bash "$SEC/install_scanners.sh" >/dev/null 2>&1 && echo "  scanners: installed" || echo "  scanners: SKIP (network?)"
fi

# 4) starter project CLAUDE.md if missing
if [ ! -f "$ROOT/CLAUDE.md" ]; then
  cat > "$ROOT/CLAUDE.md" <<EOF
# $NAME

Project operated by the $BRAND control center. This is the root context every agent reads first.
Keep it a LEAN index of pointers (aim < 200 lines): what this project is, where things live, hard rules.

## Sub-tools
(Folders with their own CLAUDE.md become modules; the control center indexes them here.)
EOF
  echo "  created starter $ROOT/CLAUDE.md"
else
  echo "  project CLAUDE.md: present"
fi

# 5) pre-commit secret gate (git repos only)
if [ -d "$ROOT/.git" ]; then
  bash "$SEC/install_gate.sh" "$ROOT" >/dev/null 2>&1 && echo "  secret gate: installed" || echo "  secret gate: SKIP"
else
  echo "  secret gate: SKIP (not a git repo)"
fi

# 6) first security scan
python3 "$SEC/scan.py" >/dev/null 2>&1 && echo "  security scan: done (see Security lens)" || echo "  security scan: SKIP"

echo
echo "Done. Restart the dashboard to operate on the new project:"
echo "  TMUX_TMPDIR=/tmp /opt/homebrew/bin/tmux kill-session -t hpcc"
echo "Control center now targets: $ROOT"
