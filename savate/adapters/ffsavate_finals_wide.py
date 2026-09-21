"""FFSavate result sheets whose columns are drawn, not spaced.

`ffsavate_finals` reads the federation's plain finals list: a class code alone
on a line, the winner beneath it, the runner-up beneath that, columns held apart
by runs of spaces. That shape is only one of the ways the FFSavate publishes a
card, and the other two defeat a line-and-spaces reader completely.

*The ruled grid.* The 2023 Elite A semi-finals and the Ligue PACA cards are real
tables with printed rules:

    Rencontre    Catégorie   Coin     Nom et Prénom        Club        DECISION
    1            F56         ROUGE    YANGA Flora    TOULOUSE MULTI-BOXE
    1/2 FINALE                                                    YANGA FLORA à
    ELITE A 5X2                       VIVIER Aurore      PROVENCE BF   l'unanimité
                             BLEU

One bout is one table row, and a table row is five to seven *text* lines, each
holding fragments of several cells: a club name wraps, the verdict wraps, the
class code sits on its own baseline halfway down. `pdftotext -layout` interleaves
all of that into an unreadable stack - which is exactly what `ffsavate_finals`
was handed, and why it produced eleven "bouts" from this file in which a club
called KNOCK DOWN BOXING became a fighter's name. So this reader does not use
the flat text at all. It takes poppler's word geometry, rebuilds the six columns,
cuts the page into bouts at the ROUGE baselines, and reads each cell back out.

Cell boundaries come from the header words, with one correction that matters:
"Coin" and "Nom et Prénom" are centred in their cells, so the midpoint between
their centres falls *inside* the name column and swallows short surnames (GIL
Océane lost its surname to the Coin column on the first attempt). The Coin
column's true right edge is known exactly - it is the widest ROUGE/BLEU token on
the page - so that edge is used instead of the header's guess.

This is also the one FFSavate layout that states corners. ROUGE and BLEU are
printed against each name, so unlike its sibling this adapter *can* fill
`winner_corner`, and does. The winner is the name the DECISION cell leads with;
it is matched against the two fighters by counting shared name tokens, because
the verdict cell is retyped by hand and does not always agree with the entry
list ("TRILLEY YOANN" for TRILLE Yoann). A tie or no match is a problem, not a
coin toss: the bout is filed unresolved.

*The dotted leader.* The Mérignac 2023 sheet is the plain list again, but with
the columns run together by leader dots:

    M 60
    DENNI Rabah......................................BOXE FRANCAISE AMIENS   majorité
    MONACO Noah...................................M J C SAVATE COTOISE

There is no column gap left to split on, so the sibling read one bout out of
twenty-three. Splitting on the leaders instead recovers all of them.

That file also carries three competitions in one PDF - Juniors, 2e Série and
Prémium - each under its own "Résultats Finale ..." heading, each running the
same ladder of class codes. Labelled by weight alone, the Juniors M60 final and
the 2e Série M60 final become one category and one weight-class lineage, which
is the silent merge the archive's labels exist to prevent. So the heading the
document prints is carried into the label: "Juniors Men -60 kg". It is not put
into `age_class`, because "2e Série" and "Prémium" are grades rather than ages
and the archive's age classes are Young/Junior/Senior.

Inherited from `ffsavate_finals`, deliberately: the decision vocabulary, the
club-with-département pattern, and the reading of F100/M150 as the sentinel for
the open class rather than a weight anybody fought at. Extended here with the
verdicts the older cards use - hors combat, jet de l'éponge, arrêt médical -
which the finals sheets never print. Everything else follows the same two rules:
nothing the sheet does not say is filled in, and a row that cannot be read is
reported and skipped.
"""

import re
import statistics
import subprocess
import unicodedata

from savate.adapters import ffsavate_finals as _plain
from savate.schema import Bout, Placing, Report, Tournament, phase_of

NAME = "ffsavate_finals_wide"
DESCRIPTION = ("FFSavate ruled-grid result tables (Rencontre/Coin/DECISION) and "
               "dotted-leader finals lists")

# The club, as every FFSavate sheet prints it: a name, then its département.
_CLUB = _plain._CLUB
# Above this a class code is the open-class sentinel, not a weight.
_SENTINEL = _plain._SENTINEL

