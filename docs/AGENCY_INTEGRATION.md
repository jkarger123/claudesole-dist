# ClaudeFather -- the Agency integration (a second shape, alongside Product)

ClaudeFather has two deployment SHAPES on the same generic engine:
- **Product** (text2tune, carsearch): one product organized into **Modules** (its parts). The Projects lens
  + the module map serve this.
- **Agency** (Karger & Co / AFP): a services business organized into **Clients, Partners, Pipeline, and a
  reusable Tool library applied across them**. This doc defines that shape.

The agency shape is **convention + config driven over the SAME folder/CLAUDE.md substrate** -- no per-agency
code. It was modeled directly from Sarah's AFP tree so it fits how she already works, and generalized.

## The taxonomy (top-level workspaces)
Detected from top-level folders named per `cc.config.agency` (defaults shown; rename per deployment):
| Concept   | Default dir | What it is |
|-----------|-------------|------------|
| Clients   | `Clients`   | Active engagements. Each client = a folder of tool-applications + artifacts. |
| Partners  | `Partners`  | Agencies you work UNDER; each has its own nested `clients/` (+ `_shared`). |
| Pipeline  | `Pipeline`  | Prospects/deals not yet clients (each has a stage). |
| Tools     | `Tools`     | The reusable engines (`/invoice`, `/press-release`, `/skimlinks-audit`, ...). |
Anything else top-level (her `AfP`, `Internal`, `Routines`) stays a normal module / existing lens.

## The data model (interpreted from the tree)
- **Tool** = a folder under `Tools/` (has an `engine/`). The agency's reusable capabilities.
- **Client** = a folder under `Clients/` (or under `Partners/<p>/clients/`). It contains:
  - **tool-applications** -- subfolders whose name matches a Tool id (e.g. `Clients/7th-avenue/invoice`
    -> uses the `invoice` tool), and/or whose CLAUDE.md says "Applies the <X> tool". This is the
    **client -> tool link**.
  - **artifacts** -- the other subfolders (Press Releases, Call Transcripts, Renderings, pitches).
- **Partner** = a folder under `Partners/` with its own `clients/`.
- **Pipeline item** = a folder under `Pipeline/` (stage from a `stage:`/`status:` marker or its summary).
- **Reverse index** -- each Tool lists the clients that apply it (so "who uses /skimlinks-audit?" is answerable).

## How a client "applies a tool" (the link)
Primary signal: the application subfolder's NAME matches a Tool id (robust; matches her tree exactly).
Secondary: the subfolder CLAUDE.md prose "Applies the <X> tool" or a structured marker
`<!-- CC:USES tool=<id> -->` / frontmatter `tool: <id>` (clean path for new agencies).

## Surfaces (the Agency lens)
A single **Agency** lens (shown when the deployment is agency-shaped) renders the model in sections:
- **Clients** -- card per client: status, the tools it uses (chips), artifact count, last activity; drill-in
  launches a session in that client folder.
- **Partners** -- partner -> its clients.
- **Pipeline** -- prospects grouped by stage.
- **Tools** -- each tool + its `used_by` client list (the reverse index) + launch.
Existing lenses (Sessions, Routines, Marketplace, Agents, Skills, Backup, Security, Chief, Docs) stay.

## Config / detection
- `cc.config.json`: `"integration": "agency"` turns on the Agency lens; `"agency": {clients, partners,
  pipeline, tools}` overrides the dir names. 
- Auto-detect: if `integration` is unset but the project root has both a `Tools/` and a `Clients/` dir,
  ClaudeFather treats it as an agency (offers the Agency lens). Product deployments are unaffected.
- A new `agency` preset bundles the agency-appropriate lens set.

## Why this is the right design
- **Zero per-agency code** -- it interprets folders + CLAUDE.md (the same substrate as Product), so an
  agency just structures its tree (Clients/Partners/Pipeline/Tools) and gets the lens. Sarah's tree already
  matches, so she gets it on her next `cc-update` with no restructuring.
- **The relationships are first-class** without a database -- tool<->client links + reverse index come from
  the folder structure, so they can't drift from reality.
- **Both shapes coexist** -- the engine, extensions, mesh, agents, routines, backup, etc. are shared;
  Product vs Agency is just which taxonomy lens is on.
