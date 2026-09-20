"""The FFSavate sheet reader, against twelve of the real documents.

The fixtures are the federation's own files, one per layout the adapter claims
to read, and the assertions are the things that would actually go wrong on
them: a verdict landing on the wrong fighter, a club column cut in the middle
of a name, a sheet that names no winner quietly acquiring one, a poule entry
with "Forfait" where its rank should be turning into a rank, and the two
semi-finals one sheet states twice being counted twice.

Row counts are asserted exactly. They were taken by reading each document and
counting its bouts by hand, so a change that silently loses or invents four
rows fails here rather than in the archive.
"""

import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import pdf
from savate.adapters import ffsavate_sheets as sheets
from savate.schema import Bout, Placing, Report, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name, slug="t", **meta):
    return sheets.read(FIXTURES / name, slug, meta)


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


def canonical(case, rows):
    case.assertEqual([], [c for r in bouts(rows) for c in check(r)])
    case.assertEqual([], [c for r in placings(rows) for c in check_placing(r)])
    ids = [r.bout_id for r in bouts(rows)] + [r.placing_id for r in placings(rows)]
    case.assertEqual(len(ids), len(set(ids)), "row ids are not unique")


# --------------------------------------------------------------------------
# The vocabulary, which every layout leans on
# --------------------------------------------------------------------------

class Verdicts(unittest.TestCase):
    def test_the_words_the_sheets_actually_print(self):
        for text, decision, printed in [
            ("Unanimité", "points", "Unanimité"),
            ("A l’Unanimité", "points", "A l’Unanimité"),
            ("Victoire à la majorité", "points", "Victoire à la majorité"),
            ("Victoire à à l’unanimité", "points", "Victoire à à l’unanimité"),
            ("Par Forfait", "forfait", "Par Forfait"),
            ("Par disqualification", "disqualification", "Par disqualification"),
            ("Disqualification 3ème reprise", "disqualification",
             "Disqualification 3ème reprise"),
            ("HC 4e rep", "abandon", "HC 4e rep"),
            ("HC3", "abandon", "HC3"),
            ("H C 4°", "abandon", "H C 4°"),
            ("Hors combat", "abandon", "Hors combat"),
            ("Jet Éponge", "abandon", "Jet Éponge"),
            ("jet de l'éponge", "abandon", "jet de l'éponge"),
            ("MAJO", "points", "MAJO"),
            ("UNA", "points", "UNA"),
            ("FORF", "forfait", "FORF"),
            ("DISQ", "disqualification", "DISQ"),
            ("Disqua", "disqualification", "Disqua"),
        ]:
            got_decision, got_printed, _head = sheets._verdict(text)
            self.assertEqual((decision, printed), (got_decision, got_printed), text)

    def test_a_verdict_must_end_the_line(self):
        """A club that happens to read like a verdict is not a result."""
        self.assertEqual(("", "", "ARRET BOXING CLUB Paris"),
                         sheets._verdict("ARRET BOXING CLUB Paris"))

    def test_a_club_ending_in_le_does_not_swallow_the_verdict(self):
        """PHOENIX BOXE MARSEILLE once became "MARSEIL" + "LE Unanimité"."""
        decision, printed, head = sheets._verdict(
            "DUNOUHAUD Ines PHOENIX BOXE MARSEILLE Unanimité")
        self.assertEqual(("points", "Unanimité"), (decision, printed))
        self.assertEqual("DUNOUHAUD Ines PHOENIX BOXE MARSEILLE", head)

    def test_the_line_before_the_verdict_keeps_its_column_spacing(self):
        decision, _printed, head = sheets._cut_verdict(
            "JANOLI         Léa         SBF DE CLUSES       Majorité")
        self.assertEqual("points", decision)
        self.assertIn("Léa         SBF", head)


