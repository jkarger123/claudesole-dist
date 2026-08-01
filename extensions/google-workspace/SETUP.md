# Google Workspace -- setup walkthrough

Brief for the **setup agent**. Goal: the user ends with Gmail + Calendar + Drive + Sheets + Docs + Forms fully
authorized (both the Cloud APIs ENABLED and the OAuth scopes granted -- two separate gates, see step 2) AND the
**Google agent** (agents/google) ready to drive them, integrated with their clients + the Calls module.
ASCII only. Be patient + concrete. Verified end-to-end on a real install (2026-06-23); the exact
wiring + tools below are what actually worked -- prefer them over improvising.

## ▶▶ SETUP WIZARD — start here (pick your path; this decides whether it STAYS working)
You are creating **your OWN** Google app — ClaudeFather never shares one app across unrelated installs (see
`AUTH_MODEL.md` §4: your Google data stays in *your* project, on *your* server). It's a ~5-minute one-time task.
Route by account type; this fork decides token durability:

**Q1 — What account will the agent drive?**

- **▸ A Google Workspace account** (`you@yourcompany.com` — a domain you/your org control) → **PATH W (durable, no verification):**
  - **W1 (recommended) — Internal OAuth app.** In your Workspace's Cloud project → OAuth consent screen → User
    type **Internal** → create a **Desktop** OAuth client → download the JSON. Internal apps have **no 7-day death,
    no verification, no user cap** — set-and-forget. Then go to "Mint the headless token."
  - **W2 (no per-user consent) — service account + domain-wide delegation.** Create a service account, enable
    domain-wide delegation, and in the **Admin console** authorize its client ID for the scopes. The agent then
    acts as any user in the domain with no consent screen — best when an admin wants central control. (Confirm
    before choosing; it needs Admin-console access.)
- **▸ A personal `@gmail`** (no Workspace domain) → **PATH P (must publish to Production):**
  - Cloud project → OAuth consent screen → User type **External** → create a **Desktop** OAuth client → download
    the JSON → **then PUBLISH the app to Production** (consent screen → "PUBLISH APP" → confirm). Publishing
    **unverified is fine** (≤100 users; one "unverified app → continue" click at consent). **Do NOT leave it in
    Testing** — Testing tokens die a flat ~7 days after issuance and nothing on our side stops it (`AUTH_MODEL.md`
    §2). Then go to "Mint the headless token."

**Q2 — Draft-only or send?** Draft-first is the safe default (`gmail:drafts`). Auto-send is a one-flag opt-in
(`PERMS="gmail:send …"`) — confirm before enabling.

**Q3 — Browser on this host, or remote?** Remote (SSH/Tailscale) → use the **tunnel-less recipe** (near the
bottom of this doc): run the minter here, open the printed URL in a browser anywhere, paste the
`http://localhost:8765/...` redirect back.

**Multiple accounts / other emails?** Repeat "Mint the headless token" per email against the **SAME** app — one
app, many `tokens/<email>.json`, no new project. The minter is client-agnostic (`_resolve_client` in
`mint_token.py`): it uses `CLIENT_JSON` env → a per-account `google_oauth.<localpart>.json` → the shared
`google_oauth.json`. (A different-org account that needs its OWN app — e.g. a Workspace Internal app in another
domain — just gets a per-account `google_oauth.<localpart>.json` client override; everything else is identical.)

> **Scope each account to the right nodes (privacy).** A newly-vaulted account defaults to visible on **every**
> fleet node. That's fine for a shared ops account but usually wrong for a *personal* inbox. In the **Accounts
> lens**, set each account's approved-nodes (All / pick), or `POST /api/google-approve {account, nodes:[…]}`.
> Nodes converge within ~10 min (the `vault_lease_ttl` RAM cache). See AUTH_MODEL.md §4 "Fleet visibility."

**Finish = VALIDATE.** After minting, run `verify.py` (below) — it must print **ALL THREE SURFACES OK** (real
Gmail + Calendar + Drive read). Green on Path W, or on Path P with the app in **Production**, means you're durable. Done.

