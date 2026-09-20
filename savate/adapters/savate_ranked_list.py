"""University savate: a classification printed deeper than a podium.

This is the French university federation's paperwork (sport-u.com) and the FISU
world university championship it feeds. What links these documents, and what
makes them worth their own adapter, is that they rank *everyone who competed*,
not only the three who reached a podium. The rest of this archive is medals:
before 2023 the federations published a gold, a silver, a bronze and nothing
else, and a competitor who finished fourth left no trace anywhere. These sheets
print 4°, 5°, 6°, and they print the people who finished below that too.

Two shapes carry that, and both are read here because they are the same
federation's output on either side of the same event.

*The classement.* One gender heading, then a weight heading, then ranked lines::

    Classement féminin
              moins 50kg
    1°        POPADIC      Ivana         SERBIE
    2°        MAY          Marine        FRANCE
    ...
    6°        LABRIQUE     Catherine     BELGIQUE

Three columns after the rank - family name in capitals, given name, country -
separated by the column gap poppler preserves with `-layout`. A line may carry
`forfait` where a rank belongs, and a line may carry no rank at all: the sheet
lists whoever is left under the last ranked place without ordering them. Neither
becomes a placing. `forfait` says someone did not take their place, and an
unranked line says the sheet declined to rank them; writing either down as a
rank would be writing down the one fact the document refuses to state. Both are
reported by name, so that nothing disappears quietly.

*The livret.* A category code in the corner, a poule table, then the bouts::

    CAT  F50
                NOM PRENOM              UNIVERSITE      1T  2T  3T  TOTAL  Classt
        A   1   SEDDIK KHODJA LINDA     UDL - UTE LYON   3       3    6      1
    ...
                TIREUR ROUGE        TIREUR BLEU        RESULTATS       Avertisst
        P1  A-B SEDDIK KHODJA ...   LE COM ROMANE      SEDDIK KHODJA ... 1

This one is a table in a PDF, which is to say words at coordinates, so it is
read through `savate.pdf`'s geometry. Four things about that reading are worth
stating, because each is a place where the obvious shortcut is wrong.

*Columns are not where their headers are.* Every header in these sheets is
centred over its column while the data under it is left-aligned - `CLUB` sits at
x=257 above a club that starts at x=214 - so a band taken from a header cuts the
first word off every row. The name and club columns are therefore taken from the
data: the club column is where most entry rows start their second run of words,
and the bout table is drawn on the same grid, so the same two positions split
TIREUR ROUGE from TIREUR BLEU. The winner's column is centred rather than
left-aligned, so it is found as the one wide gap in the ink to the right of the
blue column. Only the numeric columns, which really are centred under their
headers, are read by header position.

*Names do not always leave a gap.* "LAWSON BOUH MANA MAIMARA" ends two points
before its university begins, which is less than the gap between two words of
one name. Grouping by gaps alone therefore silently glues a fighter to their
club - and then to the next fighter, in a bout row. Hence the column positions
above, which do not care how tight the row is.

*The poule comes from the entry table, the tour from the label above.* The
`P1`/`P2` and `1°TOUR` labels are set beside a group of rows rather than on one
of them, and one sheet centres the label in its group - which puts it a few
points *below* the first row it governs. So "the last label above this row"
loses the first bout of every group to the group before, and "the nearest label"
is a coin toss between two labels sixteen points either side. A bout takes the
last label at or above it, allowing a label up to nine points below: comfortably
more than the six-point overhang of a centred label, comfortably less than the
distance to the next one. The poule is not read from those labels at all - a
competitor's poule is in the entry table, where it is unambiguous.

*Points are joined from the poule table, and dropped if they disagree.* The
sheet prints each fighter's score per tour in the 1T/2T/3T columns and prints
the bouts separately; the two are the same fact from two directions, so joining
them is reading the document rather than guessing at it. But the join rests on
having identified the tour correctly, so it is checked: the winner must have
scored strictly more than the loser. A pair that fails keeps its bout, loses its
points, and is reported. The warnings are cross-checked the same way, against
the total the poule table prints for each fighter.

What this adapter will not do:

*It does not invent a corner.* The livret's bout rows are printed under TIREUR
ROUGE and TIREUR BLEU, so there the corner is stated and is recorded. A
two-competitor final drawn as a bracket is labelled TIREUR A and TIREUR B, which
is a slot in a bracket and not a corner; that bout names a winner and leaves
`winner_corner` empty, as the FFSavate finals sheets do.

*It does not invent a decision.* A poule row says who won and what they scored.
It never says whether the bout went the distance, so `decision` stays empty
rather than becoming "points" because points happen to be printed.

*It does not derive the semi-finals from the bracket.* The livret draws a
bracket whose last column is the classification. The classification is read,
because it is printed; the bouts that produced it are not reconstructed from who
appears in which box.

*It does not claim an age class nobody printed.* A university championship
states no age class, so a label is "Women -50 kg" and `age_class` is empty
unless the manifest entry supplies one. That is reported on every read, because
a label without an age class is exactly the label that can silently merge two
different competitions if it is ever matched across tournaments.
"""

