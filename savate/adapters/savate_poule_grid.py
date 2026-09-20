"""Adapter for the CESav poule-grid sheet: seat codes, POINTS/AVT, a drawn final.

This is the layout the European confederation's own results documents are typed
in - a Word file, not a timing system's export - and it is the shape
`fisav_pool_pdf` was written for and fails on. Both print a cross-table indexed
by seat codes (A1, B3) with a POINTS block and an AVT block side by side and a
TOTAL/RANK line under them. The difference is everything around that table, and
it is enough to lose a whole championship:

    * The weight class is not the first word of a line. Varazze 2024 writes it
      as two words with a space in the middle - "J 56", "M 85 +" - and Slovenia
      2026 hides it at the end of the page's running title, "... Results M48".
      `fisav_pool_pdf` looks only at `line[0].text`, finds no class anywhere in
      Varazze, and files all nine junior and senior classes under one heading.
    * The age class is written once, as a section heading - "Juniors", then
      "Seniors" - or as a word in the running title ("YOUTH ..."). It is not in
      the code: Varazze's "M60" is a senior and Slovenia's "M60" is a youth, and
      reading the letter as the age would silently merge two different events.
    * The knockout is not drawn as a bracket with round headings. It is a column
      of "Vainqueur A" / "2nd Groups B" labels with a name beside each, and a
      "CHAMPION" box at the end.

So this is a new reader rather than a variant. Four things in it are worth
explaining, because each was a wrong answer first.

*Name and country overlap.* Varazze sets the country in a column that starts
inside the name cell, so "VUKASINOVIC"(118-187) and "SERBIA"(183-219) overlap by
four points and "SARA"(190-217) sits inside "SERBIA". Splitting on x - which is
what a column-geometry reader does - gives the name "VUKASINOVIC" and the
country "Serbia Sara". The words are separated by *vocabulary* instead: the
country is the word that is a country, and the same lexicon splits the cells the
extractor fused outright ("SARAITALIA", "MYKHAILOVUKRAINE"). A row whose country
cannot be recognised keeps its whole cell as the name and says so, because a
wrong name is worse than a missing country.

*Words are broken mid-name.* Slovenia's PDF writer emits "LONCHAM P SIM ON" for
LONCHAMP SIMON and "M AM M ADLI" for MAMMADLI. The gap that means "no space
here" is about a fifth of a character width and the gap that means a space is
about two fifths, but both are absolute point measurements and the document
changes font size between pages - so the threshold is taken as a fraction of the
line's own character pitch, not as a constant. Overlapping words are never
joined: an overlap means two cells, never one word (this is what keeps the rule
from fusing Varazze's name and country back together). One pair sits on the
line: "QUENE AUDIE" is joined on one page and separated on another, so names are
matched with the separators removed as well as by their words.

*Nothing says who stood in which corner.* These sheets name the winner; red and
blue mean corner in this archive and nothing else. So the two fighters are put
in the two slots in seat order, `winner` and `loser` are filled, and
`winner_corner` is left empty rather than invented.

*A bracket says who won by who is printed next.* A bout's winner is the fighter
who reappears in the column to the right, or in the CHAMPION box. That is a
deduction from the drawing, not a printed result, so it is recorded as
`inferred` - except the final, whose winner the CHAMPION box states outright.
Where the next column is empty the bout is left unresolved, which is the honest
reading of five Varazze classes whose champion box was never filled in.

Four things it refuses to do.

It will not read a poule that names the same fighter twice. Varazze's unlabelled
junior class does, and there is no way to know which of the two rows should have
been the third entrant, so the poule is reported and dropped rather than turned
into a man fighting himself.

It will not file a grid that carries no class code under the class above it.
Where a grid repeats a poule letter with an entirely different roster it is the
first poule of a class whose heading was left out; it gets the age and gender
from the section heading and no weight at all, which is less than the document
should have said but all of it that is true.

It will not call the larger of two losing scores a win. A win is three points in
this scale, always - the FISav worksheets print it - and Varazze has one bout
scored 1-0 and nine scored 1-1, none of which is a result. Those are reported
and left unresolved. A 3-3 is different: a draw scores three apiece, so it is
recorded as a draw, with no winner.

And it does not name a phase the drawing does not imply. Rounds are counted back
from the right-hand column of names, so the last one drawn is the final.

Two safeguards are there for documents nobody has seen yet. A class printed
twice - the FISav European sheets print every class once per language - reopens
the class it already built, and a poule already read with the same roster is
skipped, because reading it twice gives its bouts the same ids twice and the
schema then rejects the whole build. And the entrants listed down the left of
the drawing are added to the roster: that listing is sometimes the only place a
fighter is named, and reading it is what recovers the one Varazze final whose
grid lost its third competitor.
"""

import re
import statistics

from savate import normalize as norm
from savate import pdf
from savate import rules
from savate.schema import MEDALS, Bout, Placing, Report, Tournament, check, \
    check_placing

NAME = "savate_poule_grid"
DESCRIPTION = "CESav poule-grid sheet (seat codes, POINTS/AVT, Vainqueur/2nd Groups)"

