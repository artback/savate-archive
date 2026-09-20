"""Adapter for podium documents: who finished where, with no bouts.

For most of savate's published history this is the only record that exists. The
federations printed medallists and nothing else until 2023, so an archive that
insists on bout-by-bout data simply has no 2007-2022 - and a podium is a real
fact worth keeping, as long as it is kept as a podium. The bouts that produced
it are not inferred here; the only thing a final tells you for certain is who
won it, and a bronze tells you nothing about who anyone beat.

Three layouts appear, and all three are line-oriented once the weight class is
known:

    Junior Male 48                       -56 Kg   Champion       HERBERT Charles
    Champion       FRANCOISE Loïck                Vice-champion  MESSAOUDEN F.
    Vice Champion  Ulugbekov Otabek
    Bronze         Varun Walia

and a table form, one row per class with gold, silver and two bronzes across the
columns. That one needs the column geometry, so it is read through the shared
word positions rather than the text.
"""

import re

from savate import normalize as norm
from savate import pdf
from savate.schema import MEDALS, Placing, Report, Tournament

NAME = "podium_pdf"
DESCRIPTION = "podium / medallist PDF (placings only, no bouts)"

# How each place is worded, across the federations and languages seen.
RANKS = [
    (re.compile(r"^(champion(ne)?|1\s*[ºo°]|gold|or)\b", re.I), "1"),
    (re.compile(r"^(vice[\s-]*champion(ne)?|2\s*[ºo°]|silver|argent|"
                r"finalist[e]?)\b", re.I), "2"),
    (re.compile(r"^(bronze|3\s*[ºo°]|3rd|troisi[èe]me)\b", re.I), "3"),
]
# A heading that names a weight class, in any of the forms the documents use:
# "Junior Male 48", "-56 Kg", "Senior Women -60kg", "52-56".
CLASS_HEADING = re.compile(
    r"^(?P<label>(?:[A-Za-zÀ-ÿ/ ]{0,40}?)\s*"
    r"(?P<sign>[-+−])?\s*(?P<kg>\d{2,3})(?:\s*[-–]\s*(?P<kg2>\d{2,3}))?"
    r"\s*(?:kg|kgs)?)\s*$", re.I)
# Words that make a line a heading for a whole section rather than a class.
SECTION = re.compile(r"^(masculin|f[ée]minin|men|women|male|female|junior|"
                     r"senior|cadet|youth|v[ée]t[ée]ran)", re.I)
MEDAL_HEADER = re.compile(r"\b(or\s*/\s*gold|gold|argent|silver|bronze)\b", re.I)


def _rank_in(line):
    """(rank, first word of what follows the label) for a medal line.

    The label is found wherever it sits, not only at the start: one layout
    writes "Champion  NAME  COUNTRY" on its own line, another writes
    "-56 Kg  Champion  NAME  COUNTRY" with the weight class in front. And the
    label's own length is taken from the match, so "Vice Champion" does not
    leave "Champion" stuck to the front of the name.
    """
    offsets, text = [], ""
    for w in line:
        if text:
            text += " "
        offsets.append(len(text))
        text += w.text
    for start, offset in enumerate(offsets):
        for pattern, rank in RANKS:
            m = pattern.match(text[offset:])
            if m:
                end = offset + m.end()
                after = next((i for i, o in enumerate(offsets) if o >= end),
                             len(line))
                return rank, start, after
    return "", 0, 0


def _class_of(text, section):
    """Structured weight class from a heading, or None if it is not one."""
    text = " ".join(str(text or "").split())
    if not text or len(text) > 48:
        return None
    m = CLASS_HEADING.match(text)
    if not m or not m.group("kg"):
        return None
    # "52-56" is an upper bound written as a band; the class is the upper number.
    kg = m.group("kg2") or m.group("kg")
    sign = m.group("sign") or ""
    label = " ".join(f"{section} {m.group('label')}".split())
    parsed = norm.category(label)
    return {
        "category": label,
        "gender": parsed["gender"] or norm.category(section)["gender"],
        "age_class": parsed["age_class"] or norm.category(section)["age_class"],
        "weight_kg": kg,
        "weight_bound": "over" if sign == "+" else "under",
    }


def _columns(lines, minimum=3):
    """The x positions several medal lines share. The last one is the country."""
    import collections

    counts = collections.Counter()
    for line in lines:
        for w in line:
            counts[round(w.x0)] += 1
    shared = sorted(x for x, n in counts.items() if n >= minimum)
    # Positions within a few points of each other are one column that wobbles.
    merged = []
    for x in shared:
        if merged and x - merged[-1] <= 6:
            continue
        merged.append(x)
    return merged


def _split(line, after, country_x):
    """Name and country from the words following the rank label."""
    rest = line[after:]
    name = [w for w in rest if w.x0 < country_x - 4]
    country = [w for w in rest if w.x0 >= country_x - 4]
    # One layout prints the column header "Medal" inside the name cell of some
    # lines; no fighter is named "Medal", so it is dropped, not kept.
    ntext = " ".join(w.text for w in name).strip()
    ntext = re.sub(r"^medal[\s-]+", "", ntext, flags=re.I).strip()
    return (ntext,
            " ".join(w.text for w in country).strip())


def read(source, slug, meta=None, **options):
    """(Tournament, [Placing], Report) from one podium document."""
    from savate import sources

    report = Report(source=str(source), adapter=NAME)
    path = sources.fetch_archived(str(source)) if options.get("archived") \
        else sources.fetch(source, refresh=options.get("refresh", False))
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))

    words = pdf.words(path)
    report.read = len({w.page for w in words})
    lines = pdf.rows(words)
    medal_lines = [l for l in lines if _rank_in(l)[0]]
    columns = _columns(medal_lines)
    country_x = columns[-1] if len(columns) >= 2 else None

    placings, section, klass, seen = [], "", None, set()
    for line in lines:
        text = pdf.text_of(line)
        rank, start, after = _rank_in(line)
        if not rank:
            if SECTION.match(text) and len(text) < 40 and not _class_of(text, ""):
                section = text
            found = _class_of(text, section)
            if found:
                klass = found
            continue
        # A class can be printed in front of the medal on the same line.
        if start:
            inline = _class_of(pdf.text_of(line[:start]), section)
            if inline:
                klass = inline
        if klass is None:
            report.problem(f"a {MEDALS[rank]} is listed before any weight class")
            continue
        if country_x is None:
            report.problem("the medal lines share no country column - this is "
                           "not a line-oriented podium")
            break
        name, country = _split(line, after, country_x)
        if not name:
            report.problem(f"{klass['category']}: a {MEDALS[rank]} with no name")
            continue
        key = (klass["category"], rank, norm.fold(name))
        if key in seen:
            continue
        seen.add(key)
        placings.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{len(placings) + 1:04d}",
            rank=rank, medal=MEDALS[rank],
            fighter=name, country=norm.country(country),
            result_source="reported",
            **klass,
        ))

    if not placings:
        report.notes["kind"] = "no placings found - not a line-oriented podium"
    report.notes["placings"] = len(placings)
    return tournament, placings, report
