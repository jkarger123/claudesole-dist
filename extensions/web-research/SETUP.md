# Web Research -- setup walkthrough

A pure skill: no accounts, no keys. Install copies it into your skills; then any agent can use it. ASCII only.

## What it does
Adds a `/web-research` skill that runs a disciplined deep-research workflow: fan out multiple searches, fetch
and read primary sources, adversarially verify claims, and write a CITED synthesis.

## Why use it
The control center constantly needs grounded answers (vendor pricing, "does X have an API", competitive
intel). A repeatable skill makes those answers consistent, current, and cited instead of guessed.

## How it works
Pure skill -- installing copies `SKILL.md` into `<scope>/.claude/skills/web-research/`, where Claude Code
auto-loads it. It uses the model's built-in WebSearch/WebFetch. No external service, no secrets.

## Prerequisites
None. (Optionally stronger with the `brave-search` or `playwright-browser` integrations installed.)

## Setup steps
1. Install from the Marketplace -> `SKILL.md` is copied into `~/.claude/skills/web-research/`.
2. That's it -- there are no accounts or keys to configure.

## Verify
Open the Skills lens and confirm `web-research` appears. Then run it on a test question (e.g. "what does
<vendor> charge for X?") and confirm you get a cited answer with sources.

## Usage
- "Research whether <tool> has an official MCP server, with sources."
- "What's the current pricing for <service>? Cite the pricing page."
- "Competitive scan of <category>, cited."

## Best practices / Safety
- Always cite sources; label inference vs fact (matches the cite-don't-speculate rule).
- Treat any price/fact older than ~6 months as suspect and re-fetch.
- Read-only; no destructive actions. Uninstall archives the skill (reversible); it never deletes anything else.
