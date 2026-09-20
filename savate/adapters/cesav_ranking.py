"""The European confederation's ranking page: nine championships on one URL.

CESav publishes every European championship podium it has kept - 2016 to 2026,
assaut and combat, seniors and youth - as a single HTML page of tables. That
shape breaks an assumption the rest of this archive is built on, which is that a
manifest entry names one document holding one competition. Here one document
holds nine, so the entry names the event as well as the URL:

    {"adapter": "cesav_ranking",
     "source": "https://www.savate-europe.com/index.php/ranking",
     "event": "European Championship Assaut 2023"}

and the adapter reads only the tables under that heading. The page's own
structure carries everything needed to do that: an event heading, then the
venue, then a gender heading, then the table.

Two details of the page decide how it is read.

*The nation is glued to the name.* A cell reads "ABAZOVSKI LIDIJASERBIA" as
often as "NANDI CHLOE FRANCE" - the markup separates them, the text does not.
Splitting on the last word would produce a competitor called LIDIJASERBIA, so
the split is made on the longest nation name the archive already recognises,
tested as a suffix. `savate.display` holds every attested spelling, which is the
same table that resolves countries everywhere else here.

*Savate awards two bronzes.* Both third-place columns are real, and both are
rank 3. That is not a duplicate row and must not be deduplicated into one.
"""

import html
import re

from savate import display
from savate.schema import Placing, Report, Tournament

NAME = "cesav_ranking"
DESCRIPTION = "CESav's European championship ranking page (many events, one URL)"

# An event heading names a year; a venue heading does not.
_YEAR = re.compile(r"\b(20[0-2]\d)\b")
_HEADING = re.compile(r"<h[1-5][^>]*>(.*?)</h[1-5]>", re.S | re.I)
_TABLE = re.compile(r"<table.*?</table>", re.S | re.I)
_ROW = re.compile(r"<tr.*?</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")

# "-48 kg", "48-52 kg", "+85 kg", and also "F48 kg" / "M-60 kg" where the class
# code carries the gender the heading sometimes omits.
_WEIGHT = re.compile(
    r"^\s*([FM])?\s*([-+]?)\s*(\d{2,3})\s*(?:[-–]\s*(\d{2,3}))?\s*kg\s*$", re.I)

# The page's other table shape: one row per medallist, the rank in words, and
# the weight printed only on the first row of each group.
_LONG_FORM = re.compile(r"\bresult\b", re.I)
_RANK_WORDS = [
    (1, r"^champion(ne)?$|^1"),
    (2, r"vice.?champion|^2|finalist"),
    (3, r"^3|bronze|troisi"),
]
# A class the championship did not award. Printed, and not a competitor.
_NOT_AWARDED = re.compile(r"titre non attribu|non attribu|not awarded", re.I)

_GENDER = [("Women", r"^wom[ae]n|^f[ée]minin|^dames"), ("Men", r"^men|^masculin|^homme")]
_AGE = [("Junior", r"junior"), ("Young", r"youth|jeune|cadet"), ("Senior", r"senior")]


def _plain(fragment):
    text = html.unescape(_TAGS.sub(" ", fragment or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _nations():
    """Every attested nation spelling, longest first, folded for matching."""
    spellings = []
    for canonical in display.countries():
        for spelling in display.spellings(canonical):
            spellings.append((display.fold(spelling).replace(" ", ""), canonical))
    spellings.sort(key=lambda pair: -len(pair[0]))
    return spellings


_NATIONS = _nations()


def split_nation(cell):
    """("NAME", "Nation") - the nation is the longest one the cell ends with."""
    text = _plain(cell)
    if not text:
        return "", ""
    squeezed = display.fold(text).replace(" ", "")
    for folded, canonical in _NATIONS:
        if len(folded) >= 3 and squeezed.endswith(folded):
            # Cut the same number of letters off the printed string, spaces
            # and accents included, so the name keeps its own punctuation.
            kept, seen = [], 0
            for ch in reversed(text):
                if seen >= len(folded):
                    kept.append(ch)
                elif ch.isalnum():
                    seen += 1
            name = "".join(reversed(kept)).strip(" ,;-")
            return name, canonical
    return text, ""


def _match(label, table):
    for value, pattern in table:
        if re.search(pattern, label, re.I):
            return value
    return ""


def _long_form(rows, slug, gender, age, meta, offset, report):
    """The weight | Result | Name | Country shape, weight set once per group."""
    out = []
    kilos, bound, here = "", "under", gender
    for row in rows[1:]:
        cells = [_plain(c) for c in _CELL.findall(row)]
        if len(cells) < 3:
            continue
        found = _WEIGHT.match(cells[0]) if cells[0] else None
        if found:
            letter, sign, low, high = found.groups()
            kilos = high or low
            bound = "over" if sign == "+" else "under"
            here = gender or ("Women" if (letter or "").upper() == "F"
                              else "Men" if (letter or "").upper() == "M" else "")
        if not kilos:
            continue
        word, name, nation = cells[1], cells[2], cells[3] if len(cells) > 3 else ""
        if _NOT_AWARDED.search(word) or _NOT_AWARDED.search(name):
            report.problem(f"{here} {kilos} kg: the title was not awarded")
            continue
        rank = next((r for r, pattern in _RANK_WORDS
                     if re.search(pattern, word, re.I)), 0)
        if not rank or len(name) < 3:
            continue
        label = " ".join(x for x in (age, here) if x)
        category = (f"{label} {'+' if bound == 'over' else '-'}{kilos} kg"
                    if label else f"{'+' if bound == 'over' else '-'}{kilos} kg")
        resolved = display.country(nation)
        out.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{offset + len(out) + 1:03d}",
            category=category, gender=here, age_class=age,
            weight_kg=str(kilos), weight_bound=bound,
            rank=str(rank), medal={1: "gold", 2: "silver", 3: "bronze"}[rank],
            fighter=name,
            country=resolved.name if resolved.known else nation,
            result_source="reported",
        ))
    return out


