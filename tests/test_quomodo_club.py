"""The Quomodo/FFSavate reader, against ten of the real documents.

The fixtures are the federation's own files, one per layout the adapter claims
to read, and the assertions are the things that would actually go wrong on
them: a verdict landing on the wrong fighter when the winner is the SECOND line
of the pair, a red-ink winner read off the wrong side of the slash, a poule
whose ink names nobody quietly acquiring a winner, a schedule of finals being
stored as if they had been fought, a "Finaliste 1" turning into a bronze, both
of a class's two bronzes surviving, and the class code F100/M150 being read as
a hundred-kilo weight.

Row counts are asserted exactly. They were taken by reading each document and
counting its bouts by hand, so a change that silently loses or invents four
rows fails here rather than in the archive.
"""

import collections
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import quomodo_club as quomodo
from savate.schema import Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"

HAS_POPPLER = shutil.which("pdftohtml") is not None


def read(name, slug="t", **meta):
    return quomodo.read(FIXTURES / name, slug, meta)


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


def by_category(rows):
    out = collections.defaultdict(list)
    for row in rows:
        out[row.category].append(row)
    return out


def canonical(case, rows):
    """Every row is well formed, and no two rows share an id."""
    case.assertEqual([], [c for r in bouts(rows) for c in check(r)])
    case.assertEqual([], [c for r in placings(rows) for c in check_placing(r)])
    ids = [r.bout_id for r in bouts(rows)] + [r.placing_id for r in placings(rows)]
    case.assertEqual(len(ids), len(set(ids)), "row ids are not unique")


# --------------------------------------------------------------------------
# The vocabulary every layout leans on
# --------------------------------------------------------------------------


class Verdicts(unittest.TestCase):

    def test_the_words_the_sheets_actually_print(self):
        cases = [
            ("Victoire à l’unanimité", "points", "Unanimité"),
            ("Victoire à la majorité", "points", "Majorité"),
            ("unanimité", "points", "Unanimité"),
            ("majorité", "points", "Majorité"),
            ("Victoire par disqualification", "disqualification",
             "Disqualification"),
            ("Victoire par arrêt médical 1°", "abandon", "Arrêt médical"),
            ("Victoire par Hors Combat 2°", "abandon", "Hors combat"),
            ("HC 1ère reprise", "abandon", "Hors combat"),
            ("jet de l’éponge", "abandon", "Jet de l'éponge"),
            ("Forfait", "forfait", "Forfait"),
            ("Vainqueur par forfait", "forfait", "Forfait"),
            ("Abandon 2°", "abandon", "Abandon"),
        ]
        for printed, decision, detail in cases:
            with self.subTest(printed):
                _head, got, word = quomodo._verdict(f"NOM Prenom .... {printed}")
                self.assertEqual(decision, got)
                self.assertEqual(detail, word)

    def test_a_club_is_not_a_knockout(self):
        """"KO BOXING CLUB (13)" ends a line and must not read as a KO."""
        head, decision, _ = quomodo._verdict(
            "M60 Légers .... DUPONT Jean .... KO BOXING CLUB (13)")
        self.assertEqual("", decision)
        self.assertIn("KO BOXING CLUB", head)

    def test_a_demonstration_is_not_a_bout(self):
        self.assertTrue(quomodo._DEMO.search("Démonstration minimes"))
        self.assertTrue(quomodo._DEMO.search("assaut de demo"))
        # DEMOUGEOT Franck fought eight real bouts in the 2018 qualifiers.
        self.assertIsNone(quomodo._DEMO.search("ANNOUR Brahim / DEMOUGEOT Franck"))

    def test_another_sport_is_recognised_without_eating_a_club(self):
        self.assertTrue(quomodo._OTHER_SPORT.search("Canne de combat - seniors"))
        self.assertTrue(quomodo._OTHER_SPORT.search("Chausson"))
        self.assertIsNone(quomodo._OTHER_SPORT.search("BC CANNES SAVATE (06)"))


