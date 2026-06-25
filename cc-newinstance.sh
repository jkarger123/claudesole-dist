#!/usr/bin/env bash
# cc-newinstance.sh -- provision a NEW, self-contained, PORTABLE ClaudeFather instance bundle.
#
# Unlike cc-spawn.sh (a nested child that shares the parent's folder), this creates a STANDALONE bundle:
# one folder (its own CC_HOME) holding the full framework + its OWN config/secrets/state/project/
# deliverables -- so the whole instance can be picked up and moved to a dedicated drive or a new server.
#
# It is the deterministic ENGINE the "Add a ClaudeFather" provisioning agent drives. It NEVER starts the
# server or loads launchd by itself (approval gate): it stages everything and prints the exact commands.
#
# Usage:
#   cc-newinstance.sh --id <id> --dest <bundle_dir> [options]
# Options:
#   --name "<project name>"      human name           (default: id)
#   --brand "<brand>"            brand label          (default: name)
#   --preset project|overseer    role preset          (default: project)
#   --port <n>                   dashboard port       (default: auto, first free >= 8800)
#   --storage github|icloud|icloud+github             (default: github)
#   --agents a,b,c               scoped agent-tools    (default: security,backup,usage,ideas,routines)
#   --project-root <path>        the project this oversees (default: <dest>/project -- inside the bundle)
#   --user <login>               macOS user that will run it (default: current; used in the launchd hint)
#   --json                       emit a machine-readable JSON summary at the end (for the agent/UI)
#   --dry-run                    print the plan, write NOTHING
#
# Exit 0 = bundle staged. The caller then (with operator approval): launches it on the brain tmux server,
# and optionally installs the launchd plist so it survives reboot.
set -uo pipefail
SRC="${CC_HOME:-$HOME/hptuners-control}"          # the dev/master copy we provision FROM
ID="" DEST="" NAME="" BRAND="" PRESET="project" PORT="" STORAGE="github"
AGENTS="security,backup,usage,ideas,routines" PROOT="" RUNUSER="$(whoami)" DRY="" JSON=""

while [ $# -gt 0 ]; do
  case "$1" in
    --id) ID="$2"; shift 2;;
    --dest) DEST="$2"; shift 2;;
    --name) NAME="$2"; shift 2;;
    --brand) BRAND="$2"; shift 2;;
    --preset) PRESET="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --storage) STORAGE="$2"; shift 2;;
    --agents) AGENTS="$2"; shift 2;;
    --project-root) PROOT="$2"; shift 2;;
    --user) RUNUSER="$2"; shift 2;;
    --json) JSON=1; shift;;
    --dry-run) DRY=1; shift;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

die(){ echo "ERROR: $*" >&2; exit 1; }

# ---- validate -------------------------------------------------------------------------------------
[ -n "$ID" ]   || die "missing --id"
[ -n "$DEST" ] || die "missing --dest"
[ -f "$SRC/claudesole.manifest.json" ] || die "no framework manifest at SRC=$SRC (set CC_HOME)"
ID="$(echo "$ID" | tr -cd 'A-Za-z0-9_-')"
[ -n "$ID" ] || die "id reduces to empty after sanitizing (use A-Za-z0-9_-)"
DEST="${DEST/#\~/$HOME}"
[ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ] && die "dest exists and is not empty: $DEST"
PFILE="$SRC/presets/$PRESET.json"
[ -f "$PFILE" ] || die "no such preset '$PRESET' (have: $(ls "$SRC/presets" 2>/dev/null | sed 's/.json//' | tr '\n' ' '))"
ROLE="$(python3 -c "import json;print(json.load(open('$PFILE')).get('role','project'))")"
[ -n "$NAME" ]  || NAME="$ID"
[ -n "$BRAND" ] || BRAND="$NAME"
[ -n "$PROOT" ] || PROOT="$DEST/project"
PROOT="${PROOT/#\~/$HOME}"

# auto-pick a free port (>=8800) if none given
if [ -z "$PORT" ]; then PORT=8800; while lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT+1)); done; fi
lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1 && die "port $PORT is already in use"

