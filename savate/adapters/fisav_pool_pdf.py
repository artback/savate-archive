"""Adapter for FISav's other results PDF: the "pool results" layout.

FISav publishes results from more than one system, and this is the second. It
shares nothing with the poule-grid layout in fisav_pdf beyond the sport:

    * fighters are ROWS, not columns, each tagged with a slot code (A1, A2, B3)
    * points and warnings are two separate blocks side by side, both indexed by
      the same slot codes, so a row states what that fighter scored against each
      opponent and how many warnings they took doing it
    * a TOTAL and a RANK line close each block
    * the weight class is a code - M56, F+75 - not a sentence
    * the bracket is drawn separately, sometimes on the next page

Two details decide how this has to be read.

Values are right-aligned in their cells, so a number's left edge does not line up
with its column heading. The TOTAL line is used to calibrate: it carries exactly
one value per column, which fixes where a column's values actually sit.

And the bracket's lines cross. A winner is not drawn level with the bout it came
from, so the box's vertical position cannot say who won. What is reliable is
membership: the fighters in the next column are the ones who won, whichever line
they are drawn on. So rounds are paired in reading order and resolved by looking
forward - the same reasoning the ringside page uses to infer a knockout, except
here the next round is printed rather than guessed.
"""

import re
import statistics

from savate import identity
from savate import normalize as norm
from savate import pdf
from savate.schema import Bout, Report, Tournament

NAME = "fisav_pool_pdf"
DESCRIPTION = "FISav results PDF, pool-results layout (fighters as rows)"

# "M56", "F+75", "J60", "JF52": an age-and-sex prefix, an optional 'over' sign,
# and the limit in kilos. The prefix set is explicit rather than a wildcard: an
# unrecognised code must fail to be a weight class, not become one. Reading J56
# as a senior class - or worse, as no class at all, which silently files thirteen
# pages of juniors under the last senior category - is how a document quietly
# doubles somebody's record.
WEIGHT_CLASS = re.compile(r"^(?P<prefix>[A-Z]{1,2})\s*(?P<over>\+?)\s*"
                          r"(?P<kg>\d{2,3})$")
PREFIXES = {
    "M": ("Men", "Senior"), "F": ("Women", "Senior"),
    "SM": ("Men", "Senior"), "SF": ("Women", "Senior"),
    "J": ("Men", "Junior"), "JM": ("Men", "Junior"), "JF": ("Women", "Junior"),
    "C": ("Men", "Cadet"), "CM": ("Men", "Cadet"), "CF": ("Women", "Cadet"),
    "V": ("Men", "Veteran"), "VM": ("Men", "Veteran"), "VF": ("Women", "Veteran"),
}
SLOT = re.compile(r"^(?P<poule>[A-Z])(?P<seat>\d{1,2})$")
# Bracket boxes that name a slot rather than a person.
PLACEHOLDER = re.compile(r"^(vainqueur|2nd|champion|winner|finaliste)", re.I)
ROUND_HEADINGS = [("1/4", "quarter"), ("1/2", "semi"), ("final", "final")]


def _cluster(words, gap=12.0):
    groups = []
    for w in sorted(words, key=lambda w: w.x0):
        if groups and w.x0 - groups[-1][-1].x1 <= gap:
            groups[-1].append(w)
        else:
            groups.append([w])
    return groups


