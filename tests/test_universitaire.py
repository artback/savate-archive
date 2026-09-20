"""The FFSU university adapter, against the shapes its documents actually have.

Four fixtures, saved from sport-u.com so the suite never needs the network:

  sportu-2010-women-poules.xls  the poule workbook - entry list, cross-tables,
                                a bracket, and a classification column
  sportu-2008-ranked.xls        the flat classification, weight forward-filled
  sportu-2022-podium.pdf        the three-line card podium
  sportu-idf-2025-ranked.pdf    the Ile-de-France ranked list
  sportu-2015-teams.pdf         a team sheet, which must yield nothing

The synthetic sheets below are grids typed out by hand, for the shapes that are
rare in the fixtures but are exactly where a reader of this layout goes wrong:
a running-order column that looks like a list of bouts, a drawn scoreline, a
final the classification contradicts, canne de combat mixed into a savate sheet,
and a demonstration.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate.adapters import universitaire as uni
from savate.schema import MEDALS, Bout, Placing, check, check_placing

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WOMEN_2010 = FIXTURES / "sportu-2010-women-poules.xls"
RANKED_2008 = FIXTURES / "sportu-2008-ranked.xls"
PODIUM_2022 = FIXTURES / "sportu-2022-podium.pdf"
IDF_2025 = FIXTURES / "sportu-idf-2025-ranked.pdf"
TEAMS_2015 = FIXTURES / "sportu-2015-teams.pdf"


def read(path, **meta):
    return uni.read(str(path), "test", meta or {})


def bouts(rows):
    return [r for r in rows if isinstance(r, Bout)]


def placings(rows):
    return [r for r in rows if isinstance(r, Placing)]


# --------------------------------------------------------------- the contract

def test_the_adapter_offers_the_three_things_an_adapter_needs():
    assert uni.NAME == "universitaire"
    assert isinstance(uni.DESCRIPTION, str) and uni.DESCRIPTION
    assert callable(uni.read)


def test_a_document_it_cannot_read_is_reported_not_raised(tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not a workbook and not a PDF")
    _t, rows, report = read(junk)
    assert rows == []
    assert report.problems


# ------------------------------------------------------ the poule workbook

@pytest.fixture(scope="module")
def women2010():
    return read(WOMEN_2010, year="2010", country="France")


def test_the_whole_workbook_validates(women2010):
    _t, rows, _r = women2010
    for bout in bouts(rows):
        assert check(bout) == [], f"{bout.bout_id}: {check(bout)}"
    for placing in placings(rows):
        assert check_placing(placing) == []


def test_a_poule_is_read_exactly_as_the_cross_table_prints_it(women2010):
    """Women -50 kg, poule A: six bouts whose columns add to the sheet's TOTAL."""
    _t, rows, _r = women2010
    poule = [b for b in bouts(rows)
             if b.category == "Women -50 kg" and b.phase == "poule"
             and b.poule == "A"]
    assert len(poule) == 6
    scored = {(b.red.split()[0], b.red_points, b.blue.split()[0], b.blue_points)
              for b in poule}
    assert ("HERBET", "3", "HAMOURIT", "1") in scored
    assert ("HERBET", "1", "MAY", "3") in scored
    assert ("HAMOURIT", "3", "TRANCHANT", "1") in scored
    # The sheet's own column sums, which is the check that the scores landed in
    # the right columns: HERBET 7, HAMOURIT 5, MAY 9, TRANCHANT 3.
    tally = {}
    for b in poule:
        tally[b.red] = tally.get(b.red, 0) + int(b.red_points)
        tally[b.blue] = tally.get(b.blue, 0) + int(b.blue_points)
    assert sorted(tally.values()) == [3, 5, 7, 9]


def test_the_totals_the_sheet_prints_are_checked_and_agree(women2010):
    _t, _rows, report = women2010
    totals = report.notes["poule_totals"]
    assert totals["agreed"] >= 40
    assert totals["disagreed"] == []


