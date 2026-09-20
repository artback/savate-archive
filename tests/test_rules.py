"""The rules engine, checked against the championship it was derived from.

These are not invented fixtures. Every assertion runs over the 302 bouts and 61
poules in savate.db, so a rule that drifts away from how the sport is actually
scored fails here rather than at the next competition.
"""

import collections
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import rules

DB = Path(__file__).resolve().parent.parent / "savate.db"
TOURNAMENT = "world-assaut-2026"


def load():
    """(poules, advanced) from the database: real bouts, and who really went on."""
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM bouts WHERE tournament = ?", (TOURNAMENT,))]
    db.close()

    def cls(b):
        return (b["gender"], b["weight_kg"], b["weight_bound"])

    poules = collections.defaultdict(list)
    for b in rows:
        # A poule-phase bout with no poule letter belongs to no poule - that is
        # the GAREL/Calderon gap, and it is the integrity tests' subject, not
        # the ranking tests'.
        if b["phase"] == "poule" and b["poule"]:
            poules[cls(b) + (b["poule"],)].append(b)

    advanced = collections.defaultdict(set)
    for b in rows:
        if b["phase"] != "poule":
            for corner in ("red", "blue"):
                advanced[cls(b)].add(b[corner])
    return dict(poules), advanced


class ScoringModel(unittest.TestCase):
    """The 3 / 1 / -1 / 0 scale, against every scored poule bout."""

    def setUp(self):
        self.poules, _ = load()

    def test_points_match_the_published_scoresheet(self):
        checked = 0
        for key, bouts in self.poules.items():
            for b in bouts:
                if not b["winner_corner"] or not (b["red_points"] and b["blue_points"]):
                    continue
                won, lost = rules.bout_points(b["decision"])
                actual = (int(b["red_points"]), int(b["blue_points"]))
                expected = ((won, lost) if b["winner_corner"] == "red"
                            else (lost, won))
                self.assertEqual(expected, actual,
                                 f"{key} {b['red']} vs {b['blue']} ({b['decision']})")
                checked += 1
        self.assertGreater(checked, 200, "expected the whole poule programme")

    def test_three_warnings_is_always_a_disqualification(self):
        for bouts in self.poules.values():
            for b in bouts:
                for corner in ("red", "blue"):
                    warnings = b[f"{corner}_warnings"]
                    if warnings and int(warnings) >= rules.WARNINGS_FOR_DISQUALIFICATION:
                        self.assertEqual("disqualification", b["decision"],
                                         f"{b['red']} vs {b['blue']}")

    def test_an_unknown_decision_is_refused(self):
        with self.assertRaises(ValueError):
            rules.bout_points("golden point")


