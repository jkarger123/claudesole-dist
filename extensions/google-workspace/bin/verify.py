"""Read-only verification that the stored headless token drives Gmail/Calendar/Drive.

Env (same fallbacks as mint_token.py -- no hand-editing):
  ACCOUNT      account@gmail.com that was minted       (required)
  SECRETS_DIR  dir holding tokens/                      (default: ../secrets next to bin/)

Run:  uv run --with workspace-mcp python -u verify.py
"""
import os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.environ.get("SECRETS_DIR") or os.path.normpath(os.path.join(HERE, "..", "secrets"))
CREDS_DIR = os.path.join(SECRETS, "tokens")
EMAIL = os.environ.get("ACCOUNT", "")
if not EMAIL:
    sys.exit("ERROR: set ACCOUNT=the-account@gmail.com")
os.environ["WORKSPACE_MCP_CREDENTIALS_DIR"] = CREDS_DIR

from auth.credential_store import LocalDirectoryCredentialStore
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

store = LocalDirectoryCredentialStore(base_dir=CREDS_DIR)
creds = store.get_credential(EMAIL)
if not creds.valid:
    creds.refresh(Request())
    store.store_credential(EMAIL, creds)  # persist refreshed access token
print("AUTH OK  account:", EMAIL, "| token refreshed:", bool(creds.token))

# --- scope visibility (CCR ccr-1782880284369): show what this token ACTUALLY authorizes + flag missing write
#     services so the setup flow never assumes a capability the token doesn't have ---
_sc = list(getattr(creds, "scopes", None) or [])
_has = lambda sub: any(sub in s for s in _sc)
print("SCOPES:", len(_sc), "| sheets:", _has("spreadsheets"), "docs:", _has("documents"),
      "forms:", _has("forms.body"), "gmail.send:", _has("gmail.send"))
for _svc, _sub in (("sheets", "spreadsheets"), ("docs", "documents"), ("forms", "forms.body")):
    if not _has(_sub):
        print("  note:", _svc, "NOT granted -- in-place editing / Forms will 403 until re-mint (run bin/enable-services.sh)")

# --- Gmail: 3 most recent unread subjects ---
print("\n[GMAIL] 3 most recent unread:")
g = build("gmail", "v1", credentials=creds, cache_discovery=False)
msgs = g.users().messages().list(userId="me", q="is:unread", maxResults=3).execute().get("messages", [])
if not msgs:
    print("  (no unread messages)")
for m in msgs:
    md = g.users().messages().get(userId="me", id=m["id"], format="metadata",
                                  metadataHeaders=["Subject", "From"]).execute()
    h = {x["name"]: x["value"] for x in md["payload"]["headers"]}
    print("  -", (h.get("Subject") or "(no subject)")[:70], "|", (h.get("From") or "")[:35])

# --- Calendar: list calendars + today's events on primary ---
print("\n[CALENDAR] calendars + today:")
c = build("calendar", "v3", credentials=creds, cache_discovery=False)
cals = c.calendarList().list().execute().get("items", [])
print("  calendars visible:", len(cals), "->", ", ".join(cl.get("summary", "?") for cl in cals[:4]))
now = datetime.datetime.utcnow()
start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"
evs = c.events().list(calendarId="primary", timeMin=start, timeMax=end,
                      singleEvents=True, orderBy="startTime").execute().get("items", [])
if not evs:
    print("  (nothing on the calendar today)")
for e in evs[:5]:
    s = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "?"))
    print("  -", s, e.get("summary", "(no title)")[:50])

# --- Drive: most recently modified file ---
print("\n[DRIVE] most recently modified file:")
d = build("drive", "v3", credentials=creds, cache_discovery=False)
files = d.files().list(orderBy="modifiedTime desc", pageSize=1,
                       fields="files(name,mimeType,modifiedTime)").execute().get("files", [])
for f in files:
    print("  -", f["name"], "|", f["mimeType"].split(".")[-1], "|", f["modifiedTime"])
if not files:
    print("  (no files)")

print("\nALL THREE SURFACES OK")
