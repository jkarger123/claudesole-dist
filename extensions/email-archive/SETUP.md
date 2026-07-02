# Email Archive -- setup

Goal: an operator can instantly search a big exported email history (a Gmail Takeout `.mbox`) from the
**Email Archive** lens. Read-only; the archive + index stay on this node. ASCII only.

## What it does
Indexes an `.mbox` export into a node-local **SQLite FTS5** index (`command-center/email_archive.py`), then serves
an instant search lens (search box -> ranked results with highlighted snippets -> click to read the full message).
21k messages index in ~2 min and search in ~40ms.

## Steps (2 config values + one index build)
1. **Get the export onto this machine.** A Gmail **Takeout** of "Mail" yields a single big `.mbox` (e.g.
   `to-migrate.mbox`). Put it on fast local storage (an SSD), NOT an evictable cloud folder.
2. **Point the node at it** -- set in `cc.config.json` (or via the Vault/secure-field; superadmin `set_config`
   is allowlisted for these two keys):
   - `email_archive_mbox` = absolute path to the `.mbox` (REQUIRED).
   - `email_archive_db` = where to write the index (OPTIONAL; defaults to `<state_dir>/ext_stores/email-archive.sqlite`).
     For a large archive, put the DB on the SSD too.
3. **Build the index once** (a few minutes; safe to re-run -- it swaps atomically):
   ```
   python3 command-center/email_archive.py index "/path/to/to-migrate.mbox" "/path/to/email-archive.sqlite"
   ```
   (An agent can stage this into the Admin shell; it's a plain, non-sudo command.) Re-run it whenever the export
   is refreshed. `stats <db>` and `search <db> "<query>"` verify it.
4. **Open the Email Archive lens** and search. The lens self-reports "index not built yet" until step 3 completes.

## Notes
- **Read-only + private.** The lens never sends the archive anywhere; search + read happen entirely on the node.
- **Format:** standard mbox (Gmail Takeout). Bodies are indexed as plain text (HTML stripped; attachments skipped).
- **Portable / stdlib.** No pip deps (Python `mailbox` + `sqlite3` FTS5). Works on any install.