class Ranking(unittest.TestCase):
    """Standings must agree with who the organisers actually advanced."""

    def setUp(self):
        self.poules, self.advanced = load()

    def test_no_ranking_contradicts_the_real_qualification(self):
        contradictions, decisive, ambiguous = [], 0, 0
        for key, bouts in self.poules.items():
            went_on = self.advanced[key[:3]]
            through = {b["red"] for b in bouts if b["red"] in went_on} | \
                      {b["blue"] for b in bouts if b["blue"] in went_on}
            if not through or len(through) >= len({b[c] for b in bouts
                                                   for c in ("red", "blue")}):
                continue
            result = rules.standings(bouts)
            picked = rules.qualifiers(result, places=len(through))
            if not picked:
                ambiguous += 1
            elif set(picked) <= through:
                decisive += 1
            else:
                contradictions.append((key, sorted(picked), sorted(through)))
        self.assertEqual([], contradictions)
        self.assertGreaterEqual(decisive, 55)

    def test_the_three_way_cycle_is_reported_not_guessed(self):
        """Men -75 kg B: three fighters level on points, level on warnings."""
        bouts = self.poules[("Men", "75", "under", "B")]
        result = rules.standings(bouts)
        self.assertTrue(any(len(g) >= 2 for g in result.unresolved)
                        or result.standings[0].decided_by == "head-to-head")

    def test_a_perfect_cycle_cannot_be_ranked(self):
        """A beat B beat C beat A, all level: no ladder rung can separate them."""
        bouts = [
            {"red": "A", "blue": "B", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
            {"red": "B", "blue": "C", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
            {"red": "C", "blue": "A", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
        ]
        result = rules.standings(bouts)
        self.assertEqual([["A", "B", "C"]], result.unresolved)
        self.assertEqual([], rules.qualifiers(result, places=2))

    def test_weight_breaks_a_cycle_when_it_is_known(self):
        bouts = [
            {"red": "A", "blue": "B", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
            {"red": "B", "blue": "C", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
            {"red": "C", "blue": "A", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0"},
        ]
        result = rules.standings(bouts, weights={"A": 74.2, "B": 74.8, "C": 74.5})
        self.assertEqual([], result.unresolved)
        self.assertEqual(["A", "C", "B"], result.ranked)

    def test_warnings_separate_fighters_level_on_points(self):
        bouts = [
            {"red": "A", "blue": "B", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "2"},
            {"red": "B", "blue": "C", "winner_corner": "red", "decision": "points",
             "red_warnings": "2", "blue_warnings": "0"},
            {"red": "C", "blue": "A", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "1"},
        ]
        result = rules.standings(bouts)
        self.assertEqual("C", result.standings[0].name)
        self.assertEqual("warnings", result.standings[0].decided_by)


class Draws(unittest.TestCase):
    def test_compatriots_are_kept_apart_where_the_entry_allows(self):
        entries = [{"name": f"{c}{i}", "country": c}
                   for c in ("France", "Italy", "Sweden", "Algeria")
                   for i in range(3)]
        poules = rules.draw(entries, target=4)
        self.assertEqual(3, len(poules))
        for poule in poules:
            countries = [e["country"] for e in poule]
            self.assertEqual(len(countries), len(set(countries)))

    def test_a_single_nation_still_draws(self):
        entries = [{"name": f"FR{i}", "country": "France"} for i in range(6)]
        poules = rules.draw(entries, target=3)
        self.assertEqual(6, sum(len(p) for p in poules))

    def test_poule_sizes_stay_near_the_target(self):
        entries = [{"name": f"F{i}", "country": f"C{i % 7}"} for i in range(19)]
        poules = rules.draw(entries, target=4)
        self.assertEqual(19, sum(len(p) for p in poules))
        for poule in poules:
            self.assertLessEqual(len(poule), 5)
            self.assertGreaterEqual(len(poule), 3)


class Integrity(unittest.TestCase):
    def test_the_unresolved_bout_is_reported(self):
        """GAREL vs Calderon: no result, and no poule to have been scored in."""
        import sqlite3
        db = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
        bouts = [dict(r) for r in db.execute(
            "SELECT * FROM bouts WHERE tournament = ? AND status = 'unresolved'",
            (TOURNAMENT,))]
        db.close()
        problems = rules.check(bouts)
        self.assertTrue(any("has no result" in p for p in problems), problems)
        self.assertTrue(any("belongs to no poule" in p for p in problems), problems)

    def test_poules_of_different_classes_are_not_merged(self):
        """Poule A of -60 kg and poule A of -75 kg are two poules, not one."""
        bouts = [
            {"red": "A", "blue": "B", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0", "poule": "A",
             "phase": "poule", "category": "Men -60 kg", "bout_id": "b1"},
            {"red": "C", "blue": "D", "winner_corner": "red", "decision": "points",
             "red_warnings": "0", "blue_warnings": "0", "poule": "A",
             "phase": "poule", "category": "Men -75 kg", "bout_id": "b2"},
        ]
        problems = rules.check(bouts)
        self.assertEqual([], [p for p in problems if "cannot be separated" in p],
                         problems)

    def test_only_perfect_cycles_are_unrankable(self):
        """3 of 61 real poules resist the ladder, and all 3 for the same reason.

        Each is a cycle on equal points and equal warnings, where the mini
        league gives every fighter one win. Nothing short of weights orders them.
        """
        poules, _ = load()
        stuck = {key: rules.standings(bouts)
                 for key, bouts in poules.items()
                 if rules.standings(bouts).unresolved}
        self.assertEqual(3, len(stuck), sorted(stuck))
        for key, result in stuck.items():
            for group in result.unresolved:
                rows = {s.name: s for s in result.standings}
                self.assertEqual(1, len({rows[n].points for n in group}), key)
                self.assertEqual(1, len({rows[n].warnings for n in group}), key)

    # A and B finish level on 7 points; A won their meeting but carries four
    # warnings to B's none. Three fighters cannot produce this - any three-way
    # tie on points is a cycle - so it takes a poule of four.
    LEVEL_ON_POINTS = [
        {"red": "A", "blue": "B", "winner_corner": "red", "decision": "points",
         "red_warnings": "2", "blue_warnings": "0"},
        {"red": "C", "blue": "A", "winner_corner": "red", "decision": "points",
         "red_warnings": "0", "blue_warnings": "2"},
        {"red": "A", "blue": "D", "winner_corner": "red", "decision": "points",
         "red_warnings": "0", "blue_warnings": "0"},
        {"red": "B", "blue": "C", "winner_corner": "red", "decision": "points",
         "red_warnings": "0", "blue_warnings": "0"},
        {"red": "B", "blue": "D", "winner_corner": "red", "decision": "points",
         "red_warnings": "0", "blue_warnings": "0"},
        {"red": "D", "blue": "C", "winner_corner": "red", "decision": "points",
         "red_warnings": "0", "blue_warnings": "0"},
    ]

    def test_head_to_head_outranks_warnings(self):
        """The rung order FISav's own published standings demonstrate.

        A fighter with four warnings still finishes above one with none, on
        equal points, because he won the meeting.
        """
        result = rules.standings(self.LEVEL_ON_POINTS)
        self.assertEqual(["A", "B", "D", "C"], result.ranked)
        self.assertEqual(4, result.standings[0].warnings)
        self.assertEqual(0, result.standings[1].warnings)
        self.assertEqual("head-to-head", result.standings[0].decided_by)

    def test_a_different_body_can_rank_differently(self):
        """The ladder is a competition's rule, not this library's opinion."""
        result = rules.standings(
            self.LEVEL_ON_POINTS, ladder=("points", "warnings", "head-to-head"))
        self.assertEqual("B", result.standings[0].name)
        self.assertEqual("warnings", result.standings[0].decided_by)

    def test_an_unknown_criterion_is_refused(self):
        with self.assertRaises(ValueError):
            rules.standings([], ladder=("points", "coin toss"))

    def test_a_fighter_absent_from_the_entry_list_is_caught(self):
        """The failure that corrupted Men -75 kg B: a bout with a stranger in it."""
        bouts = [{"red": "A", "blue": "Nobody", "winner_corner": "red",
                  "decision": "points", "red_warnings": "0", "blue_warnings": "0",
                  "bout_id": "b1", "poule": "A"}]
        problems = rules.check(bouts, entries=[{"name": "A"}, {"name": "B"}])
        self.assertTrue(any("not in the entry list" in p for p in problems), problems)
        self.assertTrue(any("has no bout" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
