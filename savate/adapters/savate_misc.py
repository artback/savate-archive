"""The one-off sheets: four small layouts that no other adapter recognises.

This is the leftover pile, and it is deliberately one module rather than four.
Each of these layouts is a single federation's habit, published two or three
times and then abandoned - a Serbian federation's post-event report, a Croatian
club's finals list, a French sheet that prints its class code in a different
place than the other French sheets. None of them is worth a file of its own,
and none of them may be forced through another adapter's reader: the shapes
have nothing in common beyond being short. So the module sniffs which of the
four it is holding and hands the document to the reader written for it. A
document that matches none of them yields no rows and says so, which is the
only honest answer for a pile whose defining property is that it is a pile.

The four, and what each one actually states:

1. FFSAVATE INLINE FINALS - the same French finals sheet `ffsavate_finals`
   reads, except the class code sits at the FRONT OF EACH LINE instead of on a
   line of its own:

       F48       ALLIN       Juliette     ROYAL BOXING CLUB (13)     Majorité
       F48       LE COUEDIC Léna          GANT D’HERMINE VANNETAIS (56)

   Once the code is lifted off the front, the rest of the line is byte-for-byte
   the sibling adapter's line, down to the club-in-brackets and the single-space
   rows its docstring describes ("EL MIR  Abderrahmane AVENIR SPORTIF D'ORLY").
   So it is read with that adapter's own reader rather than a second copy of the
   capitals heuristic, which would drift out of agreement with it in a year.
   Corners are not assigned, for its reason: the sheet names the winner and has
   never said who stood where.

2. SERBIAN FEDERATION REPORT - a post-event report from Savate Savez Srbije.
   A club medal table, then per-class podiums under an age-and-gender heading:

       SENIORI
       -65
       1. Luka Staletović, Kangal
       2. Mateja Fekete, Arena

   The headings are Serbian and they carry the two facts a category label needs:
   JUNIORKE/SENIORKE are the women's classes (the -KE ending), JUNIORI/SENIORI
   the men's, and ML./ST. distinguish younger from older juniors - which is a
   real distinction in these events, since both are contested on the same day
   in the same document.

   Two things this reader will not do. It does not rank an entrant the report
   left unranked: whole classes are printed as bare dashes ("- Luka Ninković,
   Vojvodina"), and the federation plainly means "took part", not "came first".
   Those are counted in the report and dropped. And it does not split a name
   from a club where the document ran them together with no separator; where
   the tail after a bare hyphen matches a club the SAME DOCUMENT spells out
   elsewhere, the split is made on that evidence, and otherwise the line is
   left whole and flagged. A club is never guessed from the shape of a word.

3. CROATIAN FINALS LIST - winner and runner-up as a numbered pair, with the
   verdict set out to the right:

       1. Ana Marija Suhina Titan Gym               3
       2. Kristina Sokolid Omega Varaždin           0

   Plain text destroys this one: the name, the club and the verdict are all
   separated by single spaces once the layout is flattened, so it is read from
   the word geometry. The verdict sits at least 20pt clear of the club, and the
   club at least 4pt clear of the name, in every row of the document - measured,
   not assumed - and the one row with no gap at all is recovered by its club's
   abbreviation ("S.K.") rather than by guessing where a name ends.

   "3 / 0" and "2 / 1" here are JUDGES, not points. Three officials score the
   bout and the sheet prints how they split. Savate's own scoring vocabulary is
   3/1/-1/0 per round and means something entirely different, so writing these
   into red_points/blue_points would file a judges' count as a scoreline. They
   go in decision_detail, verbatim, next to a decision of "points" - the same
   place the French sheets' "Unanimité" goes, because it is the same fact.

   This layout yields BOUTS AND NO PLACINGS, alone among the four. It prints
   six finals under one heading of "JUNIORI" and never says which class any of
   them was for, so six gold medals would all land in one category - a claim
   the document does not make. The bouts carry everything it does say.

4. CROATIAN BOUT PAIRS - a tournament's rounds as one line per bout:

       Polufinala:
       1. Noa Plantak - Gabrijel Rubil   2:1

   The number at the front is the bout's place in the running order, not a
   round. The heading above it is the round, and it is mapped by hand rather
   than through schema.phase_of, which reads "Polufinala" as a final: the word
   "final" is a literal substring of the Croatian for "semi-final", and an
   alias test that scans for substrings cannot see the difference.

Across all four the printed order of two names is printed order and nothing
else. red/blue in this archive mean CORNER, these documents never state one,
and so winner_corner is left empty on every bout this module produces.

Not in here, and not a failure of this module: the Vojvodina association's
registers of individual placings (drzavni_r_ind.pdf, medj_r_individualni.pdf).
They are a Cyrillic column table with one row per placing, and each row belongs
to a DIFFERENT competition - roughly ten championships per file, spread over
three years, listing only the association's own members. There is no tournament
in them to be the tournament of, and filing forty placings from ten events under
one slug would assert a competition that never took place. They need a register
schema, not an adapter; this one recognises that header and declines them.
"""

