"""
ClaudeFather -- the FOCUS / INTENT engine ("context follows you", docs/VISION.md Phase 3).

Reads a lightweight activity SIGNAL (what app/file/page you're on), classifies it to a SUBJECT in your
context graph (this client/project), and -- when confident + stable -- lets the system HOME to it (assemble
the right context, brief the session). The point: you never navigate to the right context; it comes to you.

Privacy is structural, via a TRUST DIAL (capture level), default OFF -- nothing is read until you opt in:
  off     -> nothing (engine idle)
  app     -> frontmost app + bundle id only (NO macOS permission needed)   [the safe default-on]
  context -> + window title + active browser URL (needs Accessibility/Automation; degrades silently)
  deep    -> (reserved) periodic screen/OCR -- not implemented here
Everything is local, stdlib-only (subprocess to macOS lsappinfo/osascript), and reads only; it never types,
sends, or stores pixels. The richer signals simply stay empty until the user grants the one-time TCC prompt.
"""
import subprocess, re, time

_CFG = {}          # {capture, rules:{substr->subject}, autobrief}
_LAST_TITLE_OK = [True]   # remember whether AX/Automation worked (so we don't spam failing osascript)

def init(cfg=None):
    if cfg: _CFG.update({k: v for k, v in (cfg or {}).items() if v is not None})
    return {"ok": True, "capture": capture()}

def capture():
    return (_CFG.get("capture") or "off").lower()

def _sh(args, timeout=4):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception: return ""

def _quote_val(s):
    m = re.search(r'=\s*"([^"]*)"', s) or re.search(r'"([^"]+)"\s*$', s)
    return (m.group(1) if m else s).strip().strip('"')

def read_signal(level=None):
    """Return the current activity signal at the given capture level. Empty dict when off / nothing readable."""
    level = (level or capture())
    if level in ("off", "", None): return {}
    sig = {}
    front = _sh(["lsappinfo", "front"])
    if front:
        sig["app"] = _quote_val(_sh(["lsappinfo", "info", "-only", "name", front]))
        sig["bundle"] = _quote_val(_sh(["lsappinfo", "info", "-only", "bundleid", front]))
    if level in ("context", "deep"):
        title = _sh(["osascript", "-e", 'tell application "System Events" to tell (first process whose frontmost is true) to get value of attribute "AXTitle" of front window'])
        if title and "execution error" not in title.lower() and "-1743" not in title:
            sig["title"] = title; _LAST_TITLE_OK[0] = True
        else:
            _LAST_TITLE_OK[0] = False   # not granted -> remember, surface in status so the UI can prompt for the grant
        app = (sig.get("app") or "")
        low = app.lower()
        try:
            if any(b in low for b in ("chrome", "brave", "edge", "arc", "chromium", "vivaldi")):
                u = _sh(["osascript", "-e", 'tell application "%s" to get URL of active tab of front window' % app.replace('"', "")])
            elif "safari" in low:
                u = _sh(["osascript", "-e", 'tell application "Safari" to get URL of current tab of front window'])
            else: u = ""
            if u and "error" not in u.lower() and u.startswith("http"): sig["url"] = u
        except Exception: pass
    return sig

def classify(signal, subjects, rules=None):
    """Map a signal -> best subject. subjects=[{name,keys[]}]; rules={substr: subject_name} (from config,
    e.g. a domain or app -> a client). Returns {subject, confidence, why} (subject None if no match)."""
    text = " ".join(str(signal.get(k, "")) for k in ("app", "title", "url")).lower()
    if not text.strip(): return {"subject": None, "confidence": 0.0, "why": "no signal"}
    for pat, subj in (rules or {}).items():
        if pat and str(pat).lower() in text:
            return {"subject": subj, "confidence": 0.95, "why": "rule:%s" % pat}
    best, score = None, 0.0
    for s in subjects or []:
        for token in [s.get("name", "")] + (s.get("keys") or []):
            t = str(token).lower().strip()
            if len(t) < 3: continue
            if t in text:
                sc = 0.6 + min(0.3, len(t) / 40.0)
                if sc > score: best, score = s.get("name"), sc
    return {"subject": best, "confidence": round(score, 2), "why": "lexical"} if best else {"subject": None, "confidence": 0.0, "why": "no match"}

def title_grant_ok():
    """Did the last context-level read get the window title? (False => Accessibility/Automation not granted.)"""
    return bool(_LAST_TITLE_OK[0])

# --- segmentation: only commit a NEW focus after it's stable (debounce + hysteresis + min-dwell) ----------
class Segmenter:
    def __init__(self, min_dwell=2.0, switch_margin=0.15):
        self.cur = None; self.cur_since = 0.0
        self.cand = None; self.cand_since = 0.0
        self.min_dwell = min_dwell; self.switch_margin = switch_margin
    def update(self, subject, confidence, now=None):
        now = now or time.time()
        if subject == self.cur:
            self.cand = None; return self.cur, False
        if subject != self.cand:
            self.cand = subject; self.cand_since = now; return self.cur, False
        # candidate persisted long enough -> commit the switch (hysteresis: needs to hold for min_dwell)
        if now - self.cand_since >= self.min_dwell and (confidence >= self.switch_margin or subject is None):
            self.cur, self.cur_since, self.cand = subject, now, None
            return self.cur, True
        return self.cur, False
