"""The Serbian federation's three document shapes, against cuts of each.

Every fixture but one is the federation's own text, verbatim, cut down to the
rows that would break something:

    srbija-ranked-list      the 2019 national cup: unsigned weight headings
                            ("24kg:"), a class printing only third and fourth
                            place, two bronzes in one class, a year of birth
                            trailing a club, the "best cadet of the age group"
                            prize printed ABOVE the results, and the club
                            standings table that ends the results
    srbija-fused-heading    the 2021 pioneers' report, whose "-70kg: MLAĐI
                            JUNIORI:" prints a weight class and the next age
                            heading on one line - the line that files three
                            boys as older pioneer girls if it is read as a
                            weight heading alone
    srbija-team-report      the 2023 Varaždin report: a masculine plural over a
                            mixed pair, an age word in front of one athlete and
                            not another, and Damjan Marković, who "ostao bez
                            medalje" two lines under a bronze heading
    srbija-cyrillic-report  the 2022 Weiz report, in Cyrillic, with "до 85кг"
                            for a weight and "Медаље нису освојили" for the
                            two who did not medal
    srbija-oblique-names    the 2016 Sofia report: one medal whose winner is in
                            the nominative, one in the instrumental ("sa
                            Dejanom Ivković"), and one sentence claiming two
                            colours for three women
    srbija-fused-words      the 2021 Weiz report, whose text layer lost its
                            spaces ("srebrenemedaljeosvojilisujuniori")
    srbija-register         the Vojvodina table: one row per athlete-result
                            across eight championships, with no weight class
    srbija-annual-report    the 2012 annual report, which holds three
                            championships under three headings

The exception is `srbija-other-sports`, which is assembled from real lines of
the 2020 Obrenovac report with a canne de combat section and a demonstration
put into it. No document in this family mixes the sports, so there is nothing
to cut down - but the archive's rule is that canne de combat, chausson and
savate forme are different sports and must never be filed as savate, and a rule
with no test is a rule that will be broken by the next layout.

The workbook is built here rather than saved: it mirrors the geometry of the
Loverval 2021 file sheet for sheet - the barème on `récap`, the entry list on
`insc`, the medal table with its two bronze columns on `CL`, a class sheet with
its poule cross-table and its finale block, and a ring running order that is
the only place a corner is stated - at a size that can be read in one screen.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import srbija_sheets
from savate.schema import Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(stem, meta=None, **options):
    return srbija_sheets.read(str(FIXTURES / f"srbija-{stem}.txt"), stem,
                              meta or {}, **options)


def rows_of(stem, meta=None, **options):
    _tournament, rows, _report = read(stem, meta, **options)
    return rows


def problems(report):
    return " | ".join(report.problems)


def named(rows, surname):
    return [r for r in rows if surname in getattr(r, "fighter", "")]


class TheAdapterContract(unittest.TestCase):

    def test_the_module_is_an_adapter(self):
        self.assertEqual(srbija_sheets.NAME, "srbija_sheets")
        self.assertTrue(srbija_sheets.DESCRIPTION)
        self.assertTrue(callable(srbija_sheets.read))

    def test_a_document_it_cannot_read_is_reported_and_not_raised(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("nothing here is a result at all\n" * 5)
            path = handle.name
        tournament, rows, report = srbija_sheets.read(path, "junk", {})
        self.assertEqual(rows, [])
        self.assertTrue(report.problems)
        self.assertEqual(tournament.slug, "junk")

    def test_a_source_that_does_not_exist_is_reported_and_not_raised(self):
        _t, rows, report = srbija_sheets.read("/no/such/file.doc", "x", {})
        self.assertEqual(rows, [])
        self.assertIn("could not fetch", problems(report))


class TheRankedList(unittest.TestCase):
    """The national championships and cups: a podium under a weight heading."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("ranked-list")

    def test_every_row_is_a_placing_and_none_is_a_bout(self):
        # These documents publish who finished where and never who beat whom.
        self.assertTrue(self.rows)
        self.assertTrue(all(isinstance(r, Placing) for r in self.rows))

    def test_every_placing_is_well_formed(self):
        for placing in self.rows:
            with self.subTest(placing.fighter):
                self.assertEqual(check_placing(placing), [])

    def test_the_competitors_are_read_with_their_clubs(self):
        koldan = named(self.rows, "Koldan")[0]
        self.assertEqual(koldan.fighter, "Lazar Koldan")
        self.assertEqual(koldan.club, "Arena Iđoš")
        self.assertEqual(koldan.rank, "1")
        self.assertEqual(koldan.medal, "gold")

    def test_the_age_heading_and_the_weight_heading_make_the_category(self):
        self.assertEqual(named(self.rows, "Koldan")[0].category,
                         "Younger Pioneer Men -24 kg")
        self.assertEqual(named(self.rows, "Veličkov")[0].category,
                         "Older Pioneer Women -39 kg")

    def test_two_bronzes_in_one_class_both_survive(self):
        # Savate awards two bronzes. Two rank-3 rows in one class is correct.
        bronzes = [r for r in self.rows
                   if r.category == "Younger Junior Women -56 kg"
                   and r.rank == "3"]
        self.assertEqual(sorted(r.fighter for r in bronzes),
                         ["Ivana Jakovljević", "Sara Vukašinović"])

    def test_fourth_place_is_dropped_and_said_so(self):
        self.assertEqual(named(self.rows, "Vukov"), [])
        self.assertIn("below third", problems(self.report))

    def test_a_class_printing_only_a_third_place_keeps_it_and_is_flagged(self):
        veličkov = named(self.rows, "Veličkov")[0]
        self.assertEqual(veličkov.rank, "3")
        self.assertIn("third place but no first", problems(self.report))

    def test_an_unsigned_weight_heading_is_an_upper_limit_and_is_reported(self):
        koldan = named(self.rows, "Koldan")[0]
        self.assertEqual((koldan.weight_kg, koldan.weight_bound), ("24", "under"))
        self.assertIn("printed no sign", problems(self.report))

    def test_the_open_class_keeps_its_plus(self):
        lekiić = named(self.rows, "Lekiić")[0]
        self.assertEqual((lekiić.weight_kg, lekiić.weight_bound), ("75", "over"))
        self.assertEqual(lekiić.category, "Cadet Men +75 kg")

    def test_a_year_of_birth_is_not_part_of_the_club(self):
        self.assertEqual(named(self.rows, "Raičević")[0].club, "Beograd Beograd")

    def test_the_club_standings_table_is_not_read_as_placings(self):
        # Its rows are numbered too, and a club is not a competitor.
        self.assertEqual(named(self.rows, "Savate boks klub"), [])
        self.assertIn("klubova", self.report.notes.get("stopped_at", ""))

    def test_the_best_of_the_age_group_prize_is_not_a_placing(self):
        # It is printed above the results and names a cadet with her club.
        self.assertEqual(named(self.rows, "Kasap"), [])

    def test_the_date_comes_from_the_document(self):
        self.assertEqual(self.tournament.start_date, "2019-10-06")

    def test_no_competitor_is_given_a_country(self):
        # These sheets print clubs. Stamping the host nation on every row would
        # invent a fact about a visiting competitor.
        self.assertEqual({r.country for r in self.rows}, {""})