import re
import subprocess

from savate import normalize as norm
from savate.schema import MEDALS, Bout, Placing, Report, Tournament

NAME = "savate_misc"
DESCRIPTION = "one-off sheets: FFSavate inline finals, Serbian reports, Croatian finals and bout pairs"

# ---------------------------------------------------------------- layout 1

# A French finals line carrying its own class code: "F48   ALLIN  Juliette ..."
_INLINE = re.compile(r"^\s*([FM])\s*\+?\s*(\d{2,3})\s{2,}(\S.*?)\s*$")

# ---------------------------------------------------------------- layout 2

# The Serbian headings, each of which fixes an age class and a gender. The -KE
# ending is the feminine plural; ML. (mlađi) and ST. (stariji) mark the younger
# and older junior classes, which are separate competitions in one report.
_SERBIAN_SECTIONS = [
    (re.compile(r"^(?:mladi\s*[-–]?\s*)?ml\.?\s*juniorke$", re.I),
     "Younger Junior", "Junior", "Women"),
    (re.compile(r"^(?:mladi\s*[-–]?\s*)?ml\.?\s*juniori$", re.I),
     "Younger Junior", "Junior", "Men"),
    (re.compile(r"^st\.?\s*juniorke$", re.I), "Older Junior", "Junior", "Women"),
    (re.compile(r"^st\.?\s*juniori$", re.I), "Older Junior", "Junior", "Men"),
    (re.compile(r"^juniorke$", re.I), "Junior", "Junior", "Women"),
    (re.compile(r"^juniori$", re.I), "Junior", "Junior", "Men"),
    (re.compile(r"^seniorke$", re.I), "Senior", "Senior", "Women"),
    (re.compile(r"^seniori$", re.I), "Senior", "Senior", "Men"),
]

# A weight class on a line of its own: "-48", "- 56", "+85".
_WEIGHT_LINE = re.compile(r"^\s*([-+−])\s*(\d{2,3})\s*$")

# "1. Name, Club" / "3.Name- Club". The rank may hug the stop or the name.
_RANK_LINE = re.compile(r"^\s*(\d{1,2})\s*\.\s*(\S.*)$")

# The report's own title line, which is where the event's facts are stated.
_SERBIAN_HEAD = re.compile(
    r"izve[sš]taj\s+za\s+(?P<what>.+?)\s+(?P<date>\d{2}\.\d{2}\.\d{4})\.?\s*"
    r"(?P<city>[^\d]*)$", re.I)

# Name and club, where the report separated them. A comma, or a hyphen with a
# space on one side; a hyphen with no space at all is a double-barrelled name
# until the document proves otherwise.
_NAME_CLUB = re.compile(r"\s*,\s*|\s+[-–]\s*|\s*[-–]\s+")

# ---------------------------------------------------------------- layout 3/4

# Croatian/Serbian verdict wording. Each is (canonical decision, pattern).
_VERDICTS = [
    ("disqualification", re.compile(r"diskvalif", re.I)),
    ("abandon", re.compile(r"\bk\.?\s?o\.?", re.I)),
    ("abandon", re.compile(r"predaj|ozljed|prekid", re.I)),
    ("forfait", re.compile(r"predala|nije\s+nastup", re.I)),
]

# A club abbreviation, used only to rescue a row the geometry cannot split.
_CLUB_ABBREV = re.compile(r"^(s\.?k\.?|b\.?k\.?|k\.?b\.?s\.?|s\.?u\.?|f\.?c\.?|"
                          r"gym|club|klub)$", re.I)

