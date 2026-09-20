"""Adapter for FISav's per-weight-class worksheet, one PDF per category.

The richest layout in the archive, and the only one that writes a bout as a
bout: each line begins "combat :" and names the two fighters, with their points
in one block of per-fighter columns and their warnings in another. The finals
bracket sits above it, and the scoring rules are printed in the corner:

    victoire / victory : 3 points        forfait / withdrawal : 0 point
    égalité / draw : 3 points            disqualification : -1 point
    défaite / defeat : 1 point

That header is worth reading twice. It confirms the scale derived from the 2026
championship - 3 for a win, 1 for a loss, 0 for a walkover, -1 for a
disqualification - and adds the one case that never came up there: a draw scores
3, the same as a win, so a drawn bout has two winners by points and no winner at
all. It is scored as a draw, not silently handed to one corner.

These worksheets are only reachable through the Wayback Machine. The folders
holding them - "pool results combat 2017", "pool results combat 2019" - were
removed from the live site, so the federation's own results page does not list
them and a crawl of it never sees them.
"""

import re
import statistics

from savate import normalize as norm
from savate import pdf
from savate.adapters.fisav_pool_pdf import weight_class
from savate.schema import Bout, Report, Tournament

NAME = "fisav_worksheet_pdf"
DESCRIPTION = "FISav per-category worksheet PDF ('combat :' lines, via Wayback)"

BOUT = re.compile(r"^combat\s*:", re.I)
SEED = re.compile(r"^n\s*[°ºo]\s*(\d+)$", re.I)
CHAMPION = re.compile(r"champion(ne)?\s+du\s+monde|world\s+champion|"
                      r"champion(ne)?\s+d.europe", re.I)
# The scoring legend, which is also the sanity check on the scale.
DRAW_POINTS = 3