# The verdicts the finals sheets print, plus the ones only the older cards use.
# Stoppages are tested first: a bout stopped in the third round did not go to a
# decision, whatever else the sentence says about the judges.
_DECISIONS = [
    ("Hors combat", "abandon", r"hors\s*combat|\bh\.?\s?combat\b|\bh\.?c\.?\s*\d|\bpar\s+hc\b"),
    ("Jet de l'éponge", "abandon", r"jet\s+(?:de\s+l|d)['’\s]*[ée]ponge"),
] + _plain._DECISIONS

# A line that is nothing but a class code, optionally followed by leader dots
# and the federation's nickname for the class ("F48 ... Mouches", "M70 MI
# MOYENS"). Anything with a digit or a bracket after the code is not a heading.
_CLASS_LINE = re.compile(
    r"^\s*([FM])\s*\+?\s*(\d{2,3})\s*[.…\s]*"
    r"((?:[A-Za-zÀ-ÿ/'’°\-]+\s*){0,3})$")

# A class code wherever it appears - in a table cell, or glued to other text.
_CLASS_CELL = re.compile(r"\b([FM])\s*\+?\s*(\d{2,3})\b")

# Two or more leader dots (ASCII or the ellipsis character) hold the columns
# apart on the Mérignac sheet, where spaces no longer do.
_LEADERS = re.compile(r"[.…]{2,}")

# "Résultats Finale Juniors 2023" - one competition inside a multi-part PDF.
_SECTION = re.compile(r"^\s*r[ée]sultats?\s+finales?\s+(.+?)\s*$", re.I)

# Words in a Rencontre cell that describe the round or the bout's number rather
# than which competition it belonged to.
_ROUND_WORDS = re.compile(
    r"^(?:\d+|\d/\d|finale?s?|demi|demi-finale|quarts?|quart|poule|tournoi|"
    r"\d+x\d+)$", re.I)

# Tokens too common to identify anybody in a verdict sentence.
_STOPWORDS = {"PAR", "LES", "DES", "AUX", "UNE", "SUR", "ARRET", "REPRISE",
              "JUGES", "POINTS", "ABANDON", "FORFAIT", "COMBAT", "HORS",
              "EPONGE", "MEDICAL", "MAJORITE", "UNANIMITE", "PARTAGE",
              "DISQUALIFICATION", "BLESSURE", "ROUGE", "BLEU"}


def _fold(text):
    """Uppercase, accent-stripped - for comparing names a human retyped."""
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return stripped.upper()


def _tokens(text):
    return [t for t in re.split(r"[^A-Za-z0-9]+", _fold(text)) if len(t) >= 3]


def _decision(text):
    """(schema decision, the word the sheet printed, where it started).

    The offset is returned because these sheets print the verdict last, at the
    right-hand end of the winner's line, and everything before it is name and
    club. Deleting just the matched word is not enough: "disqualification 3 °"
    and "HC2\u00b0" leave "ication 3 \u00b0" and "\u00b0" behind, and that debris ends up
    filed as part of a club's name. Cutting the line at the verdict instead
    removes the whole of it, whatever wording followed.
    """
    for printed, decision, pattern in _DECISIONS:
        found = re.search(pattern, text, re.I)
        if found:
            return decision, printed, found.start()
    return "", "", -1


# The words that introduce a verdict and are left stranded when it is cut off:
# "... VANNETAIS   par forfait" cuts at "forfait" and leaves a trailing "par".
_CONNECTOR = re.compile(r"[\s.\u2026]*\b(?:par|pour|[\u00e0a])\s*$|[\s.\u2026]*\b[ld]['\u2019]\s*$",
                        re.I)


def _before_decision(text, at):
    """`text` up to where its verdict began, if that leaves anything to read."""
    if at < 0:
        return text.rstrip()
    head = text[:at].rstrip()
    while True:
        shorter = _CONNECTOR.sub("", head)
        if shorter == head:
            break
        head = shorter
    # A verdict at the very start of the line is not a verdict at the end of
    # one, so the cut is refused rather than allowed to eat the whole row.
    return head if len(head.strip()) >= 4 else text.rstrip()


