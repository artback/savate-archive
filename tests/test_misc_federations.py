"""The one-off federation pages, against the bytes the federations published.

Six fixtures, and five of them are real. `misc-croatia-2025.html` is the news
paragraph off the Hrvatski savate savez homepage, `misc-canada-champions.html`
the three season blocks off Savate Canada's Weebly page, `misc-turkey-2025.html`
the GOSBF article with the Word markup that split every name from its weight
still in it, `misc-guadeloupe-wix.html` the Ricos body of a live lgsbfda.net
post, and `misc-ukraine-bundle.js` three articles lifted verbatim out of the
JavaScript bundle savate.org.ua serves instead of pages. Every defect those
documents carry is in the fixtures, because the defects are what a parser gets
wrong: a date range whose tail looks like a date, a duplicated club token, a
championship title with another competition's placing bolted on after a comma,
a sentence whose winner wrapped onto the next paragraph, and a medal list with
no weight classes at all.

The three synthetic fixtures are named as such - `misc-hazards-croatia`,
`misc-hazards-delegation` and `misc-not-results`. No federation published them;
they exist because none of the six real documents happens to mix canne de
combat or a demonstration into its results, and a guard that is never exercised
is a guard nobody knows is broken.

What is asserted is what would actually be wrong. Rows appearing is not
evidence of anything: these check that the winner of a bout is one of the two
people in it, that the one Croatian line whose verdict reads PORAZ does not make
the Croatian a world champion, that the finals are dated from the line that says
the finals were held rather than from the qualifying round printed above it,
that the Guadeloupe sentence whose last two words are the next paragraph is
closed up and read from that text, that two bouts in the same weight class both
survive, that no corner is ever claimed, and that a page which is none of these
four yields nothing.

Four of these are regression tests and say so in the body. Each names a value
that used to be in a row and is not printed in the document: a HOST nation on a
visiting delegation (Croatia, Turkey and Ukraine - the serious one, because the
truthful value for a competition's country is exactly what poisoned it), three
national championships merged into one so that a weight class had three
champions (Canada), a gender expanded out of the class letter in "M75" on a
page that prints no word for one (Guadeloupe), and two bounds - a band and a
bare figure - read as classes with nothing in the report saying the page
printed no sign.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import misc_federations as misc
from savate.schema import Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(stem, slug, meta=None, **options):
    suffix = ".js" if stem.endswith("bundle") else ".html"
    return misc.read(str(FIXTURES / f"{stem}{suffix}"), slug, meta or {},
                     **options)


def canonical(case, rows):
    return [f"{case}: {c}" for row in rows
            for c in (check(row) if isinstance(row, Bout)
                      else check_placing(row))]


class Croatia(unittest.TestCase):
    """The world combat championship finals, Split, 3 October 2025."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "misc-croatia-2025", "hr-finals",
            {"country": "Croatia", "discipline": "combat", "city": "Split"},
            home_country="Croatia")

    def test_every_bout_is_canonical(self):
        self.assertEqual([], canonical("croatia", self.rows))

    def test_the_six_finals_the_page_prints(self):
        self.assertEqual(6, len(self.rows))
        self.assertTrue(all(isinstance(r, Bout) for r in self.rows))

    def test_the_winner_is_one_of_the_two_fighters(self):
        for bout in self.rows:
            if bout.winner:
                self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)
                self.assertNotEqual(bout.red, bout.blue, bout.bout_id)

    def test_poraz_gives_the_bout_to_the_opponent(self):
        # The one line in six where the Croatian lost. Reading the order
        # instead of the verdict would make Antonija Zec a world champion.
        zec = next(b for b in self.rows if b.red == "ANTONIJA ZEC")
        self.assertEqual("MAIMARA LAWSON", zec.winner)
        self.assertEqual("ANTONIJA ZEC", zec.loser)

    def test_pobjeda_gives_the_bout_to_the_croatian(self):
        lalic = next(b for b in self.rows if b.red == "LEE LALIĆ")
        self.assertEqual("LEE LALIĆ", lalic.winner)
        self.assertEqual("CHLOE NANDI", lalic.loser)

    def test_no_corner_is_ever_claimed(self):
        self.assertEqual({""}, {b.winner_corner for b in self.rows})

    def test_no_gender_is_invented(self):
        # Four of these are the women's classes and two the men's. The page
        # does not say so, and neither does this adapter.
        self.assertEqual({""}, {b.gender for b in self.rows})

    def test_the_open_class_is_the_only_one_printed_over(self):
        bounds = {b.weight_kg: b.weight_bound for b in self.rows}
        self.assertEqual("over", bounds["85"] if "85" in bounds else
                         bounds["75"])
        self.assertEqual("under", bounds["52"])
        self.assertTrue(any("without a sign" in p for p in
                            self.report.problems))

    def test_both_bouts_at_seventy_kilos_survive(self):
        # Two different finals at -70 kg. Neither is a duplicate of the other.
        at_seventy = [b for b in self.rows if b.weight_kg == "70"]
        self.assertEqual(2, len(at_seventy))
        self.assertEqual({"ANTONIJA ZEC", "PATRIK GRĐAN"},
                         {b.red for b in at_seventy})

    def test_the_date_is_the_finals_and_not_the_qualifiers(self):
        # The paragraph above carries "02.-06.07.2025" for the qualifying
        # round in Bulgaria. Taking the tail of that range would date these
        # six finals to the wrong country and the wrong quarter.
        self.assertEqual("2025-10-03", self.tournament.start_date)
        self.assertEqual({"2025-10-03"}, {b.date for b in self.rows})

    def test_the_nation_printed_is_the_opponents(self):
        nations = {b.red: b.blue_country for b in self.rows}
        self.assertEqual("France", nations["LEE LALIĆ"])
        self.assertEqual("Italy", nations["KATARINA KLARIĆ"])
        self.assertEqual("Tunisia", nations["PATRIK GRĐAN"])
        self.assertEqual({"Croatia"}, {b.red_country for b in self.rows})

    def test_the_phase_is_read_from_the_page(self):
        self.assertEqual({"final"}, {b.phase for b in self.rows})

    def test_no_nation_is_borrowed_from_the_host(self):
        # REGRESSION: `_home` used to fall back to the competition's own
        # country, which is where the meet was HELD. Here the two happen to be
        # Croatia, so the borrowed value looked right; on an away meet it puts
        # the host's flag on a visiting team. An entry that does not name the
        # delegation gets no nation at all.
        _t, rows, _r = read("misc-croatia-2025", "hr-finals",
                            {"country": "Croatia", "city": "Split"})
        self.assertEqual({""}, {b.red_country for b in rows})
        self.assertEqual({"France", "Italy", "Tunisia"},
                         {b.blue_country for b in rows})


