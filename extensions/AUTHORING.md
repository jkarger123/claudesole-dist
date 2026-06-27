# ClaudeFather Extensions -- authoring standard (every extension MUST follow this)

An Extension is an installable capability in the Marketplace lens. The promise to the user: install it, and a
**setup agent walks you through everything** (accounts, API keys, config) and teaches you how to use it. For
that to work, every extension MUST ship clear, structured instructions -- what it is, why you'd want it, how
it works, and the safe way to run it. No extension ships without this.

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

## Hard rules
- ASCII only. Secrets ONLY in the gitignored deployment env; never in extension.json/SETUP.md/git; never echo
  a full token. Default to read-only/least-privilege. The extension dir is FRAMEWORK (propagates via
  cc-update); per-deployment install state + secrets are PRESERVE (per-deployment, gitignored).
- Every extension is reversible (uninstall archives, never deletes user accounts/keys).
