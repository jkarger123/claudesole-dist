# Claude Code Reference (for building an AI Project Control Center)

Distilled from the OFFICIAL Claude Code documentation (fetched 2026-06-20).
Docs now live at https://code.claude.com/docs/en/ (old docs.claude.com/en/docs/claude-code/*
URLs 301-redirect there). Doc index: https://code.claude.com/docs/llms.txt

This file is a working reference for building a reusable, enterprise "AI project
control center" on top of Claude Code. Each feature section covers: WHAT it is,
WHY it matters for a control center, and a concrete HOW-TO / config snippet.

ASCII-only. No smart quotes, em-dashes, or emoji.

--------------------------------------------------------------------------------
## 0. Mental model (read first)

Claude Code is an agentic coding tool: it reads files, edits them, runs commands,
and loops autonomously until a task looks done. The single most important
constraint is the CONTEXT WINDOW: it holds the whole conversation plus every file
read and command output, and model quality degrades as it fills. Almost every
"best practice" exists to manage context. A control center should be designed
around the same constraint: scope context per task, push verbose work into
subagents, and enforce rules with hooks rather than prose.

Two layers of control exist, and they are NOT the same:
  - ADVISORY: CLAUDE.md, rules, skills, output styles. These shape behavior but
    are not guaranteed. The model can ignore them.
  - ENFORCED: settings.json permissions, hooks, sandboxing, managed policy.
    These are deterministic and apply regardless of what the model decides.
For anything that must always happen or must never happen, use the enforced layer.

--------------------------------------------------------------------------------
## 1. Overview / install / quickstart

WHAT: One engine, many surfaces (Terminal CLI, VS Code, JetBrains, Desktop app,
Web). The same CLAUDE.md, settings, and MCP servers work across all of them.

WHY for a control center: standardize on the Terminal CLI + the Agent SDK
(headless `claude -p`) as the programmable substrate; the other surfaces are for
humans. Everything below (settings, agents, hooks, skills, MCP) is file-based and
versionable, which is exactly what a control center needs.

HOW (install + first run):
```bash
# macOS / Linux / WSL native install (auto-updates)
curl -fsSL https://claude.ai/install.sh | bash
# or: brew install --cask claude-code
cd your-project
claude                 # interactive
claude -p "explain what this project does"   # headless / one-shot
```

Key doc links: overview /en/overview, quickstart /en/quickstart,
best-practices /en/best-practices, features-overview /en/features-overview.

--------------------------------------------------------------------------------
## 2. Settings and the settings hierarchy

WHAT: JSON config files (`settings.json`) applied in a precedence order. Highest
to lowest:
  1. Managed (enterprise policy: MDM/registry or `managed-settings.json`)
  2. Command-line args (session overrides)
  3. Local         `.claude/settings.local.json`  (gitignored, personal)
  4. Project       `.claude/settings.json`         (committed, team-shared)
  5. User          `~/.claude/settings.json`       (personal, all projects)

Managed file locations:
  - macOS:   /Library/Application Support/ClaudeCode/managed-settings.json
  - Linux/WSL: /etc/claude-code/managed-settings.json
  - Windows: C:\ProgramData\ClaudeCode\managed-settings.json (Program Files dir)
  Drop-in dir `managed-settings.d/*.json` is supported.

WHY for a control center: this is your boundary system. Commit a project
`settings.json` for team-shared, reviewable policy; keep secrets/personal tweaks
in `settings.local.json` (gitignored). For a true enterprise control center,
push a managed policy that users CANNOT override (deny rules, sandbox, auth lock).