class Canada(unittest.TestCase):
    """Three national championships on one Weebly page, 2013-2015."""

    def test_naming_a_season_reads_only_that_season(self):
        for year, expected in (("2015", 4), ("2014", 6), ("2013", 7)):
            _t, rows, _r = read("misc-canada-champions", f"ca-{year}",
                                {"country": "Canada"}, event=year)
            self.assertEqual(expected, len(rows), year)
            self.assertEqual([], canonical(year, rows))

    def test_naming_no_season_reads_nothing_rather_than_merging_three(self):
        # REGRESSION: all 17 champions used to come back under one slug. A
        # placing carries no season, so that is one championship with three
        # gold medallists at -65 kg and Joseph Zefrani champion in two weight
        # classes at once - every row faithful, the competition imaginary.
        _t, rows, report = read("misc-canada-champions", "ca-all",
                                {"country": "Canada"})
        self.assertEqual([], rows)
        self.assertTrue(any("3 separate national championships" in p
                            for p in report.problems))

    def test_no_class_has_two_champions_and_no_champion_two_classes(self):
        # The shape the merge produced, asserted directly: read season by
        # season, each class has one champion and each champion one class.
        for year in ("2013", "2014", "2015"):
            _t, rows, _r = read("misc-canada-champions", f"ca-{year}",
                                {"country": "Canada"}, event=year)
            classes = [(p.gender, p.weight_kg, p.weight_bound) for p in rows]
            self.assertEqual(len(classes), len(set(classes)), year)
            names = [p.fighter for p in rows]
            self.assertEqual(len(names), len(set(names)), year)

    def test_a_printed_band_is_disclosed_as_one(self):
        # REGRESSION: "48-52 kg" became weight_kg="52", weight_bound="under"
        # with nothing in the report saying the page printed neither a sign nor
        # a lower bound that survives.
        _t, rows, report = read("misc-canada-champions", "ca-2015",
                                {"country": "Canada"}, event="2015")
        self.assertTrue(rows)
        band = next(p for p in report.problems if "band" in p)
        self.assertIn("48-52 kg", band)
        self.assertIn("60-65 kg", band)

    def test_no_nationality_is_read_out_of_a_title(self):
        # "champion canadien" names a Canadian TITLE. Whether the holder is
        # Canadian is a different fact and this page never states it.
        _t, rows, _r = read("misc-canada-champions", "ca-2015",
                            {"country": "Canada"}, event="2015")
        self.assertEqual({""}, {p.country for p in rows})

    def test_gender_is_read_from_the_french_inflection(self):
        _t, rows, _r = read("misc-canada-champions", "ca-2015",
                            {"country": "Canada"}, event="2015")
        by_name = {p.fighter: p for p in rows}
        self.assertEqual("Women", by_name["Sherin Al-Safadi"].gender)
        self.assertEqual("Men", by_name["Simon Maspero"].gender)

    def test_a_band_is_the_class_it_ends_at(self):
        _t, rows, _r = read("misc-canada-champions", "ca-2015",
                            {"country": "Canada"}, event="2015")
        by_name = {p.fighter: p for p in rows}
        self.assertEqual(("52", "under"),
                         (by_name["Sherin Al-Safadi"].weight_kg,
                          by_name["Sherin Al-Safadi"].weight_bound))
        self.assertEqual(("85", "over"),
                         (by_name["Malik"].weight_kg,
                          by_name["Malik"].weight_bound))

    def test_the_two_spellings_of_the_open_class_are_one_class(self):
        # 2015 prints "+ 85 kg" and 2013 prints "85 et + kg".
        _t, rows, _r = read("misc-canada-champions", "ca-2013",
                            {"country": "Canada"}, event="2013")
        lemieux = next(p for p in rows if p.fighter == "Jonathan Lemieux")
        self.assertEqual(("85", "over"),
                         (lemieux.weight_kg, lemieux.weight_bound))

    def test_a_second_competitions_placing_is_not_filed_here(self):
        # "championne canadienne, 3e au World Combat Game" is one champion and
        # one result from a different competition, not two rows.
        _t, rows, report = read("misc-canada-champions", "ca-2013",
                                {"country": "Canada"}, event="2013")
        couture = [p for p in rows if p.fighter == "Lydia Couture"]
        self.assertEqual(1, len(couture))
        self.assertEqual("1", couture[0].rank)
        self.assertTrue(any("World Combat Game" in p for p in report.problems))

    def test_the_page_is_champions_only(self):
        _t, rows, report = read("misc-canada-champions", "ca-2014",
                                {"country": "Canada"}, event="2014")
        self.assertEqual({"1"}, {p.rank for p in rows})
        self.assertEqual({"gold"}, {p.medal for p in rows})
        self.assertTrue(any("champions only" in p for p in report.problems))

    def test_a_damaged_club_is_kept_as_printed(self):
        # "Club: L'EscouadeEscouade". The archive stores what the source
        # printed; repairing it here would hide that the page is damaged.
        _t, rows, _r = read("misc-canada-champions", "ca-2014",
                            {"country": "Canada"}, event="2014")
        zefrani = next(p for p in rows if p.fighter == "Joseph Zefrani")
        self.assertEqual("L'EscouadeEscouade", zefrani.club)