# "1. Noa Plantak - Gabrijel Rubil   2:1"
# The running-order number is optional: the exhibition bout at the foot of the
# Vukovar sheet is printed without one, and a bout that is not counted must
# still be SEEN, so that it can be reported rather than silently dropped.
_PAIR_LINE = re.compile(
    r"^\s*(?:\d{1,3}\s*\.\s*)?(?P<left>\S.*?)\s+[-–—]\s+(?P<right>\S.*?)\s+"
    r"(?P<a>\d{1,2})\s*:\s*(?P<b>\d{1,2})\s*$")

# The round headings, mapped by hand. See the module docstring: schema.phase_of
# reads "Polufinala" as a final, because "final" is a substring of it.
_CRO_PHASES = [
    (re.compile(r"^(polufinal|1/2|polufinala)", re.I), "semi"),
    (re.compile(r"^(četvrtfinal|cetvrtfinal|1/4)", re.I), "quarter"),
    (re.compile(r"^(osmina|1/8)", re.I), "r16"),
    (re.compile(r"^(finale|finala|finals?)\b", re.I), "final"),
    (re.compile(r"^(za\s+tre|bronc)", re.I), "bronze"),
]
# An exhibition bout. Not a result of the competition, and not filed as one.
_EXHIBITION = re.compile(r"^(revija|revijaln)", re.I)

# The two Vojvodina registers, recognised so they can be refused by name.
_REGISTER_HEAD = re.compile(r"пласман|такмичењ|назив\s+такмичења", re.I)


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) from one of the one-off sheets."""
    from savate import pdf, sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)

    try:
        path = sources.fetch_archived(str(source)) if options.get("archived") \
            else sources.fetch(source, refresh=options.get("refresh", False))
    except Exception as e:                       # a source that will not come
        report.problem(f"could not fetch the document: {e}")
        return tournament, [], report

    text = _text(path, report)
    lines = text.splitlines()
    report.read = len(lines)
    if not [l for l in lines if l.strip()]:
        report.problem("the document yielded no text at all")
        return tournament, [], report

    layout = _layout(lines)
    report.notes["layout"] = layout or "unrecognised"
    if layout is None:
        report.problem("none of this module's four layouts fits this document")
        return tournament, [], report
    if layout == "register":
        report.problem(
            "this is a register of individual placings, one row per placing "
            "across many different competitions - there is no single "
            "tournament in it, so nothing is filed under this slug")
        return tournament, [], report

    if layout == "ffsavate_inline":
        rows = _ffsavate_inline(lines, slug, meta, report, tournament)
    elif layout == "serbian_report":
        rows = _serbian_report(lines, slug, meta, report, tournament)
    elif layout == "croatian_pairs":
        rows = _croatian_pairs(lines, slug, meta, report, tournament)
    else:
        geometry = _geometry(path, pdf, report)
        if geometry is None:
            return tournament, [], report
        rows = _croatian_finals(geometry, pdf, slug, report, tournament)

    if not rows:
        report.problem(f"the {layout} reader found nothing to read")
    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    return tournament, rows, report


def _tournament(slug, meta, source):
    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""), format=meta.get("format", ""),
        age_class=meta.get("age_class", ""), year=meta.get("year", ""),
        start_date=meta.get("start_date", ""), end_date=meta.get("end_date", ""),
        city=meta.get("city", ""), country=meta.get("country", ""),
        source=str(source), adapter=NAME,
    )


def _text(path, report):
    """The document's text with its columns intact, or "" with a complaint."""
    try:
        done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=60)
        return done.stdout or ""
    except Exception as e:
        report.problem(f"pdftotext could not read the document: {e}")
        return ""


def _geometry(path, pdf, report):
    """Word rows, for the layout that cannot be read from flattened text."""
    try:
        return pdf.rows(pdf.words(path))
    except Exception as e:
        report.problem(f"this layout needs word positions, and poppler could "
                       f"not supply them: {e}")
        return None