# A class code: an age-and-sex prefix, the limit in kilos, and a '+' on either
# side of it for the open class. "JF 52", "M60", "F75 +", "M+85", "M 85 +".
CLASS_CODE = re.compile(r"^(?P<prefix>[A-Z]{1,2})\s*(?P<over1>\+?)\s*"
                        r"(?P<kg>\d{2,3})\s*(?P<over2>\+?)$")
# The prefix states the sex. It does not state the age class reliably - see the
# module docstring - so only the letters that carry an age are listed as one,
# and the section heading wins wherever there is one.
PREFIX_GENDER = {
    "M": "Men", "F": "Women",
    "J": "Men", "JM": "Men", "JF": "Women",
    "S": "Men", "SM": "Men", "SF": "Women",
    "C": "Men", "CM": "Men", "CF": "Women",
    "V": "Men", "VM": "Men", "VF": "Women",
}
PREFIX_AGE = {
    "J": "Junior", "JM": "Junior", "JF": "Junior",
    "S": "Senior", "SM": "Senior", "SF": "Senior",
    "C": "Cadet", "CM": "Cadet", "CF": "Cadet",
    "V": "Veteran", "VM": "Veteran", "VF": "Veteran",
}
# A section heading, or a word in the running title, that names the age class.
# Youth first: a "YOUTH" championship is not a junior one, and the two words
# appear in different documents for different events.
AGE_WORDS = [("Youth", r"\byouth\b|\bjeunes?\b"),
             ("Junior", r"\bjuniors?\b"),
             ("Cadet", r"\bcadets?\b"),
             ("Veteran", r"\bv[ée]t[ée]rans?\b|\bmasters?\b"),
             ("Senior", r"\bs[ée]niors?\b")]
SLOT = re.compile(r"^(?P<poule>[A-Z])(?P<seat>\d{1,2})$")
# Words that sit on the seat-code line without being seat codes.
GRID_HEADERS = re.compile(r"^(POINTS?|AVTS?|PTS)$", re.I)
CHAMPION = re.compile(r"^CHAMPIO", re.I)
WINNER_LABEL = re.compile(r"^(vainqueur|winner|1er|1st)\b", re.I)
RUNNERUP_LABEL = re.compile(r"^(2nd|2e|2eme|second)\s+group", re.I)
# "or" is French for gold and is deliberately not here: it is two letters, and
# the extraction that breaks "M OR" out of HEGEDUS MOR would turn a fighter into
# a medal. The words that are left cannot be halves of a name.
MEDAL_WORDS = {"gold": "1", "silver": "2", "argent": "2", "bronze": "3"}
# Phases counted back from the right-hand column of the drawing.
PHASES_FROM_RIGHT = ["final", "semi", "quarter", "r16", "r32", "r64"]

# Country spellings these documents use that the shared lexicon does not carry -
# it is keyed on French spellings and on the canonical English ones, and these
# sheets mix in Italian and English forms ("ITALIA", "HUNGRIA", "CROATIA").
# France is absent from the shared table because it is the language it is
# written in. Recognising a country is what separates it from the name beside
# it, so an unrecognised one costs a name, not just a flag.
EXTRA_COUNTRIES = {
    "france", "italia", "serbia", "croatia", "hungria", "bulgaria", "austria",
    "slovenia", "belgium", "finland", "azerbaijan", "greece", "turkey",
    "ukraine", "germany", "england", "spain", "poland", "romania", "moldova",
    "moldavie", "georgie", "georgia", "armenia", "kazakhstan", "uzbekistan",
    "macedoine", "macedonia", "albanie", "albania", "bosnie", "bosnia",
    "montenegro", "slovaquie", "slovakia", "lettonie", "latvia", "lituanie",
    "lithuania", "estonie", "estonia", "irlande", "ireland", "ecosse",
    "scotland", "malte", "malta", "chypre", "cyprus", "luxembourg", "monaco",
    "israel", "sweden", "norway", "denmark", "netherlands", "switzerland",
    "portugal", "russia", "czechia",
}


def _fold(text):
    """Letters only, accent- and case-free: the key everything is matched on."""
    return re.sub(r"[^a-z0-9]+", "", norm.fold(text))


COUNTRY_KEYS = ({_fold(k) for k in norm.COUNTRIES}
                | {_fold(v) for v in norm.COUNTRIES.values()}
                | {_fold(c) for c in EXTRA_COUNTRIES})


def is_country(text):
    return _fold(text) in COUNTRY_KEYS


def split_country(text):
    """('MYKHAILOV', 'UKRAINE') for a cell whose country fused onto the name.

    Only a spelling the lexicon knows is cut off, and only from the end, so the
    split is a recognition rather than a guess about where a word looks like it
    ends.
    """
    folded = _fold(text)
    for key in sorted(COUNTRY_KEYS, key=len, reverse=True):
        if len(folded) > len(key) and folded.endswith(key):
            return text[:len(text) - len(key)], text[len(text) - len(key):]
    return text, ""


