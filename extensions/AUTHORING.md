# ClaudeFather Extensions -- authoring standard (every extension MUST follow this)

An Extension is an installable capability in the Marketplace lens. The promise to the user: install it, and a
**setup agent walks you through everything** (accounts, API keys, config) and teaches you how to use it. For
that to work, every extension MUST ship clear, structured instructions -- what it is, why you'd want it, how
it works, and the safe way to run it. No extension ships without this.

> **▶ If your extension contributes a LENS/UI: it MUST use the dashboard design system (`docs/DESIGN_SYSTEM.md`).**
> Build the lens from the shared primitives (`cc-head`/`cc-list`/`cc-item`/`cc-grid`/`cc-tile`/`cc-panel`/`cc-in`,
> `mini`/`btn`(+`danger`), `badge bdg-*`, `confirmM`/`promptM`/`alertM`, `toast`). NEVER a native dialog,
> off-palette/GitHub-hex color, inline-colored badge, or decorative header/button emoji. The preship linter
> (`command-center/ui_lint.py`) FAILS the ship on violations — so a one-off-styled lens cannot reach the fleet.

## THE STANDARD -- every extension is built to this (checklist)
Build EVERY extension to the same spec so they're consistent + agent-usable. An extension ships:
1. **`extension.json`** -- catalog card + model-facing `summary`/`description` + `provides[]`/`requires[]` (below).
2. **`SETUP.md`** -- the guided setup-agent script (fixed section order, below).
3. **`AGENT.md`** -- agent-facing "here's the tool you have + how to use it" (declare `agent_doc`); auto-injected
   into agent context ONLY where the extension is installed. Every extension that an agent would USE ships one.
4. **Credentials via the VAULT only** (see "Credentials & secrets" below) -- DECLARE needed secrets; READ them
   only via `_deploy_env(key)`; NEVER a bespoke secret file, cc.config secret, or hardcoded value.
5. **Draggables** (if it has items a user would hand to a session) -- declare `draggables[]` + attach `ssAttr`
   to rows so they drag into a Claude session (the generic `entity` sendable needs zero server code).
6. **A `lens`** (if it has a UI) -- declare the **`lens:{id,label,icon}`** OBJECT (this is what gives it a nav tab
   via `_ext_lenses()`; `provides:["lens:x"]` is informational ONLY and surfaces NOTHING). It self-shows when
   installed (extLenses), built dense (KPI strip + tables/2-col panels -- NEVER a stack of full-width cards).
7. **A `default_category`** -- which nav folder the lens lands in (Google/Workspace/Agency/Team/Integrations/
   System); the sidebar groups lenses into collapsed categories by default. EVERY extension declares one.
8. **Server functions** (if it needs server-side compute) -- declare `functions{}`; runs sandboxed; no worker.
9. **`inputs[]` / `outputs[]`** (forward-looking; for programmatic/non-agentic extensions) -- DECLARE what the
   extension consumes (files/text/etc.) and what it produces + WHERE the deliverable lands. The platform
   auto-renders the input form and routes the output. See "Programmatic extensions" below.
10. **`context_source`** (optional but encouraged) -- a function name that returns this extension's RELEVANT
   intel as context events, so it flows into the shared context layer and surfaces SUBJECT-keyed in agent
   briefs. See "Feeding the context layer" below.
10. **`tier`/`pricing`/`publisher`** (paid extensions ride the signed-entitlement gate).

> **AUTHORIZATION (non-negotiable).** Only **official** or **operator-approved custom** extensions ever run.
> *Official* = the extension ships in the MC-**signed** dist (its `extension.json` is in `core.sig.json`,
> verified vs `superadmin.pub` -- forging needs the MC private key). *Custom* = built locally in the
> `custom/extensions/` sandbox on a **developer-type** node and explicitly approved by the operator. Anything
> else is UNAUTHORIZED: it will not install or load, and a rogue dir under `extensions/` is **quarantined** on an
> appliance + flagged in Doctor. So you do NOT hand-drop extensions into a tenant's `extensions/` -- you author
> at Mission Control, it gets signed into the dist, and tenants receive it via `cc-update`. (Per `docs/EXTENSIONS.md`.)
Reversible install (uninstall archives, never deletes user data/keys). ASCII only. The sections below detail each.

