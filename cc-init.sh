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

# 1) framework dirs -- a ClaudeFather install is a SELF-CONTAINED, relocatable bundle: code + config + state
#    + deliverables all under $CC_HOME, so you can move the whole folder to a dedicated drive / new server.
#    deliverables/ is the single clean branch where the system saves the files it makes (each module's
#    deliverables/ symlinks into it). Override its location with cc.config "deliverables_root" to put it on a
#    dedicated drive without moving the rest of the install.
mkdir -p "$CC_HOME/agents" "$CC_HOME/bin" "$CC_HOME/data" "$CC_HOME/deliverables"
# git-init the central deliverables store so authored docs are versioned from day one (CCR: node-builder git-init).
# Guarded; the project_root is the user's own tree, so we do NOT force git on it here.
if command -v git >/dev/null 2>&1 && [ ! -d "$CC_HOME/deliverables/.git" ]; then
  printf '%s\n' '.DS_Store' > "$CC_HOME/deliverables/.gitignore"
  ( git -C "$CC_HOME/deliverables" init -q && git -C "$CC_HOME/deliverables" add -A \
      && git -C "$CC_HOME/deliverables" -c user.name="$BRAND" -c user.email="node@claudefather.local" commit -qm "deliverables store initialized" ) 2>/dev/null || true
fi

# 2) write/merge config (preserve agents list + chief_brief if already present)
python3 - "$CFG" "$NAME" "$ROOT" "$BRAND" "$STORAGE" <<'PY'
import json,sys,os
cfg,name,root,brand,storage=sys.argv[1:6]
d=json.load(open(cfg)) if os.path.exists(cfg) else {}
d["project_name"]=name; d["project_root"]=root; d["brand"]=brand
if storage: d["storage_mode"]=storage
d.setdefault("storage_mode","github")
d.setdefault("framework","command-center")
# Enterprise auto-update: a provisioned node is a TENANT -> it self-converges from the dist (boot + timer).
# Leave update_role UNSET (only authoring/source nodes set it). Override update_source for a private fleet.
d.setdefault("auto_update",True)
d.setdefault("agents",["security","backup","usage","ideas","routines"])
d.setdefault("chief_brief","You are my Chief of Staff, operating from the top level. Read CLAUDE.md, give me a one-line status of the operation, and stand by.")
# Per-node auth_token (NODE_SETUP_STREAMLINE.md #3/#4): mint one ONLY when none exists -- an existing
# token is NEVER touched (lockout hard rule). Printed once below; cc-recover.sh is the break-glass.
minted=""
if not d.get("auth_token"):
    import secrets; minted=secrets.token_hex(12); d["auth_token"]=minted
json.dump(d,open(cfg,"w"),indent=2)
print("  wrote",cfg)
if minted:
    print("  LOGIN TOKEN minted (dashboard PIN -- save it; recover anytime with cc-recover.sh):")
    print("    "+minted)
PY
chmod 600 "$CFG"

# 3) scanners (only if missing)
if [ -x "$CC_HOME/bin/gitleaks" ]; then echo "  scanners: present"; else
  bash "$SEC/install_scanners.sh" >/dev/null 2>&1 && echo "  scanners: installed" || echo "  scanners: SKIP (network?)"
fi

# 3b) Ed25519 verification: without `cryptography` this node can't verify the owner's superadmin grants
#     (falls back to HMAC-only) -- best-effort install here; Doctor keeps flagging it if still missing.
if python3 -c "import cryptography" >/dev/null 2>&1; then echo "  cryptography: present"; else
  pip3 install --user cryptography >/dev/null 2>&1 && echo "  cryptography: installed" \
    || echo "  cryptography: MISSING (superadmin grants verify on HMAC fallback -- pip3 install --user cryptography)"
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
echo "Deliverables (files the system makes) land in: ${CC_HOME}/deliverables  (self-contained; the whole"
echo "  install can be moved to a dedicated drive. To put just deliverables on another drive, set"
echo "  cc.config \"deliverables_root\".)"