import re
import statistics
import subprocess

from savate import normalize as norm
from savate import pdf
from savate.schema import MEDALS, Bout, Placing, Report, Tournament

NAME = "savate_ranked_list"
DESCRIPTION = ("French/world university savate: degree-ranked classements and "
               "the FFSU livret (poule bouts, points, classification)")

# ---------------------------------------------------------------- shared ----

# Two words of one name sit one or two points apart; two columns sit twelve or
# more apart in the tightest sheet seen. Eight splits them with room either way,
# and is only ever used where a column position is not available.
COLUMN_GAP = 8.0
# A value belongs to a numeric column when its centre is under the header's.
COLUMN_SLACK = 12.0


def _slug_bit(text):
    """A row id's category part. The sign is spelled out, not dropped.

    "Women -70 kg" and "Women +70 kg" are two classes, and stripping the
    punctuation out of both leaves one id for each bout in either - which is
    every bout of one of them silently overwriting the other.
    """
    text = re.sub(r"\+\s*(\d)", r"plus \1", str(text or ""))
    text = re.sub(r"-\s*(\d)", r"minus \1", text)
    return re.sub(r"[^a-z0-9]+", "-", norm.fold(text)).strip("-") or "x"


def _pdftotext(path, report):
    """The document as poppler's -layout text, or "" with a problem logged."""
    try:
        done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
    except Exception as e:                                # pragma: no cover
        report.problem(f"pdftotext failed: {e}")
        return ""
    if done.returncode != 0:
        report.problem(f"pdftotext failed: {done.stderr.strip()[:200]}")
        return ""
    return done.stdout


def _groups(words, gap=COLUMN_GAP):
    """Words split into runs, a run ending wherever a column gap opens."""
    out = []
    for w in words:
        if out and w.x0 - out[-1][-1].x1 < gap:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _is_number(text):
    return bool(re.fullmatch(r"-?\d+", text))


def _label(gender, kg, bound, age=""):
    weight = f"{'+' if bound == 'over' else '-'}{kg} kg" if kg else ""
    return " ".join(p for p in (age, gender, weight) if p)


def _tournament(slug, meta, source):
    meta = meta or {}
    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""), format=meta.get("format", ""),
        age_class=meta.get("age_class", ""), year=meta.get("year", ""),
        start_date=meta.get("start_date", ""), end_date=meta.get("end_date", ""),
        city=meta.get("city", ""), country=meta.get("country", ""),
        source=str(source), adapter=NAME,
    )


# ----------------------------------------------------------- classement ----

# "Classement féminin" / "Classement masculin", the only gender the sheet gives.
_SECTION = re.compile(r"^\s*classement\s+(feminin|masculin)", re.I | re.M)
# "1°", "12°" - the degree mark is this federation's ordinal, not a temperature.
_RANKED = re.compile(r"^(\d{1,2})\s*[°ºo]\s+(.+)$", re.M)
_FORFAIT = re.compile(r"^(forfait)\b\s*(.*)$", re.I)
# The same heading as _SECTION, as it is printed: `norm.fold` collapses a whole
# document onto one line, so a folded document is not a thing to anchor on.
_IS_CLASSEMENT = re.compile(r"(?im)^\s*classement\s+(f[ée]minin|masculin)")
# "moins 50kg", "50-55kg", "60- 65", "plus 82".
_HEADING = re.compile(r"(?i)^(?:(moins|plus|[-+−])\s*)?"
                      r"(\d{2,3})\s*(?:[-–]\s*(\d{2,3}))?\s*(?:kgs?)?$")


