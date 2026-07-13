# Google Workspace extension -- headless OAuth Gmail / Calendar / Drive

<!-- LATEST-HANDOFF -->
**>> Resume here:** read `_handoffs/20260713-0401__google-workspace.md` first -- it is the latest handoff.
<!-- /LATEST-HANDOFF -->

A ClaudeFather **integration extension** (`extension.json` id `google-workspace`). It does two things:
1. **Mints + stores a headless Google OAuth refresh token** for one controlled account (Path B).
2. That stored token is consumed by (a) the **dashboard** server-side to render LIVE Gmail/Calendar/Drive
   lenses + VoiceMatch + Tasks, and (b) the **Google power-agent** (`agents/google`) via a self-hosted MCP.

## How it works -- the two consumers of ONE token

The extension itself only produces `secrets/tokens/<account>.json` (an OAuth refresh token + client id/secret).
Two separate runtimes read it; neither is part of this extension's code:

- **Dashboard (primary, no MCP, no agent).** `command-center/server.py` (the `GOOGLE WORKSPACE` block, ~line 540)
  calls Google's REST APIs DIRECTLY with stdlib `urllib`, swapping the refresh token for a short-lived access
  token (`_google_access_token`, cached until ~90s before expiry). It powers `/api/google/*` endpoints
  (gmail, gmail-msg/thread/labels/att, calendar, drive, send/modify/label/snooze, calendar-create/update/rsvp/delete)
  plus **VoiceMatch** (`/api/flex/context`, voice-matched reply DRAFTS using calendar availability + client context)
  and **Tasks** (`tasks_sweep_programmatic` / `tasks_ai_scan`, a morning inbox->tasks sweep).
  `GOOGLE_SECRETS_DIR`/`GOOGLE_TOKENS_DIR` in server.py point at THIS extension's `secrets/`.
- **Google agent (`agents/google`).** Uses the self-hosted MCP server (`taylorwilsdon/google_workspace_mcp`
  via `uvx workspace-mcp --single-user --transport stdio`) wired into the deployment's `.mcp.json` from
  `mcp.json` here. Same token store, same client JSON.

## Path B vs Path A (the fork that matters -- see SETUP.md)
- **Path B (DEFAULT for headless ClaudeFathers).** Self-hosted MCP + stored refresh token. Acts for ANY account
  you control, **no re-auth ever**, CAN send. This is what the dashboard + agent both use. This whole extension is Path B.
- **Path A.** Claude's first-party connectors -- browser OAuth, operator-Claude-login-bound, read/draft only,
  cannot act for a separate account. Only for interactive, own-account use.

## Key files + where things live
- `extension.json` -- catalog manifest: `provides` mcp:gmail/calendar/drive + agent:google; `setup_agent:true`.
- `SETUP.md` -- the setup-agent walkthrough (Cloud Console steps, the 3 questions, gotchas). **Authoritative.**
- `mcp.json` -- **TEMPLATE ONLY** (never the live config). The setup helper `_ext_wire_mcp` copies this block
  into `CC_HOME/.mcp.json` and replaces `<DEPLOYMENT>` / `<ACCOUNT@gmail.com>` / the permission level.
- `bin/gauth.sh` -- one-command headless auth. `ACCOUNT=.. PERMS=.. bin/gauth.sh [--remote <ssh-host>]`.
  Runs the minter unbuffered, prints ONE consent URL, opens a reverse SSH tunnel for the remote-browser case.
- `bin/mint_token.py` -- the OAuth minter. Uses workspace-mcp's OWN scope logic + `LocalDirectoryCredentialStore`
  so the on-disk token is byte-compatible with what the stdio server reads back. `--check` prints scopes only.