## Credentials & secrets (the ONE way -- non-negotiable)
Every credential lives in the per-install **vault**; nothing sensitive ever enters the chat/transcript. (Full
reference: `command-center/vault/CLAUDE.md`; spec: `docs/CREDENTIALS.md`.)
- **DECLARE** what you need: `requires[].key` (env-style names), `byok.keys[].id`, function `secrets[]`. On
  install the platform AUTO-PROVISIONS an empty vault slot per key (Vault lens shows "needed by <ext>, not set").
- **READ** secrets ONLY via `_deploy_env(key)` (resolves the vault). NEVER your own `secrets/` file, NEVER a
  cc.config secret, NEVER hardcoded, NEVER printed.
- **COLLECT** a secret via the SECURE-FIELD flow, never by asking the user to paste it in chat: the setup agent
  runs `cc-secure request "<label>" vault:<KEY>` -> a box pops up for the user -> the value goes straight to the
  vault. To show the user a secret: `cc-secure reveal "<label>" <0600-file>`. (Agents know this from their brief.)
- Legacy bespoke secret files are migrated into the vault + retired (`vault_import_env`); don't add new ones.

## Required files (in `extensions/<id>/`)
### 1. `extension.json` -- the catalog entry + the model-facing trigger
```json
{
  "id": "kebab-id",                 // dir name; stable; [a-z0-9-]
  "name": "Human Name",
  "category": "integration",        // integration | agent-tool | skill | theme
  "version": "1.0.0",
  "icon": "G",                      // 1-3 chars/emoji for the card
  "summary": "One line: WHAT it does, in plain language.",
  "description": "2-4 sentences: WHAT it does + WHY it's valuable + HOW it works (the mechanism).",
  "provides": ["mcp:gmail", "notify:telegram"],   // capabilities it adds
  "requires": [ {"key":"X","label":"plain-language thing the user must have/get"} ],
  "setup_doc": "SETUP.md",
  "setup_agent": true,              // true => the Marketplace 'Set up' button opens a guided agent
  "default_category": "Integrations", // REQUIRED: nav folder for this ext's lens (Google|Workspace|Agency|
                                   //   Team|Integrations|System) -- sidebar groups lenses into collapsed categories
  "lens": {"id":"calls","label":"Calls","icon":"PH"}, // ONLY if it has a UI -- THIS object surfaces the nav tab
                                   //   (NOT provides:["lens:x"], which is informational only)
  "tier": "free",                   // OPTIONAL: "free" (default) | "paid" -- paid = locked until entitled
  "pricing": {"monthly_usd": 49},  // OPTIONAL (paid only): shown on the card; billing automation is separate
  "publisher": "ClaudeFather",     // OPTIONAL: who authors/houses it (official vs third-party)
  "agent_doc": "AGENT.md",         // OPTIONAL: agent-facing usage doc, AUTO-INJECTED into agent context ONLY
                                   //   on nodes where this extension is INSTALLED (default file: AGENT.md)
  "draggables": [                  // OPTIONAL: entity types this extension lets a user drag INTO a session
    { "kind": "entity",            //   use "entity" (generic, self-contained) unless you ship a payload resolver
      "label": "merchant",         //   human label
      "note": "drag a merchant into a Claude session" }
  ],
  "launch_group": "Tools",         // OPTIONAL: which group this extension's launch points show under
                                   //   in the New-session picker (defaults to "Extensions")
  "launch_points": [               // OPTIONAL: the logical places a user would launch an AGENT for this
                                   //   extension. Omit => the extension's own dir is the launch place.
    { "path": "extensions/my-ext", // PROJECT-relative folder the session launches in (required)
      "name": "My Extension",      // label (required)
      "description": "Build/extend the X integration.",  // one-line preview (optional)
      "icon": "🧩" }               // optional glyph
  ]
}
```
- `summary` + `description` are what the model/orchestrator sees at selection time -- write them as advertising
  that says WHAT and WHEN to use it. Weak text = the capability is invisible. (Same rule as skills/agents.)