class TheLineThatCarriesTwoHeadings(unittest.TestCase):
    """"-70kg: MLAĐI JUNIORI:" - the defect that files boys as girls."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("fused-heading")

    def test_the_three_under_it_are_younger_junior_men(self):
        for surname in ("Dimić", "Sekulić", "Dodić"):
            with self.subTest(surname):
                row = named(self.rows, surname)[0]
                self.assertEqual(row.category, "Younger Junior Men -70 kg")
                self.assertEqual(row.gender, "Men")

    def test_the_womens_class_above_it_keeps_exactly_its_three_women(self):
        women = [r for r in self.rows
                 if r.category == "Older Pioneer Women -52 kg"]
        self.assertEqual(sorted(r.fighter for r in women),
                         ["Anastasija Vučkovac", "Elena Stojiljković",
                          "Maja Reperger"])
        self.assertEqual(sorted(r.rank for r in women), ["1", "2", "3"])

    def test_no_class_awards_one_place_twice(self):
        for rank in ("1", "2"):
            with self.subTest(rank):
                holders = [(r.category, r.rank) for r in self.rows
                           if r.rank == rank]
                self.assertEqual(len(holders), len(set(holders)))
        self.assertNotIn("same place twice", problems(self.report))

    def test_the_reading_is_reported_rather_than_done_quietly(self):
        self.assertIn("both a weight class and an age heading",
                      problems(self.report))


class OtherSportsAndDemonstrations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("other-sports")

    def test_canne_de_combat_competitors_are_not_filed_as_savate(self):
        self.assertEqual(named(self.rows, "Gojić"), [])
        self.assertEqual(named(self.rows, "Kovačević"), [])
        self.assertIn("another sport", problems(self.report))
        self.assertEqual(self.report.notes["other_sport_rows"], 2)

    def test_a_demonstration_produces_no_row_and_is_counted(self):
        self.assertEqual(named(self.rows, "Ostojić"), [])
        self.assertEqual(self.report.notes["demonstrations"], 1)
        self.assertIn("demonstration", problems(self.report))

    def test_savate_resumes_when_a_heading_names_it_again(self):
        self.assertEqual(named(self.rows, "Nikolić")[0].category,
                         "Senior Women Assaut -60 kg")


class TheProseTeamReport(unittest.TestCase):
    """A letter about what the national team won abroad."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("team-report")

    def test_every_placing_is_well_formed(self):
        for placing in self.rows:
            with self.subTest(placing.fighter):
                self.assertEqual(check_placing(placing), [])

    def test_the_two_golds_are_read_with_their_weights(self):
        nikola = named(self.rows, "Nikola Vukčević")[0]
        jovana = named(self.rows, "Jovana Vukčević")[0]
        self.assertEqual((nikola.rank, nikola.weight_kg), ("1", "85"))
        self.assertEqual((jovana.rank, jovana.weight_kg), ("1", "75"))

    def test_a_masculine_plural_does_not_sex_a_mixed_group(self):
        # "osvojili su juniori Nikola Vukčević ... i Jovana Vukčević ..." -
        # Serbian uses the masculine plural for a mixed pair, and Jovana is a
        # woman. The age class is read from it; the gender is not.
        jovana = named(self.rows, "Jovana Vukčević")[0]
        self.assertEqual(jovana.gender, "")
        self.assertEqual(jovana.age_class, "Junior")

    def test_a_singular_age_word_beside_one_athlete_does_sex_the_row(self):
        vidaković = named(self.rows, "Vidaković")[0]
        self.assertEqual((vidaković.age_class, vidaković.gender),
                         ("Senior", "Men"))

    def test_the_man_who_did_not_medal_gets_no_row(self):
        # "nije uspeo da se plasira u polufinale i ostao bez medalje", printed
        # under a bronze heading. Inheriting that heading would invent a medal.
        self.assertEqual(named(self.rows, "Marković"), [])
        self.assertIn("did not medal", problems(self.report))

    def test_the_opening_paragraph_counts_medals_and_yields_none(self):
        self.assertTrue(all(r.fighter not in ("Reprezentacija Srbije", "Naš tim")
                            for r in self.rows))
        self.assertEqual(len(self.rows), 4)

    def test_the_delegation_is_where_the_country_comes_from(self):
        self.assertEqual({r.country for r in self.rows}, {"Serbia"})
        self.assertIn("delegation", problems(self.report))

    def test_the_partial_field_is_declared(self):
        self.assertIn("partial by construction", problems(self.report))


