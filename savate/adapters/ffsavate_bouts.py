"""The French federation's results sheets that print the class code on the row.

Three of the FFSavate's layouts put the weight class on every competitor line
rather than on a line of its own, which is what `ffsavate_finals` reads. They
are one adapter because they are one document family: the same federation, the
same class codes, the same verdict words, the same refusal to name a corner.

    Niveau          Cat.   Nom Prénom 1      Club 1       Nom Prénom2 ...
    Tour de poule   M70    AZATYAN Azat      OFP BOXE...  DIALLO Moussa ...
    Finale          M85    DEMAGNY Alexandre CENTER ...   LECAILLE Aurelien ...

the full bout table, one row per bout, with the round in its own column and the
winner named in a column of its own; and

    M56       LELONG      Enzo        IMPACT MULTI BOXE (66)   Unanimité
    M56       BOUZA       Guillaume   ECOLE SAVATE AGEN (47)

the finals sheet, two lines to a bout, the verdict printed at the end of the
winner's line; and

    M60 . Légers       CATTOIRE Eric      SBF LEO LAGRANGE ARMENTIERES  Unanimité
    M60 . Légers       ZADI Karim         BF ALLONNES

the same two-line form with the federation's name for the class after the code,
under TOURS DE POULE / DEMI FINALES / FINALES headings that give the round.

Four things this adapter refuses to do.

*It does not assign corners.* "Nom Prénom 1" and "Nom Prénom 2" are the columns
of a table, not the corners of a ring, and on the two-line sheets the two lines
are a printing order. `red`/`blue` therefore carry that printed order unchanged
- not rearranged to put the winner first, which would replace the one ordering
the document gives with one it does not - and `winner_corner` is left empty
while `winner` and `loser` are named. Red and blue mean corner in this archive,
so filling one in would put a fact on the page that no document supports.

*It does not fold the sheet's repeats.* The bout tables are sorted by the first
name column and print some poule bouts twice, once from each fighter's row -
BELIN v JOUSSEAUME and JOUSSEAUME v BELIN, same winner, same verdict, one bout.
Collapsing them belongs in build_db.deduplicate(), which keys on the unordered
pair and so catches the mirror image an adapter would have to guess at. The
count of suspected repeats is reported, and every printed row is returned.

*It does not flatten the verdict.* "Unanimité" and "Majorité" both mean a bout
decided on points; "Hors combat", "HC 3ème rep", "Jet serviette" and "Disq 2ème
rep" each mean something the schema's `decision` cannot hold. The canonical
decision goes in `decision`, and the federation's own printed words - including
the reprise number, which these sheets often carry onto the next line - are kept
verbatim in `decision_detail`.

*It does not invent the age class.* A label that says only "Men -60 kg" merges a
juniors championship into a seniors one, so the category carries the most
specific thing the sheet itself states about who competed: its age class where
it names one ("Juniors", "Vétérans", "Espoirs"), otherwise its series ("Elite
A", "2e Série", "Premium"), which is not an age class and so is put in the label
without being written to `age_class` and without displacing an age class the
manifest states. Where a page states neither - the
Barbezieux women's page is headed only "FEMININE" - the label has no prefix and
the read says so. The prefix is scoped to the page it was read from, because the
footer of these sheets names both competitions in the file ("CHAMPIONNAT DE
France VETERAN - COUPE DE France ASSAUT 2023") and reading it would file a
Coupe de France under Vétérans.

The class codes are the federation's own: F48 is women under 48 kg, M85 men
under 85. Codes above every real savate class - M150, F100 - are the open class
at the top of the ladder, which is an inference about a coding scheme rather
than something a document states, so it is reported on every read, exactly as
`ffsavate_finals` reports it.
"""

import re
import subprocess

from savate import normalize as norm
from savate.schema import Bout, Placing, Report, Tournament, phase_of

NAME = "ffsavate_bouts"
DESCRIPTION = ("FFSavate results sheets with the class code on every row "
               "(bout tables, and finals/poule pairs)")

