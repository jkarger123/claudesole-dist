# Edge MCP Host -- setup

## What it does
Runs MCP servers that can only live on a specific user's own computer -- the machine where their GUI apps
(Adobe InDesign/Photoshop, Office), local files, or devices are -- and lets ClaudeFather agents drive them
over your Tailscale mesh, with no remote desktop. Every tool call is logged with timing (the transparency
proxy), so nothing is a black box.

## Why use it
Normal MCP integrations assume the server runs on the ClaudeFather node itself. But a whole class of useful
MCP servers only work where the user is -- e.g. "Sidekick for InDesign" driving Adobe InDesign via a UXP
plugin. This extension bridges that gap so the always-on control plane can use those local-only tools, and
shows exactly what they are doing (fixing the usual "slow + opaque" experience of desktop-app MCP servers).

## How it works
1. You register an **edge host** -- the user's machine (any account), reached over the tailnet by SSH.
2. You register an **edge MCP server** -- a launch command that runs on that host (e.g. a Node MCP server).
3. ClaudeFather runs that server on the host, tunneled over SSH and wrapped in a logging proxy, and exposes
   its tools to agent sessions. For stateful/GUI servers it keeps a persistent "warm" session so calls are
   fast and the app plugin stays connected.
Data path: agent/session <-> logging proxy (records every JSON-RPC frame + latency) <-> ssh edge-host <->
the MCP server <-> the user's app. If the host is also a ClaudeFather node, the server runs node-local instead.

## Prerequisites
- The user's machine on the same Tailscale tailnet as this node, with Remote Login (SSH) enabled.
- Whatever the target MCP server needs installed on that machine (e.g. Adobe InDesign 2024+ and the Sidekick
  plugin for the InDesign server; Node if the server is Node-based).
- You know which account on that machine the server should run under (host- and account-agnostic).

## Fast path -- drive a user's real logged-in browser (the common case)
One click or one command does the WHOLE thing (host + SSH key + Node + Chrome + server), no hand-assembly:
- **Dashboard:** Edge MCP lens -> **Connect a browser** -> enter a name + `user@tailnet-address` -> Set up.
- **CLI / agent:** `edge-mcp setup-browser <host-id> <user@tailnet-addr>` (e.g. `work-laptop user@100.x.y.z`).
It reuses an already-authorized SSH key if one exists (else prints a one-line snippet the user pastes), installs
Node if missing, checks Chrome, and registers the browser server. Then `edge-mcp start <server>` opens Chrome
(isolated debug profile) on the user's machine; the user logs in once and that becomes the session. Revoke any
time from the lens or `edge-mcp revoke <server>`. Only read on for the manual / non-browser (plugin-app) path.

## Windows browser hosts (e.g. an always-on shop build box)
A Windows machine works as a browser edge host too (proven on an always-on Win10 box). Two Windows facts the
`browser-attach` recipe already handles, so you rarely think about them -- but know them:
- **Visible on the user's real screen.** A command over Windows OpenSSH lands in Session 0 (a hidden desktop);
  a Chrome launched there would be invisible. The recipe instead launches Chrome via a **run-once scheduled
  task** created by the ssh user, so it opens on that user's **interactive desktop (Session 1)** -- the person
  at the machine actually sees the agent driving Chrome. **The user must be logged in** at the console (an
  always-on host set to auto-login is ideal).
- **Node >= 20.19 required** (chrome-devtools-mcp / playwright need it). Pre-launch checks this and fails LOUD
  with the actual version if it's too old. If you can't upgrade the system Node (no admin), drop a **portable
  Node** zip in a space-free dir and set the server's `config.node_dir` to it -- the recipe prepends it to PATH
  so both npx and the MCP package resolve to it. No admin needed.
Everything else is identical to a macOS host: durable per-profile logins under `%USERPROFILE%\.edge-mcp\profiles`,
idempotent start (a live port is never disturbed), same transparency proxy.

## Setup steps (manual / advanced -- plugin-app servers, custom launches)
On CLAUDEFATHER (one command does mint-key + vault-store + host-register + prints the user's snippet):
1. Enable SSH on the user's machine ONE time:
   - macOS: System Settings > General > Sharing > Remote Login = On (or `sudo systemsetup -setremotelogin on`).
   - Windows: the printed PowerShell snippet enables the OpenSSH server for you.
2. Register the host + authorize access WITHOUT sharing a password:
   `edge-mcp add-host <host-id> <user@tailnet-addr> --platform macos|windows --power laptop|always-on`
   This mints a dedicated SSH key straight into the VAULT (`vault:EDGE_SSH_KEY_<HOST>`), records the host, and
   prints ONE copy-paste block. (To reuse an already-authorized key, add `--import <privkey-path>`.)
3. On the USER'S machine: they paste that one block into Terminal (macOS) or PowerShell-as-admin (Windows).
   It authorizes ClaudeFather's public key and prints `AUTHORIZED as <user>@<host>`. Nothing runs unattended.
4. Register the MCP server to run there: `edge-mcp add-server <id> <host-id> -- <launch argv...>` (for Sidekick,
   the bundled definition auto-detects the installed `.mcpb` launch command).
5. Choose mode: `per-session` (spawn per session) or `warm` (keep a persistent handshaked session -- use for
   GUI-plugin servers like InDesign, which are slow to cold-start). Verify with `edge-mcp probe <id>`.

Credentials live ONLY in the vault; at call time the key is materialized to a 0600 temp file for `ssh -i`,
never written to a repo or printed.

## Verify
Run a read-only tool call from the Edge MCP lens (or an agent) and confirm it returns real state -- e.g. for
InDesign, the open document's name. A warm call should return in tens of milliseconds; the first (cold) call
takes a couple seconds while the server and app plugin handshake.

## Usage
- Drive the user's app from an agent (e.g. "in InDesign, add a text frame on page 2") through the edge server.
- Watch the live Activity feed in the Edge MCP lens -- every call, its arguments, result, and latency.
- Register additional edge hosts/servers as needed; each is an independent, transparent instance.

## Best practices / Safety
- The SSH key lives ONLY in the vault; never paste keys or passwords into chat. Use a dedicated least-privilege
  key per host. Registering a host is the user's explicit consent to let ClaudeFather drive their machine.
- Default to read-only actions first; the proxy audit-logs every call. Destructive or outward actions follow
  the platform's review gate.
- If the edge host is a laptop it will SLEEP (lid/idle/unplugged) -- calls then fail cleanly with "host asleep";
  ask the user to wake it. The manager auto-reconnects when it is back.
