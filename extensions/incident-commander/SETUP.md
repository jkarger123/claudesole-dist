# Incident Commander -- setup walkthrough

An agent-tool, not an external service. Install copies it into `agents/`; it then shows in the Agents lens.
ASCII only. No accounts needed for the agent itself (its data sources are other extensions).

## What it does
Adds a scoped "Incident Commander" agent that, on demand, gives you ONE ranked "what's on fire and what do I
do" answer -- pulling Sentry issues, PagerDuty incidents + on-call, and local error/nightly logs.

## Why use it
It turns several read-only integrations into a single, prioritized incident posture with recommended next
steps -- the natural capstone agent for a control center whose core question is "is it healthy?".

## How it works
Agent-tool payload (a CLAUDE.md charter + tools/run.py). Install copies it to `agents/incident-commander/`,
where it appears in the Agents lens (Run for a readiness report, Talk for live triage). It calls the
installed Sentry/PagerDuty MCP integrations + reads local logs. No new external server.

## Prerequisites
- None for the agent itself. Best paired with the `sentry` and/or `pagerduty` extensions (it degrades to
  logs-only without them and tells you so).

## Setup steps
1. Install from the Marketplace -> the charter + run.py land in `agents/incident-commander/`.
2. (Recommended) install the `sentry` and/or `pagerduty` extensions and run their Set up for full coverage.
3. Open the Agents lens and confirm "Incident Commander" appears.

## Verify
Run it (Agents lens -> Run) and confirm you get a readiness report listing which incident sources are active.
Then Talk to it for a ranked posture.

## Usage
- "What's on fire right now and what should I do first?"
- "Rank today's incidents by blast radius."
- "Anything in the logs that Sentry/PagerDuty missed?"

## Best practices / Safety
- Read-only by construction: it reports + recommends, never acks/resolves/deploys. Write actions go through
  the underlying integration's own approval gate, driven by you. Uninstall archives the agent (reversible).