def _layout(lines):
    """Which of the four shapes this document has, or None / "register"."""
    body = [l for l in lines if l.strip()]
    joined = "\n".join(body)

    codes = [(m.group(1).upper(), m.group(2))
             for m in (_INLINE.match(l) for l in body) if m]
    inline = len(codes)
    # The finals sheet prints each class TWICE in a row, once for the winner
    # and once for the runner-up. A poule grid's column header - "F 56
    # POINTS  AVT" - has the same shape as one of those lines but never
    # repeats, which is what separates the two documents.
    paired = sum(1 for a, b in zip(codes, codes[1:]) if a == b)
    pairs = sum(1 for l in body if _PAIR_LINE.match(l))
    sections = sum(1 for l in body
                   for pattern, *_ in _SERBIAN_SECTIONS
                   if pattern.match(l.strip().rstrip(":")))
    weights = sum(1 for l in body if _WEIGHT_LINE.match(l))
    ranked = sum(1 for l in body if _RANK_LINE.match(l))

    if sum(1 for l in body[:2] if _REGISTER_HEAD.search(l)) and inline == 0:
        return "register"
    if inline >= 4 and paired >= 2:
        return "ffsavate_inline"
    if sections >= 2 and weights >= 3:
        return "serbian_report"
    if pairs >= 4:
        return "croatian_pairs"
    # The Croatian finals list is the weakest signal - numbered lines and
    # nothing else - so it is only claimed once the other three are ruled out,
    # and only on the alternation that makes it a list of PAIRS. A podium that
    # counts 1, 2, 3 down a page is not this, and must not be read as it.
    if ranked >= 6 and _pairings(body) >= 3 \
            and re.search(r"finala|finale|rezultati", joined, re.I):
        return "croatian_finals"
    return None


def _pairings(body):
    """How many times a "1." line is followed by a "2." line."""
    ranks = [m.group(1) for m in
             (re.match(r"^\s*([12])\s*\.", l) for l in body) if m]
    return sum(1 for a, b in zip(ranks, ranks[1:]) if a == "1" and b == "2")


# ------------------------------------------------------------------ layout 1


def _crowded(body, report):
    """(name, club) for a line whose columns collapsed into single spaces.

    One row in the 2024 Open de France is set wide enough that poppler has no
    gap left to print - "BRUGIROUX Christopher PUNCH SAVATE GANNAT (03)" - and
    the sibling adapter's column split, which needs two spaces, declines it and
    loses the final. The split is made on the same convention that adapter
    documents and relies on elsewhere: the club is set in capitals throughout
    and the given name is not, so the name ends at its first word that is not.
    It is applied only after the column split has failed, never in front of it.
    """
    body = _CLUB_BRACKET.sub("", " ".join(body.split())).strip()
    words = body.split()
    if len(words) < 3:
        return None, ""
    at = next((i for i, w in enumerate(words)
               if i and not w.isupper() and w[:1].isupper()), None)
    if at is None or at + 1 >= len(words):
        return None, ""
    club = " ".join(words[at + 1:])
    if not club.isupper():
        report.problem(f"{body!r}: the columns collapsed and what follows the "
                       f"given name is not in capitals, so the club cannot be "
                       f"told from the name - skipped")
        return None, ""
    return " ".join(words[:at + 1]), club


# The département in brackets that closes a French club name.
_CLUB_BRACKET = re.compile(r"\s*\(\d{2,3}\)\s*$")


def _ffsavate_inline(lines, slug, meta, report, tournament):
    """Finals from a French sheet that prints the class code on every line."""
    from savate.adapters import ffsavate_finals as ffs

    # "12/05/2024 ....................... Mérignac (33)" - the sheet's one
    # line of event detail, printed above each section's finals.
    for line in lines[:40]:
        found = re.match(r"^\s*(\d{2}/\d{2}/\d{4})[\s.]*(.*?)\s*(?:\(\d{2,3}\))?\s*$",
                         line)
        if not found:
            continue
        date = norm.date(found.group(1))
        if date:
            tournament.start_date = tournament.start_date or date
            tournament.end_date = tournament.end_date or date
        town = found.group(2).strip()
        if town and len(town) < 30:
            tournament.city = tournament.city or town
        break

    rows, block, code = [], [], None

    def flush():
        if not block or code is None:
            return
        label, gender, kilos, bound = ffs._category(
            code[0], code[1], report, meta.get("age_class", ""))
        people = []
        for body in block:
            decision, printed = ffs._decision(body)
            name, club = ffs._competitor(body)
            if not name:
                name, club = _crowded(ffs._strip_decision(body), report)
            if name:
                people.append((name, club, decision, printed))
        if len(people) != 2:
            report.problem(f"{label}: {len(people)} competitor(s) on the sheet, "
                           f"a final needs two")
            return
        at = next((i for i, p in enumerate(people) if p[2]), 0)
        winner, loser = people[at], people[1 - at]
        decision, printed = winner[2], winner[3]
        if not decision:
            report.problem(f"{label}: no decision printed for {winner[0]}")
        index = sum(1 for r in rows if isinstance(r, Bout)) + 1
        rows.append(Bout(
            tournament=slug, bout_id=f"{slug}-{index:02d}-final",
            category=label, gender=gender,
            age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound, phase="final",
            red=winner[0], red_club=winner[1],
            blue=loser[0], blue_club=loser[1],
            winner=winner[0], loser=loser[0], winner_corner="",
            decision=decision, decision_detail=printed,
            status="decided", result_source="reported",
        ))
        for rank, who in (("1", winner), ("2", loser)):
            rows.append(Placing(
                tournament=slug, placing_id=f"{slug}-{index:02d}-{rank}",
                category=label, gender=gender,
                age_class=meta.get("age_class", ""),
                weight_kg=kilos, weight_bound=bound,
                rank=rank, medal=MEDALS[rank], fighter=who[0], club=who[1],
                country=meta.get("country", ""), result_source="reported",
            ))

    for line in lines:
        found = _INLINE.match(line)
        if not found:
            continue
        here = (found.group(1).upper(), int(found.group(2)))
        if here != code:
            flush()
            code, block = here, []
        block.append(found.group(3))
    flush()

    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"]) +
            " read as the open class: the code exceeds every real savate "
            "weight, and no document states what it stands for")
    if not meta.get("age_class"):
        report.problem("the sheet states no age class, so the category labels "
                       "carry gender and weight only")
    return rows


