"""Ranked lists under a weight-class heading: the Balkan federations' reports.

The Croatian and Serbian federations, the Vojvodina region and the 2023 World
Combat Games all publish the same document in different words. A heading names
an age group, a heading names a weight class, and under it the competitors are
listed in finishing order:

    KADETKINJE:                       Kadetkinje -30 kg
    -42kg:                            1. mjesto Tonka Grabar (SK Omega Vž)
    1. Ivana Jakovljević-„Knez Lazar“ Obrenovac
    2. Arijana Otašević -„Pobednik 021“ N.Sad

    Men´s Assaut -60kg                  M-52kg
     1 LAURENT MEDHI LOUIS   FRA - FR  1 Vladimir Boberić  SK "Maks Feniks"

No bouts are published anywhere in this family - who beat whom is simply not in
these documents - so every row here is a `Placing`. Inventing the bouts that
produced a podium would be fabrication, and a podium is a real fact on its own.

WHAT THE LAYOUTS SHARE, and why one adapter can read them all: a running
context (age class, gender, sometimes discipline) set by headings, a weight
class that resets it, and rank-led lines under it. Only three things vary, and
each is read rather than assumed:

*Where the rank sits.* Almost always first - "1.", "1 ", "1. mjesto",
"1.mjesto". The 2012 French university sheet prints it last, as "1°", so a
trailing marker is accepted too.

*How the name is separated from the club.* Three separators appear and they are
tried in this order: a column gap (the two-column Vojvodina sheet and the World
Combat Games list), a bracket (every Croatian sheet), or the Serbian federation's
quoted club - `Nikola Matejić-„Grocka“ Beograd`. The Serbian split is taken at
the last dash BEFORE the first quote, not at the first dash, because several
rows lose their opening quote in extraction ("Nemanja Grbić-Ruma“ Ruma") and
splitting at the quote alone would hand back "Nemanja Grbić-Ruma" as a name.

*Whether a bracket holds a club or a country.* The Croatian sheets print
visiting Hungarians and Austrians as "(Mađarska)", "( Hungary)" in the same slot
they print clubs. Only names on a short, explicit list are read as countries;
anything else is a club, so an unrecognised federation shows up as a club to be
looked at rather than as a wrong country.

WHAT THIS ADAPTER REFUSES TO DO.

*It does not carry a weight class past a heading.* A section heading clears it.
The 2018 Zagreb open prints "JUNIORI" and then, through an error in the source,
no weight line at all; carrying the previous class would file four juniors under
the women's -70 kg that preceded them. They are reported and dropped instead.

*It does not rank what the document does not rank.* Competitors printed without
a number - the Croatian "BEZ BORBE" entries, the Vojvodina sheets' unplaced
names - are counted and reported, never given a place. Places below third are
dropped for the same reason `check_placing` rejects them: a podium row is what
this schema stores, and fifth is not a podium.

*It does not read another sport.* The World Combat Games file interleaves canne
de combat and wheelchair canne with the savate; those headings clear the current
class so their athletes cannot fall into the savate one above them.

TWO THINGS IT DOES INFER, and reports on every read.

*An unsigned weight is an upper limit.* "27kg:" between "-24kg:" and "30kg:" is
the federation dropping a hyphen, and savate weight classes are upper limits
except the open class, which is always written "+". The bound is recorded as
under and the count of unsigned headings is reported.

*A two-column page is read column by column, and a heading carries over the
break.* The Vojvodina sheet prints section headings only in the column they
begin in: page 2 puts MLAĐI JUNIORI over the left column and JUNIORI, SENIORI
over the right, which is only coherent if each column is read as a continuation
of the last. Page 1 then leaves the right column under KADETI, which the archive
corroborates - Vladimir Boberić and Mateja Fekete, printed there, are older
pioneers in 2019 and younger juniors in 2024. It is still a reading of a layout
rather than something the page states, so it is reported.
"""

import collections
import re

from savate import normalize as norm
from savate.schema import MEDALS, Placing, Report, Tournament

NAME = "savate_weight_list"
DESCRIPTION = "ranked weight-class lists (Balkan federation reports, WCG results)"

# Everything after one of these is a club medal table or a standings board, not
# results. Those rows also start with "1." and would otherwise be read as
# placings with a club's name in the fighter column.
_STOP = re.compile(r"r[ae]zultati\s+klubova|najuspje[sš]nij[ie]\s+klub|"
                   r"medal\s+standing|poredak\s+klubova|\br\.?\s?br\b|"
                   r"\bukupno\b|r[ée]sultats?\s*-?\s*savate\s*-?\s*[ée]quipes",
                   re.I)