HOW (representative settings.json):
```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "model": "claude-sonnet-4-6",
  "permissions": {
    "allow": ["Bash(npm run test *)", "Read(package.json)"],
    "deny":  ["Bash(curl *)", "Read(./.env)", "Read(./secrets/**)"],
    "ask":   ["Bash(git push *)"],
    "additionalDirectories": ["../shared-lib"]
  },
  "env": { "NODE_ENV": "production" },
  "hooks": { },
  "agent": "code-reviewer",
  "cleanupPeriodDays": 30
}
```
Useful keys: `model`, `fallbackModel`, `env`, `permissions`, `hooks`, `agent`
(default main-thread agent), `outputStyle`, `autoMemoryEnabled`,
`claudeMd` (managed-only inline CLAUDE.md), `claudeMdExcludes`,
`disableSkillShellExecution`, `disableClaudeAiConnectors`,
`forceLoginMethod` / `forceLoginOrgUUID` (auth lock), `sandbox.enabled`.

Validation: managed settings parse tolerantly (bad entries stripped); user/
project/local are strict (whole file rejected if invalid). Run `claude doctor`
to validate all sources. `/config key=value` changes a single setting.

--------------------------------------------------------------------------------
## 3. Permissions and permission modes

WHAT: Per-tool allow/deny/ask rules plus session-wide permission modes. Rule
syntax is `Tool` or `Tool(pattern)`:
  - `Bash(npm run test *)`  trailing " *" = prefix match (mind the space)
  - `Read(./secrets/**)`, `Edit(src/**/*.ts)`  glob file patterns
  - `mcp__<server>` or `mcp__<server>__*`  MCP server / tool patterns
  - `Agent(Explore)`  deny/allow a specific subagent
  - `Skill(deploy *)` allow/deny a specific skill

Permission modes (set via `--permission-mode`, the `/permissions` UI, or agent
frontmatter):
  - default            prompt for risky actions
  - acceptEdits        auto-accept file edits + common fs commands (mkdir/mv/cp)
  - plan               read-only exploration, no edits
  - auto               a classifier model approves routine work, blocks risky
  - dontAsk            auto-deny anything not explicitly allowed (locked-down CI)
  - bypassPermissions  skip all prompts (DANGEROUS; still blocks rm -rf / etc.)

WHY for a control center: permissions are the per-agent boundary. A read-only
research agent gets read tools only; a deploy agent gets a narrow Bash allowlist;
CI runs use `dontAsk` so nothing unexpected executes. Deny rules in MANAGED
settings are the hard floor nobody can lift.

HOW:
```bash
claude --permission-mode dontAsk -p "list all API endpoints"
claude -p "fix lint" --allowedTools "Bash(npm run lint *),Read,Edit"
claude --permission-mode auto -p "fix all lint errors"   # classifier-gated
```
Doc: /en/permissions, /en/permission-modes, /en/sandboxing.

--------------------------------------------------------------------------------
## 4. Memory: CLAUDE.md hierarchy, imports, rules, auto memory

WHAT: Two complementary memory systems, both loaded at the START of every session:
  - CLAUDE.md files: instructions YOU write (advisory context, not enforcement).
  - Auto memory: notes CLAUDE writes itself across sessions (per repo).

CLAUDE.md load order (broad to specific; later wins on conflict):
  1. Managed policy CLAUDE.md (org-wide; cannot be excluded)
       macOS /Library/Application Support/ClaudeCode/CLAUDE.md
       Linux/WSL /etc/claude-code/CLAUDE.md ; Windows C:\Program Files\ClaudeCode\CLAUDE.md
  2. User      ~/.claude/CLAUDE.md
  3. Project   ./CLAUDE.md  or  ./.claude/CLAUDE.md
  4. Local     ./CLAUDE.local.md   (gitignore it)
Files are CONCATENATED (not overriding). Ancestor dirs load in full at launch;
SUBDIRECTORY CLAUDE.md files load on demand when CLAUDE reads files there.

Imports: `@path/to/file` pulls another file into context at launch (relative to
the importing file). Recursive up to 4 hops. To mention a path WITHOUT importing,
wrap in backticks. Imports DO consume context (no savings vs inlining).

Rules: `.claude/rules/*.md` (and `~/.claude/rules/`) split instructions into
topic files. Path-scoped rules load ONLY when matching files are touched:
```markdown
---
paths: ["src/api/**/*.ts"]
---
# API rules
- All endpoints must validate input.
```
This is the key context-saver: a rule that only matters for API code does not
burn tokens on every session.