- **Launch points (framework feature):** the New-session picker is built from declarable launch points. Any
  folder with a `CLAUDE.md` / `extension.json` is auto-recognized; declare `launch_points` to add or rename
  specific spots (and `launch_group` to place them). A NEW extension lights up its launch points with ZERO
  core change. When an agent is launched in a folder that has no `CLAUDE.md`, it is briefed to create one
  (an `# H1` title + a one-line description) so the place becomes a recognized, previewable launch point.

### 2. `SETUP.md` -- the guided walkthrough the setup agent runs (the heart of the promise)
It MUST contain these sections, in this order:
- **What it does** -- plain-language, concrete.
- **Why use it** -- the value / the problem it solves.
- **How it works** -- the mechanism (MCP server? bot? API? what data flows where).
- **Prerequisites** -- accounts/APIs the user needs (with where to get them).
- **Setup steps** -- NUMBERED, one action per step, wait-for-the-user between steps. Where each secret goes
  (always a gitignored deployment env -- never committed, never echoed in full).
- **Verify** -- a concrete check that it works.
- **Usage** -- 2-3 real things the user can now do.
- **Best practices / Safety** -- defaults (read-only first), least-privilege, what NOT to do, rate/authz limits.

## Categories -- how install wires each
- `integration` (MCP / external service): install records it; the setup agent writes the MCP server entry into
  the deployment's `.mcp.json` (or connects a claude.ai connector) + stores secrets in the gitignored env.
- `agent-tool`: payload is an `agents/<id>/` dir (charter + tools/run.py) -> appears in the Agents lens.
- `skill`: payload is a `SKILL.md` -> copied into `<scope>/.claude/skills/` -> appears in the Skills lens.
- `theme`: provides a `data-theme` palette + brand assets.

## Agent context injection (`AGENT.md`) -- per-node-clean tool awareness
Ship an optional **`AGENT.md`** (agent-facing): a concise "here is the tool you have + how to use it" doc.
The platform AUTO-INJECTS it into the launch brief of agents on this node (`_system_brief`) **only when the
extension is INSTALLED/enabled here**. A node that doesn't have the extension never hears about it -- e.g. a
CarSearch node without Skimlinks gets zero Skimlinks context, so agents there can't be told to use a tool that
isn't present. Keep it short (it's capped ~1.6KB), action-oriented (the APIs/commands/lens the agent should use),
and ASCII. This is how an extension makes itself usable by AGENTS, the same way `SETUP.md` makes it usable by a person.

## Draggables -- let users drag your items into a Claude session
A running platform theme: relevant things can be dragged straight into a session (the taskbar dock). An
extension/lens makes any item draggable by attaching `ssAttr({...})` to its row and declaring the types in
`draggables`. The generic, zero-server-code path is the **`entity`** sendable -- the descriptor carries its own
content:
```js
// in your lens row HTML:
'<div '+ssAttr({kind:'entity', name:m.name, title:m.name,
    fields:{Domain:m.domain, Commission:m.commission_rate+'%', Status:m.status},
    kind_label:'merchant'})+'>'+ ... +'</div>'
```
Drag that row onto a session tile (or tap the ➤ button) and the agent receives a clean markdown card about the
item. Use `fields:{label:value}` (auto-rendered) or a ready `body:"...markdown..."`. Ship a payload resolver +
`register_sendable("<kind>", fn)` only if you need SERVER-SIDE enrichment (e.g. fetch full detail by id).