def test_the_bracket_is_read_and_agrees_with_the_classification(women2010):
    _t, rows, _r = women2010
    final = [b for b in bouts(rows)
             if b.category == "Women -50 kg" and b.phase == "final"]
    assert len(final) == 1
    assert final[0].winner == "MAY MARINE"
    assert final[0].loser == "HERBET AMELIE"
    bronze = [b for b in bouts(rows)
              if b.category == "Women -50 kg" and b.phase == "bronze"]
    assert bronze and bronze[0].winner == "POURCELOT FANNY"
    semis = [b for b in bouts(rows)
             if b.category == "Women -50 kg" and b.phase == "semi"]
    assert len(semis) == 2
    assert {b.winner for b in semis} == {"MAY MARINE", "HERBET AMELIE"}


def test_the_winner_is_always_one_of_the_two_fighters(women2010):
    _t, rows, _r = women2010
    for b in bouts(rows):
        if b.winner:
            assert b.winner in (b.red, b.blue)
            assert b.loser in (b.red, b.blue)
            assert b.winner != b.loser


def test_nobody_fights_themselves(women2010):
    _t, rows, _r = women2010
    assert not [b for b in bouts(rows) if b.red == b.blue]


def test_no_corner_is_ever_claimed(women2010):
    """rouge and bleu are a corner, and none of these sheets states one."""
    _t, rows, _r = women2010
    assert {b.winner_corner for b in bouts(rows)} == {""}
    assert all(b.result_source == "scoresheet"
               for b in bouts(rows) if b.status == "decided")


def test_the_classification_column_becomes_the_placings(women2010):
    _t, rows, _r = women2010
    fifty = sorted((p for p in placings(rows) if p.category == "Women -50 kg"),
                   key=lambda p: int(p.rank))
    assert [(p.rank, p.fighter) for p in fifty] == [
        ("1", "MAY MARINE"), ("2", "HERBET AMELIE"),
        ("3", "POURCELOT FANNY"), ("4", "NISSAS SAHRA")]
    assert [p.medal for p in fifty] == ["gold", "silver", "bronze", ""]
    assert fifty[0].club == "Nice IUT"


def test_entrants_with_no_placing_are_counted_not_ranked(women2010):
    _t, rows, report = women2010
    assert report.notes["unplaced_entrants"]
    assert all(p.rank for p in placings(rows))


def test_the_document_dates_and_names_itself_where_it_can(women2010):
    tournament, _rows, report = women2010
    # These 2010 workbooks print no date at all; nothing is invented for them.
    assert tournament.start_date == ""
    assert tournament.city == ""
    # But they do say "SAVATE - Assauts", which is the discipline.
    assert tournament.discipline == "assaut"
    assert report.notes["discipline_from_document"] == "assaut"


def test_every_name_repair_is_reported(women2010):
    """A surname the bracket spells differently is repaired, never silently."""
    _t, _rows, report = women2010
    repairs = report.notes.get("name_repairs", [])
    assert any("PATTY" in line for line in repairs)


# ----------------------------------------------------- the flat classification

def test_the_flat_sheet_forward_fills_the_weight_class():
    _t, rows, report = read(RANKED_2008, year="2008")
    assert bouts(rows) == []
    got = {(p.category, p.rank): p.fighter for p in placings(rows)}
    assert got[("Men -56 kg", "1")] == "PANNETIER WESTLEY"
    assert got[("Men -56 kg", "3")] == "MARCIANIK ALEXIS"
    # The class is printed once and left blank on the rows beneath it.
    assert got[("Men -60 kg", "4")] == "LEYS THOMAS"
    assert report.notes["unplaced_entrants"]["JG"] > 0
    for placing in placings(rows):
        assert check_placing(placing) == []


def test_the_flat_sheet_reads_the_date_line():
    tournament, _rows, _r = read(RANKED_2008)
    assert tournament.start_date == "2008-03-26"
    assert tournament.end_date == "2008-03-28"
    assert tournament.city == "Rennes"


# ------------------------------------------------------------------ the PDFs

def test_the_podium_card_takes_the_name_from_the_line_above_the_rank():
    _t, rows, report = read(PODIUM_2022, year="2022")
    assert bouts(rows) == []
    got = placings(rows)
    assert len(got) == 34
    first = got[0]
    assert first.fighter == "MESSOUS LOUIZA"
    assert first.club == "UNIVERSITE GUSTAVE EIFFE"
    assert (first.category, first.rank, first.medal) == \
        ("Women -50 kg", "1", "gold")
    assert not [p for p in got if "Champion" in p.fighter]
    assert "+70" in report.notes["classes"]["Women +70 kg"]
    # The team podium printed under the individual results is not a fighter.
    assert not [p for p in got if "Aix-Marseille" in p.fighter]