Auto memory: on by default (v2.1.59+). Stored at
`~/.claude/projects/<project>/memory/MEMORY.md` (+ topic files). First 200 lines
or 25KB of MEMORY.md load every session. Toggle with `autoMemoryEnabled` or env
`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. Subagents can have their own memory.

WHY for a control center: this is your SCOPED-CONTEXT lever, and the #1 way to
avoid token waste. Keep root CLAUDE.md short (target < 200 lines: long files get
ignored). Push path-specific or procedural detail into rules and skills so they
load only when relevant. For monorepos / multi-pillar trees, per-directory
CLAUDE.md gives each module its own scoped context automatically, and
`claudeMdExcludes` skips other teams' files.

HOW:
  - `/init` generates a starter CLAUDE.md (or suggests improvements).
  - `/memory` lists every loaded CLAUDE.md / rule / auto-memory file and lets you
    edit them; also the auto-memory toggle.
  - `claudeMdExcludes` (any settings layer; arrays merge):
    ```json
    { "claudeMdExcludes": ["**/monorepo/other-team/CLAUDE.md"] }
    ```
  - Managed inline CLAUDE.md (managed/policy settings only):
    ```json
    { "claudeMd": "Always run make lint before committing.\nNever push to main." }
    ```
Gotchas: block-level HTML comments in CLAUDE.md are stripped before context
(use them for maintainer notes, free). Root CLAUDE.md survives /compact; nested
ones reload only when their dir is touched again. If CLAUDE keeps ignoring a
rule, the file is probably too long. AGENTS.md is NOT read; import it
(`@AGENTS.md`) or symlink. Doc: /en/memory, /en/best-practices.

--------------------------------------------------------------------------------
## 5. Subagents (.claude/agents) -- per-tool / per-role agents

WHAT: Specialized assistants, each in its OWN fresh context window, with a custom
system prompt, restricted tools, own model, and own permissions. CLAUDE delegates
to one when a task matches its `description`; only the summary returns to the main
conversation. Defined as Markdown + YAML frontmatter.

Built-in agents: Explore (Haiku, read-only, fast search), Plan (read-only,
plan-mode research), general-purpose (all tools), plus statusline-setup and
claude-code-guide.

Scope / priority (high to low): managed > `--agents` CLI flag > project
`.claude/agents/` > user `~/.claude/agents/` > plugin `agents/`. Identity comes
from the `name` field, not the filename or subfolder. Restart session to pick up
hand-edited files (or use `/agents`, which is live).

WHY for a control center: subagents ARE your "per-tool agents." Each repeatable
worker (security reviewer, test runner, db reader, migration bot) becomes a
versioned file with locked-down tools and the right model (route cheap work to
Haiku). They preserve main-context (verbose output stays in the subagent),
enforce constraints (tool allowlists per role), and standardize behavior across
the whole org when checked into a plugin.

HOW (project subagent file `.claude/agents/code-reviewer.md`):
```markdown
---
name: code-reviewer
description: Expert code review specialist. Use proactively after code changes.
tools: Read, Grep, Glob, Bash       # allowlist; omit to inherit all
model: sonnet                        # sonnet|opus|haiku|fable|<id>|inherit
permissionMode: default              # default|acceptEdits|auto|dontAsk|plan|bypassPermissions
memory: project                      # user|project|local (cross-session learning)
---
You are a senior code reviewer. Run git diff, review modified files, and report
critical issues / warnings / suggestions with specific fixes.
```
Key frontmatter: `tools` (allowlist) / `disallowedTools` (denylist; supports
`mcp__server` patterns), `model`, `permissionMode`, `maxTurns`, `skills`
(preload skill content), `mcpServers` (scope MCP to this agent only), `hooks`
(lifecycle hooks scoped to the agent), `memory`, `isolation: worktree`
(isolated git worktree), `effort`, `background`, `color`.

Invoke: natural language ("use the code-reviewer subagent..."), @-mention to
force it, or `claude --agent code-reviewer` to run the WHOLE session as that
agent (its prompt replaces the default). Disable one with
`permissions.deny: ["Agent(Explore)"]`. Restrict which agents a main-thread agent
can spawn with `tools: Agent(worker, researcher)`. Subagents can nest (depth 5
max). A "fork" inherits the full conversation instead of starting fresh.
Doc: /en/sub-agents.

--------------------------------------------------------------------------------
## 6. Skills and custom slash commands (.claude/skills, .claude/commands)

WHAT: Skills are `SKILL.md` files that package reusable instructions/workflows.
IMPORTANT: custom slash commands HAVE MERGED INTO SKILLS. `.claude/commands/x.md`
and `.claude/skills/x/SKILL.md` both create `/x`. Old `commands/` files still
work; skills add a folder for supporting files, frontmatter controls, and
auto-loading. Unlike CLAUDE.md, a skill's BODY loads only when used (cheap until
needed). Skills follow the open Agent Skills standard (agentskills.io).

Locations (override order enterprise > personal > project; plugin skills are
namespaced):
  - Enterprise (managed)   org-wide
  - Personal   ~/.claude/skills/<name>/SKILL.md
  - Project    .claude/skills/<name>/SKILL.md   (also nested per-package dirs)
  - Plugin     <plugin>/skills/<name>/SKILL.md  -> /plugin:name

WHY for a control center: skills are your REPEATABLE OPS as code. Multi-step
procedures (deploy, release, audit, fix-issue, summarize-changes) become typed
`/commands` your whole team runs identically. They keep CLAUDE.md lean (move
procedures out of it). `disable-model-invocation: true` guarantees a side-effect
op (deploy) only fires when a human types it. `allowed-tools` pre-approves the
exact tools the op needs so it runs without prompts.

HOW (`.claude/skills/deploy/SKILL.md`):
```markdown
---
name: deploy
description: Deploy the application to production
disable-model-invocation: true              # only a human can trigger /deploy
allowed-tools: Bash(git *) Bash(make deploy *)
context: fork                               # optional: run in an isolated subagent
argument-hint: [environment]
---
Deploy $ARGUMENTS to production:
1. Run the test suite
2. Build
3. Push to the deployment target
4. Verify the deployment succeeded
```
Substitutions: `$ARGUMENTS` (all args), `$0`/`$1`/`$ARGUMENTS[N]` (positional),
`$name` (named via `arguments:` frontmatter), `${CLAUDE_SESSION_ID}`,
`${CLAUDE_SKILL_DIR}`.
Dynamic context injection: `` !`shell command` `` (inline) or a ```! fenced
block runs BEFORE CLAUDE sees the skill and inlines the output (great for
"here is the live git diff / PR data"). Disable org-wide with
`disableSkillShellExecution: true` (best in managed settings).
Invocation control: `disable-model-invocation: true` (human-only),
`user-invocable: false` (model-only background knowledge). Restrict model access
with permission rules `Skill(name)` / `Skill(name *)`, or deny the `Skill` tool.
Skills work in headless mode: put `/skill-name args` in the `-p` prompt string.
Doc: /en/skills, built-ins /en/commands.

