# GitHub -- setup walkthrough

Brief for the setup agent: connect GitHub via its official MCP server, default to read-only, verify on one
repo. ASCII only. Confirm the exact endpoint/command at https://github.com/github/github-mcp-server.

## What it does
Lets agents search code, read files, open and triage issues and pull requests, and check CI/Actions status
across the repos you authorize.

## Why use it
The project lives in git. This lets an agent answer "what changed", "what's failing", and "open a PR for
this fix" from inside the control center instead of you switching to GitHub.

## How it works
GitHub's official MCP server. Two mechanisms:
- Remote (recommended): the hosted server at `https://api.githubcopilot.com/mcp/`, authorized with OAuth 2.1
  in the browser. No tokens stored locally.
- Local/headless: run GitHub's local MCP server with a fine-grained Personal Access Token.
Data flow: agent -> MCP tool -> GitHub API with your authorized scopes -> back to the agent.

## Prerequisites
- A GitHub account with access to the target repos.
- Remote: ability to complete a browser OAuth. Local: a fine-grained PAT (least-privilege).

## Setup steps
1. Choose remote (OAuth, easiest) or local (PAT, headless).
2. Remote: the install wired `github` -> `https://api.githubcopilot.com/mcp/` into the deployment `.mcp.json`;
   authorize in the browser when prompted and select the repos/scopes. Restart sessions to load it.
3. Local: create a fine-grained PAT scoped to ONLY the needed repos (read scopes first); store it as
   `GITHUB_PAT` in the gitignored deployment env; point `.mcp.json` at the local server. Never commit the PAT.

## Verify
Ask the agent to read the latest commit message and the open-PR count on ONE repo. Real values = connected.

## Usage
- "What changed in <repo> since yesterday, and is CI green?"
- "Summarize the open PRs that need review."
- "Open a PR for this fix." (only after you enable write + approve)

## Best practices / Safety
- Read-only first; enable write (open/close PRs, edit issues) only when you need it, behind explicit approval.
- Fine-grained PAT scoped to just the needed repos; never commit it; never echo it in full.
- Uninstall removes the `.mcp.json` wiring; it never touches your repos.