class NameAndClub(unittest.TestCase):

    def test_the_dot_leader_splits_the_columns(self):
        self.assertEqual(
            ("RIVIERE Vanessa", "LA SAVATE CARAMANAISE (31)"),
            quomodo._split_name_club(
                "RIVIERE Vanessa. .................. LA SAVATE CARAMANAISE (31)"))

    def test_a_single_dot_is_not_a_column(self):
        """"NGASSAM Thomas de Dieu.CS CLICHY (92)" - one dot, no column."""
        self.assertEqual(
            ("NGASSAM Thomas de Dieu", "CS CLICHY (92)"),
            quomodo._split_name_club("NGASSAM Thomas de Dieu.CS CLICHY (92)"))

    def test_no_separator_at_all_falls_back_on_the_capitals(self):
        self.assertEqual(
            ("BERNARD Hugo", "NARBONNE SAVATE MEDITERRANEE (11)"),
            quomodo._split_name_club(
                "BERNARD Hugo NARBONNE SAVATE MEDITERRANEE (11)"))

    def test_a_given_name_that_lost_its_column_comes_back(self):
        self.assertEqual(
            ("NIVAULT-TERNIN-ROZAT Alexis", "MJC SAVATE COTOISE (38)"),
            quomodo._split_name_club(
                "NIVAULT-TERNIN-ROZAT ...........Alexis MJC SAVATE COTOISE (38)"))

    def test_a_clubs_initial_stays_with_the_club(self):
        """"S SAVATITUDE" must not become part of "MICHEL Pierre"."""
        self.assertEqual(
            ("MICHEL Pierre", "S SAVATITUDE (26)"),
            quomodo._split_name_club("MICHEL Pierre ......... S SAVATITUDE (26)"))

    def test_a_half_printed_bracket_still_yields_the_club(self):
        self.assertEqual("CS MEAUX", quomodo._club("CS MEAUX (77"))
        self.assertEqual("PUNCH BLAGNAC", quomodo._club("PUNCH BLAGNAC 31)"))
        # No bracket at all: kept exactly as printed rather than guessed at.
        self.assertEqual("ADAC 74", quomodo._club("ADAC 74"))


class ClassCodes(unittest.TestCase):

    def test_an_ordinary_class(self):
        label, gender, kilos, bound = quomodo._category(
            "F", 48, False, "Espoir", quomodo.Report())
        self.assertEqual(("Espoir Women -48 kg", "Women", "48", "under"),
                         (label, gender, kilos, bound))

    def test_the_sentinel_is_the_open_class_and_is_reported(self):
        report = quomodo.Report()
        label, _gender, kilos, bound = quomodo._category(
            "M", 150, False, "", report)
        self.assertEqual(("Men open", "", "over"), (label, kilos, bound))
        self.assertIn("M150", report.notes["sentinel_classes"])

    def test_a_plus_class_is_a_weight_not_a_sentinel(self):
        report = quomodo.Report()
        label, _gender, kilos, bound = quomodo._category("M", 85, True, "", report)
        self.assertEqual(("Men +85 kg", "85", "over"), (label, kilos, bound))
        self.assertNotIn("sentinel_classes", report.notes)


