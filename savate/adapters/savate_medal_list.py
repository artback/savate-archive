"""Adapter for documents whose whole content is a podium: who medalled, where.

A podium is not a bout, and this adapter never pretends otherwise - it yields
`Placing` rows and nothing else. What links the documents it reads is not their
typography but their claim: each one names a medallist, a place and a weight
class, and says nothing about who beat whom. Inventing the bouts behind a
podium would be fabrication, so the bouts are simply not there.

Three printings of that same claim are recognised. They look nothing alike, and
a single line-oriented parser reads none of them, because in all three the fact
that carries the meaning is *which column a word sits in* - so all three are
read through poppler's word geometry rather than through extracted text.

1. THE MEDAL GRID  (CESav / savate-srbija.com, and the FISav championships they
   host: European 2019 and 2023, World 2024, World Cup Jeune 2017)

       Poids      OR / GOLD          ARGENT / SILVER      BRONZE        BRONZE
                              Seniors Masculins / Men
       M60    LAURENT MEDHI (FRANCE)   NOKAJ ALEN (CROATIA)   ...

   One row per weight class, four medal columns, and gender/age printed as a
   band heading across the table. Savate awards TWO bronzes, which is why the
   grid has two bronze columns and why two rank-3 rows per class are correct
   rather than a duplicate.

   The four columns are found from the header words, but how a word is assigned
   to one of them depends on how the sheet is set, and the two settings need
   opposite rules:

     * Centred cells (2017, 2023, 2024). The text of a cell is centred under
       its heading and spills to the left of it - "GOVINDAMA CHRISTOPHE
       (FRANCE)" starts 43pt left of the word "GOLD" it belongs to. Bands
       running from one heading to the next therefore lose the first word of
       every cell. Each word is assigned to the heading whose CENTRE is
       nearest, which is exactly what centring means.
     * Left-aligned cells (Gênes 2019). Here the country has a column of its
       own, and its left edge sits nearer the next medal's centre than its own
       - nearest-centre files every country under the following medal. Bands
       running from one heading's left edge to the next are correct instead,
       and the country is split off inside the band at the leftmost position
       the band's last word ever takes.

   Which of the two is in force is not guessed: if no word in the table starts
   left of the first heading, the sheet is left-aligned; otherwise it is
   centred. Both readings are checked against the documents in the archive.

2. THE CROATIAN FEDERATION REPORT  (dtournament.icebits.hr, printed by the
   Croatian savate federation for every national championship, cup and open)

       UZRAST              KATEGORIJA   KLUB              IME            REZULTAT
       Assaut - Mlađi kadeti
                           -25 kg
                                        SK KOBRA          Sebastian Ratkajec   1.
                                        SK ŠAN GAREŠNICA  Hrvoje Jambrek       2.

   Five columns whose x positions are declared by a header line that repeats on
   every page. Age class and discipline come from the UZRAST heading, weight
   from KATEGORIJA, and the place is a bare ordinal in REZULTAT. These are the
   only documents in this family that publish a competitor's CLUB, and a long
   club name wraps onto the lines above and below the competitor's own, which
   is why the club is gathered from the neighbouring club-only lines too.

   Each file also carries a second table, "Rezulatati po klubovima", ranking
   the CLUBS by medals won. That is a different fact about different subjects
   and is deliberately not read: parsing stops when that heading appears.

   These reports place every entrant, not only the podium - fourth through
   ninth are printed the same way. `Placing` has no room for them (a placing is
   a medal), so they are counted and reported rather than dropped in silence.

   The headings are Croatian and the archive is not, so they are translated:
   mlađi/mlađe = younger, stariji/starije = older, kadeti/kadetkinje = cadets,
   juniori/juniorke = juniors, seniori/seniorke = seniors, and the -i/-ke
   ending is what states the gender. The translation is recorded in the report
   so that the original wording is never lost behind it.

3. THE MEDALLISTS-BY-EVENT TABLE  (SportAccord World Combat Games 2013)

       Event                  Date         Medal    Name                  Code
       Women's Assaut -52kg   SUN 20 OCT   GOLD     POPADIC Ivana         SRB
                                           SILVER   TROUILLET Marion      FRA

   One event per block, the event named only on its first line. Its canne de
   combat events are skipped: canne is a different sport with its own
   federation structure, and filing it beside savate weight classes would put
   two sports in one table.

WHAT IS NOT FILLED IN. A country the document does not print stays empty - the
Croatian reports name clubs and never nationalities, and a club in Graz at a
Croatian open is not a Croatian competitor. A three-letter all-capitals country
is kept exactly as printed: it is an IOC code, and running "SRB" through the
country table would produce "Srb", which is neither the code nor the name.

WHAT IS TURNED AWAY. Three kinds of document sit next to these and are refused,
each for the same reason - the rows they would yield would not be the rows they
claim to be. A medal table by nation ("FRANCE 1° 13 ... 40 points") counts
medals without naming a single medallist, so there is no Placing in it at all.
A canne de combat sheet is another sport. And a bout sheet with corners and
verdicts is a record of who beat whom, which is a Bout and belongs to an
adapter that reads bouts. All three leave with a reported reason and no rows.
"""