--------------------------------------------------------------------------------
## 7. Hooks (PreToolUse / PostToolUse / etc.) -- guardrails + automation

WHAT: Shell commands (or HTTP / prompt / agent / mcp_tool handlers) that fire at
fixed lifecycle events. Unlike CLAUDE.md, hooks are DETERMINISTIC and run
regardless of what the model decides. This is the enforcement layer.

Events (subset):
  - Session: SessionStart, SessionEnd, Setup
  - Per-turn: UserPromptSubmit, Stop, StopFailure
  - Per-tool: PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest
  - Subagent: SubagentStart, SubagentStop
  - Other: Notification, PreCompact, FileChanged, InstructionsLoaded, Elicitation
Can BLOCK: PreToolUse, UserPromptSubmit, Stop, PermissionRequest. Cannot:
PostToolUse, SessionStart.

Configured in settings.json (or plugin `hooks/hooks.json`) with a `matcher`
(tool name; supports `Edit|Write`, regex, `mcp__memory__.*`) and an optional
`if` condition (e.g. `Bash(rm *)`).

Hook IO: input arrives as JSON on stdin (session_id, cwd, hook_event_name,
tool_name, tool_input, etc.). Control behavior via exit code or JSON on stdout:
  - exit 0  success (stdout JSON processed)
  - exit 2  BLOCK; stderr is fed back to CLAUDE
  - other   non-blocking error (stderr to transcript)

