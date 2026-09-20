"""CESav's blog articles, checked line by line against what they print.

These do not test that rows appear. Rows appeared for an earlier adapter in this
archive that filed men under "Junior Women -56 kg" and paired a fighter against
himself. They test the things that would actually go wrong on these pages:

  * "M150kg" is not a weight class, and must not become one
  * the line that ends "in Savona (Italy) on 23rd October 2016" is a different
    event on a different date and must not be filed under this championship
  * a winner is one of the two people in the bout, and never a corner
  * "Vice-champion" is a rank, not a person called Vice
  * a nation printed after a name is split off it, and nothing else is
  * savate awards two bronzes, and both rank-3 rows survive
  * a demonstration produces no row, and is counted
  * a canne de combat line is a different sport and is dropped, and counted
  * a stated winner who is neither fighter leaves the bout unresolved

and the five defects an adversarial reading of the real articles turned up,
each with a test named for it so it cannot come back:

  * two Joomla URLs ending in the same article id are ONE document
  * a page that calls itself European in the headline and World in the body
    has not said which, so the level is left empty
  * a qualifying tournament is not filed as the championship it qualifies for
  * "Champion" is a finishing position and not a medal, and the read says
    where the medal column came from
  * nothing - not the year, not the level, not the name - is read off the URL

The fixtures are the three real articles' own markup, reduced to the article
region and wrapped in the itemprop attributes Joomla puts around it, so they
exercise the real superscript ordinals, &nbsp; runs and hyphen spacing.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import cesav_sheets
from savate.schema import Bout, Placing, Report, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name, slug="t", meta=None):
    return cesav_sheets.read(str(FIXTURES / f"{name}.html"), slug, meta or {})


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


def said(report, fragment):
    return any(fragment.lower() in p.lower() for p in report.problems)


class EveryRowIsWellFormed(unittest.TestCase):
    PAGES = ["cesav-combat-2016", "cesav-pro-2024", "cesav-qualifier-2016",
             "cesav-hazards", "cesav-not-results", "cesav-headless"]

    def test_the_schema_accepts_every_row_of_every_page(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                _t, rows, _r = read(page)
                for row in bouts(rows):
                    self.assertEqual(check(row), [], row)
                for row in placings(rows):
                    self.assertEqual(check_placing(row), [], row)

    def test_no_page_ever_claims_a_corner(self):
        """rouge and bleu are corners. These articles never state one."""
        for page in self.PAGES:
            with self.subTest(page=page):
                _t, rows, _r = read(page)
                for bout in bouts(rows):
                    self.assertEqual(bout.winner_corner, "", bout)

    def test_a_winner_is_one_of_the_two_people_in_the_bout(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                _t, rows, _r = read(page)
                for bout in bouts(rows):
                    if bout.winner:
                        self.assertIn(bout.winner, (bout.red, bout.blue), bout)
                        self.assertIn(bout.loser, (bout.red, bout.blue), bout)
                        self.assertNotEqual(bout.winner, bout.loser, bout)

    def test_nobody_fights_themselves_and_no_id_repeats(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                _t, rows, _r = read(page)
                ids = [r.bout_id for r in bouts(rows)] + \
                      [r.placing_id for r in placings(rows)]
                self.assertEqual(len(ids), len(set(ids)))
                for bout in bouts(rows):
                    self.assertNotEqual(bout.red, bout.blue, bout)


class TheCombat2016Article(unittest.TestCase):
    """Ten result lines: nine bouts, and one that belongs to another event."""

    def setUp(self):
        self.t, self.rows, self.report = read("cesav-combat-2016", "c16")

    def test_it_reads_the_nine_bouts_the_article_prints_for_this_event(self):
        self.assertEqual(len(bouts(self.rows)), 9)

    def test_each_bout_is_the_pair_and_the_verdict_the_line_states(self):
        got = {(b.red, b.blue, b.winner) for b in bouts(self.rows)}
        self.assertEqual(got, {
            ("Berrou Alan", "Leskovic Luka", "Berrou Alan"),
            ("Dessoy Arnaud", "Zarkirko Arthur", "Dessoy Arnaud"),
            ("El Mjiyad Ahmed", "Golic Milos", "El Mjiyad Ahmed"),
            ("Albertus Kevin", "Podvalnyi Andrii", "Albertus Kevin"),
            ("Kada Mehdi", "Plantic Damir", "Kada Mehdi"),
            ("Kebe Karamba", "Van de Merckt Alain", "Kebe Karamba"),
            ("Nandi Chloé", "Piccolo Elisa", "Nandi Chloé"),
            ("Montanari Marion", "Golubeva Rimma", "Montanari Marion"),
            ("Bouchet Adeline", "Burgio Serena", "Bouchet Adeline"),
        })

    def test_the_savona_line_is_not_filed_under_this_championship(self):
        """It names a third city and a third date. It is another event."""
        people = {b.red for b in bouts(self.rows)} | \
                 {b.blue for b in bouts(self.rows)}
        self.assertNotIn("Beroud Jacqueline", people)
        self.assertNotIn("Vincis Chiara", people)
        self.assertTrue(said(self.report, "Savona"))

    def test_m150kg_is_kept_as_printed_and_given_no_weight(self):
        """There is no 150 kg class in savate, and the page does not say what
        the code means. The bout is real; the weight is not invented."""
        odd = [b for b in bouts(self.rows) if b.red == "El Mjiyad Ahmed"]
        self.assertEqual(len(odd), 1)
        self.assertEqual(odd[0].category, "M150kg")
        self.assertEqual(odd[0].weight_kg, "")
        self.assertEqual(odd[0].weight_bound, "")
        self.assertTrue(said(self.report, "M150kg"))

    def test_the_readable_classes_carry_their_weight_and_gender(self):
        by_pair = {b.red: b for b in bouts(self.rows)}
        self.assertEqual(by_pair["Berrou Alan"].weight_kg, "65")
        self.assertEqual(by_pair["Berrou Alan"].weight_bound, "under")
        self.assertEqual(by_pair["Berrou Alan"].gender, "Men")
        self.assertEqual(by_pair["Nandi Chloé"].gender, "Women")
        self.assertEqual(by_pair["Nandi Chloé"].weight_kg, "48")

    def test_no_placing_is_derived_from_a_round_the_page_never_names(self):
        """One bout per class is almost certainly a final. Almost is not said."""
        self.assertEqual(placings(self.rows), [])
        self.assertEqual({b.phase for b in bouts(self.rows)}, {""})

    def test_each_bout_carries_the_date_of_the_subheading_above_it(self):
        dates = {b.red: b.date for b in bouts(self.rows)}
        self.assertEqual(dates["Berrou Alan"], "2016-10-08")
        self.assertEqual(dates["Kada Mehdi"], "2016-12-03")
        self.assertEqual(self.t.start_date, "2016-10-08")
        self.assertEqual(self.t.end_date, "2016-12-03")

    def test_two_venues_leave_the_single_city_field_empty(self):
        self.assertEqual(self.t.city, "")
        self.assertEqual(self.report.notes["venues"], ["Morbihan", "Savoie"])

    def test_the_nations_are_resolved_from_the_bracketed_codes(self):
        by_pair = {b.red: b for b in bouts(self.rows)}
        self.assertEqual(by_pair["Berrou Alan"].red_country, "France")
        self.assertEqual(by_pair["Berrou Alan"].blue_country, "Croatia")
        self.assertEqual(by_pair["El Mjiyad Ahmed"].blue_country, "Montenegro")

    def test_the_headline_and_the_body_disagree_and_the_read_says_so(self):
        """Headed European Championship; opens "The Combat World Championship"."""
        self.assertTrue(said(self.report, "world"))

    def test_a_contradicted_level_is_left_unstated_and_not_picked(self):
        """The page calls itself European once and World once. It has not said.

        Storing "european" off the headline would put a scope in the archive
        that this same document contradicts two lines later, and a reader
        cannot see which of the two the column came from.
        """
        self.assertEqual(self.t.level, "")
        self.assertEqual(self.report.notes["scope_claims"],
                         ["european", "world"])
        self.assertTrue(said(self.report, "does not settle which"))

    def test_a_manifest_that_settles_the_level_in_writing_still_wins(self):
        _t, _rows, report = read("cesav-combat-2016", "c16",
                                 {"level": "world"})
        self.assertEqual(_t.level, "world")
        self.assertTrue(said(report, "the manifest declares world"))

    def test_the_gender_column_says_it_came_from_the_class_code(self):
        self.assertIn("class code", self.report.notes["gender_from"])


class ThePro2024Article(unittest.TestCase):
    """Two belt bouts, the nation glued on with inconsistent hyphens."""

    def setUp(self):
        self.t, self.rows, self.report = read("cesav-pro-2024", "p24")

    def test_both_bouts_are_read(self):
        self.assertEqual(len(bouts(self.rows)), 2)

    def test_the_named_winner_is_matched_to_a_fighter_not_stored_as_text(self):
        first, second = bouts(self.rows)
        self.assertEqual((first.red, first.blue), ("Vincis Chiara",
                                                   "Buzuel Atef Maurine"))
        self.assertEqual(first.winner, "Buzuel Atef Maurine")
        self.assertEqual(first.loser, "Vincis Chiara")
        self.assertEqual((second.red, second.blue), ("Grdan Patric",
                                                     "Fabergas Damien"))
        self.assertEqual(second.winner, "Fabergas Damien")

    def test_a_name_run_together_with_its_hyphen_still_splits(self):
        """"Grdan Patric- CROATIE-" has no space before the first hyphen."""
        second = bouts(self.rows)[1]
        self.assertEqual(second.red_country, "Croatia")
        self.assertEqual(second.blue_country, "France")

    def test_an_unsigned_class_code_is_read_as_under_and_reported(self):
        first = bouts(self.rows)[0]
        self.assertEqual((first.weight_kg, first.weight_bound), ("60", "under"))
        self.assertEqual(first.gender, "Women")
        self.assertTrue(said(self.report, "print no sign"))

    def test_the_article_says_it_is_a_european_professional_belt(self):
        self.assertEqual(self.t.level, "european")
        self.assertEqual(self.t.format, "pro")
        self.assertEqual(self.t.year, "2024")


class TheQualifier2016Article(unittest.TestCase):
    """Eleven classes, a champion and a vice-champion in each."""

    def setUp(self):
        self.t, self.rows, self.report = read("cesav-qualifier-2016", "q16")

    def test_every_printed_placing_is_read(self):
        self.assertEqual(len(placings(self.rows)), 22)
        self.assertEqual(bouts(self.rows), [])

    def test_vice_champion_is_a_rank_and_not_a_missing_row(self):
        silver = [p for p in placings(self.rows) if p.rank == "2"]
        self.assertEqual(len(silver), 11)
        self.assertEqual({p.medal for p in silver}, {"silver"})

    def test_each_class_has_exactly_one_champion_and_one_runner_up(self):
        seen = {}
        for placing in placings(self.rows):
            seen.setdefault(placing.category, []).append(placing.rank)
        self.assertEqual(len(seen), 11)
        for category, ranks in seen.items():
            self.assertEqual(sorted(ranks), ["1", "2"], category)

    def test_the_nation_is_split_off_the_name_with_or_without_a_comma(self):
        by_name = {p.fighter: p for p in placings(self.rows)}
        # No comma on the page.
        self.assertEqual(by_name["PLACE Lorenzo"].country, "France")
        self.assertEqual(by_name["CAPUTI Léonardo"].country, "Italy")
        # Comma on the page.
        self.assertEqual(by_name["SHCHERBACHENKO Sergei"].country, "Russia")
        self.assertEqual(by_name["GEORGOPOYLOS Nikolaos"].country, "Greece")
        self.assertEqual(by_name["VUKOVIC Tijana"].country, "Serbia")

    def test_no_competitor_keeps_a_nation_inside_their_name(self):
        for placing in placings(self.rows):
            self.assertNotRegex(placing.fighter,
                                r"(?i)france|russia|italy|greece|serbia|"
                                r"croatia|ukraine")

    def test_the_junior_prefix_is_read_and_never_guessed_for_the_others(self):
        by_name = {p.fighter: p for p in placings(self.rows)}
        self.assertEqual(by_name["SHCHERBACHENKO Sergei"].age_class, "Junior")
        self.assertEqual(by_name["SHCHERBACHENKO Sergei"].category,
                         "Junior Men -60 kg")
        # "M-56" and "F-52" carry no age letter, so no age class is claimed.
        self.assertEqual(by_name["PLACE Lorenzo"].age_class, "")
        self.assertEqual(by_name["BOUYJOU Margot"].age_class, "")
        self.assertTrue(said(self.report, "some classes state an age class"))

    def test_the_open_class_is_read_as_over_and_not_as_under(self):
        by_name = {p.fighter: p for p in placings(self.rows)}
        champion = by_name["EDZOEV Tamerlan"]
        self.assertEqual(champion.weight_bound, "over")
        self.assertEqual(champion.weight_kg, "85")
        self.assertEqual(champion.category, "Junior Men +85 kg")

    def test_a_qualifying_tournament_is_not_filed_as_a_championship(self):
        """"The qualifying tournament of the 2016 European Championships".

        The word "Championships" in that sentence belongs to the competition
        this event qualifies *for*. FORMATS has no value for a qualifier, so
        the format stays empty rather than becoming the thing it is not.
        """
        self.assertEqual(self.t.format, "")
        self.assertEqual(self.report.notes["calls_itself"],
                         "a qualifying tournament")
        self.assertTrue(said(self.report, "qualifying tournament"))

    def test_a_manifest_that_declares_a_format_in_writing_still_wins(self):
        tournament, _rows, report = read("cesav-qualifier-2016", "q16",
                                         {"format": "open"})
        self.assertEqual(tournament.format, "open")
        self.assertTrue(said(report, "the manifest declares the format open"))

    def test_champion_is_a_position_and_the_read_does_not_call_it_a_medal(self):
        """The document prints "Champion" and "Vice-champion" and no medal.

        schema.check_placing requires medal to match rank, so the column is
        filled from schema.MEDALS - and the read says, in the report and in
        the notes, that this is the archive's mapping and not the document.
        """
        self.assertEqual(self.report.notes["rank_words"],
                         ["Champion", "Vice-champion"])
        self.assertIn("schema.MEDALS", self.report.notes["medal_from"])
        self.assertTrue(said(self.report, "never a medal"))
        self.assertTrue(said(self.report, "not a fact this document states"))

    def test_the_photo_credit_is_not_a_competitor(self):
        self.assertNotIn("Angélique Ansart",
                         {p.fighter for p in placings(self.rows)})


class TheHazards(unittest.TestCase):
    """The things a federation page does that a parser must refuse."""

    def setUp(self):
        self.t, self.rows, self.report = read("cesav-hazards", "hz")

    def test_a_demonstration_is_not_a_bout_and_is_counted(self):
        people = {b.red for b in bouts(self.rows)} | \
                 {b.blue for b in bouts(self.rows)}
        self.assertNotIn("Martin Paul", people)
        self.assertEqual(self.report.notes["demonstrations_excluded"], 1)

    def test_canne_de_combat_is_a_different_sport_and_is_dropped(self):
        people = {b.red for b in bouts(self.rows)} | \
                 {b.blue for b in bouts(self.rows)}
        self.assertNotIn("Petit Alain", people)
        self.assertEqual(self.report.notes["other_sport_rows_excluded"], 1)
        self.assertTrue(said(self.report, "another sport"))

    def test_a_line_pairing_one_person_with_themself_produces_no_row(self):
        self.assertNotIn("Meme Personne",
                         {b.red for b in bouts(self.rows)})
        self.assertTrue(said(self.report, "same person on both sides"))

    def test_a_winner_who_is_neither_fighter_leaves_the_bout_unresolved(self):
        odd = [b for b in bouts(self.rows) if b.red == "Bianchi Sara"]
        self.assertEqual(len(odd), 1)
        self.assertEqual(odd[0].status, "unresolved")
        self.assertEqual(odd[0].winner, "")
        self.assertEqual(odd[0].loser, "")
        self.assertEqual(odd[0].result_source, "")
        self.assertTrue(said(self.report, "neither fighter"))

    def test_savate_awards_two_bronzes_and_both_survive(self):
        bronze = [p for p in placings(self.rows) if p.rank == "3"]
        self.assertEqual(len(bronze), 2)
        self.assertEqual({p.fighter for p in bronze},
                         {"LEROY Paul", "NOVAK Luka"})
        self.assertEqual({p.category for p in bronze}, {"Men -75 kg"})

    def test_a_title_that_was_not_awarded_produces_no_competitor(self):
        self.assertNotIn("Titre non attribué",
                         {p.fighter for p in placings(self.rows)})
        self.assertTrue(said(self.report, "not awarded"))

    def test_a_superscript_ordinal_still_dates_the_bouts_below_it(self):
        """"1<sup>st</sup> June" arrives as two elements and one date."""
        self.assertEqual({b.date for b in bouts(self.rows)}, {"2019-06-01"})


class OneArticleUnderTwoURLs(unittest.TestCase):
    """Joomla routes /blog/<id>-<slug> on the id and throws the slug away.

    Checked against the live site, not assumed: these two URLs and an invented
    third, /blog/12-this-slug-is-nonsense, all return article 12 with a
    byte-identical article body. Reading both would have put the page's nine
    bouts into the archive as eighteen and given Berrou Alan two wins over
    Leskovic Luka in one year.
    """

    REAL = ("https://www.savate-europe.com/index.php/blog/"
            "12-europen-championship-combat-2016-results")
    ALIAS = ("https://www.savate-europe.com/index.php/blog/"
             "12-combat-european-championship-2016-results")

    def setUp(self):
        cesav_sheets.forget_documents()

    def tearDown(self):
        cesav_sheets.forget_documents()

    def test_the_slug_carries_no_identity_only_the_id_does(self):
        self.assertEqual(cesav_sheets.document_id(self.REAL),
                         "savate-europe.com#12")
        self.assertEqual(cesav_sheets.document_id(self.ALIAS),
                         cesav_sheets.document_id(self.REAL))
        self.assertEqual(cesav_sheets.document_id(
            "https://www.savate-europe.com/index.php/blog/"
            "12-this-slug-is-nonsense"), "savate-europe.com#12")
        self.assertNotEqual(cesav_sheets.document_id(
            "https://www.savate-europe.com/index.php/blog/20-qualifying"),
            cesav_sheets.document_id(self.REAL))

    def test_a_local_file_has_no_article_id_and_is_not_deduplicated(self):
        self.assertEqual(cesav_sheets.document_id("tests/fixtures/x.html"), "")
        self.assertEqual(cesav_sheets.document_id(""), "")

    def test_the_second_url_of_one_article_is_reported_as_the_same_article(self):
        first, second = Report(), Report()
        cesav_sheets.note_document(self.REAL, first)
        cesav_sheets.note_document(self.ALIAS, second)
        self.assertEqual(first.problems, [])
        self.assertTrue(said(second, "same article"))
        self.assertIn(self.REAL, second.problems[0])
        self.assertEqual(second.notes["document_id"], "savate-europe.com#12")

    def test_reading_one_url_twice_is_not_a_duplicate(self):
        """A re-read of the same URL is a re-read, not a second competition."""
        first, again = Report(), Report()
        cesav_sheets.note_document(self.REAL, first)
        cesav_sheets.note_document(self.REAL, again)
        self.assertEqual(again.problems, [])


class NothingComesOffTheURL(unittest.TestCase):
    """The slug is the URL's wording. The document is the document."""

    def test_the_year_and_name_come_from_the_headline_not_from_the_slug(self):
        tournament, _rows, _report = read(
            "cesav-combat-2016", "cesav-world-championship-1999")
        self.assertEqual(tournament.year, "2016")
        self.assertEqual(tournament.name,
                         "COMBAT EUROPEAN CHAMPIONSHIP 2016 -RESULTS")
        # The slug says a world championship in 1999. Only the slug does.
        self.assertEqual(tournament.level, "")
        carried = {field: value
                   for field, value in tournament.as_dict().items()
                   if field not in ("slug", "source") and "1999" in str(value)}
        self.assertEqual(carried, {})

    def test_a_page_with_no_headline_says_so_rather_than_reading_the_slug(self):
        tournament, _rows, report = read(
            "cesav-headless", "cesav-european-championship-2016")
        self.assertEqual(tournament.name, "")
        self.assertEqual(tournament.level, "")
        self.assertEqual(tournament.format, "")
        self.assertEqual(tournament.discipline, "")
        self.assertTrue(said(report, "no headline"))