# ------------------------------------------------------------------ layout 2


def _serbian_report(lines, slug, meta, report, tournament):
    """Per-class podiums from a Savate Savez Srbije post-event report."""
    _serbian_header(lines, report, tournament, meta)

    section = None      # (label prefix, age class, gender)
    klass = None        # (bound, kilos)
    entries = []        # (section, klass, rank, text)
    unranked = 0

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        head = line.rstrip(":").strip()
        found = next(((a, b, c) for pattern, a, b, c in _SERBIAN_SECTIONS
                      if pattern.match(head)), None)
        if found:
            section, klass = found, None
            continue
        weight = _WEIGHT_LINE.match(line)
        if weight:
            if section is None:
                # A weight-shaped line before any heading is the club medal
                # table's arithmetic, not a class.
                continue
            klass = ("over" if weight.group(1) == "+" else "under",
                     weight.group(2))
            continue
        if section is None or klass is None:
            continue
        ranked = _RANK_LINE.match(line)
        if ranked:
            entries.append((section, klass, ranked.group(1), ranked.group(2)))
            continue
        # A competitor the report listed without a placing - usually behind a
        # bare dash. Present, but not placed, and not made to be.
        if re.search(r"[A-Za-zČĆŽŠĐčćžšđ]", line):
            unranked += 1

    known = _known_clubs(entries)
    rows, seen = [], set()
    for section, klass, rank, text in entries:
        label = f"{section[0]} {section[2]} " + (
            f"+{klass[1]} kg" if klass[0] == "over" else f"-{klass[1]} kg")
        if rank not in MEDALS:
            report.problem(f"{label}: place {rank} is past the podium "
                           f"({text}) - kept out, the schema holds 1 to 3")
            continue
        fighter, club = _split_name_club(text, known, report, label)
        if not fighter:
            continue
        key = (label, rank, norm.fold(fighter))
        if key in seen:
            continue
        seen.add(key)
        rows.append(Placing(
            tournament=slug, placing_id=f"{slug}-{len(rows) + 1:03d}",
            category=label, gender=section[2], age_class=section[1],
            weight_kg=klass[1], weight_bound=klass[0],
            rank=rank, medal=MEDALS[rank], fighter=fighter, club=club,
            country=tournament.country or meta.get("country", ""),
            result_source="reported",
        ))

    if unranked:
        report.problem(f"{unranked} competitor(s) are listed without a placing "
                       f"- the report names them but does not rank them, so "
                       f"they are counted here and not filed as placings")
    _serbian_anomalies(rows, report)
    return rows