def _unwrap(text):
    """Rejoin a word poppler split across two lines at its hyphen.

    "TOULOUSE MULTI-" / "BOXE" is one club, and the break is the cell's, not
    the name's.
    """
    return re.sub(r"(\w)-\s+(\w)", r"\1-\2", " ".join(str(text or "").split()))


def _category(letter, kilos, report, prefix=""):
    """(label, gender, weight, bound) for a class code.

    The prefix is whatever the document said this competition was - an age
    class, a series, a grade. Without it two different competitions printed in
    one PDF share a label, and every index that keys on the label merges them.
    """
    gender = "Women" if letter.upper() == "F" else "Men"
    head = (prefix + " ") if prefix else ""
    if kilos >= _SENTINEL:
        code = f"{letter.upper()}{kilos}"
        seen = report.notes.setdefault("sentinel_classes", [])
        if code not in seen:
            seen.append(code)
        return f"{head}{gender} open", gender, "", "over"
    return f"{head}{gender} -{kilos} kg", gender, str(kilos), "under"


# --------------------------------------------------------------------------
# The ruled grid
# --------------------------------------------------------------------------

def _header(line):
    """The header words of the grid table, keyed by column, or None."""
    words = {w.text: w for w in line}
    if "Rencontre" not in words or "Coin" not in words:
        return None
    if "Club" not in words or "DECISION" not in words:
        return None
    cells = {key: [words[key].x0, words[key].x1]
             for key in ("Rencontre", "Catégorie", "Coin", "Club", "DECISION")
             if key in words}
    if "Nom" in words:
        cells["Nom"] = [words["Nom"].x0,
                        words["Prénom"].x1 if "Prénom" in words else words["Nom"].x1]
    if len(cells) < 5:
        return None
    return cells


def _bands(cells, coin0, coin1):
    """The five x boundaries between the six columns.

    Header words are centred in their cells, so a midpoint between two header
    centres is not a cell edge. It is close enough everywhere except the
    Coin/Nom join, where it reaches into the name column far enough to eat a
    three-letter surname - so there the Coin column's measured right edge is
    used, which is exact.
    """
    def gap(left, right):
        return (cells[left][1] + cells[right][0]) / 2

    rencontre_cat = gap("Rencontre", "Catégorie") if "Catégorie" in cells else coin0 - 10
    cat_coin = (cells["Catégorie"][1] + coin0) / 2 if "Catégorie" in cells else coin0 - 2
    coin_nom = coin1 + 3
    nom_club = gap("Nom", "Club") if "Nom" in cells else (coin1 + cells["Club"][0]) / 2
    club_dec = gap("Club", "DECISION")
    return rencontre_cat, cat_coin, coin_nom, nom_club, club_dec


def _series(text):
    """What the Rencontre cell says this competition was, minus the round."""
    words = [w for w in str(text or "").split()
             if not _ROUND_WORDS.match(w) and not _CLASS_CELL.fullmatch(w)]
    label = " ".join(words).strip()
    if not label:
        return ""
    return " ".join(w if len(w) <= 2 and w.isupper() else w.capitalize()
                    for w in label.split())


def _winner_of(verdict, red, blue):
    """("red"|"blue"|"", why) - who the DECISION cell names.

    Counted, not guessed. The cell is typed by hand from the entry list and
    misspells surnames often enough ("TRILLEY" for TRILLE) that an equality
    test loses real results; a shared given name is enough to identify the
    winner when the surname has been mangled. Nothing beats nothing, and a tie
    is a tie - both leave the bout unresolved.
    """
    said = set(_tokens(verdict)) - _STOPWORDS
    red_tokens = set(_tokens(red)) - _STOPWORDS
    blue_tokens = set(_tokens(blue)) - _STOPWORDS
    shared = red_tokens & blue_tokens
    red_hits = len((red_tokens - shared) & said)
    blue_hits = len((blue_tokens - shared) & said)
    if red_hits > blue_hits:
        return "red", ""
    if blue_hits > red_hits:
        return "blue", ""
    if not red_hits and not blue_hits:
        return "", "the verdict names neither fighter"
    return "", "the verdict matches both fighters equally"


