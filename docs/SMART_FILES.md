# Smart files -- user deliverables surfaced in the Projects lens

When an agent makes a file FOR the user (a report, an export, a generated doc), it goes in the working
module folder's `deliverables/` subdir, and ClaudeFather shows it in that module's **Files** panel (Projects
lens) -- right next to the folder's conversations. Deliverables become discoverable instead of lost on disk.

## How it works
- **Convention:** `<module>/deliverables/` holds user-facing files. Agents are told this in their launch
  brief (Chief of Staff + every agent-tool), so they save deliverables there automatically.
- **Display:** the Projects lens drill-in renders a "Files made for you in this folder" card per module,
  from `GET /api/module-files?rel=<module>` (scans the folder's `deliverables/`, newest first).
- **Two open actions per file:**
  - **Open** -> reveals it in Finder on the host (`POST /api/reveal`). With iCloud storage that location is
    synced to every Apple device -- ideal for an operator working on the host machine (e.g. the operator's Mac).
  - **Download** -> serves the file (`GET /api/file-get?path=`, PROJECT-scoped, path-traversal blocked).
    Works from anywhere (a phone over Tailscale) -- the universal fallback for mixed / non-iCloud users.
- **Storage:** the deliverables folder inherits the project's `storage_mode` -- iCloud-synced for
  pure-Apple, git-backed for mixed. No extra config.

## For agents (this is the contract)
Save any file you create FOR the user into the current module folder's `deliverables/` subdir (create it if
needed); name it clearly. It appears in that module's Files panel for the user to open or download. Do NOT
scatter user deliverables elsewhere in the tree.