def _number(text):
    try:
        return int(float(str(text).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _nearest(x, centres, tolerance=22.0):
    """Index of the column whose values sit nearest x, or None."""
    if not centres:
        return None
    best = min(range(len(centres)), key=lambda i: abs(x - centres[i]))
    return best if abs(x - centres[best]) <= tolerance else None


def weight_class(code):
    """A class code expanded, or None if it is not one.

    The discipline is not in the code - the whole document is one discipline -
    so it stays on the tournament rather than being guessed into the category.
    """
    m = WEIGHT_CLASS.match(" ".join(str(code or "").split()))
    if not m:
        return None
    known = PREFIXES.get(m.group("prefix").upper())
    if not known:
        return None
    gender, age = known
    sign = "+" if m.group("over") else "-"
    return {"category": f"{age} {gender} {sign}{m.group('kg')} kg",
            "gender": gender, "age_class": age,
            "weight_kg": m.group("kg"),
            "weight_bound": "over" if m.group("over") else "under"}


class Sheet:
    """One document, read page by page into weight classes."""

    def __init__(self, path, report):
        self.report = report
        self.pages = pdf.by_page(pdf.words(path))
        self.countries = set()
        self.quiet = False

    def complain(self, message):
        if not self.quiet:
            self.report.problem(message)

    def classes(self):
        """Weight classes, read twice.

        Extraction occasionally runs a name into the country beside it -
        "DE ROBILLARDMAURITIUS" - and a fighter dropped for that reason is then
        missing from the bracket as well, where they may appear four more times.
        One bad cell would cost a whole knockout round. So the document is read
        once to learn which countries appear in it, and again with that
        vocabulary available to split the fused cells.
        """
        self.quiet = True
        first = self._walk()
        self.countries = {c for klass in first for c in klass["roster"].values()
                          if c}
        self.quiet = False
        return self._walk()

    def _walk(self):
        """[{class, roster, poules, brackets}] - one per weight class.

        A page is not a weight class. One page can carry the end of a class -
        its bracket - and the start of the next, and the class code is not
        reliably at the top: it can sit halfway down, or share a line with the
        grid header beneath it. So a page is cut at each code it contains, and
        everything above the first cut belongs to the class already open.
        """
        # A document can print the same weight class more than once - the 2025
        # European sheets print all sixteen three times over, once per language.
        # A repeated code is the same class, not a new one, so it reopens the
        # class already built; otherwise every combat in the event is recorded
        # three times and every poule shows three identical rows.
        current, out, opened = None, [], {}
        for number in sorted(self.pages):
            lines = pdf.rows(self.pages[number])
            cuts = [(i, weight_class(line[0].text))
                    for i, line in enumerate(lines)
                    if line and weight_class(line[0].text)]
            # Where a code is repeated - "M60" then "M60 POINTS AVT" - the
            # second sighting is the same class, not a new one.
            trimmed = []
            for i, heading in cuts:
                if trimmed and trimmed[-1][1] == heading:
                    continue
                trimmed.append((i, heading))
            bounds = [i for i, _ in trimmed] + [len(lines)]

            segments = []
            if not trimmed or trimmed[0][0] > 0:
                segments.append((None, lines[:bounds[0]]))
            for n, (start, heading) in enumerate(trimmed):
                segments.append((heading, lines[start:bounds[n + 1]]))

            for heading, block in segments:
                if heading:
                    code = heading["category"]
                    if code in opened:
                        current = opened[code]
                    else:
                        current = {"class": heading, "roster": {}, "poules": [],
                                   "brackets": [], "seen": set()}
                        opened[code] = current
                        out.append(current)
                if current is None or not block:
                    continue
                for found in self._poule_blocks(block, current):
                    # Identity is the poule and who is in it, so a reprint of the
                    # same grid is recognised however it is laid out.
                    mark = (found["poule"],
                            frozenset(r["name"] for r in found["rows"].values()))
                    if mark in current["seen"]:
                        continue
                    current["seen"].add(mark)
                    current["poules"].append(found)
                bracket = self._bracket(block)
                if bracket:
                    # The bracket is reprinted with its class; identify it by the
                    # rounds it names and who it draws, not by the page it is on.
                    mark = ("bracket", tuple(bracket["phases"]),
                            tuple(sorted(n for _, _, n in
                                         _sightings(bracket, current["roster"]))))
                    if mark not in current["seen"]:
                        current["seen"].add(mark)
                        current["brackets"].append(bracket)
        return out

    # --- the grids ------------------------------------------------------
    def _poule_blocks(self, lines, klass):
        blocks = []
        for index, line in enumerate(lines):
            text = pdf.text_of(line)
            if "POINTS" not in text or "AVT" not in text:
                continue
            block = self._read_block(lines, index, klass)
            if block:
                blocks.append(block)
        return blocks

    def _read_block(self, lines, header_index, klass):
        seats_line = next((l for l in lines[header_index + 1:header_index + 3]
                           if all(SLOT.match(w.text) for w in l) and len(l) >= 2),
                          None)
        if not seats_line:
            self.complain("a POINTS/AVT block has no slot-code row")
            return None
        anchors = [w.x0 for w in seats_line]
        seats = [w.text for w in seats_line]
        count = len(seats) // 2
        if count < 2 or seats[:count] != seats[count:]:
            self.complain(f"slot codes {seats} are not two matching blocks")
            return None

        body = lines[lines.index(seats_line) + 1:]
        totals_line = next((l for l in body if l and l[0].text == "TOTAL"), None)
        if totals_line is None:
            self.complain(f"poule {seats[0][0]}: no TOTAL row to calibrate on")
            return None
        stop = body.index(totals_line)

        # The TOTAL row carries one value per column; where its numbers sit is
        # where every column's values sit.
        # The TOTAL line sometimes totals the points block only. Pairing its
        # values with the leading anchors still fixes the offset, because every
        # column on the line shares one.
        values = [w for w in totals_line[1:] if _number(w.text) is not None]
        if len(values) >= count:
            offset = statistics.median(v.x0 - a for v, a in zip(values, anchors))
        else:
            offset = 28.0
            self.complain(f"poule {seats[0][0]}: TOTAL has only "
                          f"{len(values)} values, too few to calibrate on")
        centres = [a + offset for a in anchors]
        slot_x = totals_line[0].x0
        country_x = self._country_column(body[:body.index(totals_line)], slot_x)

        rows = {}
        for line in body[:stop]:
            tagged = [w for w in line
                      if SLOT.match(w.text) and abs(w.x0 - slot_x) <= 12]
            if not tagged:
                continue
            seat = tagged[0].text
            before = [w for w in line if w.x1 <= tagged[0].x0 - 2]
            if country_x is None:
                self.complain(f"{seat}: no country column in this block")
                continue
            name = " ".join(w.text for w in before if w.x0 < country_x - 4)
            country = " ".join(w.text for w in before
                               if w.x0 >= country_x - 4).title()
            if not country:
                name, country = self._unfuse(name)
            if not (name and country):
                self.complain(f"{seat}: could not separate name from country in "
                              f"{' '.join(w.text for w in before)!r}")
                continue
            points, warnings = {}, {}
            for w in line:
                if w.x0 <= tagged[0].x0:
                    continue
                value = _number(w.text)
                column = _nearest(w.x0, centres)
                if value is None or column is None:
                    continue
                (points if column < count else warnings)[seats[column]] = value
            rows[seat] = {"name": name, "country": country,
                          "points": points, "warnings": warnings}
            klass["roster"][name] = country

        if len(rows) != count:
            self.complain(f"poule {seats[0][0]}: {len(rows)} fighters "
                          f"read for {count} slots")
        # The TOTAL line is the sheet's own sum of the column above it. Checking
        # against it catches a mis-calibrated column, which would otherwise
        # produce a complete and entirely wrong poule.
        for i, seat in enumerate(seats[:count]):
            if seat not in rows or i >= len(values):
                continue
            printed = _number(values[i].text)
            mine = sum(rows[seat]["points"].values())
            if printed is not None and mine != printed:
                self.complain(f"poule {seats[0][0]}: {rows[seat]['name']} sums "
                              f"to {mine} but the TOTAL row says {printed}")
        return {"poule": seats[0][0] if seats else "", "seats": seats[:count],
                "rows": rows, "totals": values}

    def _unfuse(self, text):
        """Split a cell where the name ran into the country, or return it as is.

        Only a country this document has already shown elsewhere is used to make
        the cut, so the split is evidence from the same page set rather than a
        guess about what looks like a country.
        """
        words = text.split()
        if not words:
            return text, ""
        tail = words[-1].upper()
        for country in sorted(self.countries, key=len, reverse=True):
            token = country.upper().replace(" ", "")
            if len(tail) > len(token) and tail.endswith(token):
                head = words[:-1] + [tail[:-len(token)]]
                return " ".join(head).title() if text.istitle() else \
                    " ".join(head), country
        return text, ""

    @staticmethod
    def _country_column(rows, slot_x):
        """Where the country column starts, from the rows themselves.

        Splitting name from country on the gap between them fails: "PEÑA" and
        "COLOMBIA" sit eleven points apart, closer than some names are to their
        own next word. But the country is a column - it starts at the same x on
        every row of the block - so the x that most rows have a word at, nearest
        the slot codes, is where it begins.
        """
        import collections

        counts = collections.Counter()
        seen = 0
        for line in rows:
            tagged = [w for w in line if SLOT.match(w.text)
                      and abs(w.x0 - slot_x) <= 12]
            if not tagged:
                continue
            seen += 1
            for w in line:
                if w.x1 <= tagged[0].x0 - 2:
                    counts[round(w.x0)] += 1
        if not seen:
            return None
        shared = [x for x, n in counts.items() if n >= max(2, seen - 1)]
        # The leftmost shared column is where names start; the country is the
        # rightmost one that every row also has.
        return max(shared) if len(shared) >= 2 else None

    # --- the bracket ----------------------------------------------------
    def _bracket(self, lines):
        heading = next((l for l in lines
                        if "GROUPS" in pdf.text_of(l).upper()
                        and "FINAL" in pdf.text_of(l).upper()), None)
        if heading is None:
            return None
        phases = []
        for group in _cluster(heading, gap=20.0):
            label = pdf.text_of(group).lower()
            if "groups" in label:
                continue
            phases.append(next((p for token, p in ROUND_HEADINGS if token in label),
                               "final"))
        return {"top": heading[0].top, "phases": phases, "lines": lines}


def _sightings(bracket, roster):
    """[(x, y, fighter)] - every place a roster name is printed in the bracket.

    The columns are found from where the names actually are, not from where the
    headings sit: a heading is centred over its column while its boxes start
    well to the left, and the gap is wide enough to put a fighter in the wrong
    round.

    Matching is against the class's own roster, in two passes. A box usually
    holds the whole name plus the country, and sometimes a slot code, so the
    first pass asks whether a roster name fits inside the box's words. But a
    long name in a narrow box wraps, leaving a fragment - and a fragment that
    fits only one fighter on the card is still that fighter, so the second pass
    accepts it. A fragment that fits two is ambiguous and is dropped, because
    putting the wrong fighter in a round invents a result.
    """
    names = {name: set(identity.tokens(name)) for name in roster}
    countries = set()
    for country in roster.values():
        countries |= set(identity.tokens(country))
    longest = sorted(names, key=lambda n: -len(names[n]))

    def split_fused(tokens):
        """Separate a token that ran into the country beside it.

        The same extraction fault that fuses a name and a country in the grid
        fuses it in the bracket, and in a bracket it costs more: the fighter
        then matches nothing, and every round they reached loses a competitor.
        """
        out = set()
        for token in tokens:
            for country in countries:
                if len(token) > len(country) and token.endswith(country):
                    out.add(token[:-len(country)])
                    out.add(country)
                    break
            else:
                out.add(token)
        return out

    out = []
    for line in bracket["lines"]:
        if line[0].top <= bracket["top"]:
            continue
        for group in _cluster(line, gap=26.0):
            text = " ".join(w.text for w in group)
            if PLACEHOLDER.match(text.strip()):
                continue
            tokens = split_fused(set(identity.tokens(text)))
            if not tokens:
                continue
            match = next((n for n in longest if names[n] and names[n] <= tokens),
                         None)
            if match is None:
                fragment = tokens - countries
                candidates = [n for n in names
                              if fragment and fragment <= names[n]]
                match = candidates[0] if len(candidates) == 1 else None
            if match:
                out.append((group[0].x0, group[0].top, match))
    return out


def _columns(sightings, gap=55.0, wanted=None):
    """Group sightings into columns by where they start, left to right.

    `wanted` is how many columns the bracket's own headings imply. If clustering
    finds more, the narrowest gap between neighbouring columns is closed until
    the count matches - splitting one round into two would misread every bout in
    it, while merging two boxes that were always one column costs nothing.
    """
    columns, current = [], []
    for x, y, name in sorted(sightings):
        if current and x - current[-1][0] > gap:
            columns.append(current)
            current = []
        current.append((x, y, name))
    if current:
        columns.append(current)

    while wanted and len(columns) > wanted >= 1:
        distances = [columns[i + 1][0][0] - columns[i][-1][0]
                     for i in range(len(columns) - 1)]
        i = distances.index(min(distances))
        columns[i:i + 2] = [sorted(columns[i] + columns[i + 1])]
    return columns


def _bracket_bouts(klass, bracket, slug, index, report):
    """Knockout bouts, from the columns of printed names.

    The first column is the group listing, not a round. The last is the champion,
    which resolves the final rather than being one. What lies between is the
    rounds, in the order the headings name them.
    """
    roster = klass["roster"]
    where = klass["class"]["category"]
    phases = bracket["phases"]
    # The headings say how many rounds are drawn, which is the one thing about
    # the bracket that is stated rather than inferred. Where the boxes cluster
    # into more columns than that - a box indented a little further than its
    # neighbours - the closest pair is merged until the two agree.
    columns = _columns(_sightings(bracket, roster),
                       wanted=len(phases) + 2)
    if len(columns) < 3:
        return []               # a listing and a champion, with nothing drawn
    rounds = columns[1:]
    if len(phases) != len(rounds) - 1:
        report.problem(f"{where}: {len(phases)} round headings for "
                       f"{len(rounds) - 1} drawn rounds")
        phases = (phases + ["final"] * len(rounds))[:len(rounds) - 1]

    out = []
    for i, phase in enumerate(phases):
        entries = [name for _, _, name in sorted(rounds[i], key=lambda s: s[1])]
        seen, ordered = set(), []
        for name in entries:            # a box can be printed twice
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        entries = ordered
        winners = {name for _, _, name in rounds[i + 1]}
        column = {"label": phase, "phase": phase}
        if len(entries) % 2:
            report.problem(f"{where} {phase}: {len(entries)} fighters "
                           f"cannot be paired")
            continue
        for n, (a, b) in enumerate(zip(entries[::2], entries[1::2]), 1):
            corner = ("red" if a in winners else "blue" if b in winners else "")
            if not corner:
                report.problem(f"{klass['class']['category']} {column['label']}: "
                               f"neither {a} nor {b} appears in the next round")
            out.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-{index:02d}-{column['phase']}{n:02d}",
                phase=column["phase"],
                red=a, red_country=roster.get(a, ""),
                blue=b, blue_country=roster.get(b, ""),
                winner_corner=corner,
                winner={"red": a, "blue": b}.get(corner, ""),
                loser={"red": b, "blue": a}.get(corner, ""),
                status="decided" if corner else "unresolved",
                result_source="reported" if corner else "",
                **klass["class"],
            ))
    return out


