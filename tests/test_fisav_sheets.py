"""The fisav_sheets adapter, against the FISav documents it was written for.

Nine fixtures, one per layout, chosen because each of them breaks something a
careless reader would get wrong:

  africa-2018        the only pre-2019 African result the archive has. Two
                     bronzes in one class, gold and silver only in three
                     others, a name with a hyphen inside it and a name with a
                     stray space inside it.
  africa-2025        one article holding two competitions, two fighters
                     champion in both, and a nation of two words.
  world-combat-2009  fourteen title bouts with the decision stated - including
                     one the canonical vocabulary has no word for, and one
                     weight class printed across two rows.
  m65-plovdiv-2018   six poules and a knockout tree on one sheet, and the
                     sheet's own bout count to hold the reading against.
  f48-vienna-2021    a poule bout nobody scored, and a champion the sheet does
                     name.
  budapest-open-2020 places in a right-hand column that a wrapping club name
                     pushes onto a line of its own, a class handing out two
                     firsts, and an entrant with a club but no country.
  world-junior-2017  seven weight classes on seven pages of one file, whose
                     trees must not be spliced together.
  milan-m56-2022     a font whose capital M loses its word.
  euro-combat-2008   three championships in one PDF, ranks down to seventh,
                     and four competitors the sheet calls "Finalist" without
                     ever saying which of them won.

What is asserted throughout is the archive's two rules rather than the row
counts alone: nothing the document does not state is invented, and nothing that
goes wrong raises.
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import fisav_sheets
from savate.schema import Bout, Placing, Report, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name, slug="x", meta=None, **options):
    return fisav_sheets.read(FIXTURES / name, slug, meta or {}, **options)


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


def complaints(rows):
    out = []
    for row in rows:
        out.extend(check(row) if isinstance(row, Bout) else check_placing(row))
    return out


class Vocabulary(unittest.TestCase):
    """The pieces every reader shares, on the spellings the sheets use."""

    def test_a_band_is_the_class_at_its_upper_figure(self):
        self.assertEqual(("52", "under"), fisav_sheets.weight_at("48-52 kg")[0])
        self.assertEqual(("60", "under"), fisav_sheets.weight_at("56 - 60")[0])

    def test_the_printed_bound_decides_over_and_under(self):
        self.assertEqual(("75", "over"), fisav_sheets.weight_at("+75kg")[0])
        self.assertEqual(("85", "over"), fisav_sheets.weight_at("85 + Kg")[0])
        self.assertEqual(("85", "over"), fisav_sheets.weight_at("plus de 85")[0])
        self.assertEqual(("56", "under"), fisav_sheets.weight_at("-56kg")[0])

    def test_a_year_is_not_a_weight_class(self):
        """Read as one, "2010 European Championship" files an event at -201 kg."""
        for text in ("2010 European Championship", "Championnat 2016"):
            self.assertIsNone(fisav_sheets.weight_at(text)[0], text)

    def test_prose_holding_a_number_is_not_a_class_heading(self):
        """"115 assauts" and "16 ATHLETES" open with a plausible weight."""
        for text in ("2 jours de compétition - 115 assauts",
                     "IL Y A EU AU TOTAL 16 ATHLETES DE 5 PAYS AFRICAINS",
                     "60 athlètes participants"):
            probe = fisav_sheets._Probe()
            fisav_sheets._class_heading(text, probe)
            self.assertIsNone(probe.klass, text)

    def test_vice_champion_is_second_and_not_first(self):
        self.assertEqual("2", fisav_sheets.rank_at("Vice-championne du Monde :")[0])
        self.assertEqual("1", fisav_sheets.rank_at("Championne du monde :")[0])

    def test_finalist_alone_is_not_a_finishing_position(self):
        """Both sides of an undecided final are "Finalist"; neither is second."""
        self.assertEqual("", fisav_sheets.rank_at("Finalist")[0])
        self.assertEqual("", fisav_sheets.rank_at("Finalist - forfait")[0])

    def test_the_class_code_carries_the_sex_and_the_age(self):
        self.assertEqual(("Women", "", "48", "under"), fisav_sheets.code_class("F48"))
        self.assertEqual(("Men", "", "85", "over"), fisav_sheets.code_class("M+85"))
        # FISav writes the junior marker on either side of the sex letter.
        self.assertEqual(("Men", "Junior", "75", "under"),
                         fisav_sheets.code_class("JM75"))
        self.assertEqual(("Women", "Junior", "52", "under"),
                         fisav_sheets.code_class("FJ52"))
        for text in ("A1", "MJ56CI", "TOTAL", "2018"):
            self.assertIsNone(fisav_sheets.code_class(text), text)

    def test_a_two_word_nation_is_one_nation(self):
        self.assertEqual(("DOS SANTOS Ronaldo", "Guinea-Bissau"),
                         fisav_sheets.split_nation("DOS SANTOS Ronaldo Guinea Bissau"))

    def test_an_unknown_tail_is_left_on_the_name(self):
        """A surname turned into a country invents a member federation."""
        self.assertEqual(("MAR MASSAMBA Tolotra", ""),
                         fisav_sheets.split_nation("MAR MASSAMBA Tolotra"))

    def test_a_hyphen_inside_a_name_is_not_a_separator(self):
        self.assertEqual(("Jean-Louis Polimon", "ILE MAURICE"),
                         fisav_sheets.split_name_country(
                             "Jean-Louis Polimon - ILE MAURICE"))


class OtherSports(unittest.TestCase):
    """Canne de combat is not savate, whatever folder it is published in."""

    def test_rows_under_another_sport_are_dropped_and_reported(self):
        report = Report()
        out = fisav_sheets.Rows("x", report)
        fisav_sheets._class_heading("-60 kg", out)
        out.place("1", "A SAVATEUR", "France")
        fisav_sheets._class_heading("Canne de combat hommes -70 kg", out)
        out.place("1", "A CANNE PLAYER", "France")
        fisav_sheets._class_heading("-65 kg", out)
        out.place("1", "ANOTHER SAVATEUR", "France")
        self.assertEqual(["A SAVATEUR", "ANOTHER SAVATEUR"],
                         [p.fighter for p in out.rows])
        self.assertTrue(any("not savate" in p for p in report.problems),
                        report.problems)


class Africa2018(unittest.TestCase):
    """The 2018 CASavate report - the archive's only African result before 2019."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("fisav-africa-2018.pdf", "af18")

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_it_holds_the_sixteen_medallists_it_says_it_does(self):
        """The header claims 16 athletes from 5 countries, and lists all 16."""
        self.assertEqual(16, len(placings(self.rows)))
        self.assertEqual([], bouts(self.rows))

    def test_the_six_classes_are_the_six_the_report_prints(self):
        self.assertEqual(["60", "65", "70", "75", "80", "85"],
                         sorted({p.weight_kg for p in self.rows}, key=int))

    def test_both_bronzes_survive_in_the_class_that_has_two(self):
        third = [p for p in self.rows if p.weight_kg == "70" and p.rank == "3"]
        self.assertEqual(2, len(third))
        self.assertEqual(2, len({p.fighter for p in third}))

    def test_a_class_with_no_bronze_is_left_without_one(self):
        for kilos in ("65", "80", "85"):
            ranks = sorted(p.rank for p in self.rows if p.weight_kg == kilos)
            self.assertEqual(["1", "2"], ranks, kilos)

    def test_a_hyphenated_name_survives_the_country_split(self):
        who = [p for p in self.rows if p.fighter.startswith("Jean-Louis")]
        self.assertEqual(1, len(who))
        self.assertEqual("Mauritius", who[0].country)

    def test_a_name_damaged_in_the_source_is_kept_as_printed(self):
        """The PDF prints "L eandro"; repairing it would be guessing at a person."""
        self.assertIn("L éandro Montéro", [p.fighter for p in self.rows])

    def test_an_unrecognised_nation_is_kept_rather_than_mapped(self):
        self.assertIn("GUINEE BISSAU", {p.country for p in self.rows})


