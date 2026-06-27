# Granola Calls -- agent guide

This node has Granola Calls installed: meeting transcripts -> reviewed client updates. You have these tools.

## What you can do
- A user can DRAG a call onto your session -> you receive the full transcript as a message. Use it: pull
  out decisions, action items, owners, due dates, and client-facing notes.
- Read prior call context: each client's CLAUDE.md has a managed `<!-- CC:CALLS log -->` region (newest
  first). Treat it as read-only background; never hand-edit inside the markers.
- Surface what needs review: `GET /api/granola` returns `{ready, hint, proposals[], source}`. If
  `ready` is false, tell the user the `hint` (usually: add a Granola API key, or their workspace has
  end-to-end encryption ON which blocks the public API).

## The flow (propose -> approve -> apply -- never auto-write)
1. `POST /api/granola-sync` pulls recent calls + extracts (summary/notes/tasks/reminders/decisions) as
   PENDING proposals. Slow (headless claude per call); it returns immediately and fills in async.
2. The user reviews each in the Calls lens and Approves/Skips. Apply is the ONLY write path -- it appends
   the dated CC:CALLS note + creates tasks/reminders in the configured destinations.
3. Do NOT write to a client CLAUDE.md or create tasks yourself to "shortcut" this -- the review gate is the
   safety model. Propose; let the user approve.

## Notes
- Extraction uses the Max subscription (headless `claude -p`), not a metered API key.
- An unmatched call needs the user to pick a client before apply.
- If a sync errors with a 401/encryption message, it is a Granola account issue (key or workspace E2E),
  not a bug here -- relay the `hint`.
