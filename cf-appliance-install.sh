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
PORT="${CF_PORT:-8800}"                                 # 8800 = the overseer convention (an appliance is role:org)
BRAND="${CF_BRAND:-ClaudeFather}"
# ONE pinned interpreter for the runtime AND the healer. They run as different users (cfrun / root) with
# different HOMEs, so a `pip install --user` by the installing admin is invisible to BOTH. Pin one interpreter,
# install cryptography system-wide for it, and verify as each user -- see step 3.
PY_BIN="${CF_PYTHON:-/usr/bin/python3}"
ACTIVATION_URL="${CF_ACTIVATION_URL:-}"                 # our activation server; enables license self-activation
ACTIVATION_CODE="${CF_ACTIVATION_CODE:-}"               # the single-use CF-XXXX code issued at purchase
IMMUTABLE=0; [ "${1:-}" = "--immutable" ] && IMMUTABLE=1

say(){ printf "\n\033[1m== %s\033[0m\n" "$*"; }
die(){ printf "\033[31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
[ "$(id -u)" = "0" ] || die "run with sudo (need root to create the runtime user + set read-only core ownership)"
command -v git >/dev/null 2>&1 || die "git not found -- install Xcode command line tools: xcode-select --install"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

# ---- 1) dedicated non-admin runtime user ----------------------------------------------------------------
say "1/8 runtime user ($RUNUSER)"
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
say "2/8 bundle layout"
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

# ---- 3) python dependency, SYSTEM-WIDE, verified AS EACH USER THAT NEEDS IT -----------------------------
# The failure this prevents: admin runs `pip3 install --user cryptography`, it lands in the admin's home,
# and neither cfrun (home /var/empty) nor root can see it. The runtime's vault is then DISABLED and the
# healer can never verify the dist -- so updates and self-heal are dead, silently, forever. Verify by REAL
# IMPORT as each user; a pip exit code proves nothing (PEP-668 `--user` exits nonzero without installing).
say "3/8 python dependency (cryptography, system-wide for $PY_BIN)"
[ -x "$PY_BIN" ] || die "pinned interpreter $PY_BIN not found -- set CF_PYTHON to the python3 the plists should use"
if ! "$PY_BIN" -c "import cryptography" >/dev/null 2>&1; then
  echo "  installing cryptography for $PY_BIN (system-wide)..."
  "$PY_BIN" -m pip install --break-system-packages --quiet cryptography >/dev/null 2>&1 \
    || "$PY_BIN" -m pip install --quiet cryptography >/dev/null 2>&1 || true
fi
"$PY_BIN" -c "import cryptography" >/dev/null 2>&1 \
  || die "cryptography STILL not importable by $PY_BIN as root. The vault would be disabled and the healer could never verify an update. Fix: $PY_BIN -m pip install --break-system-packages cryptography"
echo "  root: import ok"
# the runtime user is the one that actually serves the dashboard -- prove IT can import, not just root
if id "$RUNUSER" >/dev/null 2>&1; then
  sudo -u "$RUNUSER" "$PY_BIN" -c "import cryptography" >/dev/null 2>&1 \
    && echo "  $RUNUSER: import ok" \
    || die "cryptography is importable by root but NOT by $RUNUSER -- it was installed into a per-user location. The vault will be DISABLED. Reinstall system-wide: $PY_BIN -m pip install --break-system-packages cryptography"
fi

# ---- 4) appliance cc.config (edition=appliance; writable paths redirected out of core) ------------------
say "4/8 appliance config"
CFG_OUT="$("$PY_BIN" - "$CORE/cc.config.json" "$RUNROOT" "$PORT" "$BRAND" "$ACTIVATION_URL" "$ACTIVATION_CODE" <<'PY'
import json,sys,os,secrets
cfg,runroot,port,brand,act_url,act_code=sys.argv[1:7]
d=json.load(open(cfg)) if os.path.exists(cfg) else {}
d["edition"]="appliance"                 # LOCKED: core-mutating ops refuse; integrity self-heals
d["role"]=d.get("role","org")            # default two-court: this box runs an overseer
d["port"]=int(port); d["brand"]=brand
d["state_dir"]=os.path.join(runroot,"state")
d["deploy_root"]=runroot                 # .env.claudefather + .mcp.json live here (writable), NOT in core
d["deliverables_root"]=os.path.join(runroot,"deliverables")
d["custom_dir"]=os.path.join(runroot,"custom")
d["auto_update"]=False                   # the privileged HEALER updates core (the runtime user can't write it)
# ---- SHIPPING DEFAULTS for a customer box (differ deliberately from a fleet peer's) ----
d["update_verify"]="enforce"             # BLOCK any update that fails signature verification (docs/UPDATES.md
                                         # names enforce as "the target for a packaged product"). A fleet peer
                                         # ships "warn" for staged rollout; a sold box must never apply unverified code.
d["vault_keychain"]=True                 # macOS: wrap the vault key in the login Keychain so it is NOT
                                         # co-located with the ciphertext in a disk image (docs/CREDENTIALS.md)
if act_url:  d["activation_url"]=act_url
if act_code: d["activation_code"]=act_code
# license_enforce is ON only when activation is actually configured. Turning it on with no way to activate
# would brick the box on first boot ("license required" with no path forward) -- exactly the self-inflicted
# outage docs/IP_PROTECTION.md warns about ("ship soft first so we never brick our own fleet").
already_licensed=os.path.isfile(os.path.join(runroot,"license.json"))
d["license_enforce"]=bool(act_url or already_licensed)
# PIN: mint one only if absent. NEVER overwrite an existing auth_token (that is a lockout).
minted=None
if not d.get("auth_token"):
    minted=secrets.token_hex(12); d["auth_token"]=minted
json.dump(d,open(cfg,"w"),indent=2)
print("  wrote",cfg,"(edition=appliance, update_verify=enforce, vault_keychain=on)")
print("  license_enforce:", d["license_enforce"], "" if d["license_enforce"] else "(SOFT -- no activation_url configured; see the note at the end)")
if minted: print("  MINTED_PIN="+minted)
PY
)"
# Show everything EXCEPT the raw PIN line; the PIN is presented once, deliberately, in the final summary.
printf "%s\n" "$CFG_OUT" | grep -v "MINTED_PIN=" || true
MINTED_PIN="$(printf "%s" "$CFG_OUT" | sed -n 's/.*MINTED_PIN=//p')"
LICENSE_ENFORCED="$(printf "%s" "$CFG_OUT" | sed -n 's/.*license_enforce: \([A-Za-z]*\).*/\1/p')"