class Africa2025(unittest.TestCase):
    """The Dakar article: two competitions, and first place only."""

    def test_the_two_disciplines_are_two_competitions(self):
        _, assaut, _ = read("fisav-africa-2025.html", "af25a", section="assaut")
        _, combat, _ = read("fisav-africa-2025.html", "af25c", section="combat")
        self.assertEqual(14, len(assaut))
        self.assertEqual(11, len(combat))
        self.assertEqual([], complaints(assaut) + complaints(combat))

    def test_a_fighter_champion_in_both_holds_each_class_once(self):
        """Merged into one competition he would hold one category twice.

        The article codes his class "M100". 100 is not on savate's ladder and
        the article prints no bound, so the figure is stored as printed and
        the bound left empty - a bound would be a guess."""
        _, assaut, _ = read("fisav-africa-2025.html", "af25a", section="assaut")
        _, combat, _ = read("fisav-africa-2025.html", "af25c", section="combat")
        for rows in (assaut, combat):
            held = [p.category for p in rows
                    if p.fighter == "AKOUAN Wilson Pharelle"]
            self.assertEqual(["Men 100 kg"], held)

    def test_reading_it_without_a_section_is_reported(self):
        _, rows, report = read("fisav-africa-2025.html", "af25")
        self.assertEqual(25, len(rows))
        self.assertTrue(any("2 competitions" in p for p in report.problems),
                        report.problems)

    def test_it_holds_nothing_but_first_places(self):
        _, rows, _ = read("fisav-africa-2025.html", "af25a", section="assaut")
        self.assertEqual({"1"}, {p.rank for p in rows})
        self.assertEqual({"gold"}, {p.medal for p in rows})

    def test_a_two_word_nation_is_not_taken_into_the_name(self):
        _, rows, _ = read("fisav-africa-2025.html", "af25a", section="assaut")
        who = [p for p in rows if p.country == "Guinea-Bissau"]
        self.assertEqual(["DOS SANTOS Ronaldo"], [p.fighter for p in who])

    def test_the_junior_code_is_read_as_junior(self):
        _, rows, _ = read("fisav-africa-2025.html", "af25a", section="assaut")
        who = [p for p in rows if p.fighter == "HELALI Badis"]
        self.assertEqual("Junior", who[0].age_class)
        self.assertEqual("Men", who[0].gender)


