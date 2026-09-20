"""The Italian federation's classification sheets, against all four of them.

Four fixtures, three generators, one adapter. They are in the repository
because the Italian documents are the archive's only source of Italian results
and because each of them carries a different way of going wrong:

  federkombat-assoluti-2021  two competitors the document refused to classify
  federkombat-assoluti-2022  fourteen titles decided without a bout
  fikbms-assoluti-2018       a club medal table with a result's exact shape,
                             and names whose spaces are written as underscores
  lpmanager-italiani-2019    licence numbers inside the name cell
  ...-2019-reprint           the same spreadsheet through a second printer,
                             which is how one competition becomes two if the
                             archive is not told they are one document

What is asserted here is what a wrong read would produce: a place nobody was
given, a club in the fighter column, two golds in one class, men under a
women's heading, a category that swallowed two competitions, or a fact - a
country, a licence, an apostrophe - that no document states.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import pdf
from savate.adapters import federkombat
from savate.schema import check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOCS = {
    "2021": FIXTURES / "federkombat-assoluti-2021.pdf",
    "2022": FIXTURES / "federkombat-assoluti-2022.pdf",
    "2018": FIXTURES / "fikbms-assoluti-2018.pdf",
    "2019": FIXTURES / "lpmanager-italiani-2019.pdf",
    "2019r": FIXTURES / "lpmanager-italiani-2019-reprint.pdf",
}
# Counted by hand off the printed tables, not taken from the adapter.
ROWS = {"2021": 119, "2022": 96, "2018": 105, "2019": 80, "2019r": 80}
CATEGORIES = {"2021": 42, "2022": 41, "2018": 51, "2019": 31, "2019r": 31}


def read(key, meta=None, **options):
    return federkombat.read(DOCS[key], f"it-{key}", meta or {}, **options)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class EveryDocument(unittest.TestCase):
    """What must hold of all four sheets, whichever system printed them."""

    @classmethod
    def setUpClass(cls):
        cls.read = {k: read(k) for k in DOCS}

    def test_each_document_yields_the_rows_it_prints(self):
        for key, (_t, rows, _r) in self.read.items():
            with self.subTest(key):
                self.assertEqual(ROWS[key], len(rows))
                self.assertEqual(CATEGORIES[key],
                                 len({p.category for p in rows}))

    def test_every_placing_is_canonical(self):
        for key, (_t, rows, _r) in self.read.items():
            with self.subTest(key):
                self.assertEqual([], [c for p in rows for c in check_placing(p)])

    def test_no_class_awards_two_golds(self):
        """The failure that catches a category key which merged two
        competitions - the whole reason the style and the serie stay in it."""
        for key, (_t, rows, _r) in self.read.items():
            with self.subTest(key):
                golds = [p.category for p in rows if p.rank == "1"]
                self.assertEqual(sorted(set(golds)), sorted(golds))

    def test_no_class_holds_both_genders(self):
        """Men filed under a women's heading is the mis-segmentation that
        looks most like a clean parse."""
        for key, (_t, rows, _r) in self.read.items():
            by_category = {}
            for p in rows:
                by_category.setdefault(p.category, set()).add(p.gender)
            with self.subTest(key):
                self.assertEqual([], [c for c, g in by_category.items()
                                      if len(g) != 1])

    def test_the_label_agrees_with_the_fields_it_was_built_from(self):
        for key, (_t, rows, _r) in self.read.items():
            for p in rows:
                with self.subTest(key, category=p.category):
                    sex = " F " if p.gender == "Women" else " M "
                    self.assertIn(sex, p.category)
                    sign = "+" if p.weight_bound == "over" else "-"
                    self.assertTrue(
                        p.category.endswith(f"{sign}{p.weight_kg} kg"))

    def test_no_row_claims_a_country_the_document_never_states(self):
        """These sheets print an Italian region, which is not a nation. The
        region is reported instead; the field stays empty."""
        for key, (_t, rows, report) in self.read.items():
            with self.subTest(key):
                self.assertEqual({""}, {p.country for p in rows})
                self.assertTrue(report.notes["club_regions"])

    def test_every_row_says_where_its_result_came_from(self):
        for key, (_t, rows, _r) in self.read.items():
            with self.subTest(key):
                self.assertEqual({"reported"}, {p.result_source for p in rows})

    def test_a_savate_club_is_not_read_as_another_sport(self):
        """Eighteen medals in these files are won by the Ecole De Savate Et
        Ranzo-do Chausson De Rue. "chausson" in a club name is not the sport,
        and a filter that cannot tell the two apart empties the archive."""
        for key, (_t, rows, _r) in self.read.items():
            with self.subTest(key):
                self.assertTrue([p for p in rows if "hausson" in p.club.upper()
                                 or "HAUSSON" in p.club.upper()])
                self.assertEqual([], [p.category for p in rows
                                      if "hausson" in p.category.lower()])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class TheUnclassified(unittest.TestCase):
    """The 2021 sheet lists two seniors it did not classify."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("2021")

    def test_a_competitor_the_document_did_not_place_gets_no_place(self):
        """"SPC 1 Sr M 70  -  NC  Gagliolo Stefano": the placing column is a
        dash. A rank invented here would be indistinguishable from an earned
        one for the rest of the archive's life."""
        named = {p.fighter for p in self.rows}
        self.assertNotIn("Gagliolo Stefano", named)
        self.assertNotIn("Lavezzo Nicholas", named)

    def test_their_whole_competition_is_absent_rather_than_half_filed(self):
        self.assertEqual([], [p for p in self.rows
                              if p.category.startswith("SPC 1 ")])

    def test_they_are_reported_rather_than_silently_dropped(self):
        self.assertEqual(2, len(self.report.notes["unranked"]))
        self.assertTrue(any("no place" in p for p in self.report.problems))
        self.assertTrue(any("Gagliolo Stefano" in row
                            for row in self.report.notes["unranked"]))

    def test_the_verdict_column_is_reported_even_though_it_has_no_field(self):
        self.assertEqual({"P": 117, "W.O.": 2, "NC": 2},
                         self.report.notes["verdicts"])

    def test_savate_awards_two_bronzes_and_both_survive(self):
        podium = sorted((p.rank, p.fighter) for p in self.rows
                        if p.category == "SA Sr F -52 kg")
        self.assertEqual([("1", "Lo Iacono Ilaria"), ("2", "Ranise Matilde"),
                          ("3", "Bruzzese Silvia"), ("3", "Malagò Erika")],
                         podium)

    def test_the_date_is_the_competition_s_not_the_printer_s(self):
        """The footer of every page reads "24 maggio 2021, Ore 21:06", which is
        when the PDF was made. The championship was on the 23rd."""
        self.assertEqual("2021-05-23", self.tournament.start_date)
        self.assertEqual("2021-05-23", self.tournament.end_date)
        self.assertEqual("2021", self.tournament.year)
        self.assertEqual("CAMPIONATI ASSOLUTI SAVATE", self.tournament.name)

    def test_the_serie_keeps_two_championships_apart(self):
        """SPC serie 2 -60 kg and SPC serie 3 -65 kg are different
        competitions. Dropping the tier merges them."""
        spc = sorted({p.category for p in self.rows
                      if p.category.startswith("SPC")})
        self.assertEqual(["SPC 2 Sr M -60 kg", "SPC 3 Sr M -65 kg",
                          "SPC 3 Sr M -70 kg"], spc)

    def test_a_style_can_be_read_on_its_own(self):
        _t, combat, report = read("2021", style=["SC", "SPC"])
        self.assertEqual(15, len(combat))
        self.assertEqual({"SC", "SPC"},
                         {p.category.split()[0] for p in combat})
        self.assertEqual(104, report.notes["excluded_by_style"])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class TitlesWonWithoutABout(unittest.TestCase):
    """The 2022 sheet decides fourteen classes on a "W.A." verdict."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("2022")

    def test_a_walkover_gold_is_still_the_gold_the_document_awards(self):
        """One competitor, verdict W.A., placing 1. The document states the
        placing, so the placing is stored - and the verdict is reported,
        because a Placing has nowhere to record how it was won."""
        self.assertEqual([("1", "Viola Valerio")],
                         [(p.rank, p.fighter) for p in self.rows
                          if p.category == "SA Sr M -85 kg"])
        self.assertEqual(14, self.report.notes["verdicts"]["W.A."])

    def test_one_competitor_may_win_two_weight_classes(self):
        """Valerio Viola takes -85 kg unopposed and +85 kg on points. Two
        classes, one person, and neither row is a duplicate of the other."""
        viola = sorted(p.category for p in self.rows
                       if p.fighter == "Viola Valerio")
        self.assertEqual(["SA Sr M +85 kg", "SA Sr M -85 kg"], viola)

    def test_the_dates_span_the_whole_championship(self):
        self.assertEqual("2022-05-19", self.tournament.start_date)
        self.assertEqual("2022-05-22", self.tournament.end_date)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class TheMedalTableAndTheUnderscores(unittest.TestCase):
    """The 2018 sheet, whose two appendices look exactly like results."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("2018")

    def test_a_club_medal_table_produces_no_competitors(self):
        """"1  ECOLE DE SAVATE ...  Liguria  12  3  3" has a result's five
        cells with a club where the fighter belongs."""
        self.assertEqual([], [p for p in self.rows
                              if "ECOLE DE SAVATE" in p.fighter.upper()])
        self.assertEqual([], [p for p in self.rows if p.fighter in
                              ("Liguria", "Lombardia", "Lazio", "Calabria")])
        self.assertIn("MEDAGLIERE PER SOCIETA'",
                      self.report.notes["skipped_sections"])
        self.assertIn("MEDAGLIERE PER REGIONE",
                      self.report.notes["skipped_sections"])

    def test_an_underscore_inside_a_name_is_the_space_it_stands_for(self):
        """Corroborated, not guessed: the 2021 and 2022 sheets print these same
        two competitors with the same parts in separate surname and forename
        columns."""
        named = {p.fighter for p in self.rows}
        self.assertIn("Lo Iacono Ilaria", named)
        self.assertIn("Latini Lisa Andrea", named)
        self.assertIn("Vasile Daniel Sandu", named)
        self.assertEqual([], [n for n in named if "_" in n])

    def test_the_one_underscore_that_could_be_an_apostrophe_is_flagged(self):
        """"D_Isidoro" is the only name where a single letter precedes the
        underscore. It is stored as a space like the rest and reported, never
        repaired into a spelling the document does not contain."""
        self.assertEqual(["D Isidoro Andrea"],
                         self.report.notes["ambiguous_underscore"])
        self.assertTrue(any("apostrophe" in p for p in self.report.problems))

    def test_a_name_the_generator_broke_is_kept_as_printed(self):
        """The source lost the accent from "Diakhaté" and printed a question
        mark. Storing the damage keeps the row findable; inventing the letter
        back would put a spelling in the archive that no source holds."""
        self.assertIn("Diakhat? Masseyni", {p.fighter for p in self.rows})

    def test_a_stub_club_is_kept_rather_than_cleaned_away(self):
        self.assertIn("N.E.S. -", {p.club for p in self.rows})

    def test_the_series_survives_this_layout_too(self):
        combat = sorted({p.category for p in self.rows
                         if p.category.startswith(("SC", "SPC"))})
        self.assertEqual(["SC 1 Sr M -70 kg", "SC 2 Jr M -70 kg",
                          "SC 3 Sr M -70 kg", "SPC 2 Sr M -70 kg",
                          "SPC 3 Sr F -56 kg"], combat)

    def test_the_age_code_is_cased_like_every_other_year_s(self):
        """This generator shouts its age codes and the 2021 one does not.
        "SA SR F -52 kg" and "SA Sr F -52 kg" being two labels for one class
        would hide each Italian championship from the one before it."""
        self.assertIn("SA Sr F -52 kg", {p.category for p in self.rows})


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class LicencesAndReprints(unittest.TestCase):
    """The 2019 sheet, and the second printing of the same spreadsheet."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("2019")

    def test_the_licence_number_is_cut_off_the_name(self):
        self.assertIn("PERUGI NICOLO'", {p.fighter for p in self.rows})
        self.assertEqual([], [p.fighter for p in self.rows
                              if "(" in p.fighter or "-" in p.fighter])

    def test_the_licence_is_reported_because_it_has_no_field(self):
        self.assertIn("PERUGI NICOLO' = 353011", self.report.notes["licences"])
        self.assertTrue(any("licence" in p for p in self.report.problems))

    def test_a_competitor_printed_without_a_licence_is_given_none(self):
        """Two rows name BELMONTE FRANCESCA and neither carries a number."""
        self.assertEqual(
            [], [row for row in self.report.notes["licences"]
                 if row.startswith("BELMONTE")])
        self.assertEqual(2, len([p for p in self.rows
                                 if p.fighter == "BELMONTE FRANCESCA"]))

    def test_the_open_class_is_the_one_the_document_signs(self):
        """"44+" is the class above 44 kg; "35" and "40" are the classes up to
        theirs. The bound is read off the sign, never assumed per class."""
        bounds = {p.category: p.weight_bound for p in self.rows}
        self.assertEqual("over", bounds["SA Spe F +44 kg"])
        self.assertEqual("under", bounds["SA Spe F -35 kg"])
        self.assertEqual("over", bounds["SA Sr M +85 kg"])

    def test_the_city_and_date_are_read_off_the_dateline(self):
        self.assertEqual("2019-04-14", self.tournament.start_date)
        self.assertEqual("Genzano", self.tournament.city)
        self.assertEqual("CAMPIONATI ITALIANI SAVATE", self.tournament.name)

    def test_the_reprint_is_the_same_competition_not_a_second_one(self):
        """The federation serves this spreadsheet twice, printed by two
        different tools at two URLs. Ingesting both would double every Italian
        medal from 2019."""
        _t, reprint, _r = read("2019r")
        same = [(p.category, p.rank, p.fighter, p.club) for p in reprint]
        mine = [(p.category, p.rank, p.fighter, p.club) for p in self.rows]
        self.assertEqual(mine, same)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class RefusingWhatIsNotItsOwn(unittest.TestCase):
    """Bad data is a Report and a skipped row; only an unreadable source is an
    error, and even that is reported rather than raised."""

    def test_another_federation_s_document_is_declined_not_guessed_at(self):
        tournament, rows, report = federkombat.read(
            FIXTURES / "fisav-world-youth-2025.pdf", "not-mine", {})
        self.assertEqual([], rows)
        self.assertTrue(any("layout nobody has read yet" in p
                            for p in report.problems))
        self.assertEqual("not-mine", tournament.slug)

    def test_a_source_that_cannot_be_read_reports_instead_of_raising(self):
        for source in ("/no/such/file.pdf", FIXTURES / "britain-2012.html"):
            with self.subTest(source=str(source)):
                _t, rows, report = federkombat.read(source, "broken", {})
                self.assertEqual([], rows)
                self.assertTrue(report.problems)

    def test_the_manifest_may_override_what_the_document_says(self):
        tournament, _rows, _r = read(
            "2021", {"name": "Campionati Assoluti Savate 2021",
                     "level": "national", "format": "championship",
                     "country": "Italy", "year": "2021"})
        self.assertEqual("Campionati Assoluti Savate 2021", tournament.name)
        self.assertEqual("national", tournament.level)
        self.assertEqual("Italy", tournament.country)


if __name__ == "__main__":
    unittest.main()
