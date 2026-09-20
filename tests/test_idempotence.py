"""Reading a source twice must not change the archive.

Documents repeat themselves - the 2025 European sheets print every weight class
three times, once per language - and one championship is sometimes published as
two documents with different names. Both quietly triple a fighter's record and
hand out titles nobody won, and both are invisible in a spot check: the rows
look perfectly correct, there are simply too many of them.

So duplication is checked on content, in the built database, and the collapse
step is checked for being a fixed point.
"""

import collections
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_db
from savate.schema import Bout, Placing, Tournament

DB = Path(__file__).resolve().parent.parent / "savate.db"


class InTheDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(DB)
        cls.db.row_factory = sqlite3.Row

    def test_no_combat_is_recorded_twice(self):
        """One bout under two slugs is a duplicate; two meetings are not.

        The key stays deliberately blind to which document a bout came from -
        that is the whole point, since a duplicate arrives as a second slug.
        It is not blind to the date. France runs thirty divisional meets a
        season and the same pair does meet twice: Pochayan and Roussy fought
        the same Women -65 kg final at Rousies on 1 February 2025 and at
        Ruy-Montceau a fortnight later, both published by the FFSBF, both real.
        Events that state no date still collide on the empty string, so a
        championship published twice is caught exactly as before.
        """
        rows = self.db.execute("""
            SELECT t.year, t.level, t.start_date, b.category, b.phase, b.poule,
                   COALESCE(ra.fighter_id, b.red) AS a,
                   COALESCE(ba.fighter_id, b.blue) AS b
            FROM bouts b JOIN tournaments t ON t.slug = b.tournament
            LEFT JOIN fighter_aliases ra ON ra.alias = b.red
            LEFT JOIN fighter_aliases ba ON ba.alias = b.blue""").fetchall()
        seen = collections.Counter(
            (r["year"], r["level"], r["start_date"] or "", r["category"],
             r["phase"], r["poule"], frozenset((r["a"], r["b"])))
            for r in rows)
        repeats = {k: n for k, n in seen.items() if n > 1}
        self.assertEqual({}, repeats)

    def test_no_placing_is_recorded_twice_in_one_event(self):
        rows = self.db.execute("""
            SELECT p.tournament, p.category, p.rank,
                   COALESCE(a.fighter_id, p.fighter) AS who
            FROM placings p
            LEFT JOIN fighter_aliases a ON a.alias = p.fighter""").fetchall()
        seen = collections.Counter(
            (r["tournament"], r["category"], r["rank"], r["who"]) for r in rows)
        self.assertEqual({}, {k: n for k, n in seen.items() if n > 1})


class Collapse(unittest.TestCase):
    """deduplicate() must be a fixed point: running it again changes nothing."""

    def rows(self):
        t = [Tournament(slug="e1", year="2019", level="world", discipline="assaut"),
             Tournament(slug="e2", year="2019", level="world", discipline="assaut")]
        def bout(slug, red, blue):
            return Bout(tournament=slug, bout_id=slug + red + blue,
                        category="Senior Men -60 kg", phase="poule", poule="A",
                        red=red, blue=blue, winner_corner="red", winner=red,
                        loser=blue, status="decided", result_source="reported")
        def place(slug, who, rank):
            return Placing(tournament=slug, placing_id=slug + who + rank,
                           category="Senior Men -60 kg", weight_kg="60",
                           weight_bound="under", gender="Men", rank=rank,
                           medal={"1": "gold", "2": "silver", "3": "bronze"}[rank],
                           fighter=who, result_source="reported")
        bouts = [bout("e1", "A", "B"), bout("e1", "A", "B"),   # reprinted
                 bout("e2", "A", "B"),                          # published twice
                 bout("e1", "C", "D")]
        placings = [place("e1", n, r) for n, r in
                    [("A", "1"), ("B", "2"), ("C", "3"), ("D", "3")]] + \
                   [place("e2", n, r) for n, r in
                    [("A", "1"), ("B", "2"), ("C", "3"), ("D", "3")]]
        return bouts, placings, t

    def test_repeats_are_collapsed(self):
        bouts, placings, t = self.rows()
        kept, kept_p, notes = build_db.deduplicate(bouts, placings, t, {})
        self.assertEqual(2, len(kept), [b.bout_id for b in kept])
        self.assertEqual(4, len(kept_p), [p.placing_id for p in kept_p])
        self.assertTrue(notes)

    def test_running_it_again_changes_nothing(self):
        bouts, placings, t = self.rows()
        once, once_p, _ = build_db.deduplicate(bouts, placings, t, {})
        twice, twice_p, notes = build_db.deduplicate(list(once), list(once_p), t, {})
        self.assertEqual([b.bout_id for b in once], [b.bout_id for b in twice])
        self.assertEqual([p.placing_id for p in once_p],
                         [p.placing_id for p in twice_p])
        self.assertEqual([], notes, "a second pass found something to collapse")

    def test_two_unrelated_events_are_left_alone(self):
        """Low overlap is not evidence of a twin, and must not merge anything."""
        _, _, t = self.rows()
        def place(slug, who, rank):
            return Placing(tournament=slug, placing_id=slug + who,
                           category="c", weight_kg="60", weight_bound="under",
                           gender="Men", rank=rank, medal="gold",
                           fighter=who, result_source="reported")
        placings = [place("e1", n, "1") for n in "ABCDE"] + \
                   [place("e2", n, "1") for n in "AFGHI"]
        _, kept, _ = build_db.deduplicate([], placings, t, {})
        self.assertEqual(10, len(kept))


if __name__ == "__main__":
    unittest.main(verbosity=2)