import re

from savate import normalize as norm
from savate import pdf
from savate.schema import MEDALS, Placing, Report, Tournament, TOURNAMENT_FIELDS

NAME = "savate_medal_list"
DESCRIPTION = "medal / podium documents (CESav grids, Croatian reports, medallist tables)"

# Every dash a federation's typesetter has reached for, flattened to one.
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})

# Gender, women first: "women" contains "men", so the male pattern would claim
# every women's section if it were tried first. Same reason as normalize.py.
_GENDERS = [
    ("Women", r"f[ée]minin|femmes?|\bwomen\b|\bgirls?\b|\bfilles?\b|\bdames?\b"),
    ("Men", r"masculins?|hommes?|\bmen\b|\bboys?\b|\bgar[cç]ons?\b"),
]
_AGE_WORD = re.compile(r"seniors?|juniors?|cadets?|v[ée]t[ée]rans?|espoirs?|"
                       r"jeunes?|young|youth|minimes?|benjamins?", re.I)
# The sheets are written in French and English by turns, and the archive keeps
# one vocabulary. Only the wordings actually seen are mapped; anything else is
# kept as the document printed it rather than guessed at.
_AGE_IN_ENGLISH = {"jeune": "Young", "jeunes": "Young", "seniors": "Senior",
                   "juniors": "Junior", "cadets": "Cadet", "espoir": "Young",
                   "espoirs": "Young", "vétéran": "Veteran",
                   "vétérans": "Veteran", "veterans": "Veteran",
                   "minimes": "Minime", "benjamins": "Benjamin",
                   "youth": "Young"}

# A weight class as any of these documents codes it: "M56", "M+85", "G 45-48",
# "-48 kg", "48-52", "+75 kg", "-52kg". The optional leading letter is the
# sheet's own gender prefix, which the band heading states anyway.
_WEIGHT = re.compile(r"^(?P<prefix>[A-Za-z]{0,2})\s*(?P<sign>[-+])?\s*"
                     r"(?P<low>\d{2,3})(?:\s*-\s*(?P<high>\d{2,3}))?"
                     r"\s*(?:kg|kgs)?$", re.I)


def _flat(text):
    """One line of text, dashes unified and whitespace collapsed."""
    return " ".join(str(text or "").translate(_DASHES).split())


