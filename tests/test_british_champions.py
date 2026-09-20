"""The British championship adapter, against all ten GBSF pages.

The fixtures are the federation's own posts, cut down to the title, the heading
and the post body - which is every byte the adapter reads. All five of the
layouts savate.org.uk has used between 2012 and 2025 are here, and so is every
defect they carry, because the defects are what a parser gets wrong: a band
printed backwards, a full stop where a hyphen belongs, an age range missing, a
post titled with one month and dated with another, and four canne de combat
results sitting above the savate ones on the same page.

The assertions are about the things that would actually be wrong rather than
about row counts alone. An earlier adapter elsewhere in this archive reported
fifty-six bouts from a file it had mis-segmented entirely; rows appearing is not
evidence of anything. So these check that the champion and the vice-champion of
a class are two different people, that the trophy winners printed in the same
prose are not filed as champions, that the women's classes on a page whose
gender is carried by a bare header line are women's, that M85 and M85+ are two
classes and not one, and that no bronze exists anywhere - because the GBSF never
printed one and savate awards two.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import sources
from savate.adapters import british_champions
from savate.schema import Placing, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PAGES = ["britain-2012", "britain-2013", "britain-2015", "britain-2016",
         "britain-2017", "britain-2018", "britain-2019-junior",
         "britain-2019-senior", "britain-2024", "britain-2025"]


def read(stem, meta=None):
    return british_champions.read(str(FIXTURES / f"{stem}.html"), stem,
                                  meta or {})


def body(stem):
    page = sources.text(str(FIXTURES / f"{stem}.html"))
    return "\n".join(british_champions._plain(british_champions._entry(page)))


def podium(rows, category):
    return {p.rank: p.fighter for p in rows if p.category == category}


class EveryPage(unittest.TestCase):
    """What must hold of all ten documents, whatever shape they are in."""

    @classmethod
    def setUpClass(cls):
        cls.read = {stem: read(stem) for stem in PAGES}

    def test_every_placing_is_canonical(self):
        for stem, (_t, rows, _r) in self.read.items():
            complaints = [f"{stem}: {c}" for p in rows for c in check_placing(p)]
            self.assertEqual([], complaints)

    def test_nothing_but_placings_is_produced(self):
        # Not one British page says who fought whom, so no bout may be claimed.
        for stem, (_t, rows, _r) in self.read.items():
            self.assertTrue(all(isinstance(r, Placing) for r in rows), stem)
            self.assertIn("no bouts", " ".join(self.read[stem][2].problems))

    def test_no_bronze_is_ever_synthesised(self):
        # Savate awards two bronzes. These pages name none, so the archive
        # stores none - and says on every read that the podium is short.
        for stem, (_t, rows, report) in self.read.items():
            self.assertEqual({"1", "2"} | {p.rank for p in rows},
                             {"1", "2"}, stem)
            self.assertIn("two bronzes", " ".join(report.problems), stem)

    def test_every_fighter_is_printed_on_the_page(self):
        # A name the page does not contain is a name the adapter made up.
        for stem, (_t, rows, _r) in self.read.items():
            text = body(stem)
            for placing in rows:
                self.assertIn(placing.fighter, text, stem)
                if placing.club:
                    self.assertIn(placing.club, text, stem)

    def test_no_name_is_a_label_a_digit_or_a_role(self):
        for stem, (_t, rows, _r) in self.read.items():
            for placing in rows:
                self.assertNotRegex(placing.fighter, r"(?i)champion|winner|kg")
                self.assertFalse(any(c.isdigit() for c in placing.fighter), stem)
                self.assertGreaterEqual(len(placing.fighter), 3)

    def test_a_class_never_holds_one_person_twice(self):
        # The champion and the vice-champion of a weight class are two people.
        for stem, (_t, rows, _r) in self.read.items():
            by_class = {}
            for placing in rows:
                by_class.setdefault(placing.category, []).append(placing.fighter)
            for category, names in by_class.items():
                self.assertEqual(len(names), len(set(names)),
                                 f"{stem}: {category} {names}")

    def test_a_class_never_holds_both_genders(self):
        for stem, (_t, rows, _r) in self.read.items():
            by_class = {}
            for placing in rows:
                by_class.setdefault(placing.category, set()).add(placing.gender)
            for category, genders in by_class.items():
                self.assertEqual(1, len(genders), f"{stem}: {category}")

    def test_a_class_never_holds_two_champions(self):
        for stem, (_t, rows, _r) in self.read.items():
            seen = [(p.category, p.rank) for p in rows]
            self.assertEqual(len(seen), len(set(seen)), stem)

    def test_nationality_is_never_assumed_from_the_championship(self):
        # A British championship is not a statement that its entrants are
        # British - the 2025 women's champion fights out of a club called
        # Formosa - and these pages never print a nationality.
        for stem, (_t, rows, _r) in self.read.items():
            self.assertEqual({""}, {p.country for p in rows} or {""}, stem)

    def test_the_publishers_masthead_is_not_read_as_the_events_country(self):
        # REGRESSION. Every tournament used to come back country="Great
        # Britain", matched off "Great Britain Savate Federation" - which is
        # on every capture and on none of them inside the post. It is the
        # <title> suffix, the RSS link titles, the logo's aria-label and the
        # footer: the publisher's name, not where anybody fought.
        for stem, (tournament, _rows, _r) in self.read.items():
            page = sources.text(str(FIXTURES / f"{stem}.html"))
            self.assertRegex(page, r"(?i)great\s+britain\s+savate")   # it is there
            self.assertNotRegex(body(stem), r"(?i)great\s+britain\s+savate")
            self.assertEqual("", tournament.country, stem)

    def test_the_one_page_that_places_the_event_places_it_outside_britain(self):
        # REGRESSION, and the sharpest case: the 2019 junior post opens
        # "Savate Northern Ireland hosted this year's Junior Assaut
        # Championships". Northern Ireland is in the UK and not in Great
        # Britain, so the masthead reading contradicted the document itself.
        tournament, _rows, _r = self.read["britain-2019-junior"]
        self.assertIn("Savate Northern Ireland", body("britain-2019-junior"))
        self.assertEqual("", tournament.country)

    def test_the_whole_series_is_read(self):
        counts = {stem: len(rows) for stem, (_t, rows, _r) in self.read.items()}
        self.assertEqual(
            {"britain-2012": 5, "britain-2013": 5, "britain-2015": 12,
             "britain-2016": 7, "britain-2017": 14, "britain-2018": 38,
             "britain-2019-junior": 20, "britain-2019-senior": 12,
             "britain-2024": 18, "britain-2025": 10}, counts)


class CanneDeCombat(unittest.TestCase):
    """The 2019 senior page publishes two sports. Only one of them is savate."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2019-senior")

    def test_the_canne_results_never_become_savate_rows(self):
        cannists = {"Morgan Alexander", "Anna Makinen", "Stuart McIntyre",
                    "James Blackman"}
        self.assertEqual(set(), cannists & {p.fighter for p in self.rows})

    def test_the_drop_is_counted_and_reported(self):
        self.assertEqual(4, self.report.notes["other_sport_rows_dropped"])
        self.assertIn("non-savate", " ".join(self.report.problems))

    def test_no_category_names_another_sport(self):
        for placing in self.rows:
            self.assertNotRegex(placing.category, r"(?i)canne|baton|chausson")

    def test_the_savate_podium_below_it_is_read_whole(self):
        self.assertEqual(12, len(self.rows))
        self.assertEqual({"1": "Alyson Sinyard", "2": "Louisa Furniss"},
                         podium(self.rows, "Senior Women -56 kg"))
        self.assertEqual({"1": "Tom Handley", "2": "Judah Wheeler"},
                         podium(self.rows, "Senior Men +85 kg"))

    def test_the_age_class_the_title_states_reaches_the_rows(self):
        self.assertEqual("Senior", self.tournament.age_class)
        self.assertEqual({"Senior"}, {p.age_class for p in self.rows})