def _number(text):
    try:
        return int(float(str(text).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _pitch(line):
    """The line's character width, from the words wide enough to measure."""
    widths = [(w.x1 - w.x0) / len(w.text) for w in line if len(w.text) >= 3]
    return statistics.median(widths) if widths else 0.0


def mend(line, factor=0.22):
    """Rejoin words the extractor broke inside a name.

    The threshold scales with the line's own character pitch because the
    document changes font size between pages, and an absolute gap that means
    "same word" on one page means "space" on the next. Words that overlap are
    left alone: an overlap is two cells printed over each other, never one word
    split in two.
    """
    pitch = _pitch(line)
    if pitch <= 0:
        return list(line)
    limit = factor * pitch
    out = []
    for w in sorted(line, key=lambda w: w.x0):
        # A seat code and a score are never halves of a word, and in Slovenia
        # the seat sits one point from the name beside it - inside the joining
        # threshold. Gluing "ÇETİNKAYA" to "A2" costs the whole row.
        joinable = not (SLOT.match(w.text) or w.text.strip("-+").isdigit()
                        or (out and (SLOT.match(out[-1].text)
                                     or out[-1].text.strip("-+").isdigit())))
        if (joinable and out and 0 <= w.x0 - out[-1].x1 < limit
                and abs(w.top - out[-1].top) < 0.5):
            previous = out[-1]
            out[-1] = pdf.Word(text=previous.text + w.text,
                               x0=previous.x0, x1=w.x1,
                               top=min(previous.top, w.top),
                               bottom=max(previous.bottom, w.bottom),
                               page=previous.page)
        else:
            out.append(w)
    return out


def class_code(text):
    """A class code expanded, or None. The age is a hint, not an answer."""
    m = CLASS_CODE.match(" ".join(str(text or "").split()).upper())
    if not m:
        return None
    prefix = m.group("prefix")
    if prefix not in PREFIX_GENDER:
        return None
    over = bool(m.group("over1") or m.group("over2"))
    return {"code": " ".join(str(text).split()),
            "gender": PREFIX_GENDER[prefix],
            "age_hint": PREFIX_AGE.get(prefix, ""),
            "weight_kg": m.group("kg"),
            "weight_bound": "over" if over else "under"}


def age_in(text):
    for age, pattern in AGE_WORDS:
        if re.search(pattern, text, re.I):
            return age
    return ""


def heading_code(line):
    """(class code, age class in the same line) for a line that opens a class.

    A code is looked for in two places and nowhere else: at the head of the
    line, which is how Varazze writes it, and at the tail of a running title,
    which is how Slovenia does. Looking anywhere in any line would turn a
    fighter's bib number into a weight class.
    """
    words = [w.text for w in line]
    text = " ".join(words)
    for span in (3, 2, 1):
        found = class_code(" ".join(words[:span]))
        if found:
            return found, age_in(text)
    if re.search(r"result|r[ée]sultat", text, re.I):
        for span in (3, 2, 1):
            found = class_code(" ".join(words[-span:]))
            if found:
                return found, age_in(text)
    return None, ""


def seat_line(line):
    """The seat codes of a grid header line, or None if it is not one.

    Two matching halves are required - A1 A2 A3 A1 A2 A3 - because that is what
    makes the line a POINTS block beside an AVT block rather than a list of
    seats. A class code and the POINTS/AVT captions are allowed in front of the
    seats: Varazze prints "F 70" and the seats on one line, and prints the
    captions on the same line as often as not.
    """
    seats, lead, seen_seat = [], [], False
    for w in line:
        if SLOT.match(w.text):
            seats.append(w)
            seen_seat = True
        elif seen_seat:
            return None                      # something after the seat block
        elif not GRID_HEADERS.match(w.text):
            lead.append(w.text)
    # What may precede the seats is the POINTS/AVT captions and the class code,
    # and nothing else. Varazze prints "F 70" and that class's seat codes on one
    # line, so refusing every line with a word in front of the seats loses a
    # whole weight class; accepting any word would make a bout list into a grid.
    if lead and not class_code(" ".join(lead)):
        return None
    if len(seats) < 4 or len(seats) % 2:
        return None
    half = len(seats) // 2
    if [w.text for w in seats[:half]] != [w.text for w in seats[half:]]:
        return None
    if len({SLOT.match(w.text).group("poule") for w in seats}) != 1:
        return None
    return seats


def _cell(words, drop_seat=True):
    """(name, country) for a name cell, given as its words in x order.

    The country is looked for from the right. It matters: MONACO NOAH FRANCE is
    a French fighter whose surname is also a country, and taking the first
    country in the cell would file him under Monaco and lose his surname.
    """
    keep = [w for w in words if not (drop_seat and SLOT.match(w.text))]
    keep = [w for w in keep if w.text.strip(" .,-–—")]
    if not keep:
        return "", ""
    for i in range(len(keep) - 1, -1, -1):
        if is_country(keep[i].text):
            rest = [w.text for w in keep[:i] + keep[i + 1:]]
            return _dedupe(rest), keep[i].text.strip(" .,")
    for i in range(len(keep) - 1, -1, -1):
        head, tail = split_country(keep[i].text)
        if tail and head:
            rest = [w.text for w in keep]
            rest[i] = head
            return _dedupe(rest), tail.strip(" .,")
    return _dedupe([w.text for w in keep]), ""


def _dedupe(words):
    """'FRANCOISE LOICK FRANCOISE LOICK' -> 'FRANCOISE LOICK'.

    Slovenia's first weight class prints every grid row's name twice, side by
    side. A cell that is exactly its own first half repeated is that half; any
    other repetition is left alone, because a name really can hold the same word
    twice.
    """
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if [_fold(w) for w in words[:half]] == [_fold(w) for w in words[half:]]:
            words = words[:half]
    return " ".join(w.strip(" .,") for w in words if w.strip(" .,"))


class Sheet:
    """One document, cut into weight classes and read grid by grid."""

    def __init__(self, path, report):
        self.report = report
        self.lines = []                  # every line, in reading order
        pages = pdf.by_page(pdf.words(path))
        self.pages = len(pages)
        for number in sorted(pages):
            for line in pdf.rows(pages[number]):
                self.lines.append(mend(line))

    # --- segmentation ---------------------------------------------------
    def classes(self):
        """[class] - one per weight class, in the order the document prints."""
        grids = self._grids()
        by_start = {g["start"]: g for g in grids}

        out, current = [], None
        age, gender_heading = "", ""
        for index, line in enumerate(self.lines):
            text = pdf.text_of(line)
            # The heading is read first, because a line can be both: Varazze
            # prints "F 70" and that class's seat codes on one line, and taking
            # the grid first would file the whole class under the one above it.
            found, line_age = heading_code(line)
            if found:
                age = line_age or age
                if (gender_heading and found["gender"]
                        and found["gender"] != gender_heading):
                    self.report.problem(
                        f"the section heading says {gender_heading} but the "
                        f"class code {found['code']!r} says {found['gender']}; "
                        f"the code is used")
                current = self._open(found, age, out)
                if current["start"] is None:
                    current["start"] = index
                current["end"] = max(current["end"] or index, index)
            if index in by_start:
                grid = by_start[index]
                current = self._place(grid, current, out, age)
                if self._already(current, grid):
                    current["end"] = grid["end"]
                    continue
                current["grids"].append(grid)
                current["end"] = grid["end"]
                continue
            if found:
                continue
            if len(line) <= 2 and age_in(text) and not any(c.isdigit()
                                                           for c in text):
                age = age_in(text)
                continue
            # "Juniors" then "Women" then the classes: the gender heading says
            # the same thing the class codes do, so it is kept as a check on
            # them rather than as the answer.
            if len(line) == 1 and re.fullmatch(r"(men|women|hommes?|femmes?)",
                                               text, re.I):
                gender_heading = next((g for g, pat in norm.GENDERS
                                       if re.search(pat, text, re.I)), "")
                continue
            if current is not None:
                current["end"] = index
        for klass in out:
            self._finish(klass)
        return out

    def _open(self, code, age, out, weight=True):
        """Start a class, or reopen one the document prints twice."""
        key = code["code"] if weight else ("unlabelled", len(out))
        for klass in out:
            if klass["key"] == key:
                return klass
        age = age or code.get("age_hint", "")
        gender = code.get("gender", "")
        parts = [p for p in (age, gender) if p]
        label = " ".join(parts)
        if weight:
            sign = "+" if code["weight_bound"] == "over" else "-"
            label = f"{label} {sign}{code['weight_kg']} kg".strip()
        if not age:
            self.report.problem(f"{label or code.get('code', '?')}: the document "
                                f"names no age class for this weight class")
        klass = {"key": key, "label": label,
                 "fields": {"category": label, "gender": gender,
                            "age_class": age,
                            "weight_kg": code.get("weight_kg", "") if weight else "",
                            "weight_bound": code.get("weight_bound", "") if weight else ""},
                 "grids": [], "roster": {}, "start": None, "end": None}
        out.append(klass)
        return klass

    def _already(self, klass, grid):
        """Is this grid one the class has already been given?

        A document can print the same class twice - the FISav European sheets
        print every class once per language - and a poule read twice gives its
        bouts the same ids twice, which the schema rejects for the whole build.
        Identity is the poule letter and who is in it. A letter that comes back
        with a different roster is not a reprint and is said out loud, because
        its bouts will collide.
        """
        names = frozenset(r["name"] for r in grid["rows"].values())
        for seen in klass["grids"]:
            if seen["poule"] != grid["poule"]:
                continue
            if frozenset(r["name"] for r in seen["rows"].values()) == names:
                return True
            self.report.problem(
                f"{klass['label']}: poule {grid['poule']} is drawn twice with "
                f"different fighters; the second is skipped")
            return True
        return False

    def _place(self, grid, current, out, age):
        """Which class a grid belongs to - possibly one with no heading.

        A grid that repeats a poule letter already used in this class, with a
        roster that shares nobody with it, is not a second poule: it is the
        first poule of a class whose code was left out. Varazze does exactly
        that once, and filing it under the class above would put nine bouts in
        the wrong weight.
        """
        names = {r["name"] for r in grid["rows"].values()}
        if current is None:
            self.report.problem("a poule grid appears before any weight class "
                                "heading; it is read with no class")
            return self._open({"gender": "", "age_hint": ""}, age, out,
                              weight=False)
        letters = {g["poule"] for g in current["grids"]}
        known = {r["name"] for g in current["grids"] for r in g["rows"].values()}
        if grid["poule"] in letters and known and not (names & known):
            self.report.problem(
                f"a poule {grid['poule']} grid with a new roster follows "
                f"{current['label']!r} and carries no class code of its own; "
                f"it is read as a separate class with no weight")
            gender = current["fields"]["gender"]
            return self._open({"gender": gender, "age_hint": ""},
                              current["fields"]["age_class"], out, weight=False)
        return current

    def _finish(self, klass):
        """Fill the class roster, and hand it the lines its bracket is drawn on."""
        for grid in klass["grids"]:
            for seat, row in grid["rows"].items():
                klass["roster"].setdefault(row["name"], row["country"])
        taken = set()
        for grid in klass["grids"]:
            taken |= set(range(grid["start"], grid["end"] + 1))
        start = klass["start"] if klass["start"] is not None else (
            min((g["start"] for g in klass["grids"]), default=0))
        end = klass["end"] if klass["end"] is not None else start
        klass["bracket"] = [(i, self.lines[i]) for i in range(start, end + 1)
                            if i not in taken and self.lines[i]]
        klass["name_column"] = statistics.median(
            [g["name_x"] for g in klass["grids"]]) if klass["grids"] else None
        self._listed(klass)
        # Slovenia's first weight class prints no country in the grid at all,
        # only in the listing beside the drawing. A country read there belongs
        # to the same fighter and is filled in; a country the grid printed is
        # never overwritten.
        for grid in klass["grids"]:
            for row in grid["rows"].values():
                if not row["country"]:
                    row["country"] = klass["roster"].get(row["name"], "")

    def _listed(self, klass):
        """Add the entrants the drawing lists down its left to the roster.

        Both generators reprint the whole class beside the bracket, and that
        listing is sometimes the only place a fighter is named: Varazze's
        unlabelled junior class has a grid that prints one entrant twice and
        never prints the third, who is in the listing and in the final. Reading
        him from there recovers that bout. Only the listing column is read -
        a cell further right is a round, and its occupant is already known.
        """
        labels = _labels(klass["bracket"])
        edge = min((x for x, _ in labels), default=None)
        column = klass.get("name_column")
        for _, line in klass["bracket"]:
            for cell in cells(line):
                x = cell[0].x0
                near = column is not None and abs(x - column) <= 20
                left = edge is not None and x < edge - 1
                if not (near or left):
                    continue
                text = pdf.text_of(cell)
                # The seat code in front of a Slovenian listing entry is part of
                # the listing, not a reason to reject it; any other digit means
                # the cell is a score or a caption.
                body = " ".join(w.text for w in cell if not SLOT.match(w.text))
                if (CHAMPION.match(text) or WINNER_LABEL.match(text)
                        or RUNNERUP_LABEL.match(text)
                        or any(c.isdigit() for c in body)):
                    continue
                name, country = _cell(cell)
                if not country:
                    # Slovenia sets the listing's country in its own column, far
                    # enough from the name to be a separate cell. The first
                    # country to the right of the name, before the next name,
                    # is that fighter's.
                    for w in line:
                        if w.x0 <= cell[-1].x1:
                            continue
                        if is_country(w.text):
                            country = w.text.strip(" .,")
                        break
                if len(name.split()) < 2:
                    continue
                if name in klass["roster"]:
                    if country and not klass["roster"][name]:
                        klass["roster"][name] = country
                    continue
                parts = {_fold(p) for p in name.split()}
                # The same person, spelled a little differently: a fragment of a
                # name already known, or the same letters broken into different
                # words. "QUENEAUDIE MATHIEU" in the grid and "QUENE AUDIE
                # MATHIEU" in the listing are one fighter, and admitting both
                # would split his bouts between two people.
                if any(_fold(name) == _fold(known)
                       or parts <= {_fold(p) for p in known.split()}
                       or {_fold(p) for p in known.split()} <= parts
                       for known in klass["roster"]):
                    continue
                klass["roster"][name] = country

    # --- the grids ------------------------------------------------------
    def _grids(self):
        found = []
        for index, line in enumerate(self.lines):
            seats = seat_line(line)
            if not seats:
                continue
            grid = self._read_grid(index, seats)
            if grid:
                found.append(grid)
        return found

    def _read_grid(self, header, seats):
        """One cross-table: its rows, their scores and their warnings."""
        letter = SLOT.match(seats[0].text).group("poule")
        body, total = [], None
        for index in range(header + 1, min(header + 40, len(self.lines))):
            line = self.lines[index]
            if not line:
                continue
            head = line[0].text.upper()
            if head == "TOTAL":
                total = (index, line)
                break
            if seat_line(line) or heading_code(line)[0]:
                break
            body.append((index, line))
        if total is None:
            self.report.problem(f"poule {letter}: no TOTAL row to calibrate on; "
                                f"the grid is skipped")
            return None

        # Every column is measured from its own seat code, with one offset taken
        # from wherever the TOTAL row and the seats can be lined up. Reading the
        # columns off the TOTAL row directly looks simpler and is wrong: one
        # Varazze row totals "9 4 2 5 , 0 0 2", and a stray comma in the middle
        # of it shifts every warnings column one place to the left.
        columns = len(seats) // 2
        values = [w for w in total[1][1:] if _number(w.text) is not None]
        pairs = [v.x1 - s.x1 for v, s in zip(values, seats[:columns])]
        if pairs:
            offset = statistics.median(pairs)
        else:
            offset = 0.0
            self.report.problem(f"poule {letter}: the TOTAL row carries no "
                                f"values to line the columns up on")
        edges = [w.x1 + offset for w in seats]
        seats = seats[:columns]
        seat_x = total[1][0].x0

        rows, end = {}, total[0]
        for index, line in body:
            tagged = [w for w in line
                      if SLOT.match(w.text) and abs(w.x0 - seat_x) <= 14
                      and SLOT.match(w.text).group("poule") == letter]
            if not tagged:
                continue
            seat = tagged[0].text
            # Words are kept by where they START, not where they end. The name
            # cell wraps and its second line overhangs the seat column -
            # "YAROSLAVA" runs four points past the "A3" beside it - and testing
            # the right edge drops half of every long name.
            name, country = _cell([w for w in line if w.x0 < tagged[0].x0 - 1])
            if not name:
                self.report.problem(f"poule {letter} seat {seat}: no name in "
                                    f"the row; it is skipped")
                continue
            points, warnings = {}, {}
            for w in line:
                if w.x0 <= tagged[0].x1:
                    continue
                value = _number(w.text)
                column = _nearest(w.x1, edges)
                if value is None or column is None:
                    continue
                if column < len(seats):
                    points[seats[column].text] = value
                else:
                    warnings[seats[column - len(seats)].text] = value
            rows[seat] = {"name": name, "country": country,
                          "points": points, "warnings": warnings,
                          "x": min(w.x0 for w in line)}
            end = max(end, index)

        if len(rows) != len(seats):
            self.report.problem(f"poule {letter}: {len(rows)} rows read for "
                                f"{len(seats)} seats")
        self._check_totals(letter, seats, rows, values[:len(seats)])
        return {"poule": letter, "seats": [w.text for w in seats], "rows": rows,
                "start": header, "end": end,
                "name_x": min((r["x"] for r in rows.values()), default=0.0)}

    def _check_totals(self, letter, seats, rows, values):
        """The sheet's own sum, against the columns as this read them.

        A mis-calibrated column produces a complete and entirely wrong poule, so
        the one arithmetic the document does for itself is worth checking.
        """
        for i, seat in enumerate(w.text for w in seats):
            if seat not in rows or i >= len(values):
                continue
            printed = _number(values[i].text)
            mine = sum(rows[seat]["points"].values())
            if printed is not None and mine != printed:
                self.report.problem(
                    f"poule {letter}: {rows[seat]['name']} sums to {mine} but "
                    f"the TOTAL row says {printed}")


def _nearest(x, edges, tolerance=9.0):
    if not edges:
        return None
    best = min(range(len(edges)), key=lambda i: abs(x - edges[i]))
    return best if abs(x - edges[best]) <= tolerance else None


# --- rows ---------------------------------------------------------------
def poule_bouts(klass, grid, slug, index, report):
    rows, out = grid["rows"], []
    seats = [s for s in grid["seats"] if s in rows]
    by_name = {}
    for seat in seats:
        by_name.setdefault(_fold(rows[seat]["name"]), []).append(seat)
    doubled = [s for group in by_name.values() if len(group) > 1 for s in group]
    if doubled:
        report.problem(
            f"{klass['label']} poule {grid['poule']}: "
            f"{rows[doubled[0]]['name']} is printed in two seats "
            f"({', '.join(doubled)}); the poule cannot be read and is dropped")
        return []

    seen = set()
    for a in seats:
        for b in seats:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            a_points = rows[a]["points"].get(b)
            b_points = rows[b]["points"].get(a)
            if a_points is None and b_points is None:
                continue                      # these two did not meet
            a_warnings = rows[a]["warnings"].get(b, 0)
            b_warnings = rows[b]["warnings"].get(a, 0)
            # A win scores 3 in this system, always. Where neither corner has
            # three the bout is left unresolved however the two numbers compare:
            # Varazze prints one bout 1-0 and several 1-1, and calling the
            # larger of two losing scores a victory would invent a result out of
            # a sheet its own author did not finish.
            top = max(a_points or 0, b_points or 0)
            higher = ""
            if top == rules.WIN:
                higher = ("a" if (a_points or 0) > (b_points or 0) else
                          "b" if (b_points or 0) > (a_points or 0) else "")
            won = max(a_points or 0, b_points or 0)
            lost = min(a_points or 0, b_points or 0)
            loser_warnings = b_warnings if higher == "a" else a_warnings
            decision = rules.decision_from_points(won, lost, loser_warnings)
            if not higher and a_points == b_points == rules.WIN:
                # Both corners on a win's points is how these sheets write a
                # draw, and a draw scores 3 apiece (the FISav worksheets print
                # the scale). It is a result with no winner, which is a state
                # the schema has: decided means a winner is known.
                decision = "draw"
            elif higher and not decision or (not higher and not decision):
                report.problem(
                    f"{klass['label']} poule {grid['poule']}: "
                    f"{rows[a]['name']} {a_points}-{b_points} {rows[b]['name']} "
                    f"is a scoreline the rules do not describe")
            winner = rows[a]["name"] if higher == "a" else \
                rows[b]["name"] if higher == "b" else ""
            loser = rows[b]["name"] if higher == "a" else \
                rows[a]["name"] if higher == "b" else ""
            out.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-{index:02d}{grid['poule']}-{a}{b}",
                phase="poule", poule=grid["poule"],
                red=rows[a]["name"], red_country=rows[a]["country"],
                blue=rows[b]["name"], blue_country=rows[b]["country"],
                red_points="" if a_points is None else str(a_points),
                blue_points="" if b_points is None else str(b_points),
                red_warnings=str(a_warnings), blue_warnings=str(b_warnings),
                # The sheet says who scored what. It never says who stood in
                # which corner, so no corner is named.
                winner_corner="",
                winner=winner, loser=loser, decision=decision,
                status="decided" if winner else "unresolved",
                result_source="reported" if winner else "",
                **klass["fields"]))
    return out