def _weight(label, report):
    """(kg, bound, printed) for a weight heading, or None.

    A band - "50-55kg" - is the class its upper number names, which is how the
    rest of this archive records one. The band as printed is kept in the report
    rather than in the label, so that "-55 kg" here and "-55 kg" in a FISav
    sheet are one string and one class.
    """
    text = " ".join(str(label or "").split())
    m = _HEADING.match(text)
    if not m:
        return None
    word, low, high = (m.group(1) or "").lower(), m.group(2), m.group(3)
    if high:
        return high, "under", text
    if word in ("plus", "+"):
        return low, "over", text
    if word in ("moins", "-", "−"):
        return low, "under", text
    # A bare number names a class without saying which side of it. Read as an
    # upper bound, which is what every other heading in these sheets means -
    # and said out loud rather than assumed silently.
    report.problem(f"weight heading {text!r} gives no bound; read as under {low} kg")
    return low, "under", text


def _person(rest, report, where):
    """(name, country) from the columns after a rank, or (None, "")."""
    parts = [p.strip() for p in re.split(r"\s{2,}", rest.strip()) if p.strip()]
    if len(parts) >= 3:
        name, country = " ".join(parts[:-1]), parts[-1]
    elif len(parts) == 2:
        # One column gap survived instead of two. The name is kept whole rather
        # than split on a guess about which word is the given name.
        name, country = parts[0], parts[1]
    else:
        report.problem(f"{where}: {rest.strip()!r} is not a name and a country")
        return None, ""
    if not re.search(r"[A-Za-zÀ-ÿ]", name):
        report.problem(f"{where}: {rest.strip()!r} has no name in it")
        return None, ""
    if any(c.isdigit() for c in country):
        report.problem(f"{where}: {country!r} is not a country; left empty")
        country = ""
    return name, norm.country(country)


def _read_classement(text, slug, meta, report, ranks="all"):
    """Placings from a degree-ranked classement."""
    age = (meta or {}).get("age_class", "")
    placings, classes = [], []
    gender, klass = "", None
    for raw in text.splitlines():
        # `flat` reads the headings; `body` keeps the column gaps, which are the
        # only thing separating a family name from a given name from a country.
        body, flat = raw.strip(), " ".join(raw.split())
        if not flat:
            continue
        section = _SECTION.match(norm.fold(flat))
        if section:
            gender = "Women" if section.group(1).startswith("f") else "Men"
            klass = None
            continue
        if not gender:
            continue                      # still in the title block
        ranked = _RANKED.match(body)
        forfeit = None if ranked else _FORFAIT.match(body)
        if not ranked and not forfeit:
            found = _weight(flat, report)
            if found:
                kg, bound, printed = found
                klass = {"category": _label(gender, kg, bound, age),
                         "gender": gender, "age_class": age,
                         "weight_kg": kg, "weight_bound": bound}
                classes.append(f"{klass['category']} <- {printed!r}")
            elif klass and len(flat.split()) >= 2 and \
                    re.search(r"[A-Za-zÀ-ÿ]", flat):
                # A competitor the sheet lists under the class without ranking.
                report.problem(f"{klass['category']}: {flat!r} is listed with "
                               f"no rank; the sheet does not place them, so "
                               f"neither does this")
            continue
        if klass is None:
            report.problem(f"a ranked line appears before any weight heading: "
                           f"{flat!r}")
            continue
        where = klass["category"]
        if forfeit:
            name, _country = _person(forfeit.group(2), report, where)
            report.problem(f"{where}: {name or flat!r} is printed 'forfait' "
                           f"where a rank belongs, so no placing is recorded")
            continue
        rank, rest = ranked.group(1), ranked.group(2)
        if ranks == "podium" and rank not in MEDALS:
            continue
        name, country = _person(rest, report, where)
        if not name:
            continue
        placings.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{_slug_bit(where)}-{rank}",
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=name, country=country,
            result_source="reported", **klass))
    report.notes["classes"] = classes
    return placings


# ---------------------------------------------------------------- livret ----

_CAT_CODE = re.compile(r"(?i)^(?:(?P<letter>[FM])\s*)?"
                       r"(?:(?P<word>plus|moins)\s*)?(?P<sign>[-+−])?\s*"
                       r"(?P<kg>\d{2,3})$")