# ---- 4) ownership + permissions: CORE read-only to cfrun, RUNTIME writable by cfrun ---------------------
say "5/8 lock down permissions"
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
say "6/8 signed dist (self-heal/update source)"
if [ -d "$DIST/.git" ]; then git -C "$DIST" pull --ff-only 2>/dev/null && echo "  pulled"; else
  git clone --depth 1 "$DIST_GIT" "$DIST" 2>/dev/null && echo "  cloned $DIST_GIT" || echo "  WARN: dist clone failed (network?) -- healer will retry"
fi
chown -R root:wheel "$DIST" 2>/dev/null || true

# ---- 6) launchd: runtime (as cfrun) + healer (as root) -------------------------------------------------
say "7/8 launchd services"
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
  <key>ProgramArguments</key><array><string>$PY_BIN</string><string>$CORE/command-center/server.py</string></array>
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
  <key>EnvironmentVariables</key><dict><key>CF_CORE</key><string>$CORE</string><key>CF_DIST</key><string>$DIST</string><key>CF_RUNROOT</key><string>$RUNROOT</string><key>CF_RUNUSER</key><string>$RUNUSER</string><key>CF_IMMUTABLE</key><string>$IMMUTABLE</string><key>CF_PYTHON</key><string>$PY_BIN</string></dict>
  <key>StandardOutPath</key><string>$RUNROOT/state/healer.log</string>
  <key>StandardErrorPath</key><string>$RUNROOT/state/healer.log</string>
</dict></plist>
PLIST
chmod 644 "$RUNTIME_PLIST" "$HEALER_PLIST"; chown root:wheel "$RUNTIME_PLIST" "$HEALER_PLIST"
launchctl bootout system "$RUNTIME_PLIST" 2>/dev/null || true
launchctl bootout system "$HEALER_PLIST" 2>/dev/null || true
launchctl bootstrap system "$RUNTIME_PLIST" 2>/dev/null && echo "  runtime service up (as $RUNUSER)" || echo "  WARN: runtime bootstrap (already loaded?)"
launchctl bootstrap system "$HEALER_PLIST" 2>/dev/null && echo "  healer service up (as root, every 30m)" || true