> The sections below are the detailed reference the wizard steps into (Cloud Console specifics, the mint command,
> verify, the remote-auth recipe, gotchas). The Path A/B fork just below is a *separate* choice — the auth
> *mechanism* (self-hosted MCP vs Claude connectors) — orthogonal to the account-type paths above.

## What it does
Connects Gmail, Google Calendar, and Google Drive, then layers a **Google power-agent** on top that uses the
WHOLE surface (not just read): inbox triage with labels + reply drafts, free/busy scheduling, Drive search +
doc creation + permission checks, a daily brief, per-client comms pulled into the client's CLAUDE.md, and it
drains the Calls (Granola) module's Google actions into real calendar events. Launch it from the Agents lens.

## Choose the path FIRST (this is the fork that matters)
A ClaudeFather runs agents + cron with **no human at a browser**, often to act for a **dedicated/service
account** (not the operator's personal Google login). That shapes the choice:

- **Path B -- self-hosted MCP server (DEFAULT for ClaudeFathers).** A Google Cloud OAuth client + a one-time
  headless auth mints a **refresh token the server reuses** (no re-auth) — indefinitely **when the app is
  Production or Internal** (a Testing app dies every ~7 days, see the wizard/`AUTH_MODEL.md` §2). It can act for
  ANY account you control and can **send email**. This is what matches "the agent does this for me without auth
  every time." Use Path B for any dedicated/service account or headless/cron use. The rest of this doc is Path B.
- **Path A -- Claude's first-party connectors.** Browser OAuth, no local keys -- but tied to the **operator's
  Claude login**, so it **cannot act for a separate account** and **cannot send email**. Only pick A if the
  user just wants read/draft against their OWN logged-in account, interactively.

## Ask the user 3 questions, then go
1. **Which Google account should the agent control?** (e.g. a dedicated `you@gmail.com` / Workspace account)
2. **Send or draft-only?** Draft-first is the safe default (agent composes, you send). Auto-send is a
   one-flag opt-in -- confirm they want the agent to send email on its own (blast-radius warning below).
3. **Can you open a browser ON this host, or are you remote?** (e.g. SSH/Tailscale from another machine) --
   this decides whether you need the reverse-SSH-tunnel during auth.

## Google Cloud Console (verified steps, with the non-obvious bits)
1. Create / choose a **project**.
2. Enable the Google APIs the extension uses. **A granted OAuth scope is NOT enough by itself -- the Cloud
   PROJECT must ALSO have each API turned ON, or calls 403 with `SERVICE_DISABLED` even though the scope is
   granted** (this bit a live node: all 21 scopes minted, but Sheets still 403'd until the Sheets API was enabled
   in the project). Enable:
   - **Gmail API + Google Calendar API + Google Drive API** (always).
   - **Google Sheets API + Google Docs API + Google Forms API** -- needed for in-place Sheets/Docs editing +
     creating Forms (the default `PERMS` below request these; enable them now so those tools don't 403 later).
   Direct activation URLs -- replace `<PROJECT#>` with your project number (shown in the Console URL and next to
   the OAuth client_id):
   - Sheets: `https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=<PROJECT#>`
   - Docs:   `https://console.developers.google.com/apis/api/docs.googleapis.com/overview?project=<PROJECT#>`
   - Forms:  `https://console.developers.google.com/apis/api/forms.googleapis.com/overview?project=<PROJECT#>`
   After clicking Enable, Google takes ~2-3 min to propagate. If a call still 403s `SERVICE_DISABLED` after that,
   the API isn't enabled in the project yet -- that is a DIFFERENT problem from a missing OAuth scope (which needs
   a re-mint). Don't conflate them: `SERVICE_DISABLED` -> enable the API (URL above); missing scope -> re-mint.
3. **OAuth consent screen — pick by account type (this decides whether tokens survive; see AUTH_MODEL.md):**
   - **Google Workspace org account** (e.g. `you@yourcompany.com`): choose **Internal**. Durable forever, no
     verification, no user cap, no 7-day death. Easiest and best — done.
   - **Personal `@gmail`**: choose **External**, then **PUBLISH the app to Production.** Do NOT leave it in
     "Testing" — a Testing app's refresh tokens die a flat ~7 days after issuance and the keep-alive can't stop it.
     Publishing unverified is fine (≤100 users); you'll just see an "unverified app" warning at consent, which is
     harmless for your own app. (Full Google verification is only needed to remove that warning / exceed 100 users.)
4. **If you chose External/Testing for initial dev, add the controlled account as a Test user** — it MUST be the
   exact account the agent will drive (a common mistake is adding a different address; then auth silently fails).
   But move to Production before relying on it (see step 3). Internal accounts skip the test-user step entirely.
5. **Credentials -> Create OAuth client ID -> Desktop app -> download the JSON.**
6. Place it at `extensions/google-workspace/secrets/google_oauth.json` (`chmod 600`; the dir is gitignored).
7. Heads-up the user: during consent they'll see an **"unverified app" warning** -> Advanced ->
   "Go to <app> (unsafe)" -> approve. That's expected for a Testing-mode app.

## Mint the headless token (one command)
The extension ships the tools under `bin/` -- use them, don't hand-roll the flow.

```
cd extensions/google-workspace
ACCOUNT=you@gmail.com PERMS="gmail:drafts calendar:full drive:full sheets:full docs:full forms:full" bin/gauth.sh          # local browser
ACCOUNT=you@gmail.com PERMS="gmail:drafts calendar:full drive:full sheets:full docs:full forms:full" bin/gauth.sh --remote <operator-ssh-host>   # remote browser
```
`gauth.sh` starts the minter **unbuffered**, prints ONE consent URL, waits for approval, and stores the
refresh token at `secrets/tokens/<account>.json`. The PERMS above match `mcp.json` -- `sheets:full docs:full`
let the agent EDIT existing Sheets/Docs IN PLACE (not just create new files), and `forms:full` lets it create
Google Forms. For **send** instead of drafts, swap `gmail:drafts` -> `gmail:send`.
> **Already installed before v2.2.0?** Your token predates the sheets/docs/forms scopes -- the agent will
> create-new-copies instead of editing in place, and Forms will 403. **One command turns it on** -- it patches
> the LIVE `.mcp.json` AND re-mints in a single run (you just approve in the browser once, then restart):
> ```
> ACCOUNT=you@gmail.com bin/enable-services.sh                       # browser on this host
> ACCOUNT=you@gmail.com bin/enable-services.sh --remote <ssh-host>   # browser on a remote host
> ```
> Run it -> open the ONE printed consent URL -> click Allow. Done. (An agent can stage this line into the Admin
> shell for you via the sessions/sudo protocol; you hit enter + approve.) The new tools appear on the google
> agent's **next launch** -- see "Restart semantics" below; you do NOT need to bounce the whole node.

### Restart semantics (don't over-restart)
The Path-B google agent spawns its own stdio MCP **fresh on every launch**, so after you enable an API, re-mint,
or edit `.mcp.json --permissions`, the new tools are picked up **the next time the agent launches** -- just start
a new google-agent session (or relaunch it). You do NOT need a global node restart; only a long-lived / attached
session that's already running won't see the change until it's relaunched. (Bouncing the whole node can kill the
very session doing the setup, so avoid it.)

