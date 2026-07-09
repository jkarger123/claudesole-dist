#!/usr/bin/env bash
# ============================================================================
# Enterprise auto-backup: project monorepo -> private GitHub.
# ADDITIVE ONLY: secret-gate -> add -> commit -> push. It NEVER runs a
# destructive git op (no reset --hard / clean / checkout / rm), so it cannot
# lose the intentionally-dirty working tree -- it only ever SAVES state.
# Usage: git-backup.sh [auto|manual]
# ============================================================================
set -uo pipefail
CC_HOME="${CC_HOME:-$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)}"   # this bundle's root (portable)
CC="$CC_HOME/command-center"
# Resolve WHICH instance we are from CC_CONFIG (else the root config) -- co-located instances share this script,
# so keying off CC_HOME alone made every instance back up the ROOT repo and stomp ONE shared state file. Now both
# REPO and STATE derive from the instance's own config (state_dir matches server.py's STATE_DIR). (deep-audit 0.6)
CFG="${CC_CONFIG:-$CC_HOME/cc.config.json}"
STATE_DIR="$(python3 -c "import json,os;c=json.load(open('$CFG'));print(os.path.expanduser(c.get('state_dir') or '$CC'))" 2>/dev/null || echo "$CC")"
STATE="$STATE_DIR/_backup_state.json"
LOG="$CC_HOME/data/backup.log"
# Repo to back up = this instance's project_root (its cc.config); override with the REPO env var.
REPO="${REPO:-$(python3 -c "import json;print(json.load(open('$CFG')).get('project_root',''))" 2>/dev/null)}"
SCAN="$CC/git-backup-secretscan.py"
MODE="${1:-auto}"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export GIT_TERMINAL_PROMPT=0          # never hang waiting for a credential prompt -> fail fast instead
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
mkdir -p "$(dirname "$LOG")"
ts(){ date -u +%FT%TZ; }
log(){ echo "$(ts) [$MODE] $*" >> "$LOG"; }

state(){ # $1 status  $2 message  $3 commit(optional)  $4 pushed(1/0/'')
  python3 - "$REPO" "$STATE" "$1" "$2" "${3:-}" "${4:-}" "$MODE" <<'PY'
import json,sys,os,subprocess,time
repo,sp,status,msg,commit,pushed,mode=sys.argv[1:8]
def g(*a):
    try: return subprocess.run(["git","-C",repo]+list(a),capture_output=True,text=True,timeout=30).stdout.strip()
    except Exception: return ""
def ksize(p):
    try: return int(subprocess.run(["du","-sk",p],capture_output=True,text=True,timeout=30).stdout.split()[0])*1024
    except Exception: return 0
d=json.load(open(sp)) if os.path.exists(sp) else {}
now=time.time()
d["last_run"]=now; d["last_status"]=status; d["last_message"]=msg; d["last_mode"]=mode
if status in("ok","clean"): d["last_success"]=now
if commit: d["last_commit"]=commit
if pushed=="1": d["last_push"]=now; d["last_push_ok"]=True
elif pushed=="0": d["last_push_ok"]=False
d["uncommitted"]=len([l for l in g("status","--porcelain").splitlines() if l])
try: d["ahead"]=int(g("rev-list","--count","@{u}..HEAD") or 0)
except Exception: d["ahead"]=0
d["tracked"]=len(g("ls-files").splitlines())
d["git_size"]=ksize(os.path.join(repo,".git"))
d["head"]=g("log","-1","--format=%h  %cd  %s","--date=iso")
d["remote"]=g("remote","get-url","origin")
json.dump(d,open(sp,"w"),indent=2)
PY
}

cd "$REPO" || { log "repo missing"; state error "repo dir missing"; exit 1; }
log "=== backup start ==="

# 1) SECRET + SIZE GATE -- before staging anything. Abort the whole run if anything sensitive/oversize.
if ! python3 "$SCAN" "$REPO" >>"$LOG" 2>&1; then
  log "BLOCKED by secret/size gate -- nothing staged, nothing pushed"
  state blocked "secret or oversize file detected -- backup aborted (see backup.log)"
  exit 3
fi

# 2) stage everything (additive; respects .gitignore)
git add -A 2>>"$LOG"

# 3) nothing new staged?
if git diff --cached --quiet 2>/dev/null; then
  if [ "$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)" -gt 0 ]; then
    if git push >>"$LOG" 2>&1; then log "no new changes; pushed pending ahead-commits"; state ok "pushed pending commits (no new file changes)" "" 1
    else log "push failed (ahead)"; state warn "local commits exist but push failed (auth/network)" "" 0; exit 4; fi
  else
    log "nothing to back up (in sync)"; state clean "already up to date with GitHub"
  fi
  exit 0
fi

# 4) commit (timestamped, identifiable)
N=$(git diff --cached --name-only | wc -l | tr -d ' ')
MSG="auto-backup $(ts) (${N} files, ${MODE})"
if ! git commit -q -m "$MSG" 2>>"$LOG"; then log "commit failed"; state error "git commit failed"; exit 5; fi
COMMIT=$(git rev-parse --short HEAD)
log "committed $COMMIT ($N files)"

# 5) push to GitHub
if git push >>"$LOG" 2>&1; then
  log "pushed $COMMIT OK"
  state ok "backed up ${N} files (${COMMIT}) and pushed to GitHub" "$COMMIT" 1
else
  log "committed $COMMIT locally but PUSH FAILED (auth/network)"
  state warn "committed ${COMMIT} locally; push failed (will retry next run)" "$COMMIT" 0
  exit 4
fi
log "=== backup done ==="
