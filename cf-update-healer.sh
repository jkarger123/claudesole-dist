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
RUNUSER="${CF_RUNUSER:-cfrun}"
IMMUTABLE="${CF_IMMUTABLE:-0}"
DIST_GIT="${CF_DIST_GIT:-https://github.com/jkarger123/claudesole-dist.git}"
ts(){ date "+%Y-%m-%d %H:%M:%S"; }
log(){ echo "[$(ts)] $*"; }

[ -d "$CORE/command-center" ] || { log "no core at $CORE -- abort"; exit 0; }

# 1) refresh the signed dist (the clean source)
if [ -d "$DIST/.git" ]; then git -C "$DIST" pull --ff-only >/dev/null 2>&1 || log "WARN dist pull failed (using existing clone)"; else
  git clone --depth 1 "$DIST_GIT" "$DIST" >/dev/null 2>&1 || { log "dist clone failed -- abort this run"; exit 0; }
fi

# 2) VERIFY the dist's signed core manifest with the shipped public key. We trust dist files only if the
#    manifest signature checks out AND each restore target matches its signed hash (no blind copy).
VERDICT="$(python3 - "$DIST" <<'PY'
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
  NOCRYPTO) log "cryptography not installed -- cannot verify dist signature; SKIPPING heal (install: pip3 install --user cryptography)"; exit 0 ;;
  *) log "dist core.sig.json signature INVALID ($VERDICT) -- refusing to heal from an untrusted dist"; exit 0 ;;
esac

# 3) restore every framework file whose live hash != the signed hash, copying ONLY a dist file that itself
#    matches the signed hash. Reports what changed.
[ "$IMMUTABLE" = "1" ] && chflags -R noschg "$CORE" 2>/dev/null || true
CHANGED="$(python3 - "$CORE" "$DIST" <<'PY'
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
  launchctl kickstart -k system/com.claudefather.runtime 2>/dev/null && log "runtime restarted" || log "WARN runtime restart failed"
else
  log "core clean (nothing to heal/update)"
fi