class WorldCombat2009(unittest.TestCase):
    """Fourteen world title bouts, each with its date, venue and decision."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-world-combat-2009.pdf", "wc09")
        cls.bouts = bouts(cls.rows)

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_it_holds_fourteen_finals_and_their_podiums(self):
        self.assertEqual(14, len(self.bouts))
        self.assertEqual({"final"}, {b.phase for b in self.bouts})
        self.assertEqual(28, len(placings(self.rows)))
        self.assertEqual(Counter({"1": 14, "2": 14}),
                         Counter(p.rank for p in placings(self.rows)))

    def test_the_winner_is_one_of_the_two_people_in_the_bout(self):
        for bout in self.bouts:
            self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)
            self.assertNotEqual(bout.winner, bout.loser)

    def test_no_corner_is_claimed(self):
        """Red and blue are a corner, and this sheet never says who stood where."""
        self.assertEqual({""}, {b.winner_corner for b in self.bouts})

    def test_a_stoppage_keeps_the_word_the_sheet_printed(self):
        """"Hors combat" reads as an abandon and stays "hors combat".

        The two fields do different jobs. `decision` is the canonical class the
        barème scores - and the barème treats a stoppage exactly as it treats a
        retirement, an ordinary defeat, so the class is right. `decision_detail`
        keeps the federation's own word, so the distinction between a fighter
        who could not continue and one who gave up is never lost, only moved to
        the field that can hold it.
        """
        stopped = [b for b in self.bouts if "hors combat" in b.decision_detail]
        self.assertEqual(2, len(stopped))
        self.assertEqual({"abandon"}, {b.decision for b in stopped})
        self.assertEqual({"decided"}, {b.status for b in stopped})

    def test_a_majority_decision_is_a_decision(self):
        majority = [b for b in self.bouts if "majorité" in b.decision_detail]
        self.assertEqual(3, len(majority))
        self.assertEqual({"points"}, {b.decision for b in majority})

    def test_a_disqualification_is_read_as_one(self):
        dq = [b for b in self.bouts if b.decision == "disqualification"]
        self.assertEqual(["Yannick FOELLER"], [b.winner for b in dq])

    def test_a_class_printed_across_two_rows_is_still_one_class(self):
        """"plus de" opens the cell on the champion's line, "85" closes it on
        the runner-up's."""
        heavy = [b for b in self.bouts if b.winner == "Fabrice AURIENG"]
        self.assertEqual([("85", "over")],
                         [(b.weight_kg, b.weight_bound) for b in heavy])

    def test_each_bout_carries_the_date_of_its_own_venue(self):
        self.assertEqual(5, len({b.date for b in self.bouts}))
        self.assertTrue(all(b.date.startswith("2009-") for b in self.bouts))