_PAIRING = re.compile(r"^[A-H][-,.;][A-H]$")
_TOUR = re.compile(r"(?i)^(\d)\s*[°ºo]?\s*tour$")
_ENTRY_LETTER = re.compile(r"^[A-H]$")
# The classification column: "1 Championne de France", "3 3ème Place". The rank
# is a bare digit, so it is only read as one when the words printed beside it -
# beside it, not somewhere else on the line - say that it is a placing.
_PLACE_WORDS = re.compile(r"(?i)champion|vice|place|finalist")
_PLACE_REACH = 80.0
# The podium graphic instead writes the ordinal under the name it belongs to.
_ORDINAL = re.compile(r"(?i)^([1-9])\s*(?:er|ere|ère|eme|ème|éme|e)$")


def _category_of(code, gender, report, notes):
    """(kg, bound, gender) from a livret category code, or None.

    "F50" is women under 50 kg. The code carries no sign, but the same sheet
    writes "Plus70" and "Plus82" for the classes that have no upper limit, so a
    bare code is the class's upper bound by the document's own usage. That is an
    inference about a coding scheme rather than something the sheet states, so
    it is noted once per document rather than assumed in silence.
    """
    text = " ".join(str(code or "").split()).replace(" ", "")
    m = _CAT_CODE.match(text)
    if not m:
        return None
    letter = (m.group("letter") or "").upper()
    if letter:
        gender = "Women" if letter == "F" else "Men"
    word, sign = (m.group("word") or "").lower(), m.group("sign") or ""
    if word == "plus" or sign == "+":
        bound = "over"
    elif word == "moins" or sign in ("-", "−"):
        bound = "under"
    else:
        bound = "under"
        notes.add(text)
    return m.group("kg"), bound, gender


def _blocks(lines):
    """The document split into category blocks, each starting at its CAT line."""
    out, current = [], None
    for line in lines:
        if line[0].text.upper() == "CAT" and len(line) >= 2:
            current = []
            out.append(current)
        if current is not None:
            current.append(line)
    return out


def _numeric_columns(lines, labels):
    """{label: centre x} for the numeric headers, gathered across a header band.

    The headers of one table are not always on one extracted line: "Classt" can
    sit half a point above "1T" and land in a row of its own. So the labels are
    collected from every line within a few points of the one carrying "NOM".
    """
    found = {}
    for line in lines:
        for w in line:
            key = norm.fold(w.text).strip(":")
            if key in labels and key not in found:
                found[key] = w.middle
    return found


def _alpha(words):
    return [w for w in words if not _is_number(w.text)]


def _entry_rows(lines):
    """[(line, words after the letter and index)] for a poule table."""
    out = []
    for line in lines:
        texts = [w.text for w in line]
        at = next((i for i in range(len(texts) - 1)
                   if _ENTRY_LETTER.match(texts[i])
                   and re.fullmatch(r"\d{1,2}", texts[i + 1])), None)
        if at is not None:
            out.append((line, texts[at], line[at + 2:]))
    return out


def _club_column(rows):
    """Where the club column starts, from the rows that leave a gap before it."""
    starts = []
    for _line, _letter, rest in rows:
        runs = _groups(_alpha(rest))
        if len(runs) >= 2:
            starts.append(runs[1][0].x0)
    if not starts:
        return None
    return statistics.median(starts)


def _split_at(words, edge):
    """(left of the edge, from the edge rightwards)."""
    if edge is None:
        return words, []
    return ([w for w in words if w.x0 < edge - 3],
            [w for w in words if w.x0 >= edge - 3])


def _entries(lines, report, where):
    """[{name, club, letter, poule, line}] from a livret poule table."""
    rows = _entry_rows(lines)
    club_x = _club_column(rows)
    out, previous, poule = [], "", 0
    for line, letter, rest in rows:
        words = _alpha(rest)
        name_words, club_words = _split_at(words, club_x)
        if not name_words:                       # the split found nothing left
            runs = _groups(words)
            name_words = runs[0] if runs else []
            club_words = runs[1] if len(runs) > 1 else []
        if not name_words:
            report.problem(f"{where}: an entry row with no name: "
                           f"{pdf.text_of(line)!r}")
            continue
        # The letters restart at A in every poule and the printed poule number
        # is not on the entry row in every sheet, so the restart is what says
        # where one poule ends. That is the sheet's own ordering, not a guess.
        if not previous or letter <= previous:
            poule += 1
        previous = letter
        clubs = _groups(club_words)
        out.append({"name": pdf.text_of(name_words),
                    "club": pdf.text_of(clubs[0]) if clubs else "",
                    "letter": letter, "poule": str(poule), "line": line})
    return out, club_x


