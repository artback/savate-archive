"""What a competition's own title says about it, and what it must not say.

The classifier's whole licence is that it reads rather than guesses, so the
tests that matter most are the ones asserting it stays silent: a title that does
not name a scope must not acquire one, and a manifest that declares a scope must
not be overruled by a word in a filename.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import competition  # noqa: E402


class TestScope:
    def test_reads_the_continent_a_title_names(self):
        assert competition.scope("Results of the 2019 African Savate Championships") == "african"
        assert competition.scope("Results of the 2019 Asian Savate Championships") == "asian"
        assert competition.scope("Results of the PanAmerican Savate Championships 2019") == "panamerican"
        assert competition.scope("European Assaut Championships 2025") == "european"
        assert competition.scope("World Championship Savate Assaut 2026") == "world"

    def test_french_titles_read_the_same(self):
        assert competition.scope("Championnat du Monde Combat 2011") == "world"
        assert competition.scope("RESULTATS EUROPE ASSAUT 2023 ZAGREB") == "european"

    def test_a_continental_title_is_not_read_as_world(self):
        # "World" appears in neither, and must not be inferred from a savate
        # championship simply being international.
        assert competition.scope("European Championships 2018") == "european"
        assert competition.scope("Results Chungju Masterships 2019") == ""

    def test_silence_stays_silent(self):
        assert competition.scope("Pool results") == ""
        assert competition.scope("") == ""

    def test_the_publishing_federation_is_evidence_only_when_the_title_is_not(self):
        # The French federation publishes its own nationals under bare titles,
        # and the internationals under titles that say so.
        assert competition.scope("Results Seniors2011",
                                 "https://www.ffsavate.com/x.pdf") == "national"
        assert competition.scope("World Youth Boys 2023",
                                 "https://www.ffsavate.com/x.pdf") == "world"


class TestFormat:
    def test_reads_the_format(self):
        assert competition.competition_format("World Cup for 13 & 14 years") == "cup"
        assert competition.competition_format("Results Chungju Masterships 2019") == "masterships"
        assert competition.competition_format("World Championship Assaut 2016") == "championship"

    def test_gala_and_pro_are_recognised(self):
        assert competition.competition_format("Gala de Savate, Paris") == "gala"
        assert competition.competition_format("Savate Pro - Night 3") == "pro"
        assert competition.competition_format("Professional Savate 2024") == "pro"

    def test_a_cup_is_not_a_championship(self):
        assert competition.competition_format("World Cup for 13 & 14 years") != "championship"


class TestLabel:
    def test_french_complements(self):
        assert competition.label("world", "championship") == "Championnat du Monde"
        assert competition.label("european", "championship") == "Championnat d'Europe"
        assert competition.label("african", "championship") == "Championnat d'Afrique"
        assert competition.label("world", "cup") == "Coupe du Monde"

    def test_panamerican_takes_an_adjective_not_a_complement(self):
        assert competition.label("panamerican", "championship") == "Championnat panaméricain"

    def test_pro_and_gala_claim_no_scope(self):
        # A professional card in Paris is Savate Pro, not "Savate Pro national".
        assert competition.label("national", "pro") == "Savate Pro"
        assert competition.label("world", "pro") == "Savate Pro"
        assert competition.label("european", "gala") == "Gala"

    def test_a_missing_half_does_not_produce_a_dangling_label(self):
        assert competition.label("world", "") == "Monde"
        assert competition.label("", "championship") == "Championnat"
        assert competition.label("", "") == ""


class TestTitleRepair:
    def test_url_encoding_is_undone(self):
        assert competition.clean_title(
            "Resultats%20du%20Championnat%20du%20MONDE%20de%20SAVATE%20%20ASSAUT%202012"
        ) == "Resultats du Championnat du MONDE de SAVATE ASSAUT 2012"

    def test_underscores_become_spaces(self):
        assert competition.clean_title("Results_World_Youth_Boys_2023") == \
            "Results World Youth Boys 2023"

    def test_the_year_is_read_from_the_title(self):
        assert competition.stated_year("World Youth 2023 - Pool Results") == "2023"
        assert competition.stated_year("Pool results") == ""


class TestClassify:
    def test_the_manifest_wins_over_the_title(self):
        read = competition.classify("World Championships 2012 - Women",
                                    declared={"level": "european"})
        assert read["level"] == "european"

    def test_a_year_conflict_is_reported_not_resolved(self):
        # The document titles itself 2012 while the manifest says 2020. The
        # classifier says so and changes nothing: a human decides.
        read = competition.classify(
            "Resultats%20du%20Championnat%20du%20MONDE%20de%20SAVATE%20%20ASSAUT%202012",
            declared={"year": "2020"})
        assert read["year"] == "2020"
        assert any("2012" in note and "2020" in note for note in read["notes"])

    def test_it_fills_only_what_the_manifest_left_empty(self):
        read = competition.classify("World Cup for 13 & 14 years",
                                    declared={"level": "", "discipline": "assaut"})
        assert read["level"] == "world"
        assert read["format"] == "cup"
        assert read["discipline"] == "assaut"
        assert read["age_class"] == "Young"
