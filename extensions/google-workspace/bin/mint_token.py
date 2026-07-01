"""One-time headless OAuth token minter for the workspace-mcp (Path B) Google extension.

Mints a refresh token for ONE account using workspace-mcp's OWN scope logic +
credential store, so the requested scopes and the on-disk token file are
guaranteed byte-compatible with what the stdio server reads back headlessly.

Run:  uv run --with workspace-mcp python -u mint_token.py            # live auth
      uv run --with workspace-mcp python -u mint_token.py --check    # scopes only

Env (with sensible fallbacks):
  ACCOUNT      account@gmail.com to control            (required for live auth)
  SECRETS_DIR  dir holding google_oauth.json + tokens/ (default: ../secrets next to bin/)
  PORT         loopback callback port                  (default: 8765)
  PERMS        space-separated workspace-mcp perms     (default: "gmail:drafts calendar:full drive:full")
"""
import os, sys

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNT = os.environ.get("ACCOUNT", "")
SECRETS = os.environ.get("SECRETS_DIR") or os.path.normpath(os.path.join(HERE, "..", "secrets"))
CLIENT = os.path.join(SECRETS, "google_oauth.json")
CREDS_DIR = os.path.join(SECRETS, "tokens")
PORT = int(os.environ.get("PORT", "8765"))
PERMS = os.environ.get("PERMS", "gmail:drafts calendar:full drive:full sheets:full docs:full forms:full").split()

from auth.permissions import parse_permissions_arg, set_permissions, get_all_permission_scopes
from auth.scopes import BASE_SCOPES
from auth.credential_store import LocalDirectoryCredentialStore

set_permissions(parse_permissions_arg(PERMS))
SCOPES = sorted(set(BASE_SCOPES) | set(get_all_permission_scopes()))

def _scopes_to_perms(scopes):
    """Map ACTUAL granted OAuth scopes -> workspace-mcp service:level labels, faithfully (CCR ccr-1782880284369:
    --check must never under-report). Matches on each scope's final path segment (e.g. 'drive', 'spreadsheets',
    'gmail.send'), reporting :full when the write scope is present, else :readonly."""
    tail = set(s.rstrip("/").rsplit("/", 1)[-1] for s in (scopes or []))
    out = []
    if "mail.google.com" in tail: out.append("gmail:full")
    elif "gmail.send" in tail: out.append("gmail:send")
    elif "gmail.compose" in tail: out.append("gmail:drafts")
    elif "gmail.modify" in tail: out.append("gmail:organize")
    elif "gmail.readonly" in tail: out.append("gmail:readonly")
    if "calendar" in tail: out.append("calendar:full")
    elif "calendar.readonly" in tail: out.append("calendar:readonly")
    if "drive" in tail or "drive.file" in tail: out.append("drive:full")
    elif "drive.readonly" in tail: out.append("drive:readonly")
    if "spreadsheets" in tail: out.append("sheets:full")
    elif "spreadsheets.readonly" in tail: out.append("sheets:readonly")
    if "documents" in tail: out.append("docs:full")
    elif "documents.readonly" in tail: out.append("docs:readonly")
    if "forms.body" in tail: out.append("forms:full")
    elif "forms.body.readonly" in tail or "forms.responses.readonly" in tail: out.append("forms:readonly")
    return out

if "--check" in sys.argv:
    # Report the ACTUAL granted scopes from the STORED TOKEN FILE (never the requested PERMS), so it never
    # under-reports after a mint (CCR ccr-1782880284369). Falls back to the requested set only if no token exists.
    import json as _json, glob as _glob
    _tf = os.path.join(CREDS_DIR, ACCOUNT + ".json") if ACCOUNT else ""
    if not (_tf and os.path.isfile(_tf)):
        _c = sorted(_glob.glob(os.path.join(CREDS_DIR, "*.json")))
        _tf = _c[0] if _c else ""
    _granted = []
    if _tf and os.path.isfile(_tf):
        try: _granted = (_json.load(open(_tf)) or {}).get("scopes") or []
        except Exception: _granted = []
    print("IMPORTS_OK")
    print("token_file:", _tf or "(none minted yet)")
    if _granted:
        print("granted_perms:", " ".join(_scopes_to_perms(_granted)) or "(none)")
        print("GRANTED_SCOPES:")
        for s in sorted(_granted): print("  ", s)
    else:
        print("requested_perms:", " ".join(PERMS), "(no token minted yet -- what a mint WOULD request)")
        print("REQUESTED_SCOPES:")
        for s in SCOPES: print("  ", s)
    sys.exit(0)

if not ACCOUNT:
    sys.exit("ERROR: set ACCOUNT=the-account@gmail.com")

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(CLIENT, scopes=SCOPES)
print("WAITING_FOR_CALLBACK on localhost:%d" % PORT, flush=True)
creds = flow.run_local_server(
    host="localhost", port=PORT, open_browser=False,
    access_type="offline", prompt="consent", include_granted_scopes="true",
    authorization_prompt_message="AUTH_URL>>> {url}",
    success_message="Authorized. You can close this tab and return to the terminal.",
)

store = LocalDirectoryCredentialStore(base_dir=CREDS_DIR)
ok = store.store_credential(ACCOUNT, creds)
print("STORED:", ok, flush=True)
print("REFRESH_TOKEN_PRESENT:", bool(creds.refresh_token), flush=True)
# Report the FINAL ON-DISK scope set (re-read from the token file), not the in-flight creds object, so the
# printed result matches what the MCP will actually read back (CCR ccr-1782880284369 item 3).
try:
    import json as _json
    _tf = os.path.join(CREDS_DIR, ACCOUNT + ".json")
    _disk = (_json.load(open(_tf)) or {}).get("scopes") if os.path.isfile(_tf) else None
except Exception:
    _disk = None
_final = _disk or list(creds.scopes or [])
print("GRANTED_SCOPES:", _final, flush=True)
print("GRANTED_PERMS:", " ".join(_scopes_to_perms(_final)), flush=True)
