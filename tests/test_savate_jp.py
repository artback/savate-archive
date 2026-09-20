"""The Japanese Tokyo Open pages, checked against what the documents say.

These do not test that rows appear. Rows appeared for an earlier adapter that
filed men under "Junior Women -56 kg" and paired a fighter against himself. They
test the things that would actually go wrong on these particular pages:

  * 三鷹 3rd Place is a gym in Mitaka, and must never become a third place
  * two bronzes in one class are two medallists, not one row and a duplicate
  * an MVP, a fighting-spirit prize and a Best Bout are not placings
  * a ワンマッチ is one bout, and is reported rather than ranked
  * a bout whose winner the page never states is stored unresolved
  * fourth place is real, and carries no medal
  * a class naming canne de combat is a different sport and is dropped
  * a surname of two kanji - or of one - is a whole name

The fixtures are the real pages' own text, reduced to the article and wrapped
in the same role="main" region Google Sites puts it in, so they exercise the
real characters: full-width digits, ideographic commas, 選手 suffixes and all.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import savate_jp
from savate.schema import Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name, slug="jp", meta=None):
    return savate_jp.read(str(FIXTURES / f"savate_jp_{name}.html"), slug,
                          meta or {})


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def by_category(rows, label):
    return [p for p in placings(rows) if p.category == label]


class EveryYearReads(unittest.TestCase):
    """The nine editions, and the number of people each page actually names."""

    COUNTS = {"2023": 18, "2022": 12, "2021": 8, "2019": 18, "2016": 11,
              "2014": 10, "2013": 5, "2012": 9, "2011": 5}

    def test_each_year_yields_the_placings_the_page_prints(self):
        for year, expected in self.COUNTS.items():
            with self.subTest(year=year):
                _t, rows, _r = read(year)
                self.assertEqual(len(placings(rows)), expected)

    def test_every_row_satisfies_the_schema(self):
        for year in self.COUNTS:
            with self.subTest(year=year):
                _t, rows, _r = read(year)
                for row in placings(rows):
                    self.assertEqual(check_placing(row), [], row)
                for row in bouts(rows):
                    self.assertEqual(check(row), [], row)

    def test_no_placing_is_nameless_and_no_id_repeats(self):
        for year in self.COUNTS:
            with self.subTest(year=year):
                _t, rows, _r = read(year, slug=f"jp-{year}")
                ids = [p.placing_id for p in placings(rows)]
                self.assertEqual(len(ids), len(set(ids)))
                for row in placings(rows):
                    self.assertTrue(row.fighter.strip(), row)
                    self.assertTrue(row.placing_id.startswith(f"jp-{year}"))

    def test_the_year_and_the_event_come_off_the_page(self):
        for year in self.COUNTS:
            with self.subTest(year=year):
                tournament, _rows, _r = read(year)
                self.assertEqual(tournament.year, year)
        # Three pages date themselves in the narrative; the rest say nothing,
        # and a date they do not state is left empty rather than guessed.
        self.assertEqual(read("2023")[0].start_date, "2023-04-30")
        self.assertEqual(read("2014")[0].start_date, "2014-04-29")
        self.assertEqual(read("2013")[0].start_date, "2013-09-01")
        self.assertEqual(read("2022")[0].start_date, "")

    def test_meta_overrides_what_the_page_says_about_itself(self):
        tournament, _rows, _r = read("2023", meta={
            "name": "Savate Tokyo Open 2023", "discipline": "assaut",
            "level": "national", "format": "open", "country": "Japan"})
        self.assertEqual(tournament.discipline, "assaut")
        self.assertEqual(tournament.country, "Japan")
        self.assertEqual(tournament.format, "open")
        self.assertEqual(tournament.adapter, "savate_jp")


class AClubIsNotAPlacing(unittest.TestCase):
    """三鷹 3rd Place is a gym. A naive ordinal regex reads it as a podium."""

    def test_the_mitaka_gym_stays_a_club(self):
        _t, rows, _r = read("2022")
        first = by_category(rows, "男子 軽量級")[0]
        self.assertEqual(first.rank, "1")
        self.assertEqual(first.fighter, "伊藤")
        self.assertEqual(first.club, "三鷹 3rd Place")

    def test_no_row_anywhere_is_named_after_the_gym(self):
        for year in ("2021", "2022", "2019"):
            with self.subTest(year=year):
                _t, rows, _r = read(year)
                for row in placings(rows):
                    self.assertNotIn("Place", row.fighter)
                    self.assertNotIn("位", row.fighter)

    def test_a_latin_ordinal_only_ranks_at_the_start_of_a_line(self):
        self.assertEqual([r for r, _s, _e in savate_jp._places("1st MIMOTO")],
                         [1])
        # _places sees the line after NFKC, which is where ２位 becomes 2位
        # and （ becomes ( - the gym's "3rd" is then inside a parenthesis.
        self.assertEqual(
            [r for r, _s, _e in savate_jp._places("2位 伊藤(三鷹 3rd Place)")],
            [2])
        self.assertEqual(savate_jp._places("敢闘賞 伊藤(三鷹 3rd Place)"), [])


class TwoBronzes(unittest.TestCase):
    """Savate awards two. Both are rank 3 and both are real."""

    def test_both_bronzes_survive_the_ideographic_comma(self):
        _t, rows, _r = read("2023")
        class_65 = by_category(rows, "男子-65kg")
        self.assertEqual([p.rank for p in class_65], ["1", "2", "3", "3"])
        self.assertEqual([p.fighter for p in class_65[2:]], ["小嶌", "長谷川"])
        self.assertEqual([p.medal for p in class_65[2:]], ["bronze", "bronze"])

    def test_both_bronzes_survive_the_kanji_ordinal_form(self):
        _t, rows, _r = read("2019")
        class_60 = by_category(rows, "男子 -60kg")
        self.assertEqual([p.fighter for p in class_60], ["三本", "永井", "岡本", "北川"])
        self.assertEqual([p.rank for p in class_60], ["1", "2", "3", "3"])
        self.assertEqual(by_category(rows, "男子 -65kg")[2].club, "")
        self.assertEqual(by_category(rows, "男子 -65kg")[2].country, "Singapore")


class AwardsAreNotResults(unittest.TestCase):
    """Every page prints prizes in the same shape as a podium."""

    def test_the_2016_mvp_produces_no_row(self):
        _t, rows, _r = read("2016")
        self.assertNotIn("CEVES Rem", [p.fighter for p in placings(rows)])

    def test_the_2021_prize_winners_produce_no_rows(self):
        _t, rows, _r = read("2021")
        # 敢闘賞, 新人賞, Risk賞 and MASAさん賞 all name someone. None is a
        # placing, and 小嶌 is named by a prize and by nothing else.
        self.assertNotIn("小嶌", [p.fighter for p in placings(rows)])
        self.assertEqual(len(placings(rows)), 8)

    def test_the_2014_award_block_produces_no_rows(self):
        _t, rows, _r = read("2014")
        # 橋本 wins the Confirmé MVP and is also a real runner-up at -85kg.
        # He must appear once, for the medal, not twice.
        self.assertEqual([p.category for p in placings(rows)
                          if p.fighter == "橋本"], ["男子 Confirme -85kg"])

    def test_the_2019_mvp_line_is_not_a_weight_class(self):
        _t, rows, report = read("2019")
        self.assertNotIn("浜崎", [p.fighter for p in placings(rows)
                                  if p.rank == "1"])
        self.assertEqual(len(report.notes["categories"]), 7)


class ASingleBoutIsNotAPodium(unittest.TestCase):
    """ワンマッチ classes print one 優勝 and are not a classification."""

    def test_the_2013_one_matches_are_reported_not_ranked(self):
        _t, rows, report = read("2013")
        self.assertEqual(len(placings(rows)), 5)
        self.assertNotIn("橋本", [p.fighter for p in placings(rows)])
        reported = report.notes["single_bouts_not_ranked"]
        self.assertEqual([s["fighter"] for s in reported],
                         ["橋本", "堀田", "高橋"])
        self.assertTrue(any("ワンマッチ" in p for p in report.problems))

    def test_the_2012_one_match_is_reported_not_ranked(self):
        _t, rows, report = read("2012")
        self.assertNotIn("女子 軽量級 ワンマッチ",
                         [p.category for p in placings(rows)])
        self.assertEqual(report.notes["single_bouts_not_ranked"],
                         [{"category": "女子 軽量級 ワンマッチ",
                           "fighter": "Yupin", "rank": "1"}])

    def test_the_round_robin_and_bracket_classes_are_kept(self):
        _t, rows, report = read("2012")
        self.assertEqual(len(placings(rows)), 9)
        self.assertEqual(report.notes["category_formats"]["男子 中重量級 リーグ戦"],
                         "round-robin")


class ABoutWithNoStatedWinner(unittest.TestCase):
    """The page names two opponents and never says who won."""

    def test_the_2016_best_bout_is_stored_unresolved(self):
        _t, rows, _r = read("2016")
        self.assertEqual(len(bouts(rows)), 1)
        bout = bouts(rows)[0]
        self.assertEqual((bout.red, bout.blue), ("MIMOTO", "BUSHAWAY"))
        self.assertEqual(bout.status, "unresolved")
        # MIMOTO won -60kg and BUSHAWAY was second, but the Best Bout line does
        # not say so and deducing it from the podium would be the archive
        # inventing a result.
        self.assertEqual(bout.winner, "")
        self.assertEqual(bout.winner_corner, "")
        self.assertEqual(bout.result_source, "")
        self.assertEqual((bout.weight_kg, bout.weight_bound), ("60", "under"))
        self.assertEqual(bout.phase, "final")

    def test_the_2021_best_bout_award_still_records_the_pairing(self):
        _t, rows, _r = read("2021")
        bout = bouts(rows)[0]
        self.assertEqual((bout.red, bout.blue), ("岡本", "伊藤"))
        self.assertEqual(bout.status, "unresolved")
        # Nothing on that line states a class, so nothing is filled in.
        self.assertEqual((bout.category, bout.phase, bout.weight_kg), ("", "", ""))

    def test_a_bout_names_two_different_people(self):
        for year in EveryYearReads.COUNTS:
            with self.subTest(year=year):
                _t, rows, _r = read(year)
                for bout in bouts(rows):
                    self.assertTrue(bout.red and bout.blue)
                    self.assertNotEqual(bout.red, bout.blue)


class RanksBeyondThePodium(unittest.TestCase):
    def test_fourth_place_is_kept_and_carries_no_medal(self):
        _t, rows, _r = read("2022")
        fourth = [p for p in placings(rows) if p.rank == "4"]
        self.assertEqual(len(fourth), 1)
        self.assertEqual(fourth[0].fighter, "長谷川")
        self.assertEqual(fourth[0].medal, "")
        self.assertEqual(fourth[0].club, "御殿下")


class ClassesAndNations(unittest.TestCase):
    def test_the_weight_bound_the_page_prints_is_the_class(self):
        _t, rows, _r = read("2023")
        over = by_category(rows, "男子+85kg")[0]
        self.assertEqual((over.weight_kg, over.weight_bound), ("85", "over"))

    def test_a_grade_class_carries_no_invented_kilos(self):
        _t, rows, _r = read("2023")
        light = by_category(rows, "女子軽量級")
        self.assertEqual({p.weight_kg for p in light}, {""})
        self.assertEqual({p.weight_bound for p in light}, {""})
        self.assertEqual({p.gender for p in light}, {"Women"})

    def test_the_inline_class_keeps_its_minus_sign(self):
        # 2021 prints the women's class on the placing line: "-52kg ２位 家城".
        _t, rows, _r = read("2021")
        inline = [p for p in placings(rows) if p.gender == "Women"]
        self.assertEqual([p.category for p in inline],
                         ["女子 -48kg", "女子 -52kg", "女子 -52kg", "女子 -56kg"])
        self.assertEqual({p.weight_bound for p in inline}, {"under"})
        self.assertEqual([p.weight_kg for p in inline], ["48", "52", "52", "56"])

    def test_under_and_over_written_in_japanese(self):
        _t, rows, _r = read("2011")
        under = by_category(rows, "一般の部 男子アンダー70kgトーナメント")
        over = by_category(rows, "一般の部 男子オーバー70kgトーナメント")
        self.assertEqual({p.weight_bound for p in under}, {"under"})
        self.assertEqual({p.weight_bound for p in over}, {"over"})
        self.assertEqual({p.weight_kg for p in under + over}, {"70"})

    def test_a_parenthesis_is_a_nation_only_when_it_names_one(self):
        _t, rows, _r = read("2023")
        found = {p.fighter: (p.country, p.club) for p in placings(rows)}
        self.assertEqual(found["ヴァネッサ"], ("France", ""))
        self.assertEqual(found["シーラ"], ("New Caledonia", ""))
        self.assertEqual(found["ジェレミー"], ("United States", ""))
        self.assertEqual(found["ソーン"], ("Australia", ""))
        self.assertEqual(found["Yupin"], ("", "Team RISK"))
        self.assertEqual(found["田中"], ("", "JSC"))
        self.assertEqual(found["瀬下"], ("", "バトルフィットネス大森"))

    def test_an_unrecognised_parenthesis_stays_the_club_it_was_printed_as(self):
        _t, rows, _r = read("2019")
        found = {p.fighter: (p.country, p.club) for p in placings(rows)}
        self.assertEqual(found["田中"], ("", "OHARA Bros. Gym"))
        self.assertEqual(found["ルミナ・K"], ("", "Team Risk, JSC"))
        self.assertEqual(found["袁"], ("Chinese Taipei", ""))


class NamesAreStoredAsPrinted(unittest.TestCase):
    def test_a_two_kanji_surname_is_a_whole_name(self):
        _t, rows, _r = read("2022")
        self.assertIn("伊藤", [p.fighter for p in placings(rows)])

    def test_a_one_kanji_surname_survives(self):
        _t, rows, _r = read("2019")
        self.assertIn("袁", [p.fighter for p in placings(rows)])

    def test_the_athlete_suffix_is_stripped_and_nothing_else_is(self):
        _t, rows, _r = read("2014")
        names = [p.fighter for p in placings(rows)]
        self.assertIn("COLLART", names)
        self.assertIn("エドガー", names)
        for name in names:
            self.assertFalse(name.endswith("選手"), name)

    def test_full_width_latin_is_normalised_not_romanised(self):
        # The page prints Ｓａｓａ－Ｐ選手 and ＨＥＡ－ＫＯ選手.
        _t, rows, _r = read("2011")
        self.assertEqual(sorted(p.fighter for p in placings(rows)),
                         sorted(["HEA-KO", "Sasa-P", "野崎", "橋本", "SHIN"]))

    def test_two_fighters_sharing_a_surname_stay_two_people(self):
        _t, rows, _r = read("2016")
        seventy_five = by_category(rows, "Male -75kg")
        self.assertEqual([p.fighter for p in seventy_five],
                         ["TARDITS Stefan", "TARDITS Alain"])

    def test_the_source_typo_is_carried_not_corrected(self):
        _t, rows, _r = read("2014")
        self.assertIn("男子 Conrirme -65kg",
                      [p.category for p in placings(rows)])


class SplitElements(unittest.TestCase):
    """2011 and 2012 put the label and the name in separate elements."""

    def test_the_label_is_joined_to_the_name_on_the_following_line(self):
        _t, rows, report = read("split_elements")
        self.assertEqual([(p.rank, p.fighter) for p in placings(rows)],
                         [("1", "SHIN"), ("2", "Sasa-P"), ("3", "山崎")])
        for row in placings(rows):
            self.assertEqual(row.category, "男子 軽中量級 Confirmé トーナメント")
        # The MVP name on its own line is still not a placing, and the
        # ワンマッチ below is still not ranked.
        self.assertNotIn("Yupin", [p.fighter for p in placings(rows)])
        self.assertEqual(report.notes["single_bouts_not_ranked"][0]["fighter"],
                         "Yupin")


class AnotherSportIsDropped(unittest.TestCase):
    """Canne de combat is not savate, whichever alphabet names it."""

    def test_canne_classes_are_dropped_and_reported(self):
        _t, rows, report = read("other_sport")
        self.assertEqual([p.fighter for p in placings(rows)], ["山田", "鈴木"])
        self.assertEqual(report.notes["other_sport_dropped"],
                         ["佐藤", "高橋", "TANAKA"])
        self.assertTrue(any("another sport" in p for p in report.problems))


class BadDocumentsReportRatherThanCrash(unittest.TestCase):
    def test_a_page_with_no_results_yields_no_rows_and_says_so(self):
        _t, rows, report = read("empty")
        self.assertEqual(rows, [])
        self.assertIn("no placings read", report.problems)

    def test_a_page_that_is_not_a_results_page_does_not_raise(self):
        _t, rows, report = read("not_results")
        self.assertEqual(placings(rows), [])
        self.assertTrue(report.problems)

    def test_a_missing_source_is_the_one_thing_that_may_raise(self):
        with self.assertRaises(FileNotFoundError):
            savate_jp.read(str(FIXTURES / "savate_jp_nope.html"), "jp", {})


if __name__ == "__main__":
    unittest.main()