class Rounds(unittest.TestCase):
    def test_the_french_ordinal_rounds(self):
        for text, phase in [
            ("QUART DE FINALE PREMIUM – F56 PLUMES", "quarter"),
            ("HUITIEME DE FINALE ELITE A - M70 MI MOYENS", "r16"),
            ("¼ finale", "quarter"),
            ("1/8 Finale", "r16"),
            ("1/2F", "semi"),
            ("Résultats 1/2 Finales Juniors M60", "semi"),
            ("FINALE ELITE A F48 MOUCHES", "final"),
            ("Tour de poule", "poule"),
            ("Première partie", ""),
        ]:
            self.assertEqual(phase, sheets._phase(text), text)

    def test_a_round_of_sixteen_is_not_a_final(self):
        """schema.phase_of() reads "finale" inside "HUITIEME DE FINALE"."""
        self.assertEqual("r16", sheets._phase("HUITIEME DE FINALE PREMIUM"))


class Headings(unittest.TestCase):
    def test_a_class_heading_is_recognised_in_all_its_printings(self):
        for text in ("ELITE B M80", "ELITE B – M85", "ELITE A - M75", "JUNIORS M56",
                     "F48J", "1/ F48 Premium", "QUART DE FINALE PREMIUM – F56 PLUMES"):
            self.assertIsNotNone(sheets._heading(text), text)

    def test_a_competitor_is_not_a_heading(self):
        for text in ("MECHIN     Baptiste   PLANETE BORG (13)",
                     "SOARES Damien CO ULIS BFS (91) Unanimité",
                     "KOU       Lin Pha     BFS EN PERIGORD (24)",
                     "ZERROUQI SOULAYMAN (Fitboxing Breteuil)"):
            self.assertIsNone(sheets._heading(text), text)

    def test_the_series_and_the_age_class_are_read_apart(self):
        elite = sheets._heading("ELITE B M80")
        self.assertEqual(("Elite B", ""), (elite["series"], elite["age"]))
        junior = sheets._heading("JUNIORS M56")
        self.assertEqual(("", "Junior"), (junior["series"], junior["age"]))

    def test_a_sentinel_code_claims_no_weight_and_no_direction(self):
        """M150 is a number these sheets print; "open" and "+" are not.

        The category used to read "Men open" with weight_bound "over", neither
        of which is on any page: the code is kept as printed instead.
        """
        report = Report()
        wide = sheets._category("M", 150, "", report)
        self.assertEqual(("", ""), (wide["weight_kg"], wide["weight_bound"]))
        self.assertEqual("Men M150", wide["category"])
        self.assertEqual("Elite A Women F100",
                         sheets._category("F", 100, "", Report(),
                                          "Elite A")["category"])
        self.assertIn("M150", report.notes["sentinel_classes"])

    def test_a_youth_class_code_keeps_the_J_the_federation_printed(self):
        """On four of these sheets the J is the only age marker on the page."""
        report = Report()
        cadet = sheets._category("F", 48, "J", report)
        self.assertEqual("Women -48 kg (J)", cadet["category"])
        self.assertEqual(("48", "under"),
                         (cadet["weight_kg"], cadet["weight_bound"]))
        self.assertEqual("Men M150 (J)",
                         sheets._category("M", 150, "J", report)["category"])
        self.assertEqual(["F48J", "M150J"], report.notes["youth_classes"])
        self.assertEqual("Women -48 kg",
                         sheets._category("F", 48, "", Report())["category"])

    def test_a_number_glued_to_the_type_cell_still_names_the_round(self):
        """poppler hands back "16JUNIOR" where the N° cell runs into TYPE."""
        self.assertEqual("Junior", sheets._age("16JUNIOR"))
        self.assertEqual("Junior", sheets._age("4 JUN M75"))
        self.assertEqual("Benjamin", sheets._age("BEN"))
        self.assertEqual("Elite B", sheets._series("2Elt B"))
        self.assertEqual("", sheets._age("CACCIATORE Hugo"))
        self.assertEqual("", sheets._age("F48J"))


