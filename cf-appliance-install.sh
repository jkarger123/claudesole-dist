#!/usr/bin/env bash
# ============================================================================================================
# cf-appliance-install.sh -- turn a fresh Mac into a HARDENED ClaudeFather APPLIANCE.
#
# What it does (the real "can't modify core" enforcement -- see docs/HARDENING.md):
#   1. Creates a dedicated NON-ADMIN runtime user ("cfrun") that owns NOTHING in the core.
#   2. Installs the framework bundle CORE owned by root, READ-ONLY to cfrun (mode r-x). With the runtime
#      running as cfrun under --dangerously-skip-permissions, the agent literally cannot write server.py
#      (the filesystem returns EPERM) -- the OS is the enforcement boundary, not Claude Code.
#   3. Puts ALL writable state (state/, deliverables/, custom/, secrets) OUTSIDE the core, owned by cfrun.
#   4. Marks this install edition=appliance (locked: core-mutating ops refuse; integrity self-heals).
#   5. Installs TWO launchd jobs: the RUNTIME (as cfrun) + a privileged HEALER/UPDATER (as root) that pulls
#      the signed dist and restores any drifted/updated core file -- so updates + self-heal run with the
#      privilege the read-only runtime intentionally lacks.
#
# Run as an ADMIN user, with sudo:   sudo bash cf-appliance-install.sh [--immutable]
#   --immutable   also chflags(schg) the core so even root must deliberately unlock to change it.
#
# Idempotent: safe to re-run (it reconciles users/perms/launchd). Honest about its limits: a determined
# owner with root can still copy + reverse plaintext Python -- codebase IP protection is a SEPARATE layer
# (license activation + obfuscation; see docs/IP_PROTECTION.md). This script stops the AGENT + casual tamper.
# ============================================================================================================
set -uo pipefail

RUNUSER="${CF_RUNUSER:-cfrun}"
CORE="${CF_CORE:-/Library/ClaudeFather/core}"           # the read-only framework bundle
RUNROOT="${CF_RUNROOT:-/Library/ClaudeFather/runtime}"  # writable: state, deliverables, custom, secrets
DIST="${CF_DIST:-/Library/ClaudeFather/dist}"           # the signed public dist clone (healer pulls this)
DIST_GIT="${CF_DIST_GIT:-https://github.com/jkarger123/claudesole-dist.git}"
PORT="${CF_PORT:-8800}"
BRAND="${CF_BRAND:-ClaudeFather}"
IMMUTABLE=0; [ "${1:-}" = "--immutable" ] && IMMUTABLE=1

