"""Tests for weight class normalization in build_db and normalize."""

from dataclasses import dataclass

import pytest

from build_db import _UNI_ADAPTERS, normalise
from savate.normalize import weight as norm
from savate.schema import Bout, Placing


# Minimal Bout for tests – only the fields the normalization path touches.
@dataclass
class _Bout:
    bout_id: str
    tournament: str
    weight_kg: str = ""
    weight_bound: str = ""
    gender: str = ""
    category: str = ""
    red: str = ""
    blue: str = ""
    winner: str = ""
    loser: str = ""
    red_club: str = ""
    blue_club: str = ""
    red_country: str = ""
    blue_country: str = ""
    red_weighed: str = ""
    blue_weighed: str = ""
    phase: str = ""
    poule: str = ""
    date: str = ""
    time: str = ""
    ring: str = ""
    decision: str = ""
    decision_detail: str = ""
    status: str = ""
    result_source: str = ""


# Minimal Placing for tests.
@dataclass
class _Placing:
    placing_id: str
    tournament: str
    weight_kg: str = ""
    weight_bound: str = ""
    gender: str = ""
    category: str = ""
    fighter: str = ""
    country: str = ""
    rank: str = ""
    medal: str = ""
    club: str = ""
    weighed: str = ""
    age_class: str = ""
    result_source: str = ""


class TestNormalizeWeight:
    """normalize.weight() corrections."""

    def test_seventy_six_becomes_seventy_five(self):
        kg, bound = norm("76", "under")
        assert kg == "75"
        assert bound == "under"

    def test_eighty_two_becomes_eighty_five_under(self):
        kg, bound = norm("82", "under")
        assert kg == "85"
        assert bound == "under"

    def test_eighty_two_becomes_eighty_five_over(self):
        kg, bound = norm("82", "over")
        assert kg == "85"
        assert bound == "over"

    def test_unchanged_weight(self):
        kg, bound = norm("75", "under")
        assert kg == "75"
        assert bound == "under"

    def test_fifty_under_university_women_becomes_forty_eight(self):
        """University/FFSU -50 kg women → -48 kg."""
        kg, bound = norm("50", "under", gender="Women",
                         adapter="savate_ranked_list")
        assert kg == "48"
        assert bound == "under"

    def test_fifty_under_university_men_becomes_fifty_six(self):
        """University/FFSU -50 kg men → -56 kg."""
        kg, bound = norm("50", "under", gender="Men",
                         adapter="universitaire")
        assert kg == "56"
        assert bound == "under"

    def test_fifty_under_youth_unaffected(self):
        """Youth adapters should NOT correct -50 kg."""
        kg, bound = norm("50", "under", gender="Men",
                         adapter="cesav_ranking")
        assert kg == "50"
        assert bound == "under"

    def test_fifty_under_unknown_adapter_unaffected(self):
        """Unknown adapter should NOT correct -50 kg."""
        kg, bound = norm("50", "under", gender="Women",
                         adapter="unknown_adapter")
        assert kg == "50"
        assert bound == "under"

    def test_uni_adapters_set(self):
        assert "savate_ranked_list" in _UNI_ADAPTERS
        assert "universitaire" in _UNI_ADAPTERS
        assert "savate_weight_list" in _UNI_ADAPTERS


class TestNormaliseWeightIntegration:
    """Weight normalization in normalise() function."""

    def test_normalise_corrects_seventy_six(self):
        bouts = [Bout(
            tournament="test", bout_id="t-0001",
            weight_kg="76", weight_bound="under", gender="Men",
            category="Men -76 kg",
            red="Alice", blue="Bob", winner="Alice", loser="Bob",
        )]
        placings: list[Placing] = []
        entries = [{"slug": "test", "adapter": "savate_ranked_list"}]
        kept_bouts, kept_placings, notes = normalise(bouts, placings, entries=entries)

        assert kept_bouts[0].weight_kg == "75"
        assert kept_bouts[0].weight_bound == "under"

    def test_normalise_skips_fifty_in_youth(self):
        bouts = [Bout(
            tournament="test", bout_id="t-0001",
            weight_kg="50", weight_bound="under", gender="Men",
            category="Cadet Men -50 kg",
            red="Alice", blue="Bob", winner="Alice", loser="Bob",
        )]
        placings: list[Placing] = []
        entries = [{"slug": "test", "adapter": "cesav_ranking"}]
        kept_bouts, kept_placings, notes = normalise(bouts, placings, entries=entries)

        # -50 kg should NOT be corrected for youth adapter
        assert kept_bouts[0].weight_kg == "50"

    def test_normalise_corrects_eighty_two(self):
        bouts = [Bout(
            tournament="test", bout_id="t-0001",
            weight_kg="82", weight_bound="under", gender="Men",
            category="Men -82 kg",
            red="Alice", blue="Bob", winner="Alice", loser="Bob",
        )]
        placings: list[Placing] = []
        entries = [{"slug": "test", "adapter": "universitaire"}]
        kept_bouts, kept_placings, notes = normalise(bouts, placings, entries=entries)

        assert kept_bouts[0].weight_kg == "85"
        assert kept_bouts[0].weight_bound == "under"