## Server functions -- run extension code ON the ClaudeFather server (the unified runtime)
When an extension needs server-side compute (call AI APIs, transform data, talk to a DB) and return the result
to the user IN-CONSOLE -- with no external worker/host -- declare `functions` in extension.json. The platform
runs them in a **sandboxed subprocess** and the lens invokes them via `POST /api/ext-action {ext, action, payload}`
(a declared function for `action` is preferred over a `worker` block, so the same lens code works for either).
```json
"functions": {
  "analyze": {
    "entry": "server/analyze.py",     // path INSIDE the extension's installed dir (no traversal)
    "runtime": "python3",
    "secrets": ["OPENAI_API_KEY","ANTHROPIC_API_KEY"],  // ONLY these are injected into the child env (allowlist)
    "timeout_sec": 90, "mem_mb": 768,
    "tier": "official"                 // only 'official' (dist-shipped, reviewed) may run today
  }
}
```
The entry reads the request as **JSON on stdin** and writes its result as **JSON on stdout**. Security the runtime
enforces (because this runs your code on a box that holds secrets): the child gets a RESTRICTED env -- only the
secrets you declare, never the node's auth/mesh tokens or other extensions' keys; a hard timeout + CPU/file-size
(and best-effort memory) limits; output is size-capped; the entry must resolve inside your extension dir; every
call is audited to `_ext_fn.log`. Prefer server functions over a hosted worker -- they make the extension
self-contained (a downloaded ClaudeFather runs it with zero external infra). BYOK: declare the per-account keys;
the runtime resolves them (deploy env today; per-account store next).