class Turkey(unittest.TestCase):
    """GOSBF's delegation report from Tashkent, July 2025."""

    @classmethod
    def setUpClass(cls):
        # The meet was in Tashkent, so "Uzbekistan" is the TRUTHFUL value for
        # this competition's country - and the one that used to be copied onto
        # twelve Turkish juniors.
        cls.tournament, cls.rows, cls.report = read(
            "misc-turkey-2025", "tr-tashkent",
            {"country": "Uzbekistan", "city": "Tashkent"})

    def test_every_placing_is_canonical(self):
        self.assertEqual([], canonical("turkey", self.rows))

    def test_the_tally_matches_the_articles_own_count(self):
        # The prose says "2 Altın, 7 Gümüş Ve 3 Bronz Madalya ... toplamda 12".
        medals = [p.rank for p in self.rows]
        self.assertEqual(12, len(medals))
        self.assertEqual(2, medals.count("1"))
        self.assertEqual(7, medals.count("2"))
        self.assertEqual(3, medals.count("3"))

    def test_the_name_is_rejoined_to_its_weight(self):
        # Word put the name in one <span> and the weight in the next. Read
        # naively they land on separate lines and every medal loses its class.
        by_name = {p.fighter: p for p in self.rows}
        self.assertEqual("85", by_name["Efe Ercan Boğaz"].weight_kg)
        self.assertEqual("48", by_name["Azra Bulut"].weight_kg)
        self.assertEqual("54", by_name["Nursultan Özdoğan"].weight_kg)
        self.assertEqual([], [p.fighter for p in self.rows if not p.weight_kg])

    def test_the_open_class_keeps_its_sign(self):
        ozkan = next(p for p in self.rows if p.fighter == "Kerem Özkan")
        self.assertEqual(("85", "over", "3"),
                         (ozkan.weight_kg, ozkan.weight_bound, ozkan.rank))

    def test_no_gender_is_inferred_from_a_given_name(self):
        self.assertEqual({""}, {p.gender for p in self.rows})

    def test_the_bracketed_tier_is_reported(self):
        # "Dünya Şampiyonlarımız (World Cup Kategorisi)" says the gold tier
        # belongs to one of the meet's two competitions and the other tiers
        # do not say which. That is the reason this page is a cross-check and
        # not a source, and the read has to surface it.
        self.assertTrue(any("World Cup Kategorisi" in p
                            for p in self.report.problems))

    def test_it_says_it_is_one_delegations_medals(self):
        self.assertTrue(any("one delegation" in p
                            for p in self.report.problems))

    def test_the_host_nation_is_never_stamped_on_the_delegation(self):
        # REGRESSION: `_home` fell back to the competition's country, so every
        # one of these Turkish medallists came back Uzbek - under a report that
        # said the page stated it collectively. The page says "Millilerimiz",
        # our nationals, and says the meet was in Tashkent.
        self.assertEqual({""}, {p.country for p in self.rows})
        self.assertFalse(any("Uzbekistan" in p for p in self.report.problems))

    def test_a_named_delegation_is_still_put_on_the_rows(self):
        _t, rows, report = read("misc-turkey-2025", "tr-tashkent",
                                {"country": "Uzbekistan"},
                                home_country="Turkey")
        self.assertEqual({"Turkey"}, {p.country for p in rows})
        self.assertTrue(any("filed as Turkey's" in p for p in report.problems))

    def test_a_weight_with_no_sign_is_disclosed(self):
        # REGRESSION: "Efe Ercan Boğaz – 85 kg" became weight_bound="under"
        # with nothing said about it, while the Croatian reader on the same
        # page shape did say so. Eleven of the twelve rows.
        unsigned = next(p for p in self.report.problems
                        if "without a sign" in p)
        self.assertIn("11 medallist", unsigned)
        self.assertIn("85 kg", unsigned)

    def test_a_sign_the_page_prints_is_not_disclosed_as_missing(self):
        ozkan = next(p for p in self.rows if p.fighter == "Kerem Özkan")
        self.assertEqual("over", ozkan.weight_bound)