# Different sports, published in the same file as the savate.
_OTHER_SPORT = re.compile(r"canne|b[aâ]ton|chausson", re.I)

# A line that is nothing but a discipline: the Croatian reports switch from
# assaut to combat mid-document without repeating the age headings.
_DISCIPLINE = re.compile(r"^(pre[\s-]?combat|combat|assaut)"
                         r"(\s+(finale?|final))?$", re.I)

# The round format the Serbian sheets append to a section heading -"3 x 1,5".
_ROUNDS = re.compile(r"\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*$")

# A weight class, in every form the family prints it: "-42kg:", "27kg:",
# "M-60/-65kg", "Seniori + 85", "moins de 60kg", "Juniori 80- 85 kg".
_WEIGHT = re.compile(
    r"^(?P<pre>[^\d]*?)"
    r"(?P<sign>[-+–—−])?\s*"
    r"(?<!\d)(?P<a>\d{2,3})(?!\d)"
    r"(?:\s*[-–—/]\s*[-+–—−]?\s*(?<!\d)(?P<b>\d{2,3})(?!\d))?"
    r"\s*(?P<unit>kgs?)?"
    r"\s*[:.]?\s*(?P<rest>.*)$", re.I)

# A place, printed in front of the competitor.
_RANK = re.compile(r"^(?P<rank>[1-9])(?!\d)\s*[.)°º]?\s*"
                   r"(?:mjesto|mesto|place|lugar)?\s*[.:]?\s*(?P<body>\S.*)$",
                   re.I)
# ... or behind them, which only the 2012 French university sheet does.
_RANK_LAST = re.compile(r"^(?P<body>.*?)\s*(?<!\d)(?P<rank>[1-9])\s*[°ºo]\s*$")

_PAREN = re.compile(r"^(?P<name>.*?)\s*[(（]\s*(?P<inside>[^()]*?)\s*[)）]+\s*$")
_QUOTE = "„“”\"«»"
# A club standings row ends in its medal columns; a competitor's never does.
_COUNTS = re.compile(r"(?:\b\d{1,3}\b[^\w]*){3}$")
# The World Combat Games print the country as "FRA - FRANCE".
_NOC = re.compile(r"^(?P<code>[A-Z]{3})\s*[-–]\s*(?P<name>[A-Za-z' .,-]{3,})$")

# Age and gender, as the four languages in this family write them. The value is
# (age class, gender); an empty gender means the word does not state one.
_VOCAB = {
    "pionir": ("Pioneer", "Men"), "pioniri": ("Pioneer", "Men"),
    "pionire": ("Pioneer", ""), "pionira": ("Pioneer", ""),
    "pionirka": ("Pioneer", "Women"), "pionirke": ("Pioneer", "Women"),
    "kadet": ("Cadet", "Men"), "kadeti": ("Cadet", "Men"),
    "kadete": ("Cadet", ""), "kadeta": ("Cadet", ""),
    "kadetkinja": ("Cadet", "Women"), "kadetkinje": ("Cadet", "Women"),
    "junior": ("Junior", "Men"), "juniori": ("Junior", "Men"),
    "juniore": ("Junior", ""), "juniora": ("Junior", ""), "juniors": ("Junior", ""),
    "juniorka": ("Junior", "Women"), "juniorke": ("Junior", "Women"),
    "senior": ("Senior", "Men"), "seniori": ("Senior", "Men"),
    "seniore": ("Senior", ""), "seniora": ("Senior", ""), "seniors": ("Senior", ""),
    "seniorka": ("Senior", "Women"), "seniorke": ("Senior", "Women"),
    "student": ("University", ""), "studenti": ("University", ""),
    "studente": ("University", ""), "univerzitetsko": ("University", ""),
    "veteran": ("Veteran", ""), "veterani": ("Veteran", "Men"),
    "veteranke": ("Veteran", "Women"),
    "djevojcice": ("Children", "Women"), "djevojke": ("Children", "Women"),
    "djecaci": ("Children", "Men"), "djecake": ("Children", "Men"),
    "men": ("", "Men"), "mens": ("", "Men"), "male": ("", "Men"),
    "women": ("", "Women"), "womens": ("", "Women"), "female": ("", "Women"),
    "masculin": ("", "Men"), "feminin": ("", "Women"),
    "hommes": ("", "Men"), "femmes": ("", "Women"), "dames": ("", "Women"),
    "gens": ("", "Men"), "filles": ("", "Women"),
    # The Vojvodina sheet codes the gender onto the weight: M-52kg, Ž-33kg.
    "m": ("", "Men"), "z": ("", "Women"), "f": ("", "Women"), "w": ("", "Women"),
}

