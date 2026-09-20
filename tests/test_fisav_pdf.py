"""The FISav PDF adapter, against a real championship document.

The fixture is the federation's own 2025 World Youth Championship results, 15
pages of poule grids and brackets. It earns its place in the repository twice
over: it proves the grid is read correctly, and - because every page prints its
own standings - it independently checks the ranking ladder in savate.rules
against a competition that ladder was not derived from.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import normalize as norm
from savate import pdf, rules
from savate.adapters import fisav_pdf
from savate.schema import Report, check

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fisav-world-youth-2025.pdf"
SLUG = "fisav-world-youth-2025"


def key(name):
    return norm.fold(name).replace(" ", "")


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class Extraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.bouts, cls.report = fisav_pdf.read(
            FIXTURE, SLUG, {"year": "2025", "level": "world",
                            "discipline": "assaut"})

    def test_the_document_is_read_without_complaint(self):
        self.assertEqual([], self.report.problems)
        self.assertEqual(15, self.report.notes["weight_classes"])

    def test_every_bout_is_canonical(self):
        complaints = [c for b in self.bouts for c in check(b)]
        self.assertEqual([], complaints)

    def test_the_whole_programme_is_present(self):
        phases = {}
        for b in self.bouts:
            phases[b.phase] = phases.get(b.phase, 0) + 1
        self.assertEqual(131, phases["poule"])
        self.assertEqual(15, phases["final"], "one final per weight class")
        self.assertEqual(14, phases["semi"])

    def test_every_fighter_has_a_country(self):
        missing = [b.bout_id for b in self.bouts
                   if not (b.red_country and b.blue_country)]
        self.assertEqual([], missing)

    def test_youth_categories_still_yield_a_sex_and_an_age_class(self):
        """'Young Boys' is a category label, not a gender the parser can skip."""
        self.assertEqual({"Men", "Women"}, {b.gender for b in self.bouts})
        self.assertEqual({"Young"}, {b.age_class for b in self.bouts})

    def test_scorelines_are_ones_the_sport_produces(self):
        for b in self.bouts:
            if b.phase != "poule" or not b.winner_corner:
                continue
            won = int(b.red_points if b.winner_corner == "red" else b.blue_points)
            lost = int(b.blue_points if b.winner_corner == "red" else b.red_points)
            self.assertEqual((won, lost), rules.bout_points(b.decision),
                             f"{b.bout_id}: {b.red} vs {b.blue}")


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class AgainstThePrintedStandings(unittest.TestCase):
    """The ladder, checked on a championship it was not derived from."""

    @classmethod
    def setUpClass(cls):
        report = Report()
        cls.poules = []
        for number, words in sorted(pdf.by_page(pdf.words(FIXTURE)).items()):
            page = fisav_pdf.Page(words, report)
            if not page.category:
                continue
            for label, top, bottom in page.poule_regions():
                block = page.poule(label, top, bottom)
                if block:
                    cls.poules.append((page.category, block))
        cls.report = report

    def _bouts_of(self, block):
        out = []
        for p in block["pairings"]:
            corner = "red" if p["red_points"] > p["blue_points"] else "blue"
            won = max(p["red_points"], p["blue_points"])
            lost = min(p["red_points"], p["blue_points"])
            out.append({"red": key(p["red"]), "blue": key(p["blue"]),
                        "winner_corner": corner,
                        "decision": rules.decision_from_points(won, lost),
                        "red_warnings": str(p["red_warnings"]),
                        "blue_warnings": str(p["blue_warnings"])})
        return out

    def test_there_are_poules_to_check(self):
        self.assertEqual(22, len(self.poules))

    def test_the_ladder_reproduces_every_printed_classement(self):
        wrong = []
        for category, block in self.poules:
            weights = {key(n): s["weight"] for n, s in block["standings"].items()}
            result = rules.standings(self._bouts_of(block), weights=weights)
            printed = [key(n) for n in block["standings"]]
            if result.ranked != printed:
                wrong.append((category, block["label"], result.ranked, printed))
        self.assertEqual([], wrong)

    def test_the_printed_totals_match_the_grid(self):
        """The standings panel is an independent copy of the same numbers."""
        for category, block in self.poules:
            result = rules.standings(self._bouts_of(block))
            computed = {s.name: s for s in result.standings}
            for name, printed in block["standings"].items():
                mine = computed[key(name)]
                self.assertEqual(printed["points"], mine.points,
                                 f"{category} {block['label']} {name} points")
                self.assertEqual(printed["warnings"], mine.warnings,
                                 f"{category} {block['label']} {name} warnings")
                self.assertEqual(printed["wins"], mine.wins,
                                 f"{category} {block['label']} {name} wins")


if __name__ == "__main__":
    unittest.main(verbosity=2)