# carry the FAMILY mesh token (shared badge) from the parent so the new node joins this family's mesh
MESH_TOKEN="$(python3 -c "import json;print(json.load(open('$SRC/cc.config.json')).get('mesh_token') or '')" 2>/dev/null || echo '')"
# fresh per-node dashboard auth token (a NEW node's initial token -- not a change to an existing one)
AUTH_TOKEN="$(python3 -c "import secrets;print(secrets.token_hex(16))")"

cat <<PLAN
== provision plan ==
  id:           $ID
  bundle dest:  $DEST
  name / brand: $NAME / $BRAND
  preset/role:  $PRESET / $ROLE
  port:         $PORT
  storage:      $STORAGE
  agents:       $AGENTS
  project root: $PROOT  (inside bundle = portable)
  run as user:  $RUNUSER
  mesh family:  $([ -n "$MESH_TOKEN" ] && echo "joining (family token carried)" || echo "NONE found at SRC -- node will be mesh-isolated until a token is set")
PLAN

if [ -n "$DRY" ]; then echo "(dry run -- nothing written)"; exit 0; fi

# ---- 1) build the bundle: copy every framework_path (manifest-driven; preserve_paths excluded by construction)
mkdir -p "$DEST"
( cd "$SRC" && python3 -c "import json;[print(p) for p in json.load(open('claudesole.manifest.json'))['framework_paths']]" ) | while read -r p; do
  for s in $SRC/$p; do
    [ -e "$s" ] || continue
    rel="${s#$SRC/}"
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -R "$s" "$DEST/$(dirname "$rel")/"
  done
done
# the generic instance supervisor + install guides + version stamp
cp "$SRC/command-center/cc-instance-supervise.sh" "$DEST/command-center/" 2>/dev/null || true
chmod +x "$DEST/command-center/cc-instance-supervise.sh" 2>/dev/null || true
for f in install/AGENT_INSTALL.md install/README_INSTALL.md install/install.sh cc-init.sh cc-recover.sh cc-update.sh cc-newinstance.sh superadmin.pub; do
  [ -f "$SRC/$f" ] && { mkdir -p "$DEST/$(dirname "$f")"; cp "$SRC/$f" "$DEST/$f"; }
done
python3 -c "import json;print(json.load(open('$SRC/claudesole.manifest.json'))['version'])" > "$DEST/VERSION"
mkdir -p "$DEST/data" "$DEST/bin" "$DEST/deliverables" "$DEST/launchd" "$PROOT"

# ---- 2) starter project CLAUDE.md
if [ ! -f "$PROOT/CLAUDE.md" ]; then
  cat > "$PROOT/CLAUDE.md" <<EOF
# $NAME

Project operated by the $BRAND control center (a self-contained ClaudeFather bundle).
Keep this a LEAN index (< 200 lines): what this project is, where things live, hard rules.

## Sub-tools
(Folders with their own CLAUDE.md become modules; the control center indexes them here.)
EOF
fi

# ---- 3) write the per-instance config (secrets included; chmod 600 below). Values pass as argv so
#         names/brands with spaces or quotes can't break the JSON.
python3 - "$DEST/cc.config.json" "$NAME" "$PROOT" "$BRAND" "$STORAGE" "$AGENTS" "$PORT" "$ID" "$ROLE" "$PRESET" "$DEST/deliverables" "$AUTH_TOKEN" "$MESH_TOKEN" <<'PY'
import json,sys
cfg,name,proot,brand,storage,agents,port,iid,role,preset,deliv,auth,mesh=sys.argv[1:14]
d={
 "project_name": name,
 "project_root": proot,
 "brand": brand,
 "storage_mode": storage,
 "framework": "command-center",
 "agents": [a.strip() for a in agents.split(",") if a.strip()],
 "chief_brief": "You are my Chief of Staff, operating from the top level. Read CLAUDE.md, give me a one-line status of the operation, and stand by.",
 "port": int(port),
 "instance_id": iid,
 "role": role,
 "preset": preset,
 "deliverables_root": deliv,
 "auth_token": auth,
}
if mesh: d["mesh_token"]=mesh
json.dump(d,open(cfg,"w"),indent=2)
print("  wrote",cfg)
PY
chmod 600 "$DEST/cc.config.json"