_MODIFIER = {"mladi": "Younger", "mlade": "Younger", "mladji": "Younger",
             "mladje": "Younger", "stariji": "Older", "starije": "Older"}

# Words a heading may contain without being about age or gender at all.
_IGNORABLE = {"i", "and", "et", "de", "du", "la", "le", "les", "des", "za",
              "u", "s", "sa", "savate", "savateu", "resultats", "results",
              "official", "boks", "boksu", "jeunes", "mjesto", "kategorija"}

# A discipline printed as part of a class heading - "Men´s Assaut -60kg". It
# belongs in the label: without it the World Combat Games' assaut -60 kg and
# its combat -60 kg are one category holding two different competitions.
_DISCIPLINES = {"assaut": "Assaut", "combat": "Combat",
                "precombat": "Precombat", "prekombat": "Precombat"}

# Bounds spelled out in words, which only the French sheet does.
_UNDER_WORDS = {"moins", "sous", "under"}
_OVER_WORDS = {"plus", "over", "sur"}

# The countries these sheets print where a club would otherwise go. Deliberately
# a short explicit list: an unknown word stays a club, which shows up as an odd
# club rather than as a country nobody sent anyone from.
_COUNTRY_WORDS = {
    "madarska": "Hungary", "hungary": "Hungary", "magyarorszag": "Hungary",
    "austrija": "Austria", "austria": "Austria", "osterreich": "Austria",
    "slovenija": "Slovenia", "slovenia": "Slovenia",
    "srbija": "Serbia", "serbia": "Serbia",
    "hrvatska": "Croatia", "croatia": "Croatia",
    "italija": "Italy", "italy": "Italy",
    "njemacka": "Germany", "germany": "Germany",
    "slovacka": "Slovakia", "slovakia": "Slovakia",
    "bosna": "Bosnia and Herzegovina", "romania": "Romania",
}

# Below this, two words on a line are one word with a column between them.
_GAP = 8.0
# How far a word may sit off a line's baseline and still belong to it. Wider
# than the shared default: the French university sheet sets its place markers
# ("1°", "2°") a few points high, and at the default tolerance a row's place
# breaks off onto a line of its own and the competitor loses their medal.
_BASELINE = 5.0
# The top of savate's women's weight ladder. Above it, a class filed under a
# women's heading says the heading is wrong, not that the class exists.
_WOMENS_TOP = 75
# A place outside the podium. `check_placing` only stores 1-3, and a fifth is
# not a medal, so those rows are counted and reported rather than stored.
_PODIUM = set(MEDALS)


def _fold(text):
    """Accent- and case-insensitive key. `đ` needs doing by hand: it is a
    letter in its own right, not a d with a stroke, so NFKD leaves it alone."""
    return norm.fold(text).replace("đ", "d")


def _tokens(text):
    return [t for t in re.split(r"[^0-9A-Za-zÀ-ÿŽžĐđŠšČčĆć]+", _fold(text)) if t]


def _read_context(text):
    """(age, gender, discipline, bound, recognised) from a heading's words."""
    age, gender, bound, modifier, recognised = "", "", "", "", True
    discipline = ""
    for token in _tokens(text):
        if token in _DISCIPLINES:
            discipline = _DISCIPLINES[token]
        elif token in _MODIFIER:
            modifier = _MODIFIER[token]
        elif token in _VOCAB:
            klass, who = _VOCAB[token]
            age = klass or age
            gender = who or gender
        elif token in _UNDER_WORDS:
            bound = "under"
        elif token in _OVER_WORDS:
            bound = "over"
        elif token in _IGNORABLE:
            continue
        else:
            recognised = False
    if modifier and age:
        age = f"{modifier} {age}"
    return age, gender, discipline, bound, recognised


def _is_section(text):
    """(age, gender) if this line is an age/gender heading, else None."""
    body = _ROUNDS.sub("", text).strip().strip(":.-–— ")
    if not body or len(body) > 48 or re.search(r"\d", body):
        return None
    if len(_tokens(body)) > 6:
        return None
    age, gender, _d, _bound, recognised = _read_context(body)
    if not recognised or not (age or gender):
        return None
    return age, gender