def _number(text):
    try:
        return int(float(str(text).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _nearest(x, centres, tolerance=26.0):
    if not centres:
        return None
    best = min(range(len(centres)), key=lambda i: abs(x - centres[i]))
    return best if abs(x - centres[best]) <= tolerance else None


class Worksheet:
    """One weight class: its roster, its poule bouts and its final."""

    def __init__(self, words, report):
        self.report = report
        self.lines = pdf.rows(words)
        self.klass = None
        for line in self.lines[:6]:
            for w in line:
                found = weight_class(w.text)
                if found:
                    self.klass = found
                    break
            if self.klass:
                break

    def header(self):
        """(fighter names in column order, points centres, warning centres)."""
        row = next((l for l in self.lines
                    if sum(1 for w in l if w.text.upper() == "TIREUR") >= 2), None)
        if row is None:
            return None, [], []
        names = [w for w in row if w.text.upper() != "TIREUR"]
        if len(names) < 4 or len(names) % 2:
            return None, [], []
        half = len(names) // 2
        # The two blocks repeat the same fighters; that is what identifies them.
        if [w.text for w in names[:half]] != [w.text for w in names[half:]]:
            self.report.problem("the points and warnings blocks list different "
                                "fighters")
            return None, [], []
        return ([w.text for w in names[:half]],
                [w.x0 for w in names[:half]], [w.x0 for w in names[half:]])

    def offset(self, points_x, bouts):
        """How far right of its heading a column's values sit."""
        gaps = []
        for line in bouts:
            for w in line:
                if _number(w.text) is None:
                    continue
                near = min(points_x, key=lambda x: abs(w.x0 - x))
                if 0 < w.x0 - near < 90:
                    gaps.append(w.x0 - near)
        return statistics.median(gaps) if gaps else 50.0

    def bouts(self):
        """[(red, blue, red_points, blue_points, red_warn, blue_warn)]."""
        names, points_x, warn_x = self.header()
        if not names:
            return []
        lines = [l for l in self.lines if BOUT.match(pdf.text_of(l))]
        shift = self.offset(points_x, lines)
        points_c = [x + shift for x in points_x]
        warn_c = [x + shift for x in warn_x]

        out = []
        for line in lines:
            # "combat" and ":" are separate words, so the label has to be
            # dropped word by word - matching the line's prefix leaves the
            # label's first word behind, and it becomes the red corner.
            words = [w for w in line
                     if w.text.lower() != "combat" and w.text != ":"]
            corners = [w for w in words if _number(w.text) is None]
            if len(corners) < 2:
                self.report.problem(f"a combat line names {len(corners)} fighters")
                continue
            red, blue = corners[0].text, corners[1].text
            points, warnings = {}, {}
            for w in words:
                value = _number(w.text)
                if value is None:
                    continue
                column = _nearest(w.x0, points_c)
                if column is not None and w.x0 < min(warn_c) - 10:
                    points[names[column]] = value
                    continue
                column = _nearest(w.x0, warn_c)
                if column is not None:
                    warnings[names[column]] = value
            out.append({
                "red": red, "blue": blue,
                "red_points": points.get(red), "blue_points": points.get(blue),
                "red_warnings": warnings.get(red, 0),
                "blue_warnings": warnings.get(blue, 0),
            })
        return out

    def final(self):
        """(winner, runner_up) from the finals block, or (None, None).

        The block seeds the finalists n°1 and n°2 and prints the title beside
        them. n°1 is the champion; nothing else in the sheet says so, and the
        poule table cannot, because the final is fought after it.
        """
        seeds = {}
        for line in self.lines:
            texts = [w.text for w in line]
            for i, text in enumerate(texts):
                m = SEED.match(text)
                if not m:
                    continue
                # The name sits on this line or the one above, to the left.
                candidates = [t for t in texts[:i] if t.isalpha() and len(t) > 2]
                if candidates:
                    seeds[m.group(1)] = candidates[-1]
        if not any(CHAMPION.search(pdf.text_of(l)) for l in self.lines):
            return None, None
        return seeds.get("1"), seeds.get("2")


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout], Report) from one worksheet PDF."""
    from savate import rules, sources

    report = Report(source=str(source), adapter=NAME)
    path = (sources.fetch_archived(str(source)) if options.get("archived")
            else sources.fetch(source, refresh=options.get("refresh", False)))
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))

    pages = pdf.by_page(pdf.words(path))
    report.read = len(pages)
    bouts = []
    for index in sorted(pages):
        sheet = Worksheet(pages[index], report)
        if not sheet.klass:
            continue
        rows = sheet.bouts()
        for n, row in enumerate(rows, 1):
            red_points, blue_points = row["red_points"], row["blue_points"]
            if red_points is None and blue_points is None:
                continue
            red_points = red_points or 0
            blue_points = blue_points or 0
            drawn = (red_points == blue_points == DRAW_POINTS)
            corner = ("" if drawn else
                      "red" if red_points > blue_points else
                      "blue" if blue_points > red_points else "")
            decision = "draw" if drawn else rules.decision_from_points(
                max(red_points, blue_points), min(red_points, blue_points),
                row["blue_warnings"] if corner == "red" else row["red_warnings"])
            bouts.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-{index:02d}-p{n:02d}",
                phase="poule",
                poule="A",
                red=row["red"], blue=row["blue"],
                red_points=str(red_points), blue_points=str(blue_points),
                red_warnings=str(row["red_warnings"]),
                blue_warnings=str(row["blue_warnings"]),
                winner_corner=corner,
                winner={"red": row["red"], "blue": row["blue"]}.get(corner, ""),
                loser={"red": row["blue"], "blue": row["red"]}.get(corner, ""),
                decision=decision,
                status="decided" if corner else "unresolved",
                result_source="reported" if corner else "",
                **sheet.klass,
            ))

        champion, runner_up = sheet.final()
        if champion and runner_up:
            bouts.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-{index:02d}-final",
                phase="final",
                red=champion, blue=runner_up,
                winner_corner="red", winner=champion, loser=runner_up,
                status="decided", result_source="reported",
                **sheet.klass,
            ))
    if not bouts:
        report.notes["kind"] = "no 'combat :' lines - not a worksheet"
    return tournament, bouts, report