def _poule_token(block):
    """A filename-safe tag for a poule, or "" where the source names none."""
    letter = str(block.get("poule") or "").strip()
    return "".join(c for c in letter if c.isalnum()).upper()


def _poule_bouts(klass, block, slug, index, report):
    from savate import rules

    rows, out = block["rows"], []
    seats = [s for s in block["seats"] if s in rows]
    seen = set()
    for a in seats:
        for b in seats:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            a_points = rows[a]["points"].get(b)
            b_points = rows[b]["points"].get(a)
            if a_points is None and b_points is None:
                continue        # these two did not meet
            a_warnings = rows[a]["warnings"].get(b, 0)
            b_warnings = rows[b]["warnings"].get(a, 0)
            corner = ("red" if (a_points or 0) > (b_points or 0) else
                      "blue" if (b_points or 0) > (a_points or 0) else "")
            won = max(a_points or 0, b_points or 0)
            lost = min(a_points or 0, b_points or 0)
            loser_warnings = (b_warnings if corner == "red" else a_warnings)
            decision = rules.decision_from_points(won, lost, loser_warnings)
            if corner and not decision:
                report.problem(f"{klass['class']['category']} poule "
                               f"{block['poule']}: {rows[a]['name']} "
                               f"{a_points}-{b_points} {rows[b]['name']} is a "
                               f"scoreline with no known decision")
            out.append(Bout(
                tournament=slug,
                # The poule letter belongs in the id. Without it a weight
                # class drawn as two poules gives its A1-A2 pairing the same
                # id twice, and the schema check rejects the whole build - as
                # it did for the 2024 European championships, which is the
                # first source in this archive to split a class in two.
                bout_id=f"{slug}-{index:02d}{_poule_token(block)}-{a}{b}",
                phase="poule", poule=block["poule"],
                red=rows[a]["name"], red_country=rows[a]["country"],
                blue=rows[b]["name"], blue_country=rows[b]["country"],
                red_points="" if a_points is None else str(a_points),
                blue_points="" if b_points is None else str(b_points),
                red_warnings=str(a_warnings), blue_warnings=str(b_warnings),
                winner_corner=corner,
                winner={"red": rows[a]["name"], "blue": rows[b]["name"]}.get(corner, ""),
                loser={"red": rows[b]["name"], "blue": rows[a]["name"]}.get(corner, ""),
                decision=decision,
                status="decided" if corner else "unresolved",
                result_source="reported" if corner else "",
                **klass["class"],
            ))
    return out


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout], Report) from one FISav pool-results PDF."""
    from savate import sources

    report = Report(source=str(source), adapter=NAME)
    path = (sources.fetch_archived(str(source))
        if options.get("archived")
        else sources.fetch(source, refresh=options.get("refresh", False)))
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))

    sheet = Sheet(path, report)
    classes = sheet.classes()
    report.read = len(sheet.pages)
    report.notes["weight_classes"] = len(classes)

    bouts = []
    for index, klass in enumerate(classes, 1):
        before = len(bouts)
        for block in klass["poules"]:
            bouts.extend(_poule_bouts(klass, block, slug, index, report))
        for bracket in klass["brackets"]:
            bouts.extend(_bracket_bouts(klass, bracket, slug, index, report))
        if len(bouts) == before:
            # Usually a class of two, drawn as a single final with no poule and
            # no round headings. Said out loud rather than dropped, because a
            # missing weight class is exactly what nobody notices.
            report.problem(f"{klass['class']['category']}: no readable bouts "
                           f"(a class too small to have a poule?)")
    if not bouts:
        report.notes["kind"] = "no bouts found - probably not this layout"
    return tournament, bouts, report