class NotSavate(unittest.TestCase):
    """Canne de combat and a demonstration are excluded, and counted."""

    def setUp(self):
        self.sheet = sheets._Sheet("t", {}, Report())

    def test_canne_de_combat_is_dropped_and_reported(self):
        self.assertTrue(self.sheet.skip("M65 canne de combat DUPONT v DURAND", "M65"))
        self.assertEqual(1, self.sheet.other_sport)
        self.assertTrue(self.sheet.report.problems)

    def test_a_demonstration_is_not_a_bout(self):
        for text in ("Démonstration MARTIN v DUPONT", "demo F52",
                     "Exhibition - M70"):
            self.assertTrue(self.sheet.skip(text, "x"), text)
        self.assertEqual(3, self.sheet.demos)

    def test_an_ordinary_bout_is_not_skipped(self):
        self.assertFalse(
            self.sheet.skip("SOARES Damien CO ULIS BFS (91) Unanimité", "M80"))
        self.assertEqual((0, 0), (self.sheet.demos, self.sheet.other_sport))


# --------------------------------------------------------------------------
# The documents
# --------------------------------------------------------------------------

@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class SeriesBlocks(unittest.TestCase):
    """Beaumont-lès-Valence 2026: ELITE A / ELITE B headings, two lines each."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-beaumont-2026.pdf",
                                           "beaumont", country="France")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_fifteen_bouts_all_decided(self):
        self.assertEqual(15, len(bouts(self.rows)))
        self.assertTrue(all(b.status == "decided" for b in bouts(self.rows)))

    def test_the_winner_is_one_of_the_two_fighters(self):
        for bout in bouts(self.rows):
            self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)

    def test_no_corner_is_claimed(self):
        """rouge and bleu are a corner; this sheet never prints one."""
        self.assertEqual({""}, {b.winner_corner for b in bouts(self.rows)})

    def test_the_sheet_dates_itself(self):
        self.assertEqual("2026-03-14", self.t.start_date)
        self.assertEqual("Beaumont Lès Valence", self.t.city)

    def test_the_series_keeps_two_65_kg_competitions_apart(self):
        labels = {b.category for b in bouts(self.rows)}
        self.assertIn("Elite A Men -65 kg", labels)
        self.assertIn("Elite B Men -65 kg", labels)

    def test_a_name_is_not_cut_in_half_by_the_club_column(self):
        found = {b.red: b.red_club for b in bouts(self.rows)}
        self.assertEqual("VENISSIEUX BOXE FRANCAISE", found["SEDDIK KHODJA Linda"])
        self.assertEqual("Scheffler Boxing Club", found["FIEUTELOT Nicolas"])

    def test_a_mixed_case_club_is_not_pulled_into_the_name(self):
        clubs = {b.blue_club for b in bouts(self.rows)}
        self.assertIn("Saint fons gerland savate", clubs)

    def test_hors_combat_is_an_abandon_and_keeps_the_round_it_printed(self):
        stopped = [b for b in bouts(self.rows) if b.decision == "abandon"]
        self.assertEqual(1, len(stopped))
        self.assertEqual("FIEUTELOT Nicolas", stopped[0].winner)
        self.assertIn("HC", stopped[0].decision_detail)

    def test_no_podium_is_invented_from_a_sheet_that_names_no_round(self):
        """The file name says these are semi-finals; the document does not."""
        self.assertEqual([], placings(self.rows))
        self.assertEqual({""}, {b.phase for b in bouts(self.rows)})


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class DashSeparatedClubs(unittest.TestCase):
    """Riaillé 2026: numbered blocks, "NAME - CLUB (dd)", Espoir and Premium."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-riaille-2026.pdf", "riaille")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_twenty_two_numbered_bouts(self):
        self.assertEqual(22, len(bouts(self.rows)))

    def test_the_dash_splits_the_club_off_and_the_name_keeps_its_hyphen(self):
        first = bouts(self.rows)[0]
        self.assertEqual("LECLERE-MESSEBEL Éléonore", first.red)
        self.assertEqual("U S CRETEIL", first.red_club)

    def test_a_dash_with_no_space_before_it_still_splits(self):
        found = {b.blue: b.blue_club for b in bouts(self.rows)}
        self.assertEqual("PLANETE BORG", found["GRUCHOT Loretta"])

    def test_the_departement_never_reaches_the_club(self):
        for bout in bouts(self.rows):
            self.assertNotIn("(", bout.red_club + bout.blue_club, bout.bout_id)

    def test_the_two_series_on_the_sheet_are_kept_apart(self):
        heads = {b.category.split()[0] for b in bouts(self.rows)}
        self.assertEqual({"Premium", "Espoir"}, heads)

    def test_the_section_titles_are_not_read_as_competitors(self):
        people = {b.red for b in bouts(self.rows)} | {b.blue for b in bouts(self.rows)}
        self.assertNotIn("Deuxième partie", people)
        self.assertNotIn("Première partie", people)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class NoWinnerNamed(unittest.TestCase):
    """The cadets sheet prints two names per class and no verdict at all."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-cadets-2026.pdf", "cadets")

    def test_the_J_on_every_class_code_survives_into_the_category(self):
        """The word "cadet" is nowhere on this sheet; the J is on every line.

        Dropping it filed seventeen cadet bouts as "Women -48 kg", which is
        what a senior bout at the same weight is filed as.
        """
        self.assertEqual({""}, {b.age_class for b in bouts(self.rows)})
        self.assertEqual([], [b.bout_id for b in bouts(self.rows)
                              if not b.category.endswith("(J)")])
        self.assertTrue(any("J suffix" in p for p in self.report.problems))

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_seventeen_pairings_none_of_them_resolved(self):
        self.assertEqual(17, len(bouts(self.rows)))
        self.assertEqual({"unresolved"}, {b.status for b in bouts(self.rows)})
        self.assertEqual({""}, {b.winner for b in bouts(self.rows)})

    def test_the_printed_order_is_not_read_as_a_podium(self):
        """Champion first is the habit of every sibling sheet, not a fact here."""
        self.assertEqual([], placings(self.rows))

    def test_the_read_says_so_out_loud(self):
        self.assertTrue(any("name no winner" in p for p in self.report.problems))

    def test_the_club_in_brackets_is_split_off(self):
        first = bouts(self.rows)[0]
        self.assertEqual("LECLERE-MESSEBEL ELÉONORE", first.red)
        self.assertEqual("U S CRETEIL", first.red_club)
        self.assertEqual("Women -48 kg (J)", first.category)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class RoundInTheHeading(unittest.TestCase):
    """Maubeuge 2023: the heading names the round, and the verdict the winner."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-maubeuge-2023.pdf", "maubeuge")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_five_bouts_on_their_stated_rounds(self):
        found = collections.Counter(b.phase for b in bouts(self.rows))
        self.assertEqual({"quarter": 4, "r16": 1}, dict(found))

    def test_the_verdict_names_the_winner_wherever_it_is_printed(self):
        """On one of these five bouts it sits on the second line, not the first."""
        found = {(b.red, b.blue): b.winner for b in bouts(self.rows)}
        self.assertEqual("RODRIGUES Mathias",
                         found[("SIMILLE Saian", "RODRIGUES Mathias")])
        self.assertEqual("POCHET Alix", found[("POCHET Alix", "BEURRE Romane")])

    def test_a_club_with_no_departement_is_still_split_off(self):
        found = {b.red: b.red_club for b in bouts(self.rows)}
        self.assertEqual("BF HERMINOISE", found["BOISMOREAU Willan"])

    def test_no_podium_from_a_quarter_final(self):
        self.assertEqual([], placings(self.rows))


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class TwoCornerTable(unittest.TestCase):
    """Torreilles: a Décision column that names the method and not the winner."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-torreilles-2024.pdf",
                                           "torreilles")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_one_hundred_and_thirteen_bouts_none_of_them_decided(self):
        self.assertEqual(113, len(bouts(self.rows)))
        self.assertEqual({"unresolved"}, {b.status for b in bouts(self.rows)})

    def test_the_red_corner_is_not_read_as_the_winner(self):
        self.assertEqual({""}, {b.winner for b in bouts(self.rows)})
        self.assertEqual({""}, {b.winner_corner for b in bouts(self.rows)})

    def test_the_method_is_kept_even_though_the_winner_is_not(self):
        found = collections.Counter(b.decision for b in bouts(self.rows))
        self.assertGreater(found["points"], 90)
        self.assertIn("forfait", found)
        self.assertEqual(0, found[""])

    def test_the_surname_and_the_given_name_are_read_as_one_person(self):
        first = bouts(self.rows)[0]
        self.assertEqual("DEMASSIEUX Fiby", first.red)
        self.assertEqual("MARAMICI Marguerite", first.blue)
        self.assertEqual("CICER", first.red_club)

    def test_a_section_whose_header_omits_the_given_name_still_reads_it(self):
        """The last enceinte's header names only NOM and Club."""
        found = {b.red for b in bouts(self.rows)}
        self.assertIn("DENISART Tanguy", found)
        self.assertIn("CAZAT Enzo", found)

    def test_a_weight_class_never_holds_both_genders(self):
        by_class = collections.defaultdict(set)
        for bout in bouts(self.rows):
            by_class[bout.category].add(bout.gender)
        self.assertEqual([], [c for c, g in by_class.items() if len(g) > 1])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class WinnerColumn(unittest.TestCase):
    """The 2e série championship: the one table in this pile with a Vainqueur."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-c2m-2023.pdf", "c2m")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_seventy_six_decided_bouts(self):
        self.assertEqual(76, len(bouts(self.rows)))
        self.assertEqual({"decided"}, {b.status for b in bouts(self.rows)})

    def test_the_winner_is_always_one_of_the_two(self):
        for bout in bouts(self.rows):
            self.assertIn(bout.winner, (bout.red, bout.blue), bout.bout_id)

    def test_the_niveau_column_becomes_a_real_phase(self):
        found = collections.Counter(b.phase for b in bouts(self.rows))
        self.assertEqual({"poule": 63, "semi": 13}, dict(found))

    def test_the_last_page_is_read_in_the_same_columns_as_the_first(self):
        semis = [b for b in bouts(self.rows) if b.phase == "semi"]
        pairs = {(b.red, b.blue) for b in semis}
        self.assertIn(("MARTIN Fabien", "PINTO Dylan"), pairs)
        self.assertIn(("ROUX Swann", "THIEULIN Jonathan"), pairs)

    def test_no_weight_class_is_invented_where_the_sheet_prints_none(self):
        self.assertEqual({""}, {b.weight_kg for b in bouts(self.rows)})
        self.assertEqual({"2e Série Senior Men"}, {b.category for b in bouts(self.rows)})

    def test_the_sheets_own_title_is_not_read_as_a_bout(self):
        people = {b.red for b in bouts(self.rows)}
        self.assertFalse([p for p in people if "Championnat" in p])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class RunningOrder(unittest.TestCase):
    """The Espoirs qualifier: a timetable with COIN ROUGE and COIN BLEU."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-tq-espoirs-2024.pdf", "tq-esp")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_fifty_six_bouts_over_two_days(self):
        self.assertEqual(56, len(bouts(self.rows)))
        self.assertEqual({"2024-12-21", "2024-12-22"},
                         {b.date for b in bouts(self.rows)})

    def test_the_verdict_codes_are_read_but_not_turned_into_a_winner(self):
        self.assertEqual({"unresolved"}, {b.status for b in bouts(self.rows)})
        self.assertEqual({""}, {b.winner for b in bouts(self.rows)})
        self.assertEqual(0, sum(1 for b in bouts(self.rows) if not b.decision))

    def test_the_poule_letter_and_the_semi_finals_are_kept(self):
        self.assertEqual({"A", "B", "C"},
                         {b.poule for b in bouts(self.rows) if b.poule})
        self.assertEqual(4, sum(1 for b in bouts(self.rows) if b.phase == "semi"))

    def test_a_long_name_next_to_a_long_club_is_still_four_fields(self):
        found = {(b.red, b.blue) for b in bouts(self.rows)}
        self.assertIn(("BERFROI Terry", "CAVROT--WESTERLINCK Ethan"), found)
        self.assertIn(("PICHARD Axel", "RICHARD-BENGOECHEA Luken"), found)

    def test_a_club_that_wrapped_onto_its_own_line_is_folded_back(self):
        found = {(b.red, b.blue): b.blue_club for b in bouts(self.rows)}
        self.assertEqual("AVENIR SPORTIF D’ORLY",
                         found[("BERTHIER Arthur", "EL MIR Abderrahmane")])

    def test_every_bout_carries_a_time(self):
        self.assertEqual([], [b.bout_id for b in bouts(self.rows) if not b.time])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class StatedWinnersMergedNotDuplicated(unittest.TestCase):
    """The juniors qualifier prints its two M60 semi-finals twice: once in the
    table with no winner, once as a block that names one."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-tq-juniors-2025.pdf", "tqj")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_the_two_semi_finals_are_resolved_and_not_added_again(self):
        self.assertEqual(24, len(bouts(self.rows)))
        decided = [b for b in bouts(self.rows) if b.status == "decided"]
        self.assertEqual(2, len(decided))
        self.assertEqual({"semi"}, {b.phase for b in decided})
        self.assertEqual({"BABAGBETO Napua", "BEN ARIEN Tony"},
                         {b.winner for b in decided})

    def test_each_resolved_row_is_reported(self):
        said = [p for p in self.report.problems if "resolved from it" in p]
        self.assertEqual(2, len(said))

    def test_the_bout_numbers_that_are_missing_stay_missing(self):
        """The sheet numbers its bouts 1-29 and prints only 24 of them."""
        self.assertEqual(24, len(bouts(self.rows)))


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class PouleTable(unittest.TestCase):
    """The minimes championship: the federation's own poule standings."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-minimes-2026.pdf", "minimes")

    def test_the_age_class_is_read_off_the_sheets_own_footer(self):
        """"FFSAVATE - Résultat championnat Avenir minime 2026", on every page.

        Not off the manifest, and not off the URL: the read is given no age
        class at all here and still files these as minimes, because the sheet
        says so in the place a sheet says what it is.
        """
        self.assertEqual({"Minime"}, {p.age_class for p in placings(self.rows)})
        self.assertIn("minime", self.report.notes["age_class_from"].lower())
        self.assertTrue(all(p.category.startswith("Minime ")
                            for p in placings(self.rows)))

    def test_the_J_on_every_class_code_survives_into_the_category(self):
        self.assertEqual([], [p.placing_id for p in placings(self.rows)
                              if not p.category.endswith("(J)")])

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_every_competitor_on_the_sheet_is_placed(self):
        """Eighty-eight are listed; four carry Forfait where a rank belongs."""
        self.assertEqual(84, len(placings(self.rows)))
        self.assertEqual(21, len({p.category for p in placings(self.rows)}))
        self.assertEqual([], bouts(self.rows))

    def test_a_class_printed_without_its_own_header_is_still_read(self):
        found = [p for p in placings(self.rows)
                 if p.category == "Minime Men -45 kg (J)"]
        self.assertEqual(3, len(found))
        self.assertEqual("Yassin AY", [p.fighter for p in found if p.rank == "1"][0])
        self.assertTrue(any("no header row of its own" in p
                            for p in self.report.problems))

    def test_a_club_called_savate_forme_is_not_mistaken_for_another_sport(self):
        """Savate Forme Body Boxing enters minimes; savate forme is a discipline."""
        found = [p for p in placings(self.rows) if p.fighter == "Evan PAMART"]
        self.assertEqual(1, len(found))
        self.assertEqual("Savate Forme Body Boxing", found[0].club)

    def test_a_forfait_is_reported_unranked_rather_than_given_a_rank(self):
        forfeits = [p for p in self.report.problems if "Forfait" in p]
        self.assertTrue(forfeits)
        self.assertNotIn("Forfait", {p.rank for p in placings(self.rows)})

    def test_every_rank_is_a_finishing_position(self):
        for placing in placings(self.rows):
            self.assertTrue(placing.rank.isdigit(), placing.fighter)
            self.assertGreaterEqual(int(placing.rank), 1)

    def test_a_poule_ranks_each_of_its_competitors_once(self):
        by_class = collections.defaultdict(list)
        for placing in placings(self.rows):
            by_class[placing.category].append(placing.rank)
        for label, ranks in by_class.items():
            self.assertEqual(len(ranks), len(set(ranks)), label)

    def test_the_first_poule_is_read_in_the_right_columns(self):
        first = [p for p in placings(self.rows)
                 if p.category.startswith("Minime Women -42 kg")]
        found = {p.fighter: (p.rank, p.club) for p in first}
        self.assertEqual(("1", "B.F.S. Club Thiernois"), found["Maeva DARDENNE"])
        self.assertEqual(("4", "Gant d'Argent Lille Sud"), found["Lina SCHEIT"])

    def test_the_columns_the_schema_cannot_hold_are_named_in_the_report(self):
        self.assertIn("poule_columns_dropped", self.report.notes)


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class DottedLeaders(unittest.TestCase):
    """The 2013 Espoirs finals, whose columns are held apart by dot runs."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-espoirs-finales-2013.pdf",
                                           "espoirs-2013", age_class="Espoir")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_fourteen_finals_and_twenty_eight_placings(self):
        self.assertEqual(14, len(bouts(self.rows)))
        self.assertEqual(28, len(placings(self.rows)))
        self.assertEqual({"final"}, {b.phase for b in bouts(self.rows)})

    def test_the_weight_word_is_not_glued_to_the_name(self):
        people = {b.red for b in bouts(self.rows)} | {b.blue for b in bouts(self.rows)}
        self.assertIn("CANO Sophie", people)
        self.assertFalse([p for p in people if "Mouches" in p or "Coqs" in p])

    def test_the_verdict_can_sit_on_either_line(self):
        found = {(b.red, b.blue): b.winner for b in bouts(self.rows)}
        self.assertEqual("CANO Sophie", found[("CANO Sophie", "ARAUX Brunella")])
        self.assertEqual("ROBIN Adeline",
                         found[("GONZALES Cynthia", "ROBIN Adeline")])

    def test_a_club_with_no_departement_is_still_a_club(self):
        found = {b.blue: b.blue_club for b in bouts(self.rows)}
        self.assertEqual("ADAC 74", found["SCHEFFLER Adrien"])

    def test_the_gold_is_the_fighter_the_sheet_says_won(self):
        golds = {p.category: p.fighter for p in placings(self.rows) if p.rank == "1"}
        self.assertEqual("ROBIN Adeline", golds["Espoir Women -52 kg"])
        self.assertEqual("POSSAMAI Guillaume", golds["Espoir Men -75 kg"])


@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class TwoColumnStandings(unittest.TestCase):
    """The 2010 national assaut standings: two ranked lists to a page.

    The page is read correctly - the gutter is found, the six classes do not
    interleave, all thirty-four names and positions come out - and then nothing
    is stored, because there is no row in this archive for a position that won
    nothing. The document is a season table, "Classements nationaux saison
    2009/2010"; schema.Placing fills a medal from the rank, so storing it gave
    eighteen women a gold, silver or bronze medal for a competition that never
    took place.
    """

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-classement-2010.pdf",
                                           "classement-2010")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_a_season_ranking_awards_no_medals_because_it_stores_nothing(self):
        self.assertEqual([], self.rows)
        self.assertEqual([], placings(self.rows))
        self.assertEqual([], bouts(self.rows))

    def test_what_was_read_and_refused_is_named_in_the_report(self):
        refused = self.report.notes["standings_refused"]
        self.assertEqual(34, len(refused))
        self.assertIn("Mouches Women -48 kg 1 LEBORGNE Audrey", refused)
        self.assertIn("Légères Women -60 kg 1 BOISBINEUF Cécile", refused)
        self.assertTrue(any("not a competition" in p
                            for p in self.report.problems))

    def test_the_two_printed_columns_are_still_not_interleaved(self):
        """The refusal is about the schema, not about the reading.

        A line is "<label> <rank> <SURNAME> <forename>" and the label's only
        figures are the hyphen-bound kilogram, so the rank is the line's only
        bare integer."""
        by_class = collections.defaultdict(list)
        for line in self.report.notes["standings_refused"]:
            tokens = line.split()
            bare = [i for i, t in enumerate(tokens) if t.isdigit()]
            self.assertEqual(1, len(bare), line)
            by_class[" ".join(tokens[:bare[0]])].append(int(tokens[bare[0]]))
        for label, ranks in by_class.items():
            self.assertEqual(sorted(ranks), sorted(set(ranks)), label)
            self.assertEqual(1, min(ranks), label)


class PalmaresPage(unittest.TestCase):
    """The 2014 Elite A palmarès, as the federation's own site published it."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.rows, cls.report = read("ffsavate-palmares-2014.html",
                                           "palmares-2014", year="2014")

    def test_every_row_is_canonical(self):
        canonical(self, self.rows)

    def test_fourteen_finals_with_a_champion_and_a_runner_up(self):
        self.assertEqual(14, len(bouts(self.rows)))
        self.assertEqual(28, len(placings(self.rows)))
        self.assertEqual({"final"}, {b.phase for b in bouts(self.rows)})

    def test_the_champion_takes_the_gold(self):
        golds = {p.category: p.fighter for p in placings(self.rows) if p.rank == "1"}
        self.assertEqual("CHAMANE Samya", golds["Women -48 kg"])
        self.assertEqual("LATIFI Loïck", golds["Men -56 kg"])

    def test_a_method_that_wraps_across_two_lines_is_read_whole(self):
        found = {b.winner: b.decision_detail for b in bouts(self.rows)}
        self.assertEqual("Victoire par Hors Combat 4°", found["GOBARDHAN Alvyn"])
        self.assertEqual("abandon",
                         {b.winner: b.decision for b in bouts(self.rows)}["GOBARDHAN Alvyn"])

    def test_the_club_is_split_off_at_the_slash_and_keeps_its_brackets_out(self):
        found = {b.red: b.red_club for b in bouts(self.rows)}
        self.assertEqual("M. DE QUART. CHANTECLER", found["MADISSE Patrick"])
        self.assertEqual("BULL BOXING AMBLAINVILLE", found["LATIFI Loïck"])

    def test_a_name_with_brackets_of_its_own_survives(self):
        people = {b.blue for b in bouts(self.rows)}
        self.assertIn("SURREL (TEBBAKH) Sara", people)