- **Remote operator (no browser on the Mac):** `--remote <host>` opens a reverse SSH tunnel
  (`ssh -N -R PORT:localhost:PORT <host>`) so the OAuth loopback callback reaches the operator's browser.
  Needs working OUTBOUND ssh from this host to `<host>`; no inbound ssh to the Mac required. The user opens
  the printed URL in THAT machine's browser and signs in **as the controlled account**.

## Wire the deployment config
Copy this extension's `mcp.json` block into the DEPLOYMENT's `.mcp.json` (the setup wiring helper /
`_ext_wire_mcp` targets `CC_HOME/.mcp.json`), replacing the placeholders:
- `<DEPLOYMENT>` -> the deployment root (DEPLOY_ROOT == CC_HOME),
- `<ACCOUNT@gmail.com>` -> the controlled account,
- permission `gmail:drafts` -> `gmail:send` only if the user opted into auto-send.
Verified env-var names (do NOT use `GOOGLE_OAUTH_CREDENTIALS`):
`GOOGLE_CLIENT_SECRET_PATH`, `WORKSPACE_MCP_CREDENTIALS_DIR`, `USER_GOOGLE_EMAIL`, `OAUTHLIB_INSECURE_TRANSPORT=1`.
Server: `taylorwilsdon/google_workspace_mcp` via `uvx workspace-mcp --single-user --transport stdio`.