# ---- 4) peers.json: seed with the family's peers so the new node can reach them (chmod 600).
#         NOTE: registering THIS node INTO the other nodes' peers is a separate mesh step (printed below).
if [ -f "$SRC/peers.json" ]; then cp "$SRC/peers.json" "$DEST/peers.json"; else echo "[]" > "$DEST/peers.json"; fi
chmod 600 "$DEST/peers.json"

# ---- 5) stage a launchd plist (NOT loaded -- approval gate). Each bundle supervises its OWN server.
PLIST="$DEST/launchd/com.claudefather.$ID.plist"
SUP="$DEST/command-center/cc-instance-supervise.sh"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.claudefather.$ID</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SUP</string>
    <string>$DEST/cc.config.json</string>
    <string>cc-$ID</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/cc-$ID.launchd.log</string>
  <key>StandardErrorPath</key><string>/tmp/cc-$ID.launchd.log</string>
</dict>
</plist>
EOF

# ---- 6) register in the parent's _instances.json so the new node shows up in Portfolio
python3 - "$SRC/cc.config.json" "$ID" "$PROOT" "$PRESET" "$ROLE" "$PORT" "$DEST/cc.config.json" "$SRC/command-center" <<'PY'
import json,sys,os
pcfg,id,root,preset,role,port,cfg,base=sys.argv[1:9]
p=json.load(open(pcfg)) if os.path.exists(pcfg) else {}
sd=os.path.expanduser(p.get("state_dir") or base)
reg=os.path.join(sd,"_instances.json")
d=[x for x in (json.load(open(reg)) if os.path.exists(reg) else []) if x.get("id")!=id]
d.append({"id":id,"project_root":root,"preset":preset,"role":role,"port":int(port),
          "config":cfg,"url":"http://127.0.0.1:%s"%port,"bundle":os.path.dirname(cfg),"standalone":True})
json.dump(d,open(reg,"w"),indent=2); print("  registered ->",reg)
PY

# ---- done: print the operator-approval steps (launch + persist) and the new node's initial token
TMUXBIN="/opt/homebrew/bin/tmux"
cat <<DONE

== bundle staged: $DEST ==
  Self-contained: code + config + secrets + project + deliverables all under that one folder. Move it
  anywhere (a dedicated drive / new server) and re-run the launch line with the new path.

NEXT (operator-approved):
  1) Launch now on the brain tmux server (inherits SSD/TCC context):
       TMUX_TMPDIR=/tmp $TMUXBIN new-session -d -s cc-$ID "CC_CONFIG=$DEST/cc.config.json python3 $DEST/command-center/server.py"
     then open:  http://127.0.0.1:$PORT
  2) Survive reboot (per-user launchd -- run as the user that will host it; needs that login session):
       cp "$PLIST" ~/Library/LaunchAgents/
       launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.claudefather.$ID.plist
  3) Mesh: add this node to the OTHER family nodes' peers (so they can reach it), e.g. append
       {"id":"$ID","url":"http://127.0.0.1:$PORT"}  (or the tailnet URL) to each peers.json.

  Initial dashboard auth token for '$ID' (store it; this is a brand-new token, not a change):
       $AUTH_TOKEN
DONE

if [ -n "$JSON" ]; then
  python3 - "$ID" "$DEST" "$PORT" "$ROLE" "$PRESET" "$PLIST" "$AUTH_TOKEN" <<'PY'
import json,sys
id,dest,port,role,preset,plist,tok=sys.argv[1:8]
print("CC_NEWINSTANCE_JSON="+json.dumps({"id":id,"bundle":dest,"port":int(port),"role":role,
      "preset":preset,"plist":plist,"url":"http://127.0.0.1:%s"%port,"auth_token":tok,"staged":True}))
PY
fi
