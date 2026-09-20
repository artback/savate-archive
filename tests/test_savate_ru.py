"""The Russian federation's hall-of-fame pages, against cuts of all four.

The fixtures are savate-boxe.ru's own markup, verbatim, cut down to a handful
of `div.warrior` blocks each - including the `display:none` column header whose
three spans read "Стиль | Год | Титул" and would otherwise be read as an honour.
The blocks were chosen for what they would break rather than for being typical:

    legends              a Год cell holding two years; the cadet discipline;
                         all five tier words on one athlete; a place printed
                         "(г. Санкт-Петербург)" with the space the other blocks
                         do not have
    champions            the Chauss'fight row, which is a different sport; two
                         different men holding the 2016 European youth title;
                         life dates trailing a name; the Mediterranean cup
    prizery-chempionatov "(Калужская обл., г.Таруса)", a place that is a region
                         and a city; a region with no city at all; life dates
                         with spaces round the dash; the World Combat Games
    prizery-pervenstv    a name with no place at all; the source's misspelt
                         "перевенства"; "Победительница Кубка мира", the only
                         feminine winner of a cup on the four pages

The point these tests exist to hold is the one the adapter was written for:
these pages are careers, not competitions, so `read` returns no rows at all.
Every assertion below is therefore about the parse in the Report - and about
the two facts that decide it, which are that no row prints a weight class and
that two people hold one title in one year.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import sources
from savate.adapters import savate_ru

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PAGES = ["legends", "champions", "prizery-chempionatov", "prizery-pervenstv"]


def read(stem):
    return savate_ru.read(str(FIXTURES / f"savate-ru-{stem}.html"), stem, {})


def page(stem):
    return sources.text(str(FIXTURES / f"savate-ru-{stem}.html"))


def roll(stem):
    """The honours a page could be read for - dropped rows filtered out."""
    return [h for h in savate_ru.roll(page(stem)) if not h["problem"]]


def everything(stem):
    """Every row on the page, dropped ones included."""
    return savate_ru.roll(page(stem))


def by_name(stem, surname):
    return [h for h in roll(stem) if surname in h["fighter"]]


class NoRowsAreStored(unittest.TestCase):
    """The whole point: an honours roll is not a podium and yields nothing."""

    def test_every_page_returns_no_rows(self):
        for stem in PAGES:
            with self.subTest(stem):
                _tournament, rows, report = read(stem)
                self.assertEqual(rows, [])
                self.assertTrue(report.problems)
                self.assertIn("honours roll", report.problems[0])

    def test_the_honours_are_still_reported(self):
        counts = {}
        for stem in PAGES:
            _t, _rows, report = read(stem)
            self.assertEqual(report.notes["kind"], "honours-register")
            counts[stem] = len(report.notes["honours"])
        self.assertEqual(counts,
                         {"legends": 20, "champions": 15,
                          "prizery-chempionatov": 13, "prizery-pervenstv": 8})

    def test_read_does_not_raise_on_a_document_it_does_not_know(self):
        other = FIXTURES / "britain-2018.html"
        _t, rows, report = savate_ru.read(str(other), "x", {})
        self.assertEqual(rows, [])
        self.assertIn("not a savate-boxe.ru", report.problems[0])


class TheColumnHeaderIsNotAnHonour(unittest.TestCase):

    def test_stil_god_titul_never_becomes_a_row(self):
        for stem in PAGES:
            with self.subTest(stem):
                self.assertIn("Стиль", page(stem))       # it is in the markup
                titles = {h["title"] for h in roll(stem)}
                self.assertNotIn("Титул", titles)        # and never in a row
                styles = {h["style"] for h in roll(stem)}
                self.assertNotIn("Стиль", styles)


class TheAthleteLine(unittest.TestCase):

    def test_a_cyrillic_name_is_kept_exactly_as_printed(self):
        [person] = [p for p in savate_ru.athletes(page("legends"))
                    if "БАБАДЖАНЯН" in p["fighter"]]
        self.assertEqual(person["fighter"], "Нарек БАБАДЖАНЯН")

    def test_the_parenthesis_is_a_city_and_never_a_country(self):
        people = {p["fighter"]: p for p in savate_ru.athletes(page("legends"))}
        self.assertEqual(people["Нарек БАБАДЖАНЯН"]["city"], "Санкт-Петербург")
        # The same city, printed with a space after "г." on this block only.
        self.assertEqual(people["Сергей ЩЕРБАЧЕНКО"]["city"], "Санкт-Петербург")
        self.assertEqual(people["Сергей ЩЕРБАЧЕНКО"]["place"], "г. Санкт-Петербург")
        # No honour anywhere claims a country: the pages never print one.
        for stem in PAGES:
            for h in roll(stem):
                self.assertNotIn("country", h)

    def test_a_region_and_a_city_in_one_parenthesis(self):
        [person] = [p for p in savate_ru.athletes(page("prizery-chempionatov"))
                    if "ЛОХОВА" in p["fighter"]]
        self.assertEqual(person["fighter"], "Олеся ЛОХОВА")
        self.assertEqual(person["place"], "Калужская обл., г.Таруса")
        self.assertEqual(person["city"], "Таруса")

    def test_a_region_with_no_city_leaves_the_city_empty(self):
        [person] = [p for p in savate_ru.athletes(page("prizery-chempionatov"))
                    if "МАЛЬГИН" in p["fighter"]]
        self.assertEqual(person["place"], "Архангельская область")
        self.assertEqual(person["city"], "")

    def test_life_dates_are_not_part_of_the_name(self):
        [person] = [p for p in savate_ru.athletes(page("champions"))
                    if "КОЧКИН" in p["fighter"]]
        self.assertEqual(person["fighter"], "Алексей КОЧКИН")
        self.assertEqual(person["lifespan"], "08.12.1983-31.03.2013")
        [person] = [p for p in savate_ru.athletes(page("prizery-chempionatov"))
                    if "ГИСМЕЕВА" in p["fighter"]]
        self.assertEqual(person["fighter"], "Элина ГИСМЕЕВА")
        self.assertEqual(person["lifespan"], "06.05.1992 - 04.08.2019")

    def test_a_name_with_no_place_is_still_read(self):
        [person] = [p for p in savate_ru.athletes(page("prizery-pervenstv"))
                    if "САДЫГЗАДЕ" in p["fighter"]]
        self.assertEqual(person["fighter"], "Гуснияр САДЫГЗАДЕ")
        self.assertEqual(person["place"], "")
        self.assertEqual(len(person["honours"]), 1)

    def test_the_doubled_colon_in_the_coach_label_does_not_reach_the_coach(self):
        [person] = [p for p in savate_ru.athletes(page("legends"))
                    if "БАБАДЖАНЯН" in p["fighter"]]
        self.assertEqual(person["trainers"], ["Никандров Ю.Г.", "Буланов С.О."])
        self.assertIn("Тренеры::", page("legends"))


class ChaussFightIsNotSavate(unittest.TestCase):

    def test_the_row_is_dropped_and_counted(self):
        _t, rows, report = read("champions")
        self.assertEqual(rows, [])
        dropped = report.notes["dropped_other_sport"]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["style"], "Chauss'fight")
        self.assertTrue(any("another sport" in p for p in report.problems))

    def test_it_is_not_among_the_honours(self):
        for h in roll("champions"):
            self.assertNotIn("Chauss", h["style"])
            self.assertIn(h["discipline"], ("combat", "assaut"))
        # and it is the only row on the page that was dropped
        self.assertEqual(len(everything("champions")), 16)
        self.assertEqual(len(roll("champions")), 15)

    def test_a_dropped_row_is_the_same_shape_as_a_kept_one(self):
        kept = roll("champions")[0]
        [dropped] = [h for h in everything("champions") if h["problem"]]
        self.assertEqual(set(kept), set(dropped))


class TheTierLadder(unittest.TestCase):

    def test_the_five_tiers_on_one_athlete(self):
        got = {(h["title"], h["rank"], h["rank_stated"])
               for h in by_name("legends", "ЩЕРБАЧЕНКО")}
        self.assertIn(("Чемпион мира", "1", True), got)
        self.assertIn(("Победитель первенства Европы", "1", True), got)
        self.assertIn(("Вице-чемпион мира", "2", True), got)
        self.assertIn(("Финалист первенства мира", "2", False), got)
        self.assertIn(("Призер первенства мира", "3", False), got)

    def test_vice_champion_is_not_read_as_champion(self):
        for stem in PAGES:
            for h in roll(stem):
                if h["title"].lower().startswith("вице"):
                    self.assertEqual(h["rank"], "2", h["title"])
                    self.assertEqual(h["tier"], "runner-up")

    def test_a_tier_that_is_read_rather_than_printed_says_so(self):
        for stem in PAGES:
            for h in roll(stem):
                if h["tier"] in ("finalist", "medallist"):
                    self.assertFalse(h["rank_stated"], h["title"])
                else:
                    self.assertTrue(h["rank_stated"], h["title"])

    def test_the_source_misspelling_does_not_lose_the_honour(self):
        [h] = by_name("prizery-pervenstv", "САДЫГЗАДЕ")
        self.assertEqual(h["title"], "Финалист перевенства мира")
        self.assertEqual(h["event"], "championship")
        self.assertEqual(h["age_tier"], "youth")     # первенство, misspelt
        self.assertEqual(h["scope"], "world")
        self.assertEqual(h["rank"], "2")


class TheCompetitionACellNames(unittest.TestCase):

    def test_chempionat_is_senior_and_pervenstvo_is_youth(self):
        tiers = {h["title"]: (h["event"], h["age_tier"])
                 for stem in PAGES for h in roll(stem)}
        self.assertEqual(tiers["Призер чемпионата Европы"],
                         ("championship", "senior"))
        self.assertEqual(tiers["Финалист первенства Европы"],
                         ("championship", "youth"))

    def test_a_bare_title_is_the_senior_championship_and_is_flagged(self):
        [h] = [h for h in by_name("legends", "БАБАДЖАНЯН")
               if h["title"] == "Чемпион мира"]
        self.assertEqual((h["event"], h["age_tier"]), ("championship", "senior"))
        self.assertFalse(h["event_stated"])
        [h] = [h for h in by_name("legends", "БАБАДЖАНЯН")
               if h["title"] == "Победитель первенства мира"]
        self.assertTrue(h["event_stated"])

    def test_a_cup_is_not_a_championship(self):
        [h] = [h for h in by_name("champions", "ЕГОРОВ")
               if "Кубка мира" in h["title"]]
        self.assertEqual(h["event"], "cup")
        self.assertEqual(h["scope"], "world")
        self.assertTrue(h["student"])
        [h] = [h for h in by_name("champions", "ЕГОРОВ")
               if "Средиземноморских" in h["title"]]
        self.assertEqual((h["event"], h["scope"]), ("cup", "mediterranean"))

    def test_the_world_combat_games_are_neither(self):
        [h] = [h for h in by_name("prizery-chempionatov", "ГОЛУБЕВА")
               if "Combat Games" in h["title"]]
        self.assertEqual(h["event"], "games")
        self.assertEqual(h["scope"], "world")
        self.assertEqual(h["age_tier"], "")

    def test_a_year_cell_holding_two_years_is_the_honour_won_twice(self):
        got = [h for h in by_name("legends", "БАБАДЖАНЯН")
               if h["title"] == "Вице-чемпион мира"]
        self.assertEqual([h["year"] for h in got], ["2015", "2019"])
        self.assertTrue(all(h["year_shared"] for h in got))
        self.assertTrue(all(h["years"] == "2015, 2019" for h in got))

    def test_the_cadet_discipline_keeps_its_age_class(self):
        cadets = [h for h in roll("legends") if h["age_class"]]
        self.assertTrue(cadets)
        for h in cadets:
            self.assertEqual(h["age_class"], "Cadet")
            self.assertEqual(h["discipline"], "assaut")
            self.assertIn("кадеты", h["style"])

    def test_komba_is_combat_and_asso_is_assaut(self):
        seen = {(h["style"], h["discipline"])
                for stem in PAGES for h in roll(stem)}
        self.assertIn(("Комба", "combat"), seen)
        self.assertIn(("Ассо", "assaut"), seen)
        self.assertIn(("Ассо (кадеты)", "assaut"), seen)
        self.assertEqual({d for _s, d in seen}, {"combat", "assaut"})


class GenderComesFromGrammarOneWayOnly(unittest.TestCase):

    def test_a_feminine_title_names_a_woman(self):
        [h] = [h for h in by_name("prizery-pervenstv", "ПЛУЖНИКОВА")
               if "Победительница" in h["title"]]
        self.assertEqual(h["gender"], "Women")
        self.assertEqual(h["rank"], "1")
        self.assertEqual(h["event"], "cup")

    def test_a_masculine_title_is_unmarked_and_not_called_men(self):
        for stem in PAGES:
            for h in roll(stem):
                if h["title_form"] == "unmarked":
                    self.assertEqual(h["gender"], "")
                else:
                    self.assertEqual(h["gender"], "Women")

    def test_every_feminine_stem_is_recognised(self):
        got = {h["title"].split()[0] for stem in PAGES for h in roll(stem)
               if h["gender"] == "Women"}
        self.assertTrue({"Чемпионка", "Призерка", "Финалистка",
                         "Победительница"} <= got)


class WhyNoTournamentIsProposed(unittest.TestCase):
    """The two facts that make these rows unstorable, asserted from the data."""

    def test_almost_nothing_prints_a_weight_class(self):
        for stem in PAGES:
            _t, _rows, report = read(stem)
            honours = report.notes["honours"]
            classed = [h for h in honours if h["weight_kg"]]
            self.assertLessEqual(len(classed), 1)
            self.assertTrue(any("print no weight class" in p
                                for p in report.problems))

    def test_the_one_class_that_is_printed_is_a_professional_title(self):
        [h] = [h for h in roll("legends") if h["weight_kg"]]
        self.assertEqual((h["weight_kg"], h["weight_bound"]), ("52", "under"))
        self.assertTrue(h["professional"])
        self.assertEqual(h["gender"], "Women")

    def test_two_people_hold_one_title_in_one_year(self):
        _t, _rows, report = read("champions")
        clashes = {k: v for k, v in report.notes["competitions"].items()
                   if v["golds"] > 1}
        self.assertEqual(len(clashes), 1)
        [(key, clash)] = clashes.items()
        self.assertIn("combat european youth championship 2016", key)
        self.assertEqual(sorted(clash["winners"]),
                         ["Игорь КУРГАНСКИЙ", "Тамерлан ЕДЗОЕВ"])
        self.assertTrue(any("more than one winner" in p
                            for p in report.problems))


if __name__ == "__main__":
    unittest.main()