def _read_grid(words, slug, meta, report):
    from savate import pdf

    bouts, placings = [], []
    cells = None
    pages = pdf.by_page(words)

    for number in sorted(pages):
        page = pages[number]
        header_y = None
        for line in pdf.rows(page, 3.0):
            found = _header(line)
            if found:
                cells, header_y = found, line[0].top
                break
        if cells is None:
            continue
        top = header_y + 4 if header_y is not None else min(w.top for w in page) - 1
        body = [w for w in page if w.top > top]
        corners = [w for w in body if w.text.upper() in ("ROUGE", "BLEU")]
        if not corners:
            report.problem(f"page {number}: a grid header but no ROUGE/BLEU rows")
            continue

        coin0 = min(w.x0 for w in corners)
        coin1 = max(w.x1 for w in corners)
        b_rc, b_cc, b_cn, b_nc, b_cd = _bands(cells, coin0, coin1)

        def column(word):
            middle = word.middle
            if middle < b_rc:
                return "rencontre"
            if middle < b_cc:
                return "categorie"
            if middle < b_cn:
                return "coin"
            if middle < b_nc:
                return "nom"
            if middle < b_cd:
                return "club"
            return "decision"

        reds = sorted({round(w.top, 1) for w in corners if w.text.upper() == "ROUGE"})
        blues = sorted({round(w.top, 1) for w in corners if w.text.upper() == "BLEU"})
        steps = [reds[i + 1] - reds[i] for i in range(len(reds) - 1)]
        # Half a row below the last BLEU is where the table ends. Without a
        # bottom the final bout swallows the officials' names in the footer.
        step = statistics.median(steps) if steps else 30.0

        for index, red_top in enumerate(reds):
            blue_top = next((b for b in blues if b > red_top), None)
            if blue_top is None:
                report.problem(f"page {number}: a ROUGE row with no BLEU beneath it")
                continue
            start = top if index == 0 else (blues[index - 1] + red_top) / 2
            if index + 1 < len(reds):
                end = (blue_top + reds[index + 1]) / 2
            else:
                end = blue_top + step / 2
            band = [w for w in body if start <= w.top < end]
            middle = (red_top + blue_top) / 2

            def cell(which, lower=None, upper=None):
                picked = [w for w in band if column(w) == which
                          and (lower is None or w.top >= lower)
                          and (upper is None or w.top < upper)]
                picked.sort(key=lambda w: (w.top, w.x0))
                return _unwrap(" ".join(w.text for w in picked))

            code = _CLASS_CELL.search(cell("categorie"))
            red = cell("nom", None, middle)
            blue = cell("nom", middle, None)
            red_club = cell("club", None, middle)
            blue_club = cell("club", middle, None)
            verdict = cell("decision")
            where = f"page {number} bout {index + 1}"
            if not (red and blue):
                report.problem(f"{where}: a corner has no name, skipped")
                continue
            if not code:
                report.problem(f"{where} ({red} v {blue}): no class code in the "
                               f"Catégorie cell, skipped")
                continue

            series = _series(cell("rencontre"))
            prefix = series or meta.get("age_class", "")
            label, gender, kilos, bound = _category(
                code.group(1), int(code.group(2)), report, prefix)
            decision, printed, _at = _decision(verdict)
            corner, why = _winner_of(verdict, red, blue)
            if not verdict:
                report.problem(f"{where} ({label}): no verdict printed")
            elif not corner:
                report.problem(f"{where} ({label}): {why} - {verdict!r}")
            winner = {"red": red, "blue": blue}.get(corner, "")
            loser = {"red": blue, "blue": red}.get(corner, "")
            if corner and not decision:
                report.problem(f"{where} ({label}): verdict {verdict!r} does not "
                               f"name a way the bout ended")

            phase = phase_of(cell("rencontre"))
            identifier = f"{slug}-p{number}-{index + 1:02d}"
            bouts.append(Bout(
                tournament=slug, bout_id=identifier,
                category=label, gender=gender,
                age_class=meta.get("age_class", ""),
                weight_kg=kilos, weight_bound=bound,
                phase=phase,
                red=red, red_club=red_club,
                blue=blue, blue_club=blue_club,
                winner_corner=corner, winner=winner, loser=loser,
                decision=decision if corner else "",
                decision_detail=printed if corner else "",
                status="decided" if corner else "unresolved",
                result_source="reported" if corner else "",
            ))
            if phase == "final" and corner:
                clubs = {"red": red_club, "blue": blue_club}
                other = "blue" if corner == "red" else "red"
                for rank, who, club in ((1, winner, clubs[corner]),
                                        (2, loser, clubs[other])):
                    placings.append(Placing(
                        tournament=slug,
                        placing_id=f"{identifier}-{rank}",
                        category=label, gender=gender,
                        age_class=meta.get("age_class", ""),
                        weight_kg=kilos, weight_bound=bound,
                        rank=str(rank), medal={1: "gold", 2: "silver"}[rank],
                        fighter=who, club=club,
                        country=meta.get("country", "France"),
                        result_source="reported",
                    ))
    return bouts, placings


