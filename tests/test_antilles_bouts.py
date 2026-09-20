"""The Guadeloupe adapter, against nine of the league's own articles.

Every fixture here is a real page from liguesavateguadeloupe.com, kept whole
apart from the site furniture around the article. They were chosen because each
one breaks a different assumption, and between them they cover the four ways
this corpus can turn into rows that never happened:

  * bouts in another sport, in identical prose, under their own heading
  * demonstrations, which have two names, no result, and are not bouts
  * a stated non-decision, which is a real bout nobody won
  * a winner named by a surname that is spelt differently from the fighter's

So the assertions are not counts of rows for their own sake. They ask whether
the winner of each bout is one of the two people in it, whether the article's
English-boxing card stayed out, whether an exhibition produced nothing, and
whether the bout the article says had no decision is stored unresolved rather
than dropped or guessed.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import antilles_bouts
from savate.schema import Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name, slug="gp-test", meta=None, **options):
    tournament, rows, report = antilles_bouts.read(
        FIXTURES / name, slug, meta or {}, **options)
    bouts = [r for r in rows if isinstance(r, Bout)]
    placings = [r for r in rows if isinstance(r, Placing)]
    return tournament, bouts, placings, report


def page(markup, slug="gp-test", headline="T"):
    """Read a scrap of article markup without going near a file.

    `headline` is the article's own title line, which is where several of these
    pages put the only date they have - so a test about dating the sheet has to
    be able to set it.
    """
    import tempfile
    body = (f'<title>{headline} - Ligue de Guadeloupe de Savate Boxe '
            'Française</title>'
            f'<article><h2 itemprop="headline">{headline}</h2>'
            f'<div itemprop="articleBody">{markup}</div>'
            '<div class="footer">x</div></article>')
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(body)
        path = f.name
    tournament, rows, report = antilles_bouts.read(path, slug, {})
    return tournament, [r for r in rows if isinstance(r, Bout)], report


class EveryRow(unittest.TestCase):
    """What must hold of every row this adapter produces, from any article."""

    ARTICLES = [
        "gp-2013-creps-poule.html", "gp-2013-creps-tallies.html",
        "gp-2014-creps-two-line.html", "gp-2015-plage-timoun.html",
        "gp-2016-gosier-timoun.html", "gp-2016-abymes-mixed-sport.html",
        "gp-2017-karukera-challenge.html", "gp-2019-gant-de-bronze.html",
        "gp-2022-petit-challenge.html",
    ]

    def test_every_row_is_canonical(self):
        for name in self.ARTICLES:
            with self.subTest(name):
                _t, bouts, placings, _r = read(name)
                self.assertEqual([], [c for b in bouts for c in check(b)])
                self.assertEqual(
                    [], [c for p in placings for c in check_placing(p)])

    def test_the_winner_is_one_of_the_two_people_in_the_bout(self):
        # The failure this guards against is the one that is invisible once it
        # is in the database: a misspelt surname read as a third person.
        for name in self.ARTICLES:
            _t, bouts, _p, _r = read(name)
            for bout in bouts:
                with self.subTest(f"{name}: {bout.red} v {bout.blue}"):
                    if bout.winner:
                        self.assertIn(bout.winner, (bout.red, bout.blue))
                        self.assertEqual(
                            bout.loser,
                            bout.blue if bout.winner == bout.red else bout.red)
                    else:
                        self.assertEqual("unresolved", bout.status)

    def test_no_corner_is_ever_claimed(self):
        # rouge/bleu is a corner. These articles never say who stood where, so
        # the field stays empty however complete the rest of the row is.
        for name in self.ARTICLES:
            _t, bouts, _p, _r = read(name)
            for bout in bouts:
                with self.subTest(name):
                    self.assertEqual("", bout.winner_corner)

    def test_nobody_fights_themselves(self):
        for name in self.ARTICLES:
            _t, bouts, _p, _r = read(name)
            for bout in bouts:
                with self.subTest(f"{name}: {bout.red}"):
                    self.assertNotEqual(bout.red, bout.blue)

    def test_reading_is_repeatable(self):
        _t, first, _p, _r = read("gp-2016-gosier-timoun.html")
        _t, again, _p, _r = read("gp-2016-gosier-timoun.html")
        self.assertEqual([b.as_dict() for b in first],
                         [b.as_dict() for b in again])


class AnotherSport(unittest.TestCase):
    """The 2016 Abymes card: English boxing first, and longer than the savate.

    This is the document a heading-blind parser fails on, and it fails in the
    worst direction - it reads five English-boxing bouts as savate before it
    reaches a single real one.
    """

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.bouts, _p, cls.report = read(
            "gp-2016-abymes-mixed-sport.html", "gp-2016-abymes")

    def test_only_the_savate_half_of_the_card_is_read(self):
        self.assertEqual(4, len(self.bouts), "9 VS pairs, 4 of them savate")

    def test_the_english_boxing_is_dropped_and_counted(self):
        self.assertEqual({"boxe anglaise": 6}, self.report.notes["other_sport"])
        self.assertTrue(any("boxe anglaise" in p for p in self.report.problems))

    def test_no_english_boxer_became_a_savateur(self):
        people = {b.red for b in self.bouts} | {b.blue for b in self.bouts}
        for boxer in ("MUSNIER CYRIL", "PAREDES FLORENT", "DELANEY JOHN",
                      "SACILE HAILE", "MOYSAN ALEXANDRE", "LEROY PALAMEDE"):
            self.assertNotIn(boxer, people)

    def test_the_savate_bouts_keep_their_own_discipline(self):
        labels = [b.category for b in self.bouts]
        self.assertEqual(["Assaut -85 kg", "Assaut -70 kg",
                          "Combat -80 kg", "Combat -91 kg"], labels)

    def test_a_card_of_two_disciplines_is_not_called_one(self):
        self.assertEqual("", self.tournament.discipline)

    def test_the_class_is_read_from_the_middle_of_the_line(self):
        # "... (ying yang control ) - 85 kg vainqueur FRANCILLETTE"
        self.assertEqual("85", self.bouts[0].weight_kg)
        self.assertEqual("under", self.bouts[0].weight_bound)

    def test_a_fighter_surnamed_junior_is_not_an_age_class(self):
        bout = self.bouts[0]
        self.assertEqual("BARLAGNE JUNIOR", bout.blue)
        self.assertEqual("", bout.age_class)
        self.assertEqual("FRANCILLETTE DENIS", bout.winner)

    def test_canne_de_combat_is_dropped_the_same_way(self):
        _t, bouts, report = page(
            "<p>CANNE DE COMBAT :</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>")
        self.assertEqual([], bouts)
        self.assertEqual({"canne de combat": 1}, report.notes["other_sport"])


class Demonstrations(unittest.TestCase):
    """An exhibition has two names and no result. It is not a bout."""

    def test_a_headed_demo_section_produces_no_rows(self):
        tournament, bouts, _p, report = read(
            "gp-2017-karukera-challenge.html", "gp-2017-karukera")
        self.assertEqual(7, len(bouts), "4 under EN DEMO, 7 under ASSAUTS")
        self.assertEqual(4, report.notes["demonstrations"])
        people = {b.red for b in bouts} | {b.blue for b in bouts}
        for shown in ("COURTOIS BRYAN", "SOUMBO KILLYAN", "COLOT ANTHONY",
                      "DEHER MATHEO", "DELPORTE NATHALIE"):
            self.assertNotIn(shown, people)

    def test_a_demo_line_in_the_middle_of_the_real_ones_is_skipped(self):
        _t, bouts, report = page(
            "<p>A DUPONT (x) VS B DURAND (y) vainqueur : DUPONT</p>"
            "<p>DEMO BOULATE EMRICK (ying yang) et DELOUMEAUX NAYAN (dyn)</p>"
            "<p>C MARTIN (x) VS D BERNARD (y) vainqueur : MARTIN</p>")
        self.assertEqual(2, len(bouts))
        self.assertEqual(1, report.notes["demonstrations"])

    def test_a_demo_written_with_vs_and_a_slash_is_still_a_demo(self):
        _t, bouts, report = page(
            "<p>DEMO/ VITALIS CANDICE VS HOCQUINGHEN ALIA phenix club "
            "toutes les deux</p>")
        self.assertEqual([], bouts)
        self.assertEqual(1, report.notes["demonstrations"])

    def test_a_demo_heading_does_not_swallow_the_bouts_after_it(self):
        # "Pour la DEMO filles ..." opens a demonstration and is followed by
        # the real card with no heading between. A decided bout ends the demo.
        _t, bouts, report = page(
            "<p>Pour la DEMO filles étaient opposées : RILCY NANCY "
            "(kana savate) et GIROUDIERE MARIE-LAURE (dynamik contact)</p>"
            "<p>-70kg PATISSON JEAN-MICHEL (kana savate) VS RESON NICOLAS "
            "(phenix club) vainqueur RESON</p>")
        self.assertEqual(1, len(bouts))
        self.assertEqual(1, report.notes["demonstrations"])


class NoDecision(unittest.TestCase):
    """A bout nobody won is a fact, and a different fact from no bout."""

    def test_a_stated_non_decision_survives_with_its_warnings(self):
        _t, bouts, _p, report = read("gp-2016-gosier-timoun.html")
        undecided = [b for b in bouts if b.status == "unresolved"]
        self.assertEqual(1, len(undecided))
        bout = undecided[0]
        self.assertEqual("VITALIS CANDICE", bout.red)
        self.assertEqual("RILCY VICTORIA", bout.blue)
        self.assertEqual("", bout.winner)
        self.assertEqual("", bout.loser)
        self.assertEqual("", bout.decision)
        self.assertEqual(("3", "3"), (bout.red_warnings, bout.blue_warnings))
        self.assertEqual(11, len(bouts), "10 decided and the non-decision")

    def test_a_cancelled_bout_is_unresolved_rather_than_dropped(self):
        _t, bouts, _p, _r = read("gp-2015-plage-timoun.html")
        undecided = [b for b in bouts if b.status == "unresolved"]
        self.assertEqual(1, len(undecided))
        self.assertEqual("COUDRIEU SHAWN", undecided[0].red)
        self.assertEqual("BOULATE EMRICK", undecided[0].blue)
        self.assertIn("annul", undecided[0].decision_detail)
        self.assertEqual(13, len(bouts))

    def test_a_winner_who_is_neither_fighter_leaves_the_bout_unresolved(self):
        _t, bouts, report = page(
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : MERCIER</p>")
        self.assertEqual(1, len(bouts))
        self.assertEqual("unresolved", bouts[0].status)
        self.assertEqual("", bouts[0].winner)
        self.assertTrue(any("unresolved" in p for p in report.problems))


class TheGrammar(unittest.TestCase):
    """The shapes a bout line takes, and the one question each of them answers."""

    def test_the_verdict_may_come_before_or_after_the_name(self):
        _t, bouts, _p, _r = read("gp-2017-karukera-challenge.html")
        # "... : MICHELY VAINQUEUR UNANIMITE DES JUGES"
        self.assertEqual("MICHELY MANUELLA", bouts[0].winner)
        # "... :VAINQUEUR LADREZEAU MAJORITE DES JUGES" - the order inverts
        self.assertEqual("LADREZEAU GREGORY", bouts[-1].winner)
        self.assertEqual("FEUILLARD STEPHANE", bouts[-1].loser)

    def test_a_club_with_no_brackets_is_split_off_the_name(self):
        _t, bouts, _p, _r = read("gp-2017-karukera-challenge.html")
        self.assertEqual("VAUCHEL CLEMENTINE", bouts[0].red)
        self.assertEqual("DYNAMIK CONTACT", bouts[0].red_club)
        self.assertEqual("MICHELY MANUELLA", bouts[0].blue)
        self.assertEqual("GWADABOXING CLUB", bouts[0].blue_club)

    def test_a_club_the_lexicon_does_not_know_leaves_the_name_whole(self):
        _t, bouts, _r = page(
            "<p>F-70KG DUPONT ALAIN CLUB INCONNU DE NULLE PART VS "
            "DURAND PAUL (phenix club) vainqueur : DURAND</p>")
        self.assertEqual("DUPONT ALAIN CLUB INCONNU DE NULLE PART",
                         bouts[0].red)
        self.assertEqual("", bouts[0].red_club)

    def test_the_verdict_may_be_on_the_following_line(self):
        _t, bouts, _p, _r = read("gp-2014-creps-two-line.html")
        self.assertEqual(6, len(bouts))
        self.assertEqual("BARLAGNE MARIUS", bouts[0].red)
        self.assertEqual("FRANCILLETTE DENIS", bouts[0].blue)
        self.assertEqual("FRANCILLETTE DENIS", bouts[0].winner)
        self.assertEqual(["80", "65", "65", "75", "80", "80"],
                         [b.weight_kg for b in bouts])

    def test_a_women_s_bout_announced_with_gagnante_is_not_lost(self):
        # Keying only on "vainqueur" loses all four women's assauts here.
        _t, bouts, _p, _r = read("gp-2019-gant-de-bronze.html")
        women = [b for b in bouts if b.gender == "Women"]
        self.assertEqual(4, len(women))
        self.assertEqual("EDMOND JOANNIE", women[0].winner)
        self.assertEqual("JORDIER EMMANUELLE", women[1].winner)

    def test_one_article_can_hold_two_disciplines(self):
        tournament, bouts, _p, _r = read("gp-2019-gant-de-bronze.html")
        self.assertEqual(["Assaut"] * 5 + ["Combat"] * 2,
                         [b.category.split()[0] for b in bouts])
        self.assertEqual("", tournament.discipline)

    def test_a_misspelt_winner_is_matched_and_reported_not_invented(self):
        _t, bouts, _p, report = read("gp-2019-gant-de-bronze.html")
        last = bouts[-1]
        # The article prints BANABDELBARI; the fighter is BENABDELBARI MEDHI.
        self.assertEqual("BENABDELBARI MEDHI", last.winner)
        self.assertIn(last.winner, (last.red, last.blue))
        self.assertTrue(report.notes["typo_winners"])

    def test_a_name_typed_twice_is_not_a_double_barrelled_name(self):
        _t, bouts, _p, _r = read("gp-2015-plage-timoun.html")
        stuttered = [b for b in bouts if b.blue.startswith("BOULATE EMRICK")]
        self.assertTrue(stuttered)
        self.assertNotIn("BOULATE BOULATE EMRICK",
                         {b.blue for b in bouts} | {b.red for b in bouts})

    def test_warnings_are_only_recorded_where_the_article_is_unambiguous(self):
        _t, bouts, _p, report = read("gp-2022-petit-challenge.html")
        self.assertEqual(2, len(bouts))
        # "2 avertissements pour chaque tireuse" - both, plainly.
        self.assertEqual(("2", "2"),
                         (bouts[0].red_warnings, bouts[0].blue_warnings))
        # "2 avertissements contre 1" never says whose. Nothing is split.
        self.assertEqual(("", ""),
                         (bouts[1].red_warnings, bouts[1].blue_warnings))
        self.assertTrue(any("avertissement" in p or "warnings" in p
                            for p in report.problems))

    def test_a_participation_list_is_not_a_set_of_bouts(self):
        # The same 2022 article lists nine fighters who fought "sans décision",
        # by club, with no pairings. There is nothing there to pair.
        _t, bouts, _p, _r = read("gp-2022-petit-challenge.html")
        people = {b.red for b in bouts} | {b.blue for b in bouts}
        for listed in ("FABIANO", "BIONVILLE", "RUPAIRE", "MAZABRAUD",
                       "POPOTTE", "HIPPODAN"):
            self.assertNotIn(listed, people)


class ThePoule(unittest.TestCase):
    """The 2013 CREPS challenge, the only article with a bracket in it."""

    @classmethod
    def setUpClass(cls):
        cls.tournament, cls.bouts, cls.placings, cls.report = read(
            "gp-2013-creps-poule.html", "gp-2013-creps")

    def test_the_knockout_lines_are_joined_back_to_the_full_names(self):
        final = next(b for b in self.bouts if b.phase == "final")
        self.assertEqual("PEZERON JOEVIN", final.red)
        self.assertEqual("LADREZEAU GREGORY", final.blue)
        self.assertEqual("LADREZEAU GREGORY", final.winner)

    def test_the_third_place_bout_is_a_bronze_and_its_winner_is_read(self):
        third = next(b for b in self.bouts if b.phase == "bronze")
        self.assertEqual("ROSEMOND JONATHAN", third.red)
        self.assertEqual("WURTZ DIMITRI", third.blue)
        # The article prints ROSEMEND on the deciding line.
        self.assertEqual("ROSEMOND JONATHAN", third.winner)

    def test_no_medal_is_invented_for_a_poule_that_prints_no_podium(self):
        # REGRESSION. This poule used to become four placings carrying gold,
        # silver and bronze. The article prints a final, a 3rd-place bout and
        # no classification at all, and says nothing about any medal being
        # handed out - so the archive gets the two bouts and a note, and the
        # reader is not told about a podium nobody described.
        self.assertEqual([], self.placings)
        self.assertTrue(
            any("no classification" in p and "no medal" in p
                for p in self.report.problems), self.report.problems)

    def test_what_the_two_bouts_do_state_is_said_out_loud(self):
        # Dropping the rows must not drop the fact. The order follows from the
        # final and the 3rd-place bout, and the report says so by name.
        said = " ".join(self.report.problems)
        self.assertIn("LADREZEAU GREGORY beat PEZERON JOEVIN", said)
        self.assertIn("ROSEMOND JONATHAN beat WURTZ DIMITRI", said)

    def test_only_the_poule_s_own_bouts_carry_its_label(self):
        labelled = [b for b in self.bouts if b.poule]
        self.assertEqual(4, len(labelled))
        self.assertTrue(all("de 4 tireurs" in b.poule for b in labelled))
        self.assertEqual("Assaut Senior Men -75 kg", labelled[0].category)

    def test_a_poule_with_no_decided_final_yields_no_placings(self):
        _t, bouts, report = page(
            "<p>Poule ASSAUT SENIOR MASCULIN de 4 tireurs - 75 kg :</p>"
            "<p>match 1 : DUPONT ALAIN (x) VS DURAND PAUL (y) , "
            "DUPONT VAINQUEUR à l'unanimité .</p>")
        self.assertEqual(1, len(bouts))
        self.assertEqual("Poule ASSAUT SENIOR MASCULIN de 4 tireurs - 75 kg",
                         bouts[0].poule)


class WhatTheArticleSays(unittest.TestCase):
    """Dates, classes and the difference between read and inferred."""

    def test_the_article_dates_itself_where_it_can(self):
        tournament, _b, _p, report = read("gp-2022-petit-challenge.html")
        self.assertEqual("2022-04-09", tournament.start_date)
        self.assertEqual("2022", tournament.year)
        self.assertNotIn("year_inferred", report.notes)

    def test_a_year_is_not_manufactured_by_deleting_a_digit(self):
        # REGRESSION, and the worst of them: the Martinique trip prints
        # "Samedi 18 avril 20145" and the St-Félix challenge is headlined
        # "04/06/20416". Neither "2015" nor "2016" appears anywhere in either
        # page; both used to be produced by deleting one digit and checking the
        # weekday, and 21 rows carried a full ISO date nobody had published.
        for printed in ("Samedi 18 avril 20145", "Le 18 avril 20145"):
            with self.subTest(printed):
                _t, bouts, report = page(
                    f"<p>{printed} 6 jeunes tireurs</p>"
                    "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : "
                    "DUPONT</p>")
                self.assertEqual("", _t.start_date)
                self.assertEqual("", _t.year)
                # The bout is still read. It is the date that is unreadable.
                self.assertEqual(1, len(bouts))
                self.assertEqual("", bouts[0].date)
                self.assertTrue(any("20145" in p and "not a year" in p
                                    for p in report.problems),
                                report.problems)

    def test_a_five_digit_year_in_the_headline_is_no_better(self):
        # REGRESSION: the headline is where doc 272's "04/06/20416" lives, and
        # the numeric branch took the same repair the long-form one did.
        _t, bouts, report = page(
            "<p>CARRE MANY (x) VS DECHADIRAC TYRON (y) vainqueur : "
            "DECHADIRAC à l'unanimité</p>", headline="CHALLENGE 04/06/20416")
        self.assertEqual(("", ""), (_t.start_date, _t.year))
        self.assertEqual("", bouts[0].date)
        self.assertTrue(any("20416" in p for p in report.problems),
                        report.problems)

    def test_the_year_is_never_taken_from_the_address(self):
        # REGRESSION: an undated article used to take the year out of its own
        # URL slug. A filename is not something a competition says about itself.
        import tempfile
        folder = tempfile.mkdtemp()
        path = Path(folder) / "140-challenge-23-novembre-2013.html"
        path.write_text(
            '<title>X - Ligue de Guadeloupe de Savate Boxe Française</title>'
            '<article><h2 itemprop="headline">CHALLENGE DE GOYAVE</h2>'
            '<div itemprop="articleBody">'
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>"
            '</div><div class="footer">x</div></article>', encoding="utf-8")
        tournament, rows, report = antilles_bouts.read(path, "gp-test", {})
        self.assertEqual(("", ""), (tournament.start_date, tournament.year))
        self.assertEqual("", rows[0].date)
        self.assertTrue(any("left undated" in p for p in report.problems))

    def test_a_year_printed_in_the_headline_is_read(self):
        # The other half of the same rule: "CHALLENGE 3 RIVIERES 2018" is the
        # page saying 2018, so 2018 is read - with no date, because it gives
        # no day, and with no complaint, because nothing was inferred.
        tournament, _b, report = page(
            "<p>C'est en pleine air que c'est disputé la compétition</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>",
            headline="CHALLENGE 3 RIVIERES 2018")
        self.assertEqual("2018", tournament.year)
        self.assertEqual("", tournament.start_date)
        self.assertEqual([], report.problems)

    def test_a_weekday_checks_a_date_the_headline_printed(self):
        # REGRESSION: the weekday test only ran where the weekday stood beside
        # the date, so "CHALLENGE DE GOYAVE 22/11/2019" over a body reading "en
        # ce samedi apres-midi" went unremarked - 13 rows on a Friday under a
        # line calling it a Saturday. The check belongs to the document.
        _t, bouts, report = page(
            "<p>LE CLUB DE GOYAVE nous a accueilli , avec 13 assauts de "
            "poussin à senior en ce samedi apres-midi</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>",
            headline="CHALLENGE DE GOYAVE 22/11/2019")
        # The date is what the page states, and so is the weekday. They do not
        # agree, and saying so is the only honest thing left to do.
        self.assertEqual("2019-11-22", bouts[0].date)
        self.assertTrue(any("vendredi" in p and "samedi" in p
                            for p in report.problems), report.problems)

    def test_a_weekday_that_agrees_is_not_a_complaint(self):
        _t, _b, report = page(
            "<p>Un challenge en ce samedi apres-midi</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>",
            headline="CHALLENGE DE GOYAVE 23/11/2019")
        self.assertEqual([], report.problems)

    def test_a_weekday_that_is_wrong_does_not_delete_the_date(self):
        _t, _b, report = page(
            "<p>Voici les résultats de la compétition samedi 22 novembre 2015</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>")
        self.assertEqual("2015-11-22", _t.start_date)
        self.assertTrue(any("samedi" in p for p in report.problems))

    def test_the_class_is_named_by_the_bound_the_article_prints(self):
        _t, bouts, _r = page(
            "<p>F-70KG DUPONT ALAIN (phenix club) VS DURAND PAULE "
            "(moule savate) vainqueur : DUPONT</p>"
            "<p>+85 kg MARTIN LUC (phenix club) VS BERNARD JEAN "
            "(moule savate) vainqueur : MARTIN</p>")
        self.assertEqual(("70", "under", "Women"),
                         (bouts[0].weight_kg, bouts[0].weight_bound,
                          bouts[0].gender))
        self.assertEqual(("85", "over"),
                         (bouts[1].weight_kg, bouts[1].weight_bound))

    def test_a_round_format_is_not_a_weight_class(self):
        _t, bouts, _r = page(
            "<p>- ASSAUT MINIME en 3x1'30</p>"
            "<p>DUPONT ALAIN (phenix club) VS DURAND PAUL (moule savate) "
            "vainqueur : DUPONT à l'unanimité des juges en 3x2'</p>")
        self.assertEqual("", bouts[0].weight_kg)
        self.assertEqual("Minime", bouts[0].age_class)

    def test_an_article_that_lists_no_bouts_says_so_rather_than_inventing(self):
        tournament, bouts, placings, report = read(
            "gp-2013-creps-tallies.html", "gp-2013-tallies")
        self.assertEqual([], bouts)
        self.assertEqual([], placings)
        self.assertTrue(any("no bouts read" in p for p in report.problems))
        # It still dates itself, which is worth keeping even with no rows.
        self.assertEqual("2013-06-22", tournament.start_date)

    def test_a_manifest_entry_always_wins_over_what_was_read(self):
        tournament, _b, _p, _r = read(
            "gp-2019-gant-de-bronze.html", "gp-2019",
            {"name": "Gala Gant de Bronze", "discipline": "assaut",
             "level": "regional", "country": "France"})
        self.assertEqual("Gala Gant de Bronze", tournament.name)
        self.assertEqual("assaut", tournament.discipline)
        self.assertEqual("regional", tournament.level)
        self.assertEqual("France", tournament.country)

    def test_one_discipline_can_be_asked_for_on_its_own(self):
        _t, bouts, _p, _r = read("gp-2019-gant-de-bronze.html",
                                 discipline="combat")
        self.assertEqual(2, len(bouts))
        self.assertTrue(all(b.category.startswith("Combat") for b in bouts))


class BadData(unittest.TestCase):
    """read() reports and skips. It does not raise on a broken article."""

    def test_rubbish_lines_are_skipped_with_a_complaint(self):
        _t, bouts, report = page(
            "<p>A VS</p><p>VS B</p><p>VS</p>"
            "<p>DUPONT ALAIN (x) VS DURAND PAUL (y) vainqueur : DUPONT</p>")
        self.assertEqual(1, len(bouts))
        self.assertEqual(3, report.notes["skipped"])
        self.assertTrue(all(check(b) == [] for b in bouts))

    def test_a_page_that_is_not_an_article_is_reported_not_raised(self):
        _t, bouts, report = page("<p>Bonjour tout le monde .</p>")
        self.assertEqual([], bouts)
        self.assertTrue(report.problems)

    def test_a_source_that_cannot_be_read_at_all_still_raises(self):
        with self.assertRaises(FileNotFoundError):
            antilles_bouts.read(FIXTURES / "no-such-article.html", "x", {})


if __name__ == "__main__":
    unittest.main()