def cells(line, spread=3.0):
    """Split a line into the cells it was printed as, on the gaps between them.

    A line of a bracket holds the same fighter twice - once in the listing down
    the left, once in the round they reached - and a reader that scans the whole
    line for names sees the first and consumes the second. The gap that ends a
    cell is measured against the line's own character pitch for the same reason
    `mend` is: the documents change font size from page to page.
    """
    pitch = _pitch(line)
    limit = spread * pitch if pitch > 0 else 20.0
    out = []
    for w in sorted(line, key=lambda w: w.x0):
        if out and w.x0 - out[-1][-1].x1 <= limit:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _sightings(lines, roster):
    """[(x, top, fighter)] - every place a roster name is printed.

    Matched three ways, longest window first: the words of a cell as they stand,
    the same words with their separators removed (which survives a name the
    extractor broke differently on two pages), and a token subset that fits one
    roster name and no other. A fragment that fits two fighters is dropped,
    because putting the wrong fighter in a round invents a result.
    """
    exact, squashed, tokens = {}, {}, {}
    for name in roster:
        parts = frozenset(_fold(p) for p in name.split() if _fold(p))
        exact.setdefault(parts, name)
        squashed.setdefault(_fold(name), name)
        tokens[name] = parts

    def pieces(chunk):
        """The words of a cell as name tokens: countries dropped, fusions cut."""
        got = []
        for w in chunk:
            if SLOT.match(w.text) or is_country(w.text):
                continue
            head, tail = split_country(w.text)
            text = _fold(head if tail and head else w.text)
            if text:
                got.append(text)
        return got

    out = []
    for _, line in lines:
        for cell in cells(line):
            words = [w for w in cell if not SLOT.match(w.text)]
            i = 0
            while i < len(words):
                hit, span = None, 0
                for size in range(len(words) - i, 0, -1):
                    got = pieces(words[i:i + size])
                    if not got:
                        continue
                    if frozenset(got) in exact:
                        hit, span = exact[frozenset(got)], size
                        break
                    if "".join(got) in squashed:
                        hit, span = squashed["".join(got)], size
                        break
                if hit is None:
                    for size in range(len(words) - i, 0, -1):
                        got = frozenset(pieces(words[i:i + size]))
                        if not got:
                            continue
                        fits = [n for n, t in tokens.items() if got <= t]
                        if len(fits) == 1:
                            hit, span = fits[0], size
                            break
                if hit is None:
                    i += 1
                    continue
                out.append((words[i].x0, words[i].top, hit))
                i += span
    return out


