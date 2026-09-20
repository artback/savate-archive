"""Fighter identity: what may be merged, and what must not be.

The dangerous failure here is a false merge. A split record is visibly
incomplete; a merged one looks authoritative and is wrong, and inventing a
career out of two siblings is worse than reporting two short ones. So most of
these tests assert that things stay apart.
"""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import identity

DB = Path(__file__).resolve().parent.parent / "savate.db"


class Keys(unittest.TestCase):
    def test_case_accents_punctuation_and_order_do_not_make_a_new_person(self):
        same = ["Bartol Pavičić", "PAVICIC Bartol", "bartol pavicic",
                "Pavičić, Bartol", "BARTOL  PAVIČIĆ"]
        self.assertEqual(1, len({identity.key(n) for n in same}), same)

    def test_hyphens_and_spaces_are_the_same_separator(self):
        self.assertEqual(identity.key("CAVROT-WESTERLINCK Ethan"),
                         identity.key("CAVROT WESTERLINCK Ethan"))

    def test_siblings_stay_apart(self):
        """The real pair that fuzzy matching would merge."""
        self.assertNotEqual(identity.key("CAVROT-WESTERLINCK Ethan"),
                            identity.key("CAVROT WESTERLINCK Noha"))

    def test_a_shared_surname_is_not_a_shared_person(self):
        for a, b in [("Farzam Fallah", "MohammadHossein Fallah"),
                     ("Mahdi Dareini", "Sajjad Dareini"),
                     ("Kerem ÖZKAN", "KEREM ALTAY")]:
            self.assertNotEqual(identity.key(a), identity.key(b), (a, b))

    def test_a_dropped_middle_name_is_not_merged_on_its_own(self):
        """It may well be one person - but that is a decision, not a guess."""
        self.assertNotEqual(identity.key("Mohamed Sidiki GUISSE"),
                            identity.key("Mohamed GUISSE"))

    def test_particles_are_kept_in_the_key(self):
        self.assertNotEqual(identity.key("DE SOUSA Jean"),
                            identity.key("SOUSA Jean"))


class RegisterBehaviour(unittest.TestCase):
    def test_the_commonest_spelling_becomes_the_display_name(self):
        register = identity.Register()
        register.add("NIHAT GULIYEV", "Azerbaijan", count=2)
        register.add("Nihat GULIYEV", "Azerbaijan", count=9)
        people = register.fighters()
        self.assertEqual(1, len(people))
        self.assertEqual("Nihat GULIYEV", people[0]["name"])
        self.assertEqual(11, people[0]["appearances"])

    def test_a_confirmed_link_merges_names_the_key_cannot(self):
        register = identity.Register(
            {"same": [["Mohamed Sidiki GUISSE", "Mohamed GUISSE"]],
             "different": []})
        register.add("Mohamed Sidiki GUISSE", "Guinea Conakry")
        register.add("Mohamed GUISSE", "Guinea Conakry")
        self.assertEqual(1, len(register.fighters()))

    def test_two_people_with_one_name_can_be_forced_apart(self):
        register = identity.Register(
            {"same": [], "different": [["Jean Dupont", "Jean Dupont"]]})
        register.add("Jean Dupont", "France")
        register.add("jean dupont", "Belgium")
        self.assertEqual(2, len(register.fighters()))

    def test_candidates_suggest_but_the_register_does_not_act(self):
        register = identity.Register()
        register.add("CAVROT-WESTERLINCK Ethan", "France")
        register.add("CAVROT WESTERLINCK Noha", "France")
        self.assertEqual(2, len(register.fighters()))
        pairs = identity.candidates(register)
        self.assertEqual(1, len(pairs))
        self.assertEqual("review", pairs[0]["confidence"])


class InTheDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(DB)
        cls.db.row_factory = sqlite3.Row

    def test_every_spelling_resolves_to_exactly_one_fighter(self):
        orphans = self.db.execute("""
            SELECT COUNT(*) FROM raw_appearances
            WHERE fighter NOT IN (SELECT alias FROM fighter_aliases)
        """).fetchone()[0]
        self.assertEqual(0, orphans)

    def test_a_career_spans_the_spellings_it_was_written_under(self):
        row = self.db.execute(
            "SELECT * FROM fighter_record WHERE fighter_id = 'guliyev nihat'"
        ).fetchone()
        self.assertIsNotNone(row, "the known two-spelling fighter is missing")
        self.assertEqual(2, row["spellings"])
        # The point is that the two spellings resolve to one career that spans
        # more than one competition - not how many the archive holds today.
        # Pinning the exact count makes every new source a test failure.
        self.assertGreaterEqual(row["tournaments"], 2)

    def test_no_fighter_id_is_used_by_two_people(self):
        dupes = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT id FROM fighters GROUP BY id "
            "HAVING COUNT(*) > 1)").fetchone()[0]
        self.assertEqual(0, dupes)

    def test_merging_reduced_the_fighter_count(self):
        """Against every spelling anywhere - a podium name need never fight.

        Comparing only against the bouts table understates the register badly
        once placings are loaded: most of the archive's people appear on a
        podium and in no bout at all.
        """
        people = self.db.execute("SELECT COUNT(*) FROM fighters").fetchone()[0]
        spellings = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT fighter FROM raw_appearances "
            "UNION SELECT fighter FROM placings)").fetchone()[0]
        self.assertLess(people, spellings)
        self.assertGreater(spellings - people, 100)

    def test_a_podium_only_fighter_still_has_an_identity(self):
        """Most of the archive is people who appear on a podium and nowhere else."""
        orphans = self.db.execute(
            "SELECT COUNT(*) FROM placings "
            "WHERE fighter NOT IN (SELECT alias FROM fighter_aliases)"
        ).fetchone()[0]
        self.assertEqual(0, orphans)


if __name__ == "__main__":
    unittest.main(verbosity=2)
