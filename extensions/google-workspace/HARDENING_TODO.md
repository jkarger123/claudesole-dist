# google-workspace — hardening batch (from a field node brief, 2026-06-30, v0.99.94)

> Consolidated lessons from a live scope-upgrade + SSD relocation on a field node. Goal: the extension self-diagnoses
> and self-heals the four traps so no future install hits them. Ship as ONE batch in a calm window (deferred
> from the night of 2026-06-30 to a calm window; nothing here blocks the operator, whose only open step is clicking
> Enable on the Sheets/Docs/Forms Cloud APIs).

The four traps: (1) off-SSD frozen paths → split-brain token store; (2) OAuth scope granted but Cloud API
disabled → SERVICE_DISABLED 403; (3) diagnostics read the wrong token file / under-report; (4) unclear restart
semantics (bouncing the whole node needlessly).

## Item status
| # | Item | Status |
|---|---|---|
| 1 | Canonical portable token path + split-brain GUARD | self-heal SHIPPED (ccr-334, v0.99.94); **GUARD is new** |
| 2 | Cloud API enablement (SETUP.md + SERVICE_DISABLED detection) | **queued** (ccr-1782881362598) |
| 3 | Diagnostics print WHICH token file + account they read | **new** |
| 4 | Scope-upgrade runbook + enable-services.sh (URLs + re-mint) | script EXISTS (v2.2.1); **add Cloud URLs + runbook** |
| 5 | Clarify restart semantics (Path-B spawns MCP per launch) | **new — also corrects tonight's "restart the node" wording** |
| 6 | gauth.sh --remote SSH preflight (fail fast) | **new** |
| 7 | bin/doctor.sh single green/red end-to-end health check | **new — the capstone** |

## Build spec (turnkey)
**1 — split-brain GUARD (extends the shipped self-heal).** Beyond re-pointing on boot, add a boot + Doctor check
that ERRORS if the dashboard-resolved token file (`GOOGLE_TOKENS_DIR/<acct>.json`) and the MCP-configured
`WORKSPACE_MCP_CREDENTIALS_DIR` don't resolve to the SAME file. `_ext_wire_mcp` already substitutes `<DEPLOYMENT>`
(v0.99.94) — keep it never-frozen. Surface: server.py `_heal_google_mcp_paths` already computes both; add an
`os.path.realpath` equality assert → Doctor `err` when they differ post-heal.

**2 — Cloud API enablement (the queued CCR).** (a) SETUP.md "Cloud Console" step: enable Sheets, Docs, Forms
APIs too, with `https://console.developers.google.com/apis/api/{sheets,docs,forms}.googleapis.com/overview?project=<PROJECT#>`
(derive `<PROJECT#>` from the client_id, e.g. a 12-digit number like `123456789012`). (b) Parse a 403's `reason`:
`SERVICE_DISABLED` → print "ENABLE the API" + the exact URL; missing-scope → "RE-MINT". Do NOT conflate. Surfaces:
`verify.py`, Doctor, dashboard `google_status`. **Fix the mis-advice `verify.py` currently prints** (it says
"re-mint," which does NOT fix SERVICE_DISABLED).

**3 — diagnostics name their source.** `mint_token.py --check`, `verify.py`, `gauth.sh` all print the ABSOLUTE
path of the token file they read + the account, so a catalog-vs-deployment mixup is obvious (the false "send is
broken" came from `--check` reading the catalog drafts-only token while the live deployment token had send).

**4 — scope-upgrade runbook + enable-services.sh.** Confirmed `bin/enable-services.sh` exists (v2.2.1: patches
`.mcp.json` perms + re-mints). Add: it also PRINTS the per-service Cloud activation URLs (from the project number)
and the ordered runbook — (a) enable Cloud API, (b) re-mint w/ matching PERMS, (c) add service to `.mcp.json`
--permissions, (d) relaunch the agent. Any missing step = silent 403.

**5 — restart semantics (SETUP.md + tonight's wording).** The Path-B google agent spawns its stdio MCP FRESH per
launch, so it gains new tools on its NEXT launch — NO global node restart needed; only long-lived/attached
sessions do. Say this explicitly so operators don't bounce the whole node (which can kill the setup session
itself). Correct the "restart the node" phrasing I used in SETUP.md + the v0.99.90/.94 changelog notes.

**6 — gauth.sh --remote preflight.** Before minting, `ssh -o BatchMode=yes -o ConnectTimeout=5 <host> true`;
if it fails, exit with a clear "remote host <host> unreachable over SSH — fix the alias/IP (Tailscale?) before
minting; the callback tunnel can't deliver otherwise." (We burned time on a stale host alias / changed tailnet IP.)

**7 — bin/doctor.sh (capstone).** One command → a green/red table: token present + path (under CC_HOME?),
granted scopes, EACH service's Cloud API actually enabled (live probe per service; distinguish SERVICE_DISABLED),
`.mcp.json --permissions` vs granted scopes, dashboard-token-path == MCP-token-path. This one check would have
caught all of tonight's traps at once. (Optionally surface as a dashboard google-workspace health panel.)

## Filed CCRs (reference)
- ccr-1782880284334 — portable CC_HOME-relative secret paths + self-heal — **SHIPPED v0.99.94**
- ccr-1782880284369 — mint --check under-report + scope-vs-perms drift — **SHIPPED v0.99.94**
- ccr-1782881362598 — scope ≠ Cloud API enabled; SETUP.md + SERVICE_DISABLED detection — **queued (folds into item 2)**