class TheCyrillicReport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "cyrillic-report", {"age_class": "Junior"})

    def test_names_are_transliterated_into_serbian_latin(self):
        # Никола Вукчевић and Nikola Vukčević are one person, not two rows in
        # the register. The transliteration is letter for letter.
        self.assertEqual(named(self.rows, "Vukčević")[0].fighter,
                         "Nikola Vukčević")
        self.assertIn("Cyrillic", problems(self.report))

    def test_a_cyrillic_weight_is_still_a_weight(self):
        # "до 85кг" - the unit is кг, not kg, and the preposition is до.
        vukčević = named(self.rows, "Vukčević")[0]
        self.assertEqual((vukčević.weight_kg, vukčević.weight_bound),
                         ("85", "under"))

    def test_the_clubs_come_through_with_their_abbreviations(self):
        self.assertEqual(named(self.rows, "Abazovski")[0].club, "KBS Novi Sad")

    def test_those_who_did_not_medal_are_not_given_one(self):
        for surname in ("Dimić", "Lukić"):
            with self.subTest(surname):
                self.assertEqual(named(self.rows, surname), [])


class NamesInTheWrongCase(unittest.TestCase):
    """Serbian declines names, and un-declining one would invent a person."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "oblique-names", {"age_class": "Cadet"})

    def test_the_nominative_medallist_is_stored(self):
        marjanović = named(self.rows, "Marjanović")[0]
        self.assertEqual(marjanović.fighter, "Dejan Marjanović")
        self.assertEqual((marjanović.rank, marjanović.weight_kg), ("1", "80"))

    def test_a_name_after_a_preposition_is_refused_and_reported(self):
        self.assertEqual(named(self.rows, "Ivković"), [])
        self.assertIn("not in the nominative", problems(self.report))

    def test_a_sentence_claiming_two_colours_is_dropped_whole(self):
        # Three women, two medal colours, and nothing saying which is whose.
        for surname in ("Zorić", "Domazetovski", "Đekić"):
            with self.subTest(surname):
                self.assertEqual(named(self.rows, surname), [])
        self.assertIn("more than one medal colour", problems(self.report))


class DocumentsThatAreRefusedWhole(unittest.TestCase):

    def test_a_text_layer_with_no_spaces_is_not_guessed_at(self):
        tournament, rows, report = read("fused-words")
        self.assertEqual(rows, [])
        self.assertIn("lost the spaces", problems(report))
        self.assertGreater(report.notes["fused_words"], 0.08)

    def test_a_register_of_many_championships_is_not_a_tournament(self):
        tournament, rows, report = read("register")
        self.assertEqual(rows, [])
        self.assertIn("not one competition", problems(report))


class AnAnnualReportHoldingThreeChampionships(unittest.TestCase):

    def test_without_an_event_nothing_is_read_and_the_events_are_listed(self):
        _t, rows, report = read("annual-report")
        self.assertEqual(rows, [])
        self.assertIn("more than one competition", problems(report))
        self.assertTrue(any("PLOVDIV" in e
                            for e in report.notes["events_in_document"]))

    def test_an_event_selects_only_its_own_medals(self):
        rows = rows_of("annual-report", event="SVETSKO PRVENSTVO")
        self.assertEqual(sorted(r.fighter for r in rows),
                         ["Goran Bajšanski", "Ivana Popadić", "Siniša Zeljković"])

    def test_the_other_event_has_its_own_age_headings(self):
        rows = rows_of("annual-report", event="EVROPSKOG PRVENSTVA U COMBAT")
        self.assertEqual(named(rows, "Ikić")[0].age_class, "Junior")
        self.assertEqual(named(rows, "Čestić")[0].age_class, "Senior")

    def test_a_medallist_with_no_weight_class_keeps_the_medal_and_is_flagged(self):
        _t, rows, report = read("annual-report", event="SVETSKO PRVENSTVO")
        bajšanski = named(rows, "Bajšanski")[0]
        self.assertEqual((bajšanski.rank, bajšanski.weight_kg), ("2", ""))
        self.assertIn("no weight class", problems(report))

    def test_an_event_the_document_does_not_hold_yields_nothing(self):
        _t, rows, report = read("annual-report", event="WORLD CUP 1998")
        self.assertEqual(rows, [])
        self.assertIn("holds no competition called", problems(report))


def _workbook(path):
    """A competition workbook shaped exactly like the Loverval 2021 file."""
    import openpyxl

    book = openpyxl.Workbook()
    recap = book.active
    recap.title = "récap"
    for row, text in enumerate([
            "•Victoire: 3 points", "•Egalité: 2 points", "•défaite : 1 point",
            "•Forfait: 0 point", "•Disqualification: - 1 point"], start=7):
        recap.cell(row=row, column=3, value=text)

    entries = book.create_sheet("insc")
    entries.cell(row=1, column=2, value="Name")
    for row, (surname, forename, country) in enumerate(
            [("ARZT", "ANASTASIIA", "UKRAIN"), ("FAURE", "NADA", "SERBIA"),
             ("LAPAUW", "CLOE", "BELGIUM"), ("NANDI", "CHLOE", "FRANCE")],
            start=3):
        entries.cell(row=row, column=2, value=surname)
        entries.cell(row=row, column=3, value=forename)
        entries.cell(row=row, column=4, value=country)
        entries.cell(row=row, column=5, value="F48")

    medals = book.create_sheet("CL")
    medals.cell(row=2, column=7, value="november 2021")
    medals.cell(row=5, column=1, value="presents")
    medals.cell(row=7, column=4, value="Féminines / Women")
    medals.cell(row=8, column=1, value=4)
    medals.cell(row=8, column=2, value="-48")
    for column, value in ((4, "NANDI CHLOE"), (5, "FRANCE"),
                          (7, "FAURE NADA"), (8, "SERBIA"),
                          (10, "ARZT ANASTASIIA"), (11, "UKRAIN"),
                          (13, "LAPAUW CLOE"), (14, "BELGIUM")):
        medals.cell(row=8, column=column, value=value)

    klass = book.create_sheet("F48")
    klass.cell(row=3, column=3, value="Championnat d'Europe assaut")
    klass.cell(row=3, column=14, value="F48")
    klass.cell(row=5, column=14, value="4 athlètes")
    for row, (surname, country) in enumerate(
            [("ARZT", "UKRAIN"), ("FAURE", "SERBIA"), ("LAPAUW", "BELGIUM"),
             ("NANDI", "FRANCE")], start=14):
        klass.cell(row=row, column=1, value=f"tireur {row - 13}")
        klass.cell(row=row, column=2, value=surname)
        klass.cell(row=row, column=3, value=country)
    # The finale block: the two finalists in the column the label heads, and
    # the champion named beside the words that say so.
    klass.cell(row=12, column=7, value="Finale")
    klass.cell(row=14, column=6, value="NANDI")
    klass.cell(row=15, column=6, value="n°1")
    klass.cell(row=16, column=9, value="NANDI")
    klass.cell(row=17, column=10, value="champion d'Europe")
    klass.cell(row=18, column=6, value="FAURE")
    klass.cell(row=19, column=6, value="n°2")

    klass.cell(row=22, column=1, value="séries: 6 assauts")
    klass.cell(row=24, column=2, value="TIREUR")
    klass.cell(row=24, column=3, value="TIREUR")
    order = ["ARZT", "FAURE", "LAPAUW", "NANDI"]
    for index, surname in enumerate(order):
        klass.cell(row=24, column=5 + index, value=surname)
        klass.cell(row=24, column=9 + index, value=surname)
    bouts = [
        # red, blue, number, red points, blue points, red warn, blue warn
        ("ARZT", "FAURE", 1, 1, 3, 2, 2),        # an ordinary decision
        ("ARZT", "LAPAUW", 2, 3, -1, 0, 3),      # a disqualification
        ("ARZT", "NANDI", 3, 0, 3, None, None),  # a forfait
        ("FAURE", "LAPAUW", 4, 2, 2, None, None),   # a draw
        ("FAURE", "NANDI", 5, None, None, None, None),   # nothing recorded
        ("LAPAUW", "NANDI", 6, None, 3, None, None),     # one cell filled
    ]
    for offset, (red, blue, number, red_points, blue_points, red_warn,
                 blue_warn) in enumerate(bouts):
        row = 25 + offset
        klass.cell(row=row, column=1, value="assaut :")
        klass.cell(row=row, column=2, value=red)
        klass.cell(row=row, column=3, value=blue)
        klass.cell(row=row, column=4, value=number)
        if red_points is not None:
            klass.cell(row=row, column=5 + order.index(red), value=red_points)
        if blue_points is not None:
            klass.cell(row=row, column=5 + order.index(blue), value=blue_points)
        if red_warn is not None:
            klass.cell(row=row, column=9 + order.index(red), value=red_warn)
        if blue_warn is not None:
            klass.cell(row=row, column=9 + order.index(blue), value=blue_warn)

    ring = book.create_sheet("R1")
    ring.cell(row=1, column=2, value="Ring 1")
    ring.cell(row=1, column=8,
              value="vendredi 26 novembre / Friday, November the 26th")
    scheduled = [
        (1, "09:00:00", "F48", "UKRAIN", "ARZT", "", "FAURE", "SERBIA"),
        (2, "09:15:00", "F48", "BELGIUM", "LAPAUW", "", "ARZT", "UKRAIN"),
        (3, "09:30:00", "F48", "FRANCE", "NANDI", "", "ARZT", "UKRAIN"),
        (7, "19:30:00", "F48", "FRANCE", "NANDY", "F", "FAURE", "SERBIA"),
    ]
    for offset, row_values in enumerate(scheduled):
        row = 4 + offset
        for column, value in zip((1, 2, 3, 4, 5, 6, 7, 8), row_values):
            if value:
                ring.cell(row=row, column=column, value=value)
    book.save(path)
    return path


class TheCompetitionWorkbook(unittest.TestCase):
    """The one document in this family that publishes bouts."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        path = Path(cls.directory.name) / "loverval"
        _workbook(path)
        cls.tournament, cls.rows, cls.report = srbija_sheets.read(
            str(path), "loverval", {})
        cls.bouts = [r for r in cls.rows if isinstance(r, Bout)]
        cls.placings = [r for r in cls.rows if isinstance(r, Placing)]

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def bout(self, red, blue):
        found = [b for b in self.bouts
                 if {b.red.split()[0], b.blue.split()[0]} == {red, blue}
                 and b.phase == "poule"]
        self.assertEqual(len(found), 1, f"{red} v {blue}")
        return found[0]

    def test_every_row_is_well_formed(self):
        for bout in self.bouts:
            with self.subTest(bout.bout_id):
                self.assertEqual(check(bout), [])
        for placing in self.placings:
            with self.subTest(placing.placing_id):
                self.assertEqual(check_placing(placing), [])

    def test_the_winner_is_always_one_of_the_two_in_the_bout(self):
        for bout in self.bouts:
            with self.subTest(bout.bout_id):
                if bout.winner:
                    self.assertIn(bout.winner, (bout.red, bout.blue))
                self.assertNotEqual(bout.red, bout.blue)

    def test_the_barème_is_read_from_the_workbook_itself(self):
        self.assertEqual(self.report.notes["bareme"]["-1"], "disqualification")
        self.assertEqual(self.report.notes["bareme"]["1"], "loss")

    def test_a_three_to_one_is_a_decision_on_points(self):
        bout = self.bout("ARZT", "FAURE")
        self.assertEqual(bout.winner, "FAURE NADA")
        self.assertEqual(bout.decision, "points")
        self.assertEqual((bout.red_points, bout.blue_points), ("1", "3"))
        self.assertEqual((bout.red_warnings, bout.blue_warnings), ("2", "2"))

    def test_minus_one_is_a_disqualification(self):
        bout = self.bout("ARZT", "LAPAUW")
        self.assertEqual(bout.decision, "disqualification")
        self.assertEqual(bout.winner, "ARZT ANASTASIIA")

    def test_zero_is_a_forfait(self):
        bout = self.bout("ARZT", "NANDI")
        self.assertEqual(bout.decision, "forfait")
        self.assertEqual(bout.winner, "NANDI CHLOE")

    def test_a_draw_has_no_winner(self):
        bout = self.bout("FAURE", "LAPAUW")
        self.assertEqual(bout.decision, "draw")
        self.assertEqual(bout.winner, "")
        self.assertEqual(bout.status, "unresolved")
        self.assertEqual(bout.result_source, "")

    def test_a_bout_with_no_score_is_unresolved_rather_than_a_win(self):
        bout = self.bout("FAURE", "NANDI")
        self.assertEqual(bout.status, "unresolved")
        self.assertEqual((bout.winner, bout.winner_corner), ("", ""))

    def test_one_score_filled_in_still_names_a_winner_but_no_decision(self):
        bout = self.bout("LAPAUW", "NANDI")
        self.assertEqual(bout.winner, "NANDI CHLOE")
        self.assertEqual(bout.decision, "")

    def test_the_corner_comes_only_from_the_ring_sheet(self):
        # The running order is the only sheet that says who stood where. Where
        # it names the pair the other way round, the row is turned round too.
        first = self.bout("ARZT", "FAURE")
        self.assertEqual((first.red, first.blue),
                         ("ARZT ANASTASIIA", "FAURE NADA"))
        self.assertEqual(first.winner_corner, "blue")
        reversed_pair = self.bout("ARZT", "LAPAUW")
        self.assertEqual(reversed_pair.red, "LAPAUW CLOE")
        self.assertEqual(reversed_pair.winner_corner, "blue")
        self.assertEqual(reversed_pair.red_points, "-1")

    def test_a_bout_the_ring_sheet_does_not_hold_has_no_corner(self):
        unscheduled = self.bout("FAURE", "LAPAUW")
        self.assertEqual(unscheduled.winner_corner, "")
        self.assertEqual(unscheduled.ring, "")

    def test_the_bouts_are_dated_from_the_day_the_ring_sheet_heads(self):
        self.assertEqual(self.bout("ARZT", "FAURE").date, "2021-11-26")
        self.assertEqual(self.tournament.start_date, "2021-11-26")

    def test_the_surnames_are_joined_to_the_forenames_on_the_entry_sheet(self):
        # The class sheets print surnames; the entry sheet prints the forename
        # beside the same surname in the same class, in the same workbook.
        self.assertEqual(self.bout("ARZT", "FAURE").red, "ARZT ANASTASIIA")
        self.assertEqual(self.bout("ARZT", "FAURE").blue, "FAURE NADA")

    def test_a_nation_the_archive_does_not_know_is_kept_as_printed(self):
        # This workbook writes UKRAIN and RSF. "UKRAIN" is now a registered
        # spelling of Ukraine - a truncation, not a guess - so it resolves.
        # "RSF" deliberately does not: it is almost certainly the Russian
        # Savate Federation, no document in the archive writes the letters out,
        # and almost is not verified. It is kept as printed, which shows up as
        # a country to look at rather than as a wrong one.
        self.assertEqual(self.bout("ARZT", "FAURE").red_country, "Ukraine")
        self.assertEqual(self.bout("ARZT", "FAURE").blue_country, "Serbia")

    def test_the_final_is_read_with_the_champion_the_sheet_names(self):
        final = [b for b in self.bouts if b.phase == "final"]
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0].winner, "NANDI CHLOE")
        self.assertEqual(final[0].result_source, "reported")
        self.assertEqual(final[0].decision, "")
        # NANDY in the running order and NANDI on the class sheet are one
        # person, so the final still finds its corner.
        self.assertEqual(final[0].winner_corner, "red")

    def test_the_medal_table_keeps_both_bronzes(self):
        bronzes = [p for p in self.placings if p.rank == "3"]
        self.assertEqual(sorted(p.fighter for p in bronzes),
                         ["ARZT ANASTASIIA", "LAPAUW CLOE"])
        self.assertTrue(all(p.medal == "bronze" for p in bronzes))

    def test_the_medal_table_and_the_final_agree(self):
        gold = [p for p in self.placings if p.rank == "1"][0]
        self.assertEqual(gold.fighter, "NANDI CHLOE")
        self.assertNotIn("medal table gives gold", problems(self.report))

    def test_the_weight_band_is_the_class_it_ends_at(self):
        self.assertEqual({p.weight_kg for p in self.placings}, {"48"})
        self.assertEqual({p.weight_bound for p in self.placings}, {"under"})
        self.assertEqual({p.category for p in self.placings}, {"Women -48 kg"})


if __name__ == "__main__":
    unittest.main()