say(){ printf "\n\033[1m== %s\033[0m\n" "$*"; }
die(){ printf "\033[31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
[ "$(id -u)" = "0" ] || die "run with sudo (need root to create the runtime user + set read-only core ownership)"
command -v git >/dev/null 2>&1 || die "git not found -- install Xcode command line tools: xcode-select --install"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

# ---- 1) dedicated non-admin runtime user ----------------------------------------------------------------
say "1/7 runtime user ($RUNUSER)"
if id "$RUNUSER" >/dev/null 2>&1; then
  echo "  exists"
else
  # find a free service-range UID (>= 300, below the 500 login range is fine for a daemon account)
  UID_N=300; while dscl . -list /Users UniqueID 2>/dev/null | awk '{print $2}' | grep -qx "$UID_N"; do UID_N=$((UID_N+1)); done
  sysadminctl -addUser "$RUNUSER" -fullName "ClaudeFather Runtime" -UID "$UID_N" -home "/var/empty" -shell "/usr/bin/false" -password "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" 2>/dev/null \
    || dscl . -create "/Users/$RUNUSER" >/dev/null 2>&1
  dscl . -create "/Users/$RUNUSER" IsHidden 1 2>/dev/null
  echo "  created uid=$UID_N (hidden, non-admin, no shell)"
fi
# ensure NOT in admin
dseditgroup -o edit -d "$RUNUSER" -t user admin 2>/dev/null || true

# ---- 2) lay out the bundle: CORE (read-only) + RUNTIME (writable) ---------------------------------------
say "2/7 bundle layout"
SRC="$(cd "$(dirname "$0")" && pwd)"                    # this script ships INSIDE the framework bundle
[ -f "$SRC/command-center/server.py" ] || die "run this from inside a ClaudeFather bundle (no command-center/server.py next to the script)"
mkdir -p "$CORE" "$RUNROOT"/{state,deliverables,custom} "$(dirname "$DIST")"
# copy the framework into CORE (rsync preserves a clean snapshot; excludes any local state/secrets)
rsync -a --delete \
  --exclude '.git' --exclude 'instances' --exclude 'data' --exclude 'deliverables' \
  --exclude '.env.claudefather' --exclude '.mcp.json' --exclude '.vault*' --exclude '.superadmin_ed25519' \
  --exclude '_*.json' --exclude '*.log' \
  "$SRC"/ "$CORE"/ || die "rsync of framework into $CORE failed"
# pre-create the writable secret/config files OUTSIDE the read-only core
touch "$RUNROOT/.env.claudefather" "$RUNROOT/.mcp.json"
[ -s "$RUNROOT/.mcp.json" ] || echo '{"mcpServers":{}}' > "$RUNROOT/.mcp.json"
echo "  core=$CORE  runtime=$RUNROOT"

# ---- 3) appliance cc.config (edition=appliance; writable paths redirected out of core) ------------------
say "3/7 appliance config"
python3 - "$CORE/cc.config.json" "$RUNROOT" "$PORT" "$BRAND" <<'PY'
import json,sys,os
cfg,runroot,port,brand=sys.argv[1:5]
d=json.load(open(cfg)) if os.path.exists(cfg) else {}
d["edition"]="appliance"                 # LOCKED: core-mutating ops refuse; integrity self-heals
d["role"]=d.get("role","org")            # default two-court: this box runs an overseer
d["port"]=int(port); d["brand"]=brand
d["state_dir"]=os.path.join(runroot,"state")
d["deploy_root"]=runroot                 # .env.claudefather + .mcp.json live here (writable), NOT in core
d["deliverables_root"]=os.path.join(runroot,"deliverables")
d["custom_dir"]=os.path.join(runroot,"custom")
d["auto_update"]=False                   # the privileged HEALER updates core (the runtime user can't write it)
d.setdefault("project_name",brand); d.setdefault("project_root",os.path.join(runroot,"custom"))
json.dump(d,open(cfg,"w"),indent=2)
print("  wrote",cfg,"(edition=appliance)")
PY

# ---- 4) ownership + permissions: CORE read-only to cfrun, RUNTIME writable by cfrun ---------------------
say "4/7 lock down permissions"
chown -R root:wheel "$CORE"
chmod -R go-w "$CORE"                                   # no group/other write anywhere in core
find "$CORE" -type d -exec chmod 755 {} \;             # dirs traversable + readable, NOT writable by others
find "$CORE" -type f -exec chmod 644 {} \;
find "$CORE" -type f \( -name '*.sh' -o -name 'cc-task' -o -name '*.command' \) -exec chmod 755 {} \;
chown -R "$RUNUSER":staff "$RUNROOT"
chmod -R u+rwX,go-rwx "$RUNROOT"
chmod 600 "$RUNROOT/.env.claudefather"
echo "  core: root:wheel r-x (cfrun cannot write)   runtime: $RUNUSER rwx"
if [ "$IMMUTABLE" = "1" ]; then chflags -R schg "$CORE" 2>/dev/null && echo "  core: chflags schg (system-immutable; healer unlocks during update)"; fi

# ---- 5) signed dist clone (the healer's clean source) --------------------------------------------------
say "5/7 signed dist (self-heal/update source)"
if [ -d "$DIST/.git" ]; then git -C "$DIST" pull --ff-only 2>/dev/null && echo "  pulled"; else
  git clone --depth 1 "$DIST_GIT" "$DIST" 2>/dev/null && echo "  cloned $DIST_GIT" || echo "  WARN: dist clone failed (network?) -- healer will retry"
fi
chown -R root:wheel "$DIST" 2>/dev/null || true

# ---- 6) launchd: runtime (as cfrun) + healer (as root) -------------------------------------------------
say "6/7 launchd services"
RUNTIME_PLIST=/Library/LaunchDaemons/com.claudefather.runtime.plist
HEALER_PLIST=/Library/LaunchDaemons/com.claudefather.healer.plist
cat > "$RUNTIME_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.claudefather.runtime</string>
  <key>UserName</key><string>$RUNUSER</string>
  <key>WorkingDirectory</key><string>$CORE/command-center</string>
  <key>EnvironmentVariables</key><dict><key>CC_CONFIG</key><string>$CORE/cc.config.json</string><key>CC_HOME</key><string>$CORE</string></dict>
  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>$CORE/command-center/server.py</string></array>
  <key>KeepAlive</key><true/><key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$RUNROOT/state/runtime.out.log</string>
  <key>StandardErrorPath</key><string>$RUNROOT/state/runtime.err.log</string>
</dict></plist>
PLIST
cat > "$HEALER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.claudefather.healer</string>
  <key>UserName</key><string>root</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$CORE/cf-update-healer.sh</string></array>
  <key>StartInterval</key><integer>1800</integer><key>RunAtLoad</key><true/>
  <key>EnvironmentVariables</key><dict><key>CF_CORE</key><string>$CORE</string><key>CF_DIST</key><string>$DIST</string><key>CF_RUNUSER</key><string>$RUNUSER</string><key>CF_IMMUTABLE</key><string>$IMMUTABLE</string></dict>
  <key>StandardOutPath</key><string>$RUNROOT/state/healer.log</string>
  <key>StandardErrorPath</key><string>$RUNROOT/state/healer.log</string>
</dict></plist>
PLIST
chmod 644 "$RUNTIME_PLIST" "$HEALER_PLIST"; chown root:wheel "$RUNTIME_PLIST" "$HEALER_PLIST"
launchctl bootout system "$RUNTIME_PLIST" 2>/dev/null || true
launchctl bootout system "$HEALER_PLIST" 2>/dev/null || true
launchctl bootstrap system "$RUNTIME_PLIST" 2>/dev/null && echo "  runtime service up (as $RUNUSER)" || echo "  WARN: runtime bootstrap (already loaded?)"
launchctl bootstrap system "$HEALER_PLIST" 2>/dev/null && echo "  healer service up (as root, every 30m)" || true

# ---- 7) verify ----------------------------------------------------------------------------------------
say "7/7 verify"
sleep 6
H="$(curl -s --max-time 6 http://localhost:$PORT/api/health 2>/dev/null || true)"
echo "  health: ${H:-<no response yet -- check $RUNROOT/state/runtime.err.log>}"
echo
echo "DONE. Appliance core is READ-ONLY to the runtime user ($RUNUSER); updates + self-heal run via the"
echo "privileged healer. Set this box's PIN/secrets in $RUNROOT/.env.claudefather (cfrun-owned, 0600),"
echo "then: sudo launchctl kickstart -k system/com.claudefather.runtime"
echo "Codebase/IP protection (license activation + obfuscation) is a separate layer -- see docs/IP_PROTECTION.md."