def _columns(sightings, gap=60.0):
    columns, current = [], []
    for x, top, name in sorted(sightings):
        if current and x - current[-1][0] > gap:
            columns.append(current)
            current = []
        current.append((x, top, name))
    if current:
        columns.append(current)
    return columns


def _labels(lines):
    """[(x, top)] for every 'Vainqueur A' / '2nd Groups B' box."""
    out = []
    for _, line in lines:
        for i, w in enumerate(line):
            tail = " ".join(x.text for x in line[i:i + 3])
            if WINNER_LABEL.match(tail) or RUNNERUP_LABEL.match(tail):
                out.append((w.x0, w.top))
    return out


def _champion(lines, roster):
    """The fighter the CHAMPION box names, or "".

    Varazze prints the box's name on the line above the word and Slovenia prints
    it in the right-hand column, so only the first is looked for here - the
    second falls out of the column reading. The name must be within a line's
    height of the word: a class whose box was left empty has the last row of its
    bracket forty points above, and taking that would hand five championships to
    the wrong fighter.
    """
    numbered = {i: line for i, line in lines}
    for index, line in lines:
        if len(line) != 1 or not CHAMPION.match(line[0].text):
            continue
        above = [i for i in numbered if i < index]
        if not above:
            continue
        previous = numbered[max(above)]
        if line[0].top - previous[0].top > 25:
            continue
        seen = _sightings([(0, previous)], roster)
        if len({name for _, _, name in seen}) == 1:
            return seen[0][2]
    return ""


