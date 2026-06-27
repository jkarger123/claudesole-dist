# Skimlinks Affiliate Intelligence (agent-tool)

I am the Skimlinks sync tool. I keep a tenant's full Skimlinks affiliate-merchant catalog mirrored into their
Supabase and track every change (new/removed merchants, commission moves, tenure).

## What's here
- `tools/skimlinks_sync.py` -- the weekly sync engine. Skimlinks v3 API (paginated) -> diff vs Supabase ->
  upsert `skimlinks_merchants` (soft-delete on disappearance) + append to `skimlinks_changes`. Config comes
  from the deployment env (`SKIMLINKS_CLIENT_ID`, `SKIMLINKS_SUPABASE_URL`, `SKIMLINKS_SUPABASE_KEY`,
  optional `SKIMLINKS_MIN_EXPECTED`). Flags: `--dry-run`, `--stats`, `--changes`, `--new`, `--removed`,
  `--quick` (first 1000, for testing).
- `tools/backfill_skimlinks_changes.py` -- recovery tool; rebuilds `skimlinks_changes` from snapshots if the
  change log is ever corrupted.

## How it runs
Normally via the platform **routine** "Skimlinks weekly sync" (Sundays 03:00, registered when the extension is
installed). It runs in this node's own server context (Full Disk Access) -- never a cross-user launchd. Manual:
`POST /api/routine-run {"name":"Skimlinks weekly sync"}` or run the script directly.

## Hard boundaries
- The sync WRITES to the tenant's Supabase -- only run a full pass on schedule or when explicitly asked.
- Secrets live in the gitignored deployment env, never here, never echoed. The Supabase service key is
  server-side only (the lens/agents read via the read-only `/api/ext-data` proxy).
- Removed merchants are soft-deleted (status=removed), never hard-deleted.
- The `--quick` flag bypasses the merchant-count safety guard -- use only for testing.