def _despaced(text):
    """'C O M B A T' -> 'COMBAT'.

    The 2016 Zagreb report letter-spaces its discipline headings. Flowed text
    hides that - pdftotext collapses the gaps - but word geometry does not, and
    a heading read as six one-letter words is a heading that never fires.
    """
    parts = text.split()
    if len(parts) >= 3 and all(len(part) == 1 for part in parts):
        return "".join(parts)
    return text


def _segments(text):
    return [s for s in re.split(r"\s{2,}", text.strip()) if s]


def _country_of(text):
    """The country a bracket holds, or "" if it holds a club."""
    key = re.sub(r"[^a-z ]+", "", _fold(text)).strip()
    if key in _COUNTRY_WORDS:
        return _COUNTRY_WORDS[key]
    return ""


def _competitor(body):
    """(name, club, country) from the text following a place."""
    # A non-breaking space is a space; a run of two is still a column gap.
    body = body.replace("\u00a0", " ")
    fields = _segments(body)

    # A column gap: the Vojvodina sheet and the World Combat Games list.
    if len(fields) >= 2:
        if len(fields) == 2:
            name, rest = fields[0], fields[1]
        else:
            name, rest = " ".join(fields[:-1]), fields[-1]
        found = _NOC.match(rest)
        if found:
            return name.strip(), "", norm.country(found.group("name"))
        country = _country_of(rest)
        return (name.strip(), "" if country else rest.strip(), country)

    # A bracket: every Croatian sheet. Several rows lose the closing bracket
    # to the line break that follows it, so an opening one is enough - the
    # club or country it introduces runs to the end of the line either way.
    found = _PAREN.match(body)
    if found:
        name, inside = found.group("name"), found.group("inside")
    elif "(" in body and ")" not in body:
        name, inside = body.split("(", 1)
    else:
        name, inside = None, ""
    if name is not None:
        country = _country_of(inside)
        return (name.strip(" -–—,"), "" if country else inside.strip(), country)

    # A quoted club: the Serbian federation. Split at the last dash before the
    # first quote, so a row whose opening quote was lost still splits.
    quote = next((i for i, c in enumerate(body) if c in _QUOTE), -1)
    if quote >= 0:
        head = body[:quote]
        dashes = list(re.finditer(r"[-–—]+", head))
        if dashes:
            cut = dashes[-1]
            name, club = head[:cut.start()], head[cut.end():] + body[quote:]
        else:
            name, club = head, body[quote:]
        club = " ".join(club.strip(" -–—,").split())
        return (name.strip(" -–—,"),
                "".join(c for c in club if c not in _QUOTE).strip(), "")

    return body.strip(" -–—,"), "", ""


def _lines(path, report):
    """The document's lines, in reading order, with column gaps kept as runs of
    spaces. Geometry rather than flowed text, because one sheet in this family
    sets two columns per page and flowed text interleaves them into nonsense."""
    from savate import pdf

    words = pdf.words(path)
    if not words:
        return []
    report.notes["pages"] = len({w.page for w in words})
    out = []
    for page in sorted({w.page for w in words}):
        on_page = [w for w in words if w.page == page]
        for group in _columns(on_page, report, page):
            for row in pdf.rows(group, tolerance=_BASELINE):
                text, previous = "", None
                for word in row:
                    if previous is not None:
                        text += "  " if word.x0 - previous > _GAP else " "
                    text += word.text
                    previous = word.x1
                out.append(text)
    return out


def _columns(page_words, report, page):
    """One group of words per column, left to right, or the whole page.

    The split is taken from where the place numbers line up, not from white
    space: the sheet's centred title spans both columns and would close any
    gutter measured over the whole page.
    """
    from savate import pdf

    starts = collections.Counter()
    for row in pdf.rows(page_words, tolerance=_BASELINE):
        if row and _RANK.match(row[0].text + " x"):
            starts[round(row[0].x0)] += 1
    if len(starts) < 2:
        return [page_words]
    ordered = sorted(starts)
    left, right = ordered[0], ordered[-1]
    if right - left < 100 or starts[left] < 3 or starts[right] < 3:
        return [page_words]
    cut = right - 10
    first = [w for w in page_words if w.x0 < cut]
    second = [w for w in page_words if w.x0 >= cut]
    if not first or not second:
        return [page_words]
    report.notes.setdefault("split_pages", []).append(page)
    return [first, second]


def _label(age, gender, discipline, weight):
    return " ".join(p for p in (age, gender, discipline, weight) if p)