# --------------------------------------------------------------------------
# A: the dotted finals sheet
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class EspoirsFinals2015(unittest.TestCase):
    """uploads/803 - sixteen finals, Béziers, 21 February 2015."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-espoirs-2015.pdf")

    def test_every_final_and_nothing_else(self):
        canonical(self, self.rows)
        self.assertEqual(16, len(bouts(self.rows)))
        self.assertEqual(32, len(placings(self.rows)))
        self.assertTrue(all(b.phase == "final" for b in bouts(self.rows)))

    def test_the_sheet_dates_itself(self):
        self.assertEqual("2015-02-21", self.tournament.start_date)
        self.assertEqual("2015", self.tournament.year)

    def test_the_winner_is_the_line_carrying_the_verdict(self):
        """F48's verdict is on the SECOND line; F52's on the first."""
        found = {b.category: b for b in bouts(self.rows)}
        f48 = found["Espoir Women -48 kg"]
        self.assertEqual("RIVIERE Vanessa", f48.red)
        self.assertEqual("GUILLOT Ludivine", f48.blue)
        self.assertEqual("GUILLOT Ludivine", f48.winner)
        self.assertEqual("RIVIERE Vanessa", f48.loser)

        f52 = found["Espoir Women -52 kg"]
        self.assertEqual("DERRIENNIC Anne Gaelle", f52.winner)
        self.assertEqual("ARMOUGOM Megane", f52.loser)

    def test_no_corner_is_invented(self):
        self.assertTrue(all(b.winner_corner == "" for b in bouts(self.rows)))
        self.assertTrue(all(b.winner in (b.red, b.blue) for b in bouts(self.rows)))

    def test_the_club_survives_the_dot_leader(self):
        found = {b.category: b for b in bouts(self.rows)}
        self.assertEqual("LA SAVATE CARAMANAISE",
                         found["Espoir Women -48 kg"].red_club)
        self.assertEqual("CS CLICHY", found["Espoir Men -80 kg"].red_club)
        self.assertEqual("NGASSAM Thomas de Dieu",
                         found["Espoir Men -80 kg"].red)

    def test_a_disqualification_is_not_a_points_win(self):
        m80 = next(b for b in bouts(self.rows)
                   if b.category == "Espoir Men -80 kg")
        self.assertEqual("disqualification", m80.decision)
        self.assertEqual("POCHET Alexis", m80.winner)

    def test_the_open_class_carries_no_weight(self):
        opens = [b for b in bouts(self.rows) if b.category.endswith("open")]
        self.assertEqual(2, len(opens))
        self.assertTrue(all(b.weight_kg == "" and b.weight_bound == "over"
                            for b in opens))
        self.assertTrue(any("F100" in p and "M150" in p
                            for p in self.report.problems))

    def test_one_gold_and_one_silver_a_class(self):
        for category, rows in by_category(placings(self.rows)).items():
            with self.subTest(category):
                self.assertEqual(["1", "2"], sorted(r.rank for r in rows))
                self.assertEqual(["gold", "silver"],
                                 sorted(r.medal for r in rows))


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class TournoisDeFrance2015(unittest.TestCase):
    """uploads/836 - a full bracket: eighths, quarters, semis and finals."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-tournois-2015.pdf")

    def test_every_round_is_read_and_placed(self):
        canonical(self, self.rows)
        rounds = collections.Counter(b.phase for b in bouts(self.rows))
        self.assertEqual({"r16": 2, "quarter": 7, "semi": 9, "final": 7}, rounds)

    def test_three_bouts_in_one_class_and_round_pair_correctly(self):
        """The 1/4 M70 block is six lines: three bouts, not one and a mess."""
        m70 = [b for b in bouts(self.rows)
               if b.category == "Senior Men -70 kg" and b.phase == "quarter"]
        self.assertEqual(3, len(m70))
        self.assertEqual(
            [("CLONROZIER Damien", "CLONROZIER Damien"),
             ("BENHAMOU Jonathan", "THOMAS Julien"),
             ("VACHE Jérôme", "VACHE Jérôme")],
            [(b.red, b.winner) for b in m70])

    def test_only_a_final_produces_a_podium(self):
        """A semi-final loser is not a silver medallist."""
        self.assertEqual(14, len(placings(self.rows)))
        finals = {b.category for b in bouts(self.rows) if b.phase == "final"}
        self.assertEqual(finals, {p.category for p in placings(self.rows)})

    def test_the_age_class_comes_from_the_section_banner(self):
        self.assertTrue(all(r.age_class == "Senior"
                            for r in bouts(self.rows) + placings(self.rows)))


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class OpenDeFranceAutomne2021(unittest.TestCase):
    """uploads/1873 - semis and finals, and two outcomes that are not points."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-open-2021.pdf")

    def test_counts(self):
        canonical(self, self.rows)
        self.assertEqual({"semi": 8, "final": 10},
                         dict(collections.Counter(b.phase
                                                  for b in bouts(self.rows))))
        self.assertEqual(20, len(placings(self.rows)))

    def test_a_towel_and_a_hors_combat_are_abandons(self):
        found = {(b.category, b.phase): b for b in bouts(self.rows)}
        towel = found[("Men -85 kg", "final")]
        self.assertEqual("abandon", towel.decision)
        self.assertEqual("Jet de l'éponge", towel.decision_detail)
        self.assertEqual("BRUGIROUX Christopher", towel.winner)

        hors = found[("Men -75 kg", "semi")]
        self.assertEqual("abandon", hors.decision)
        self.assertEqual("Hors combat", hors.decision_detail)
        self.assertEqual("KAMARA Alassane", hors.winner)

    def test_a_name_split_by_the_leader_is_put_back_together(self):
        semi = next(b for b in bouts(self.rows)
                    if b.blue.startswith("NIVAULT"))
        self.assertEqual("NIVAULT-TERNIN-ROZAT Alexis", semi.blue)
        self.assertEqual("MJC SAVATE COTOISE", semi.blue_club)


# --------------------------------------------------------------------------
# B: the poule sheet, where the winner is red ink
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class CoupeDeFrance2018(unittest.TestCase):
    """uploads/1321 - red-ink poules on page one, dotted finals on page two."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-coupe-2018.pdf")

    def test_both_layouts_in_one_file(self):
        canonical(self, self.rows)
        self.assertEqual({"poule": 13, "final": 4},
                         dict(collections.Counter(b.phase
                                                  for b in bouts(self.rows))))
        self.assertEqual(8, len(placings(self.rows)))

    def test_the_red_name_is_the_winner_on_either_side_of_the_slash(self):
        poules = {(b.red, b.blue): b for b in bouts(self.rows)
                  if b.phase == "poule"}
        # Red on the left.
        self.assertEqual("CHAMPION Brigitte",
                         poules[("CHAMPION Brigitte", "MAJENE Sandy")].winner)
        # Red on the right.
        self.assertEqual("MICHAUX Vanessa",
                         poules[("MAJENE Sandy", "MICHAUX Vanessa")].winner)
        self.assertEqual("MEUNIER Mélissa",
                         poules[("NAVINER Karine", "MEUNIER Mélissa")].winner)

    def test_black_ink_on_both_names_leaves_the_bout_unresolved(self):
        """LOPES / MEUNIER is a forfait with nobody marked. It stays unresolved."""
        bout = next(b for b in bouts(self.rows)
                    if (b.red, b.blue) == ("LOPES Isabelle", "MEUNIER Mélissa")
                    and b.phase == "poule")
        self.assertEqual("unresolved", bout.status)
        self.assertEqual("", bout.winner)
        self.assertEqual("", bout.result_source)
        # The decision is still a fact the sheet states.
        self.assertEqual("forfait", bout.decision)
        self.assertTrue(any("unresolved" in p for p in self.report.problems))

    def test_the_poules_take_their_class_from_the_banner_above_them(self):
        classes = {b.category for b in bouts(self.rows) if b.phase == "poule"}
        self.assertEqual({"Women -60 kg", "Women -65 kg"}, classes)

    def test_no_poule_bout_produces_a_medal(self):
        self.assertTrue(all(p.category in {"Women -52 kg", "Women -56 kg",
                                           "Women -60 kg", "Women -65 kg"}
                            for p in placings(self.rows)))
        self.assertEqual(4, len({p.category for p in placings(self.rows)}))


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class Assaut2021(unittest.TestCase):
    """uploads/1876 - poules, semis and finals, and two classes with no poule."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-assaut-2021.pdf")

    def test_counts(self):
        canonical(self, self.rows)
        self.assertEqual({"poule": 135, "semi": 24, "final": 16},
                         dict(collections.Counter(b.phase
                                                  for b in bouts(self.rows))))
        self.assertEqual(32, len(placings(self.rows)))

    def test_a_pairing_marked_finale_is_a_note_not_a_bout(self):
        """Two classes had two entries and no round robin. The sheet says
        "finale" where a verdict goes; the bout itself is on the finals page,
        and storing the note too would double it."""
        self.assertTrue(any("finale" in p and "not stored" in p
                            for p in self.report.problems))
        f75 = [b for b in bouts(self.rows) if b.category == "Women -75 kg"]
        self.assertEqual(["final"], [b.phase for b in f75])

    def test_the_semi_finals_pair_two_by_two(self):
        f48 = [b for b in bouts(self.rows)
               if b.category == "Women -48 kg" and b.phase == "semi"]
        self.assertEqual(2, len(f48))
        self.assertEqual([("LEGROS Elise", "FAURE Nada", "LEGROS Elise"),
                          ("CASSIN Alix", "NANDI Chloé", "NANDI Chloé")],
                         [(b.red, b.blue, b.winner) for b in f48])

    def test_every_poule_bout_has_a_weight_class(self):
        self.assertTrue(all(b.category and b.gender
                            for b in bouts(self.rows) if b.phase == "poule"))


# --------------------------------------------------------------------------
# C: the veterans' technique sheet - placings, and no bout at all
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class VeteransTechnique2015(unittest.TestCase):
    """uploads/834 - "GROS Stéphane - BC FRANOIS SERRE (25)   Champion"."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-veterans-2015.pdf")

    def test_a_podium_is_not_a_bout(self):
        """The sheet names a champion and a vice-champion and no bout between
        them. Inventing one would be fabrication."""
        canonical(self, self.rows)
        self.assertEqual([], bouts(self.rows))
        self.assertEqual(14, len(placings(self.rows)))

    def test_name_club_and_rank(self):
        first = placings(self.rows)[0]
        self.assertEqual("GROS Stéphane", first.fighter)
        self.assertEqual("BC FRANOIS SERRE", first.club)
        self.assertEqual("1", first.rank)
        self.assertEqual("gold", first.medal)
        self.assertEqual("Vétéran Men -60 kg", first.category)

    def test_vice_champion_is_read_before_champion(self):
        second = placings(self.rows)[1]
        self.assertEqual("RICHEBOIS Fabrice", second.fighter)
        self.assertEqual("2", second.rank)


