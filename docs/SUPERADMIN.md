# Superadmin grants — "Mission Control, make it so" (cryptographically authorized)

Lets the **platform owner** (via Mission Control) issue an authoritative instruction to **any node in any
family** — proven to be from the owner, so the receiving node executes it instead of treating it as an
untrusted peer. This is the *legitimate* channel for owner-directed fleet changes (vs. a casual mesh message,
which a node correctly refuses).

## Security model — PUBLIC-KEY (Ed25519), the default since v0.10.0
Every install is **automatically under the owner's superadmin**, with no per-node provisioning:

- The owner holds an **Ed25519 PRIVATE key on Mission Control** (`.superadmin_ed25519`, 0600, gitignored,
  **never shipped**). Generate it once: `POST /api/superadmin-keygen`.
- The matching **PUBLIC key ships in the framework** (`superadmin.pub`, a framework_path), so **every
  install** — the owner's nodes *and* any future public install — verifies the owner's grants out of the box.
- MC signs a grant with the private key (`alg: ed25519`); any node verifies it against the shipped public key.
- A **compromised install holds only the public key** — it can verify, it can **never forge**. (MC
  compromise = platform-owner compromise = out of scope; true of any scheme where the owner can act.)
- Every grant is **node-bound** (`node` must equal the target — no retarget), **short-lived** (`exp`), and
  **single-use** (`nonce` — no replay), and limited to the **action allowlist**.

This realizes the asymmetric-authority model: **DOWN** = the owner can force any node; **UP** = nodes can only
file *change requests* (the CCR system) which the owner approves — MC never acts on a peer's say-so.

### Fallback: derived-key (HMAC), no dependency
For a node that lacks `cryptography` or is explicitly provisioned, a grant can instead be HMAC-signed
(`alg: hmac`): the **master** stays only on MC, each node holds its own `node_key = HMAC(master, "sa-v1:"+id)`,
and compromising one node can't forge to another. The `alg` is inside the signed payload, so it can't be
downgraded. `superadmin_grant` auto-signs Ed25519 when the private key is present, else HMAC.

Dependency: `pip install --user cryptography` for the CC's python (the installer does this). Without it a node
still boots — it just can't verify Ed25519 grants until installed (doctor warns).

## Setup (public-key — the default)
1. On **Mission Control**, generate the owner keypair ONCE (operator-authed):
   `curl -H "X-CC-Token: <pin>" -XPOST localhost:8800/api/superadmin-keygen`
   → writes `.superadmin_ed25519` (private, 0600, gitignored — keep it ONLY on MC) and `superadmin.pub`.
2. **Ship `superadmin.pub`** with the framework (it's already a framework_path; commit + push it to dist).
   Every install that pulls the framework now trusts your superadmin automatically — **no per-node step.**
3. Done. `superadmin-send` works against any node carrying that `superadmin.pub`.

### Fallback provisioning (derived-key, for a node without `cryptography`)
1. On MC set `"superadmin_master": "<openssl rand -hex 32>"` in `cc.config.json` (600; never commit/mesh).
2. `POST /api/superadmin-derive {"node":"afp"}` → that node's derived key.
3. Out-of-band, set `"superadmin_node_key": "<key>"` in that node's `cc.config.json` → restart it.

## Use it (from Mission Control, operator-authed)
```
curl -H "X-CC-Token: <pin>" -XPOST localhost:8800/api/superadmin-send \
  -d '{"node":"afp","action":"accept_skip_permissions"}'
```
`superadmin-send` mints a signed grant and POSTs it to the node's `/api/superadmin-exec` in one call.
(`/api/superadmin-grant` returns the signed grant without sending, for fully out-of-band delivery.)

### Allowlisted actions (tight by design — never arbitrary execution)
| action | effect |
|---|---|
| `ping` | proof-of-authority echo (safe; use to verify provisioning) |
| `accept_skip_permissions` | runs the per-user skip-permissions self-heal on that node |
| `set_config` | sets ONE allowlisted cc.config key (`params:{key,value}`) — allowlist: `mesh_auth_enforce`, `mesh_reply_sla`, `subscription_monthly`, `pipeline_stale_sec`. Secrets (auth_token/mesh_token/master) are NOT settable this way. |
| `instruct` | `params:{text}` — deliver an AUTHORIZED owner directive into the node's chief as a clean turn, marked SUPERADMIN (not the untrusted peer frame), so the agent acts on it. The broad **"make the agent do anything"** power. |
| `cc_update` | `params:{upstream?, restart?}` — pull the latest framework on the node (defaults to the dist); optionally restart after. |
| `restart` | reload the node's CC in place (os.execv). |

New actions are added deliberately in `superadmin_exec` — there is intentionally no generic shell "run
anything"; `instruct` routes through the node's agent (which itself runs under the deployment's guardrails).

## Endpoints
- `POST /api/superadmin-exec` — node side. **Not** operator-auth/family-token gated (the signature IS the
  auth), so the owner reaches a node cross-family. Verifies the grant, runs the allowlisted action.
- `POST /api/superadmin-send` / `…-grant` / `…-derive` — MC side. Require the master **and** operator auth,
  so only the Mission Control operator can issue grants or derive node keys.