# A class code as the sheets write it: F48, M150, "M65 . S/Légers".
_CODE = re.compile(r"([FM])\s?\+?(\d{2,3})")
# One competitor line of a two-line sheet: the code, optionally the
# federation's name for the class, then the person.
_PAIR = re.compile(r"^\s*([FM])\s?(\d{2,3})\s*(?:\.\s*(\S+))?\s\s+(\S.*)$")
# A round heading on a line of its own. Deliberately anchored and short: the
# page footer of these files ends "... 2023 v Finale   3", and matching a round
# word loosely anywhere would file six pages of poule bouts as finals.
_HEADING = re.compile(r"^(tours?\s+de\s+poules?|poules?|demi[\s-]*finales?|"
                      r"1/2\s*finales?|quarts?\s+de\s+finales?|finales?)$", re.I)
# The form number in the footer. It names both competitions in the file, so it
# is never read for anything.
_FOOTER = "CNC/AP"

# A decision word, as these sheets print it: the canonical decision, and a
# pattern that also swallows the reprise it is often qualified by.
_DECISIONS = [
    ("points", r"unanimit[ée]s?"),
    ("points", r"majorit[ée]s?"),
    ("points", r"partage"),
    ("disqualification", r"(?:par\s+)?disqualification|disq\.?\s*\d*\s*"
                        r"[èeé]?m?e?\s*rep\.?"),
    ("forfait", r"(?:par\s+)?forfait|\bw\.?\s?o\.?\b"),
    ("abandon", r"hors\s+combat|\bhc\s*\d*\s*[èeé]?m?e?\s*rep\.?|"
                r"jet\s+(?:de\s+)?(?:l[ae]\s+)?(?:serviette|[ée]ponge)|"
                r"\bk\.?\s?o\.?\b|arr[êe]t|abandon|blessure"),
]
# "Jet serviette" on one line, "1ère reprise" on the next: the reprise belongs
# to the verdict above it, not to a competitor.
_REPRISE = re.compile(r"^\s*\d\s*[èeé]?r?m?e?\s*(reprise|rep\.?)\s*$", re.I)

# The age classes these sheets name, in the archive's English vocabulary.
_AGES = [("Junior", r"juniors?"), ("Espoir", r"espoirs?"),
         ("Veteran", r"v[ée]t[ée]rans?"), ("Cadet", r"cadets?"),
         ("Minime", r"minimes?"), ("Senior", r"seniors?")]
# The competitive series. Not an age class - Elite A and 2e Série are levels of
# licence, not years of birth - so these label a category without ever being
# written to `age_class`.
_SERIES = [("Elite A", r"[ée]lite\s*a\b"), ("Elite B", r"[ée]lite\s*b\b"),
           ("2e Série", r"2\s*(?:[èe]me|nd|e)?\s*s[ée]rie"),
           ("Premium", r"premium\b")]

# Above this a code is the open class, not a weight: savate's real classes stop
# at 85 kg for men and 75 for women.
_SENTINEL = 90

# The club as the sheets print it, with its département in brackets.
_CLUB = re.compile(r"^(.*?)\s*\((\d{2,3})\)\s*$")


def _caps(token):
    """Is this token set in capitals? Surnames are; given names are not."""
    return (bool(re.search(r"[A-ZÀ-ÖØ-Þ]", token))
            and not re.search(r"[a-zà-öø-ÿ]", token))


def _person(text):
    """(name, club) from "SURNAME Given  CLUB (dd)", or ("", "") if unreadable.

    The column gap is not reliable here - "CAVROT WESTERLINCK Ethan IMPACT SBF
    (59)" is printed with single spaces throughout - so the split is made on
    case instead, which these sheets are consistent about: the surname is in
    capitals, the given name is not, and the club is in capitals again. That
    reads a run of capitals, then the given names, then hands everything from
    the next capitalised word on to the club.
    """
    tokens = " ".join(str(text or "").split()).split(" ")
    if not tokens:
        return "", ""
    surname = []
    while tokens and _caps(tokens[0]):
        surname.append(tokens.pop(0))
    given = []
    while tokens and not _caps(tokens[0]):
        given.append(tokens.pop(0))
    if not surname or not given:
        # Not the shape this reads. Fall back to the column gap, which the
        # wider sheets do keep.
        parts = [p.strip() for p in re.split(r"\s{2,}", " ".join(
            surname + given + tokens)) if p.strip()]
        if len(parts) < 2:
            return "", ""
        return parts[0], _CLUB.sub(r"\1", parts[-1]).strip()
    return " ".join(surname + given), _CLUB.sub(r"\1", " ".join(tokens)).strip()