def bracket_bouts(klass, slug, index, report):
    """The knockout, from the columns of printed names."""
    lines, roster = klass["bracket"], klass["roster"]
    if not roster:
        return []
    columns = _columns(_sightings(lines, roster))
    labels = _labels(lines)
    columns = _drop_listing(columns, labels, klass)
    if not columns:
        return []

    champion = _champion(lines, roster)
    if len(_unique(columns[-1])) == 1 and len(columns) > 1:
        drawn = _unique(columns[-1])[0]
        if champion and champion != drawn:
            report.problem(f"{klass['label']}: the CHAMPION box names "
                           f"{champion!r} but the bracket ends with {drawn!r}")
        champion = champion or drawn
        columns = columns[:-1]

    out = []
    for depth, column in enumerate(columns):
        entries = _unique(column)
        phase = PHASES_FROM_RIGHT[len(columns) - 1 - depth] \
            if len(columns) - 1 - depth < len(PHASES_FROM_RIGHT) else ""
        if len(entries) % 2:
            report.problem(f"{klass['label']} {phase or 'knockout'}: "
                           f"{len(entries)} fighters cannot be paired; the "
                           f"column is skipped")
            continue
        forward = ({n for _, _, n in columns[depth + 1]}
                   if depth + 1 < len(columns) else set())
        for n, (a, b) in enumerate(zip(entries[::2], entries[1::2]), 1):
            winner = ""
            source = ""
            if a in forward or b in forward:
                winner = a if a in forward else b
                source = "inferred"      # deduced from the next round, not read
            elif champion in (a, b):
                winner = champion
                source = "reported"      # the CHAMPION box states it
            if not winner:
                report.problem(f"{klass['label']} {phase or 'knockout'}: "
                               f"neither {a} nor {b} is named again, so the "
                               f"bout is left unresolved")
            out.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-{index:02d}-{phase or 'ko'}{n:02d}",
                phase=phase,
                red=a, red_country=roster.get(a, ""),
                blue=b, blue_country=roster.get(b, ""),
                winner_corner="",
                winner=winner,
                loser=({a, b} - {winner}).pop() if winner else "",
                status="decided" if winner else "unresolved",
                result_source=source,
                **klass["fields"]))
    return out