class Ukraine(unittest.TestCase):
    """Articles out of savate.org.ua's JavaScript bundle."""

    def test_the_world_cup_medals_and_their_dates(self):
        tournament, rows, report = read(
            "misc-ukraine-bundle", "ua-weiz", {"country": "Ukraine"},
            event="Savate World Cup 2025 in Austria")
        self.assertEqual([], canonical("weiz", rows))
        self.assertEqual(7, len(rows))
        by_name = {p.fighter: p for p in rows}
        self.assertEqual(("75", "under", "1"),
                         (by_name["Nazar Kostiuk"].weight_kg,
                          by_name["Nazar Kostiuk"].weight_bound,
                          by_name["Nazar Kostiuk"].rank))
        # "85+ kg" and "+85 kg" are the same class written two ways.
        self.assertEqual(("85", "over"),
                         (by_name["Myroslav Liashko"].weight_kg,
                          by_name["Myroslav Liashko"].weight_bound))
        self.assertEqual("2025-10-03", tournament.start_date)
        self.assertEqual("2025-10-05", tournament.end_date)
        self.assertEqual(2, sum(1 for p in rows if p.rank == "3"))

    def test_an_age_class_is_not_split_out_of_a_heading_that_names_two(self):
        # "Youth and Junior World Cup Winners" is two age classes in one
        # heading, so the medallists under it get neither.
        _t, rows, report = read("misc-ukraine-bundle", "ua-weiz",
                                {"country": "Ukraine"},
                                event="Savate World Cup 2025 in Austria")
        by_name = {p.fighter: p for p in rows}
        self.assertEqual("Senior", by_name["Nazar Kostiuk"].age_class)
        self.assertEqual("", by_name["Maksym Melnyk"].age_class)
        self.assertTrue(any("more than one age class" in p
                            for p in report.problems))

    def test_medals_with_no_weight_class_are_kept_and_flagged(self):
        tournament, rows, report = read(
            "misc-ukraine-bundle", "ua-helsinki", {"country": "Ukraine"},
            event="Helsinki Savate Open 2026")
        self.assertEqual([], canonical("helsinki", rows))
        self.assertEqual(7, len(rows))
        self.assertEqual({""}, {p.weight_kg for p in rows})
        self.assertEqual(4, sum(1 for p in rows if p.rank == "1"))
        self.assertEqual(7, sum(1 for p in report.problems
                                if "no weight class" in p))
        self.assertEqual("2026-03-13", tournament.start_date)

    def test_an_unsigned_weight_is_disclosed_and_a_printed_one_is_not(self):
        # "Nazar Kostiuk — 75 kg" prints no bound; the European championship
        # article prints "weight category up to 56 kg", which states it in
        # words. The first is this archive's convention and has to say so, the
        # second is the document and must not be reported as missing.
        _t, _rows, report = read("misc-ukraine-bundle", "ua-weiz",
                                 {"country": "Austria"},
                                 event="Savate World Cup 2025 in Austria")
        self.assertTrue(any("without a sign" in p for p in report.problems))
        # The same federation's European championship article writes the bound
        # out: "Artur Hubenko — weight category up to 56 kg (juniors)".
        self.assertEqual(("56", "under", True),
                         misc._weight("weight category up to 56 kg (juniors)"))
        self.assertEqual(("75", "under", False), misc._weight("75 kg"))
        self.assertEqual(("85", "over", True), misc._weight("85+ kg"))
        self.assertEqual(("60", "under", True), misc._weight("-60 kg"))

    def test_the_host_nation_is_never_stamped_on_the_delegation(self):
        # REGRESSION: the truthful country for the Helsinki Open is Finland,
        # and it used to arrive on seven Ukrainian medallists.
        _t, rows, _r = read("misc-ukraine-bundle", "ua-helsinki",
                            {"country": "Finland", "city": "Helsinki"},
                            event="Helsinki Savate Open 2026")
        self.assertEqual({""}, {p.country for p in rows})
        _t, rows, _r = read("misc-ukraine-bundle", "ua-helsinki",
                            {"country": "Finland", "city": "Helsinki"},
                            event="Helsinki Savate Open 2026",
                            home_country="Ukraine")
        self.assertEqual({"Ukraine"}, {p.country for p in rows})

    def test_an_article_with_no_results_yields_none(self):
        # The national championship post is four screens of narrative, two
        # trophy winners and a petition link. There is not one placing in it.
        _t, rows, report = read("misc-ukraine-bundle", "ua-2026",
                                {"country": "Ukraine"},
                                event="Ukrainian Savate Championship 2026")
        self.assertEqual([], rows)
        self.assertTrue(any("none of this module's four layouts" in p
                            for p in report.problems))

    def test_naming_no_article_reads_nothing(self):
        _t, rows, report = read("misc-ukraine-bundle", "ua-x",
                                {"country": "Ukraine"})
        self.assertEqual([], rows)
        self.assertTrue(any("no article was named" in p
                            for p in report.problems))

    def test_an_article_that_is_not_there(self):
        _t, rows, report = read("misc-ukraine-bundle", "ua-x",
                                {"country": "Ukraine"}, event="Tokyo 1964")
        self.assertEqual([], rows)
        self.assertTrue(any("no article matching" in p
                            for p in report.problems))