class AnArticleThatIsNotResults(unittest.TestCase):
    def test_it_reports_rather_than_raising_or_inventing(self):
        _t, rows, report = read("cesav-not-results")
        self.assertEqual(rows, [])
        self.assertTrue(said(report, "may not be a results article"))


class ReadingTheClassCodes(unittest.TestCase):
    """The unit the whole adapter turns on."""

    def check(self, printed, weight, bound, gender, age=""):
        klass = cesav_sheets.read_class(printed)
        self.assertIsNotNone(klass, printed)
        self.assertEqual((klass.weight_kg, klass.weight_bound), (weight, bound))
        self.assertEqual(klass.gender, gender)
        self.assertEqual(klass.age_class, age)

    def test_the_codes_the_pages_print(self):
        self.check("M-65kg", "65", "under", "Men")
        self.check("F-48kg", "48", "under", "Women")
        self.check("JM+85", "85", "over", "Men", "Junior")
        self.check("F60", "60", "under", "Women")
        self.check("M-56", "56", "under", "Men")

    def test_a_band_is_the_class_ending_at_its_upper_figure(self):
        self.check("60-65 kg", "65", "under", "")

    def test_a_figure_no_savate_class_carries_is_left_without_a_weight(self):
        for printed in ("M150kg", "F100", "M15"):
            with self.subTest(printed=printed):
                klass = cesav_sheets.read_class(printed)
                self.assertFalse(klass.readable, printed)
                self.assertEqual(klass.weight_kg, "")
                self.assertEqual(klass.label, printed)

    def test_text_that_is_not_a_class_is_not_read_as_one(self):
        for printed in ("Champion : PLACE Lorenzo FRANCE", "Results:",
                        "8th October, Morbihan", "", "Photos"):
            with self.subTest(printed=printed):
                self.assertIsNone(cesav_sheets.read_class(printed))


class SplittingANationOffAName(unittest.TestCase):
    def test_the_longest_attested_spelling_wins(self):
        self.assertEqual(cesav_sheets.split_nation("PLACE Lorenzo FRANCE"),
                         ("PLACE Lorenzo", "France"))
        self.assertEqual(cesav_sheets.split_nation("SHVANEV Ilya, RUSSIA"),
                         ("SHVANEV Ilya", "Russia"))

    def test_a_name_with_no_nation_is_left_whole(self):
        self.assertEqual(cesav_sheets.split_nation("DUBOIS Marc"),
                         ("DUBOIS Marc", ""))


if __name__ == "__main__":
    unittest.main()