def _unique(column):
    """The names of a column, top to bottom, each once."""
    seen, out = set(), []
    for _, _, name in sorted(column, key=lambda s: s[1]):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _drop_listing(columns, labels, klass):
    """Drop the column that re-lists the poule entries rather than a round.

    Both generators reprint the whole class down the left of the drawing. It is
    a roster, not a round, and pairing it would invent a bout between everyone
    who entered.
    """
    if not columns:
        return columns
    first = columns[0][0][0]
    name_column = klass.get("name_column")
    if labels and first < min(x for x, _ in labels) - 1:
        return columns[1:]
    if name_column is not None and abs(first - name_column) <= 15:
        return columns[1:]
    return columns


def medal_placings(klass, lines, slug, index, report):
    """Placings from the small gold/silver/bronze table some classes carry.

    A class with two entrants gets no grid at all - Varazze prints "Number of
    registered : 2" and the two medallists. It is a podium and is kept as one:
    the bout that decided it is not written down, and inventing it would be
    fabrication.
    """
    out = []
    for _, line in lines:
        if len(line) < 2:
            continue
        medal_word = line[-1].text.strip(" .,").lower()
        rank = MEDAL_WORDS.get(medal_word)
        if not rank:
            continue
        name, country = _cell(line[:-1])
        if not name:
            report.problem(f"{klass['label']}: a {medal_word} line with no name")
            continue
        out.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{index:02d}-p{rank}",
            rank=rank, medal=MEDALS[rank],
            fighter=name, country=country,
            result_source="reported",
            **{k: v for k, v in klass["fields"].items()}))
    return out


