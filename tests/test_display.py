"""Repairing what a PDF text layer damaged, without repairing what it did not.

The risk in this module runs one way. Every test that asserts a repair is worth
one that asserts a *refusal*: a real two-word surname welded into one word, or a
fixture caption promoted to a competitor, would both be invention wearing the
costume of a fix.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import display  # noqa: E402


class TestNameRepair:
    def test_a_lone_capital_rejoins_its_word(self):
        assert display.name("M EANEY ALEKSIS").text == "MEANEY ALEKSIS"
        assert display.name("BUGADA M ARINE").text == "BUGADA MARINE"

    def test_it_rejoins_repeatedly(self):
        assert display.name("DEL M ONTE M ATTEO").text == "DEL MONTE MATTEO"

    def test_a_split_with_no_lone_capital_is_left_visibly_imperfect(self):
        # "AM IM ER" is AMIMER, but every fragment is two letters, so neither
        # the shape rule nor the corpus can reach it. A half-repaired name is
        # the honest outcome; a guessed one is not.
        assert display.name("AM IM ER M EHDI").text == "AM IM ER MEHDI"

    def test_an_initial_is_not_swallowed(self):
        # "J. DUPONT" and "A Kovacs" are initials, not damage.
        assert display.name("J. DUPONT").text == "J. DUPONT"
        assert display.name("A Kovacs").text == "A Kovacs"

    def test_the_weigh_in_note_leaves_the_name(self):
        repaired = display.name("EDGREN JOHANNES (Pesé 82Kg)")
        assert repaired.text == "EDGREN JOHANNES"
        assert "82" in repaired.weight

    def test_the_federation_leaves_the_name_and_is_kept(self):
        repaired = display.name(
            ": ALAMELLE Jianny, Fédération Française de Savate Boxe Française")
        assert repaired.text == "ALAMELLE Jianny"
        assert repaired.club == "Fédération Française de Savate Boxe Française"

    def test_a_parenthesised_country_leaves_the_name_and_is_kept(self):
        repaired = display.name("ALOYAN Artur (Russie)")
        assert repaired.text == "ALOYAN Artur"
        assert repaired.country == "Russie"

    def test_a_column_header_that_ran_into_the_cell_is_trimmed(self):
        # Forty real medallists arrive as "Medal <name>". Rejecting them to
        # avoid one bad row would be the wrong trade.
        assert display.name("Medal Onur KAYA").text == "Onur KAYA"
        assert display.name("forfait David SZABO TOTH").text == "David SZABO TOTH"


class TestNameRefusal:
    def test_a_fixture_caption_is_not_a_competitor(self):
        assert not display.name("– Ivan MURATKIN (Russie) & Damjan MARKOVIC").usable
        assert not display.name("round vs Erick RETAJAC Ibague,").usable

    def test_punctuation_alone_is_not_a_competitor(self):
        assert not display.name("-").usable
        assert not display.name("").usable

    def test_a_refusal_says_why(self):
        assert display.name("-").reason


class TestCorroboratedRepair:
    def test_a_mid_word_split_joins_only_when_the_corpus_attests_it(self):
        words = display.vocabulary(["DIMITRI PETROV", "ANNA JAMES"])
        assert display.name("MICHAT DIM ITRI", words).text == "MICHAT DIMITRI"

    def test_it_declines_without_corroboration(self):
        assert display.name("MICHAT DIM ITRI", set()).text == "MICHAT DIM ITRI"

    def test_a_real_two_word_surname_is_never_welded(self):
        # Every one of these is a legitimate particle. No corpus may join them.
        words = display.vocabulary(["DELMONTE X", "BENMOUSSA X", "VANHOECKE X",
                                    "DIFRANCO X", "LOIACONO X"])
        for name in ("DEL MONTE MATTEO", "BEN MOUSSA Maria", "VAN HOECKE CHRIS",
                     "DI FRANCO ERICA", "Ilaria LO IACONO"):
            assert display.name(name, words).text == name

    def test_a_damaged_name_does_not_vote_for_its_own_fragments(self):
        # "MICHAT DIM ITRI" must not contribute DIM and ITRI to the corpus, or
        # those votes block the very repair the corpus exists to authorise.
        words = display.vocabulary(["MICHAT DIM ITRI", "DIMITRI PETROV"])
        assert "dim" not in words
        assert "dimitri" in words


class TestCountry:
    def test_spellings_of_one_nation_collapse(self):
        for spelling in ("France", "FRA", "Fr", "Francia", "Frankreich"):
            assert display.country(spelling).name == "France"

    def test_the_federation_code_is_read_not_derived(self):
        # Deriving three letters from the name gives SWI and NET, which is
        # wrong for exactly the nations a reader would notice.
        assert display.country("Switzerland").code == "SUI"
        assert display.country("Netherlands").code == "NED"
        assert display.country("Iran").code == "IRI"

    def test_a_parenthesised_cell_still_resolves(self):
        assert display.country("(France)").name == "France"
        assert display.country("ABDINOV (Russie)").name == "Russia"

    def test_the_kerning_split_is_repaired_in_country_cells_too(self):
        assert display.country("Germ Any").name == "Germany"
        assert display.country("Denm Ark").name == "Denmark"

    def test_a_designation_that_is_not_a_nation_keeps_its_name_and_gets_no_flag(self):
        neutral = display.country("Neutral Athlete")
        assert neutral.known
        assert neutral.name == "Neutral Athlete"
        assert neutral.flag == ""

    def test_an_unknown_string_is_reported_not_guessed(self):
        # "Rsf" appears 17 times beside Russian names in 2021 and is almost
        # certainly the Russian Savate Federation. Almost is not verified, so
        # it stays unresolved and renders verbatim rather than becoming a flag.
        assert not display.country("Rsf").known
        assert not display.country("Jakhongir").known

    def test_flags_are_built_from_iso_codes(self):
        assert display.flag("FR") == "🇫🇷"
        assert display.flag("") == ""
        assert display.flag("XX!") == ""