# --------------------------------------------------------------------------
# The plain list, with leader dots or column gaps
# --------------------------------------------------------------------------

def _peel(body):
    """(name, club) from "SURNAME Given CLUB NAME", with no gap to split on.

    Some rows separate every field with a single space. Surnames are set in
    capitals on these sheets and given names are not, so the name is the run of
    capitals plus the first merely-capitalised word after it. Everything left is
    the club.

    Only *one* word is peeled from the club — the given name that lost its
    column.  Anything further left belongs to the club: a multi-word name like
    "Nouveau Chevalier Roze" is a real club, and peeling it all would make it
    look like the fighter's name.
    """
    parts = body.split()
    if len(parts) < 3:
        return "", ""
    taken = []
    while parts and parts[0].isupper():
        taken.append(parts.pop(0))
    if not taken or not parts:
        return "", ""
    # Only peel ONE given-name word.  Everything else is the club.
    if parts[0][:1].isupper() and not parts[0].isupper():
        taken.append(parts.pop(0))
    if not parts:
        return "", ""
    return " ".join(taken), " ".join(parts)


def _competitor(line):
    """(name, club, decision, printed) from one printed line, or None."""
    decision, printed, at = _decision(line)
    body = _before_decision(line, at).strip()
    if len(body) < 4:
        return None

    parts = None
    if _LEADERS.search(body):
        pieces = [p.strip(" .…") for p in _LEADERS.split(body)]
        pieces = [p for p in pieces if p]
        if len(pieces) >= 2:
            parts = [pieces[0], pieces[-1]]
    if parts is None:
        parts = [p.strip() for p in re.split(r"\s{2,}", body) if p.strip()]

    if len(parts) < 2:
        name, club = _peel(body)
        if not name:
            return None
        parts = [name, club]

    club = ""
    found = _CLUB.match(parts[-1])
    if found:
        club = found.group(1).strip()
        parts = parts[:-1]
    elif len(parts) > 2:
        club = parts[-1]
        parts = parts[:-1]
    elif len(parts) == 2:
        club = parts[-1]
        parts = parts[:-1]

    # A single space between the given name and the club hands the club back
    # with the given name glued to its front.  Clubs are set in capitals; given
    # names are not.  Peel only the first word — everything else is the club.
    if club:
        head = club.split(" ", 1)
        if len(head) == 2:
            word = head[0]
            if not word.isupper() and word[:1].isupper():
                parts.append(word)
                club = head[1].strip()
            # else: multi-word club, leave it — peeling "Nouveau Chevalier
            # Roze" would put the whole name on the fighter.

    name = " ".join(" ".join(parts).split()).strip(" .…")
    club = " ".join(club.split()).strip(" .…")
    if not name or not re.search(r"[A-Za-zÀ-ÿ]", name):
        return None
    if re.search(r"\d{2}/\d{2}/\d{4}|classement|r[ée]sultat|championnat|"
                 r"f[ée]d[ée]ration|t[ée]l[ée]phone", name, re.I):
        return None
    return name, club, decision, printed