class SeparateMedalLists(unittest.TestCase):
    """2015 prints its champions and its vice-champions as two lists.

    The class code is the only thing joining them, and two of the codes are one
    character apart: M85 and M85+ are different classes, and a prefix match on
    "M85" would hand the heavyweight title to the wrong man.
    """

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2015")

    def test_both_lists_are_read(self):
        self.assertEqual({"1", "2"}, {p.rank for p in self.rows})
        self.assertEqual(6, len({p.category for p in self.rows}))

    def test_m85_and_m85_plus_stay_two_classes(self):
        self.assertEqual({"1": "Kalle Heinola", "2": "Jasbir Nagi"},
                         podium(self.rows, "Men -85 kg"))
        self.assertEqual({"1": "Judah Wheeler", "2": "Tom Handley"},
                         podium(self.rows, "Men +85 kg"))

    def test_the_bound_is_read_off_the_code(self):
        under = next(p for p in self.rows if p.category == "Men -85 kg")
        over = next(p for p in self.rows if p.category == "Men +85 kg")
        self.assertEqual(("85", "under"), (under.weight_kg, under.weight_bound))
        self.assertEqual(("85", "over"), (over.weight_kg, over.weight_bound))

    def test_the_clubs_come_off_the_names(self):
        champion = next(p for p in self.rows
                        if p.fighter == "Emmanuel Roux")
        self.assertEqual("London", champion.club)