def test_the_open_class_keeps_its_bound():
    _t, rows, _r = read(PODIUM_2022)
    over = [p for p in placings(rows) if p.category == "Men +82 kg"]
    assert over and {p.weight_bound for p in over} == {"over"}
    assert {p.weight_kg for p in over} == {"82"}


def test_the_regional_sheet_keeps_places_below_the_podium():
    _t, rows, _r = read(IDF_2025, year="2025", level="regional")
    got = [p for p in placings(rows) if p.category == "Men -65 kg"]
    assert [p.rank for p in got] == ["1", "2", "3", "4", "5"]
    assert [p.medal for p in got] == ["gold", "silver", "bronze", "", ""]
    assert got[4].fighter == "ARTHUR Rajaonera Steven"
    assert got[0].club == "UNIVERSITE PARIS CITE STAPS"


def test_a_team_document_yields_no_fighter_row():
    _t, rows, report = read(TEAMS_2015)
    assert rows == []
    assert any("equipe" in p.lower() for p in report.problems)


# ------------------------------------------- hand-built sheets for the corners

class _Cell:
    EMPTY, TEXT, NUMBER = 0, 1, 2


class _FakeSheet:
    """The few things savate.adapters.universitaire._Sheet asks of xlrd."""

    def __init__(self, name, grid):
        self.name = name
        self.nrows = len(grid)
        self.ncols = max(len(row) for row in grid)
        self._grid = [list(row) + [""] * (self.ncols - len(row)) for row in grid]

    def cell_value(self, r, c):
        return self._grid[r][c]

    def cell_type(self, r, c):
        value = self._grid[r][c]
        if value == "":
            return _Cell.EMPTY
        return _Cell.NUMBER if isinstance(value, (int, float)) else _Cell.TEXT


def _sheet(name, grid):
    import xlrd

    saved = (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER,
             xlrd.XL_CELL_BOOLEAN)
    assert saved == (0, 1, 2, 4), "xlrd's cell type codes moved"
    return uni._Sheet(_FakeSheet(name, grid))


def _rows_of(sheet, **meta):
    from savate.schema import Report

    report = Report()
    made = uni._poule_sheet(sheet, "t", meta, report, uni._Counter(), {})
    return made or [], report


# A five-fighter poule, its bracket, and - in the two right-hand columns - the
# running order the 2011 workbooks print, which names the same pairs again with
# no scores at all.
_DRAW_LISTING = [
    ["", "", "", "", "", "", "ELIMINATOIRES"],
    ["", "NOM", "PRENOM", "AS", "PL.", "", "POULE A"],
    [1.0, "ALPHA", "ANNE", "U1", "1°", "", "NOM", "", "NOM", "", 1.0, 2.0, 3.0],
    [2.0, "BRAVO", "BEA", "U2", "2°", 1.0, "ALPHA", 2.0, "BRAVO", "", 3.0, 1.0,
     "", "", "", "", "", "ALPHA", 2.0, "BRAVO"],
    [3.0, "CHARLIE", "CLO", "U3", "3°", 2.0, "BRAVO", 3.0, "CHARLIE", "", "",
     3.0, 1.0, "", "", "", "", "BRAVO", 3.0, "CHARLIE"],
    ["", "", "", "", "", 1.0, "ALPHA", 3.0, "CHARLIE", "", 3.0, "", 1.0,
     "", "", "", "", "ALPHA", 3.0, "CHARLIE"],
    ["", "", "", "", "", "", "", "", "TOTAL", "", 6.0, 4.0, 2.0],
]


def test_a_running_order_column_is_not_read_as_a_second_set_of_bouts():
    rows, report = _rows_of(_sheet("JF moins 50", _DRAW_LISTING))
    fought = bouts(rows)
    assert len(fought) == 3
    pairs = {frozenset((b.red, b.blue)) for b in fought}
    assert len(pairs) == 3
    assert all(b.status == "decided" for b in fought)