class Plovdiv2018(unittest.TestCase):
    """Six poules and a knockout tree on one sheet, with the sheet's own totals."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-m65-plovdiv-2018.pdf", "m65")
        cls.bouts = bouts(cls.rows)

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_the_reading_reproduces_the_sheets_own_bout_count(self):
        """The sheet says "systeme a 23 assauts" and lists 18 athletes."""
        self.assertEqual(23, len(self.bouts))
        self.assertEqual([], [p for p in self.report.problems
                              if "comes to" in p or "competitors entered" in p])

    def test_all_six_poules_are_read(self):
        poules = Counter(b.poule for b in self.bouts if b.phase == "poule")
        self.assertEqual({"A": 3, "B": 3, "C": 3, "D": 3, "E": 3, "F": 3},
                         dict(poules))

    def test_nobody_fights_themselves(self):
        for bout in self.bouts:
            self.assertNotEqual(bout.red, bout.blue, bout.bout_id)

    def test_the_bracket_runs_quarters_semis_final(self):
        self.assertEqual({"poule": 18, "quarter": 2, "semi": 2, "final": 1},
                         dict(Counter(b.phase for b in self.bouts)))
        final = [b for b in self.bouts if b.phase == "final"][0]
        self.assertEqual({"GHASSIRI", "BOURGUARNE"}, {final.red, final.blue})
        self.assertEqual("GHASSIRI", final.winner)

    def test_warnings_land_in_their_own_fighters_column(self):
        """Points and warnings are two blocks of the same columns; swapping
        them would rewrite the poule's ranking."""
        bout = next(b for b in self.bouts
                    if {b.red, b.blue} == {"GHASSIRI", "PLAISTOWE"})
        self.assertEqual(("3", "0"), (bout.red_points, bout.red_warnings))
        self.assertEqual(("1", "2"), (bout.blue_points, bout.blue_warnings))

    def test_nations_come_off_the_entry_list(self):
        bout = next(b for b in self.bouts
                    if {b.red, b.blue} == {"GHASSIRI", "PLAISTOWE"})
        self.assertEqual("France", bout.red_country)
        self.assertEqual("United Kingdom", bout.blue_country)

    def test_the_class_is_the_code_in_the_corner(self):
        self.assertEqual({"Men -65 kg"}, {b.category for b in self.bouts})
        self.assertEqual({("65", "under")},
                         {(b.weight_kg, b.weight_bound) for b in self.bouts})


