# Media Contact Sync — extension (in development)

Keeps ONE shared media-contact list current + clean, automatically. Affiliate managers each connect their OWN
Gmail (read-only) → harvest contacts from out-of-office replies + signatures → dedup against a shared Airtable
list → add-or-gap-fill, never duplicate, never overwrite. Daily + on-demand. Co-developed by the operator +
Mission Control; the requesting agency is the requirements owner. CCR filed from that node.

## Architecture (build order)
1. **`bin/contact_engine.py`** — THE ENGINE (built + tested): `extract_contacts(msg)` (OOO backups + signature) →
   `normalize_contact(c)` → `Dedup(master).decide(c)` → an ACTION. Pure stdlib, no I/O, fully testable.
   Merge policy is locked (see below). `bin/test_contacts.py` demonstrates it on the Bailey Valente scenario
   (1 skip / 1 flag+fill / 1 add) + signature extraction + a never-overwrite conflict.
2. **Gmail adapter** (TODO) — for each configured manager account, pull recent OOO/signature mail via the node's
   multi-account Google (`/api/google/gmail?account=<manager>&q=...`, v0.99.202) → feed the engine.
3. **Airtable writer** (TODO) — apply add/gap-fill via the airtable extension's MCP/PAT (base + table from config);
   flags → a review queue; full change log. Never overwrite (enforced in the engine; the writer only ADDs or
   sets BLANK fields).
4. **Job + setup** (TODO) — daily schedule + "run now"; per-install config (managers, base, sources); SETUP.md
   "connect a manager / add another account" flow (reuses google-workspace multi-account setup).

## Merge policy (operator-LOCKED — do not loosen without James)
- same **email** → same person: fill BLANK fields only; a differing non-blank field (title/phone) = CONFLICT → flag, never overwrite.
- same **name + publisher**, email missing/different → probably same: gap-fill BUT always FLAG for a human.
- otherwise → ADD (net-new).
- GOLDEN RULE: only ADD or FILL BLANKS. Worst case = a missed add (a human catches it), never a corrupted record.

## v1 vs v2
- **v1:** OOO + signatures → dedup/gap-fill into Airtable (seeded from the agency's affiliate media/contact
  spreadsheet, Publishers tab, ~1,292 rows) → daily + on-demand + full log.
- **v2:** human review queue UI, thread-participants source, weekly summary, Excel export view.

## Depends on
`google-workspace` (managers' read-only Gmail; multi-account) + `airtable` (the shared base; PAT in vault).