def test_a_poule_the_sheet_scores_2_2_is_stored_unresolved():
    grid = [row[:] for row in _DRAW_LISTING]
    grid[4][11], grid[4][12] = 2.0, 2.0      # BRAVO 2 - 2 CHARLIE
    grid[6][11], grid[6][12] = 3.0, 3.0
    rows, report = _rows_of(_sheet("JF moins 50", grid))
    drawn = [b for b in bouts(rows) if {b.red_points, b.blue_points} == {"2"}]
    assert len(drawn) == 1
    assert drawn[0].status == "unresolved"
    assert drawn[0].winner == "" and drawn[0].loser == ""
    assert drawn[0].decision == ""
    assert drawn[0].result_source == ""
    assert report.notes["drawn_scorelines"]


def test_a_final_the_classification_contradicts_is_unresolved():
    grid = [
        ["", "", "", "", "", "", "FINALES"],
        ["", "NOM", "PRENOM", "AS", "Place"],
        [1.0, "ALPHA", "ANNE", "U1", "1°"],
        [2.0, "BRAVO", "BEA", "U2", "2°", "", "A1", "ALPHA", "A2", "BRAVO",
         1.0, 3.0],
    ]
    rows, report = _rows_of(_sheet("JF moins 50", grid))
    final = [b for b in bouts(rows) if b.phase == "final"]
    assert len(final) == 1
    assert final[0].red_points == "1" and final[0].blue_points == "3"
    assert final[0].winner == "" and final[0].status == "unresolved"
    assert any("cannot both be true" in p for p in report.problems)


def test_a_demonstration_produces_no_bout():
    grid = [row[:] for row in _DRAW_LISTING]
    grid[5][14] = "démonstration"
    rows, report = _rows_of(_sheet("JF moins 50", grid))
    assert len(bouts(rows)) == 2
    assert report.notes["demonstrations_dropped"] == 1


def test_canne_de_combat_is_not_filed_as_savate():
    grid = [row[:] for row in _DRAW_LISTING]
    grid[1][1] = "NOM"
    grid[0][1] = "Catégorie : Canne de combat JF moins 50 kg"
    rows, report = _rows_of(_sheet("Canne JF 50", grid))
    assert rows == []
    assert report.notes["other_sport_dropped"] == 1
    assert any("another sport" in p for p in report.problems)


def test_a_name_that_matches_two_entrants_is_refused():
    grid = [
        ["", "", "", "", "", "", "FINALES"],
        ["", "NOM", "PRENOM", "AS", "Place"],
        [1.0, "MARTIN", "ANNE", "U1", "1°"],
        [2.0, "MARTON", "BEA", "U2", "2°"],
        [3.0, "ZULU", "CLO", "U3", "3°", "", "A1", "MARTAN", "A2", "ZULU",
         3.0, 1.0],
    ]
    rows, report = _rows_of(_sheet("JF moins 50", grid))
    assert bouts(rows) == []
    assert any("could be any of" in p for p in report.problems)


def test_two_bronzes_in_one_class_both_survive():
    """Savate awards two, and the schema must not treat the second as a dupe."""
    grid = [
        ["Clt", "Nom", "Prénom", "Association Sportive", "Poids"],
        [1, "ALPHA", "ANNE", "U1", "-50"],
        [2, "BRAVO", "BEA", "U2", "-50"],
        [3, "CHARLIE", "CLO", "U3", "-50"],
        [3, "DELTA", "DAN", "U4", "-50"],
    ]
    from savate.schema import Report

    report = Report()
    rows = uni._flat_sheet(_sheet("JF", grid), "t", {}, report,
                           uni._Counter(), {})
    third = [p for p in placings(rows) if p.rank == "3"]
    assert len(third) == 2
    assert {p.fighter for p in third} == {"CHARLIE CLO", "DELTA DAN"}
    assert {p.medal for p in third} == {"bronze"}
    assert not [p for p in report.problems if "place 3" in p]


