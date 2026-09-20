"""The pool-results adapter, against a real championship document.

The fixture is FISav's 2024 World Assaut Championships - a layout with nothing
in common with the poule-grid one beyond the sport. It is here to hold three
things still: that the grid is read in the right columns, that the bracket is
resolved by who appears in the next round rather than by where a line is drawn,
and that a class code the adapter does not recognise fails loudly instead of
being filed under the previous class.
"""

import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import pdf, rules
from savate.adapters import fisav_pool_pdf
from savate.schema import check

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fisav-world-assaut-2024.pdf"
SLUG = "fisav-world-assaut-2024"


class ClassCodes(unittest.TestCase):
    def test_senior_and_junior_codes_are_both_understood(self):
        self.assertEqual(("Men", "Senior"),
                         (fisav_pool_pdf.weight_class("M56")["gender"],
                          fisav_pool_pdf.weight_class("M56")["age_class"]))
        self.assertEqual(("Women", "Junior"),
                         (fisav_pool_pdf.weight_class("JF52")["gender"],
                          fisav_pool_pdf.weight_class("JF52")["age_class"]))

    def test_the_over_sign_is_kept(self):
        heavy = fisav_pool_pdf.weight_class("M+85")
        self.assertEqual("over", heavy["weight_bound"])
        self.assertEqual("85", heavy["weight_kg"])

    def test_an_unknown_code_is_not_a_weight_class(self):
        """Silently accepting it would file a whole division under the last one."""
        for code in ("A1", "TOTAL", "X56", "POINTS", "2024", ""):
            self.assertIsNone(fisav_pool_pdf.weight_class(code), code)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class Extraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.bouts, cls.report = fisav_pool_pdf.read(
            FIXTURE, SLUG, {"year": "2024", "level": "world",
                            "discipline": "assaut"})

    def test_the_document_is_read_without_complaint(self):
        self.assertEqual([], self.report.problems)

    def test_every_bout_is_canonical(self):
        self.assertEqual([], [c for b in self.bouts for c in check(b)])

    def test_bout_ids_are_unique(self):
        ids = [b.bout_id for b in self.bouts]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_sixteen_weight_classes_reached_a_final(self):
        finals = [b for b in self.bouts if b.phase == "final"]
        self.assertEqual(16, len(finals))
        self.assertEqual(16, len({b.category for b in finals}))
        self.assertTrue(all(b.winner for b in finals))

    def test_the_poule_programme_is_present(self):
        phases = collections.Counter(b.phase for b in self.bouts)
        self.assertEqual(188, phases["poule"])
        self.assertGreater(phases["semi"], 0)

    def test_every_fighter_has_a_country(self):
        self.assertEqual([], [b.bout_id for b in self.bouts
                              if not (b.red_country and b.blue_country)])

    def test_a_fused_name_and_country_is_separated(self):
        """'DE ROBILLARDMAURITIUS' - one cell, two facts, four bracket boxes."""
        fighters = {b.red for b in self.bouts} | {b.blue for b in self.bouts}
        fused = [f for f in fighters if "MAURITIUS" in f.upper()]
        self.assertEqual([], fused, "a country is still stuck to a name")

    def test_this_events_disqualification_scale_is_recognised(self):
        """It scores a disqualification -3, where the 2026 worlds scores it -1.

        The warnings are what identify it, so the decision survives the change.
        """
        odd = [b for b in self.bouts
               if b.phase == "poule" and b.red_points and b.blue_points
               and min(int(b.red_points), int(b.blue_points)) < 0]
        self.assertTrue(odd, "the fixture should contain a disqualification")
        for b in odd:
            self.assertEqual("disqualification", b.decision, b.bout_id)

    def test_the_grid_agrees_with_the_ranking_ladder(self):
        """Poules read from this layout must rank without contradiction."""
        poules = collections.defaultdict(list)
        for b in self.bouts:
            if b.phase == "poule":
                poules[(b.category, b.poule)].append(b.as_dict())
        self.assertGreater(len(poules), 20)
        for key, bouts in poules.items():
            result = rules.standings(bouts)
            self.assertEqual(len(result.standings),
                             len({b["red"] for b in bouts} | {b["blue"] for b in bouts}),
                             key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
