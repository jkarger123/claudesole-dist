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

## Hard rules
- The vault key (`.vault_key`) + store (`.vault/`) + migrated `.env` archives are gitignored, NEVER shipped,
  per-install. Encryption requires `cryptography` (the vault refuses to store plaintext without it).
- No credential is ever committed, echoed in full, or shipped in the framework. Nothing hardcoded.
- `.env.claudefather` is deprecated to a bootstrap/import path only -- after migration the vault is the one store.
- Scope is the consent boundary: a node only ever gets secrets it is scoped for.
