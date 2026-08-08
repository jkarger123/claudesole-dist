#!/usr/bin/env bash
# ============================================================================================================
# cf-update-healer.sh -- the PRIVILEGED update + self-heal job for a hardened appliance (runs as root via
# launchd com.claudefather.healer, every 30 min). The runtime server runs as a non-admin user with a
# READ-ONLY core, so it cannot update or self-heal itself -- this job does, with the privilege it lacks.
#
# Each run: pull the signed dist -> VERIFY the signed core manifest (Ed25519 vs superadmin.pub) -> restore
# any drifted/updated framework file from the verified dist -> reset core ownership/perms back to read-only
# -> restart the runtime if anything changed. This is update + self-heal in one: a customer edit to core is
# overwritten back to the signed version on the next run.
# ============================================================================================================
set -uo pipefail
CORE="${CF_CORE:-/Library/ClaudeFather/core}"
DIST="${CF_DIST:-/Library/ClaudeFather/dist}"
RUNROOT="${CF_RUNROOT:-/Library/ClaudeFather/runtime}"
RUNUSER="${CF_RUNUSER:-cfrun}"
IMMUTABLE="${CF_IMMUTABLE:-0}"
DIST_GIT="${CF_DIST_GIT:-https://github.com/jkarger123/claudesole-dist.git}"
# PIN the interpreter. This job runs as ROOT while the runtime runs as cfrun -- if they resolve different
# pythons (PATH python3 vs the plist's /usr/bin/python3), `cryptography` can be importable by one and not the
# other, and this job goes silently dead while the dashboard shows a green vault. One pinned interpreter,
# installed system-wide, is the whole fix. Must match the runtime plist's ProgramArguments.
PY_BIN="${CF_PYTHON:-/usr/bin/python3}"
ts(){ date "+%Y-%m-%d %H:%M:%S"; }
log(){ echo "[$(ts)] $*"; }

# HEALTH BEACON: the server reads this and Doctor turns RED on degraded/stale. A job that can silently stop
# working must leave evidence that it stopped -- "no news" must never read as "healthy".
HEALTH="$RUNROOT/state/_healer_health.json"
beacon(){  # beacon <status> <reason>
  mkdir -p "$(dirname "$HEALTH")" 2>/dev/null || true
  cat > "$HEALTH" 2>/dev/null <<JSON
{"status":"$1","reason":"$2","ts":$(date +%s),"python":"$PY_BIN","core":"$CORE","dist":"$DIST"}
JSON
  chmod 644 "$HEALTH" 2>/dev/null || true
}

[ -d "$CORE/command-center" ] || { log "no core at $CORE -- abort"; beacon degraded "no core at $CORE"; exit 1; }
[ -x "$PY_BIN" ] || { log "FATAL pinned interpreter $PY_BIN not executable"; beacon degraded "pinned interpreter $PY_BIN missing"; exit 1; }

# 1) refresh the signed dist (the clean source)
if [ -d "$DIST/.git" ]; then git -C "$DIST" pull --ff-only >/dev/null 2>&1 || log "WARN dist pull failed (using existing clone)"; else
  git clone --depth 1 "$DIST_GIT" "$DIST" >/dev/null 2>&1 || { log "dist clone failed -- abort this run"; beacon degraded "cannot reach the signed dist ($DIST_GIT) -- no updates or self-heal until network/git is restored"; exit 1; }
fi

# 2) VERIFY the dist's signed core manifest with the shipped public key. We trust dist files only if the
#    manifest signature checks out AND each restore target matches its signed hash (no blind copy).
VERDICT="$("$PY_BIN" - "$DIST" <<'PY'
import json,os,sys,base64,hashlib
dist=sys.argv[1]
try:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
except Exception:
    print("NOCRYPTO"); sys.exit(0)