def _entry_points(entry, columns):
    """{'1': '3', '2': '-1', ...} - the fighter's score in each tour."""
    points = {}
    for w in entry["line"]:
        if not _is_number(w.text):
            continue
        for tour in ("1", "2", "3", "4"):
            centre = columns.get(f"{tour}t")
            if centre is not None and abs(w.middle - centre) <= COLUMN_SLACK:
                points[tour] = w.text
    return points


def _warning_columns(block, report, where):
    """(avertissement-rouge x, avertissement-bleu x) for the bout table."""
    head = next((l for l in block
                 if any(norm.fold(w.text).startswith("resultat") for w in l)
                 and any(norm.fold(w.text) == "tireur" for w in l)), None)
    if head is None:
        return None, None
    marks = sorted((w for l in block if abs(l[0].top - head[0].top) <= 8
                    for w in l if norm.fold(w.text).startswith("avertiss")),
                   key=lambda w: w.x0)
    if len(marks) < 2:
        report.problem(f"{where}: the bout table has no two warning columns, "
                       f"so warnings are left empty")
        return None, None
    return marks[0].middle, marks[1].middle


def _result_column(bout_lines, club_x):
    """Where the RESULTATS column starts: the one wide gap right of the blue one.

    The winner's name is centred in its cell rather than left-aligned, so it has
    no fixed left edge to key on. What it does have is clear air between it and
    the blue corner's column - fifty points and more in every sheet seen, where
    two words of one name are two apart.
    """
    words = sorted((w for line in bout_lines for w in _alpha(line)
                    if club_x is None or w.x0 >= club_x - 3),
                   key=lambda w: w.x0)
    best, edge, reach = 0.0, None, None
    for w in words:
        if reach is not None and w.x0 - reach > best:
            best, edge = w.x0 - reach, (w.x0 + reach) / 2
        reach = w.x1 if reach is None else max(reach, w.x1)
    return edge if best >= 20 else None


# A tour label is set beside its group of rows, sometimes level with the
# group's first row and sometimes a little below it, so a label up to this far
# below a row still governs that row. Kept well under the distance to the next
# label - six points below in the tightest sheet, sixteen above the next.
_TOUR_REACH = 9.0


def _tour_of(line, tours):
    """Which tour a bout row belongs to: the last label at or above it."""
    if not tours:
        return ""
    above = [l for l in tours if l[0].top <= line[0].top + _TOUR_REACH]
    label = max(above, key=lambda l: l[0].top) if above else tours[0]
    return _TOUR.match(pdf.text_of(label[:1])).group(1)


def _match(printed, entries, report, where):
    """The entry a printed name refers to, or None.

    These sheets contain typing errors - one prints the winner of a bout as
    "PROKOP Ttouan" against an entry of "PROKOP Titouan" - so a name that does
    not match exactly is matched on its family name, and only when exactly one
    entry answers to it. The entry's spelling is the one kept, so that a bout
    and its fighter are the same string.
    """
    key = norm.fold(printed)
    if not key:
        return None
    exact = [e for e in entries if norm.fold(e["name"]) == key]
    if len(exact) == 1:
        return exact[0]
    family = key.split()[0]
    near = [e for e in entries if norm.fold(e["name"]).split()[:1] == [family]]
    if len(near) == 1:
        if report is not None and norm.fold(near[0]["name"]) != key:
            report.problem(f"{where}: {printed!r} read as {near[0]['name']!r}, "
                           f"which is how the entry table spells it")
        return near[0]
    return None


def _named_left_of(lines, index, w, entries, where):
    """The entry whose name is printed immediately left of a rank, or None.

    The classification prints the name and its rank on one line in some sheets
    and on two in others, so both are tried - nearest first - and the candidate
    is accepted only when the poule table recognises it. That is what stops a
    university's name being read as a competitor's.
    """
    for line in [lines[index]] + list(reversed(lines[max(0, index - 3):index])):
        left = [x for x in line if x.x1 < w.x0 - 4 and x is not w]
        runs = [r for r in _groups(_alpha(left)) if pdf.text_of(r).strip()]
        if not runs:
            continue
        entry = _match(pdf.text_of(runs[-1]), entries, None, where)
        if entry is not None:
            return entry, pdf.text_of(runs[-1])
    return None, ""