# --------------------------------------------------------------------------
# Choosing a layout, and failing loudly when the choice is wrong
# --------------------------------------------------------------------------

@unittest.skipUnless(pdf.available(), "pdftotext (poppler) is not installed")
class LayoutChoice(unittest.TestCase):
    def test_each_fixture_is_recognised_for_what_it_is(self):
        for name, layout in [
            ("ffsavate-beaumont-2026.pdf", "heading_blocks"),
            ("ffsavate-riaille-2026.pdf", "heading_blocks"),
            ("ffsavate-cadets-2026.pdf", "heading_blocks"),
            ("ffsavate-maubeuge-2023.pdf", "heading_blocks"),
            ("ffsavate-minimes-2026.pdf", "poule_table"),
            ("ffsavate-torreilles-2024.pdf", "corner_table"),
            ("ffsavate-tq-juniors-2025.pdf", "corner_table"),
            ("ffsavate-tq-espoirs-2024.pdf", "running_order"),
            ("ffsavate-c2m-2023.pdf", "winner_column"),
            ("ffsavate-espoirs-finales-2013.pdf", "dotted"),
            ("ffsavate-classement-2010.pdf", "ranking_columns"),
            ("ffsavate-palmares-2014.html", "palmares_html"),
        ]:
            _t, _rows, report = read(name)
            self.assertEqual(layout, report.notes["layout"], name)

    def test_a_manifest_may_override_the_guess_and_the_report_says_so(self):
        _t, _rows, report = sheets.read(
            FIXTURES / "ffsavate-c2m-2023.pdf", "t", {"layout": "winner_column"})
        self.assertEqual("the manifest", report.notes["layout_from"])

    def test_a_wrong_layout_reports_instead_of_raising(self):
        _t, rows, report = sheets.read(
            FIXTURES / "ffsavate-c2m-2023.pdf", "t", {"layout": "ranking_columns"})
        self.assertEqual([], rows)
        self.assertTrue(report.problems)

    def test_an_unknown_layout_is_a_complaint_and_not_a_crash(self):
        _t, rows, report = sheets.read(
            FIXTURES / "ffsavate-c2m-2023.pdf", "t", {"layout": "nonsense"})
        self.assertEqual([], rows)
        self.assertTrue(any("nonsense" in p for p in report.problems))

    def test_a_source_that_cannot_be_read_at_all_does_raise(self):
        with self.assertRaises(FileNotFoundError):
            sheets.read(FIXTURES / "no-such-file.pdf", "t", {})


if __name__ == "__main__":
    unittest.main()