# --------------------------------------------------------------------------
# The youth sheets: a stated placing this adapter refuses to number
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class Jeunes2015(unittest.TestCase):
    """uploads/828 - minimes and cadets, plus the Trophée Denise Avédiguian."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-jeunes-2015.pdf")

    def test_thirty_six_classes_each_with_a_champion_and_a_runner_up(self):
        canonical(self, self.rows)
        self.assertEqual([], bouts(self.rows))
        self.assertEqual(72, len(placings(self.rows)))
        for key, rows in by_category(placings(self.rows)).items():
            with self.subTest(key):
                self.assertEqual(["1", "2"], sorted(r.rank for r in rows))

    def test_a_finaliste_is_counted_and_never_ranked(self):
        """The sheet numbers its finalists from one and the trophy rules in the
        same file number them from three. Nothing settles it, so nothing is
        stored - but the count and the labels are reported."""
        self.assertEqual({"Finaliste 1": 32, "Finaliste 2": 20},
                         self.report.notes["unranked_placings"])
        self.assertTrue(any("Finaliste 1" in p and "not stored" in p
                            for p in self.report.problems))
        self.assertFalse(any(p.rank == "3" for p in placings(self.rows)))

    def test_minimes_and_cadets_are_different_competitions(self):
        """F48J appears under both banners; without the age class in the label
        the two would merge into one weight class."""
        ages = collections.Counter(p.age_class for p in placings(self.rows))
        self.assertEqual({"Minime": 40, "Cadet": 32}, dict(ages))
        self.assertIn("Minime Women -48 kg",
                      {p.category for p in placings(self.rows)})
        self.assertIn("Cadet Women -48 kg",
                      {p.category for p in placings(self.rows)})

    def test_the_ligue_points_table_is_not_a_competitor(self):
        """The trophy section ranks LIGUES, not people. None of it is a row."""
        names = {p.fighter for p in placings(self.rows)}
        for ligue in ("Ile de France", "Rhône Alpes", "PACA", "Réunion"):
            self.assertNotIn(ligue, names)


# --------------------------------------------------------------------------
# D: the international podium table
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class MondeAssaut2018(unittest.TestCase):
    """uploads/1380 - CAT / Résultat / Prénom / NOM / PAYS."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read("quomodo-monde-assaut-2018.pdf")

    def test_sixteen_classes_two_medals_each(self):
        canonical(self, self.rows)
        self.assertEqual([], bouts(self.rows))
        self.assertEqual(32, len(placings(self.rows)))

    def test_the_two_name_columns_are_read_as_labelled(self):
        first = placings(self.rows)[0]
        self.assertEqual("ATANASIO Kelly", first.fighter)
        self.assertEqual("France", first.country)
        self.assertEqual("Women -48 kg", first.category)

    def test_a_country_written_in_french_is_mapped(self):
        countries = {p.country for p in placings(self.rows)}
        self.assertIn("Serbia", countries)
        self.assertIn("Japan", countries)
        self.assertIn("Belgium", countries)
        self.assertNotIn("SERBIE", countries)

    def test_the_class_carries_down_the_vice_championne_row(self):
        """Only the champion's row prints the weight class."""
        self.assertTrue(all(p.category for p in placings(self.rows)))
        silver = [p for p in placings(self.rows) if p.rank == "2"]
        self.assertEqual(16, len(silver))


