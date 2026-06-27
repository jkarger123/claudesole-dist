# Credential Vault — MC-hosted, encrypted, checkout/lease on demand

The enterprise way to give nodes their secrets without hand-copying API keys into every node's
`.env.claudefather`. Mission Control holds ONE encrypted vault; each node **leases** a secret at
runtime over the family-authenticated channel, caches it in **RAM only**, and re-leases — so revoking
at MC takes effect within one lease TTL and a stolen disk image holds no plaintext.

## Why this design
- **Checkout/lease on demand** (not push): a node asks for a secret when it needs it; the value is never
  written to the node's disk. Revocable — flip a secret to revoked at MC and leases stop within one TTL.
- **Native ClaudeFather vault** (not an external KMS): reuses the platform's own trust primitives — the
  `cryptography` lib (already the superadmin dep) for encryption-at-rest, and the family **mesh token**
  for lease authentication. Zero new infra; a downloaded ClaudeFather has it built in.
- **Shared vs node-unique (billing isolation):** a secret carries a SHARED value plus optional per-node
  overrides. Nodes on the shared key share one bill; a node with its own override is isolated. One id,
  one scope, many possible values.

## Model
A secret = `{ id, label, scope[], shared:<cipher>, per_node:{node:<cipher>}, revoked }`.
- **`scope`** = who may lease it: `["*"]` (any family node) or a list of node ids (`["afp","shopos"]`).
- **`shared`** = the default encrypted value; **`per_node[node]`** = an override for one node (wins on lease).
- Values are **Fernet ciphertext**; the key (`.vault_key`, 0600, gitignored, MC-only) is the only way to
  decrypt. `_vault.json` alone (e.g. in a backup) is useless without the key.

## Pieces (server.py)
- **MC management (operator-only)** — `vault_set` / `vault_revoke` / `vault_delete` / `vault_list`
  (`vault_list` NEVER returns values). Gated by `_operator_only()` (a family mesh token does NOT grant
  management — only an operator credential does).
- **Lease (family-token authed)** — `vault_lease(id, node)` → decrypted value if the node is in scope and
  the secret isn't revoked. Reachable on the mesh ingress track (`/api/vault-lease`); the handler verifies
  `X-Mesh-Token` against the family/superadmin token.
- **Node side** — `vault_get(id)` leases from `CC.config.vault_url` (the MC base url) and caches in RAM for
  `vault_lease_ttl` (default 600s). **`_deploy_env(key)` falls back to it**, so every existing secret read
  (`_deploy_env("OPENAI_API_KEY")`, extensions, server functions) transparently resolves from the vault
  when a local value isn't present.
- **Audit** — every set/revoke/delete/lease appends to `_vault_audit.log` (jsonl); the last 40 show in the
  Vault lens.

## APIs
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/api/vault` | operator | list secrets (metadata only) + recent audit |
| POST | `/api/vault-set` | operator | `{id, value, label?, scope?, node?}` → encrypt + store |
| POST | `/api/vault-revoke` | operator | `{id, revoked}` → toggle revoked |
| POST | `/api/vault-delete` | operator | `{id, node?}` → delete a per-node override or the whole secret |
| POST | `/api/vault-lease` | family mesh token | `{id, node}` → decrypted value if allowed |

## Set up
1. **On Mission Control** (the overseer): open the **Credential Vault** lens. Needs the `cryptography`
   package (already present for superadmin). The Fernet key auto-creates on first use at
   `$CC_HOME/.vault_key` (0600, gitignored).
2. **Add a secret:** id (e.g. `OPENAI_API_KEY`), value, scope (`*` or specific node ids). Optionally add a
   per-node override (enter a node id) for billing isolation.
3. **Point a node at the vault:** set `"vault_url": "http://<mc-host>:8800"` (or the tailnet URL) in that
   node's `cc.config.json`, and make sure it shares the family `mesh_token`. Restart the node. From then on
   any missing `_deploy_env(...)` key is leased from the vault automatically.
4. **Rotate/revoke:** update the value (re-set) or Revoke in the lens; nodes pick up the change within one
   lease TTL (they re-lease on cache expiry).

## Hard rules
- **`.vault_key`, `_vault.json`, `_vault_audit.log` are MC-only state — gitignored, NEVER shipped.** They
  are not in `framework_paths`, so `cc-update` never propagates them.
- Management is **operator-only**; a node holding only the family mesh token can lease in-scope secrets but
  can NEVER set/revoke/list. Lease auth requires a valid family/superadmin token.
- Encryption needs `cryptography` (Fernet). Without it the vault refuses to store (never falls back to
  plaintext).
- The vault is a SUPERSET of `.env.claudefather`, not a replacement: local env still wins (os.environ →
  .env.claudefather → vault). Keep a node bootable even if MC is briefly unreachable by leaving truly
  critical local secrets in its env; lease the shared/rotating ones.