# Unicode decomposition does not touch a letter that is one glyph rather than
# a letter plus a mark, so norm.fold leaves Croatian "đ" alone and "Mlađi" never
# matches a stem written "mladi". Without this, the younger cadets and the
# cadets both come out labelled "Cadet" and two separate competitions inside
# one file merge into one category.
_STROKES = str.maketrans({"đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                          "ø": "o", "Ø": "O"})


def _fold(text):
    return norm.fold(str(text or "").translate(_STROKES))


def _gender_of(text):
    for gender, pattern in _GENDERS:
        if re.search(pattern, text, re.I):
            return gender
    return ""


def _age_of(text):
    found = _AGE_WORD.search(text)
    return found.group(0).title() if found else ""


def _country(text):
    """A country as the document printed it, mapped to the archive's spelling.

    A three-letter all-capitals token is an IOC code and is kept verbatim:
    title-casing "SRB" yields "Srb", which is neither the code nor a country.
    """
    text = _flat(text)
    if re.fullmatch(r"[A-Z]{3}", text):
        return text
    return norm.country(text)


def _weight(text):
    """{weight_kg, weight_bound, printed} for a class code, or None.

    A band such as "45-48" is an upper bound written as two numbers; the class
    is the upper one, and the band is kept as printed so the lower number is
    not thrown away.
    """
    text = _flat(text)
    if not text:
        return None
    found = _WEIGHT.match(text)
    if not found or not found.group("low"):
        return None
    # A bare number is not a weight class. Every one of these federations
    # writes a sign, a band, the unit or its own gender prefix, and the 2019
    # sheet opens each row with the number of entrants present - read as a
    # class, that "10" becomes "-10 kg" and shunts the whole row one column
    # sideways, which is how a silver ends up filed as a gold.
    if not any(found.group(g) for g in ("prefix", "sign", "high")) \
            and not re.search(r"kgs?$", text, re.I):
        return None
    if found.group("high"):
        return {"weight_kg": found.group("high"), "weight_bound": "under",
                "printed": f"{found.group('low')}-{found.group('high')} kg"}
    sign = found.group("sign") or "-"
    return {"weight_kg": found.group("low"),
            "weight_bound": "over" if sign == "+" else "under",
            "printed": f"{sign}{found.group('low')} kg"}


class _Sheet:
    """Placings accumulated from one document, with their ids and duplicates."""

    def __init__(self, slug, report):
        self.slug = slug
        self.report = report
        self.rows = []
        self._seen = set()

    def add(self, rank, fighter, klass, country="", club=""):
        fighter = _flat(fighter)
        if not fighter:
            self.report.problem(
                f"{klass['category']}: a {MEDALS[rank]} with no name")
            return
        key = (klass["category"], rank, norm.fold(fighter))
        if key in self._seen:
            return
        self._seen.add(key)
        self.rows.append(Placing(
            tournament=self.slug,
            placing_id=f"{self.slug}-{len(self.rows) + 1:04d}",
            category=klass["category"], gender=klass["gender"],
            age_class=klass["age_class"], weight_kg=klass["weight_kg"],
            weight_bound=klass["weight_bound"],
            rank=rank, medal=MEDALS[rank],
            fighter=fighter, country=_country(country), club=_flat(club),
            result_source="reported",
        ))


# --------------------------------------------------------------------------
# 1. The medal grid
# --------------------------------------------------------------------------

_MEDAL_WORD = [(re.compile(r"^(or|gold)$", re.I), "1"),
               (re.compile(r"^(argent|silver)$", re.I), "2"),
               (re.compile(r"^bronze$", re.I), "3")]
# A cell holding this is a place nobody took. The 2017 sheet prints it where a
# bronze was not awarded; it is not a competitor and must not become one. It is
# looked for token by token because one such cell has a stray "zz" left beside
# it, and a whole-string test would let "XXXXX zz" through as a medallist.
_EMPTY_CELL = re.compile(r"^[xX]{3,}$")


def _unawarded(name):
    return any(_EMPTY_CELL.match(token) for token in _flat(name).split())


def _medal_word(word):
    for pattern, rank in _MEDAL_WORD:
        if pattern.match(word.text):
            return rank
    return ""


def _grid_header(line):
    """[(rank, x0, x1)] for the four medal headings on a line, or None.

    A new heading starts at a medal word that is separated from what precedes
    it. Without the gap test the second BRONZE joins the first, because it is
    the same word - and two bronze columns is the whole point of the layout.
    """
    groups, started = [], False
    for word in line:
        rank = _medal_word(word)
        if rank and (not groups or word.x0 - groups[-1][2] > 20):
            groups.append([rank, word.x0, word.x1])
            started = True
            continue
        if not started:
            continue          # "poids", "présents": labels before the medals
        if rank or word.text in ("/", "-", "|"):
            groups[-1][2] = max(groups[-1][2], word.x1)
            continue
        return None           # anything else after the medals: not a heading
    if [g[0] for g in groups] != ["1", "2", "3", "3"]:
        return None
    return [tuple(g) for g in groups]


def _lead_weight(line, limit):
    """(class, words consumed) if a line opens with a weight code, else None.

    The 2019 sheet prefixes each row with the number of entrants present, so a
    code is looked for at the first word and, when that first word is a bare
    small integer, at the second. Longest match wins, so "-48" and "kg" are one
    code rather than a code followed by a stray unit.
    """
    for start in (0, 1):
        if start and not re.fullmatch(r"\d{1,2}", line[0].text):
            break
        for length in (3, 2, 1):
            end = start + length
            if end > len(line) or line[end - 1].x1 > limit:
                continue
            found = _weight(" ".join(w.text for w in line[start:end]))
            if found:
                return found, end
    return None, 0


def _split_cell(text):
    """(name, country) for a grid cell: "NAME (COUNTRY)" or "NAME - COUNTRY"."""
    text = _flat(text)
    paren = re.search(r"\(([^()]*)\)\s*$", text)
    if paren:
        return text[:paren.start()].strip(), paren.group(1).strip()
    dashed = list(re.finditer(r"-\s+", text))
    if dashed:
        last = dashed[-1]
        return text[:last.start()].strip(), text[last.end():].strip()
    return text, ""


def _read_grid(lines, sheet, meta, report):
    header = next((_grid_header(l) for l in lines if _grid_header(l)), None)
    ranks = [g[0] for g in header]
    starts = [g[1] for g in header]
    centres = [(g[1] + g[2]) / 2 for g in header]
    weight_limit = starts[0]

    # Every data word in the table, so the alignment can be settled once.
    body = []
    for line in lines:
        klass, used = _lead_weight(line, weight_limit)
        if klass:
            body.append((klass, line[used:]))
    if not body:
        report.problem("the grid has a medal heading but no weight-class rows")
        return
    # One set of edges, used by every test below. A heading and the column it
    # heads are typeset to the same nominal position but not to the same float
    # - the 2019 sheet's "argent" starts 0.0013pt right of the names under it -
    # so the slack belongs in the edges themselves rather than in each caller,
    # where two callers rounded it differently and split one cell in two.
    edges = [x - 4 for x in starts] + [float("inf")]

    def column(word):
        return max(i for i in range(len(starts)) if word.x0 >= edges[i])

    left_aligned = min((w.x0 for _k, rest in body for w in rest),
                       default=starts[0]) >= edges[0]
    report.notes["grid_alignment"] = "left" if left_aligned else "centred"

    # Left-aligned sheets put the country in its own sub-column. Its position
    # is the leftmost a band's final word ever takes, which no name reaches.
    country_x = {}
    if left_aligned:
        for index in range(len(starts)):
            lasts = []
            for _klass, rest in body:
                cell = [w for w in rest if column(w) == index]
                if len(cell) > 1:
                    lasts.append(cell[-1].x0)
            country_x[index] = min(lasts) if lasts else float("inf")

    # The age class may be stated once in the title rather than on each band -
    # "Coupe du Monde Jeune 13 et 14 ans" heads the 2017 sheet and no band
    # repeats it - so the matter above the medal heading is read for one, and
    # a band heading that names its own overrides it.
    titled = ""
    for line in lines:
        if _grid_header(line):
            break
        titled = titled or _age_of(_flat(pdf.text_of(line)))
    fallback = _AGE_IN_ENGLISH.get(titled.lower(), titled) \
        or _flat(meta.get("age_class", ""))
    if titled:
        report.notes["age_from_title"] = titled

    gender, age = "", fallback
    skipped = 0
    for line in lines:
        klass, used = _lead_weight(line, weight_limit)
        if not klass:
            text = _flat(pdf.text_of(line))
            if len(text) <= 40 and _gender_of(text):
                gender = _gender_of(text)
                found = _age_of(text)
                age = _AGE_IN_ENGLISH.get(found.lower(), found) or fallback
            continue
        rest = line[used:]
        if not rest:
            continue          # a class printed with no medals awarded
        if not gender:
            skipped += 1
            continue
        cells = {}
        for word in rest:
            if left_aligned:
                index = column(word)
            else:
                index = min(range(len(centres)),
                            key=lambda i: abs(word.middle - centres[i]))
            cells.setdefault(index, []).append(word)
        label = " ".join(x for x in [_flat(meta.get("discipline", "")).title(),
                                     age, gender, klass["printed"]] if x)
        shaped = {"category": label, "gender": gender, "age_class": age,
                  "weight_kg": klass["weight_kg"],
                  "weight_bound": klass["weight_bound"]}
        for index, words in sorted(cells.items()):
            if left_aligned:
                edge = country_x[index]
                name = " ".join(w.text for w in words if w.x0 < edge)
                country = " ".join(w.text for w in words if w.x0 >= edge)
            else:
                name, country = _split_cell(" ".join(w.text for w in words))
            if _unawarded(name) or not _flat(name):
                continue
            sheet.add(ranks[index], name, shaped, country=country)
    if skipped:
        report.problem(f"{skipped} weight-class row(s) printed before any "
                       f"gender heading, so their category cannot be named")


# --------------------------------------------------------------------------
# 2. The Croatian federation report
# --------------------------------------------------------------------------

_HR_HEADER = ["UZRAST", "KATEGORIJA", "KLUB", "IME", "REZULTAT"]
# The second table in the same file ranks clubs, not competitors.
_HR_CLUB_TABLE = re.compile(r"po\s+klubovima|poredak", re.I)
_HR_DISCIPLINE = re.compile(r"^(assaut|precombat|combat)\b")
_HR_RANK = re.compile(r"^(\d{1,2})\.$")
# Croatian states the age class and the gender in one word: the -i ending is
# masculine, -ke/-kinje feminine. Longer stems first, or "kadeti" swallows
# "kadetkinje".
_HR_AGE = [("kadetkinje", "Cadet", "Women"), ("kadetkinja", "Cadet", "Women"),
           ("kadeti", "Cadet", "Men"), ("kadet", "Cadet", "Men"),
           ("juniorke", "Junior", "Women"), ("juniorka", "Junior", "Women"),
           ("juniori", "Junior", "Men"), ("junior", "Junior", "Men"),
           ("seniorke", "Senior", "Women"), ("seniorka", "Senior", "Women"),
           ("seniori", "Senior", "Men"), ("senior", "Senior", "Men"),
           ("veteranke", "Veteran", "Women"), ("veterani", "Veteran", "Men")]
_HR_QUALIFIER = [("mladi", "Younger"), ("mlade", "Younger"),
                 ("stariji", "Older"), ("starije", "Older")]


def _hr_class(heading, report):
    """A weightless class from an UZRAST heading, or None if it is unreadable.

    None is not an error on its own. A heading wraps - "Assaut - Mlađe" on one
    line and "kadetkinje" on the next - so the caller keeps feeding it the
    growing text, and only a competitor arriving with no class resolved means
    something was actually missed.
    """
    folded = _fold(_flat(heading))
    if not _HR_DISCIPLINE.match(folded):
        return None
    discipline = _HR_DISCIPLINE.match(folded).group(1).title()
    age = gender = ""
    for stem, name, who in _HR_AGE:
        if stem in folded:
            age, gender = name, who
            break
    if not age:
        return None
    qualifier = next((q for stem, q in _HR_QUALIFIER if stem in folded), "")
    report.notes.setdefault("headings", {})[_flat(heading)] = \
        " ".join(x for x in (discipline, qualifier, age, gender) if x)
    return {"discipline": discipline, "gender": gender,
            "age_class": " ".join(x for x in (qualifier, age) if x)}


def _read_croatian(lines, sheet, report):
    anchors, active = None, False
    entries = []                       # (kind, banded words) in reading order

    def band(line, index):
        left = anchors[index] - 2
        right = anchors[index + 1] - 2 if index + 1 < len(anchors) else float("inf")
        return [w for w in line if left <= w.x0 < right]

    for line in lines:
        texts = [w.text for w in line]
        if texts == _HR_HEADER:
            anchors, active = [w.x0 for w in line], True
            continue
        if _HR_CLUB_TABLE.search(pdf.text_of(line)):
            active = False
            continue
        if not active:
            continue
        cells = [band(line, i) for i in range(5)]
        entries.append(cells)

    heading, klass, weight = [], None, None
    below_podium, unreadable = 0, set()
    for index, cells in enumerate(entries):
        age_words, weight_words, club_words, name_words, rank_words = cells
        rank = _HR_RANK.match(pdf.text_of(rank_words)) if rank_words else None
        name = _flat(pdf.text_of(name_words))

        if rank:
            if rank.group(1) not in MEDALS:
                below_podium += 1
                continue
            # Long text wraps around the line that carries the place: the head
            # sits on the line above and the tail on the line below, with
            # nothing else on either. Club names do this constantly, and so do
            # the occasional three-part name - "Petar Vučemilović" / "Grgić" -
            # whose medal would otherwise vanish without a word said.
            if not name:
                name = _wrapped(entries, index, 3)
            club = _flat(pdf.text_of(club_words)) or _wrapped(entries, index, 2)
            if klass is None or weight is None:
                unreadable.add(_flat(" ".join(heading)) or "(no heading)")
                continue
            label = " ".join([klass["discipline"], klass["age_class"],
                              klass["gender"], weight["printed"]])
            sheet.add(rank.group(1), name, {
                "category": label, "gender": klass["gender"],
                "age_class": klass["age_class"],
                "weight_kg": weight["weight_kg"],
                "weight_bound": weight["weight_bound"]}, club=club)
            continue

        if weight_words and not (club_words or name_words or rank_words):
            found = _weight(pdf.text_of(weight_words))
            if found:
                weight = found
            continue

        if age_words and not any(cells[1:]):
            text = _flat(pdf.text_of(age_words))
            if _HR_DISCIPLINE.match(_fold(text)):
                # A new section opens. The previous class must go immediately,
                # before the new heading has even been read in full: keeping it
                # one line longer would file this section's first competitors
                # under the last section's age class and gender.
                heading, klass, weight = [text], None, None
            elif heading and klass is None:
                heading.append(text)
            else:
                continue
            found = _hr_class(" ".join(heading), report)
            if found:
                klass, weight = found, None

    if below_podium:
        report.problem(f"{below_podium} placing(s) of fourth or lower are "
                       f"printed and not kept: a Placing is a medal, and the "
                       f"archive has nowhere to record a fifth place")
    for text in sorted(unreadable):
        report.problem(f"competitors skipped under heading {text!r}: neither "
                       f"an age class nor a weight could be read from it")
    # Two headings that come out with one label have merged two competitions,
    # which is invisible in the rows and fatal to every reader that keys on the
    # category. It is cheap to notice here and impossible to notice later.
    labels = {}
    for heading, label in report.notes.get("headings", {}).items():
        labels.setdefault(label, []).append(heading)
    for label, headings in labels.items():
        if len(headings) > 1:
            report.problem(f"headings {', '.join(map(repr, headings))} all "
                           f"read as {label!r}: two sections of this file are "
                           f"being filed as one category")
    report.notes["below_podium"] = below_podium


def _wrapped(entries, index, column):
    """Text spilled into `column` on the lines either side of `index`.

    A neighbour counts as spill when it carries no place of its own: every
    competitor in these reports has one, so a line in the results table with no
    ordinal is not a competitor but the overflow of the line beside it. Both
    the club and the name wrap, sometimes on the same pair of lines - "SK
    'SILVER EAGLE' / Silvio", then the place alone, then "RUGVICA /
    Cvjetanović" - so the test cannot demand that the neighbour hold nothing
    else.
    """
    parts = []
    for step in (-1, 1):
        neighbour = index + step
        if 0 <= neighbour < len(entries) and _spill(entries[neighbour], column):
            parts.append(pdf.text_of(entries[neighbour][column]))
    return _flat(" ".join(parts))


def _spill(cells, column):
    return bool(cells[column]) and not _HR_RANK.match(_flat(pdf.text_of(cells[4])))


# --------------------------------------------------------------------------
# 3. The medallists-by-event table
# --------------------------------------------------------------------------

_EVENT_HEADER = ["Event", "Date", "Medal", "Name"]
_EVENT = re.compile(r"^(?P<who>men|women)'s\s+(?P<discipline>[A-Za-z ]+?)\s*"
                    r"(?P<weight>[-+]\s?\d{2,3}\s*kg)?$", re.I)
# Canne de combat and bâton are separate sports under the same federation.
_OTHER_SPORT = re.compile(r"canne|b[aâ]ton|chausson", re.I)


def _read_events(lines, sheet, report):
    """The country column is headed "Country" / "Code" on the two lines that
    straddle the header, so it is taken from there rather than from the first
    "Country" anywhere in the book - the entry lists earlier in the same file
    head a column of their own with that word, far to the left.
    """
    anchors, country_x, page = None, 0.0, None
    klass, named, other = None, "", set()
    for number, line in enumerate(lines):
        texts = [w.text for w in line]
        if texts[:4] == _EVENT_HEADER:
            anchors, page = [w.x0 for w in line], line[0].page
            near = [w for l in lines[max(0, number - 2):number + 3] for w in l
                    if w.text in ("Country", "Code") and w.page == page]
            country_x = min((w.x0 for w in near), default=float("inf"))
            continue
        # The table lives on the page its header heads. The result book runs to
        # a dozen further pages of draws and entry lists whose columns sit at
        # other positions entirely; reading on past the page turn would pour
        # them through these bands and call every surname an event.
        if page is None or line[0].page != page:
            continue

        def band(index):
            left = anchors[index] - 2
            right = (anchors[index + 1] - 2 if index + 1 < len(anchors)
                     else country_x - 2)
            return _flat(pdf.text_of([w for w in line if left <= w.x0 < right]))

        event, medal, name = band(0), band(2), band(3)
        country = _flat(pdf.text_of([w for w in line if w.x0 >= country_x - 2]))
        if event:
            klass, named = _event_class(event), event
        rank = next((r for p, r in _MEDAL_WORD if p.fullmatch(medal)), "")
        if not rank:
            continue
        # An event is only reported as skipped once a medal actually goes
        # unrecorded under it. Page furniture wanders into the event column -
        # the footer's report number lands there - and naming that as a
        # skipped event would bury the one real omission, canne de combat.
        if klass is None:
            other.add(named)
            continue
        sheet.add(rank, name, klass, country=country)
    if other:
        report.notes["skipped_events"] = sorted(other)
        report.problem("event(s) skipped: " + ", ".join(sorted(other)) +
                       " - a different sport from savate, or an event whose "
                       "name states neither a gender nor a weight class")


def _event_class(event):
    found = _EVENT.match(_flat(event))
    if not found:
        return None
    if _OTHER_SPORT.search(found.group("discipline")):
        return None
    weight = _weight(found.group("weight") or "")
    gender = "Women" if found.group("who").lower() == "women" else "Men"
    discipline = found.group("discipline").strip().title()
    label = " ".join(x for x in (discipline, gender,
                                 weight["printed"] if weight else "") if x)
    return {"category": label, "gender": gender, "age_class": "",
            "weight_kg": weight["weight_kg"] if weight else "",
            "weight_bound": weight["weight_bound"] if weight else ""}


# --------------------------------------------------------------------------

def read(source, slug, meta=None, **options):
    """(Tournament, [Placing], Report) from one podium document."""
    from savate import sources

    meta = dict(meta or {})
    report = Report(source=str(source), adapter=NAME)
    fields = {k: v for k, v in meta.items() if k in TOURNAMENT_FIELDS}
    fields.setdefault("name", meta.get("title", "") or slug)
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME, **fields)

    try:
        path = sources.fetch_archived(str(source), cache=options.get(
            "cache", sources.CACHE), refresh=options.get("refresh", False))
    except Exception as e:
        report.problem(f"{source} could not be fetched: {e}")
        return tournament, [], report
    try:
        words = pdf.words(path)
    except Exception as e:
        report.problem(f"{path} has no readable word geometry: {e}")
        return tournament, [], report

    report.read = len({w.page for w in words})
    lines = pdf.rows(words)
    sheet = _Sheet(slug, report)

    # The layout is settled by the header each one prints, not by the host it
    # came from: two of these documents are Wayback copies of the other two,
    # and a federation is free to change its site without changing its
    # paperwork. Whatever goes wrong inside a reader is a report, never a
    # traceback - an adapter that dies takes the whole build with it, and
    # federation paperwork is reliably irregular.
    readers = [
        ("croatian_report",
         lambda: any([w.text for w in l] == _HR_HEADER for l in lines),
         lambda: _read_croatian(lines, sheet, report)),
        ("medallists_by_event",
         lambda: any([w.text for w in l][:4] == _EVENT_HEADER for l in lines),
         lambda: _read_events(lines, sheet, report)),
        ("medal_grid",
         lambda: any(_grid_header(l) for l in lines),
         lambda: _read_grid(lines, sheet, meta, report)),
    ]
    for layout, matches, run in readers:
        if not matches():
            continue
        report.notes["layout"] = layout
        try:
            run()
        except Exception as e:
            report.problem(f"the {layout} reader failed on this document: "
                           f"{type(e).__name__}: {e}")
        break
    else:
        report.problem("no medal-list layout recognised: this is not a grid, "
                       "a Croatian federation report or a medallist table")

    report.notes["placings"] = len(sheet.rows)
    if not sheet.rows:
        report.problem("no placings found")
    return tournament, sheet.rows, report