def read(source, slug, meta=None, **options):
    """(Tournament, [Placing], Report) from one ranked weight-class list."""
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    tournament = Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""), level=meta.get("level", ""),
        format=meta.get("format", ""), age_class=meta.get("age_class", ""),
        year=meta.get("year", ""), country=meta.get("country", ""),
        city=meta.get("city", ""), source=str(source), adapter=NAME)

    try:
        path = sources.fetch_archived(str(source)) if options.get("archived") \
            else sources.fetch(source, refresh=options.get("refresh", False))
    except Exception as e:                       # network, 404, wrong type
        report.problem(f"could not fetch the document: {e}")
        return tournament, [], report
    try:
        lines = _lines(path, report)
    except Exception as e:
        report.problem(f"could not read the document's words: {e}")
        return tournament, [], report

    placings = []
    section_age = meta.get("age_class", "")
    section_gender, discipline = "", ""
    klass, unsigned, unranked, off_podium, orphans, seen = None, 0, 0, 0, 0, set()

    def place(rank, body):
        """Store one ranked competitor, or say why it was not stored."""
        nonlocal off_podium, orphans
        if rank not in _PODIUM:
            off_podium += 1
            return
        if klass is None:
            orphans += 1
            return
        if _COUNTS.search(body):
            report.problem(f"{klass['category']}: a row ending in count columns "
                           f"was not read as a competitor: {body[:60]!r}")
            return
        name, club, country = _competitor(body)
        name = " ".join(name.split())
        if len(name) < 3 or not re.search(r"[A-Za-zÀ-ÿ]{2}", name):
            report.problem(f"{klass['category']}: place {rank} has no readable "
                           f"name in {body[:60]!r}")
            return
        if re.search(r"\d", name):
            report.problem(f"{klass['category']}: place {rank} reads as "
                           f"{name!r}, which carries digits - not stored")
            return
        key = (klass["category"], rank, _fold(name))
        if key in seen:
            return
        seen.add(key)
        placings.append(Placing(
            tournament=slug, placing_id=f"{slug}-{len(placings) + 1:04d}",
            category=klass["category"], gender=klass["gender"],
            age_class=klass["age_class"], weight_kg=klass["weight_kg"],
            weight_bound=klass["weight_bound"],
            rank=rank, medal=MEDALS[rank],
            fighter=name, club=club,
            # Only where the document prints one. These sheets name clubs, not
            # nations, and stamping the host country on every row would put a
            # Hungarian guest at a Zagreb open under Croatia.
            country=country,
            result_source="reported"))

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if _STOP.search(line):
            report.notes["stopped_at"] = line.strip()[:70]
            break
        if _OTHER_SPORT.search(line):
            klass = None
            report.notes.setdefault("other_sport", [])
            if line.strip()[:50] not in report.notes["other_sport"]:
                report.notes["other_sport"].append(line.strip()[:50])
            continue

        stripped = _despaced(line.strip())
        if _DISCIPLINE.match(stripped):
            discipline = stripped.split()[0].title()
            section_age, section_gender, klass = meta.get("age_class", ""), "", None
            continue

        found = _WEIGHT.match(stripped)
        rest = (found.group("rest") or "").strip() if found else ""
        if found and (not rest or _RANK.match(rest)):
            pre_age, pre_gender, pre_sport, pre_bound, recognised = \
                _read_context(found.group("pre"))
            if found.group("unit") or recognised or found.group("sign"):
                kilos = found.group("b") or found.group("a")
                sign = found.group("sign") or ""
                if sign == "+":
                    bound = "over"
                elif sign:
                    bound = "under"
                elif pre_bound:
                    bound = pre_bound
                elif found.group("b"):
                    bound = "under"
                else:
                    bound = "under"
                    unsigned += 1
                age = pre_age or section_age
                gender = pre_gender or section_gender
                weight = f"{'+' if bound == 'over' else '-'}{kilos} kg"
                sport = pre_sport or discipline
                klass = {"category": _label(age, gender, sport, weight),
                         "gender": gender, "age_class": age,
                         "weight_kg": kilos, "weight_bound": bound}
                if rest:
                    inner = _RANK.match(rest)
                    place(inner.group("rank"), inner.group("body"))
                continue

        found = _RANK.match(stripped)
        if found:
            place(found.group("rank"), found.group("body"))
            continue

        # A heading that lost its start to an extraction artefact - the
        # Vojvodina sheet overflows a club name into the next column - still
        # ends in a clean weight.
        fields = _segments(line)
        if len(fields) > 1:
            tail = _WEIGHT.match(fields[-1])
            if tail and not (tail.group("rest") or "").strip():
                _a, tail_gender, tail_sport, _b, tail_ok = \
                    _read_context(tail.group("pre"))
                if tail_ok and (tail.group("unit") or tail.group("sign")):
                    kilos = tail.group("b") or tail.group("a")
                    sign = tail.group("sign") or ""
                    bound = "over" if sign == "+" else "under"
                    if not sign and not tail.group("b"):
                        unsigned += 1
                    gender = tail_gender or section_gender
                    weight = f"{'+' if bound == 'over' else '-'}{kilos} kg"
                    klass = {"category": _label(section_age, gender,
                                                tail_sport or discipline,
                                                weight),
                             "gender": gender, "age_class": section_age,
                             "weight_kg": kilos, "weight_bound": bound}
                    continue

        heading = _is_section(stripped)
        if heading:
            # A heading that names only a gender - the French sheet's "Jeunes
            # Filles" - does not erase an age class the tournament declares.
            section_age = heading[0] or meta.get("age_class", "")
            section_gender = heading[1]
            klass = None
            continue

        found = _RANK_LAST.match(stripped)
        if found and klass is not None:
            place(found.group("rank"), found.group("body"))
            continue

        if klass is not None and _looks_like_entrant(stripped):
            unranked += 1

    report.read = len(lines)
    report.notes["placings"] = len(placings)
    report.notes["categories"] = len({p.category for p in placings})
    if unranked:
        report.notes["unranked_entrants"] = unranked
        report.problem(f"{unranked} competitor(s) printed under a weight class "
                       f"without a place - listed, not ranked, so not stored")
    if off_podium:
        report.notes["below_third"] = off_podium
        report.problem(f"{off_podium} placing(s) below third were dropped: this "
                       f"schema stores a podium and fifth is not one")
    if orphans:
        report.problem(f"{orphans} ranked line(s) appeared with no weight class "
                       f"in force and were dropped rather than filed under the "
                       f"previous one")
    if unsigned:
        report.problem(f"{unsigned} weight heading(s) printed no sign; read as "
                       f"an upper limit, which is what every savate class is "
                       f"except the open class, and that is always written '+'")
    if report.notes.get("split_pages"):
        report.problem(
            "page(s) " + ", ".join(str(p) for p in report.notes["split_pages"]) +
            " were read as two columns, left then right, with the age heading "
            "in force carried across the break - the sheet prints a heading "
            "only in the column it begins in")
    if report.notes.get("other_sport"):
        report.problem("heading(s) naming another sport were skipped: " +
                       "; ".join(report.notes["other_sport"][:4]))
    twice = sorted({p.category for p in placings
                    if p.rank != "3" and sum(
                        1 for q in placings
                        if q.category == p.category and q.rank == p.rank) > 1})
    if twice:
        report.problem(
            "the document awards the same place twice in " +
            ", ".join(twice[:4]) +
            (" and others" if len(twice) > 4 else "") +
            " - two weight classes printed under one heading, or a place "
            "mistyped; kept as printed rather than reassigned")
    # Savate's women's ladder stops at +75 kg. A women's class above it means
    # the document lost a heading, not that such a class exists - the 2024
    # Serbian combat report prints JUNIORKE and then six men's classes under
    # it. The rows are kept exactly as printed, because the only thing that
    # would fix them is a heading nobody wrote; the flag is what a reader needs.
    above = sorted({p.category for p in placings
                    if p.gender == "Women" and p.weight_kg.isdigit()
                    and int(p.weight_kg) > _WOMENS_TOP})
    if above:
        report.problem(
            "class(es) " + ", ".join(above) + " sit above savate's women's "
            "ladder, which stops at +75 kg: the section heading above them is "
            "probably missing from the document. Kept as printed")
    without_age = {p.category for p in placings if not p.age_class}
    if without_age:
        report.problem(f"{len(without_age)} category label(s) carry no age "
                       f"class because the document states none")
    if not placings:
        report.problem("no ranked weight-class lists found - this is probably "
                       "not a document this adapter can read")
    return tournament, placings, report


def _looks_like_entrant(text):
    """Is this an unplaced competitor rather than prose or a signature?"""
    if len(text) > 90 or not re.search(r"[A-Za-zÀ-ÿ]", text):
        return False
    return bool(_PAREN.match(text) or re.search(r"[„“”\"]", text)
                or len(_segments(text)) >= 2)