# ---- 8) verify -- ASSERT the hardening actually holds, do not just report a 200 ------------------------
# An installer that says "DONE" without proving the read-only core is worse than useless: it manufactures
# confidence. Each check below is a claim this script makes; if a claim fails, say so loudly.
say "8/8 verify"
sleep 6
FAILED=0
H="$(curl -s --max-time 8 http://localhost:$PORT/api/health 2>/dev/null || true)"
if printf "%s" "$H" | grep -q '"edition"[[:space:]]*:[[:space:]]*"appliance"'; then
  echo "  [ok]   health: edition=appliance"
else
  echo "  [FAIL] health did not report edition=appliance -- got: ${H:-<no response; check $RUNROOT/state/runtime.err.log>}"; FAILED=1
fi

# THE assertion: the runtime user must NOT be able to write core. This is the whole enforcement boundary.
if sudo -u "$RUNUSER" touch "$CORE/command-center/server.py" 2>/dev/null; then
  echo "  [FAIL] $RUNUSER CAN WRITE THE CORE -- the appliance is NOT hardened. Do not ship this box."; FAILED=1
else
  echo "  [ok]   $RUNUSER cannot write core (permission denied, as intended)"
fi

# the vault must be usable BY THE RUNTIME USER, not merely by root
if sudo -u "$RUNUSER" "$PY_BIN" -c "import cryptography" >/dev/null 2>&1; then
  echo "  [ok]   $RUNUSER can import cryptography (vault enabled)"
else
  echo "  [FAIL] $RUNUSER cannot import cryptography -- the credential VAULT will be DISABLED."; FAILED=1
fi

# force one healer pass and read its beacon -- proves updates/self-heal actually work rather than assuming it
launchctl kickstart -k system/com.claudefather.healer >/dev/null 2>&1 || true
sleep 8
if [ -f "$RUNROOT/state/_healer_health.json" ]; then
  HS="$("$PY_BIN" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('status','?'),'--',d.get('reason','')[:120])" "$RUNROOT/state/_healer_health.json" 2>/dev/null || echo "?")"
  case "$HS" in
    ok*) echo "  [ok]   healer: $HS" ;;
    *)   echo "  [FAIL] healer: $HS"; FAILED=1 ;;
  esac
else
  echo "  [FAIL] healer left no health beacon -- it did not complete a run. Check $RUNROOT/state/healer.log"; FAILED=1
fi

# full declared-dependency sweep, including the cfrun + root interpreters
if [ -f "$CORE/cf-preflight" ]; then
  echo
  bash "$CORE/cf-preflight" --appliance --quiet || FAILED=1
fi

echo
if [ "$FAILED" = "0" ]; then
  printf "\033[32m\033[1mAPPLIANCE READY\033[0m -- every hardening assertion passed.\n"
else
  printf "\033[31m\033[1mAPPLIANCE NOT READY\033[0m -- one or more assertions FAILED above. Fix them before handing this box over.\n"
fi
echo
echo "  Dashboard:  http://localhost:$PORT/"
if [ -n "$MINTED_PIN" ]; then
  echo "  LOGIN PIN:  $MINTED_PIN     <-- write this down NOW; it is shown once and is not recoverable from the UI."
else
  echo "  LOGIN PIN:  (kept the existing auth_token in $CORE/cc.config.json -- unchanged)"
fi
echo "  Core:       $CORE      (root:wheel, read-only to $RUNUSER)"
echo "  Runtime:    $RUNROOT   ($RUNUSER-owned: state, deliverables, custom, secrets, vault, license)"
echo "  Updates:    signed dist every 30m via com.claudefather.healer (update_verify=enforce)"
echo
if [ "${LICENSE_ENFORCED:-False}" = "True" ]; then
  echo "  License:    ENFORCED. The box self-activates on boot against $ACTIVATION_URL."
else
  echo "  License:    SOFT (not enforced) -- no CF_ACTIVATION_URL was given, so enforcing would have locked"
  echo "              this box out with no way to activate. To enforce later:"
  echo "                1. on this box:  curl -s http://localhost:$PORT/api/license | grep fingerprint"
  echo "                2. on Mission Control:  POST /api/license-issue {fingerprint, customer, days}"
  echo "                3. back here:           POST /api/license-install <the signed license>"
  echo "                4. set \"license_enforce\": true in $CORE/cc.config.json and restart the runtime."
  echo "              Or re-run this installer with CF_ACTIVATION_URL=... CF_ACTIVATION_CODE=CF-XXXX-..."
fi
echo
echo "  Secrets go in the VAULT (dashboard -> Vault), not in files. $RUNROOT/.env.claudefather is bootstrap-only."
echo "  Codebase/IP protection (license + obfuscation) is a separate layer -- see docs/IP_PROTECTION.md."
[ "$FAILED" = "0" ] || exit 1
