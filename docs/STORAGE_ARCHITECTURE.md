# ClaudeFather storage architecture — one dedicated SSD per node

The enterprise-clean storage model for the fleet, the rationale, the doctor check that enforces it, and the
exact backup-first runbook to migrate an existing node onto it.

## The standard
**Each node gets its own dedicated APFS SSD, and that node's macOS user HOME lives on it.** Everything that
node produces — its project AND (for iCloud nodes) its iCloud container — lives in that home, i.e. on its
own SSD. Nothing of consequence sits on the Mac's small internal boot drive.

```
/Volumes/<node-ssd>/<user>/                         <- the node user's HOME, on its own SSD
  ├── <project>/                                     <- the project tree
  └── Library/Mobile Documents/com~apple~CloudDocs/  <- iCloud container (iCloud nodes) -> on the SSD, synced
```

### Why this is the right model
- **iCloud on the SSD, for real.** macOS iCloud syncs the container *inside the home*, on *whatever volume
  the home is on*. It is NOT a configurable path — so the only supported way to get iCloud onto an SSD is to
  put the **home** on the SSD. Then iCloud is on the SSD by definition (not a hack — the standard mechanism).
- **Capacity is per-node and additive.** Fill a node's SSD → add another and point new work at it. No shared
  "overflow" tangle, no one node starving another.
- **The internal drive stays empty.** The Mac's small boot drive (e.g. ~500 GB) never fills, because no
  node's data lives there.
- **Backup is built in.** For iCloud nodes the cloud copy IS off-site backup; add a second SSD / Time Machine
  per node for local redundancy. (Answers the "no backup plan when the internal fills" problem directly.)
- **Isolation.** One node's drive issue doesn't touch the others.

### Requirements (desktop pattern)
- The SSD must be **APFS** (check: `diskutil info /Volumes/<ssd> | grep Personality`).
- The SSD must be **always mounted at login** — fine for a Mac Studio with a fixed enclosure; do NOT use this
  for a node on a laptop. If a node's SSD is ever disconnected, only THAT node can't log in until reconnected
  (so always keep a separate admin account for recovery).
- Ownership must be **enforced** on the volume (NOT "ignore ownership") — a home dir requires real ownership.

## Fresh installs (the easy path)
Create the node's user with its home **already on the SSD** — then the project and iCloud just live there.
- GUI: System Settings → Users & Groups → add user → (or) Advanced Options → Home directory → the SSD path.
- Or at create time set `NFSHomeDirectory` to `/Volumes/<ssd>/<user>`.
Set `cc.config` `project_root` to a path inside that home. Done — internal drive stays clean.

## Doctor check
`/api/doctor` flags a node whose home (hence iCloud container) is on the **internal boot volume** instead of
its own SSD — so any node not following the standard surfaces itself. It compares the home's volume device to
the root volume device (`st_dev`); same device = on the internal drive.

## Runbook — relocate an EXISTING node's home onto its SSD (backup-first)
Run **on that node's Mac, from a SEPARATE admin account** (not the user being moved, who must be logged out).
This is real sysadmin with real downside if botched — **back up first.** The framework cannot do this
remotely; it is a macOS user/disk operation.

```sh
# 0. PREREQS
#    - Full Time Machine backup (and verify it).  A botched home move = broken login.
#    - SSD is APFS and permanently attached.  Confirm: diskutil info /Volumes/<ssd>
#    - Turn OFF "ignore ownership" on the SSD so the home keeps real ownership:
sudo diskutil enableOwnership /Volumes/<ssd>
#    - Log the target user OUT.  Do everything below from a different ADMIN account.

USER=<user>; SSD=/Volumes/<node-ssd>

# 1. Copy the home to the SSD, preserving perms/ACLs/xattrs (-E) — critical for ~/Library + iCloud:
sudo rsync -aE --delete /Users/$USER/ "$SSD/$USER/"

# 2. Fix ownership on the new home:
sudo chown -R $USER:staff "$SSD/$USER"

# 3. Point the account's home at the SSD:
sudo dscl . -change /Users/$USER NFSHomeDirectory /Users/$USER "$SSD/$USER"

# 4. REBOOT.  Then log in as $USER and verify:
echo $HOME            # -> /Volumes/<node-ssd>/<user>
df -h "$HOME"         # -> the SSD device, NOT the internal volume
#    Confirm iCloud re-indexes the container at the new location (sign-in stays; let it settle/redownload).
#    Confirm the ClaudeFather CC + project open normally and /api/doctor no longer flags storage.

# 5. ONLY after everything is verified over a day or two, reclaim the old space:
sudo rm -rf /Users/$USER.old   # (rename the old home to <user>.old in step 1 instead of --delete if cautious)
```

### Gotchas
- **iCloud re-index:** after the move, iCloud re-validates the container at the new path; files may show
  `.icloud` placeholders briefly and re-download. Stay signed in; let it settle before judging.
- **Ownership:** if you skip `enableOwnership` / `chown`, the home will have wrong perms and login/iCloud break.
- **Recovery:** if the SSD is missing at boot, the user can't log in — that's why you keep a separate admin
  account. Re-attach the SSD and reboot to recover.
- **Per-node, repeatable:** do this once per node (e.g. node-a, node-b, node-c), each onto its own SSD. After
  that, every node's project + iCloud lives on its dedicated drive and the internal disk stays empty.
