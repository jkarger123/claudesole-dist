# CONTROL CENTER BLUEPRINT -- a portable, productizable AI project control plane

Status: design blueprint (research synthesis, 2026-06-20)
Audience: anyone evolving this control center into a drop-in product for any project/company.
Scope: how to turn the current stdlib-Python "command center" (lenses, Chief-of-Staff agent,
modules, Ralph loops, backup hub, usage analytics, live in-browser terminal) into a UNIFORM
"agent-per-tool" platform that is portable (drop any project in), covers all the bases an
enterprise needs, navigates easily, and wastes no tokens re-building context.

Every non-obvious claim below is sourced; see "SOURCES" at the end. ASCII-only by project rule.

--------------------------------------------------------------------------------
## 0. THE BIG IDEA (one paragraph)

A control center is, structurally, an Internal Developer Platform (IDP): a single pane of
glass that turns the operational domains of running software (security, backup, deploy,
incidents, cost, docs, roadmap, onboarding, data) into self-service "paved roads" so a team
does not have to master each domain separately. The organizing goal is reducing cognitive
load (Team Topologies). Our twist: each paved road is operated by a SCOPED CLAUDE AGENT --
a directory with its own CLAUDE.md, its own tools, and a one-click "start session" entry
point that launches `claude` already in the right place with the right context. The dashboard
is the catalog + launcher; the agents are the workers; an orchestrator (Chief of Staff)
routes. Portability comes from a hard split between a generic FRAMEWORK and per-project
CONFIG (12-Factor): the engine ships fixed, each project supplies declarative config +
secrets + its own tree. "No wasted tokens" comes from the Claude Code context hierarchy
(root -> pillar -> tool CLAUDE.md loaded on demand), scoped subagents with isolated context,
on-demand skills, and durable handoffs instead of re-explaining state every session.

--------------------------------------------------------------------------------
## 1. THE AGENT-PER-TOOL ARCHITECTURE

### 1.1 Principle

Every capability of the control center is the SAME shape: a self-contained "agent-tool". An
agent-tool is a directory that is simultaneously (a) a Claude Code subagent definition,
(b) a scoped CLAUDE.md context, (c) a small set of executable tools/scripts it owns, and
(d) a dashboard lens with a "start session" button. Uniformity is the product: once one
agent-tool exists, adding the next is filling in the same template, and the dashboard
discovers it automatically.