- `bin/verify.py` -- read-only proof across all three surfaces (3 unread + today's events + recent Drive file);
  proves the token auto-refreshes. `ACCOUNT=.. uv run --with workspace-mcp python -u bin/verify.py`.
- `secrets/` (`chmod 700`, gitignored, EXCLUDED from cc-update propagation):
  - `secrets/google_oauth.json` -- the OAuth **Desktop client** JSON from Google Cloud Console (`chmod 600`).
  - `secrets/tokens/<account>.json` -- the minted **refresh token** + client id/secret (`chmod 600`).
  - `secrets/.gitignore` -- ships `* / !.gitignore` so a fresh deploy's secrets dir is self-protecting.

## Scope / permission model (`workspace-mcp --permissions service:level`, cumulative; least privilege)
- gmail: `readonly` -> `organize` -> `drafts` (DEFAULT, compose only) -> `send` -> `full`.
- calendar: `readonly` -> `full`.  drive: `readonly` -> `full`.
- sheets: `readonly` -> `full` (DEFAULT `full` = in-place cell read/write). docs: `readonly` -> `full` (DEFAULT
  `full` = in-place text insert/replace). forms: `readonly` -> `full` (DEFAULT `full` = create/edit forms).
- ONLY services listed in `--permissions` register their tools + request scopes -> **adding a service requires a
  token re-mint** (re-run `bin/gauth.sh` with the matching PERMS) or the new tools 403. sheets/docs/forms were
  added in extension v2.2.0; a pre-2.2.0 install must re-mint to edit files in place / use Forms.
- DRAFT-FIRST is the safe default. Auto-SEND is a deliberate one-flag upgrade: `gmail:drafts` -> `gmail:send`
  in BOTH `mcp.json` perms AND the minted token's scopes (re-run `gauth.sh` with `PERMS="gmail:send ..."`).
  The dashboard's `google_status()` derives `canRead/canSend/canModify` from the token's actual scopes.

## Verified env-var names for workspace-mcp (do NOT guess)
`GOOGLE_CLIENT_SECRET_PATH` (client JSON), `WORKSPACE_MCP_CREDENTIALS_DIR` (token store),
`USER_GOOGLE_EMAIL` (single-user default), `OAUTHLIB_INSECURE_TRANSPORT=1` (loopback callback).
**`GOOGLE_OAUTH_CREDENTIALS` is NOT read by this server** -- a common dead end.

## Hard rules / gotchas
- **NEVER commit, print, or propagate `secrets/`.** Token + client JSON stay local, gitignored, and out of
  cc-update. Never echo token-file contents.
- **Lens visibility is per-INSTANCE install state, NOT token presence.** `google_configured()` requires
  `"google-workspace" in _ext_installed()` because local instances share `CC_HOME` (hence the same tokens dir);
  token-presence alone would leak the lenses onto sibling instances. Self-hides via `window.CC.google`.
- **Unbuffered stdout is mandatory** for the auth flow (the consent URL is a plain `print()` that buffers under
  nohup/pipes). `gauth.sh` uses `python -u`; replicate if you hand-roll.
- **macOS has no `timeout`** -- never use it in setup scripts.
- **Refresh flow needs** `access_type=offline` + `prompt=consent` (+ `OAUTHLIB_RELAX_TOKEN_SCOPE=1`, Google
  reorders/adds openid scopes). The minter sets these.
- **~7-day testing-token lapse** for a PERSONAL Gmail account in Console "Testing" mode: an idle refresh token
  can die after ~7 days. Regular use keeps it alive; re-mint by re-running `bin/gauth.sh`. Workspace/Internal accounts are exempt.
- Stay in Console **"Testing"** mode (don't Publish) and add the controlled account as a **Test user** -- it
  must be the EXACT account the agent drives, or auth silently fails.

## How to extend it
- **New Google surface in the dashboard:** add a REST helper + `/api/google/<thing>` route in server.py's
  GOOGLE WORKSPACE block (mirror `gmail_*`/`calendar_*`/`drive_*`), bump the required scope in `mcp.json`
  + re-mint the token if the new scope isn't already granted. Restart via the `claudesole-restart` skill.
- **New agent capability:** it flows from the MCP perms in `mcp.json` -- raise the `--permissions` level there,
  re-mint the token with matching `PERMS`, re-wire the deployment `.mcp.json`.
- **Agent + integration wiring** (client_map, Granola `google` outbox drain) lives in `agents/google/config.json`
  (gitignored) and `command-center/granola.py` (`_dest_google` writes `_granola_google_outbox.jsonl`), not here.
- Don't edit `mcp.json` to point at real paths -- it's a propagated template; the live config is `CC_HOME/.mcp.json`.

<!-- CC:NOTES -->
<!-- /CC:NOTES -->
