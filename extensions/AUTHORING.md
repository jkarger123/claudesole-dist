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
  "setup_agent": true               // true => the Marketplace 'Set up' button opens a guided agent
}
```
- `summary` + `description` are what the model/orchestrator sees at selection time -- write them as advertising
  that says WHAT and WHEN to use it. Weak text = the capability is invisible. (Same rule as skills/agents.)

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

## Hard rules
- ASCII only. Secrets ONLY in the gitignored deployment env; never in extension.json/SETUP.md/git; never echo
  a full token. Default to read-only/least-privilege. The extension dir is FRAMEWORK (propagates via
  cc-update); per-deployment install state + secrets are PRESERVE (per-deployment, gitignored).
- Every extension is reversible (uninstall archives, never deletes user accounts/keys).
