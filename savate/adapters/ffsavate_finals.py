"""The French federation's finals sheet: one weight class, two names, a verdict.

    F48
    NANDI          Chloé       U S CRETEIL (94)          Unanimité
    JANOLI         Léa         SBF DE CLUSES (74)

A class code on its own line, then the winner with the decision printed at the
end of their line, then the runner-up. The FFSavate has published its national
finals this way since at least 2023 - Elite A, Assaut, Vétérans, Juniors, 2e
Série - and it is the only source in this archive that names a competitor's
CLUB, which is a fact worth having and one no international sheet carries.

Two things this adapter refuses to do.

*It does not assign corners.* The sheet says who won. It never says who stood in
the red corner, and red/blue in this archive mean corner and nothing else, so
inventing one to make the row look complete would put a fact on the page that no
document supports. `winner` and `loser` are filled; `winner_corner` is left
empty, and the interface names the winner without drawing a corner rail.

*It does not guess where a column ended.* Some rows separate the given name
from the club with a single space instead of the column gap, and the split then
hands the club back with a first name glued to its front. Club names in these
sheets are set in capitals and given names are not, which is enough to put the
word back where it belongs without guessing at either field.

*It does not flatten the verdict.* "Unanimité" and "Majorité" both mean the bout
went to a decision on points, which is what `decision` records. Which of the two
it was is a different fact - how divided the judges were - and it is kept in
`decision_detail` rather than thrown away for tidiness.

The class codes are the federation's own: F48 is women under 48 kg, M85 men
under 85. Two codes are sentinels rather than weights - F100 and M150 - and they
mark the open class at the top of each ladder. That reading is corroborated
inside this archive (NAROU Yoann, printed under M150 here, is the +85 kg
European champion in the FISav sheets), but it is an inference about a coding
scheme rather than something a document states, so it is reported on every read.
"""

import re

from savate.schema import Bout, Placing, Report

NAME = "ffsavate_finals"
DESCRIPTION = "FFSavate national finals sheets (class code, winner, runner-up)"

# A line that is nothing but a class code.
_CLASS = re.compile(r"^\s*([FM])\s*\+?\s*(\d{2,3})\s*$")

# The verdict, printed at the end of the winner's line.
_DECISIONS = [
    ("Unanimité", "points", r"unanimit[ée]"),
    ("Majorité", "points", r"majorit[ée]"),
    ("Partage", "points", r"partage"),
    ("KO", "abandon", r"\bk\.?\s?o\.?\b"),
    ("Arrêt", "abandon", r"arr[êe]t"),
    ("Abandon", "abandon", r"abandon"),
    ("Blessure", "abandon", r"blessure"),
    ("Forfait", "forfait", r"forfait|w\.?\s?o\.?\b"),
    ("Disqualification", "disqualification", r"disqualif"),
]

# The club, as the sheet prints it: a name and its département in brackets.
_CLUB = re.compile(r"^(.*?)\s*\((\d{2,3})\)\s*$")

# Above this the code is a sentinel for the open class, not a weight. Real
# savate classes top out at 85 kg for men and 75 for women.
_SENTINEL = 90


def _decision(text):
    """(schema decision, the word the sheet printed) or ("", "")."""
    for printed, decision, pattern in _DECISIONS:
        if re.search(pattern, text, re.I):
            return decision, printed
    return "", ""


def _strip_decision(text):
    for _printed, _decision, pattern in _DECISIONS:
        text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s{2,}", "  ", text).strip()


def _competitor(line):
    """(name, club) from one printed line, or (None, "") if it is not one."""
    body = _strip_decision(line)
    if not body or len(body) < 4:
        return None, ""

    # poppler keeps the column gaps, so two or more spaces separate the fields.
    parts = [p.strip() for p in re.split(r"\s{2,}", body) if p.strip()]
    if len(parts) < 2:
        return None, ""

    club = ""
    found = _CLUB.match(parts[-1])
    if found:
        club = found.group(1).strip()
        parts = parts[:-1]
    elif len(parts) > 2:
        club = parts[-1]
        parts = parts[:-1]
    elif len(parts) == 2:
        # Two parts: "NAME  CLUB" or "NAME CLUB" (single-space case).
        # If the second part is ALL CAPS it is the club.
        if parts[-1].isupper():
            club = parts[-1]
            parts = parts[:-1]

    # Some rows put only one space between the given name and the club, so the
    # column split hands back "Gwendoline MENEZ-HOM KRAON BOXING CLUB".  Club
    # names in these sheets are set in capitals throughout and given names are
    # not, so a leading capitalised-but-not-capitals word belongs to the person.
    # Peel only the first — multi-word clubs like "Nouveau Chevalier Roze" are
    # valid and peeling them all would put the club on the fighter's name.
    if club:
        head = club.split(" ", 1)
        if len(head) == 2:
            word = head[0]
            if not word.isupper() and word[:1].isupper():
                parts.append(word)
                club = head[1].strip()

    name = " ".join(parts).strip()
    if not name or not re.search(r"[A-Za-zÀ-ÿ]", name):
        return None, ""
    # A heading, a date line or a venue is not a competitor.
    if re.search(r"\d{2}/\d{2}/\d{4}|classement|r[ée]sultat|championnat", name, re.I):
        return None, ""
    return name, club