class GenderCarriedByAHeader(unittest.TestCase):
    """2016 states the gender once, in a bare header line, and never again.

    Losing it files women in the men's classes, which is the mis-segmentation
    this archive's probe exists to catch.
    """

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2016")

    def test_the_header_carries_down_its_own_lines_and_no_further(self):
        women = {p.fighter for p in self.rows if p.gender == "Women"}
        self.assertEqual({"Nathalie Chaar", "Morgan Alexander"}, women)
        self.assertEqual(5, sum(1 for p in self.rows if p.gender == "Men"))

    def test_the_page_is_gold_only_and_says_so(self):
        self.assertEqual({"1"}, {p.rank for p in self.rows})
        self.assertEqual(7, len(self.report.notes["gold_only_classes"]))

    def test_the_best_fight_of_the_day_is_not_a_bout(self):
        # "James Antill/Nicholas Gowron" is a compliment, not a result.
        self.assertNotIn("Nicholas Gowron", {p.fighter for p in self.rows})


class BothMedallistsOnOneLine(unittest.TestCase):
    """2018, the largest page: nineteen classes, seniors and juniors together."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2018")

    def test_every_class_is_read(self):
        self.assertEqual(19, len({p.category for p in self.rows}))
        self.assertEqual(38, len(self.rows))

    def test_the_section_headers_give_each_row_its_age_class(self):
        self.assertEqual(9, len({p.category for p in self.rows
                                 if p.age_class == "Senior"}))
        self.assertEqual(10, len({p.category for p in self.rows
                                  if p.age_class == "Junior"}))

    def test_the_comma_between_the_two_medallists_is_not_read_into_a_name(self):
        self.assertEqual({"1": "Alice Zebboudj", "2": "Ally Sinyard"},
                         podium(self.rows, "Senior Women -52 kg"))

    def test_vice_champion_is_read_with_or_without_its_hyphen(self):
        self.assertEqual({"1": "Caitlin Dunlop", "2": "Amina Miah"},
                         podium(self.rows, "Junior Women 8-10 yrs -45 kg"))

    def test_the_trophy_and_the_commendations_are_not_podium_rows(self):
        names = [p.fighter for p in self.rows]
        self.assertNotIn("Theo Pottier", names)
        self.assertNotIn("Ubaid Raja", names)
        # The trophy winner is a champion, but of one class and once only.
        self.assertEqual(1, names.count("Darryll Walker"))
        self.assertEqual({"1": "Darryll Walker", "2": "Lee Curtis"},
                         podium(self.rows, "Junior Men 11-15 yrs -56 kg"))

    def test_a_band_printed_backwards_yields_no_weight_and_is_reported(self):
        # "Male 80-65kg" sits between 75-80 and 85+ and is plainly meant to be
        # 80-85. The document is not corrected: the class keeps the federation's
        # own wording and carries no weight at all.
        rows = [p for p in self.rows if "80-65" in p.category]
        self.assertEqual(2, len(rows))
        self.assertEqual("Senior Men 80-65kg", rows[0].category)
        self.assertEqual("", rows[0].weight_kg)
        self.assertEqual("", rows[0].weight_bound)
        self.assertIn("80-65kg", " ".join(self.report.problems))
        self.assertEqual({"1": "Judah Wheeler", "2": "Sam Byford-Winter"},
                         podium(self.rows, "Senior Men 80-65kg"))


class AgeRangesInTheCategory(unittest.TestCase):
    """2019's juniors, where the class carries an age range as well as a weight."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2019-junior")

    def test_the_age_range_stays_with_the_class(self):
        self.assertIn("Junior Men 10-11 yrs -39 kg",
                      {p.category for p in self.rows})
        self.assertIn("Junior Men 12-13 yrs -60 kg",
                      {p.category for p in self.rows})

    def test_two_classes_at_the_same_weight_stay_apart(self):
        # 10-11yrs <60kg and 12-13yrs <60kg are different championships.
        sixty = {p.category for p in self.rows if p.weight_kg == "60"}
        self.assertEqual({"Junior Men 10-11 yrs -60 kg",
                          "Junior Men 12-13 yrs -60 kg"}, sixty)

    def test_a_missing_age_range_is_reported_and_not_invented(self):
        # The page prints "Female yrs, 22-24kg" with no ages at all.
        rows = [p for p in self.rows if p.fighter == "Rebecca Coyle"]
        self.assertEqual(1, len(rows))
        self.assertEqual("Junior Women -24 kg", rows[0].category)
        self.assertIn("age range is missing", " ".join(self.report.problems))

    def test_the_cup_winners_above_the_results_are_not_champions(self):
        # "Best Over 10 Fighter : Ryan Mc Court" has the same shape as a result.
        names = [p.fighter for p in self.rows]
        self.assertEqual(1, names.count("Ryan McCourt"))
        self.assertNotIn("Ryan Mc Court", names)
        self.assertEqual({"1": "Oran Denvir", "2": "Ryan McCourt"},
                         podium(self.rows, "Junior Men 10-11 yrs -39 kg"))
        self.assertEqual(1, names.count("Corey McCullogh"))
        self.assertEqual("2", next(p.rank for p in self.rows
                                   if p.fighter == "Corey McCullogh"))


