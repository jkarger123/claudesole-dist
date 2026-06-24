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
PERMS = os.environ.get("PERMS", "gmail:drafts calendar:full drive:full").split()

from auth.permissions import parse_permissions_arg, set_permissions, get_all_permission_scopes
from auth.scopes import BASE_SCOPES
from auth.credential_store import LocalDirectoryCredentialStore

set_permissions(parse_permissions_arg(PERMS))
SCOPES = sorted(set(BASE_SCOPES) | set(get_all_permission_scopes()))

if "--check" in sys.argv:
    print("IMPORTS_OK\nperms:", PERMS, "\nSCOPES:")
    for s in SCOPES:
        print("  ", s)
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
print("GRANTED_SCOPES:", creds.scopes, flush=True)