def _named_under(lines, index, w, entries, where):
    """The entry whose name the podium graphic prints above an ordinal."""
    for line in reversed(lines[max(0, index - 4):index + 1]):
        candidates = [x for x in line if x is not w]
        hit = next((x for x in candidates
                    if x.x0 - 2 <= w.middle <= x.x1 + 2
                    and any(c.isalpha() for c in x.text)), None)
        if hit is None:
            continue
        for run in _groups(_alpha(candidates)):
            if any(x is hit for x in run):
                entry = _match(pdf.text_of(run), entries, None, where)
                if entry is not None:
                    return entry, pdf.text_of(run)
    return None, ""


def _classification(lines, entries, report, where):
    """[(rank, entry)] from the bracket's classification column or podium."""
    out, seen = [], set()
    for index, line in enumerate(lines):
        for spot, w in enumerate(line):
            after = line[spot + 1:]
            ordinal = _ORDINAL.match(w.text)
            beside = " ".join(x.text for x in after
                              if x.x0 - w.x1 <= _PLACE_REACH)
            if re.fullmatch(r"[1-9]", w.text) and _PLACE_WORDS.search(beside):
                entry, printed = _named_left_of(lines, index, w, entries, where)
            elif ordinal and not any(re.fullmatch(r"(?i)p|poule", x.text)
                                     for x in after[:1]):
                entry, printed = _named_under(lines, index, w, entries, where)
            else:
                continue
            rank = ordinal.group(1) if ordinal else w.text
            if rank in seen:
                # "3  3ème Place" prints the rank twice, once as a digit and
                # once as an ordinal. The second spelling is not a second
                # placing, and its failure to find a name is not a problem.
                continue
            if entry is None:
                report.problem(f"{where}: rank {rank} in the classification "
                               f"names nobody the poule table knows; skipped")
                continue
            seen.add(rank)
            out.append((rank, entry))
    return out


def _final_from_bracket(lines, entries, report, where):
    """(winner, loser) for a two-competitor final drawn as a bracket.

    A category with two entrants has no poule: the sheet draws the two tireurs
    on the left and prints the winner again in the box they advance to. The name
    that appears twice is therefore the winner - and because that reading comes
    from the shape of the bracket and not from anything the sheet says in words,
    it is reported on every read.
    """
    counts = {}
    for line in lines:
        for run in _groups(_alpha(line)):
            entry = _match(pdf.text_of(run), entries, None, where) \
                if len(run) >= 2 else None
            if entry:
                counts[entry["name"]] = counts.get(entry["name"], 0) + 1
    twice = [n for n, c in counts.items() if c > 1]
    if len(twice) != 1 or len(counts) != 2:
        return None, None
    winner = twice[0]
    loser = next(n for n in counts if n != winner)
    report.problem(f"{where}: no verdict is printed; the final is read from the "
                   f"bracket, where {winner!r} is the name repeated in the "
                   f"advancing box")
    return winner, loser


def _bouts_begin(block):
    """Index of the line where the entry table stops and the bouts start."""
    marks = []
    for i, line in enumerate(block):
        flat = norm.fold(pdf.text_of(line))
        if "tours de poules" in flat:
            marks.append(i)
        elif "tireur" in flat and ("rouge" in flat or "bleu" in flat):
            marks.append(i)
    return min(marks) if marks else None