## Paid extensions (entitlements) -- the monetization layer
A `"tier": "paid"` extension is **locked by default** and unlocks ONLY when this node holds a valid
**Mission-Control-signed entitlement** (Ed25519, same owner key as superadmin; private key MC-only,
`superadmin.pub` shipped to every install). This is deliberately un-bypassable by an agent on the node:
forging a token needs the private key, and editing the stored grant file just produces a token that fails
signature verification. There is **no honor-system plan flag** that unlocks paid extensions -- the signature
is the only authority. Default = locked, so a sold/downloaded product never leaks paid features.
- **Internal fleet nodes** are unlocked by issuing each a perpetual wildcard grant (`ext:"*"`, `days:0`).
- **External customers** get a per-extension grant with an expiry (`days:31`), re-issued monthly to renew;
  on lapse the extension re-locks (existing data the extension wrote to the tenant's own store is untouched).
- Mechanism (server.py): `entitlement_grant(node, ext, days)` mints + delivers (local, or pushed to a peer
  via the signed superadmin `set_entitlement`); `_entitled(eid)` is the gate checked at install (and callable
  at run-time by a payload). APIs: `GET /api/entitlements`, `POST /api/entitlement-grant|entitlement-revoke`.
- Billing automation (charging the card) is SEPARATE and not required: a future Stripe webhook simply calls
  `entitlement_grant` on payment. Authors only declare `tier`/`pricing`/`publisher`; the platform enforces.

## Programmatic extensions -- inputs, outputs & the deliverable contract (forward-looking)
An extension does NOT have to drive an agent. A **programmatic** extension is pure code (a `functions{}` entry)
that takes declared INPUTS and produces declared OUTPUTS. Declaring the I/O contract lets the platform render
the input form, run the function, and route the deliverable -- with zero bespoke UI. The run engine is LIVE:
`POST /api/ext-run {ext,fn,inputs}` -> `ext_run` marshals inputs -> runs the sandboxed function -> routes outputs
via the extensible `_ext_route_one` registry. (Custom programmatic extensions are built in the `custom/` sandbox
via the **Build** lens on a developer-type node -- scaffold, edit `server/run.py`, approve, run.)
```json
"inputs": [
  { "id": "report",              // stable key passed to the function
    "type": "file",              // file | files | text | number | select | boolean | secret | session | extension
    "label": "Report to analyze",
    "accept": [".pdf",".csv"],   // (file) extension/mime filter
    "from": "upload",            // OPTIONAL source hint: upload | deliverable | drive | vault | basket
    "required": true,
    "options": ["weekly","monthly"]   // (select)
  }
],
"outputs": [
  { "id": "summary",
    "type": "deliverable",       // WHERE it goes -- an OPEN, extensible registry (we are the official builder):
                                 //   deliverable (file in deliverables/) | inline (render in its lens) |
                                 //   download (browser) | email | telegram | slack (outward, review-gated) |
                                 //   agent (hand the file into a Claude session) | extension (chain into another
                                 //   extension's input) | webhook | tree (write into the project tree) | vault
    "label": "Summary report",
    "destination": "deliverables/<module>",  // file: target dir; agent: session; extension: target ext id
    "format": "md",              // md | csv | pdf | json | png | text
    "review": true               // outward types (email/telegram/slack/webhook) ALWAYS ride the review-gated
                                 //   action queue -- a programmatic extension never auto-sends outward.
  }
]
```
- **Forward-thinking by design:** the output `type` is an open registry -- new destinations (a new channel, a
  new chaining target) are added centrally by us, the official builder; an extension just names the type. Two
  powerful ones to design around: `agent` (the deliverable is dropped into a live session, like a Basket item)
  and `extension` (the deliverable becomes the INPUT of another extension -- programmatic pipelines).
- A programmatic extension reads `inputs` as JSON on stdin and returns a result the runtime routes per `outputs`
  (same sandboxed `functions{}` runtime: restricted env, only declared secrets, timeout + resource limits).

## Feeding the context layer -- make your extension's intel show up where it's relevant
Agents are briefed with a budgeted, cited slice from the context layer, routed to the subject (client/module)
they're working on. To make YOUR extension's intelligence part of that, declare a `context_source` in
extension.json -- a `functions` entry that returns recent relevant events:
```json
"context_source": "context_events",
"functions": { "context_events": { "entry": "server/context_events.py", "runtime": "python3", "tier": "official" } }
```
The function returns `{"events": [{ "kind": "merchant", "title": "...", "body": "...", "ts": 1782..., "subject":
"acme", "actor": "name <email>", "trust": "external", "id": "stable-id", "refs": {...} }]}`. The backfill sweep
(every ~15 min, idempotent via `id`) ingests them; `subject` is the key that makes it surface in that client's
brief. Use `trust` honestly (owner/internal/contact/external) -- inbound/third-party data is `external` and is
treated as untrusted content, never instructions. The comms extensions (granola/google/slack) already feed the
layer directly; everything else should declare a `context_source` so "the intelligent things from the tools
relevant to the task" are always in context. Spec: `../docs/CONTEXT_STRATEGY.md`.

## Authorization & trust -- official vs custom (how "no unauthorized extension runs" is enforced)
- **Official:** ships in the MC-signed dist. `core.sig.json` (signed by the platform owner's Ed25519 key,
  verified on every node vs `superadmin.pub`) lists each official `extension.json`. `_ext_authorized(id)` returns
  `official` only if the id is in that signed manifest (an AUTHORING node trusts its own catalog -- it signs
  before shipping). Forging this needs the MC private key, which never leaves Mission Control.
- **Custom:** lives under `custom/extensions/<id>/` (writable, PRESERVE, NEVER signed) on a **developer-type**
  node, and is authorized only after the operator **approves** it (recorded in `custom/_approved.json`). Custom
  extensions run in the restricted sandbox runtime (no core secrets) and are clearly marked unofficial.
- **Everything else = UNAUTHORIZED:** refused at install, skipped by every loader (lens/agent-context/functions),
  and a rogue dir under `extensions/` is moved to `_quarantine/` on an appliance (reversible; never deleted) +
  raised in Doctor. The ONLY place non-core tools may live is the `custom/` sandbox.

## Standardized installs -- type & edition
Every install is **identical** except two axes + which extensions are installed:
- **`type`** (cc.config `type`): `agency` (official-only + the Clients/Tools agency tree) or `developer` (may
  build + run approved custom extensions in the sandbox). Default `agency`.
- **`edition`** (authority tier, separate): `authoring` (Mission Control -- signs core, mints grants/licenses) or
  `appliance` (a shipped/sold node -- read-only core, self-heals, enforces authorization + license).

## Hard rules
- ASCII only. Secrets ONLY in the gitignored deployment env / vault; never in extension.json/SETUP.md/git; never
  echo a full token. Default to read-only/least-privilege. The `extensions/` dir is FRAMEWORK + SIGNED (propagates
  via cc-update; modifying or adding to it on a tenant is detected/quarantined); custom tools go in `custom/`.
- Per-deployment install state + secrets are PRESERVE (per-deployment, gitignored).
- Every extension is reversible (uninstall archives, never deletes user accounts/keys).