def _decision(text):
    """(canonical decision, the words the sheet printed) or ("", "")."""
    for decision, pattern in _DECISIONS:
        found = re.search(pattern, text, re.I)
        if found:
            return decision, " ".join(found.group(0).split())
    return "", ""


def _strip_decision(text):
    for _decision, pattern in _DECISIONS:
        text = re.sub(pattern, "  ", text, flags=re.I)
    return text.strip()


def _qualifier(lines):
    """(label prefix, age class) from a page's heading lines.

    Age class first: it is the fact the schema has a field for. A series is
    taken only when no age class is named, and never written to `age_class`.
    """
    text = " ".join(" ".join(l.split()) for l in lines)
    for age, pattern in _AGES:
        if re.search(pattern, text, re.I):
            return age, age
    for series, pattern in _SERIES:
        if re.search(pattern, text, re.I):
            return series, ""
    return "", ""


def _klass(letter, kilos, prefix, age, report):
    """The category fields for one class code."""
    gender = "Women" if letter.upper() == "F" else "Men"
    head = f"{prefix} " if prefix else ""
    if kilos >= _SENTINEL:
        code = f"{letter.upper()}{kilos}"
        seen = report.notes.setdefault("sentinel_classes", [])
        if code not in seen:
            seen.append(code)
        # The open class. No weight is claimed for it, because the sheet gives
        # none: only the bound is known.
        return {"category": f"{head}{gender} open", "gender": gender,
                "age_class": age, "weight_kg": "", "weight_bound": "over"}
    return {"category": f"{head}{gender} -{kilos} kg", "gender": gender,
            "age_class": age, "weight_kg": str(kilos), "weight_bound": "under"}