def test_an_entry_list_masquerading_as_a_classification_is_dropped():
    """Every entrant printed as "1" is a seeding column, not a result."""
    grid = [
        ["PLACE CLT", "NOM", "PRÉNOM", "ASSOCIATION SPORTIVE", "POIDS"],
        [1, "ALPHA", "ANNE", "U1", "-50"],
        [1, "BRAVO", "BEA", "U2", "-50"],
        [1, "CHARLIE", "CLO", "U3", "-50"],
        [1, "DELTA", "DAN", "U4", "-56"],
        [1, "ECHO", "EVE", "U5", "-56"],
        [1, "FOXTROT", "FAY", "U6", "-56"],
    ]
    from savate.schema import Report

    report = Report()
    rows = uni._flat_sheet(_sheet("JF inscrits", grid), "t", {}, report,
                           uni._Counter(), {})
    assert rows == []
    assert any("entry list" in p for p in report.problems)


# ------------------------------------------------------------ weight classes

@pytest.mark.parametrize("printed,expected", [
    ("Catégorie : JG  +89 kg", ("Men", "89", "over")),
    ("Catégorie : JF -48KG", ("Women", "48", "under")),
    ("Catégorie : JG 76-82", ("Men", "82", "under")),
    ("H moins de 56 kg", ("Men", "56", "under")),
    ("H + de 85 kg", ("Men", "85", "over")),
    ("F moins 50 kg", ("Women", "50", "under")),
    ("JFmoinsde 50", ("Women", "50", "under")),
    ("JG plus 85", ("Men", "85", "over")),
    ("- 56 kg", ("", "56", "under")),
    ("F 55", ("Women", "55", "under")),
    ("M +82", ("Men", "82", "over")),
    ("-55 KG F", ("Women", "55", "under")),
    ("+70 KG F", ("Women", "70", "over")),
    ("RESULTATS", ("", "", "")),
])
def test_every_wording_of_a_weight_class_in_this_family(printed, expected):
    assert uni._class_of(printed) == expected


def test_a_band_printed_backwards_is_reported():
    from savate.schema import Report

    report = Report()
    assert uni._class_of("JG 86-82", report) == ("Men", "86", "under")
    assert any("lower figure is the larger" in p for p in report.problems)


# ------------------------------------- a decision is read or it is empty

# Every bout below is scored and none of the sheets says a word about how it
# ended. The adapter used to read the barème backwards - 3-1 became "points",
# 3-0 became "forfait", 3--1 became "disqualification" - and that told readers
# that 790 bouts across nine workbooks ended in ways no document states. Seven
# of the "forfait" rows named a fighter who had scored points elsewhere in the
# same poule, so he was there and he fought.

def _scored(blue_score):
    """The five-fighter poule with ALPHA v BRAVO scored 3 to `blue_score`."""
    grid = [row[:] for row in _DRAW_LISTING]
    grid[3][11] = blue_score
    rows, report = _rows_of(_sheet("JF moins 50", grid))
    fought = [b for b in bouts(rows)
              if {b.red, b.blue} == {"ALPHA ANNE", "BRAVO BEA"}]
    assert len(fought) == 1
    return fought[0], report


def test_a_3_1_scoreline_is_not_a_points_decision():
    bout, _report = _scored(1.0)
    assert (bout.red_points, bout.blue_points) == ("3", "1")
    assert bout.winner == "ALPHA ANNE" and bout.status == "decided"
    assert bout.decision == "" and bout.decision_detail == ""


def test_a_3_0_scoreline_is_not_a_forfait():
    """A zero is a fighter who scored nothing, not a bout nobody boxed."""
    bout, _report = _scored(0.0)
    assert (bout.red_points, bout.blue_points) == ("3", "0")
    assert bout.winner == "ALPHA ANNE" and bout.status == "decided"
    assert bout.decision == ""


def test_a_minus_one_is_not_a_disqualification():
    bout, _report = _scored(-1.0)
    assert (bout.red_points, bout.blue_points) == ("3", "-1")
    assert bout.decision == ""


def test_the_verdict_the_sheet_prints_beside_the_score_is_still_read():
    """"3 par forfait" is the sheet speaking, and that is read, with its words."""
    bout, _report = _scored("1 par forfait")
    assert (bout.red_points, bout.blue_points) == ("3", "1")
    assert bout.decision == "forfait"
    assert bout.decision_detail == "par forfait"


def test_the_shared_stoppage_vocabulary_is_what_reads_a_verdict():
    assert uni._decision_word("abandon au 2e") == "abandon"
    assert uni._decision_word("arrêt de l'arbitre") == "abandon"
    assert uni._decision_word("par blessure") == "abandon"
    assert uni._decision_word("W.O.") == "forfait"
    assert uni._decision_word("disqualifié") == "disqualification"
    assert uni._decision_word("") == ""
    assert uni._decision_word("2 x 2mn") == ""


