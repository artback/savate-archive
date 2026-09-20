"""Adapter for a table of results: CSV, TSV, or a shared Google Sheet.

This is the adapter for sources nobody has seen yet. A federation that mails a
spreadsheet, an organiser who shares a Sheet, an export from some other timing
system - all of them are a table with columns whose names we cannot predict.

So the column names are not hard-coded. `guess_columns` matches whatever headers
arrived against the canonical fields, and a mapping file overrides it wherever
the guess is wrong. Run with --dry-run first: it prints what it matched and what
it ignored, which is the moment to correct it, not after the rows are in.

The shapes it handles, because spreadsheets use all of them:

  * a winner named outright ("Winner: Dupont") rather than by corner
  * a score as one cell ("3-1") or as two
  * how the bout ended folded into the score cell ("WO", "DQ") or in its own
  * dates in any of the usual orders, times with or without am/pm
"""

import csv
import io
import re

from savate import normalize as norm
from savate.schema import Bout, Report, Tournament, phase_of

NAME = "tabular"
DESCRIPTION = "any table of results: CSV, TSV, or a shared Google Sheet"

# Header wordings that have meant each canonical field. Matched loosely, so
# "Fighter A", "fighter_a" and "FIGHTER A (red)" all land on the red corner.
HEADER_HINTS = {
    "date": ["date", "day", "jour", "fecha"],
    "time": ["time", "heure", "hora", "start"],
    "ring": ["ring", "mat", "area", "piste", "tatami"],
    "category": ["category", "class", "weight class", "categorie", "catégorie",
                 "division", "categoria"],
    "phase": ["phase", "round", "tour", "stage", "ronda", "etape", "étape"],
    "poule": ["poule", "pool", "group", "grupo", "groupe"],
    "red": ["red", "rouge", "fighter a", "fighter 1", "tireur 1", "boxer a",
            "competitor a", "athlete a", "name 1", "rojo"],
    "blue": ["blue", "bleu", "fighter b", "fighter 2", "tireur 2", "boxer b",
             "competitor b", "athlete b", "name 2", "azul"],
    "red_country": ["red country", "country a", "nation a", "pays 1", "club a"],
    "blue_country": ["blue country", "country b", "nation b", "pays 2", "club b"],
    "red_points": ["red points", "points a", "score a", "points 1", "pts a"],
    "blue_points": ["blue points", "points b", "score b", "points 2", "pts b"],
    "winner": ["winner", "vainqueur", "gagnant", "ganador", "won by"],
    "score": ["score", "result", "résultat", "resultat", "resultado", "marcador"],
    "decision": ["decision", "décision", "method", "how", "by", "outcome",
                 "manner", "type"],
}

CORNER_WORDS = {"red": "red", "rouge": "red", "r": "red", "a": "red", "1": "red",
                "blue": "blue", "bleu": "blue", "b": "blue", "2": "blue"}


def _key(header):
    """A header reduced to what it means: accent-folded, punctuation dropped.

    Folding first matters. Stripping non-ASCII from "Catégorie" leaves
    "cat gorie", which matches nothing, so a French sheet would silently arrive
    with no category column at all.
    """
    return " ".join(re.sub(r"[^a-z0-9]+", " ", norm.fold(header)).split())


def guess_columns(headers):
    """{canonical field: header} for the headers this recognises.

    Exact hints win over partial ones, and a header is claimed once, so two
    fields cannot quietly read the same column.
    """
    taken, found = set(), {}
    keyed = {h: _key(h) for h in headers}
    for exact in (True, False):
        for field, hints in HEADER_HINTS.items():
            if field in found:
                continue
            for header, key in keyed.items():
                if header in taken or not key:
                    continue
                hit = (key in hints) if exact else \
                    any(h in key or key in h for h in hints)
                if hit:
                    found[field] = header
                    taken.add(header)
                    break
    return found