def _serbian_header(lines, report, tournament, meta):
    """Fill the tournament from the report's own title line, where it has one.

    The title line is only evidence if the report agrees with itself. These
    reports are written from the previous one's file, and one of them carries a
    title line for a different event in a different town in a different year
    from the date over the president's signature at the foot. A document that
    contradicts itself does not state a fact; it states a disagreement. So on a
    mismatch nothing is taken from the line, and the line and the signature are
    both quoted in the report for a human to settle.
    """
    signed = ""
    for line in reversed(lines[-12:]):
        found = re.search(r"(\d{2}\.\d{2}\.\d{4})", line)
        if found:
            signed = norm.date(found.group(1))
            break

    # The scope is stated in the body ("Prijavu na prvenstvo Srbije poslalo je
    # 14 klubova"), not only in the title, so it survives a suspect title line.
    if re.search(r"prvenstvo\s+srbije", "\n".join(lines), re.I):
        tournament.country = tournament.country or "Serbia"
        tournament.level = tournament.level or "national"
        tournament.format = tournament.format or "championship"

    for line in lines[:20]:
        found = _SERBIAN_HEAD.search(line.strip())
        if not found:
            continue
        title = " ".join(line.split())
        report.notes["title_line"] = title
        report.notes["signature_date"] = signed
        date = norm.date(found.group("date"))
        if signed and date and signed[:4] != date[:4]:
            report.problem(
                f"the report contradicts itself: its title line reads {title!r} "
                f"while it is signed {signed}. Nothing is taken from the title "
                f"line - not the date, the town or the discipline - because a "
                f"document that disagrees with itself states neither reading")
            return
        if date:
            tournament.start_date = tournament.end_date = date
        city = " ".join(found.group("city").split()).title()
        if city:
            tournament.city = city
        what = found.group("what")
        if re.search(r"combat", what, re.I):
            tournament.discipline = "combat"
        elif re.search(r"assaut|aso\s+savate", what, re.I):
            tournament.discipline = "assaut"
        return
    report.problem("the report has no title line, so its date, city and "
                   "discipline are taken from the manifest alone")