def _category(letter, kilos, report, age=""):
    """(label, gender, weight, bound) for a class code.

    The age class goes in the label. Without it "Men -60 kg" from a juniors
    sheet and "Men -60 kg" from a seniors sheet are one string, and every
    reader of the archive that keys on the label - the category index, the
    weight-class lineage - silently merges two different competitions.
    """
    gender = "Women" if letter.upper() == "F" else "Men"
    prefix = (age + " ") if age else ""
    if kilos >= _SENTINEL:
        report.notes.setdefault("sentinel_classes", [])
        code = f"{letter.upper()}{kilos}"
        if code not in report.notes["sentinel_classes"]:
            report.notes["sentinel_classes"].append(code)
        # The open class. The sheet gives no weight for it, and this does not
        # invent one: the bound is recorded as open, the kilos left empty.
        return f"{prefix}{gender} open", gender, "", "over"
    return f"{prefix}{gender} -{kilos} kg", gender, str(kilos), "under"


def read(source, slug, meta=None, **options):
    from savate import normalize as norm, pdf, sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    path = sources.fetch(source)
    try:
        text = pdf.text(str(path))
    except Exception:
        text = ""
    if not isinstance(text, str):
        text = ""
    if not text.strip():
        try:
            import subprocess
            text = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                  capture_output=True, text=True,
                                  timeout=60).stdout
        except Exception as e:
            report.problem(f"no text layer and pdftotext failed: {e}")
            text = ""

    lines = text.splitlines()
    tournament = _tournament(slug, meta, source)

    # The sheet dates itself under its title. Nothing else in this archive
    # does, and two French meets a fortnight apart can otherwise look like one
    # event published twice - the same pair does meet more than once a season.
    for line in lines[:12]:
        when, city, _dept = norm.dateline(line)
        if when:
            tournament.start_date = tournament.start_date or when
            tournament.city = tournament.city or city
            if not tournament.year:
                tournament.year = when[:4]
            break

    bouts, placings = [], []
    current = None
    block = []

    def flush():
        """Turn one class block into its final, or say why it could not."""
        if not current or not block:
            return
        label, gender, kilos, bound = current
        people = []
        for line in block:
            decision, printed = _decision(line)
            name, club = _competitor(line)
            if name:
                people.append((name, club, decision, printed))

        if len(people) < 2:
            report.problem(f"{label}: {len(people)} competitor(s) on the sheet, "
                           f"a final needs two")
            return

        # The winner is the line carrying the verdict; failing that, the first,
        # which is how every sheet seen so far orders them.
        winner_at = next((i for i, p in enumerate(people) if p[2]), 0)
        loser_at = 1 if winner_at == 0 else 0
        if loser_at >= len(people):
            return
        winner, loser = people[winner_at], people[loser_at]
        decision, printed = winner[2], winner[3]
        if not decision:
            report.problem(f"{label}: no decision printed for {winner[0]}")

        index = len(bouts) + 1
        bouts.append(Bout(
            tournament=slug,
            bout_id=f"{slug}-{index:02d}-final",
            category=label, gender=gender, age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound,
            phase="final",
            # Printed order, which is the only order the sheet gives. The
            # corner is NOT claimed: winner_corner stays empty.
            red=winner[0], red_club=winner[1],
            blue=loser[0], blue_club=loser[1],
            winner=winner[0], loser=loser[0],
            winner_corner="",
            decision=decision, decision_detail=printed,
            status="decided", result_source="reported",
        ))
        for rank, who in ((1, winner), (2, loser)):
            placings.append(Placing(
                tournament=slug,
                placing_id=f"{slug}-{index:02d}-{rank}",
                category=label, gender=gender,
                age_class=meta.get("age_class", ""),
                weight_kg=kilos, weight_bound=bound,
                rank=str(rank), medal={1: "gold", 2: "silver"}[rank],
                fighter=who[0], club=who[1],
                country=meta.get("country", ""),
                result_source="reported",
            ))

    for line in lines:
        found = _CLASS.match(line)
        if found:
            flush()
            current = _category(found.group(1), int(found.group(2)), report,
                                meta.get("age_class", ""))
            block = []
            continue
        if current and line.strip():
            block.append(line)
    flush()

    report.read = len(lines)
    report.notes["finals"] = len(bouts)
    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"]) +
            " read as the open class: the code exceeds every real savate "
            "weight, and no document states what it stands for")
    if not bouts:
        report.problem("no finals found - this may not be a finals sheet")
    return tournament, bouts + placings, report


def _tournament(slug, meta, source):
    from savate.schema import Tournament

    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", "national"),
        format=meta.get("format", "championship"),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        country=meta.get("country", "France"),
        source=source, adapter=NAME,
        competition=meta.get("competition", ""),
    )