def _read_block(block, slug, meta, report, notes):
    """[Bout|Placing] for one category block of a livret."""
    age, country = meta.get("age_class", ""), meta.get("country", "")
    code = " ".join(w.text for w in block[0][1:])
    gender = ""
    for line in block[:6]:
        flat = norm.fold(pdf.text_of(line))
        if re.search(r"feminin", flat):
            gender = "Women"
        elif re.search(r"masculin", flat):
            gender = "Men"
        if gender:
            break
    found = _category_of(code, gender, report, notes)
    if not found:
        report.problem(f"category code {code!r} is not a weight class; the "
                       f"block under it is skipped")
        return []
    kg, bound, gender = found
    if not gender:
        report.problem(f"{code!r}: the sheet names no gender for this category, "
                       f"so the block is skipped rather than guessed at")
        return []
    klass = {"category": _label(gender, kg, bound, age), "gender": gender,
             "age_class": age, "weight_kg": kg, "weight_bound": bound}
    where = klass["category"]

    head_at = next((i for i, l in enumerate(block)
                    if any(norm.fold(w.text) == "nom" for w in l)), None)
    if head_at is None:
        report.problem(f"{where}: no table of entrants; the block is skipped")
        return []
    bouts_at = _bouts_begin(block)
    band = [l for l in block if abs(l[0].top - block[head_at][0].top) <= 12]
    columns = _numeric_columns(band, {"1t", "2t", "3t", "4t", "total",
                                      "classt", "avertisst"})
    entries, club_x = _entries(block[head_at + 1:bouts_at], report, where)
    if not entries:
        report.problem(f"{where}: no competitors read; the block is skipped")
        return []
    table_ends = next(i for i, l in enumerate(block)
                      if l is entries[-1]["line"])
    by_name = {norm.fold(e["name"]): e for e in entries}

    rows, index = [], 0
    if bouts_at is None:
        # Two entrants and a straight final: no poule, only a bracket.
        # Below the entry table only: the table names both fighters once
        # each, which would make every name a name that appears twice.
        winner, loser = _final_from_bracket(block[table_ends + 1:], entries,
                                            report, where)
        if not winner:
            report.problem(f"{where}: a category with no poule and no readable "
                           f"bracket result; nothing is recorded")
            return []
        return [Bout(
            tournament=slug, bout_id=f"{slug}-{_slug_bit(where)}-01",
            phase="final", **klass,
            red=winner, red_club=by_name[norm.fold(winner)]["club"],
            blue=loser, blue_club=by_name[norm.fold(loser)]["club"],
            winner=winner, loser=loser,
            winner_corner="",     # TIREUR A and TIREUR B are slots, not corners
            status="decided", result_source="reported")]

    tail = block[bouts_at:]
    rouge_x, bleu_x = _warning_columns(block, report, where)
    tours = [l for l in tail if _TOUR.match(pdf.text_of(l[:1]))]
    bout_lines = [l for l in tail if any(_PAIRING.match(w.text) for w in l)]
    result_x = _result_column(bout_lines, club_x)
    if result_x is None and bout_lines:
        report.problem(f"{where}: the winner's column could not be told from "
                       f"the blue corner's; no bout is recorded as decided")

    for line in bout_lines:
        pairing = next(i for i, w in enumerate(line) if _PAIRING.match(w.text))
        rest = line[pairing + 1:]
        words = _alpha(rest)
        red_words, right = _split_at(words, club_x)
        blue_words, winner_words = _split_at(right, result_x)
        red = _match(pdf.text_of(red_words), entries, report, where)
        blue = _match(pdf.text_of(blue_words), entries, report, where)
        if red is None or blue is None or red is blue:
            report.problem(f"{where}: the two fighters of "
                           f"{pdf.text_of(line)!r} cannot both be placed in "
                           f"the poule table; the bout is skipped")
            continue
        winner = _match(pdf.text_of(winner_words), entries, report, where)
        if winner is not None and winner not in (red, blue):
            report.problem(f"{where}: {pdf.text_of(winner_words)!r} is named "
                           f"the winner of a bout they are not in; left open")
            winner = None

        warnings = {"red": "", "blue": ""}
        for w in rest:
            if not _is_number(w.text):
                continue
            near = [(abs(w.middle - x), side)
                    for x, side in ((rouge_x, "red"), (bleu_x, "blue"))
                    if x is not None and abs(w.middle - x) <= COLUMN_SLACK]
            if near:
                warnings[min(near)[1]] = w.text

        tour = _tour_of(line, tours)
        red_points = _entry_points(red, columns).get(tour, "")
        blue_points = _entry_points(blue, columns).get(tour, "")
        if winner is not None and red_points and blue_points:
            high = (red if float(red_points) > float(blue_points)
                    else blue if float(blue_points) > float(red_points) else None)
            if high is not winner:
                report.problem(
                    f"{where}: the {tour or '?'}T scores of {red['name']} and "
                    f"{blue['name']} do not agree with the printed winner, so "
                    f"that bout keeps no points")
                red_points = blue_points = ""
        elif winner is None:
            red_points = blue_points = ""

        if red["poule"] != blue["poule"]:
            report.problem(f"{where}: {red['name']} and {blue['name']} are in "
                           f"different poules yet meet; the poule is left empty")
            poule = ""
        else:
            poule = red["poule"]

        index += 1
        rows.append(Bout(
            tournament=slug, bout_id=f"{slug}-{_slug_bit(where)}-{index:02d}",
            phase="poule", poule=poule, **klass,
            red=red["name"], red_club=red["club"],
            blue=blue["name"], blue_club=blue["club"],
            red_points=red_points, blue_points=blue_points,
            red_warnings=warnings["red"], blue_warnings=warnings["blue"],
            winner_corner="" if winner is None
            else ("red" if winner is red else "blue"),
            winner="" if winner is None else winner["name"],
            loser="" if winner is None
            else (blue["name"] if winner is red else red["name"]),
            status="decided" if winner is not None else "unresolved",
            result_source="reported" if winner is not None else ""))

    last = tail.index(bout_lines[-1]) if bout_lines else 0
    for rank, entry in _classification(tail[last + 1:], entries, report, where):
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{_slug_bit(where)}-p{rank}",
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=entry["name"], club=entry["club"], country=country,
            result_source="reported", **klass))

    _check_warnings(entries, columns, rows, where, report)
    return rows