WHY for a control center: hooks are your SAFETY GUARDRAILS and your AUTOMATION
glue. Use PreToolUse to hard-block dangerous commands or writes to protected
paths (your "never flash without passing the gate" class of rule). Use PostToolUse
to auto-format/lint after every edit. Use Stop to refuse to end a turn until tests
pass. Use SessionStart to inject fresh state. These run every time, no exceptions,
which CLAUDE.md cannot promise.

HOW (block destructive bash via PreToolUse, settings.json):
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command",
                    "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh" }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "npm run lint:fix" }] }
    ]
  }
}
```
Blocking hook script (preferred structured form):
```bash
#!/bin/bash
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
if echo "$CMD" | grep -qiE '\brm -rf\b'; then
  jq -n '{hookSpecificOutput:{hookEventName:"PreToolUse",
          permissionDecision:"deny",
          permissionDecisionReason:"Destructive command blocked by policy"}}'
else
  exit 0
fi
```
(Equivalently: write to stderr and `exit 2` to block.)
Tip: CLAUDE can write hooks for you ("write a hook that blocks writes to
migrations/"). Browse configured hooks with `/hooks`. Doc: /en/hooks,
/en/hooks-guide.

--------------------------------------------------------------------------------
## 8. MCP (Model Context Protocol) -- external integrations + security

WHAT: Open standard for connecting CLAUDE to external tools/data (GitHub, Jira,
Slack, Sentry, Postgres, Figma, custom servers). Transports: HTTP (recommended
for remote), stdio (local process), SSE (deprecated), WebSocket. Tools appear as
`mcp__<server>__<tool>`.

Scopes (precedence local > project > user > plugin > claude.ai connector):
  - local   `~/.claude.json` (per project, private)   [default]
  - project `.mcp.json` in repo root (committed, team-shared)
  - user    `~/.claude.json` (all your projects)

WHY for a control center: MCP is how the control center reaches the rest of your
stack (issue trackers, DBs, monitoring, your own internal APIs). Commit a project
`.mcp.json` so the whole team gets the same connectors. Tool Search (default on)
defers MCP tool definitions until needed, so you can wire many servers without
blowing up context.

SECURITY (critical for enterprise):
  - Untrusted servers + servers that fetch external content = PROMPT INJECTION
    risk. Only connect servers you trust.
  - Project `.mcp.json` servers require explicit approval before use
    (reset with `claude mcp reset-project-choices`).
  - Restrict with permission rules: `deny: ["mcp__<server>__*"]`, or scope a
    server to a single subagent via `mcpServers` frontmatter so the main
    conversation never sees it.
  - Enterprise: managed MCP config (`managed-mcp.json`) with `allowedMcpServers`
    / `deniedMcpServers` allowlists; `--strict-mcp-config` / `--bare` ignore
    ambient config. Pin OAuth scopes with `oauth.scopes`. Disable cloud
    connectors with `disableClaudeAiConnectors: true`.
  - `headersHelper` and stdio servers run arbitrary shell only after workspace
    trust is accepted.

HOW:
```bash
claude mcp add --transport http github https://api.githubcopilot.com/mcp/ \
  --header "Authorization: Bearer $GH_PAT"
claude mcp add --transport stdio db -- npx -y @bytebase/dbhub \
  --dsn "postgresql://readonly:pass@host:5432/db"