# ------------------------------- one medallist per step, or a problem said

def _placed(*people):
    return [Placing(tournament="t", placing_id=f"t-p{i:04d}", category=cat,
                    rank=rank, medal=MEDALS.get(rank, ""), fighter=name,
                    club=club, result_source="reported")
            for i, (cat, rank, name, club) in enumerate(people, 1)]


def test_one_name_spelled_two_ways_on_one_step_of_the_podium_is_reported():
    """TRIOZEAU and TRIOREAU GUILLAUME are one bronze in the 2009 workbook.

    Two bronzes is legal savate, so the count alone cannot catch it; the near
    spelling can, and saying so is all this adapter may do - deciding that two
    spellings are one person is not a reading.
    """
    from savate.schema import Report

    report = Report()
    rows = _placed(("Men -80 kg", "3", "TRIOZEAU GUILLAUME", "AMM MARSEILLE"),
                   ("Men -80 kg", "3", "TRIOREAU GUILLAUME", "SPORT MARSEILLE"))
    kept = uni._dedupe_placings(rows, report)
    assert len(kept) == 2
    assert any("may be one person spelled two ways" in p
               for p in report.problems)


def test_a_class_with_two_silver_medallists_is_reported():
    from savate.schema import Report

    report = Report()
    rows = _placed(("Women -60 kg", "2", "MINIER MATHILDE", "SABATIER"),
                   ("Women -60 kg", "2", "MIGNIER MATHILDE", "SABATIER"))
    kept = uni._dedupe_placings(rows, report)
    assert len(kept) == 2
    assert any("hold place 2" in p for p in report.problems)


def test_two_genuine_bronzes_are_not_reported_as_a_crowd():
    from savate.schema import Report

    report = Report()
    rows = _placed(("Men -80 kg", "3", "ALPHA ANNE", "U1"),
                   ("Men -80 kg", "3", "ZULU ZOE", "U2"))
    assert len(uni._dedupe_placings(rows, report)) == 2
    assert report.problems == []


# ---------------------------------- a club in a name is said, not rewritten

def test_a_club_typed_into_the_forename_cell_is_reported():
    """"CAVALLO | U2 Marseille" with an empty AS cell, in the 2004 workbook."""
    from savate.schema import Report

    report = Report()
    rows = _placed(("Women -56 kg", "1", "ROULAUD SOPHIE", "U2 Marseille"),
                   ("Women -56 kg", "2", "CAVALLO U2 Marseille", ""))
    uni._report_stray_cells(rows, report)
    assert any("carries the club 'U2 Marseille' inside the name" in p
               for p in report.problems)


def test_a_club_split_between_the_forename_and_the_as_cell_is_reported():
    """"GRONIER | Quentin U2 | Marseille" - half a club in each cell."""
    from savate.schema import Report

    report = Report()
    rows = _placed(("Men -89 kg", "1", "TRELA STEPHANE", "U2 Marseille"),
                   ("Men -89 kg", "2", "GRONIER Quentin U2", "Marseille"))
    uni._report_stray_cells(rows, report)
    assert any("spells the association" in p for p in report.problems)


def test_a_forename_cell_that_ends_in_the_sport_is_reported():
    from savate.schema import Report

    report = Report()
    rows = _placed(("Women -60 kg", "1", "CELTON CELINE BOXE", "U1"),
                   ("Women +65 kg", "2", "PERROS CINDY BF", "U2"),
                   ("Women -70 kg", "3", "QUELFENNEC MELISSA", "U3"))
    uni._report_stray_cells(rows, report)
    said = [p for p in report.problems if "name of the sport" in p]
    assert len(said) == 2
    assert all("CELTON" in p or "PERROS" in p for p in said)


def test_an_ordinary_name_and_club_raise_nothing():
    from savate.schema import Report

    report = Report()
    rows = _placed(("Women -60 kg", "1", "ROULAUD SOPHIE", "Limoges"),
                   ("Women -60 kg", "2", "IACONO LAURE", "Staps Nantes"))
    uni._report_stray_cells(rows, report)
    assert report.problems == []