class Vienna2021(unittest.TestCase):
    """A world cup poule with one bout nobody scored."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-f48-vienna-2021.pdf", "f48")
        cls.bouts = bouts(cls.rows)

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_an_unscored_pairing_is_stored_unresolved_and_reported(self):
        """The totals row proves it: three fighters hold eight points where
        three fought bouts would pay twelve."""
        open_bout = next(b for b in self.bouts if b.status == "unresolved")
        self.assertEqual({"BELJAK", "ARZT"}, {open_bout.red, open_bout.blue})
        self.assertEqual(("", ""), (open_bout.red_points, open_bout.blue_points))
        self.assertEqual("", open_bout.winner)
        self.assertEqual("", open_bout.result_source)
        self.assertTrue(any("carries no points" in p for p in self.report.problems),
                        self.report.problems)

    def test_the_final_names_its_winner(self):
        final = next(b for b in self.bouts if b.phase == "final")
        self.assertEqual({"ARZT", "BELJAK"}, {final.red, final.blue})
        self.assertEqual("ARZT", final.winner)
        self.assertEqual("BELJAK", final.loser)

    def test_the_scoring_scale_is_read_off_the_sheet(self):
        """This sheet pays a draw 2 points, the 2019 sheets pay it 3."""
        self.assertEqual([], [p for p in self.report.problems
                              if "scoring scale" in p])
        self.assertEqual(4, len(self.bouts))


class BudapestOpen2020(unittest.TestCase):
    """Places in a right-hand column, and clubs the archive can keep."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-budapest-open-2020.pdf", "bo20")

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_it_holds_every_entrant_the_sheet_places(self):
        self.assertEqual(101, len(self.rows))
        self.assertEqual(38, len({p.category for p in self.rows}))

    def test_a_wrapped_club_does_not_carry_its_entrant_into_the_next_class(self):
        """The place and the rest of the club are printed on their own lines."""
        who = next(p for p in self.rows if p.fighter == "Ivan Juranko")
        self.assertEqual("M - 25 kg child 3x1 min", who.category)
        self.assertEqual("3", who.rank)
        self.assertIn("Varaždin", who.club)

    def test_a_class_that_hands_out_two_firsts_keeps_both_and_says_so(self):
        firsts = [p.fighter for p in self.rows
                  if p.category == "M 60-65 kg senior" and p.rank == "1"]
        self.assertEqual(2, len(firsts))
        self.assertTrue(any("share place 1" in p for p in self.report.problems),
                        self.report.problems)

    def test_a_club_is_not_promoted_to_a_country(self):
        who = next(p for p in self.rows if p.fighter == "Delphine Fremondeau")
        self.assertEqual("", who.country)
        self.assertEqual("London SAVATE", who.club)

    def test_the_sheets_own_class_heading_is_kept(self):
        """"cadet1" and "cadet2" are different age bands, and "Combat S2" is a
        different discipline; a rebuilt label loses all three."""
        labels = {p.category for p in self.rows}
        self.assertIn("M80-85 kg Combat S2", labels)
        self.assertIn("M 70-75 kg senior A cath.", labels)
        self.assertIn("M 70-75 kg senior B cath.", labels)


class WorldJunior2017(unittest.TestCase):
    """Seven weight classes on seven pages, each with its own tree."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-world-junior-2017-ring1.pdf", "wj17")
        cls.bouts = bouts(cls.rows)

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_each_page_is_its_own_class(self):
        self.assertEqual(7, len({b.category for b in self.bouts}))
        self.assertEqual({"Junior"}, {b.age_class for b in self.bouts})
        self.assertEqual({"Men"}, {b.gender for b in self.bouts})

    def test_two_pages_trees_are_not_spliced_together(self):
        """The pages share their heights; read as one document the bouts of
        page four would take opponents from page five."""
        for bout in self.bouts:
            self.assertNotEqual(bout.red, bout.blue, bout.bout_id)
        for category in {b.category for b in self.bouts}:
            here = [b for b in self.bouts if b.category == category]
            self.assertLessEqual(len(here), 3, category)

    def test_a_single_bout_page_is_a_final(self):
        here = [b for b in self.bouts if b.weight_kg == "60"]
        self.assertEqual(1, len(here))
        self.assertEqual("final", here[0].phase)
        self.assertEqual({"MARIMOUTOU Eddy", "DOZDOR Roko"},
                         {here[0].red, here[0].blue})
        self.assertEqual("DOZDOR Roko", here[0].winner)

    def test_the_poule_bouts_are_not_invented(self):
        """The header counts them; the page never prints them."""
        self.assertEqual([], [b for b in self.bouts if b.phase == "poule"])
        self.assertTrue(any("poule bouts are not printed" in p
                            for p in self.report.problems), self.report.problems)


class Milan2022(unittest.TestCase):
    """A font whose capital M is kerned into the following word."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "fisav-milan-m56-2022.pdf", "m56-2022")

    def test_every_row_is_well_formed(self):
        self.assertEqual([], complaints(self.rows))

    def test_the_kerning_split_is_repaired_before_any_name_is_matched(self):
        sheet = fisav_sheets.Sheet(FIXTURES / "fisav-milan-m56-2022.pdf")
        joined = "\n".join(" ".join(w.text for w in line)
                           for line in fisav_sheets._rejoin_kerned(sheet.lines))
        for whole, broken in (("EMILIO", "EM ILIO"), ("MAURITIUS", "M AURITIUS"),
                              ("MOLLET", "M OLLET"), ("CHAMPION", "CHAM PION")):
            self.assertIn(whole, joined)
            self.assertNotIn(broken, joined)

    def test_two_real_words_are_not_welded_together(self):
        sheet = fisav_sheets.Sheet(FIXTURES / "fisav-milan-m56-2022.pdf")
        joined = "\n".join(" ".join(w.text for w in line)
                           for line in fisav_sheets._rejoin_kerned(sheet.lines))
        self.assertIn("CHARLES HERBERT", joined)
        self.assertIn("SEBASTIEN ZOLLKAU", joined)

    def test_the_knockout_path_is_complete_and_the_groups_are_not_invented(self):
        self.assertEqual({"semi": 2, "final": 1},
                         dict(Counter(b.phase for b in self.rows)))
        final = next(b for b in self.rows if b.phase == "final")
        self.assertEqual("CHARLES HERBERT", final.winner)
        self.assertTrue(any("group bouts are not printed" in p
                            for p in self.report.problems), self.report.problems)

    def test_the_footer_dates_and_places_the_competition(self):
        self.assertEqual("2022-09-24", self.tournament.start_date)
        self.assertEqual("Milan", self.tournament.city)