# --------------------------------------------------------------------------
# E/F: the European championship's two sheets
# --------------------------------------------------------------------------


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class EuropePamiers2018(unittest.TestCase):
    """uploads/1359 - a numbered classification, and a list of finalists."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "quomodo-europe-pamiers-2018.pdf")

    def test_counts(self):
        canonical(self, self.rows)
        self.assertEqual(14, len(bouts(self.rows)))
        self.assertEqual(30, len(placings(self.rows)))

    def test_a_finalist_is_not_a_medallist(self):
        """"FINALES" names the two who reached the final. The final was fought
        months later at a separate gala, so neither of them is ranked here."""
        for bout in bouts(self.rows):
            self.assertEqual("final", bout.phase)
            self.assertEqual("unresolved", bout.status)
            self.assertEqual("", bout.winner)
        self.assertTrue(any("FINALES" in p for p in self.report.problems))

    def test_savate_awards_two_bronzes(self):
        bronzes = [p for p in placings(self.rows)
                   if p.category == "Senior Men -65 kg" and p.rank == "3"]
        self.assertEqual(2, len(bronzes))
        self.assertEqual({"MIGUEL ESCUDERO M.", "SHEWIKH Ahmed"},
                         {p.fighter for p in bronzes})
        self.assertTrue(all(p.medal == "bronze" for p in bronzes))

    def test_the_numbered_junior_classification_is_read_as_ranks(self):
        juniors = [p for p in placings(self.rows)
                   if p.age_class == "Junior" and p.category == "Junior Men -65 kg"]
        self.assertEqual([("1", "DOZDOR Roko", "CRO"),
                          ("2", "FALGARONNE Hugo", "FRA"),
                          ("3", "SHVANEV Ilya", "RUS")],
                         [(p.rank, p.fighter, p.country) for p in juniors])

    def test_a_named_champion_is_ranked_and_the_nation_is_kept_as_printed(self):
        f65 = [p for p in placings(self.rows)
               if p.category == "Senior Women -65 kg"]
        self.assertEqual([("1", "SURREL Sara", "FRA"),
                          ("2", "REITBAUER Michaela", "AUS")],
                         [(p.rank, p.fighter, p.country) for p in f65])

    def test_the_open_class_is_a_plus_class_here_not_a_sentinel(self):
        opens = {p.category for p in placings(self.rows) if "+85" in p.category}
        self.assertEqual({"Junior Men +85 kg", "Senior Men +85 kg"}, opens)


@unittest.skipUnless(HAS_POPPLER, "poppler is not installed")
class EuropeFinales2018(unittest.TestCase):
    """uploads/1358 - a schedule of finals, published before they were fought."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.rows, cls.report = read(
            "quomodo-europe-finales-2018.pdf")

    def test_fifteen_finals_one_of_them_already_fought(self):
        canonical(self, self.rows)
        self.assertEqual(15, len(bouts(self.rows)))
        decided = [b for b in bouts(self.rows) if b.status == "decided"]
        self.assertEqual(1, len(decided))
        self.assertEqual("SURREL Sara", decided[0].winner)
        self.assertEqual(2, len(placings(self.rows)))

    def test_a_fixture_is_stored_unresolved_and_said_to_be_one(self):
        for bout in bouts(self.rows):
            if bout.status == "unresolved":
                self.assertEqual("", bout.winner)
                self.assertEqual("", bout.result_source)
        self.assertTrue(any("schedule" in p for p in self.report.problems))

    def test_the_date_and_the_two_nations_are_kept(self):
        f48 = next(b for b in bouts(self.rows)
                   if b.category == "Senior Women -48 kg")
        self.assertEqual("2018-12-08", f48.date)
        self.assertEqual(("AGARD Capucine", "FRA"), (f48.red, f48.red_country))
        self.assertEqual(("HURIEVA Olena", "UKR"), (f48.blue, f48.blue_country))

    def test_a_venue_line_is_not_a_competitor(self):
        """F75's second line reads "CROATIA - tbd"."""
        f75 = next(b for b in bouts(self.rows)
                   if b.category == "Senior Women -75 kg")
        self.assertEqual(("GREIMEL Carina", "KOVACIC Marjana"), (f75.red, f75.blue))
        self.assertEqual("", f75.date)


# --------------------------------------------------------------------------
# Refusing to crash
# --------------------------------------------------------------------------


class BadInput(unittest.TestCase):

    def test_a_file_with_no_text_layer_is_reported_not_raised(self):
        empty = FIXTURES / "quomodo-not-a-pdf.tmp"
        empty.write_bytes(b"%PDF-1.4\nnot really\n")
        try:
            tournament, rows, report = read(empty.name)
        finally:
            empty.unlink()
        self.assertEqual([], rows)
        self.assertTrue(report.problems)
        self.assertEqual("quomodo_club", tournament.adapter)

    def test_a_missing_file_is_the_one_thing_that_raises(self):
        with self.assertRaises(FileNotFoundError):
            read("quomodo-there-is-no-such-sheet.pdf")


if __name__ == "__main__":
    unittest.main()