def _brief(error):
    """One line of an exception. pdftotext answers a non-PDF with pages of
    syntax errors, and a report is for reading."""
    text = " ".join(str(error).split())
    return text[:200] + ("..." if len(text) > 200 else "")


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) from one CESav poule-grid sheet."""
    from savate import sources

    report = Report(source=str(source), adapter=NAME)
    try:
        path = (sources.fetch_archived(str(source)) if options.get("archived")
                else sources.fetch(source, refresh=options.get("refresh", False)))
    except Exception as e:                    # a source that will not arrive
        report.problem(f"could not fetch {source}: {_brief(e)}")
        return Tournament(slug=slug, source=str(source), adapter=NAME,
                          **(meta or {})), [], report

    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))
    try:
        sheet = Sheet(path, report)
        classes = sheet.classes()
    except Exception as e:
        report.problem(f"{path} could not be read as a poule-grid "
                       f"sheet: {_brief(e)}")
        report.notes["kind"] = "unreadable - probably not this layout"
        return tournament, [], report

    report.read = sheet.pages
    report.notes["weight_classes"] = len(classes)

    rows = []
    for index, klass in enumerate(classes, 1):
        before = len(rows)
        for grid in klass["grids"]:
            rows.extend(poule_bouts(klass, grid, slug, index, report))
        rows.extend(bracket_bouts(klass, slug, index, report))
        rows.extend(medal_placings(klass, klass.get("bracket", []), slug,
                                   index, report))
        if len(rows) == before:
            report.problem(f"{klass['label']}: no readable rows")

    kept = []
    for row in rows:
        bad = check(row) if isinstance(row, Bout) else check_placing(row)
        if bad:
            report.problem(f"{getattr(row, 'bout_id', '') or row.placing_id}: "
                           f"{'; '.join(bad)}; the row is dropped")
            continue
        kept.append(row)

    # These sheets never name a corner, so `decided` counted on winner_corner is
    # zero by design. The count that matters is said here instead.
    report.notes["decided_by_name"] = sum(
        1 for r in kept if isinstance(r, Bout) and r.winner)
    if not kept:
        report.notes["kind"] = "no rows found - probably not this layout"
    return tournament, kept, report