class TheNameOnTheNextLine(unittest.TestCase):
    """2012, the oldest British result: a class, then an en-dash, then a name."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2012")

    def test_the_en_dash_lines_are_read(self):
        self.assertEqual(5, len(self.rows))
        self.assertEqual({"1"}, {p.rank for p in self.rows})
        self.assertIn("Sian-Marie Clark", {p.fighter for p in self.rows})

    def test_a_full_stop_where_a_band_belongs_yields_no_weight(self):
        # "Female 52.56kg" is plainly 52-56kg, and is not repaired into one.
        row = next(p for p in self.rows if p.fighter == "Sian-Marie Clark")
        self.assertEqual("Women 52.56kg", row.category)
        self.assertEqual("", row.weight_kg)
        self.assertEqual("Women", row.gender)
        self.assertIn("full stop", " ".join(self.report.problems))

    def test_the_canne_display_is_noted_and_produces_nothing(self):
        # The day included a canne de combat DISPLAY, which is not a contest.
        self.assertEqual(0, self.report.notes["demonstration_rows_dropped"])
        self.assertIn("Canne de Combat",
                      " ".join(self.report.notes["other_sport_mentioned"]))
        self.assertNotIn("Jon West", {p.fighter for p in self.rows})


class ADocumentThatContradictsItself(unittest.TestCase):
    """2013 is titled July and dated 30th January in its own first sentence."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("britain-2013")

    def test_neither_date_is_chosen(self):
        self.assertEqual("", self.tournament.start_date)
        self.assertIn("disagree", " ".join(self.report.problems))

    def test_the_year_both_readings_agree_on_is_kept(self):
        self.assertEqual("2013", self.tournament.year)

    def test_the_gender_printed_after_the_class_is_read(self):
        # "65-70kg Male: Tim Campbell (Cambridge)".
        self.assertEqual({"Men"}, {p.gender for p in self.rows})
        row = next(p for p in self.rows if p.fighter == "Tim Campbell")
        self.assertEqual(("70", "under", "Cambridge"),
                         (row.weight_kg, row.weight_bound, row.club))


