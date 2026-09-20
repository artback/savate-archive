"""The analytical views, checked for the things a wrong view quietly gets right.

A broken analytical view does not raise; it returns a plausible number. So these
test the invariants that a miscounted join would break: that every bout is seen
from exactly two corners, that a decided bout produces exactly one win and one
loss, and that the derived time dimensions only exist where the source actually
published a time.
"""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB = Path(__file__).resolve().parent.parent / "savate.db"


class Views(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(DB)
        cls.db.row_factory = sqlite3.Row

    def one(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()[0]

    def test_every_bout_appears_from_both_corners(self):
        bouts = self.one("SELECT COUNT(*) FROM bouts")
        self.assertEqual(2 * bouts, self.one("SELECT COUNT(*) FROM appearances"))

    def test_a_decided_bout_has_exactly_one_winner_and_one_loser(self):
        odd = self.one("""
            SELECT COUNT(*) FROM (
                SELECT bout_id, SUM(outcome = 'win') w, SUM(outcome = 'loss') l
                FROM appearances GROUP BY bout_id
                HAVING (w + l) NOT IN (0, 2) OR (w + l = 2 AND (w <> 1 OR l <> 1)))
        """)
        self.assertEqual(0, odd)

    def test_an_unresolved_bout_produces_no_outcome(self):
        unresolved = self.one("SELECT COUNT(*) FROM bouts WHERE status='unresolved'")
        self.assertEqual(
            2 * unresolved,
            self.one("SELECT COUNT(*) FROM appearances WHERE outcome IS NULL"))

    def test_time_dimensions_exist_only_where_a_time_was_published(self):
        """A paper source has no clock, and must not acquire one here."""
        self.assertEqual(
            0, self.one("SELECT COUNT(*) FROM fighter_bouts "
                        "WHERE time = '' AND part_of_day IS NOT NULL"))
        self.assertEqual(
            0, self.one("SELECT COUNT(*) FROM fighter_bouts "
                        "WHERE time <> '' AND part_of_day IS NULL"))

    def test_rest_is_never_negative(self):
        self.assertEqual(0, self.one("SELECT COUNT(*) FROM fighter_bouts "
                                     "WHERE minutes_rested < 0"))

    def test_a_fighters_record_adds_up(self):
        bad = self.one("SELECT COUNT(*) FROM fighter_record "
                       "WHERE wins + losses <> bouts")
        self.assertEqual(0, bad)

    def test_head_to_head_is_symmetric(self):
        """If A met B three times, B met A three times."""
        mismatched = self.one("""
            SELECT COUNT(*) FROM head_to_head a
            JOIN head_to_head b ON a.fighter = b.opponent AND a.opponent = b.fighter
            WHERE a.meetings <> b.meetings OR a.wins <> b.meetings - b.wins
        """)
        self.assertEqual(0, mismatched)

    def test_every_final_yields_exactly_one_champion(self):
        finals = self.one("SELECT COUNT(*) FROM bouts "
                          "WHERE phase='final' AND status='decided'")
        self.assertEqual(finals, self.one("SELECT COUNT(*) FROM champions"))

    def test_coverage_counts_the_same_bouts_the_table_holds(self):
        self.assertEqual(self.one("SELECT COUNT(*) FROM bouts"),
                         self.one("SELECT SUM(bouts) FROM coverage"))

    def test_the_database_spans_more_than_one_tournament(self):
        """Career questions need it; a regression to one source would be silent."""
        self.assertGreater(self.one("SELECT COUNT(*) FROM tournaments"), 1)
        self.assertGreater(
            self.one("SELECT COUNT(*) FROM fighter_record WHERE tournaments > 1"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
