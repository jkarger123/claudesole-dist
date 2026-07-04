# Key rotation + history scrub -- checklist

These three secrets were committed to git history and are still LIVE. Removing them from history does
NOT un-leak them -- anyone who pulled the repo has the values. **Rotation (revoking the old key at the
provider) is the real fix; the history scrub is cleanup AFTER.** Order matters:

> **ROTATE every key first -> verify live product still works -> THEN scrub history -> force-push.**

Status is tracked in `rotation_ledger.json` (the Security lens reads it; it stays RED until each entry's
`revoked` is `true`). After you complete a key, set its `revoked: true` + `rotated_date` (or tell me and
I'll update it) and re-run the scan.

Deploy/restart references (from CLAUDE.md):
- Restart the live bridge: `TMUX_TMPDIR=/tmp /opt/homebrew/bin/tmux kill-session -t <bridge-session>` (auto-recreates ~5s).
- Worker deploy: `cd <worker-dir> && export $(grep -E '^CLOUDFLARE_' ../.env | xargs) && npx wrangler@4 deploy`.

---

## 1. Anthropic API key  (ANTHROPIC_API_KEY)
The live bridge uses this to run the customer agent. Rotating it briefly affects ONLY new agent calls.

1. **Create new key:** console.anthropic.com -> Settings -> API Keys -> Create Key (name it, e.g.,
   `runtime-2026-06`). Copy it once.
2. **Update the live runtime:** edit `<runtime root>/.env`, set
   `ANTHROPIC_API_KEY=<new>`. (Do NOT put it anywhere that gets committed.)
3. **Restart the bridge:** `tmux kill-session -t <bridge-session>` (above), then `tail -20 .../bridge.log`.
4. **Verify:** run one real tuning request through the site (or watch a job process cleanly in the log).
5. **Revoke the old key:** back in the Anthropic console, delete/disable the OLD key.
6. **Confirm dead:** an API call with the old key must return HTTP 401. (I can verify with trufflehog
   `--only-verified` once it's revoked -- it should stop reporting it as live.)
7. Set `anthropic-api-key.revoked = true` in the ledger.

## 2. Bridge secret  (BRIDGE_SECRET)
Self-generated shared secret between the Mac bridge and the Cloudflare Worker. BOTH sides must match,
so update them close together to avoid an auth gap.

1. **Generate a new secret:** `openssl rand -hex 32` (copy it).
2. **Set it on the Worker:** `cd <worker-dir> && npx wrangler@4 secret put BRIDGE_SECRET`
   (paste the new value when prompted).
3. **Set it in the runtime:** edit `<runtime root>/.env`,
   `BRIDGE_SECRET=<new>`.
4. **Restart the bridge** (above). The old value is now useless the moment both sides use the new one.
5. **Verify:** confirm the bridge claims/processes a job (bridge.log) and the site round-trips a message.
6. Set `bridge-secret.revoked = true`.

## 3. Cloudflare API token  (CLOUDFLARE_API_TOKEN)
Used by wrangler for Worker deploys + R2 (frontend deploy).

1. **Roll/create:** dash.cloudflare.com -> My Profile -> API Tokens -> either Roll the existing token or
   Create a new one with the same scopes (Workers Scripts: Edit, R2: Edit, Account: Read as needed).
2. **Update `.env`:** set `CLOUDFLARE_API_TOKEN=<new>` in the `.env` your deploys read
   (`<project root>/.env` and/or `<worker-dir>/.env`).
3. **Verify:** `export $(grep -E '^CLOUDFLARE_' .env | xargs) && npx wrangler@4 whoami` (should show the
   account); optionally a no-op `wrangler deploy` dry run.
4. **Delete the old token** in the dashboard.
5. Set `cloudflare-api-token.revoked = true`.

---

## 4. AFTER all three are rotated -- scrub history (cleanup)
Only now is this worth doing (the values are already worthless once revoked). It rewrites every commit
SHA, so it is gated behind human approval and requires collaborators to re-clone.

1. **Dry-run find:** `<CC_HOME>/bin/gitleaks git <project root> --redact` to
   list what history still contains (fingerprints).
2. **Scrub:** `git filter-repo --replace-text <(printf '%s==>REDACTED\n' "<old-value>")` for each old
   value (or use BFG). `brew`/standalone `git-filter-repo` required.
3. **Force-push** (DESTRUCTIVE, rewrites remote history): coordinate first; then
   `git push --force` (note: the deny-list blocks force-push -- temporarily allow it for this one step).
4. **Re-clone** anywhere the repo is mirrored (the source-of-truth dev box, etc.).
5. Re-run `gitleaks git .` -> 0 findings for those fingerprints.

> The Security agent NEVER force-pushes or scrubs autonomously -- this section is a human-run procedure.
