# Erasure and data-subject requests — runbook

The site's notice promises: a data subject can consult, correct or erase their
data, and an erasure is honoured by replaying the archive, republished the same
day. This runbook is how that promise is kept.

## Where the data lives

| Artifact | Path | Status |
|---|---|---|
| Federation documents (originals) | `raw_sources/` | Provenance. Never edited. |
| Manifest | `tournaments.json` | Which documents feed the archive. |
| Derived data | `savate.db`, `savate.json`, `savate.csv`, `placings.csv` | Rebuilt, never hand-edited. |
| Published data | `ui/data.js` (+ `ui/` deployed) | What the world sees. |

An erasure request concerns what *we* publish. The pipeline makes that a
rebuild: nothing is patched in place.

## 1. Locate the person

Ask for (or search) the name as the site shows it — the site search or:

```
python3 - <<'EOF'
import sqlite3
db = sqlite3.connect("savate.db")
for name in db.execute("SELECT name FROM fighters WHERE name LIKE '%s%' ORDER BY name LIMIT 20", "NAME"):
    print(name[0])
EOF
```

Note the canonical spelling (the one with the most appearances) and, if the
request is scoped to one event, the event slug (visible on the event page URL).

## 2. Record the request

Create or edit `erasure.json` (repo root). It does not exist in the normal
state; its presence is the record that an erasure is in force.

```json
[
  {
    "fighter": "NANDI Chloe",
    "events": [],
    "reason": "Erasure request 2026-09-19 (data subject, verified)"
  }
]
```

- `fighter`: one spelling the site shows for the person. Every spelling that
  person was written under is dropped — the register knows the whole alias set.
- `events`: `[]` = every event. Or a list of event slugs to erase from only
  those events (the person keeps their other rows).
- `reason`: why, and when. An erasure without a recorded reason is a gap.

## 3. Rebuild and republish

```
python3 build_db.py        # prints every erasure applied and the rows dropped
python3 export_ui.py       # ui/data.js no longer contains the person
```

`build_db.py` refuses to build if the named person is not in the register, and
prints what it dropped:

```
erasure: ADAM Alexandre (ffsavate-...-2023-paris) - test reason
erasure: 4 bout(s) and 1 placing(s) dropped from the build
```

The person's bouts, placings and (for a full-scope request) their person card
all leave the export; poules that held them shrink accordingly, because poules
are derived from the surviving bouts.

Deploy `ui/` as usual (see `docs/deploy.md`).

## 4. Confirm

- `ui/data.js`: search the person's name and its aliases — none should remain.
- The deployed site: same.
- Reply to the requester: what was erased, from which events, when.

## What the erasure does NOT touch

- **`raw_sources/`** — the federation documents. They are the federations'
  publications, not ours; the archive's job is to say where every remaining
  row came from. If a request demands the underlying documents as well, that
  is a decision for counsel, and it weakens the provenance of the whole
  archive: record the decision in `erasure.json` and act on it explicitly.
- **Other people's rows in the same events** — a bout only names its two
  corners; erasing one corner erases that bout, never the opponent's record in
  other bouts.
- **The manifest** — the document stays a known source; only the rows are
  gone. Removing the manifest entry would delete the whole event, which is a
  different (heavier) decision.

## Correction requests

The same mechanism, lighter: there is no "rename" — a wrong row is fixed by
correcting the source-side record where it lives (an adapter repair, a
manifest `meta` fix, or an `identity` override in `overrides.json` for name
merging), then rebuild and republish. If the correction is "this never
happened", that is an erasure.