claude mcp list ; claude mcp get github ; /mcp   # /mcp does OAuth + status
```
Committed `.mcp.json` with env expansion (`${VAR}` / `${VAR:-default}`):
```json
{
  "mcpServers": {
    "api": {
      "type": "http",
      "url": "${API_BASE_URL:-https://api.example.com}/mcp",
      "headers": { "Authorization": "Bearer ${API_KEY}" }
    }
  }
}
```
Doc: /en/mcp, /en/mcp-quickstart, /en/managed-mcp, /en/security.

--------------------------------------------------------------------------------
## 9. Headless mode / Agent SDK / automation

WHAT: `claude -p "<prompt>"` (alias `--print`) runs non-interactively. This is the
Agent SDK via CLI; Python and TypeScript SDK packages exist for full programmatic
control (callbacks, structured outputs, native message objects).

Key flags:
  - `--output-format` text | json | stream-json
  - `--json-schema '<schema>'`  forces structured output (in `structured_output`)
  - `--allowedTools` / `--disallowedTools`  scope tools per run
  - `--permission-mode` (dontAsk for locked-down CI; acceptEdits for write tasks)
  - `--max-turns`, `--append-system-prompt`, `--system-prompt`
  - `--continue` / `--resume <session_id>`  multi-step sessions
  - `--bare`  skip auto-discovery of hooks/skills/plugins/MCP/CLAUDE.md for
    reproducible CI (only explicit flags take effect; recommended for scripts)

WHY for a control center: headless mode is how the control center DRIVES CLAUDE:
cron jobs, CI gates, batch fan-out, pipelines. `--output-format json` gives you
`session_id`, `total_cost_usd`, and a per-model cost breakdown for spend tracking.
`--bare` guarantees the same result on every machine (no ambient config drift).
This is the backbone of "scheduled/automated AI ops."

HOW:
```bash
# CI typo linter (pipe diff; no Bash perm needed to read it)
git diff main | claude --bare -p "report typos as file:line + issue" \
  --output-format json | jq -r '.result'

# Locked-down CI run
claude --bare --permission-mode dontAsk -p "apply lint fixes" \
  --allowedTools "Read,Edit,Bash(npm run lint *)"

# Structured extraction
claude -p "extract function names from auth.py" --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}' \
  | jq '.structured_output'

# Fan-out across files
for f in $(cat files.txt); do
  claude --bare -p "Migrate $f. Return OK or FAIL." \
    --allowedTools "Edit,Bash(git commit *)"
done

# Multi-step with a captured session id
sid=$(claude -p "start a review" --output-format json | jq -r '.session_id')
claude -p "now focus on db queries" --resume "$sid"
```
Scheduling: Routines (Anthropic-managed cron, survive machine-off, can trigger on
API/GitHub events; create via `/schedule`), Desktop scheduled tasks (local), and
`/loop` (in-session polling). CI integrations: GitHub Actions, GitLab CI/CD.
Doc: /en/headless, /en/agent-sdk/overview, /en/cli-reference, /en/routines.

--------------------------------------------------------------------------------
## 10. Output styles

WHAT: `outputStyle` setting (e.g. "Explanatory", "Concise", custom) changes how
CLAUDE communicates. Set in settings.json or via `/output-style`.

WHY for a control center: pick a consistent voice for dual-audience output
(engineer vs customer-facing). Lower priority than the structural features above;
mentioned for completeness.

HOW: `{ "outputStyle": "Explanatory" }` in settings.json. (Rebuilds on /clear.)
Doc: /en/settings (outputStyle key).

--------------------------------------------------------------------------------
## 11. Plugins and marketplaces -- packaging + distribution

WHAT: A plugin bundles skills, agents, hooks, MCP servers, LSP servers,
background monitors, default settings, and `bin/` executables into one
installable unit. Manifest at `.claude-plugin/plugin.json`. Plugin skills/agents
are namespaced (`/my-plugin:deploy`).

WHY for a control center: plugins are how you DISTRIBUTE the control center
itself. Package your standard agents + guardrail hooks + ops skills + MCP wiring
into one versioned plugin and install it across every repo/team from a private
marketplace. Updates ship by bumping `version`. This turns the control center
from per-repo config into a reusable, governed product.

HOW (minimal plugin):
```
my-plugin/
  .claude-plugin/plugin.json   # {"name","description","version","author"}
  skills/deploy/SKILL.md
  agents/code-reviewer.md
  hooks/hooks.json
  .mcp.json
  settings.json                # only "agent"/"subagentStatusLine" honored