def read(source, slug, meta=None, **options):
    from savate import sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    wanted = str(options.get("event") or meta.get("event") or "").strip()

    page = sources.text(source)
    tournament = Tournament(
        slug=slug, name=meta.get("name", wanted or slug),
        discipline=meta.get("discipline", ""), level=meta.get("level", "european"),
        format=meta.get("format", "championship"),
        age_class=meta.get("age_class", ""), year=meta.get("year", ""),
        country=meta.get("country", ""), source=source, adapter=NAME,
    )

    # Walk headings and tables in the order the page prints them.
    pieces = re.findall(r"(<h[1-5][^>]*>.*?</h[1-5]>)|(<table.*?</table>)",
                        page, re.S | re.I)
    event, gender, age = "", "", ""
    placings, seen_events = [], []
    wanted_fold = display.fold(wanted)

    for heading, table in pieces:
        if heading:
            label = _plain(heading)
            if not label:
                continue
            if _YEAR.search(label) and len(label) > 8:
                event = label
                seen_events.append(label)
                gender, age = "", ""
                continue
            found = _match(label, _GENDER)
            if found:
                gender = found
                age = _match(label, _AGE) or age
            elif _match(label, _AGE):
                age = _match(label, _AGE)
            continue

        if not table or not event:
            continue
        if wanted and display.fold(event) != wanted_fold:
            continue

        rows = _ROW.findall(table)
        header = [_plain(c) for c in _CELL.findall(rows[0])] if rows else []
        if any(_LONG_FORM.search(h) for h in header):
            placings.extend(_long_form(rows, slug, gender, age, meta,
                                       len(placings), report))
            continue

        for row in rows:
            cells = [_plain(c) for c in _CELL.findall(row)]
            if len(cells) < 2 or not cells[0]:
                continue
            weight = _WEIGHT.match(cells[0])
            if not weight:
                continue
            letter, sign, low, high = weight.groups()
            # A band "48-52 kg" is the class ending at its upper figure; the
            # page's own "-48 kg" and "+85 kg" say which end is open.
            kilos = high or low
            bound = "over" if sign == "+" else "under"
            # Where the heading never said, the class code does.
            here = gender or ("Women" if (letter or "").upper() == "F"
                              else "Men" if (letter or "").upper() == "M" else "")
            label = " ".join(x for x in (age, here) if x)
            category = (f"{label} {'+' if bound == 'over' else '-'}{kilos} kg"
                        if label else f"{'+' if bound == 'over' else '-'}{kilos} kg")
            gender_here = here

            for column, cell in enumerate(cells[1:5], start=1):
                # Column four is the second bronze. Savate awards two, and both
                # are rank 3 - collapsing them would delete a real medallist.
                rank = 3 if column >= 3 else column
                if _NOT_AWARDED.search(cell):
                    report.problem(f"{category}: the title was not awarded")
                    continue
                name, nation = split_nation(cell)
                if not name or len(name) < 3:
                    continue
                placings.append(Placing(
                    tournament=slug,
                    placing_id=f"{slug}-{len(placings) + 1:03d}",
                    category=category, gender=gender_here, age_class=age,
                    weight_kg=str(kilos), weight_bound=bound,
                    rank=str(rank),
                    medal={1: "gold", 2: "silver", 3: "bronze"}[rank],
                    fighter=name, country=nation or meta.get("country", ""),
                    result_source="reported",
                ))

    report.read = len(pieces)
    report.notes["events_on_page"] = seen_events
    if wanted and display.fold(wanted) not in {display.fold(e) for e in seen_events}:
        report.problem(f"the page does not carry an event called {wanted!r}; "
                       f"it holds: {', '.join(seen_events)}")
    if not placings:
        report.problem("no podium rows read")
    return tournament, placings, report