## Verify (read-only, all three surfaces)
```
ACCOUNT=you@gmail.com uv run --with workspace-mcp python -u bin/verify.py
```
Prints 3 unread subjects + today's events + calendars + the most-recently-modified Drive file, and proves
the token auto-refreshes. (Equivalent conversational checks: "3 most recent unread subjects?" / "What's on
my calendar today?" / "Most recently modified Drive doc?")

## Wire the agent + integrations (this is what makes it more than a connector)
1. `cp agents/google/config.example.json agents/google/config.json` and fill: `timezone`, `work_hours`,
   `primary_calendar`, and `client_map` (client folder -> email domains). Keep `client_map` in SYNC with the
   Granola module's so client matching is consistent across both. (`agents/*/config.json` is gitignored.)
2. (Agency) the Google agent reads `client_map` to pull per-client comms and file dated notes to each
   client's `CLAUDE.md`.
3. (Calls module) if you run Granola with the `google` destination, approved calls drop action items into
   `<state>/_granola_google_outbox.jsonl`; ask the Google agent to "drain the granola outbox" to turn them
   into real calendar events/tasks (it confirms the batch first).

## The capability surface
- **Gmail**: search (full query syntax), read full threads, LABEL management for triage, create DRAFTS.
  SENDING is gated behind the `gmail:send` opt-in (default is draft-only -- a safety feature, not a gap).
- **Calendar**: list calendars, list/get/create/update/delete events, respond to invites, and `suggest_time`
  (free/busy across multiple attendees with work-hour preferences).
- **Drive**: structured search, read/download content, metadata, **permissions** (check before sharing),
  create + copy files.
- **Sheets / Docs**: read + EDIT existing spreadsheets and documents IN PLACE (read a range, update/append
  cells, insert/replace text) -- so "modify this sheet" edits the SAME file, keeping its ID/sharing/links,
  instead of spawning a new copy.
- **Forms**: create + edit Google Forms (questions, sections) and read responses.

## Scope model (least privilege; `--permissions service:level`, cumulative)
- gmail: `readonly` -> `organize` (labels+modify) -> `drafts` (compose) -> `send` -> `full`. Default `drafts`.
- calendar: `readonly` -> `full` (calendar + calendar.events).
- drive: `readonly` -> `full` (drive + drive.file).
- sheets: `readonly` -> `full` (read + write cell values). Default `full` (in-place editing).
- docs: `readonly` -> `full` (read + insert/replace text). Default `full` (in-place editing).
- forms: `readonly` -> `full` (create/edit forms + read responses). Default `full`.
Request only what the use case needs; start read/draft, upgrade deliberately. **Only services listed in
`--permissions` register their tools** -- so adding a service means re-minting the token (re-consent) with a
matching `PERMS`, or the new tools 403.

## Auth error decoder (2026-07-24 incident -- learn these ONCE, never fight them again)
Each failure string has ONE cause and ONE fix. Don't guess -- match the string:
- **`Error 400: invalid_scope`** -> a requested scope isn't listed on the OAuth consent screen. Cause: `uvx`
  pulled a newer `workspace-mcp` whose `:full` levels request `gmail.modify`/`calendar.events`/`forms.body.readonly`.
  Fix: already handled -- `bin/mint_token.py` drops those (redundant) scopes, and `mcp.json` PINS the version.
- **`Error 401: invalid_client / OAuth client was not found`** (AFTER you sign in, for a client that clearly
  exists + whose refresh token works) -> the client JSON points at Google's LEGACY `…/o/oauth2/auth` endpoint,
  which new-console clients reject post-login. Fix: already handled -- `mint_token.py` forces `…/o/oauth2/v2/auth`.
  (If you ever hit it hand-rolling: `curl` the consent URL from the box -- a clean 302 to sign-in means the client
  is fine and the endpoint is the problem.)
- **`Error 403: access_denied … only … testers`** -> the signing-in account is NOT a Test user on THIS OAuth
  app's project. Fix: add it under the project's **Audience -> Test users**. Confirm you're in the RIGHT project
  (the client_id in the consent URL tells you which) and that the operator actually OWNS/can access it.
- **`SERVICE_DISABLED` (403 on a real API call, scope IS granted)** -> the Cloud API isn't enabled in the project.
  Fix: enable it (Console URLs in step 2). This is NOT a scope problem -- do not re-mint.
- **`invalid_grant` on refresh** -> the refresh token is genuinely dead (idle >~7d on a Testing personal Gmail,
  or revoked). Fix: re-mint. (This is the only one keep-alive can't prevent; Doctor flags it RED + alerts.)

## Remote operator with NO browser on the Mac -- the RELIABLE, tunnel-less way (preferred over `--remote`)
Don't fight SSH tunnels or guess the operator's machine. Run the minter LOCALLY on the Mac; it listens on
`localhost:8765` and holds the PKCE verifier in memory. The operator opens the printed consent URL in ANY
browser, approves, and the browser lands on `http://localhost:8765/?...&code=...` ("can't reach" -- expected).
They copy that WHOLE address; you deliver it to the still-listening minter by curling it ON the Mac:
`curl 'http://localhost:8765/?state=..&code=..&scope=..'`. The minter exchanges + stores. No tunnel, no inbound
SSH, no `--remote`, works regardless of which device the operator is on.

## Scope floor -- read/send can't silently vanish anymore (server.py)
Keep-alive keeps a token ALIVE but has no concept of scope; on 2026-07-24 a re-mint narrowed an account to
send-only and nothing noticed until a read failed. Now: `_google_health` records each account's high-watermark
capabilities; `_vault_materialize_google` REFUSES to overwrite a broader token with a narrower one; and Doctor
goes RED + fires a loud alert the moment `canRead`/`canSend` drops below what the account had. So a downgrade is
loud, and a narrow token can't clobber a good one.

## Gotchas (these cost real time on the first install -- bake them in)
- **Unbuffered stdout:** the auth lib prints the consent URL with a plain `print()`; under nohup/pipes it
  buffers forever. `gauth.sh` already runs the minter with `python -u` -- if you roll your own, do the same.
- **macOS has no `timeout`** by default -- don't use it in setup scripts.
- **Refresh token:** the flow needs `access_type=offline` + `prompt=consent` (the minter sets these); set
  `OAUTHLIB_RELAX_TOKEN_SCOPE=1` during the flow (Google reorders/adds openid scopes).
- **~7-day testing-token DEATH (personal Gmail in Testing mode):** a refresh token minted while the app is in
  "Testing" dies a **flat ~7 days after issuance** — NOT inactivity, and **refreshing/keep-alive does NOT prevent
  it**. The fix is to **publish the app to Production** (personal `@gmail`) or use an **Internal** app (Workspace);
  re-running `bin/gauth.sh` only buys another 7 days until you do. Workspace/Internal apps never have this. (See
  `AUTH_MODEL.md` §2 — the old "regular use keeps it alive" claim was wrong.)

## Safety
- READ-FIRST, DRAFT-FIRST. Sending email requires the explicit `gmail:send` opt-in; even then, CONFIRM
  before bulk/outbound sends. CONFIRM before creating/deleting events or creating/sharing Drive files.
  Prefer archive/label over delete; deletes need explicit, named confirmation.
- **Secrets** live under `secrets/` (`700`; client JSON + token `600`), gitignored AND excluded from
  `cc-update` propagation -- they never enter git and never replicate to other nodes. Never print tokens or
  secret-file contents.
- Uninstall removes the wiring; it never touches your Google account or data.