def read_rows(source):
    """Rows and headers from a CSV/TSV path, or a Google Sheet.

    A Sheet is named by its URL or bare id; it is read through the CSV export
    the Sheet itself serves, so nothing but the standard library is needed. The
    Sheet has to be readable by anyone with the link - if it is not, the export
    answers with a sign-in page, which is caught here rather than parsed as data.
    """
    text = None
    if re.match(r"https?://", str(source)) or re.fullmatch(r"[\w-]{30,}", str(source)):
        import urllib.request

        m = re.search(r"/spreadsheets/d/([\w-]+)", str(source))
        sheet_id = m.group(1) if m else str(source)
        gid = re.search(r"[#&?]gid=(\d+)", str(source))
        url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
               f"?format=csv&gid={gid.group(1) if gid else '0'}")
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
        text = raw.decode("utf-8-sig", errors="replace")
        if text.lstrip()[:15].lower().startswith("<!doctype") or "<html" in text[:400].lower():
            raise SystemExit(
                f"{source}: the sheet export returned a web page, not CSV - it is "
                f"probably not shared with 'anyone with the link'.")
    else:
        with open(source, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader), list(reader.fieldnames or [])


def read(source, slug, meta=None, mapping=None, **options):
    """(Tournament, [Bout], Report) from any table of results."""
    rows, headers = read_rows(source)
    columns = guess_columns(headers)
    columns.update({k: v for k, v in (mapping or {}).items() if v})
    report = Report(source=str(source), adapter=NAME, read=len(rows),
                    notes={"headers": headers, "mapped": dict(columns),
                           "ignored": [h for h in headers
                                       if h not in set(columns.values())]})

    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))

    def cell(row, field):
        header = columns.get(field)
        return " ".join(str(row.get(header, "") or "").split()) if header else ""

    bouts = []
    for i, row in enumerate(rows, 1):
        red, blue = cell(row, "red"), cell(row, "blue")
        if not (red and blue):
            if any(str(v or "").strip() for v in row.values()):
                report.problem(f"row {i}: no pair of fighters")
            continue

        red_points, blue_points = cell(row, "red_points"), cell(row, "blue_points")
        if not (red_points and blue_points):
            red_points, blue_points = norm.score_pair(cell(row, "score"))

        # The winner is named, cornered, or left to the score to settle.
        raw_winner = cell(row, "winner")
        corner = CORNER_WORDS.get(_key(raw_winner))
        if corner:
            winner_corner = corner
        elif raw_winner:
            folded = norm.fold(raw_winner)
            winner_corner = ("red" if folded == norm.fold(red) else
                             "blue" if folded == norm.fold(blue) else "")
            if not winner_corner:
                report.problem(
                    f"row {i}: winner {raw_winner!r} is neither {red!r} nor {blue!r}")
        elif red_points and blue_points and red_points != blue_points:
            try:
                winner_corner = "red" if float(red_points) > float(blue_points) else "blue"
            except ValueError:
                winner_corner = ""
        else:
            winner_corner = ""

        decision = norm.decision(cell(row, "decision")) or \
            norm.decision(cell(row, "score"))
        if not decision and winner_corner and red_points and blue_points:
            decision = "points"

        phase_text = cell(row, "phase")
        phase = phase_of(phase_text)
        if phase_text and not phase:
            report.problem(f"row {i}: round {phase_text!r} not recognised")

        bouts.append(Bout(
            tournament=slug,
            bout_id=f"{slug}-{i:04d}",
            date=norm.date(cell(row, "date")),
            time=norm.clock(cell(row, "time")),
            ring=cell(row, "ring"),
            phase=phase,
            poule=cell(row, "poule"),
            red=red, red_country=cell(row, "red_country"),
            blue=blue, blue_country=cell(row, "blue_country"),
            red_points=red_points, blue_points=blue_points,
            winner_corner=winner_corner,
            winner={"red": red, "blue": blue}.get(winner_corner, ""),
            loser={"red": blue, "blue": red}.get(winner_corner, ""),
            decision=decision,
            status="decided" if winner_corner else "unresolved",
            result_source="reported" if winner_corner else "",
            **norm.category(cell(row, "category")),
        ))
    return tournament, bouts, report