def _read_lines(text, slug, meta, report):
    bouts, placings = [], []
    section = ""
    current = None
    block = []

    def flush():
        if not current or not block:
            return
        label, gender, kilos, bound = current
        people = [p for p in (_competitor(line) for line in block) if p]
        if len(people) < 2:
            report.problem(f"{label}: {len(people)} competitor(s) on the sheet, "
                           f"a final needs two")
            return
        if len(people) > 2:
            report.problem(f"{label}: {len(people)} lines under one class code, "
                           f"reading the first two as the final")
            people = people[:2]
        at = next((i for i, p in enumerate(people) if p[2]), 0)
        winner, loser = people[at], people[1 - at]
        decision, printed = winner[2], winner[3]
        if not decision:
            report.problem(f"{label}: no decision printed for {winner[0]}")
        if winner[0] == loser[0]:
            report.problem(f"{label}: both lines name {winner[0]}, skipped")
            return

        index = len(bouts) + 1
        bouts.append(Bout(
            tournament=slug, bout_id=f"{slug}-{index:02d}-final",
            category=label, gender=gender,
            age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound, phase="final",
            # Printed order. The sheet never says who stood where, so the
            # corner is not claimed - only the winner is.
            red=winner[0], red_club=winner[1],
            blue=loser[0], blue_club=loser[1],
            winner=winner[0], loser=loser[0], winner_corner="",
            decision=decision, decision_detail=printed,
            status="decided", result_source="reported",
        ))
        for rank, who in ((1, winner), (2, loser)):
            placings.append(Placing(
                tournament=slug, placing_id=f"{slug}-{index:02d}-{rank}",
                category=label, gender=gender,
                age_class=meta.get("age_class", ""),
                weight_kg=kilos, weight_bound=bound,
                rank=str(rank), medal={1: "gold", 2: "silver"}[rank],
                fighter=who[0], club=who[1],
                country=meta.get("country", "France"),
                result_source="reported",
            ))

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = _SECTION.match(stripped)
        if heading and not _LEADERS.search(stripped):
            flush()
            current, block = None, []
            section = re.sub(r"\s*(19|20)\d{2}\s*$", "", heading.group(1)).strip()
            report.notes.setdefault("sections", [])
            if section and section not in report.notes["sections"]:
                report.notes["sections"].append(section)
            continue
        found = _CLASS_LINE.match(line)
        if found:
            flush()
            prefix = section or meta.get("age_class", "")
            current = _category(found.group(1), int(found.group(2)), report, prefix)
            block = []
            continue
        if current:
            block.append(line)
    flush()
    return bouts, placings


# --------------------------------------------------------------------------

def _layout_text(path, report):
    try:
        return pdf.text(str(path))
    except Exception as e:
        report.problem(f"pdf.text failed on {path}: {e}")
        try:
            done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                  capture_output=True, text=True, timeout=120)
            return done.stdout or ""
        except Exception as e2:
            report.problem(f"pdftotext failed on {path}: {e2}")
            return ""


def read(source, slug, meta=None, **options):
    from savate import pdf, sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    tournament = Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", "national"),
        format=meta.get("format", "championship"),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        start_date=meta.get("start_date", ""),
        city=meta.get("city", ""),
        country=meta.get("country", "France"),
        source=source, adapter=NAME,
        competition=meta.get("competition", ""),
    )

    try:
        path = sources.fetch(source)
    except Exception as e:
        report.problem(f"could not fetch {source}: {e}")
        return tournament, [], report

    text = _layout_text(path, report)

    # Same dated venue line as the narrow sheets carry; see ffsavate_finals.
    from savate import normalize as norm
    for line in text.splitlines()[:12]:
        when, city, _dept = norm.dateline(line)
        if when:
            tournament.start_date = tournament.start_date or when
            tournament.city = tournament.city or city
            if not tournament.year:
                tournament.year = when[:4]
            break

    words = []
    try:
        words = pdf.words(path)
    except Exception as e:
        report.problem(f"no word geometry available: {e}")

    grid = any(_header(line) for line in pdf.rows(words, 3.0)) if words else False
    report.notes["layout"] = "grid" if grid else "list"
    try:
        if grid:
            bouts, placings = _read_grid(words, slug, meta, report)
        else:
            bouts, placings = _read_lines(text, slug, meta, report)
    except Exception as e:
        # Report, do not crash: a malformed sheet must not take the build down.
        report.problem(f"{type(e).__name__} while reading: {e}")
        bouts, placings = [], []

    report.read = len(words) if grid else len(text.splitlines())
    report.notes["bouts"] = len(bouts)
    report.notes["placings"] = len(placings)
    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"]) +
            " read as the open class: the code exceeds every real savate "
            "weight, and no document states what it stands for")
    if not bouts:
        report.problem("no bouts found - this may not be an FFSavate result sheet")
    return tournament, bouts + placings, report
