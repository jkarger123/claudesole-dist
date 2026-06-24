# Module map -- the whole-tree view in every CLAUDE.md

ClaudeFather auto-maintains a compact map of the WHOLE module tree (every folder with a CLAUDE.md) and
stamps it into the PROJECT root CLAUDE.md as a `CC:TREEMAP` region. Because a Claude Code session at ANY
depth auto-loads the root CLAUDE.md (context flows downward), every level inherits a complete "what exists +
where" view -- the lowest-level agent always knows the full hierarchy, without duplicating the map into
every file.

## Why this design (not a copy in every node)
Down-flow already delivers the root to every level, so we anchor ONE authoritative map at the root instead
of stamping it into all CLAUDE.mds (which would bloat tokens + be a maintenance nightmare). Each module
still keeps its own `CC:CHILDREN` index of DIRECT children; `CC:TREEMAP` is the full recursive picture.

## Self-maintaining (can't drift)
- Source of truth is the live filesystem; each module's first `#` heading is its one-line summary.
- Regenerated automatically when: a module is added / removed / combined (dashboard or `/api/module-*`),
  the Projects lens is viewed (debounced -- catches modules an agent added directly on disk), and on boot.
- One compact line per module, indented by depth, summary truncated, bounded (~160 lines).

## Adding a tool/project -> it self-adds to the CLAUDE.md
However you add it -- the Projects lens "+ add sub-tool", `/api/module-add`, or an agent/person just creating
a folder with a CLAUDE.md -- it appears in the map automatically (immediately for dashboard ops; on the next
Projects-lens view or boot for raw filesystem adds). Removing/combining updates it the same way.

## Pairs with the root slim-down
As the hand-written root CLAUDE.md is trimmed, this auto-map becomes the lean, always-current orientation
index -- zero hand maintenance.
