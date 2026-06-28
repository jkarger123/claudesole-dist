# Vault & Credentialing — the credential subsystem (home + full reference)

This folder is the documentation home for ClaudeFather's **credential system**: the per-install **vault**, the
single **resolver**, the **scope/sharing** model, the **migration**, the **secure-field** out-of-band channel,
and the **extension credential contract**. The engine lives in `../server.py`; this folder is the canonical
spec + map (like `../Usage/`). Quick spec: `../../docs/CREDENTIALS.md`. THIS file is the deep reference.

> One rule above all: **every credential lives ONLY in the per-install vault, and nothing sensitive ever
> enters the chat/transcript.** If you're adding a feature/extension that touches a secret, it goes through
> the mechanisms below — never a new `.env`, never a per-extension secret file, never a value printed in chat.

## 1. The store (one encrypted vault per install)
- Location: `<DEPLOY_ROOT>/.vault/_vault.json` (encrypted values) + `<DEPLOY_ROOT>/.vault_key` (Fernet key, 0600).
  Under `DEPLOY_ROOT` so it's writable even on a read-only-core appliance; SHARED by co-located instances on a box.
- A secret record: `{label, scope:[...], shared:<cipher>|null, per_node:{node:<cipher>}, needed_by:[ext], revoked, created, updated}`.
- Encryption: Fernet (the `cryptography` dep). No crypto -> the vault refuses to store (never plaintext).
- Gitignored, never shipped: `.vault/`, `.vault_key`, `_vault_audit.log`, `*.migrated-*`.
- Engine fns (`server.py`): `_vault_fernet/_vault_enc/_vault_dec`, `_vault_load/_vault_save`, `vault_set`,
  `vault_list`, `vault_revoke`, `vault_delete`, `vault_lease`, `vault_declare` (empty slot), `_vault_audit`.

## 2. The single resolver — `_deploy_env(key)`
The ONLY way code/extensions read a secret. Order:
1. `os.environ` (ephemeral override / CI),
2. the install **vault** — `_vault_local(key)` (this box's store, scope + per-node aware) or, for a REMOTE node
   in a fleet, a lease from the overseer's vault (`vault_url`, RAM-cached via `vault_get`),
3. legacy `.env.claudefather` (bootstrap/import ONLY — retired after migration).
Never read a secret any other way. Never hardcode. Never echo.

## 3. Scope & sharing (central vault + per-secret scope)
- `scope:["*"]` or `["afp","shopos"]` — which nodes may use a secret (the consent boundary).
- **shared value** -> in-scope nodes use the SAME credential; **per_node values** -> each node its OWN value
  for the same logical key (billing isolation). Per-node wins for that node.
- Rotate once (update shared) -> every in-scope node gets it. The overseer hosts the vault; co-located instances
  read it directly; remote nodes lease over the signed family channel (`/api/vault-lease`, mesh-token authed).

## 4. Migration (auto-import then retire) — DONE fleet-wide (v0.94–0.95)
`vault_import_env(scrub)` / `POST /api/vault-import {scrub}`: imports every `.env.claudefather` key AND the
file-based extension secrets (slack `bot_token`, google `google_oauth.json` -> `google_oauth_client`, per-account
google token JSONs -> one `google_tokens` dict) INTO the vault, verifies each reads back, and (scrub) archives
the plaintext (`*.migrated-<ts>`, reversible). Google loads its OAuth token VAULT-FIRST (`_google_token_load`),
slack `_token()` prefers the vault, **Granola** reads its key vault-first (`granola._api_key()` →
`_deploy_env("GRANOLA_API_KEY")`, v0.99.5). After migration the vault is the ONLY store.
- **Pattern for any engine module that needs a secret:** take the `secret` resolver in its `init(ctx)` (server.py
  passes `_deploy_env`) and read `secret("KEY")` — NEVER `cc.config`. Granola is the reference (it used to read
  cc.config only, so a key added the standard way — vault/secure-field — was silently ignored until fixed).

## 5. Secure fields — secrets to/from a session WITHOUT the chat (v0.96)
The out-of-band channel. Agents use the `cc-secure` helper (`../cc-secure`); humans answer via a dashboard modal.
- **REQUEST (user -> vault):** `cc-secure request "<label>" vault:<KEY> [scope]` -> `POST /api/secure-request`
  -> a modal pops up in the dashboard (mobile/desktop) -> the user types it -> `POST /api/secure-fulfill` routes
  it STRAIGHT to the vault (browser -> server -> vault). The value never touches the agent's stdin or the chat.
  The agent then reads `<KEY>` via `_deploy_env`.
- **ASK (one-time, returned to the agent):** `cc-secure ask "<label>"` -> dest `return` -> the value is handed
  back to the agent ONCE (encrypted, single-fetch via `/api/secure-get`), for transient use, never via chat.
- **REVEAL (agent -> user):** write the value to a 0600 file, `cc-secure reveal "<label>" <file>` ->
  `POST /api/secure-reveal` (the PATH travels, not the value; the file is shredded) -> a modal shows the user
  one-time. Never in the transcript.
- Store: `<state>/_secure.json` (values encrypted; pruned; reveal values decrypted only when served to the
  auth-gated dashboard). Fns: `secure_request/fulfill/get/reveal/pending/ack`. Browser ops are operator-gated.
- Agents are told all this automatically — it's injected into every launch brief (`_system_brief`).

## 6. Extension credential contract (every extension MUST follow)
- DECLARE the secrets you need: `requires[].key` (env-style), `byok.keys[].id`, function `secrets[]`.
- On install, the platform AUTO-PROVISIONS an empty vault slot per declared key (`_ext_declare_secrets` ->
  `vault_declare`), so the Vault lens shows "needed by <ext>, not set."
- READ secrets ONLY via `_deploy_env(key)` (-> the vault). Never your own secret file, never `cc.config`, never hardcoded.
- Set up secrets via the **secure field** flow (or the Vault lens), never by asking the user to paste into chat.
- Full authoring rules: `../../extensions/AUTHORING.md`.

## 7. APIs
Vault: `GET /api/vault` · `POST /api/vault-set|vault-revoke|vault-delete|vault-import` (operator) · `POST /api/vault-lease` (family-mesh).
Secure: `POST /api/secure-request|secure-reveal` (agent) · `GET /api/secure-get` (agent) · `GET /api/secure-pending` + `POST /api/secure-fulfill|secure-ack` (operator/browser).
UI: the **Vault lens** (overseer) manages secrets; the global **secure-field modal** handles prompts/reveals.

## 8. Hard rules
- Vault key/store/audit + `.migrated` archives: gitignored, never shipped, per-install.
- No credential committed, echoed, hardcoded, or shipped. Secrets never enter chat/transcript — use secure fields.
- `vault_set` sanitizes ids to `[A-Za-z0-9_.-]` (strips `:` `@` etc.) — keep secret ids in that charset (that's
  why google tokens are one `google_tokens` dict, not `google_token:<email>`).
- Encryption requires `cryptography`; doctor warns if a secret/plaintext is found outside the vault.