class EuroCombat2008(unittest.TestCase):
    """Three championships in one PDF, ranked past the podium."""

    def test_a_section_picks_one_championship_out_of_the_file(self):
        _, junior, _ = read("fisav-euro-combat-2008.pdf", "j08", section="junior")
        _, senior, _ = read("fisav-euro-combat-2008.pdf", "s08", section="senior")
        self.assertEqual(34, len(junior))
        self.assertEqual(63, len(senior))
        self.assertEqual([], complaints(junior) + complaints(senior))

    def test_the_title_states_the_age_class_for_everything_under_it(self):
        _, junior, _ = read("fisav-euro-combat-2008.pdf", "j08", section="junior")
        self.assertEqual({"Junior"}, {p.age_class for p in junior})

    def test_an_undecided_final_stores_no_placing_and_is_reported(self):
        """Both fighters are called "Finalist"; neither is a silver medallist."""
        _, senior, report = read("fisav-euro-combat-2008.pdf", "s08",
                                 section="senior")
        for name in ("AKMATOV", "SUIRE", "DEMIR Sennur", "KOVACEVIC"):
            self.assertNotIn(name, " ".join(p.fighter for p in senior))
        self.assertEqual(4, len([p for p in report.problems
                                 if "never decides" in p]), report.problems)

    def test_both_bronzes_survive(self):
        _, junior, _ = read("fisav-euro-combat-2008.pdf", "j08", section="junior")
        third = [p for p in junior if p.weight_kg == "60" and p.rank == "3"]
        self.assertEqual(sorted(["VAGGE Andrea", "HUNIC Tomislav"]),
                         sorted(p.fighter for p in third))

    def test_a_row_the_pdf_split_in_two_is_put_back_together(self):
        """The class and "Vice Champion" sit five points above the name."""
        _, junior, _ = read("fisav-euro-combat-2008.pdf", "j08", section="junior")
        who = [p for p in junior if p.rank == "2" and p.weight_bound == "over"]
        self.assertEqual(["FERNANDEZ Javier Iglesias"], [p.fighter for p in who])
        self.assertEqual("Spain", who[0].country)

    def test_places_past_the_podium_are_kept(self):
        _, senior, _ = read("fisav-euro-combat-2008.pdf", "s08", section="senior")
        self.assertEqual({"1", "2", "3", "4", "5", "6", "7"},
                         {p.rank for p in senior})
        self.assertEqual({""}, {p.medal for p in senior if p.rank not in "123"})


class BadInput(unittest.TestCase):
    """Report, do not crash."""

    def test_a_document_no_reader_understands_yields_no_rows_and_says_so(self):
        """FISav's generated pool sheets belong to another adapter. Their draw
        slots and bracket labels read as ranks if nothing stops them, and an
        earlier version of this reader turned one of them into 266 medallists
        whose names ended in "UKRAINE A1 3 1"."""
        for name in ("fisav-world-assaut-2024.pdf", "fisav-world-youth-2025.pdf"):
            _, rows, report = read(name, "other")
            self.assertEqual([], rows, name)
            self.assertTrue(report.problems, name)

    def test_a_missing_source_is_the_one_thing_that_does_raise(self):
        with self.assertRaises(FileNotFoundError):
            read("no-such-file.pdf", "nope")


if __name__ == "__main__":
    unittest.main()
