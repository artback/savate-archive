"""The published site must be the database, not a memory of it.

ui/data.js is a generated artifact; between the last export and the next it
goes stale the moment the manifest changes. A site that shows 264 events while
the database holds 265 is not a bug, it is a lie the reader cannot see. So the
export is checked against the database it came from, and an old export is a
test failure, not a footnote.
"""

import json
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ui" / "data.js"
DB = ROOT / "savate.db"


def load_ui():
    raw = DATA.read_text(encoding="utf-8")
    prefix = "window.SAVATE="
    return json.loads(raw[len(prefix):raw.rindex("}") + 1])


class UiDrift(unittest.TestCase):
    def setUp(self):
        if not DATA.exists():
            self.skipTest("ui/data.js has not been exported yet")
        if not DB.exists():
            self.skipTest("savate.db has not been built yet")
        self.ui = load_ui()
        self.db = sqlite3.connect(DB)

    def tearDown(self):
        self.db.close()

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_the_export_holds_every_event_in_the_database(self):
        self.assertEqual(self.count("tournaments"), len(self.ui["events"]))

    def test_the_export_holds_every_bout_in_the_database(self):
        self.assertEqual(self.count("bouts"), len(self.ui["bouts"]))

    def test_the_export_holds_every_placing_in_the_database(self):
        self.assertEqual(self.count("placings"), len(self.ui["placings"]))

    def test_every_event_the_site_lists_exists_in_the_database(self):
        known = {r[0] for r in self.db.execute("SELECT slug FROM tournaments")}
        slugs = {e[8] for e in self.ui["events"]}
        self.assertEqual(known, slugs)

    def test_every_event_carries_the_document_it_was_read_from(self):
        """The per-event source link is the archive's proof. A row without it
        is a line the reader cannot check, so it is a defect, not a detail."""
        for e in self.ui["events"]:
            self.assertGreaterEqual(len(e), 13, e[0])
            self.assertTrue(str(e[12]).strip(), f"no source for {e[0]!r}")

    def test_every_person_in_the_database_has_a_row(self):
        """A person with no bout and no placing anywhere is a card that says
        nothing. Erasure and dedupe must leave no such ghost in the table the
        site is built from."""
        ghosts = self.db.execute("""
            SELECT f.id FROM fighters f
            WHERE NOT EXISTS (
                SELECT 1 FROM fighter_aliases a
                WHERE a.fighter_id = f.id
                  AND (a.alias IN (SELECT red FROM bouts)
                       OR a.alias IN (SELECT blue FROM bouts)
                       OR a.alias IN (SELECT fighter FROM placings)))
        """).fetchall()
        self.assertEqual([], [g[0] for g in ghosts])


if __name__ == "__main__":
    unittest.main()