def _check_warnings(entries, columns, rows, where, report):
    """Do the warnings counted bout by bout add up to the table's total?

    The poule table prints each fighter's total warnings and the bout rows print
    them one bout at a time. They are the same number twice, so a disagreement
    means one of them was read out of the wrong column - which is the failure
    this adapter is least able to see on its own.
    """
    centre = columns.get("avertisst")
    if centre is None:
        return
    counted = {}
    for row in rows:
        if not isinstance(row, Bout):
            continue
        for who, count in ((row.red, row.red_warnings),
                           (row.blue, row.blue_warnings)):
            if count:
                counted[who] = counted.get(who, 0) + int(count)
    for entry in entries:
        printed = next((w.text for w in entry["line"] if _is_number(w.text)
                        and abs(w.middle - centre) <= COLUMN_SLACK), None)
        if printed is None or int(printed) == counted.get(entry["name"], 0):
            continue
        report.problem(f"{where}: {entry['name']} is printed with {printed} "
                       f"warning(s) in the poule table but "
                       f"{counted.get(entry['name'], 0)} across the bout rows")


def _read_livret(path, slug, meta, report):
    """Bouts and placings from an FFSU livret."""
    words = pdf.words(path)
    report.read = len({w.page for w in words})
    blocks = _blocks(pdf.rows(words))
    rows, notes = [], set()
    for block in blocks:
        rows.extend(_read_block(block, slug, meta or {}, report, notes))
    if notes:
        report.notes["bare_codes"] = sorted(notes)
        report.problem(
            "category code(s) " + ", ".join(sorted(notes)) + " carry no sign "
            "and are read as upper bounds, because the same sheet writes "
            "'Plus70' and 'Plus82' when it means a class with no upper limit")
    return rows


# ------------------------------------------------------------------ read ----

def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) from one university results PDF.

    `ranks="podium"` restricts a classement to the top three, for a manifest
    that needs to stay inside the podium-only shape `schema.check_placing`
    still enforces. The default is every rank the sheet prints, which is the
    reason these documents are worth reading at all.
    """
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)
    try:
        path = sources.fetch_archived(str(source)) if options.get("archived") \
            else sources.fetch(source, refresh=options.get("refresh", False))
    except Exception as e:
        report.problem(f"the document could not be fetched: {e}")
        return tournament, [], report

    text = _pdftotext(path, report)
    rows = []
    if _IS_CLASSEMENT.search(text) and _RANKED.search(text):
        rows = _read_classement(text, slug, meta, report,
                                ranks=options.get("ranks", "all"))
        report.read = len(text.splitlines())
    elif re.search(r"(?i)tours de poules|tireur\s+rouge|^\s*CAT\b", text, re.M):
        try:
            rows = _read_livret(path, slug, meta, report)
        except pdf.PdfUnavailable as e:
            report.problem(str(e))
        except Exception as e:                            # pragma: no cover
            report.problem(f"the livret could not be read: {e!r}")
    else:
        report.problem("this is neither a degree-ranked classement nor an FFSU "
                       "livret; nothing was read")

    if rows and not meta.get("age_class"):
        report.problem("the document states no age class, so every category "
                       "label is gender and weight only - these labels must "
                       "not be matched against another competition's")
    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    if not rows:
        report.problem("no rows were read from this document")
    return tournament, rows, report
