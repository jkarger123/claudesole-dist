# Google auth in ClaudeFather — the canonical model (READ THIS before touching auth)

This is the single source of truth for how the Google Workspace extension authenticates. If anything else in
this extension contradicts it, this file wins. The whole point: **one "app" can serve many accounts, and nothing
falls off — once you get the two layers and the publishing status right.**

## 1. The two layers people conflate (this is the crux)
- **The "app" = an OAuth _client_** (`client_id` + `client_secret`), which lives inside **one Google Cloud project**
  with **one OAuth consent screen**. This is the identity your integration presents to Google.
- **An "account" = a Google _email_** (`alice@gmail.com`, `ops@yourcompany.com`, `bot@yourcompany.com`). Each account
  **grants the app access to its own data**, producing a **per-account refresh token**.

**One app authorizes UNLIMITED accounts.** You do NOT create an app per email. `mint_token.py` mints
`tokens/<email>.json` (a refresh token that _embeds_ the client it was minted against) for each account, all
against the **same** client. Runtime refresh uses the client embedded in each token file — so once minted, an
account is self-contained.

## 2. Why tokens "fall off" — publishing status, NOT the account
A refresh token's lifetime is decided by the **app's publishing status at the moment the token is issued**:

| Consent screen state | Refresh-token lifetime | Verification | User cap |
|---|---|---|---|
| **External · Testing** | **dies a flat ~7 days after issuance** | none | 100 test users |
| **External · Production (unverified)** | durable (only the 6-month-idle rule) | none | 100 users |
| **External · Production (verified)** | durable | required for restricted scopes (Gmail/Drive) = CASA security assessment | none |
| **Internal** (Workspace org only) | durable | **none, ever** | **none** |

