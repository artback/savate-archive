"""Writing the canonical rows out: one CSV, one JSON, one SQLite database.

SQLite is the one that makes it a database rather than a pile of exports - it is
a single file, needs nothing installed, and answers the questions the whole
exercise is for ("every bout this fighter ever had", "which nation won what, by
year"). The CSV and JSON are the same rows for anything that would rather read a
file than a query.
"""

import csv
import json
import sqlite3

from savate.schema import BOUT_FIELDS, PLACING_FIELDS, TOURNAMENT_FIELDS

from savate.analytics import VIEWS

SCHEMA = f"""
CREATE TABLE tournaments ({", ".join(f"{f} TEXT" for f in TOURNAMENT_FIELDS)},
    PRIMARY KEY (slug));
CREATE TABLE bouts ({", ".join(f"{f} TEXT" for f in BOUT_FIELDS)},
    PRIMARY KEY (bout_id),
    FOREIGN KEY (tournament) REFERENCES tournaments(slug));
CREATE INDEX bouts_tournament ON bouts(tournament);
CREATE INDEX bouts_red ON bouts(red);
CREATE INDEX bouts_blue ON bouts(blue);
CREATE INDEX bouts_phase ON bouts(phase);

CREATE TABLE placings ({", ".join(f"{f} TEXT" for f in PLACING_FIELDS)},
    PRIMARY KEY (placing_id),
    FOREIGN KEY (tournament) REFERENCES tournaments(slug));
CREATE INDEX placings_tournament ON placings(tournament);
CREATE INDEX placings_fighter ON placings(fighter);

-- One row per person, and one per spelling that person has been written under.
CREATE TABLE fighters (id TEXT PRIMARY KEY, name TEXT, countries TEXT,
                       appearances INTEGER, spellings INTEGER);
CREATE TABLE fighter_aliases (alias TEXT PRIMARY KEY, fighter_id TEXT,
                              FOREIGN KEY (fighter_id) REFERENCES fighters(id));
CREATE INDEX fighter_aliases_id ON fighter_aliases(fighter_id);
""" + VIEWS


def write_placings_csv(path, placings):
    import csv as _csv

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=PLACING_FIELDS)
        writer.writeheader()
        writer.writerows(p.as_dict() for p in placings)


def write_csv(path, bouts):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BOUT_FIELDS)
        writer.writeheader()
        writer.writerows(b.as_dict() for b in bouts)


def write_json(path, tournaments, bouts):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"tournaments": [t.as_dict() for t in tournaments],
                   "bouts": [b.as_dict() for b in bouts]},
                  fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def write_db(path, tournaments, bouts, people=None, placings=None):
    """Rebuild the database from scratch.

    Rebuilding, rather than updating in place, is deliberate: the canonical rows
    are derived data and every source can be re-read, so there is nothing in
    here to lose and no half-migrated state to debug.
    """
    import os

    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        db.executemany(
            f"INSERT INTO tournaments VALUES ({','.join('?' * len(TOURNAMENT_FIELDS))})",
            [tuple(t.as_dict()[f] for f in TOURNAMENT_FIELDS) for t in tournaments])
        db.executemany(
            f"INSERT INTO bouts VALUES ({','.join('?' * len(BOUT_FIELDS))})",
            [tuple(b.as_dict()[f] for f in BOUT_FIELDS) for b in bouts])
        db.executemany(
            f"INSERT INTO placings VALUES ({','.join('?' * len(PLACING_FIELDS))})",
            [tuple(p.as_dict()[f] for f in PLACING_FIELDS) for p in placings or []])
        for person in people or []:
            db.execute("INSERT INTO fighters VALUES (?, ?, ?, ?, ?)",
                       (person["id"], person["name"],
                        ", ".join(person["countries"]),
                        person["appearances"], len(person["aliases"])))
            db.executemany("INSERT OR REPLACE INTO fighter_aliases VALUES (?, ?)",
                           [(alias, person["id"]) for alias in person["aliases"]])
        db.commit()
    finally:
        db.close()
