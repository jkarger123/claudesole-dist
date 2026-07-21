---
name: skill-builder
description: >
  Build a new Claude Code skill from a plain-language description. Use when someone says "make a skill for
  X", "turn this into a /command", "capture this workflow", "I keep doing this, automate it", or when a
  repeated procedure (see cc-skill scan) should become a reusable /skill. Drafts a well-formed SKILL.md
  (sharp trigger description, lean body, correct frontmatter, right scope), scaffolds it, and lints it.
argument-hint: "[what the skill should do]"
allowed-tools: Read, Write, Edit, Bash(cc-skill*), Bash(*skill_scan.py*)
---

You are turning an idea (or an observed repeated procedure) into a real Claude Code skill. A skill is a
`SKILL.md` folder; the folder name is the `/command`; the **description is the only thing the model sees
until the skill runs** — so the description is the whole product. Make it excellent.

## 1. Pin down four things (ask only what you can't infer)
- **What it does + when to use it** — one or two sentences, in the words a user would actually type, with
  real keywords. This becomes the `description` (the trigger). If it's vague, the skill is invisible.
- **Scope** — `project` (this codebase only) · `node` (all this node's projects — the **default**) ·
  `fleet` (promote later). Only go fleet if it's genuinely useful on other nodes.
- **Side effects?** — if it deploys/pushes/restarts/deletes or spends money, it must be **human-only**
  (`disable-model-invocation: true`) so the model can't fire it unprompted.
- **Steps** — the actual procedure. If it came from `cc-skill scan`, use the observed tool sequence as the
  skeleton and confirm the specifics.

First check for overlap: run `cc-skill list`. If a near-match exists, **sharpen that one instead of forking**.

## 2. Scaffold it
```
cc-skill new <name> --scope <node|project> --desc "WHAT it does + WHEN to use it"
```
This writes the SKILL.md stub in the right dir (`~/.claude/skills/<name>/` for node,
`<project>/.claude/skills/<name>/` for project). For a fleet skill, scaffold as `node` first, then
`cc-skill promote <name>` once it's proven.

## 3. Write the body (edit the scaffolded SKILL.md)
- **Lean** (< ~500 lines). It re-enters context every turn once loaded — no narrative, just what to do.
- **Numbered steps**, real commands, exact paths. Put heavy reference in sibling files and link them
  (`See [reference.md](reference.md)`), so it loads only when needed.
- **`allowed-tools`** — pre-approve exactly the tools the steps need (e.g. `Bash(git*), Read`). No more.
- **Bundle scripts** next to SKILL.md and call them from the body (don't inline a big script).
- Useful frontmatter when it fits: `argument-hint`, `arguments`, `paths:` (glob — only activate when working
  in matching files), `model:` / `effort:` overrides, `context: fork` + `agent:` (run in an isolated subagent).

## 4. Lint + test (do not skip)
```
cc-skill lint <name>
```
Fix every flag — a thin/empty description or empty body silently kills discoverability. Then **actually
invoke `/<name>`** in a session using the phrasing a real user would type, and confirm it fires and works.
Tune the description until it triggers on the right requests and not the wrong ones.

## 5. Ship
- **node / project**: it's already live — the file *is* the deployment.
- **fleet**: `cc-skill promote <name>` packages it as a signed `category:"skill"` extension. From Mission
  Control, sign + ship per `docs/MISSION_CONTROL.md` (in the ClaudeFather framework root); from a tenant, it files a CCR.

## Notes
- The gold standard is a description that reads like the user's own request. Lead with the use case.
- Reuse before you build; sharpen before you fork; node-scope before you promote.
- Full field reference + precedence: `docs/MEMORY_SKILLS_AGENTS.md` and the Skill
  Authoring Agent charter (`skill-authoring/AGENT.md`).
