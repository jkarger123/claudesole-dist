# Email Auth — once-and-for-all (the durability + fleet-distribution design)

> Goal (operator directive, 2026-07-23): *"if an email account is added to the vault it should never have any
> issues from that point forward, and it should be available to any nodes that are approved by Mission Control."*

This doc is the canonical spec for how a Google account, once vaulted, (a) **stays alive forever** and (b) is
**usable on every Mission-Control-approved node**. The engine lives in `command-center/server.py` (the GOOGLE
WORKSPACE block ~line 748 + the vault block ~line 5700). This extension only *mints* the token; the durability
+ distribution live in the engine so every deployment gets them.

## The two failures this closes
1. **Token death.** A personal `@gmail` OAuth token in Cloud Console **"Testing"** mode has its refresh token
   killed after **~7 days idle** (and Google's 6-month inactivity rule applies even in Production). Refreshes
   were **lazy/on-demand only**, so an idle account silently crossed the cliff and only failed at first use —
   and `_google_access_token` returned `None` **silently** with no detection/alert/heal.
2. **Single-node lockup.** Tokens lived in each node's **local** vault/disk; `_google_token_load` /
   `_google_accounts` / `_vault_materialize_google` read `_vault_local` ONLY — never the overseer lease that
   `_deploy_env` already uses. An account minted at MC was invisible to afp + every separate-install node.

## The design — 4 mechanisms

### 1. Fleet distribution (available to any approved node)
- The vault holds ONE key `google_tokens` = `{account_email: token_dict}` (scope `["*"]`), plus a new
  **`_google_approvals.json`** state map `{account: ["*"] | [node,...]}` (default `["*"]`), living with the
  **authority** (the node whose local vault holds the real refresh token — normally Mission Control).
- New route **`/api/google-lease`** (mesh-authed, in `AUTH_MESH_INGRESS`): a node POSTs `{node}`; the authority
  returns ONLY the accounts whose approval list includes that node (`google_lease(node, authed)`), audited via
  the vault audit log. Node side: `_google_tokens_remote()` leases from `VAULT_URL/api/google-lease`, RAM-cached
  for the lease TTL (never written to the vault; materialized to disk 0600 for the agent's MCP).
- The three Google read paths now use `_google_tokens_merged()` = **approval-filtered local blob** UNION
  **remote lease**. So: add an account once at MC → every approved node sees it; **approval is enforced even for
  co-located instances** (they share CC_HOME's vault but the per-node approval filter still applies).

### 2. Keep-alive (never dies) — the core guarantee
- Daemon **`_google_keepalive_loop`**: every `google_keepalive_hours` (default **6**, must stay < 7 days) it
  force-refreshes every **locally-held** account's access token, which **resets Google's idle clock**. Exactly
  one co-located instance runs it (shared lock `/tmp/cf-google-keepalive.lock`); remote nodes rely on the
  authority (they share the same refresh token via lease). Records `_google_health[acct]={ok, at}`.
- **This alone makes it permanent** regardless of Console mode — no operator action at Google required.
  (Publishing the OAuth consent screen to **Production** is optional extra hardening — it removes the 7-day
  window entirely — but is NOT a dependency of the guarantee.)

### 3. Self-heal + loud alert (no silent death)
- `_google_access_token` on a refresh failure now: parses the error, and on **`invalid_grant`** (dead/revoked
  refresh token) → (a) tries an overseer **re-lease** (MC may hold a fresher re-mint), (b) if still dead sets
  `_google_health[acct]={ok:False, reason, since}` and raises a **throttled loud alert** (`notify_send` phone +
  operator note + Doctor red) naming the exact account + the one-line fix (`bin/gauth.sh`). Never silent.
- Doctor gains a **live liveness probe** per account (mint an access token; classify `ok` /
  `invalid_grant`(re-consent) / `SERVICE_DISABLED`(enable API) — never conflate them).

### 4. Approval control (approved by Mission Control)
- `/api/google-accounts` (status: per-account health + scopes + approved nodes) and `/api/google-approve`
  (`{account, nodes}`) — operator-only. Surfaced as a small panel: each account → alive/last-keepalive/
  needs-reconsent + an approved-nodes control (All / pick) + the lease-audit peek. Default new account = `["*"]`.

## Hard rules (unchanged, reinforced)
- Tokens NEVER leave the vault except an in-scope, mesh-authed lease to an approved node (audited). Never
  committed, echoed, or shipped. `secrets/` stays gitignored + excluded from `cc-update`.
- Keep-alive/lease/heal all fail **open + quiet** except the deliberate LOUD operator alert on a dead token.
- Config keys (cc.config, all optional): `google_keepalive_hours` (6), `google_keepalive` (true),
  `vault_lease_ttl` (600). No hardcoding; nothing tenant-specific in the engine.

## Touch-points (server.py)
`_google_tokens_local_raw` / `_google_approvals` / `_google_approved_for` / `_google_tokens_remote` /
`_google_tokens_merged` (new helpers, GOOGLE block) · `_google_accounts` / `_google_token_load` /
`_vault_materialize_google` (route through merged) · `_google_access_token` (invalid_grant heal+alert) ·
`google_lease` + `/api/google-lease` route · `_google_keepalive_loop` daemon (+ boot `_daemon` line) ·
Doctor google probe (~line 10452) · `/api/google-accounts` + `/api/google-approve` + the panel in `PAGE`.
