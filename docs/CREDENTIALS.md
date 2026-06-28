# Credentials -- the one way (per-install vault)

The single, standardized, enterprise credential model for every ClaudeFather install. There is exactly ONE
place credentials live and ONE way code reads them. No more scattered `.env` files, no "some encrypted some
not," no per-extension secret files.

## The model
- **One vault per INSTALL.** A single encrypted store at the install root (`<DEPLOY_ROOT>/.vault/_vault.json`,
  key `<DEPLOY_ROOT>/.vault_key`, 0600). Co-located instances on a box (overseer + nodes) SHARE it; it lives
  under DEPLOY_ROOT so it stays writable even on a read-only-core appliance.
- **Every secret has a SCOPE + a value shape:**
  - `scope: ["*"]` or `["afp","shopos"]` -- which nodes may use it.
  - **shared value** -> those nodes use the SAME credential; OR
  - **per-node values** (`per_node[node]`) -> each node gets its OWN credential for the same logical name
    (billing isolation: `STRIPE_KEY` = afp:k1, shopos:k2). Per-node wins over shared for that node.
- **Encrypted at rest** (Fernet), audited (`_vault_audit.log`), rotatable/revocable in one place (the Vault lens).

## The single resolver
All code + extensions read a secret ONE way -- `_deploy_env(key)` -- which resolves, in order:
1. **process env** (`os.environ`) -- ephemeral override / CI only.
2. **the install vault** -- `_vault_local(key)` (this box's shared store, scope-aware), or for a REMOTE node
   within an install, a lease from the overseer's vault over the signed family channel (`vault_url`, RAM-cached).
3. **legacy `.env.claudefather`** -- bootstrap/import ONLY, being retired after migration.
The vault is the system of record; env is an override; `.env` is migration residue.

## Sharing across nodes (central vault + scope -- the chosen model)
The install's overseer holds the vault; scope IS the consent control:
- **Share a credential with node B:** add B to that secret's `scope` (one action at the vault). B leases it.
- **Give B its own:** set a `per_node` value for B. Same id, different value, billing-isolated.
- **Rotate once:** update the shared value -> every in-scope node gets it on next lease/read.
- Remote nodes need `cc.config vault_url` (the overseer) + the family `mesh_token` to lease; co-located
  instances read the shared file directly. Mission Control / the overseer HOSTS the vault, so it inherently has
  whatever it needs -- no special case.

## Migration (auto-import then retire)
`vault_import_env(scrub=False|True)` (operator: `POST /api/vault-import {scrub}`):
1. Pulls every key from `.env.claudefather` INTO the vault (scope `["*"]` by default -- re-scope afterwards).
2. Verifies each reads back from the vault.
3. `scrub=True` -> archives the plaintext `.env.claudefather` to `.env.claudefather.migrated-<ts>` (reversible,
   gitignored) so the vault is the ONLY store. Idempotent (a key already in the vault is left as-is).
Run per install (each deployment imports its own `.env`). Rollout is additive-first: ship vault-first
resolution (vault empty -> `.env` still answers, nothing breaks) -> import (no scrub) -> verify reads come from
the vault -> THEN scrub.

## Secure fields -- secrets to/from a session WITHOUT the chat (v0.96)
Sensitive values NEVER go in the chat/transcript. The out-of-band channel (deep ref: command-center/vault/CLAUDE.md):
- **REQUEST (user -> vault):** an agent runs `cc-secure request "<label>" vault:<KEY>` -> a modal pops up in the
  dashboard (mobile/desktop) -> the user types the value -> it routes STRAIGHT to the vault (browser->server->vault),
  never through the agent or chat. The agent then reads `<KEY>` via the resolver.
- **ASK (one-time to the agent):** `cc-secure ask "<label>"` -> the value is returned to the agent ONCE (encrypted,
  single-fetch), for transient use, never via chat.
- **REVEAL (agent -> user):** the agent writes the value to a 0600 file + `cc-secure reveal "<label>" <file>` (the
  path travels, not the value; file shredded) -> a modal shows the user one-time.
Agents are told this automatically (injected into every launch brief). APIs: `POST /api/secure-request|secure-reveal`,
`GET /api/secure-get` (agent); `GET /api/secure-pending`, `POST /api/secure-fulfill|secure-ack` (operator/browser).

## Extension credential contract (every extension follows this)
- DECLARE needed secrets (`requires[].key`, `byok.keys[].id`, function `secrets[]`). On install the platform
  AUTO-PROVISIONS an empty vault slot per key (`vault_declare`) -> Vault lens shows "needed by <ext>, not set."
- READ via `_deploy_env(key)` ONLY (-> the vault). No bespoke secret files, no cc.config secrets, nothing hardcoded.
- Fill via the secure-field flow or the Vault lens -- never by asking the user to paste into chat.

## APIs (operator-only except lease)
`GET /api/vault` (list, never values) · `POST /api/vault-set {id,value,label,scope,node}` ·
`POST /api/vault-revoke|vault-delete` · `POST /api/vault-import {scrub}` · `POST /api/vault-lease {id,node}`
(family-mesh authed -- the only cross-node read path). Vault lens = the per-install management UI.

## Extension contract (the only way for extensions)
- An extension DECLARES the secrets it needs (`requires[]`, function `secrets[]`) and reads them ONLY via
  `_deploy_env(key)` -- never its own secret file, never hardcoded.
- Setup agents WRITE secrets into the vault (`/api/vault-set`), not into `.env` or bespoke files.
- Legacy per-extension secret files (e.g. google-workspace `secrets/`, slack `bot_token`) are migrated into the
  vault and the extension converted to `_deploy_env`, then the file is retired.
- Engine modules with their own config also resolve vault-first: pass `_deploy_env` into `init(ctx)` and read
  `secret("KEY")`, never `cc.config`. (Granola is the reference: `GRANOLA_API_KEY` via `granola._api_key()` ->
  `_deploy_env` since v0.99.5 -- before that it read cc.config only, so a vault key was silently ignored.)

## Hard rules
- The vault key (`.vault_key`) + store (`.vault/`) + migrated `.env` archives are gitignored, NEVER shipped,
  per-install. Encryption requires `cryptography` (the vault refuses to store plaintext without it).
- No credential is ever committed, echoed in full, or shipped in the framework. Nothing hardcoded.
- `.env.claudefather` is deprecated to a bootstrap/import path only -- after migration the vault is the one store.
- Scope is the consent boundary: a node only ever gets secrets it is scoped for.