**THE 7-DAY DEATH IS NOT INACTIVITY.** For a *Testing* app it is a flat 7-day expiry from issuance, and
**refreshing does NOT reset it** (a refresh returns a new _access_ token but the _same_ refresh token). So the
keep-alive daemon canNOT save a Testing token — it dies at 7 days no matter how often it's used. The only fixes
are: **publish the app to Production**, or use an **Internal** app. (The old docs' "regular use keeps it alive"
was WRONG — that logic only applies to Production's separate 6-month-idle rule, which the keep-alive _does_ beat.)

Corollary: publishing/durability is a property of the **app**, so publishing **one** app to Production makes
**every account under it** durable at once.

## 3. Account types → which app to use
- **Personal `@gmail`** (a consumer Google login): must use an **External** app. Publish it to **Production** (unverified is
  fine for ≤100 users) so it doesn't die weekly.
- **Google Workspace account** (e.g. `you@yourcompany.com`): best served by an **Internal** app *in that same
  Workspace org* — no verification, no cap, no expiry, ~2-minute setup. (It can also use a shared External
  Production app, but the org's admin may have to allowlist third-party apps first.)
- **Workspace, admin-controlled, no per-user consent:** a **service account with domain-wide delegation** — the
  org admin authorizes it once for specific scopes and it can act as any user in the domain. No consent screens,
  no token expiry drama. Best for a B2B Workspace customer. (Only works for that domain; not personal `@gmail`.)

## 4. The trust-domain rule — fleet vs. customer (THE product decision)
> **Share one app only within a single trust domain you fully control. Across trust domains, every operator
> brings their own app.**

- **Your own fleet** (the multiple nodes one operator runs) is ONE trust domain you control — if it's under 100
  users, use **ONE shared app** (one Cloud project, **published to Production**). Every fleet email authorizes it;
  that client is `secrets/google_oauth.json` on every node.
- **A separate/unrelated ClaudeFather install** (someone else self-hosting on their own server) is a **different
  trust domain**. They must **NOT** share your app, because ClaudeFather is self-hosted, so sharing = shipping the
  client secret onto every install. That causes: secret exposure; a hard **100-user cap across ALL installs
  combined**; the app owner's **restricted-scope verification burden covering everyone**; a **shared blast radius**
  (one install's abuse flags the app → everyone breaks) and **shared API quota**; and it makes the app owner a
  **data processor for every other operator's Gmail** — which also contradicts ClaudeFather's "nothing leaves your
  server" promise. So: **every independent operator brings their own app.**

BYO-app is not a burden to hide — for a sovereignty product it's a **feature**: each operator's Google data stays
entirely inside *their* project and *their* server, no third party in the trust path.

**Fleet visibility — a new account is available to EVERY node by default; SCOPE it if it shouldn't be.** Once an
account is vaulted, `_google_approved_for` **defaults to open** (`["*"]`), so every Mission-Control-approved node
can lease + read that inbox. That is right for a shared ops account, but WRONG for a *personal* inbox — you rarely
want one person's Gmail visible on unrelated project nodes. Scope each account to just the nodes that should drive
it: the **Accounts lens** approved-nodes control, or `POST /api/google-approve {account, nodes:["<node>", …]}`
(server-side `_google_approve` → shared-vault key `google_approvals`). A scoping change is enforced authoritatively
at once, but each node RAM-caches its lease for `vault_lease_ttl` (default **600s**), so other nodes converge
within ~10 min. (Example: a personal assistant account scoped to `["afp"]` disappears from every other node's
Accounts view on its next lease refresh.)

## 5. How we make BYO painless (so no one "sets up apps" the hard way)
The extension is **client-agnostic**: it takes whatever client the operator configures and mints per-email tokens
against it. Setup is a guided ~5-minute task, branched by account type:
- **Workspace org →** create an **Internal** app (fast path; durable forever, zero verification) *or* a
  **service account** with domain-wide delegation.
- **Personal / mixed →** create an **External** app and **publish to Production**.
The wizard detects the case, gives exact click-by-click steps (or semi-automates via `gcloud`), and **validates
live** (mint → real Gmail/Calendar/Drive read) before declaring success.

## 6. What keeps accounts alive once set up right (already built)
- **Keep-alive daemon** (`_google_keepalive_loop`, every ~6h): refreshes each account so it never trips the
  6-month-idle rule. (Useless against Testing's 7-day rule — see §2 — which is why the app must be Production/Internal.)
- **Scope-floor guard** (v0.99.218): `_caps_from_scopes` records each account's high-watermark (read/send);
  `_vault_materialize_google` refuses to overwrite a broader token with a narrower one; Doctor goes RED + fires a
  loud alert the moment `canRead`/`canSend` drops below the watermark. (`gmail.compose` counts as send-capable.)
- **Loud `invalid_grant` handling** (`_google_access_token`): a dead/revoked token isn't silent — it alerts with
  the exact remedy (re-consent) and Doctor shows the account down.

## 7. Minting mechanics (the tunnel-less, headless-safe flow)
- `bin/mint_token.py` runs a loopback callback server on `localhost:PORT` (default 8765), prints the consent URL
  (`AUTH_URL>>>`), and stores `tokens/<ACCOUNT>.json` on the callback. It **forces Google's v2 auth endpoint**
  (`/o/oauth2/v2/auth`) — the legacy endpoint 401s `invalid_client` for new-console clients. It **drops 3
  console-unlisted scopes** (`gmail.modify` / `calendar.events` / `forms.body.readonly`) that would break consent;
  override with `DROP_SCOPES=`.
- **Client resolution** (client-agnostic): `CLIENT_JSON=<path>` env wins; else `google_oauth.<account-localpart>.json`
  if present (per-account override for mixed/transition setups); else `google_oauth.json` (the one configured app).
- **Consolidating / re-homing an account onto a different app** (e.g. moving a fleet off an old client, or an
  account that was minted against a now-retired app and can't be revived): re-mint it against the target client.
  Because each `tokens/<email>.json` **embeds its own client**, runtime refresh of *other* accounts is unaffected —
  you only re-consent the one you're moving. To make the target app the fleet DEFAULT for future mints too, repoint
  the shared default: `cp google_oauth.json google_oauth.json.old-<proj#>.$(date +%s).bak` then copy the target
  client over `google_oauth.json` (chmod 600) — reversible via the backup. Then re-mint the stale account (no
  per-account override needed once the default is the target), `_google_vault_resync()`, and re-probe
  `/api/google-accounts` to clear its health flag. (Done live 2026-07-31: two accounts consolidated onto one
  External-Production app; a third stood up on its own Internal app via a per-account override.)
- **Remote operator with no browser on the box:** run the minter locally; the operator opens the printed URL in
  ANY browser, approves, lands on `http://localhost:8765/?...code=...` ("can't reach" is expected), copies that
  whole address, and you deliver it by `curl`-ing it **on the box**. No SSH tunnel, no `--remote`. (SETUP.md §remote.)

## 8. Never do
- Never ship our client secret to a customer install (§4). Never publish a Testing app's tokens as "durable."
- Never overwrite a broader working token with a narrower one (the guard enforces this).
- Never print a token/secret to chat or git. `secrets/` is `700`, files `600`, gitignored, excluded from cc-update.