class Guadeloupe(unittest.TestCase):
    """A live Wix post, read by the grammar `antilles_bouts` already owns."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "misc-guadeloupe-wix", "gp-dynamik",
            {"country": "France", "discipline": "assaut"})

    def test_every_bout_is_canonical(self):
        self.assertEqual([], canonical("guadeloupe", self.rows))

    def test_the_seven_decided_assauts_the_article_counts(self):
        self.assertEqual(7, len(self.rows))
        self.assertEqual("2024-04-20", self.tournament.start_date)

    def test_the_winner_is_one_of_the_two_fighters(self):
        for bout in self.rows:
            self.assertNotEqual(bout.red, bout.blue, bout.bout_id)
            if bout.winner:
                self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)

    def test_the_sentence_that_wrapped_is_closed_up_and_read(self):
        # REGRESSION: "SAINTE-ROSE FANCHINE SEBASTIEN ... VS RAIMBAULT ROMAIN
        # ... vainqueur l'unanimité" was filed unresolved because its last two
        # words are the next paragraph, "RAIMBAULT .". That tail is printed
        # text - a plain <p> - not the colour Wix set the name in, and the
        # article's own count says seven assauts were decided.
        bout = next(b for b in self.rows
                    if b.red.startswith("SAINTE-ROSE"))
        self.assertEqual("decided", bout.status)
        self.assertEqual("RAIMBAULT ROMAIN", bout.winner)
        self.assertEqual("SAINTE-ROSE FANCHINE SEBASTIEN", bout.loser)
        self.assertEqual("", bout.winner_corner)
        self.assertEqual(7, sum(1 for b in self.rows if b.status == "decided"))
        self.assertTrue(any("wrapped onto the next paragraph" in p
                            for p in self.report.problems))

    def test_a_line_that_names_its_winner_is_never_joined_to_the_next(self):
        # The join only fires on a verdict followed by no capital. Every other
        # bout on this card names its winner on its own line and must stay one
        # bout, with both fighters still its own.
        for bout in self.rows:
            self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)
        self.assertEqual(7, len(self.rows))

    def test_no_gender_is_read_out_of_the_class_letter(self):
        # REGRESSION: "M75", "M70", "M65", "M56", "M85" became gender="Men"
        # while the "+90" bout on the same card got none. The letter is
        # expanded from another site's grammar; this page prints no word for a
        # gender anywhere, so no row carries one.
        self.assertEqual({""}, {b.gender for b in self.rows})
        self.assertNotIn("Men", " ".join(b.category for b in self.rows))
        self.assertTrue(any("class letter" in p for p in self.report.problems))

    def test_the_demonstrations_are_counted_and_not_filed(self):
        # "7 assauts avec décision et 5 en démonstration." The five are never
        # listed, so not one of them may become a row.
        self.assertEqual(5, self.report.notes.get("demonstrations_claimed"))
        self.assertTrue(any("demonstrations" in p
                            for p in self.report.problems))

    def test_no_corner_is_ever_claimed(self):
        self.assertEqual({""}, {b.winner_corner for b in self.rows})

    def test_the_club_is_kept_beside_each_fighter(self):
        raimbault = next(b for b in self.rows if b.red == "RAIMBAULT ROMAIN")
        self.assertEqual("gwadaboxing club", raimbault.red_club)
        self.assertEqual("savateboxing971", raimbault.blue_club)

    def test_it_was_read_by_the_adapter_that_owns_this_grammar(self):
        self.assertEqual("antilles_bouts",
                         self.report.notes.get("delegated_to"))


class Hazards(unittest.TestCase):
    """Synthetic pages. No federation published these; see the module docstring.

    They exist so the guards that none of the six real documents happens to
    trip are exercised: another sport mixed into the results, a demonstration
    among the bouts, and a verdict word the reader has never seen.
    """

    def test_another_sport_is_dropped_and_counted(self):
        _t, rows, report = read("misc-hazards-croatia", "hz",
                                {"country": "Testland"})
        self.assertNotIn("EMA EMIC", {b.red for b in rows})
        self.assertEqual(1, report.notes["other_sport_rows"])
        self.assertTrue(any("another sport" in p for p in report.problems))

    def test_a_demonstration_is_dropped_and_counted(self):
        _t, rows, report = read("misc-hazards-croatia", "hz",
                                {"country": "Testland"})
        self.assertNotIn("GLO GLOIC", {b.red for b in rows})
        self.assertEqual(1, report.notes["demonstrations"])

    def test_an_unknown_verdict_is_unresolved_and_not_a_win(self):
        _t, rows, report = read("misc-hazards-croatia", "hz",
                                {"country": "Testland"})
        bout = next(b for b in rows if b.red == "IVA IVIC")
        self.assertEqual("unresolved", bout.status)
        self.assertEqual("", bout.winner)
        self.assertTrue(any("NEODLUCENO" in p for p in report.problems))

    def test_a_tier_heading_for_another_sport_takes_its_medallists_with_it(self):
        _t, rows, report = read("misc-hazards-delegation", "hz",
                                {"country": "Testland"})
        names = {p.fighter for p in rows}
        self.assertNotIn("Cile Cilic", names)     # under the canne heading
        self.assertNotIn("Dea Deic", names)       # canne on its own line
        self.assertNotIn("Fra Fric", names)       # a demonstration
        self.assertEqual(2, report.notes["other_sport_rows"])
        self.assertEqual(1, report.notes["demonstrations"])

    def test_a_sentence_is_not_a_medallist(self):
        _t, rows, _r = read("misc-hazards-delegation", "hz",
                            {"country": "Testland"})
        for placing in rows:
            self.assertTrue(misc.looks_like_person(placing.fighter),
                            placing.fighter)

    def test_a_page_that_is_none_of_the_four_yields_nothing(self):
        _t, rows, report = read("misc-not-results", "nr", {})
        self.assertEqual([], rows)
        self.assertTrue(any("none of this module's four layouts" in p
                            for p in report.problems))


class WordShapes(unittest.TestCase):
    """The one heuristic in this module that is not anchored to a label."""

    def test_names_pass_and_prose_does_not(self):
        for name in ("Melnyk Maksym", "Efe Ercan Boğaz", "Nazar Kostiuk",
                     "Arzu Şevval Karakaya", "Alaban de Carheil"):
            self.assertTrue(misc.looks_like_person(name), name)
        for prose in ("Glory to Ukraine!", "Results of Ukrainian athletes:",
                      "In addition to sports achievements", "",
                      "Toplamda 26 sporcuyla", "Kostiuk", "2 Altın"):
            self.assertFalse(misc.looks_like_person(prose), prose)


class Contract(unittest.TestCase):
    """What every adapter in this package owes its caller."""

    def test_the_three_things_an_adapter_needs(self):
        self.assertEqual("misc_federations", misc.NAME)
        self.assertTrue(misc.DESCRIPTION)
        self.assertTrue(callable(misc.read))

    def test_a_report_comes_back_from_every_read(self):
        for stem, options in (("misc-croatia-2025", {}),
                              ("misc-turkey-2025", {}),
                              ("misc-not-results", {}),
                              ("misc-canada-champions", {"event": "1999"})):
            _t, rows, report = read(stem, "x", {}, **options)
            self.assertEqual("misc_federations", report.adapter)
            self.assertIsInstance(report.problems, list)
            self.assertTrue(all(isinstance(r, (Bout, Placing)) for r in rows))

    def test_a_source_that_cannot_be_read_is_reported_not_raised(self):
        _t, rows, report = misc.read(str(FIXTURES / "no-such-file.html"),
                                     "x", {})
        self.assertEqual([], rows)
        self.assertTrue(any("could not fetch" in p for p in report.problems))


if __name__ == "__main__":
    unittest.main()