def _pages(path, report):
    """The document's pages, each a list of lines, or [] if it cannot be read.

    pdftotext's -layout mode is what makes these files readable at all: the
    bout table is columns of whitespace, and the finals sheets put the verdict
    in a column of its own. Losing the layout turns both into a name soup.
    """
    try:
        done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
    except Exception as e:
        report.problem(f"pdftotext could not be run: {e}")
        return []
    if done.returncode != 0:
        report.problem("pdftotext could not read this file as a PDF: "
                       + " ".join(done.stderr.split())[:160])
        return []
    return [page.splitlines() for page in done.stdout.split("\f")]


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout | Placing], Report) from one FFSavate results sheet."""
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)
    path = sources.fetch(source, refresh=options.get("refresh", False))

    rows, placings = [], []
    # The manifest's own metadata is the starting point; a page that names its
    # age class or series overrides it, and which of the two was used is
    # reported, because "the manifest says Juniors" and "the sheet says
    # JUNIORS" are not the same claim. A series read off the page takes the
    # label - it is the more specific thing, and it is the document's own word -
    # without displacing an age class the manifest states, because a series is
    # not an age class and cannot stand in for one.
    meta_age = meta.get("age_class", "")
    prefix, found_age = _qualifier([meta_age, meta.get("name", "")])
    if meta_age:
        prefix = meta_age
    age = found_age or meta_age
    prefix_from = "the manifest" if prefix else ""
    phase = ""
    block = []
    lines_read = 0

    def add(klass, first, second, won, decision, detail, printed_phase):
        """One bout, in the order the sheet printed its two people.

        `won` is 0, 1 or None: which of the two the sheet named as the winner.
        The order is never rearranged to put the winner first - it is the only
        ordering the document gives, and `winner` already says who won.
        """
        winner = loser = ""
        status, result_source = "unresolved", ""
        if won is not None:
            winner, loser = first[0], second[0]
            if won:
                winner, loser = loser, winner
            status, result_source = "decided", "reported"
        index = len(rows) + 1
        rows.append(Bout(
            tournament=slug, bout_id=f"{slug}-{index:03d}",
            phase=printed_phase,
            red=first[0], red_club=first[1],
            blue=second[0], blue_club=second[1],
            # The sheet names the winner and never the corner. See the module
            # docstring: winner_corner stays empty on purpose.
            winner=winner, loser=loser, winner_corner="",
            decision=decision, decision_detail=detail,
            status=status, result_source=result_source,
            **klass))
        if printed_phase == "final" and winner:
            podium = [first, second] if not won else [second, first]
            for rank, who in ((1, podium[0]), (2, podium[1])):
                placings.append(Placing(
                    tournament=slug,
                    placing_id=f"{slug}-{index:03d}-{rank}",
                    rank=str(rank), medal={1: "gold", 2: "silver"}[rank],
                    fighter=who[0], club=who[1],
                    country=meta.get("country", ""),
                    result_source="reported", **klass))

    def flush():
        """Turn a pending pair of competitor lines into a bout."""
        if not block:
            return
        if len(block) == 1:
            report.problem(f"{block[0]['code']}: {block[0]['name']} is printed "
                           f"without an opponent")
            block.clear()
            return
        first, second = block[0], block[1]
        block.clear()
        if first["code"] != second["code"]:
            report.problem(f"a bout pairs {first['code']} with {second['code']}"
                           f" ({first['name']} / {second['name']}): the two "
                           f"lines are not one bout, so neither is kept")
            return
        # The winner is the line carrying the verdict. Where neither carries
        # one the bout is kept unresolved rather than awarded to the first
        # line: the order alone does not say who won.
        carry = [i for i, p in enumerate((first, second)) if p["decision"]]
        if len(carry) > 1:
            report.problem(f"{first['code']}: a verdict is printed against "
                           f"both {first['name']} and {second['name']}, so "
                           f"neither is named the winner")
            won = None
        elif not carry:
            report.problem(f"{first['code']}: no verdict printed for "
                           f"{first['name']} v {second['name']}")
            won = None
        else:
            won = carry[0]
        winner = (first, second)[won] if won is not None else first
        add(first["klass"], (first["name"], first["club"]),
            (second["name"], second["club"]), won,
            winner["decision"], winner["detail"], first["phase"])

    for page in _pages(path, report):
        lines_read += len(page)
        body = [l for l in page if _FOOTER not in l]
        first_row = next((i for i, l in enumerate(body)
                          if _grid(l) or _PAIR.match(l)), len(body))
        found, found_age = _qualifier(body[:first_row])
        if found:
            prefix, prefix_from = found, "the sheet"
            age = found_age or meta_age
        for line in body[:first_row]:
            when, city, _dept = norm.dateline(line)
            if when and not tournament.start_date:
                tournament.start_date = when
                tournament.city = city

        for line in body:
            if not line.strip():
                flush()
                continue
            text = " ".join(line.split())
            if _HEADING.match(text):
                flush()
                phase = phase_of(text)
                continue
            if _REPRISE.match(text) and block:
                # A verdict carried onto the next line.
                block[-1]["detail"] = f"{block[-1]['detail']} {text}".strip()
                continue
            fields = _grid(line)
            if fields:
                flush()
                _grid_bout(fields, line, prefix, age, report, add)
                continue
            pair = _PAIR.match(line)
            if pair:
                decision, detail = _decision(pair.group(4))
                name, club = _person(_strip_decision(pair.group(4)))
                code = f"{pair.group(1)}{pair.group(2)}"
                if not name:
                    report.problem(f"{code}: no competitor could be read from "
                                   f"{text!r}")
                    flush()
                    continue
                if len(block) == 2:
                    flush()
                block.append({
                    "code": code, "name": name, "club": club,
                    "decision": decision, "detail": detail, "phase": phase,
                    "klass": _klass(pair.group(1), int(pair.group(2)),
                                    prefix, age, report)})
                if len(block) == 2:
                    flush()
                continue
            flush()
        flush()

    report.read = lines_read
    report.notes["bouts"] = len(rows)
    report.notes["placings"] = len(placings)
    report.notes["category_prefix"] = prefix
    report.notes["category_prefix_from"] = prefix_from
    bare = sorted({r.category for r in rows
                   if r.category.startswith(("Men", "Women"))})
    if bare:
        report.problem(
            f"{len(bare)} categor{'y' if len(bare) == 1 else 'ies'} are "
            f"labelled by gender and weight alone ({', '.join(bare[:3])}"
            f"{', ...' if len(bare) > 3 else ''}): the page they were printed "
            f"on names neither an age class nor a series, and neither does the "
            f"manifest")
    elif prefix_from == "the manifest":
        report.problem(f"the sheet itself names no age class or series; the "
                       f"categories are labelled {prefix!r} on the manifest's "
                       f"word, not the document's")
    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"]) +
            " read as the open class: the code exceeds every real savate "
            "weight, and no document states what it stands for")
    mirrors = _mirrors(rows)
    if mirrors:
        report.notes["mirrored_rows"] = mirrors
        report.problem(f"{mirrors} bout(s) are printed twice, once from each "
                       f"fighter's row; every printed row is kept and "
                       f"build_db.deduplicate() folds the pair")
    if not rows:
        report.problem("no bouts found - this is not one of the three FFSavate "
                       "layouts this adapter reads")
    return tournament, rows + placings, report


def _grid(line):
    """The cells of a bout-table row, or None if the line is not one.

    A row is recognised by its own content rather than by where it sits: the
    first cell names a round the schema knows and the second is a class code.
    That is what separates a bout row from the column headings, the legend and
    the federation's address, without a list of the strings to skip.
    """
    fields = [f.strip() for f in re.split(r"\s{2,}", line.strip()) if f.strip()]
    if len(fields) < 7 or not phase_of(fields[0]):
        return None
    return fields if _CODE.fullmatch(fields[1]) else None


def _grid_bout(fields, line, prefix, age, report, add):
    """One row of the bout table: two named fighters, a winner and a verdict."""
    code = _CODE.fullmatch(fields[1])
    if len(fields) > 8:
        report.problem(f"a bout row has {len(fields)} columns, not 8: "
                       f"{' '.join(line.split())!r}")
        return
    winner_cell = fields[6] if len(fields) >= 7 else ""
    decision_cell = fields[7] if len(fields) == 8 else ""
    if len(fields) == 7:
        # Seven columns is either a missing winner or a missing verdict. The
        # cell itself says which; it is not guessed from the position.
        if _decision(winner_cell)[0]:
            winner_cell, decision_cell = "", winner_cell
    decision, detail = _decision(decision_cell)
    if decision_cell and not decision:
        report.problem(f"verdict {decision_cell!r} is not one this adapter "
                       f"knows; the bout is kept without a decision")
        detail = " ".join(decision_cell.split())
    red, blue = fields[2], fields[4]
    if winner_cell and norm.fold(winner_cell) not in (norm.fold(red),
                                                      norm.fold(blue)):
        report.problem(f"the winner {winner_cell!r} is neither {red!r} nor "
                       f"{blue!r}; the bout is kept unresolved")
        winner_cell = ""
    won = None if not winner_cell \
        else 0 if norm.fold(winner_cell) == norm.fold(red) else 1
    # The verdict is kept even where the winner column could not be matched to
    # either fighter: how the bout ended is a fact the sheet states, and it is
    # not the same fact as who won it.
    add(_klass(code.group(1), int(code.group(2)), prefix, age, report),
        (red, fields[3]), (blue, fields[5]), won, decision, detail,
        phase_of(fields[0]))


def _mirrors(bouts):
    """How many rows repeat a pair already printed in the same round."""
    seen, repeats = set(), 0
    for b in bouts:
        key = (b.category, b.phase, frozenset((norm.fold(b.red),
                                               norm.fold(b.blue))))
        if key in seen:
            repeats += 1
        seen.add(key)
    return repeats


def _tournament(slug, meta, source):
    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", "national"),
        format=meta.get("format", "championship"),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        start_date=meta.get("start_date", ""),
        city=meta.get("city", ""),
        country=meta.get("country", "France"),
        source=str(source), adapter=NAME,
    )