try:
    pub=load_pem_public_key(open(os.path.join(dist,"superadmin.pub"),"rb").read())
    doc=json.load(open(os.path.join(dist,"core.sig.json")))
    payload=doc["payload"]; sig=base64.b64decode(doc["sig"])
    canon=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    pub.verify(sig,canon)                      # raises on bad signature
    print("OK")
except Exception as e:
    print("BAD:"+str(e)[:80])
PY
)"
case "$VERDICT" in
  OK) : ;;
  NOCRYPTO)
    # THE silent-death case (was: log one line + exit 0). Without cryptography this job can never verify the
    # dist, so it can never update or self-heal -- forever, every 30 minutes, while the box looks fine.
    # It must be LOUD and it must be actionable: `--user` installs are invisible here because this runs as
    # root with a different HOME, so the fix is always a SYSTEM-WIDE install for the PINNED interpreter.
    log "FATAL: $PY_BIN cannot import cryptography -- signature verification is impossible, so NO update and"
    log "       NO self-heal will EVER run on this box until it is fixed. This is not a transient error."
    log "       Fix (system-wide, for THIS interpreter -- a --user install will NOT be visible to root/cfrun):"
    log "         sudo $PY_BIN -m pip install --break-system-packages cryptography"
    log "       Verify:  sudo $PY_BIN -c 'import cryptography'   AND   sudo -u $RUNUSER $PY_BIN -c 'import cryptography'"
    beacon degraded "$PY_BIN cannot import cryptography -- updates and self-heal are DEAD until fixed: sudo $PY_BIN -m pip install --break-system-packages cryptography"
    exit 1 ;;
  *)
    log "dist core.sig.json signature INVALID ($VERDICT) -- refusing to heal from an untrusted dist"
    beacon degraded "dist signature INVALID ($VERDICT) -- refusing to heal from an untrusted source"
    exit 1 ;;
esac

# 3) restore every framework file whose live hash != the signed hash, copying ONLY a dist file that itself
#    matches the signed hash. Reports what changed.
[ "$IMMUTABLE" = "1" ] && chflags -R noschg "$CORE" 2>/dev/null || true
CHANGED="$("$PY_BIN" - "$CORE" "$DIST" <<'PY'
import json,os,sys,hashlib,shutil
core,dist=sys.argv[1],sys.argv[2]
payload=json.load(open(os.path.join(dist,"core.sig.json")))["payload"]
def h(p):
    try: return hashlib.sha256(open(p,"rb").read()).hexdigest()
    except Exception: return None
changed=[]
for rel,want in payload.get("files",{}).items():
    cp=os.path.join(core,rel); dp=os.path.join(dist,rel)
    if h(cp)==want: continue                  # already clean
    if h(dp)!=want: continue                  # dist copy doesn't match the signed hash -> don't trust it
    os.makedirs(os.path.dirname(cp),exist_ok=True)
    shutil.copy2(dp,cp); changed.append(rel)
print("\n".join(changed))
PY
)"

# 4) reset ownership/perms back to read-only-to-runtime + re-lock immutable
chown -R root:wheel "$CORE"
find "$CORE" -type d -exec chmod 755 {} \; ; find "$CORE" -type f -exec chmod 644 {} \;
find "$CORE" -type f \( -name '*.sh' -o -name 'cc-task' -o -name '*.command' \) -exec chmod 755 {} \;
[ "$IMMUTABLE" = "1" ] && chflags -R schg "$CORE" 2>/dev/null || true

# 5) restart the runtime only if something actually changed
if [ -n "$CHANGED" ]; then
  N=$(printf "%s\n" "$CHANGED" | grep -c .)
  log "restored/updated $N core file(s): $(printf "%s " $CHANGED | cut -c1-200)"
  beacon ok "restored/updated $N core file(s)"
  launchctl kickstart -k system/com.claudefather.runtime 2>/dev/null && log "runtime restarted" || log "WARN runtime restart failed"
else
  log "core clean (nothing to heal/update)"
  beacon ok "core clean"
fi