```
```bash
claude --plugin-dir ./my-plugin        # local dev/test
/plugin                                 # browse/install marketplaces
/plugin marketplace add <org/repo>      # add a (private) marketplace
/plugin install my-plugin@my-marketplace
/reload-plugins                         # pick up changes without restart
```
Marketplace = a repo with `.claude-plugin/marketplace.json`. Host it privately
for internal-only distribution. Official: `claude-plugins-official`; community:
`claude-community`. Validate before publish: `claude plugin validate`.
Note: plugin agents do NOT honor `hooks`/`mcpServers`/`permissionMode`
frontmatter (security); copy into `.claude/agents/` if you need those.
Doc: /en/plugins, /en/plugin-marketplaces, /en/discover-plugins,
/en/plugins-reference.

--------------------------------------------------------------------------------
## 12. Official best practices (condensed, actionable)

  - GIVE CLAUDE A WAY TO VERIFY ITS WORK. A test, build exit code, linter, or
    screenshot diff closes the loop so CLAUDE iterates without you. Escalate the
    gate: in-prompt -> /goal condition -> Stop hook -> adversarial review subagent.
    Make CLAUDE show evidence, not assert success.
  - EXPLORE -> PLAN -> CODE -> COMMIT. Use plan mode to separate research from
    edits; skip it for one-sentence changes.
  - BE SPECIFIC. Name files (`@path`), reference example patterns, describe the
    symptom + likely location + what "fixed" means.
  - KEEP CLAUDE.md SHORT. Test each line: "would removing this cause a mistake?"
    If no, cut it or convert it to a hook. Bloat makes CLAUDE ignore real rules.
  - MANAGE CONTEXT AGGRESSIVELY. `/clear` between unrelated tasks; after two
    failed corrections, /clear and re-prompt; `/compact <focus>` to steer
    summarization; subagents for verbose investigation.
  - REDUCE PROMPTS SAFELY. Auto mode (classifier), permission allowlists, or
    sandboxing -- each cuts interruptions while keeping control.
  - PREFER CLI TOOLS (gh, aws, gcloud) over ad-hoc API calls -- most
    context-efficient.
  - SCALE OUT. Non-interactive `-p` for CI/cron; parallel sessions (worktrees,
    agent teams); fan-out loops; writer/reviewer two-session pattern; adversarial
    review subagent before "done."
  - COMMON FAILURES: kitchen-sink session, correct-over-and-over, over-specified
    CLAUDE.md, trust-then-verify gap, infinite unscoped exploration. Fixes:
    /clear, prune, always verify, scope or delegate.

Doc: /en/best-practices.

--------------------------------------------------------------------------------
## 13. Feature -> control-center mapping (cheat sheet)

  Per-tool / per-role agents      -> Subagents (.claude/agents) + tool allowlists
  Safety guardrails (hard rules)  -> Hooks (PreToolUse deny, Stop gate) + managed deny perms
  Auto-format / post-edit checks  -> Hooks (PostToolUse)
  Repeatable ops (deploy/audit)   -> Skills (.claude/skills) [+ disable-model-invocation]
  Scoped context / avoid bloat    -> CLAUDE.md hierarchy + path-scoped rules + auto memory
  Per-agent boundaries            -> Permissions (allow/deny/ask) + permission modes
  Integrations (Jira/DB/monitor)  -> MCP (.mcp.json) + managed MCP allowlists
  Scheduled / unattended ops      -> Headless claude -p + Routines/cron + --bare
  Org-wide distribution           -> Plugins + private marketplace
  Hard enterprise policy          -> Managed settings + managed CLAUDE.md (uneditable)
  Spend tracking                  -> claude -p --output-format json (total_cost_usd)
  One bounded expert answer       -> claude -p --agent <name> (persona + tool scope enforced)
  Act on that answer in code      -> + --output-format json (parse result/verdict/cost/ms)
  MANY agents (broad or confident)-> a dynamic WORKFLOW (say "ultracode" / use the Workflow tool)

--------------------------------------------------------------------------------
## 14. Capability -> WHEN/WHY to reach for it (ClaudeFather playbook -- updated 2026-07-03)

Decision rule of thumb:
- Need ONE bounded expert answer you can act on -> `claude -p --agent <name> --output-format json`. In CF this is
  the **`_agent_run(agent, prompt)`** primitive (subscription, returns {result,cost,ms}); the `cc-review` / Agent Lab
  / incident-triage / change-review-gate all sit on it. Reach for it over a raw `_claude_text` Haiku call whenever the
  task wants an EXPERT with tools + enforced scope (read the repo, security lens, etc.), not just a quick opinion.
- Need MANY agents orchestrated -- to be COMPREHENSIVE (fan out + cover), CONFIDENT (independent + adversarial verify),
  or to take on SCALE one context can't hold -> a **dynamic workflow** (mention "ultracode" or ask to use the Workflow
  tool). CF used one to build the Agent Lab (2 codegen agents + a review pass). The server can also orchestrate
  `_agent_run` itself in Python (the review "deep" mode + the Agent Lab Panel are fan-outs) -- no Workflow tool needed
  at runtime. Pick a workflow when the WORK-LIST is knowable and parallel/verify pays off; scout inline first.
- Recurring, human-triggered capability -> a **skill** (`.claude/skills`) or a scoped **agent-tool** (`agents/`).
- A hard guardrail / post-edit automation -> a **hook** (PreToolUse deny / Stop gate / PostToolUse).
- An external system -> an **MCP** extension. Continue a specific past conversation -> **`--resume <id>`** (fork to branch).
- Unattended run -> `-p` + `--dangerously-skip-permissions` (or `--permission-mode`); pick a tier with `--model`
  (OMIT it to use the subagent's own configured model -- forcing one overrides its quality choice).

The three tiers of "an agent" in CF, and when each:
- `.claude/agents/*` **subagents** (code-reviewer, cost-reporter, deploy-checker, incident-scanner, security-auditor):
  invoked headless via `--agent` as FUNCTIONS, or by the main agent via the Task tool. Use for a scoped expert opinion.
- `agents/<slug>/` **agent-tools** (backup/cost/deploy/google/incidents/security/usage...): human-gated, read-only,
  session-based helpers surfaced in the Agents lens. Use for an operator-driven scoped operation.
- **Teams** (rung-4 rosters): multiple agents that must SHARE findings + reconcile. Use for the rare coordinate case.

Where CF already wires specialists into its LIFECYCLE (the pattern to extend): before a change propagates (the
change-review gate + CCR auto-review), on a resource spike / node wedge / job failure (incident triage), and an
opt-in weekly security-auditor beat. Deliberately NOT wired into the fast reflexes (self-heal, deterministic router)
-- those are better without an AI in the path. See docs/RESILIENCE.md + docs/SERVER_METRICS.md.

--------------------------------------------------------------------------------
## Source URLs (fetched 2026-06-20)

  https://code.claude.com/docs/en/overview
  https://code.claude.com/docs/en/settings
  https://code.claude.com/docs/en/permissions  (referenced)
  https://code.claude.com/docs/en/permission-modes  (referenced)
  https://code.claude.com/docs/en/memory
  https://code.claude.com/docs/en/sub-agents
  https://code.claude.com/docs/en/skills
  https://code.claude.com/docs/en/hooks
  https://code.claude.com/docs/en/hooks-guide  (referenced)
  https://code.claude.com/docs/en/mcp
  https://code.claude.com/docs/en/headless
  https://code.claude.com/docs/en/agent-sdk/overview  (referenced)
  https://code.claude.com/docs/en/plugins
  https://code.claude.com/docs/en/plugin-marketplaces  (referenced)
  https://code.claude.com/docs/en/best-practices
  Doc index: https://code.claude.com/docs/llms.txt