def _known_clubs(entries):
    """Club spellings this document itself used, folded for matching.

    Only clubs the report separated cleanly with a comma or a spaced hyphen
    count. They are the evidence used to split the rows it ran together, and
    evidence from anywhere else would be a guess about this document.
    """
    clubs = set()
    for _section, _klass, _rank, text in entries:
        parts = _NAME_CLUB.split(text.strip(), maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            clubs.add(norm.fold(parts[1]))
    return clubs


def _split_name_club(text, known, report, label):
    """(fighter, club) from "Name, Club", or (fighter, "") with a complaint."""
    text = " ".join(text.split()).strip().strip("-–").strip()
    if not text:
        return "", ""
    parts = _NAME_CLUB.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    # No separator the report uses. A bare hyphen may still be one, but only if
    # what follows it is a club this same document spelled out somewhere else.
    for at in (m.start() for m in re.finditer(r"[-–]", text)):
        tail = text[at + 1:].strip()
        if tail and norm.fold(tail) in known:
            return text[:at].strip(), tail
    report.problem(f"{label}: {text!r} has no separator between the name and "
                   f"the club, and no club in this document matches its tail - "
                   f"kept whole rather than split on a guess")
    return text, ""


def _serbian_anomalies(rows, report):
    """Two golds in one class is the report's claim, not a parsing error."""
    import collections
    counts = collections.Counter((p.category, p.rank) for p in rows)
    for (category, rank), n in sorted(counts.items()):
        if rank in ("1", "2") and n > 1:
            report.problem(f"{category}: the report lists {n} competitors in "
                           f"place {rank} - kept as printed")


# ------------------------------------------------------------------ layout 3


def _croatian_finals(geometry, pdf, slug, report, tournament):
    """Winner/runner-up pairs from a Croatian finals list, read by geometry."""
    _croatian_header([pdf.text_of(l) for l in geometry], report, tournament)

    age = ""
    pending = None
    rows = []
    for line in geometry:
        text = pdf.text_of(line).strip()
        if not text:
            continue
        head = re.match(r"^(juniori|seniori|kadeti|veterani)\b", text, re.I)
        if head and len(text) < 20:
            age = {"juniori": "Junior", "seniori": "Senior",
                   "kadeti": "Cadet", "veterani": "Veteran"}[head.group(1).lower()]
            pending = None
            continue
        rank, rest = _leading_rank(line)
        if rank is None or not rest:
            continue
        name, club, verdict = _finals_row(rest, report)
        if not name:
            continue
        if rank == 1:
            if pending:
                report.problem(f"{pending[0]}: a first place with no second "
                               f"under it - the pair is incomplete and dropped")
            pending = (name, club, verdict, age)
            continue
        if pending is None:
            report.problem(f"{name}: a second place with no first above it")
            continue
        rows.extend(_croatian_bout(pending, (name, club, verdict, age),
                                   slug, rows, report))
        pending = None
    if pending:
        report.problem(f"{pending[0]}: a first place with no second under it")

    report.problem("this sheet states no weight classes and no gender - the "
                   "age class on the section heading is all it gives, so the "
                   "category labels carry that and nothing more, and no "
                   "placings are filed: a medal needs a class to be a medal in")
    return rows


def _croatian_bout(first, second, slug, rows, report):
    """One final, plus its two placings, from the 1./2. pair of lines."""
    name, club, verdict, age = first
    other, other_club, other_verdict, _age = second
    printed = " ".join(v for v in (verdict, other_verdict) if v).strip()

    decision = next((d for d, pattern in _VERDICTS if pattern.search(printed)), "")
    detail = printed
    winner, loser = first, second
    if not decision:
        a, b = _judges(verdict), _judges(other_verdict)
        if a is not None and b is not None:
            if a == b:
                report.problem(f"{name} v {other}: the sheet prints {a}:{b}, "
                               f"which names no winner - left unresolved")
                return _unresolved(first, second, slug, rows, age)
            decision, detail = "points", f"{a}:{b}"
            if b > a:
                winner, loser = second, first
        elif printed:
            report.problem(f"{name} v {other}: verdict {printed!r} is not one "
                           f"this reader knows - the bout is left unresolved")
            return _unresolved(first, second, slug, rows, age)
        else:
            report.problem(f"{name} v {other}: no verdict printed")
            return _unresolved(first, second, slug, rows, age)

    if decision == "disqualification":
        # The sheet names who was disqualified. If it names the competitor
        # printed first - the one every other row shows as the winner - the
        # sheet contradicts its own ordering and nothing is claimed.
        named = [p for p in (first, second)
                 if _names_one(printed, p[0])]
        if len(named) == 1:
            loser = named[0]
            winner = second if loser is first else first
        elif named:
            report.problem(f"{name} v {other}: the disqualification names both "
                           f"competitors - left unresolved")
            return _unresolved(first, second, slug, rows, age)

    # No placings, deliberately. A placing claims "first in category C", and
    # this sheet never says which class a final was for - six finals sit under
    # one heading of "JUNIORI". Six gold medals in one category is a claim the
    # document does not make, and the bout rows already carry everything it
    # does say: who met whom in a final, and who won.
    index = sum(1 for r in rows if isinstance(r, Bout)) + 1
    return [Bout(
        tournament=slug, bout_id=f"{slug}-{index:02d}-final",
        category=age or "", age_class=age, phase="final",
        red=name, red_club=club, blue=other, blue_club=other_club,
        winner=winner[0], loser=loser[0], winner_corner="",
        decision=decision, decision_detail=detail,
        status="decided", result_source="reported",
    )]


def _unresolved(first, second, slug, rows, age):
    """The bout happened and both names are known; who won is not."""
    index = sum(1 for r in rows if isinstance(r, Bout)) + 1
    return [Bout(
        tournament=slug, bout_id=f"{slug}-{index:02d}-final",
        category=age or "", age_class=age, phase="final",
        red=first[0], red_club=first[1], blue=second[0], blue_club=second[1],
        status="unresolved", result_source="",
    )]


def _judges(text):
    """A bare judges' count, as an int, or None."""
    text = (text or "").strip()
    return int(text) if re.fullmatch(r"\d", text) else None


def _names_one(text, name):
    """Does a verdict line name this competitor? Matched on the surname."""
    words = [norm.fold(w) for w in name.split() if len(w) > 2]
    folded = norm.fold(text)
    return any(w in folded for w in words)


def _leading_rank(line):
    """(1 or 2, the rest of the words) for a "1." line, or (None, []).

    The stop may be glued to the name - "1.Luka" - so the rank is taken off the
    word rather than off the line.
    """
    if not line:
        return None, []
    head = line[0].text
    found = re.match(r"^([12])\.(.*)$", head)
    if not found:
        return None, []
    rest = list(line[1:])
    tail = found.group(2).strip()
    if tail:
        from savate.pdf import Word
        rest.insert(0, Word(text=tail, x0=line[0].x0, x1=line[0].x1,
                            top=line[0].top, bottom=line[0].bottom,
                            page=line[0].page))
    return int(found.group(1)), rest


# The two gaps this layout is built on, in points, both measured across every
# row of the documents seen: the verdict stands at least 20pt clear of the club,
# and the club at least 4pt clear of the name.
_VERDICT_GAP = 20.0
_CLUB_GAP = 4.0


def _finals_row(words, report):
    """(name, club, verdict) from the words after the rank."""
    at, width = _widest(words)
    verdict = ""
    if width >= _VERDICT_GAP:
        verdict = " ".join(w.text for w in words[at:])
        words = words[:at]
    if not words:
        return "", "", verdict
    at, width = _widest(words)
    if width >= _CLUB_GAP:
        name = " ".join(w.text for w in words[:at])
        club = " ".join(w.text for w in words[at:])
        return name, club, verdict
    # No column gap at all. A club abbreviation is the document's own marker
    # for where the club starts; without one the line is kept whole.
    for i, w in enumerate(words):
        if i and _CLUB_ABBREV.match(w.text):
            return (" ".join(x.text for x in words[:i]),
                    " ".join(x.text for x in words[i:]), verdict)
    text = " ".join(w.text for w in words)
    report.problem(f"{text!r}: no gap and no club abbreviation, so the name "
                   f"and the club are left joined rather than split by guess")
    return text, "", verdict


def _widest(words):
    """(index of the word after the widest gap, that gap's width)."""
    at, width = 0, 0.0
    for i in range(1, len(words)):
        gap = words[i].x0 - words[i - 1].x1
        if gap > width:
            at, width = i, gap
    return at, width


def _croatian_header(lines, report, tournament):
    """Date, city and discipline from the two title lines, where printed."""
    for line in lines[:6]:
        text = " ".join(line.split())
        if re.search(r"combat", text, re.I):
            tournament.discipline = tournament.discipline or "combat"
        elif re.search(r"\bassaut\b", text, re.I):
            tournament.discipline = tournament.discipline or "assaut"
        found = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
        if found:
            date = norm.date("{:0>2}.{:0>2}.{}".format(*found.groups()))
            if date:
                tournament.start_date = tournament.end_date = date
            city = text[:found.start()].strip(" ,.-")
            if city and len(city) < 30:
                tournament.city = tournament.city or city
    if not tournament.start_date:
        report.problem("no date is printed on this sheet")


# ------------------------------------------------------------------ layout 4


def _croatian_pairs(lines, slug, meta, report, tournament):
    """One line per bout: two names and the judges' split."""
    _croatian_header(lines, report, tournament)

    phase, exhibition = "", False
    rows, skipped = [], []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        head = line.rstrip(":").strip()
        if _EXHIBITION.match(head) and len(head) < 20:
            exhibition, phase = True, ""
            continue
        found = next((p for pattern, p in _CRO_PHASES if pattern.match(head)), None)
        if found and len(head) < 24:
            phase, exhibition = found, False
            continue
        pair = _PAIR_LINE.match(line)
        if not pair:
            continue
        left, right = pair.group("left").strip(), pair.group("right").strip()
        a, b = int(pair.group("a")), int(pair.group("b"))
        if exhibition:
            skipped.append(f"{left} v {right} {a}:{b}")
            continue
        if not phase:
            report.problem(f"{left} v {right}: no round heading above this "
                           f"bout, so its phase is left empty")
        if left == right:
            report.problem(f"{left!r} is printed on both sides of one bout - "
                           f"skipped")
            continue
        index = len(rows) + 1
        if a == b:
            report.problem(f"{left} v {right}: the sheet prints {a}:{b}, which "
                           f"names no winner - left unresolved")
            rows.append(Bout(
                tournament=slug, bout_id=f"{slug}-{index:03d}", phase=phase,
                red=left, blue=right, decision_detail=f"{a}:{b}",
                status="unresolved", result_source=""))
            continue
        winner, loser = (left, right) if a > b else (right, left)
        rows.append(Bout(
            tournament=slug, bout_id=f"{slug}-{index:03d}", phase=phase,
            red=left, blue=right,
            winner=winner, loser=loser, winner_corner="",
            decision="points", decision_detail=f"{a}:{b}",
            status="decided", result_source="reported"))

    if skipped:
        report.problem("exhibition bout(s) not filed as results: " +
                       "; ".join(skipped))
    report.problem("this sheet states no weight classes, no age classes and no "
                   "gender - the bouts carry the round and the two names only")
    return rows