class TheTables(unittest.TestCase):
    """2024 and 2025 print a real four-column table."""

    def test_the_age_column_gives_each_row_its_age_class(self):
        _t, rows, _r = read("britain-2024")
        ages = {p.category: p.age_class for p in rows}
        self.assertEqual("Benjamin", ages["Benjamin Men -48 kg"])
        self.assertEqual("Cadet", ages["Cadet Men -48 kg"])
        self.assertEqual("Junior", ages["Junior Men -65 kg"])
        self.assertEqual("Senior", ages["Senior Men -70 kg"])

    def test_two_age_classes_at_one_weight_stay_apart(self):
        _t, rows, _r = read("britain-2024")
        self.assertEqual({"1": "Sonny Byford-Winter", "2": "Oren Yuchatel"},
                         podium(rows, "Benjamin Men -48 kg"))
        self.assertEqual({"1": "Friedemann Waldert", "2": "Ellis Rhodes"},
                         podium(rows, "Cadet Men -48 kg"))

    def test_the_club_is_split_off_the_name_in_the_cell(self):
        _t, rows, _r = read("britain-2025")
        champion = next(p for p in rows if p.rank == "1"
                        and p.gender == "Women")
        self.assertEqual("Heiman Yuan", champion.fighter)
        self.assertEqual("Formosa", champion.club)

    def test_the_award_printed_under_the_table_is_not_a_result(self):
        _t, rows, _r = read("britain-2025")
        names = {p.fighter for p in rows}
        self.assertNotIn("Friedemann Waldert", names)
        self.assertNotIn("Louisa Furniss", names)

    def test_a_year_with_no_womens_class_is_not_a_failure(self):
        _t, rows, _r = read("britain-2024")
        self.assertEqual({"Men"}, {p.gender for p in rows})
        self.assertEqual(18, len(rows))