This mirrors how IDPs treat every service identically as a catalog "entity" with the same
descriptor shape (Backstage catalog-info.yaml), and how Claude Code treats every specialized
worker identically as a subagent with the same frontmatter (.claude/agents/*.md). We fuse
the two: a control-center agent-tool IS a catalog entity AND a subagent.

### 1.2 Standard layout for ONE agent-tool

Each agent-tool lives under `agents/<name>/` and has EXACTLY this layout:

```
agents/
  <name>/                         # e.g. security, backup, usage, ideas, chief
    agent.md                      # the entry point: Claude Code subagent frontmatter + body
    CLAUDE.md                     # scoped context loaded when a session opens here
    tool.yaml                     # catalog descriptor (what the dashboard reads)
    tools/                        # the executable tools this agent owns (scripts/CLIs)
      <verb>.py / <verb>.sh
    skills/                       # OPTIONAL: long reference material, loaded on demand only
      <topic>/SKILL.md
    state/                        # this agent's durable memory (handoffs, last-run, findings)
      HANDOFF.md                  # latest durable handoff (resume pointer)
      memory/MEMORY.md            # auto-loaded short memory (<=200 lines / 25 KB)
    routines/                     # OPTIONAL: cron specs this agent owns (scheduled audits)
      <name>.cron.yaml
```

Rationale for each file:

- `agent.md` -- the single "start session" entry point. It is a valid Claude Code subagent
  file: YAML frontmatter (`name`, `description`, `tools`, `disallowedTools`, `model`,
  `permissionMode`, `memory`) + a Markdown body that is the agent's system prompt. The
  dashboard's "start session" launches `claude` with cwd = this directory (or `--agent
  <name>`), so the body becomes the operating instructions and the scoped CLAUDE.md loads
  automatically. Per Claude Code, subagents run in their OWN context window and return only
  a summary -- this is the core token-isolation mechanism.

- `CLAUDE.md` -- scoped context for any session opened in this dir. Loaded automatically
  because Claude Code loads CLAUDE.md from filesystem root DOWN to the working directory;
  subdirectory CLAUDE.md files load on demand when that dir is entered, so they cost zero
  tokens until the agent is actually used. Keep it LEAN (target < ~200 lines; long files
  reduce adherence). Use `@path` imports for anything bulky.

- `tool.yaml` -- the catalog descriptor the dashboard reads to render the lens, the launch
  button, status, owner, and scorecard checks. This is our `catalog-info.yaml` equivalent.
  See schema in 1.4.

- `tools/` -- the deterministic scripts the agent drives (e.g. `git-backup.sh`,
  `secretscan.py`, `usage_report.py`). Few, consolidated, well-described tools beat many
  thin one-per-endpoint tools (Anthropic "writing tools for agents"). Namespace them by the
  agent prefix so the model never confuses cross-agent tools.

- `skills/` -- OPTIONAL long-form know-how (runbooks, domain references). Skills load ONLY
  when invoked, so a 2,000-line runbook costs nothing until needed. Set
  `disable-model-invocation: true` for material that should never auto-load.

- `state/HANDOFF.md` + `state/memory/MEMORY.md` -- durable handoff + auto-memory so a fresh
  session resumes instead of rebuilding context. MEMORY.md's first 200 lines / 25 KB auto-load
  at session start; HANDOFF.md is the human/agent-readable "where we left off" pointer.

- `routines/` -- OPTIONAL scheduled audits this agent owns (e.g. nightly backup verify,
  weekly secret-rotation check). These become cron entries (section 4).

### 1.3 The agent.md frontmatter template (uniform)

```
---
name: <name>                      # unique, kebab-case; e.g. security
description: >                    # WHEN to use this agent (drives auto-delegation + lens copy)
  <one or two sentences: the domain this agent owns and when to hand off to it>
tools: Read, Grep, Glob, Bash     # scoped allowlist -- only what this agent needs
disallowedTools: Write, Edit      # OPTIONAL denylist (e.g. read-only auditors)
model: sonnet                     # or inherit / haiku for cheap agents
permissionMode: default           # acceptEdits for trusted automation
memory: project                   # enable persistent per-agent memory under state/
---

# <Name> agent

ROLE: <one line>.
OPERATE FROM: agents/<name>/ (you are scoped here; do not wander).
YOU OWN: <the domain and the tools/ in this dir>.
START EVERY SESSION: read state/HANDOFF.md, then state/memory/MEMORY.md, then act.
TOOLS YOU DRIVE: <list tools/ with one line each>.
HAND OFF WHEN: <conditions to escalate to chief or another agent>.
END EVERY SESSION: update state/HANDOFF.md (resume pointer) + record findings.
```

This template is the WHOLE contract. New capability == copy the directory, fill the template.

### 1.4 tool.yaml (catalog descriptor) schema

```
apiVersion: cc/v1
kind: AgentTool
metadata:
  name: security
  title: Security
  owner: platform-team
  lens_icon: shield
  lens_order: 30
spec:
  purpose: "Continuously assess security posture and flag drift."
  entrypoint: agent.md            # what "start session" launches
  scope_dir: .                    # cwd the dashboard opens claude in (relative to this file)
  model: sonnet
  tools:                          # the deterministic tools this agent owns
    - id: secretscan
      run: tools/secretscan.py
      desc: "Scan tree for committed secrets before backup/push."
  routines:                       # scheduled audits (-> cron)
    - id: nightly_posture
      schedule: "0 3 * * *"
      run: tools/posture_report.py
  scorecard:                      # checks this agent must keep green (see 1.5)
    - id: no_committed_secrets
      desc: "Latest secretscan found zero secrets."
    - id: backups_encrypted
      desc: "Backup target is encrypted at rest."
  handoff: state/HANDOFF.md
```

The dashboard reads every `agents/*/tool.yaml`, renders one lens per agent-tool, and wires the
launch button to `entrypoint` + `scope_dir`. This is how new agent-tools appear with zero
dashboard code -- discovery, exactly like Backstage catalog discovery via Location entities.

### 1.5 Scorecards -- the anti-dropped-ball layer

Borrow the Cortex/Port/OpsLevel scorecard pattern: every agent-tool declares `scorecard`
checks in its tool.yaml. The dashboard rolls them into a single maturity grid (one row per
agent-tool, Bronze/Silver/Gold or pass/fail). Checks make standards measurable rather than
aspirational, so gaps across ALL domains are visible at a glance and nothing silently rots
(e.g. "backups verified in last 24h", "no committed secrets", "incident runbook exists",
"docs build green", "SLOs defined"). Time-boxed pushes use "initiatives" (Cortex) -- a
dated campaign to get a check green. The Chief agent reads the grid first every session.

### 1.6 How the dashboard launches an agent-tool SCOPED

The current server already launches persistent `claude` sessions in a pane cwd over a PTY.
Generalize that to: "start session" for agent X == open a tmux/PTY pane with
`cwd = agents/X/`, run `claude` (optionally `--agent X`), which loads agents/X/CLAUDE.md +
all ancestor CLAUDE.md (root master, pillar) automatically, plus the agent.md body as the
operating prompt. The session is attachable in the browser terminal. No special per-agent
launch code -- the directory + tool.yaml is the whole config.

Three launch flavors (all the same mechanism, different cwd):
- Tool session: cwd = agents/X/ (operate the capability).
- Module session: cwd = any project module folder that carries its own CLAUDE.md (the
  existing "modules" system -- folders are scopes).
- Orchestrator session: cwd = control root, the Chief agent that delegates to the others.

--------------------------------------------------------------------------------
## 2. PORTABILITY / PACKAGING -- "drop any project in"

### 2.1 The framework / config split (12-Factor)

Portability is one hard boundary: the generic ENGINE ships fixed; everything project-specific
is declarative CONFIG + secrets supplied per install. Twelve-Factor's litmus test: the
framework repo "could be made open source at any moment without compromising any credentials."
This mirrors Backstage (engine + plugins are generic; app-config.yaml + per-repo
catalog-info.yaml are org-specific) and data-driven design (reusable engine + externalized
declarative logic).

FRAMEWORK (ships, never edited per project):
- `command-center/server.py` (stdlib web + PTY terminal + lens renderer + catalog discovery)
- `command-center/ralph_runner.py` (the generic autonomous-loop driver)
- The agent-tool TEMPLATE (`templates/agent-tool/` -- the standard layout from 1.2)
- The cron/routine runner, backup hub, usage-analytics collector, scorecard roller
- A library of STOCK agent-tools (section 3) shipped as defaults

CONFIG (per project, supplied at init; never committed with secrets):
- `cc.config.yaml` -- the project manifest (schema in 2.3)
- `agents/` -- the agent-tools enabled for this project (stock + custom)
- The PROJECT TREE itself + its CLAUDE.md hierarchy (root master -> pillar -> module)
- `.env` / vault references -- secrets, integration tokens, host endpoints (12-Factor:
  env vars; OWASP: never hardcode, centralize, least-privilege, rotate, audit)
- `machines.yaml` -- the fleet (which boxes, ssh aliases, what each is for)

### 2.2 Install / init flow ("new project" setup)

A scaffolder, exactly like Backstage `/create` (pick template -> fill params -> generate ->
register). One command:

```
cc init                 # interactive: asks the questions below, scaffolds, registers
cc init --from cc.config.yaml   # non-interactive (CI / repeatable)
```

`cc init` does:
1. Ask: project root path, project name, primary language/stack, fleet machines, which stock
   agent-tools to enable, integrations (git host, deploy target, secrets backend, chat).
2. Scaffold: write `cc.config.yaml`; create `agents/` populated with the chosen stock
   agent-tools (copied from `templates/`); create the root master CLAUDE.md from a template
   (with the project's pillars + the context-hierarchy boilerplate); create `state/` dirs.
3. Wire secrets: write `.env.example`, prompt for real values into `.env` or a vault ref
   (never committed). Validate dev/prod parity expectations (12-Factor X).
4. Register: scan the project tree for existing modules (folders that should carry a
   CLAUDE.md), offer to seed CLAUDE.md stubs, and add them to the catalog -- the same
   "register an existing service" path as Backstage (commit a descriptor, import it).
5. Verify: run each enabled agent-tool's scorecard once; print the maturity grid; print the
   "start session" URLs. Green-by-default onboarding.

Adding ONE new capability later == `cc add-agent <name> [--from stock/<name>]` which copies
the template, opens the editor on agent.md + tool.yaml, and the dashboard auto-discovers it.

### 2.3 cc.config.yaml schema (the project manifest)

```
apiVersion: cc/v1
kind: ControlCenterConfig
project:
  name: acme-platform
  root: /abs/path/to/project          # the project tree (its CLAUDE.md hierarchy lives here)
  pillars:                            # top-level sub-trees, each with its own CLAUDE.md
    - {name: web,  path: web,  desc: "customer frontend"}
    - {name: api,  path: api,  desc: "backend services"}
hierarchy:
  root_claude_md: CLAUDE.md           # the master index (lean pointers, not a dump)
  knowledge_index: KNOWLEDGE_INDEX.md # running index of findings docs
fleet:                                # the machines (12-Factor: per-deploy config)
  - {alias: studio, role: home,   host: local}
  - {alias: ci,     role: deploy, host: ci@10.0.0.5, key: ~/.ssh/ci_key}
agents:                               # enabled agent-tools (stock or custom)
  - security
  - backup
  - deploy
  - incidents
  - cost
  - docs
  - roadmap
  - onboarding
  - data
  - chief                             # the orchestrator (always last)
integrations:                         # references only; secrets via env/vault
  git_host:   {kind: github, org: acme, token_env: GH_TOKEN}
  deploy:     {kind: cloudflare, account_env: CF_ACCOUNT}
  secrets:    {kind: dotenv, path: .env}      # or {kind: vault, addr_env: VAULT_ADDR}
  chat:       {kind: none}
dashboard:
  port: 8799
  bind: 127.0.0.1                     # local-only by default (see security defaults)
```

This single file is what makes the platform "drop-in": the same engine reads it for any
project. Everything secret lives behind `*_env` references, never inline.

### 2.4 Distribution

Ship the framework as a git template repo (or a tiny installer) containing
`command-center/`, `templates/`, and `agents-stock/`. `cc init` clones/copies the framework,
generates the per-project config, and leaves the project tree untouched except for seeded
CLAUDE.md stubs. Upgrades = pull the framework; config + agents/ are yours.

--------------------------------------------------------------------------------
## 3. THE STOCK SET OF AGENT-TOOLS (what a real enterprise control center ships with)

Each is one directory following section 1.2. The set maps onto the standard operational
domains of running software. One-line purpose each; "good" defined by the cited source.

ALREADY IN THIS SYSTEM (formalize as agent-tools):
- chief        -- Orchestrator/Chief of Staff: reads the scorecard grid, routes work to the
                  other agents, owns cross-cutting decisions. (orchestrator-worker pattern)
- backup       -- Versioned backups + secret-scanned pushes to the GitHub hub; verifies
                  restores. Good = tested RTO/RPO, encrypted at rest.
- usage        -- Token/cost analytics from Claude transcripts; per-agent + per-project spend;
                  flags waste. Good = FinOps Inform->Optimize->Operate.
- ideas        -- Idea/roadmap intake and triage. Good = a living strategic roadmap.
- modules      -- Module registry: keeps folder CLAUDE.mds + the CC:CHILDREN/CC:NOTES indexes
                  coherent; enforces "single source of truth" placement.
- ralph        -- Autonomous-loop operator: designs/launches/monitors Ralph loops, owns the
                  progress/rules/verify pattern.

ADD TO COMPLETE ENTERPRISE COVERAGE:
- security     -- Continuous security-posture assessment + secret hygiene + dependency/audit
                  drift. Good = automated detect-and-react posture (NIST).
- deploy       -- CI/CD visibility + release orchestration to the fleet; tracks the four DORA
                  keys. Good = frequent, automated, low-fail-rate deploys (DORA).
- observability-- SLI/SLO definitions, dashboards, alerting health. Good = quantitative SLOs
                  acted on before users feel pain (Google SRE).
- incidents    -- Incident intake, on-call, runbook execution, blameless postmortems. Good =
                  postmortems fix systems not people (Google SRE).
- docs         -- Docs-as-code surfaced per module (Diataxis: tutorials/how-to/reference/
                  explanation). Good = docs organized by user need; build stays green.
- cost         -- (if not folded into usage) cloud/LLM FinOps beyond Claude tokens.
- roadmap      -- Strategic roadmap + initiatives that drive scorecard checks to green.
- onboarding   -- Golden-path "create a new X" scaffolders + new-dev paved roads. Good =
                  low cognitive load, fast time-to-first-PR (Team Topologies / Spotify).
- data         -- Database/data administration: backups, replication, migration safety. Good =
                  resilient, recoverable data systems (cloud reliability pillar).
- compliance   -- Controls + evidence for SOC 2 / ISO 27001 audits. Good = independently
                  attestable controls mapped to Trust Services Criteria.

Not every project enables all of these -- `cc.config.yaml: agents:` selects the subset. The
template guarantees they are uniform regardless of who wrote them.

--------------------------------------------------------------------------------
## 4. BEST PRACTICES BAKED IN (no dropped balls, no token waste)

### 4.1 The context hierarchy (root -> pillar -> tool), loaded on demand

Claude Code loads CLAUDE.md from filesystem ROOT down to the session's working directory.
Ancestors load in full at session start; subdirectory CLAUDE.md files load ONLY when a file
in that dir is read -- so deep context costs zero tokens until used. Design accordingly:

- ROOT master CLAUDE.md = a LEAN INDEX of pointers (pillars, hard rules, where things live),
  not a dump. (This project's rule: "reference, don't inline"; keep CLAUDE.md a lean index.)
- PILLAR CLAUDE.md = how to work that pillar.
- TOOL/MODULE CLAUDE.md = the specific scope, loaded only when you operate there.
Bulky material goes in skills/ or findings docs and is `@`-imported or read on demand. Keep
each CLAUDE.md under ~200 lines (longer files reduce instruction adherence).

Operating consequence: ALWAYS START FROM THE RIGHT PLACE. Launching a session in agents/X/
(or a module folder) is what loads X's context and nothing irrelevant. The dashboard's
scoped-launch buttons enforce this -- you never operate the security capability from a random
cwd that pulls the wrong context.

### 4.2 Scoped subagents = isolated context = the main window stays clean

High-volume work (searching the tree, running tests, processing logs, broad research) is
delegated to subagents, which run in a SEPARATE context window and return only a summary.
This is the single biggest token saver: verbose output never pollutes the orchestrator's
window. Each agent-tool IS such a subagent; the Chief delegates to them. Use read-only
auditors (`disallowedTools: Write, Edit`) for security/usage/docs scans. Scope each agent's
`tools:` to only what it needs -- fewer, namespaced, well-described tools (Anthropic tool
guidance) so the model picks correctly and cheaply.

Multi-agent is worth it only for high-value, parallelizable, breadth-first work -- it can use
~15x the tokens of a single agent (Anthropic). So: parallel fan-out for research/audits;
single agent for tightly interdependent edits. The Chief decides which.

### 4.3 Durable handoffs (resume, do not rebuild)

Every agent-tool keeps `state/HANDOFF.md` (the resume pointer) and `state/memory/MEMORY.md`
(auto-loaded, first 200 lines / 25 KB). The session-end discipline: write/refresh HANDOFF.md,
update the resume pointer, record findings to the right module's CLAUDE.md CC:NOTES region (a
finding belongs to the module it is ABOUT, not the cwd you found it in). Next session reads
the handoff and continues -- no re-explaining state, no re-deriving context = no wasted tokens.
This is the durable-memory analog of the existing Ralph progress.md pattern.

### 4.4 The compact tool + cache discipline

Long sessions waste tokens; use /compact (or auto-compaction) to summarize and drop stale
tool output, and /clear between unrelated tasks. Add a "Compact Instructions" section to the
agent's CLAUDE.md so the RIGHT state survives compaction. Avoid cache-busting churn mid-task
(switching models, toggling MCP, changing effort) -- these invalidate the prompt cache;
editing files/CLAUDE.md does NOT. Prefer MCP tool deferral (only tool names load until used)
and skills with `disable-model-invocation: true` to keep reference material out of context
until called.

### 4.5 Routines / cron (scheduled audits = the safety net)

Each agent-tool can own `routines/` cron specs (nightly backup verify, weekly secret-rotation
check, daily SLO review, dependency-audit). The framework's cron runner executes them and
feeds results into the scorecard grid. Two hard rules from ops practice:
- Heartbeat/dead-man's-switch: every scheduled job pings a monitor on success; missing pings
  alert (silent failure is the enemy). Idempotent jobs, central logs, no overlapping runs.
- Crawl-walk-run automation: start runbooks manual, graduate to semi-auto, then full-auto;
  treat manual runbook execution as toil to be engineered away (Google SRE toil budget).

### 4.6 "Always operate from the right place" (the meta-rule)

The dashboard exists so you never have to remember where to be. Pick the lens -> click start
session -> you are dropped into the correct scope with the correct CLAUDE.md chain and the
correct agent prompt. The catalog (tool.yaml per agent) + scoped launch + context hierarchy
together guarantee: right context, nothing extra, every time. That is what makes it both
all-bases-covered AND token-frugal.

--------------------------------------------------------------------------------
## 5. HOW THIS MAPS ONTO THE CURRENT SYSTEM (concrete next steps)

1. Create `templates/agent-tool/` with the exact 1.2 layout + 1.3/1.4 templates.
2. Convert the existing capabilities (chief, backup, usage, ideas, modules, ralph) into
   `agents/<name>/` directories following the template. Their current scripts move into the
   agent's `tools/`; their current docs become the agent CLAUDE.md + state/HANDOFF.md.
3. Add catalog discovery to server.py: scan `agents/*/tool.yaml`, render one lens each, wire
   the start-session button to `entrypoint` + `scope_dir` (reuse the existing PTY-launch path,
   just set cwd = the agent dir).
4. Add the scorecard roller: read every `tool.yaml: spec.scorecard`, run the checks (or read
   their last routine result), render the maturity grid as the dashboard home.
5. Add `cc.config.yaml` + a `cc init` / `cc add-agent` scaffolder; move all project-specific
   values (paths, fleet, integrations, secrets) into config + .env.
6. Ship the missing stock agent-tools (security, deploy, observability, incidents, docs,
   roadmap, onboarding, data, compliance) as templates under `agents-stock/`.
7. Keep root CLAUDE.md lean (index of pointers); put bulk in skills/findings; enforce the
   handoff discipline at session end.

--------------------------------------------------------------------------------
## SOURCES

Internal developer platforms / single pane of glass / catalogs / scorecards / scaffolding:
- Backstage System Model (entity model): https://backstage.io/docs/features/software-catalog/system-model
- Backstage Descriptor Format (catalog-info.yaml): https://backstage.io/docs/features/software-catalog/descriptor-format
- Backstage Software Templates / Scaffolder: https://backstage.io/docs/features/software-templates/
- Backstage TechDocs (docs-as-code, MkDocs): https://backstage.io/docs/features/techdocs/
- Backstage Plugins: https://backstage.io/docs/plugins/
- Backstage Getting Started (app-config.yaml; framework vs config): https://backstage.io/docs/getting-started/
- Spotify Golden Paths: https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem
- Port -- build your software catalog (blueprints/entities/relations): https://docs.port.io/build-your-software-catalog/
- Port -- Scorecards (rules + Bronze/Silver/Gold levels): https://docs.port.io/promote-scorecards/
- Cortex -- Scorecards (rules, levels, Define->Assess->Take Action, Initiatives): https://docs.cortex.io/standardize/scorecards
- Humanitec -- What is an Internal Developer Platform (platform vs portal; five planes): https://humanitec.com/blog/what-is-an-internal-developer-platform
  (Note: OpsLevel maturity-rubric docs could not be fetched directly; the pattern is corroborated by Cortex + Port.)

Claude Code context management / agents / token efficiency:
- How Claude Code Works (context window, delegation, compaction): https://code.claude.com/docs/en/how-claude-code-works.md
- Memory: CLAUDE.md + auto memory (hierarchy, on-demand loading, path-scoped rules): https://code.claude.com/docs/en/memory.md
- Subagents (frontmatter, tools, models, isolated context, persistent memory): https://code.claude.com/docs/en/sub-agents.md
- Skills (on-demand loading, disable-model-invocation, preload into subagents): https://code.claude.com/docs/en/skills.md
- Settings (scope hierarchy, permissions, hooks): https://code.claude.com/docs/en/settings.md
- Sessions (continue/resume, persistence): https://code.claude.com/docs/en/sessions.md
- Prompt Caching (cache lifetime + invalidation): https://code.claude.com/docs/en/prompt-caching.md
- Headless / programmatic (bare mode, structured output, CI): https://code.claude.com/docs/en/headless.md

Enterprise operating domains / platform engineering / AI productization / ops automation:
- NIST glossary -- security posture: https://csrc.nist.gov/glossary/term/security_posture
- AWS Well-Architected -- DR objectives (RTO/RPO): https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery-dr-objectives.html
- DORA -- continuous delivery + four keys: https://dora.dev/capabilities/continuous-delivery/ , https://dora.dev/guides/dora-metrics-four-keys/
- Google SRE -- SLOs: https://sre.google/sre-book/service-level-objectives/
- Google SRE -- Postmortem Culture (blameless): https://sre.google/sre-book/postmortem-culture/
- Google SRE -- Eliminating Toil: https://sre.google/sre-book/eliminating-toil/
- FinOps Foundation Framework: https://www.finops.org/framework/
- Diataxis (docs by user need): https://diataxis.fr/
- Fowler/Cochran -- Developer Effectiveness (DevEx / cognitive load): https://martinfowler.com/articles/developer-effectiveness.html
- ProductPlan -- Product Roadmap: https://www.productplan.com/glossary/product-roadmap/
- Google Cloud Architecture -- Reliability (data resilience): https://docs.cloud.google.com/architecture/framework/reliability
- AICPA SOC suite (SOC 2): https://www.aicpa-cima.com/resources/landing/system-and-organization-controls-soc-suite-of-services
- Team Topologies -- key concepts (team types, cognitive load, platform): https://teamtopologies.com/key-concepts
- Thoughtworks/Fowler -- platform as a product: https://martinfowler.com/articles/talk-about-platforms.html
- Platform Engineering -- what is platform engineering: https://platformengineering.org/blog/what-is-platform-engineering
- CNCF Platforms White Paper: https://tag-app-delivery.cncf.io/whitepapers/platforms/
- Anthropic -- built a multi-agent research system (orchestrator-worker; ~15x tokens): https://www.anthropic.com/engineering/built-multi-agent-research-system
- Anthropic -- building effective agents (workflows vs agents; building blocks): https://www.anthropic.com/engineering/building-effective-agents
- Anthropic -- writing tools for agents (consolidated, namespaced, high-signal tools): https://www.anthropic.com/engineering/writing-tools-for-agents
- LangGraph multi-agent (supervisor; handoffs as tool calls): https://docs.langchain.com/oss/python/langchain/multi-agent
- Twelve-Factor -- Config (III): https://12factor.net/config
- Twelve-Factor -- Dev/prod parity (X): https://12factor.net/dev-prod-parity
- Data-driven programming (engine + declarative logic): https://en.wikipedia.org/wiki/Data-driven_programming
- OWASP -- Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- HashiCorp Vault -- what is Vault: https://developer.hashicorp.com/vault/docs/what-is-vault
- PagerDuty -- what is a runbook + runbook automation: https://www.pagerduty.com/resources/learn/what-is-a-runbook/
- healthchecks.io docs -- dead-man's-switch / heartbeat: https://healthchecks.io/docs/
