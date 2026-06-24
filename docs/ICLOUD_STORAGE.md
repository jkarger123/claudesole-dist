# iCloud tiered deliverables

For deployments with `storage_mode` containing `icloud`, agent **deliverables** (the "📁 Files made for you"
folder) get real iCloud sync **without** putting the bulk project on the internal disk.

## The macOS constraint (why it's tiered)
iCloud Drive syncs **only** `~/Library/Mobile Documents/com~apple~CloudDocs`, which lives on the **internal
boot volume**. It will **not** sync an external SSD path — it doesn't follow symlinks into one, and relocating
the container to an external drive is Apple-unsupported and corrupts sync. So a file is *either* physically on
the SSD *or* in iCloud — never both. The lifecycle below reconciles that with the "keep big things on the SSD"
rule:

| Tier | Where | Window | Behavior |
|---|---|---|---|
| **Hot** | iCloud container (internal) | recent, ≤ `deliverables_icloud_days` (default **90**) | synced to all Apple devices; "open" reveals it in iCloud |
| **Cold** | SSD archive (`<project>/.deliverables_archive/`) | older | off internal **and** off iCloud; still listed + openable from the Files panel |

## How it works
- Each module's `deliverables/` becomes a **symlink into the iCloud container**
  (`~/Library/Mobile Documents/.../CloudDocs/ClaudeFather/<deployment>/<module>/`). Agents keep writing to
  `deliverables/` exactly as before — the bytes transparently land in iCloud and sync.
- A lifecycle pass (`icloud_age_off`, runs on boot + on demand) moves files older than the retention window
  from the iCloud container to the SSD archive — freeing internal disk while keeping them accessible.
- The **Files panel** lists both tiers, tagged ☁ iCloud / 🗄 SSD, and **"open" reveals each at its real
  location** (iCloud for hot, SSD for cold) — `/api/reveal` resolves the symlink's real path.
- Disk-safe: iCloud "Optimize Mac Storage" also offloads hot files from the local disk when space is tight.

## Config
```json
{ "storage_mode": "icloud", "deliverables_icloud_days": 90 }
```

## Operations
- **Retroactively route existing deliverables into iCloud:** `POST /api/icloud-relink`
  (or superadmin action `relink_deliverables`).
- **Force an age-off pass now:** `POST /api/icloud-ageoff {"days": 90}` (or superadmin `ageoff_deliverables`).
- Requires the deployment's `storage_mode` to include `icloud` and the iCloud Drive folder to exist for the
  user the CC runs as. github-mode deployments are unaffected (plain git-backed `deliverables/`).