class TheClassNobodyExplains(unittest.TestCase):
    """M150: a code above every weight savate fights, and above every reading.

    It is printed at the top of the men's ladder on three pages, which makes
    the open class the obvious guess - and the adapter used to make it, filing
    the class as "open" with weight_bound="over". Neither word is printed
    anywhere on those pages. If the 150 were ever pounds it would be 68 kg,
    two classes below where the guess puts it. So it is read the way the
    backwards band and the full-stop band are read: not at all.
    """

    PAGES_WITH_M150 = {"britain-2025": "Senior Men M150",
                       "britain-2024": "Senior Men M150",
                       "britain-2017": "Men M150"}

    def test_the_word_open_is_on_none_of_the_pages_that_print_m150(self):
        # REGRESSION. The whole defect in one assertion: a label the document
        # does not contain cannot be a reading of it.
        for stem in self.PAGES_WITH_M150:
            self.assertNotRegex(body(stem), r"(?i)\bopen\b", stem)

    def test_the_federation_writes_open_when_it_means_open(self):
        # And this is why the guess cannot be waved through. The GBSF does use
        # the word - "the Seniors fighting in the Open", 2019 junior page - so
        # its absence beside M150 on three other pages is the federation not
        # saying it, not the federation abbreviating it.
        self.assertRegex(body("britain-2019-junior"), r"(?i)\bOpen\b")
        self.assertNotIn("M150", body("britain-2019-junior"))

    def test_no_row_anywhere_is_filed_as_an_open_class(self):
        # REGRESSION.
        for stem in PAGES:
            _t, rows, _r = read(stem)
            self.assertEqual([], [p.category for p in rows
                                  if "open" in p.category.lower()], stem)

    def test_m150_keeps_the_printed_token_and_carries_no_weight_or_bound(self):
        # REGRESSION. The label is the federation's own token, exactly as it
        # already was for 2018's "80-65kg" and 2012's "52.56kg".
        for stem, label in self.PAGES_WITH_M150.items():
            _t, rows, report = read(stem)
            m150 = [p for p in rows if p.category == label]
            self.assertEqual(2, len(m150), stem)
            for placing in m150:
                self.assertEqual("", placing.weight_kg, stem)
                self.assertEqual("", placing.weight_bound, stem)
            self.assertIn("M150", " ".join(report.problems), stem)

    def test_the_unread_class_is_reported_rather_than_passed_over(self):
        # Reporting it is the other half: a reader has to be able to see that
        # the archive could not read the class, not merely that it is blank.
        for stem in self.PAGES_WITH_M150:
            _t, _rows, report = read(stem)
            said = " ".join(report.problems)
            self.assertIn("above every weight savate fights", said, stem)
            self.assertIn("no weight class and no bound were read", said, stem)

    def test_it_is_not_collapsed_into_the_85_kg_class(self):
        _t, rows, _r = read("britain-2017")
        self.assertEqual({"1": "Judah Wheeler", "2": "Tom Handley"},
                         podium(rows, "Men M150"))
        self.assertEqual({"1": "Kalle Heinola", "2": "Jon Schwochert"},
                         podium(rows, "Men -85 kg"))

    def test_the_medallists_are_still_read(self):
        # Refusing the class is not refusing the people in it. All six rows
        # stay, with their names, clubs and ranks.
        _t, rows, _r = read("britain-2025")
        self.assertEqual({"1": "Tom Handley", "2": "Steven Chahar"},
                         podium(rows, "Senior Men M150"))
        _t, rows, _r = read("britain-2024")
        self.assertEqual({"1": "Sam Byford-Winter", "2": "Tom Handley"},
                         podium(rows, "Senior Men M150"))

    def test_a_real_heavyweight_code_is_still_read_as_a_weight(self):
        # The fix must not swallow the class above it: M85 and M85+ are real
        # savate weights and are read as they always were.
        _t, rows, _r = read("britain-2015")
        eighty_five = next(p for p in rows if p.category == "Men -85 kg")
        over = next(p for p in rows if p.category == "Men +85 kg")
        self.assertEqual(("85", "under"),
                         (eighty_five.weight_kg, eighty_five.weight_bound))
        self.assertEqual(("85", "over"), (over.weight_kg, over.weight_bound))


class BadInput(unittest.TestCase):
    """Bad data is a Report and a skipped row. It is never an exception."""

    def test_a_page_with_no_results_reads_empty_and_complains(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("<html><body><div class='entry-content'>"
                         "<p>The committee met on Tuesday.</p>"
                         "</div></body></html>")
            path = handle.name
        _t, rows, report = british_champions.read(path, "nothing", {})
        self.assertEqual([], rows)
        self.assertIn("no podium rows read", " ".join(report.problems))

    def test_a_document_that_is_not_a_page_is_refused_not_misread(self):
        pdf = FIXTURES / "fisav-world-assaut-2024.pdf"
        if not pdf.exists():
            self.skipTest("the PDF fixture is not present")
        _t, rows, report = british_champions.read(str(pdf), "pdf", {})
        self.assertEqual([], rows)
        self.assertIn("not an HTML page", " ".join(report.problems))

    def test_a_missing_source_is_the_one_thing_that_raises(self):
        with self.assertRaises(FileNotFoundError):
            british_champions.read("no/such/page.html", "missing", {})


if __name__ == "__main__":
    unittest.main()
