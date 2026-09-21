"""The French university championships, as sport-u.com published them.

The FFSU ran a national savate championship every March from at least 2004, and
put the results on sport-u.com in whatever the organiser had to hand. That is
four different documents, not one, and this adapter reads all four because they
are one competition series and splitting them across four adapters would put the
same championship under four different readings of the same weight class.

  *The poule workbooks* (2004, 2007, 2009, 2010, 2011) are the richest thing in
  this archive for their era: an Excel sheet per weight class, each holding the
  entry list, the poule cross-tables, and the knockout bracket. A poule bout is
  written as ``order NAME order NAME`` with the two scores in the columns headed
  by those same order numbers, so the sheet states which score belongs to whom
  and this does not have to guess. Where the sheet prints a column header, that
  header is used; where it does not, the two scores are read left to right and
  the fallback is recorded in the report.

  *The flat ranked sheets* (2005, 2006, 2008, and the "PAR POIDS" sheets inside
  the 2009 workbook) are a classification and nothing else - Clt, name, club,
  weight. They become placings. Entrants with a blank Clt finished unplaced and
  are counted, not invented into a rank.

  *The 2022 podium PDF* is a three-line card per competitor - name, then rank
  and title, then university - and not a table, so the name is the line BEFORE
  the rank and the club the line after.

  *The Ile-de-France regional sheet* is a ranked list per class, headed
  ``-55 KG F``, which is the weight-then-gender order the national sheets write
  the other way round.

Seven things this adapter refuses to do.

*It does not assign corners.* Not one of these documents says who stood in the
red corner. It names who won, or prints the scores that say so. `winner` and
`loser` are filled and `winner_corner` is left empty, which is what red and blue
mean in this archive.

*It does not turn a team result into a fighter's result.* Six documents in this
family are the championnat par equipes: team poule grids, team rankings, and in
one case a team's composition by weight slot. A rencontre's 3-1 belongs to two
universities, not to two people, and decomposing it into individual bouts would
be writing bouts nobody recorded. Those documents are read far enough to say
what they are and then return no rows.

*It does not rank a poule the sheet left unranked*, and it does not resolve a
2-2. The 2004 and 2007 sheets print drawn scorelines, which the modern bareme
(3/1/-1/0) has no rule for; such a bout is stored unresolved with both scores as
printed, rather than given to whoever the bracket happens to favour.

*It does not accept a name it cannot place.* Every fighter in a bout row is
resolved against that sheet's own entry list, by the order number the row prints
or by surname. A surname that matches no entrant, or matches two, is reported
and its bout is skipped; a row whose two names resolve to one person is skipped
outright.

*It does not state a result the same sheet denies.* In a bracket the loser
cannot finish above the winner, so a final whose two figures hand the title to
the runner-up is a sheet at odds with itself - the 2009 women's -48 kg and the
2011 women's -60 kg both are. There is no way to know which figure was typed
wrongly, so the bout keeps its printed scores and names nobody.

*It does not read a decision out of a scoreline.* These sheets print the bareme
- 3 to the winner, 1 to a loser who finished, 0 to one who did not box, -1 to
one thrown out - and once in a corpus a word beside it ("3 par forfait"). The
word is read; the figures are not a verdict and are not turned into one. The
archive's own rules.bout_points scores an abandon 3-1 exactly as it scores a
points win, so a 3-1 cannot tell the two apart, and a 3-0 is what the sheet
gives a forfeit and a fighter who was there and scored nothing alike. Every bout
in this family therefore carries its scores, its winner and an empty `decision`,
except the one 2004 bronze whose sheet says "par forfait".

*It does not file another sport as savate, or a demonstration as a bout.* Canne
de combat, chausson, baton and savate forme are dropped with a count in the
report; so is any row the sheet marks as a demonstration or hors competition.

The sheet names are not trustworthy and the printed class line is. The 2004
workbook has a sheet called ``JG 86-82`` whose own heading reads
``Categorie : JG 76-82``; the heading is believed and the sheet name is used
only where no heading exists.

What the report always carries, because a reader of these rows will want it:
``poule_totals`` - how many of the sheet's own column sums the scores this
adapter picked out reproduce, and which ones they do not; ``name_repairs`` -
every surname resolved to an entrant it was not spelled as; ``drawn_scorelines``
- the 2-2s; and ``unlettered_poules`` - the tables numbered by drawing order
because the sheet gave them no letter.

Two contradictions these workbooks make and this adapter states rather than
settles: a class whose podium ends up holding two people on one step - the 2009
workbook prints its classification twice and spells three of the names
differently the second time, which no exact-name dedupe can see - and a name
cell holding something that is not a name, an association typed into the PRENOM
column or a sport typed after the forename. Both are reported, and in both the
row is kept exactly as the document prints it: deciding that two spellings are
one person, or that a forename is really a club, would be this adapter writing
the document rather than reading it.
"""

import re

from savate.schema import (MEDALS, Bout, Placing, Report, Tournament)

NAME = "universitaire"
DESCRIPTION = ("FFSU French university championships: XLS poule workbooks, "
               "flat ranked sheets and podium PDFs from sport-u.com")

# ---------------------------------------------------------------- vocabulary

_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
           "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
           "novembre": 11, "decembre": 12}

# A cell that is nothing but a finishing position: "1°", "4°_", "3 °".
_PLACE_MARK = re.compile(r"^(\d{1,2})\s*[°ºo]\s*_?$")

# A bracket seed, as these sheets write it: A1, B 2, P3, C2, B1/D2.
_SEED = re.compile(r"^[A-Z]\s?\d(?:\s*/\s*[A-Z]\s?\d)?$", re.I)

# Rows that close a poule table. Meeting one means the next bout row belongs to
# a new poule, which is the only thing that separates two unlettered tables.
_CLOSERS = {"total", "totaux", "avertissements", "avertissement", "place",
            "places", "notes tech", "notestech", "pl"}

# Words that furnish these sheets. None of them is ever a competitor, and a
# fuzzy match is only safe if it can never be offered one of these to repair.
_STRUCTURE = _CLOSERS | {
    "nom", "noms", "prenom", "prenoms", "as", "ordre", "clt", "poids", "sexe",
    "finales", "finale", "eliminatoires", "poule", "croisees", "vainqueur",
    "categorie", "tireurs", "tireur", "officiel", "equipe", "academie",
    "association sportive", "1 jour", "2 jour", "resultats", "resultat"}

# Block headings, in the wordings these workbooks use. "3° PLACE" is not in the
# schema's own alias table, and "ELIMINATOIRES" is this federation's word for
# the poule round rather than for a knockout.
_HEADINGS = [
    (re.compile(r"^poule\s*([a-z0-9]+)$"), "poule"),
    (re.compile(r"^poules?$"), "poule"),
    (re.compile(r"^eliminatoires?$"), "poule"),
    (re.compile(r"^1\s*/\s*8\s*(de\s*)?finales?"), "r16"),
    (re.compile(r"^1\s*/\s*4\s*(de\s*)?finales?"), "quarter"),
    (re.compile(r"^quarts?\s*de\s*finales?"), "quarter"),
    (re.compile(r"^1\s*/\s*2\s*(de\s*)?finales?"), "semi"),
    (re.compile(r"^demi[- ]?finales?"), "semi"),
    (re.compile(r"^finales?$"), "final"),
    (re.compile(r"^3\s*[°ºe]{0,2}\s*(eme\s*)?place$"), "bronze"),
    (re.compile(r"^petite\s*finale$"), "bronze"),
]

# The words these sheets print beside a score are read through the shared
# vocabulary (normalize.decision), which already knows forfait, W.O., the French
# stoppage phrases and KO. Two wordings the FFSU sheets use are not in it yet -
# a bare "arrêt" with no one named as stopping it, and "blessure" - so they are
# read here and nowhere else, rather than by widening the shared table under
# another adapter's feet.
_LOCAL_DECISION_WORDS = [
    (re.compile(r"\barr[eê]ts?\b|blessure", re.I), "abandon"),
]


def _decision_word(detail):
    """The sheet's own verdict word -> a canonical decision, or "".

    "" is the common answer and the right one: these workbooks print a score and
    almost never a word, and a decision this function cannot read is a decision
    the document does not state.
    """
    from savate import normalize as norm
    text = str(detail or "")
    if not text.strip():
        return ""
    named = norm.decision(text)
    if named:
        return named
    for pattern, decision in _LOCAL_DECISION_WORDS:
        if pattern.search(text):
            return decision
    return ""


# Sports that are not savate, however often they share a hall with it. The FFSU
# runs canne de combat on the same weekend in some years, and a row of it filed
# as savate is not a savate result at all.
_OTHER_SPORT = re.compile(r"\bcanne\b|canne\s*de\s*combat|b[aâ]ton|chausson|"
                          r"savate\s*forme|\bforme\b", re.I)

# A demonstration has no result and is not a bout.
_DEMO = re.compile(r"d[ée]monstration|\bd[ée]mo\b|exhibition|hors\s*comp[ée]tition",
                   re.I)


def _collapse(text):
    return " ".join(str(text or "").split())


def _fold(text):
    from savate import normalize as norm
    return norm.fold(text)


def _key(text):
    """A cell reduced to what it says: accent-folded, punctuation dropped."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _fold(text)).split())


def _namekey(text):
    """A surname reduced for matching: letters and digits only.

    "GRANAT-BAS" and "GRANAT BAS" are one person and must key the same; a
    trailing weigh-in note ("DUVAL 81,2 KG") is not part of the name.
    """
    text = re.sub(r"\b\d{2,3}[.,]?\d*\s*kg\b", " ", str(text or ""), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", _fold(text))


def _loose(key):
    """A surname key with the spellings these sheets vary on flattened.

    The bracket is typed a second time by hand, and the second typing wanders:
    RAPHALEN becomes RAFALEN, GHASSIRI becomes GASSIRI, ESSERE becomes ESSSERRE,
    CARAVECCHIA becomes CARAVECHIA. Those are all the same three habits - ph for
    f, a dropped h, a doubled letter - so they are flattened rather than guessed
    at one by one.
    """
    key = key.replace("ph", "f").replace("h", "").replace("y", "i")
    out = []
    for letter in key:
        if not out or out[-1] != letter:
            out.append(letter)
    return "".join(out)


def _within(a, b, limit):
    """True if at most `limit` single-character edits separate two keys."""
    if abs(len(a) - len(b)) > limit:
        return False
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


# ------------------------------------------------------------ weight classes

_GENDER_PREFIX = re.compile(r"^\s*(jg|jf)", re.I)
_GENDER_TOKEN = re.compile(r"(?:^|[^a-z])([hfmg])(?:[^a-z]|$)", re.I)


def _class_of(label, report=None):
    """(gender, weight kg, bound) from a printed class line, or ("","","").

    The wordings differ by year and by sheet - "JG +89 kg", "H moins de 56 kg",
    "JFmoinsde 50", "- 56 kg", "F 50", "-55 KG F" - so every one seen in this
    family is read here rather than in four separate readers.
    """
    text = _collapse(label)
    if not text:
        return "", "", ""
    text = re.sub(r"^\s*cat[ée]gorie\s*(de\s*poids)?\s*:?\s*", "", text, flags=re.I)
    folded = _fold(text)

    gender = ""
    prefix = _GENDER_PREFIX.match(folded)
    if prefix:
        gender = "Men" if prefix.group(1).lower() == "jg" else "Women"
    else:
        token = _GENDER_TOKEN.search(folded)
        if token:
            gender = {"h": "Men", "m": "Men", "g": "Men",
                      "f": "Women"}[token.group(1).lower()]

    body = _GENDER_PREFIX.sub(" ", folded)
    kilos, bound = "", ""
    over = re.search(r"\+\s*(?:de\s+)?(\d{2,3})|plus\s*(?:de\s*)?(\d{2,3})", body)
    under = re.search(r"moins\s*(?:de\s*)?(\d{2,3})", body)
    band = re.search(r"(\d{2,3})\s*[-–]\s*(\d{2,3})", body)
    minus = re.search(r"[-–]\s*(\d{2,3})", body)
    bare = None if "+" in body else \
        re.search(r"(?:^|\s)(\d{2,3})(?:\s*kg)?\s*$", body)
    if over:
        kilos, bound = (over.group(1) or over.group(2)), "over"
    elif under:
        kilos, bound = under.group(1), "under"
    elif band:
        low, high = int(band.group(1)), int(band.group(2))
        if low > high and report is not None:
            report.problem(f"class {text!r} prints a band whose lower figure is "
                           f"the larger; read as the class ending at {low} kg")
        kilos, bound = str(max(low, high)), "under"
    elif minus:
        kilos, bound = minus.group(1), "under"
    elif bare:
        kilos, bound = bare.group(1), "under"
    return gender, kilos, bound


def _category(gender, kilos, bound, age_class=""):
    """The canonical label a row is filed under.

    Constructed, not copied. One class is written "H moins de 56 kg" in 2007,
    "JG moins 56" on the sheet tab, "- 56 kg" in 2008 and "M 56" in 2022, and
    filing those as four categories would split one weight class across four
    rows of every index that reads this archive. The document's own wording is
    kept in the report rather than thrown away.
    """
    sign = "+" if bound == "over" else "-"
    parts = [p for p in (age_class, gender) if p]
    if kilos:
        parts.append(f"{sign}{kilos} kg")
    return " ".join(parts)


# --------------------------------------------------------------- date / city

def _dateline(lines):
    """(start ISO, end ISO, city) from the French heading lines, or ("","","").

    "LIMOGES, les 18 et 19 mars 2004" and "les 31 mars et 1er avril 2005" are
    both here; a heading that does not carry a date gives back empties rather
    than a year guessed from the filename.
    """
    city = ""
    for line in lines:
        text = _collapse(line)
        if not text:
            continue
        found = re.match(r"^(.{3,40}?),\s*les?\s+\d", text, re.I)
        if found and not city:
            city = re.sub(r"^(?:[àa]u?x?|de|du)\s+", "", found.group(1).strip(),
                          flags=re.I)
        found = re.search(r"\b[àa]\s+([A-ZÉÈÀÂÎÔÛ][\w'’ -]{2,30})\s*$", text)
        if found and not city:
            city = found.group(1).strip()

    for line in lines:
        text = _collapse(line)
        folded = _fold(text)
        year = re.search(r"\b(19|20)\d{2}\b", folded)
        months = [(m.start(), _MONTHS[m.group(0)])
                  for m in re.finditer("|".join(_MONTHS), folded)]
        if not (year and months):
            continue
        y = int(year.group(0))
        spans, start_at = [], 0
        for at, month in months:
            days = [int(d) for d in re.findall(r"\b(\d{1,2})(?:er)?\b",
                                               folded[start_at:at])]
            spans.append((month, days))
            start_at = at
        dated = [(m, d) for m, days in spans for d in days if 1 <= d <= 31]
        if not dated:
            continue
        first, last = dated[0], dated[-1]
        try:
            from datetime import date as _date
            return (_date(y, first[0], first[1]).isoformat(),
                    _date(y, last[0], last[1]).isoformat(), city)
        except ValueError:
            return "", "", city
    return "", "", city


# ------------------------------------------------------------------- reading

def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) for one FFSU university document."""
    from savate import sources

    meta = dict(meta or {})
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)
    path = sources.fetch(source)

    try:
        head = path.open("rb").read(8)
    except OSError as e:
        raise OSError(f"{source} cannot be read: {e}") from e

    if head[:4] == b"%PDF":
        rows = _read_pdf(path, slug, meta, tournament, report)
    elif head[:4] == b"\xd0\xcf\x11\xe0":
        rows = _read_workbook(path, slug, meta, tournament, report)
    else:
        report.problem("not a PDF and not an .xls workbook - this adapter reads "
                       "neither this format nor whatever it is")
        rows = []

    report.notes.setdefault("bouts", sum(1 for r in rows if isinstance(r, Bout)))
    report.notes.setdefault("placings",
                            sum(1 for r in rows if isinstance(r, Placing)))
    if not rows and not report.problems:
        report.problem("no rows: the document was read but held no result this "
                       "adapter recognises")
    return tournament, rows, report


def _tournament(slug, meta, source):
    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""),
        format=meta.get("format", ""),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        start_date=meta.get("start_date", ""),
        end_date=meta.get("end_date", ""),
        city=meta.get("city", ""),
        country=meta.get("country", ""),
        source=str(source), adapter=NAME,
        competition=meta.get("competition", ""),
    )


# ------------------------------------------------------------------ the XLS

class _Sheet:
    """One worksheet as cells that know whether they are a number."""

    def __init__(self, sheet):
        import xlrd

        self.name = sheet.name
        self.nrows, self.ncols = sheet.nrows, sheet.ncols
        self.text = [["" for _ in range(self.ncols)] for _ in range(self.nrows)]
        self.number = [[None] * self.ncols for _ in range(self.nrows)]
        for r in range(self.nrows):
            for c in range(self.ncols):
                kind = sheet.cell_type(r, c)
                value = sheet.cell_value(r, c)
                if kind == xlrd.XL_CELL_NUMBER:
                    self.number[r][c] = float(value)
                    self.text[r][c] = _collapse(value)
                elif kind == xlrd.XL_CELL_TEXT:
                    self.text[r][c] = _collapse(value)
                elif kind == xlrd.XL_CELL_BOOLEAN:
                    self.text[r][c] = _collapse(value)

    def at(self, r, c):
        if 0 <= r < self.nrows and 0 <= c < self.ncols:
            return self.text[r][c]
        return ""

    def num(self, r, c):
        """The cell as a score, or None. A place mark is never a score."""
        if not (0 <= r < self.nrows and 0 <= c < self.ncols):
            return None
        if self.number[r][c] is not None:
            return self.number[r][c]
        text = self.text[r][c]
        if not text or _PLACE_MARK.match(text):
            return None
        if re.fullmatch(r"-?\d+(?:[.,]\d+)?", text):
            return float(text.replace(",", "."))
        found = re.match(r"^(-?\d+(?:[.,]\d+)?)\s+(\D.*)$", text)
        if found and _decision_word(found.group(2)):
            return float(found.group(1).replace(",", "."))
        return None

    def note(self, r, c):
        """The decision word printed beside a score, in the sheet's own wording."""
        text = self.at(r, c)
        found = re.match(r"^-?\d+(?:[.,]\d+)?\s+(\D.*)$", text)
        return _collapse(found.group(1)) if found else ""


_SKIP_SHEET = re.compile(r"engag|pes[ée]e|inscri|par\s*eq|equipe|équipe", re.I)


def _read_workbook(path, slug, meta, tournament, report):
    try:
        import xlrd
    except ImportError:                                   # pragma: no cover
        report.problem("xlrd is required to read the FFSU .xls workbooks")
        return []
    try:
        book = xlrd.open_workbook(str(path))
    except Exception as e:
        report.problem(f"not a readable .xls workbook ({type(e).__name__}: {e}); "
                       f"a .doc from the same folder arrives looking like one")
        return []

    report.read = book.nsheets
    counter = _Counter()
    rows, classes, skipped = [], {}, []
    title_lines, discipline = [], ""

    for raw in book.sheets():
        sheet = _Sheet(raw)
        title_lines += [sheet.at(r, c) for r in range(min(4, sheet.nrows))
                        for c in range(min(3, sheet.ncols)) if sheet.at(r, c)]
        if re.search(r"assaut", " ".join(title_lines), re.I):
            discipline = "assaut"
        if _SKIP_SHEET.search(sheet.name):
            skipped.append(f"{sheet.name} (entry/weigh-in or team sheet)")
            continue
        made = _poule_sheet(sheet, slug, meta, report, counter, classes)
        if made is None:
            made = _flat_sheet(sheet, slug, meta, report, counter, classes)
        if made is None:
            skipped.append(f"{sheet.name} (no entry list and no Clt column)")
            continue
        rows += made
    rows = _dedupe_placings(rows, report)
    _report_stray_cells(rows, report)

    start, end, city = _dateline(title_lines)
    tournament.start_date = tournament.start_date or start
    tournament.end_date = tournament.end_date or end
    tournament.city = tournament.city or city
    if start and not tournament.year:
        tournament.year = start[:4]
    if discipline and not tournament.discipline:
        tournament.discipline = discipline
        report.notes["discipline_from_document"] = "assaut"
    elif not discipline and not tournament.discipline:
        report.problem("the workbook never names the discipline; assaut vs "
                       "combat is left empty rather than assumed")

    if skipped:
        report.notes["sheets_skipped"] = skipped
    if not rows and skipped and len(skipped) == book.nsheets:
        report.problem("every sheet in this workbook is an entry list, a "
                       "weigh-in or a team rencontre: it records universities "
                       "and weigh-in weights, not who beat whom, so it yields "
                       "no fighter row without inventing one")
    report.notes["classes"] = classes
    return rows


# A discipline typed into the PRENOM cell. The FFSU sheets carry three of these
# ("CELINE BOXE", "MELISSA BOXE", "GAELLE BOXE") and one "CINDY BF": the sheet's
# own typing, so the name is stored as printed - but a person whose name ends in
# the name of the sport is how an identity-keyed archive grows a second person
# out of one, so it is said out loud.
_SPORT_IN_A_NAME = re.compile(r"\b(boxe(\s+fran[çc]aise)?|b\.?f\.?|s\.?b\.?f\.?|"
                              r"savate|assauts?|canne)\s*$", re.I)


def _report_stray_cells(rows, report):
    """Say so where a fighter's name cell holds something that is not a name.

    These workbooks are typed by hand into a NOM / PRENOM / AS grid and the hand
    slips: an association lands in the PRENOM cell ("CAVALLO | U2 Marseille"),
    or spills across the two ("GRONIER | Quentin U2 | Marseille"), or the sheet
    writes the sport after the forename ("CELTON | CELINE BOXE"). The cell is
    stored as the document prints it, because rewriting a name is a fact this
    adapter would be making up; but the workbook's own AS column names the clubs,
    so when a name ends in one of them the archive can at least say which rows
    it happened to instead of letting a club walk in as a forename.
    """
    clubs, people = set(), {}
    for row in rows:
        if isinstance(row, Bout):
            for club in (row.red_club, row.blue_club):
                if len(_key(club)) >= 3:
                    clubs.add(_key(club))
            people.setdefault((row.red, row.red_club), None)
            people.setdefault((row.blue, row.blue_club), None)
        elif isinstance(row, Placing):
            if len(_key(row.club)) >= 3:
                clubs.add(_key(row.club))
            people.setdefault((row.fighter, row.club), None)

    said = set()
    for name, club in sorted(people):
        if name in said:
            continue
        said.add(name)
        tokens = _collapse(name).split()
        for i in range(1, len(tokens)):
            tail = " ".join(tokens[i:])
            if _key(tail) in clubs:
                report.problem(
                    f"{name!r} carries the club {tail!r} inside the name: the "
                    f"workbook's own AS column prints {tail!r} as an "
                    f"association, so this fighter's forename is not stated and "
                    f"the name is kept exactly as the cell prints it")
                break
            if club and _key(f"{tail} {club}") in clubs:
                report.problem(
                    f"{name!r} ends in {tail!r}, which with its club {club!r} "
                    f"spells the association {tail + ' ' + club!r} the workbook "
                    f"prints elsewhere: the club cell is half a club and the "
                    f"forename half a name, and both are kept as printed")
                break
        if _SPORT_IN_A_NAME.search(name):
            report.problem(
                f"{name!r} ends in the name of the sport, which the sheet typed "
                f"into the forename cell; stored as printed, not cleaned")


def _dedupe_placings(rows, report):
    """One placing per fighter per class.

    The 2009 workbook states its classification twice - once as a flat "PAR
    POIDS" list with licence numbers, once in the PLACE column of each weight
    sheet - and both are the same fact. The first seen is kept; a second that
    disagrees about the rank is reported rather than quietly dropped.
    """
    seen, out, repeats = {}, [], 0
    for row in rows:
        if not isinstance(row, Placing):
            out.append(row)
            continue
        key = (row.category, _namekey(row.fighter))
        if key in seen:
            repeats += 1
            if seen[key] != row.rank:
                report.problem(
                    f"{row.category}: {row.fighter} is placed {seen[key]} on one "
                    f"sheet of this workbook and {row.rank} on another")
            continue
        seen[key] = row.rank
        out.append(row)
    if repeats:
        report.notes["placings_stated_twice"] = repeats
    _report_crowded_ranks(out, report)
    return out


# How many people one finishing position can hold. Savate runs two bronzes off
# the two losing semi-finalists; every other position holds one.
_HOLDERS = {"3": 2}


def _report_crowded_ranks(rows, report):
    """Say so when a class ends up with two people on one step of the podium.

    An exact-name dedupe cannot see that "TRIOZEAU GUILLAUME" on the PAR POIDS
    sheet and "TRIOREAU GUILLAUME" on the weight sheet are one man with a
    licence number, so the class comes out with two bronze medallists - a
    medallist the document never awarded. Merging them would be this adapter
    deciding two spellings are one person, which is exactly the kind of guess
    this archive is not allowed to make, so the rows stay as the sheets print
    them and the contradiction is reported instead. A near-match is named as
    such, because that is the case a reader most needs pointed out.
    """
    held, classed = {}, {}
    for row in rows:
        if isinstance(row, Placing) and row.rank:
            held.setdefault((row.category, row.rank), []).append(row.fighter)
            classed.setdefault(row.category, []).append(
                (row.fighter, row.rank))
    for (category, rank), who in sorted(held.items()):
        if len(who) > _HOLDERS.get(str(rank), 1):
            report.problem(
                f"{category}: {len(who)} fighters hold place {rank} "
                f"({', '.join(who)}) where the document awards "
                f"{_HOLDERS.get(str(rank), 1)}")
    for category, placed in sorted(classed.items()):
        for one, two in _near_spellings(placed):
            report.problem(
                f"{category}: {one[0]!r} (place {one[1]}) and {two[0]!r} "
                f"(place {two[1]}) differ by a letter or two and may be one "
                f"person spelled two ways on two sheets; both are kept as the "
                f"document prints them and neither is merged into the other")


def _near_spellings(placed):
    """The (name, rank) pairs in one class that are near-matches of each other.

    Near is the same measure the bout rows use on a surname the bracket retyped:
    the spelling habits _loose flattens, or at most two edits. Two people in one
    weight class whose whole names are that close are rare; one person typed
    twice is not.
    """
    pairs = []
    for i, one in enumerate(placed):
        for two in placed[i + 1:]:
            a, b = _namekey(one[0]), _namekey(two[0])
            if not a or not b or a == b:
                continue
            if _loose(a) == _loose(b) or _within(a, b, 2):
                pairs.append((one, two))
    return pairs


class _Counter:
    def __init__(self):
        self.bout = 0
        self.placing = 0

    def next_bout(self):
        self.bout += 1
        return self.bout

    def next_placing(self):
        self.placing += 1
        return self.placing


# ------------------------------------------------------- the poule workbooks

def _entry_header(sheet):
    """(row, column of NOM) for the entry list, or None if there is not one."""
    for r in range(min(20, sheet.nrows)):
        for c in range(1, min(8, sheet.ncols)):
            if _key(sheet.at(r, c)) == "nom" and \
                    _key(sheet.at(r, c + 1)) in ("prenom", "prenoms"):
                return r, c
    return None


def _entries(sheet, header_row, nom_col):
    """{order number: entry} read down from the entry header."""
    out = {}
    blank = 0
    for r in range(header_row + 1, sheet.nrows):
        order = sheet.num(r, nom_col - 1)
        surname = sheet.at(r, nom_col)
        if order is None or not surname:
            # The cross-table's own header sits between the entry header and
            # the first entrant on several sheets, and its entry columns are
            # empty. An empty row is a gap; a row with other words in it is
            # the end of the list.
            if sheet.at(r, nom_col - 1) or surname:
                break
            blank += 1
            if blank > 8:
                break
            continue
        if order != int(order) or int(order) < 1:
            break
        blank = 0
        rank = _PLACE_MARK.match(sheet.at(r, nom_col + 3))
        out[int(order)] = {
            "order": int(order), "row": r,
            "surname": surname,
            "given": sheet.at(r, nom_col + 1),
            "club": sheet.at(r, nom_col + 2),
            "rank": rank.group(1) if rank else "",
        }
    return out


def _class_line(sheet, header_row, nom_col, report):
    """The class this sheet is about, read from its own heading where it has one."""
    for r in range(0, header_row):
        for c in range(0, min(nom_col + 2, sheet.ncols)):
            text = sheet.at(r, c)
            if not text or len(text) > 60:
                continue
            if re.search(r"championnat|savate|boxe|tireur|r[ée]sultat", text, re.I) \
                    and not re.search(r"cat[ée]gorie", text, re.I):
                continue
            gender, kilos, bound = _class_of(text, report)
            if kilos:
                return text, gender, kilos, bound
    gender, kilos, bound = _class_of(sheet.name, report)
    return sheet.name, gender, kilos, bound


def _headings(sheet):
    """[(row, col, phase, poule name)] for every block heading on the sheet."""
    out = []
    for r in range(sheet.nrows):
        for c in range(sheet.ncols):
            text = sheet.at(r, c)
            if not text or len(text) > 24:
                continue
            key = _fold(text).strip().strip('"“”').strip()
            key = re.sub(r"\s+", " ", key)
            for pattern, phase in _HEADINGS:
                found = pattern.match(key)
                if found:
                    label = ""
                    if phase == "poule" and found.groups() and found.group(1):
                        label = found.group(1).upper()
                    out.append((r, c, phase, label))
                    break
    return out


def _resolve(token, index, entries):
    """(entry, how) for a surname printed in a bout row, or (None, reason).

    Exact first. A sheet that abbreviates "SEGUIR BAKIR" to "SEGUIR" or spells
    "ESSERE" as "ESSERRE" in its own bracket is common enough that dropping
    those rows would lose real bouts, so a prefix or single-letter difference is
    accepted - but only where exactly one entrant matches, and every such repair
    is reported.
    """
    key = _namekey(token)
    if not key:
        return None, "empty"
    if key in index:
        return entries[index[key]], "exact"

    tiers = [
        lambda k: _loose(k) == _loose(key),
        lambda k: len(k) >= 4 and len(key) >= 4 and (k.startswith(key)
                                                     or key.startswith(k)),
        lambda k: len(k) >= 4 and _within(k, key, 1),
        lambda k: len(k) >= 6 and len(key) >= 6 and _within(k, key, 2),
    ]
    for tier in tiers:
        near = [k for k in index if tier(k)]
        if len(near) == 1:
            return (entries[index[near[0]]],
                    f"{token!r} read as the entrant {near[0]!r}")
        if len(near) > 1:
            return None, (f"{token!r} could be any of "
                          f"{', '.join(sorted(near))} and is not resolved")
    return None, f"{token!r} is in no entry list on this sheet"


def _label_key(text):
    """The key a bout row prints beside a fighter: an order number or a seed."""
    text = _collapse(text)
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return str(int(float(text)))
    if _SEED.match(text):
        return re.sub(r"\s+", "", text).upper()
    return ""


def _label_kind(text):
    """"num", "seed" or "" for a cell used as a key beside a fighter's name."""
    text = _collapse(text)
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return "num"
    if _SEED.match(text):
        return "seed"
    return ""


def _could_be_a_name(text):
    """Is this cell a printed surname at all?

    A score, an order number, a seed and a finishing position all sit in the
    same rows as the names, and treating one of them as a competitor is how a
    reader invents a bout. Only a cell with letters in it is a candidate.
    """
    text = _collapse(text)
    if not text or len(text) > 40:
        return False
    if _PLACE_MARK.match(text) or _SEED.match(text):
        return False
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", text):
        return False
    if _key(text) in _STRUCTURE:
        return False
    return len(re.findall(r"[A-Za-zÀ-ÿ]", text)) >= 2


def _pairs_in_row(sheet, r, index, entries, first_col):
    """[(n1, entry1, entry2, why)] for each fighter pair printed on one row."""
    found = []
    for c in range(first_col, sheet.ncols - 2):
        left, right = sheet.at(r, c), sheet.at(r, c + 2)
        if not (_could_be_a_name(left) and _could_be_a_name(right)):
            continue
        # "DUVAL 3.0 | MOUMINE 3°" is a bracket line beside a classification
        # line, not a bout: a finishing position never follows an opponent.
        if _PLACE_MARK.match(sheet.at(r, c + 1)) or \
                _PLACE_MARK.match(sheet.at(r, c + 3)):
            continue
        one, why_one = _resolve(left, index, entries)
        two, why_two = _resolve(right, index, entries)
        if one is None and two is None:
            continue
        found.append((c, one, two, (why_one, why_two)))
    # Two overlapping pairs cannot both be real; keep the leftmost of any overlap.
    kept = []
    for pair in found:
        if kept and pair[0] - kept[-1][0] < 3:
            continue
        kept.append(pair)
    return kept


def _poule_sheet(sheet, slug, meta, report, counter, classes):
    """Bouts and placings from one weight-class sheet, or None if it is not one."""
    header = _entry_header(sheet)
    if header is None:
        return None
    header_row, nom_col = header
    if nom_col < 1:
        return None
    # "Clt." in the column an order number would occupy means this is a
    # classification, not a draw: 2005's whole championship is one such sheet,
    # and read as a poule its finishing positions become entry numbers.
    if _key(sheet.at(header_row, nom_col - 1)) in _FLAT_RANK:
        return None
    entries = _entries(sheet, header_row, nom_col)
    if len(entries) < 2:
        return None

    printed, gender, kilos, bound = _class_line(sheet, header_row, nom_col, report)
    if _OTHER_SPORT.search(printed) or _OTHER_SPORT.search(sheet.name):
        report.problem(f"sheet {sheet.name!r} ({printed!r}) is another sport, "
                       f"not savate: its rows are dropped")
        report.notes["other_sport_dropped"] = \
            report.notes.get("other_sport_dropped", 0) + 1
        return []
    category = _category(gender, kilos, bound, meta.get("age_class", ""))
    if not category:
        report.problem(f"sheet {sheet.name!r}: no weight class could be read "
                       f"from {printed!r} - its rows are filed uncategorised")
    classes.setdefault(category or sheet.name, printed)
    where = f"{sheet.name} ({category or 'no class'})"

    index = {}
    clashes = set()
    for order, entry in entries.items():
        key = _namekey(entry["surname"])
        if key in index:
            clashes.add(key)
        index[key] = order
    for key in clashes:
        report.problem(f"{where}: two entrants share the surname key {key!r}; "
                       f"bout rows naming it are skipped")
        index.pop(key, None)

    headings = _headings(sheet)
    first_col = nom_col + 4

    # Every fighter pair printed anywhere on the sheet, with its block heading.
    found = []
    for r in range(header_row, sheet.nrows):
        for n1, one, two, why in _pairs_in_row(sheet, r, index, entries, first_col):
            found.append({"row": r, "col": n1, "one": one, "two": two, "why": why})

    # The running order, not a result. The 2011 workbooks print each poule's
    # draw in a spare column as "NAME order NAME" with no scores at all; read
    # as bouts those would duplicate the whole poule, unresolved. They are
    # recognised by shape - the middle cell IS the second fighter's own order
    # number and nothing numeric follows - and kept only to bound the block to
    # their left, since a draw listing has no label column of its own.
    for pair in found:
        pair["schedule"] = _is_draw_listing(sheet, pair)

    by_row = {}
    for pair in found:
        by_row.setdefault(pair["row"], []).append(pair)
    for pair in found:
        later = [p for p in by_row[pair["row"]] if p["col"] > pair["col"]]
        if later:
            nxt = min(later, key=lambda p: p["col"])
            pair["right"] = nxt["col"] if nxt["schedule"] else nxt["col"] - 1
        else:
            pair["right"] = sheet.ncols
        pair["labelled"] = bool(_label_key(sheet.at(pair["row"], pair["col"] - 1)))
        pair["block"] = _block_of(pair, headings)
    found = [p for p in found if not p["schedule"]]

    bouts = _emit_bouts(sheet, found, slug, meta, report, counter, where,
                        category, gender, kilos, bound, entries)
    _cross_check(bouts, entries, report, where)

    # A bracket the sheet heads but this could not read is a gap a reader has
    # to know about. The 2004 workbook draws its knockout one fighter to a row,
    # with the pairing carried by the lines between them rather than by any
    # cell, and nothing in a spreadsheet's values says which two rows are one
    # bout - so those bouts are left out rather than paired by proximity.
    drawn = {b.phase for b in bouts}
    for phase in sorted({h[2] for h in headings} & set(_KNOCKOUT)):
        if phase not in drawn:
            report.notes.setdefault("bracket_not_read", []).append(
                f"{where}: the sheet heads a {phase} block whose bouts are not "
                f"written on one row, so none was read from it")
    placings = _emit_placings(entries, slug, meta, report, counter, where,
                              category, gender, kilos, bound)
    return bouts + placings


def _is_demonstration(sheet, pair):
    """Is this row marked as a demonstration? Then it has no result to record."""
    for c in range(max(0, pair["col"] - 2), min(pair["right"] + 2, sheet.ncols)):
        if _DEMO.search(sheet.at(pair["row"], c)):
            return True
    return False


def _is_draw_listing(sheet, pair):
    """Is this pair the poule's running order rather than one of its results?"""
    if pair["two"] is None:
        return False
    middle = sheet.num(pair["row"], pair["col"] + 1)
    if middle is None or middle != pair["two"]["order"]:
        return False
    return not any(sheet.num(pair["row"], c) is not None
                   for c in range(pair["col"] + 3, sheet.ncols))


_KNOCKOUT = ("r64", "r32", "r16", "quarter", "semi", "bronze", "final")


def _cross_check(bouts, entries, report, where):
    """Unresolve a knockout bout the sheet's own classification contradicts.

    In a bracket the loser cannot finish above the winner, so a final whose
    scoreline hands the title to the runner-up is a sheet at odds with itself.
    The 2009 women's -48 kg sheet is exactly that: its classification, its poule
    table and the workbook's own PAR POIDS list all make NISSAS champion, and
    the final's two figures are the other way round. There is no way to tell
    which of the two the organiser typed wrongly, so the bout keeps its printed
    scores and states no winner.
    """
    ranks = {_full(e): int(e["rank"]) for e in entries.values() if e["rank"]}
    for bout in bouts:
        if bout.phase not in _KNOCKOUT or not bout.winner:
            continue
        won, lost = ranks.get(bout.winner), ranks.get(bout.loser)
        if won is None or lost is None or won <= lost:
            continue
        report.problem(
            f"{where}: the {bout.phase} scores {bout.winner} over {bout.loser}, "
            f"but the sheet places them {won} and {lost} - the two cannot both "
            f"be true, so the bout is stored unresolved")
        bout.winner = bout.loser = ""
        bout.status, bout.result_source, bout.decision = "unresolved", "", ""


def _block_of(pair, headings):
    """(phase, poule label, heading row) for the block a pair belongs to."""
    near = [h for h in headings
            if h[0] <= pair["row"] and pair["col"] - 4 <= h[1] <= pair["col"] + 3]
    if not near:
        return "", "", -1
    row, _col, phase, label = max(near, key=lambda h: (h[0], -abs(h[1] - pair["col"])))
    return phase, label, row


def _emit_bouts(sheet, found, slug, meta, report, counter, where,
                category, gender, kilos, bound, entries):
    """One bout per printed pair, grouped into the blocks the sheet draws."""
    blocks = {}
    for pair in found:
        # An unlabelled pair with no score anywhere is a bracket line drawn
        # beside its own result column, not a bout: nothing about it says the
        # two ever met.
        scores = [c for c in range(pair["col"] + 1, min(pair["right"], sheet.ncols))
                  if sheet.num(pair["row"], c) is not None]
        if not pair["labelled"] and not scores:
            continue
        if pair["one"] is None or pair["two"] is None:
            bad = [w for w in pair["why"] if w and w != "exact"]
            report.problem(f"{where} row {pair['row'] + 1}: {'; '.join(bad)}")
            continue
        if _is_demonstration(sheet, pair):
            report.notes["demonstrations_dropped"] = \
                report.notes.get("demonstrations_dropped", 0) + 1
            continue
        if pair["one"]["order"] == pair["two"]["order"]:
            report.problem(f"{where} row {pair['row'] + 1}: both names resolve to "
                           f"{pair['one']['surname']!r}; the row is skipped")
            continue
        for why in pair["why"]:
            if why and why != "exact":
                report.notes.setdefault("name_repairs", []).append(f"{where}: {why}")
        blocks.setdefault(pair["block"], []).append(pair)

    rows = []
    poule_seq = 0
    used = set()
    for block in sorted(blocks, key=lambda b: (b[2], b[0])):
        phase, label, _at = block
        for i, run in enumerate(_split_runs(sheet, blocks[block])):
            name = label if (i == 0 and label) else ""
            if phase == "poule":
                poule_seq += 1
                if not name or name in used:
                    # Several sheets letter POULE A and POULE B and then draw a
                    # third table with no heading at all. Calling it C would be
                    # writing a label the sheet does not carry, and calling it B
                    # would merge two different poules, so it is numbered by the
                    # order it is drawn and the report says so.
                    name = str(poule_seq)
                    while name in used:
                        name += "-"
                    report.notes.setdefault("unlettered_poules", []).append(
                        f"{where}: a poule table the sheet did not letter, "
                        f"numbered {name} in the order it is drawn")
                used.add(name)
            # A poule's header row is a column key, corroborated by the TOTAL
            # row beneath it. A knockout block's strip of seeds is not: the
            # 2009 sheets head a quarter-final A2 | C1 | B2 | C2 and then draw
            # A2 against C2 in the first column pair, so reading those labels
            # as columns points a fighter's score at someone else's seed.
            keys = _score_columns(sheet, run, report, where) \
                if phase not in _KNOCKOUT else {}
            if not phase and keys and _closes_below(sheet, run):
                # A cross-table headed by the entrants' order numbers and
                # closed by a TOTAL, Avertissements or Place row is a poule,
                # whether or not the sheet wrote the word above it. Several
                # 2004 sheets and the two-fighter classes of 2009 never do.
                phase = "poule"
                report.notes.setdefault("poules_read_from_shape", []).append(
                    f"{where}: a cross-table with no heading, read as a poule "
                    f"from its order-number header and its summary rows")
            made = [_bout(sheet, pair, keys, slug, meta, counter, report,
                          where, category, gender, kilos, bound,
                          phase, name if phase == "poule" else "")
                    for pair in run]
            if keys:
                _check_totals(sheet, run, keys, report, where, name)
            rows += made
    return [b for b in rows if b is not None]


def _check_totals(sheet, run, keys, report, where, poule):
    """Add up each column and compare it with the sheet's own TOTAL row.

    This is the one check on this layout that is not self-referential: the
    column sums were typed by the organiser, so if they agree with the scores
    this adapter picked out, the scores are in the right columns.
    """
    last = max(p["row"] for p in run)
    label_col = min(p["col"] for p in run) + 2
    total_row = None
    for r in range(last + 1, min(last + 6, sheet.nrows)):
        if _key(sheet.at(r, label_col)) in ("total", "totaux"):
            total_row = r
            break
    if total_row is None:
        return
    agreed, disagreed = 0, []
    for key, column in keys.items():
        printed = sheet.num(total_row, column)
        if printed is None:
            continue
        summed = sum(sheet.num(p["row"], column) or 0 for p in run
                     if sheet.num(p["row"], column) is not None)
        if abs(summed - printed) < 0.001:
            agreed += 1
        else:
            disagreed.append(f"{key}: sheet says {printed:g}, columns add to "
                             f"{summed:g}")
    tally = report.notes.setdefault("poule_totals", {"agreed": 0, "disagreed": []})
    tally["agreed"] += agreed
    if disagreed:
        tally["disagreed"].append(f"{where} poule {poule}: " + "; ".join(disagreed))


def _closes_below(sheet, run):
    """Does a TOTAL / Avertissements / Place row close this block?"""
    last = max(p["row"] for p in run)
    left = min(p["col"] for p in run)
    right = max(p["right"] for p in run)
    for r in range(last + 1, min(last + 6, sheet.nrows)):
        for c in range(max(0, left), min(right, sheet.ncols)):
            if _key(sheet.at(r, c)) in _CLOSERS:
                return True
    return False


def _split_runs(sheet, pairs):
    """Split one heading's pairs into the separate tables the sheet draws.

    Two signals, because neither alone is enough. A TOTAL/Avertissements/Place
    row closes a table - but a two-fighter poule has no summary rows at all, so
    the 2004 sheets run four of them under one ELIMINATOIRES heading with
    nothing between. The second signal is the sport: every fighter is in exactly
    one poule and meets everyone in it, so a poule's bouts form one connected
    group and two poules share nobody.
    """
    pairs = sorted(pairs, key=lambda p: (p["row"], p["col"]))
    runs, run = [], []
    for pair in pairs:
        if run and _closed_between(sheet, run[-1], pair):
            runs.append(run)
            run = []
        run.append(pair)
    if run:
        runs.append(run)
    return [group for r in runs for group in _connected(r)]


def _connected(run):
    """Split a run into groups that share no fighter, in drawing order."""
    groups = []
    for pair in run:
        who = {pair["one"]["order"], pair["two"]["order"]}
        joined = [g for g in groups if g["who"] & who]
        if not joined:
            groups.append({"who": who, "pairs": [pair]})
            continue
        first = joined[0]
        for other in joined[1:]:
            first["who"] |= other["who"]
            first["pairs"] += other["pairs"]
            groups.remove(other)
        first["who"] |= who
        first["pairs"].append(pair)
    for group in groups:
        group["pairs"].sort(key=lambda p: (p["row"], p["col"]))
    return [g["pairs"] for g in groups]


def _closed_between(sheet, previous, pair):
    left = min(previous["col"], pair["col"]) - 1
    right = max(previous["right"], pair["right"])
    for r in range(previous["row"] + 1, pair["row"]):
        for c in range(max(0, left), min(right + 1, sheet.ncols)):
            if _key(sheet.at(r, c)) in _CLOSERS:
                return True
    return False


def _score_columns(sheet, run, report, where):
    """{printed key: column} from the poule's own header row, or {}.

    The header is the strip of order numbers a poule table is headed with. It
    is taken as a strip - a run of consecutive labelled columns - because the
    same row often carries the bracket's seeds and scores further right, and
    picking labels out of the whole row mixes the two strips together.
    """
    top = min(p["row"] for p in run)
    left = min(p["col"] for p in run) + 3
    wanted = set()
    for pair in run:
        if pair["labelled"]:
            wanted.add(_label_key(sheet.at(pair["row"], pair["col"] - 1)))
            wanted.add(_label_key(sheet.at(pair["row"], pair["col"] + 1)))
    wanted.discard("")
    if not wanted:
        return {}

    for r in range(top, max(-1, top - 6), -1):
        for strip in _label_strips(sheet, r, left):
            if wanted <= set(strip):
                return strip
    report.notes.setdefault("no_score_header", []).append(
        f"{where}: a poule with no column header; its two scores are read "
        f"left to right")
    return {}


def _label_strips(sheet, row, left):
    """[{key: column}] for each run of consecutive labelled cells on one row."""
    strips, current, previous = [], {}, None
    for c in range(max(0, left), sheet.ncols):
        key = _label_key(sheet.at(row, c))
        if not key:
            continue
        if previous is not None and c != previous + 1:
            if len(current) >= 2:
                strips.append(current)
            current = {}
        current.setdefault(key, c)
        previous = c
    if len(current) >= 2:
        strips.append(current)
    return strips


def _bout(sheet, pair, keys, slug, meta, counter, report, where,
          category, gender, kilos, bound, phase, poule):
    row, n1 = pair["row"], pair["col"]
    one, two = pair["one"], pair["two"]
    right = min(pair["right"], sheet.ncols)

    after = [(c, sheet.num(row, c)) for c in range(n1 + 3, right)
             if sheet.num(row, c) is not None]
    # The cell between the two names is a key only where it matches the key
    # before the first name. "A1 LELANT 3.0 LEPY 1.0" heads the pair with a
    # seed and then scores it, so its 3.0 is LELANT's score even though it also
    # happens to equal LEPY's order number.
    keyed = pair["labelled"] and _label_kind(sheet.at(row, n1 - 1)) == \
        _label_kind(sheet.at(row, n1 + 1)) != ""
    middle = [] if keyed else (
        [(n1 + 1, sheet.num(row, n1 + 1))]
        if sheet.num(row, n1 + 1) is not None else [])

    points, how = ("", ""), ""
    if keys and keyed:
        k1 = _label_key(sheet.at(row, n1 - 1))
        k2 = _label_key(sheet.at(row, n1 + 1))
        c1, c2 = keys.get(k1), keys.get(k2)
        if c1 is not None and c2 is not None:
            strip = range(min(keys.values()), max(keys.values()) + 1)
            stray = [c for c, _v in after if c not in (c1, c2) and c in strip]
            if stray:
                report.problem(
                    f"{where} row {row + 1}: {one['surname']} v {two['surname']} "
                    f"also prints a score in a column belonging to neither of "
                    f"them; only what is in their own columns is kept")
            points = (sheet.num(row, c1), sheet.num(row, c2))
            how = "header"
    if not how:
        # A score printed between the two names belongs to the first of them -
        # "DEROBILLARD 1.0 MIGNIER 3.0" - and that reading has to be tried
        # first, because the same row may carry a stray figure further right
        # that would otherwise be read as the pair of scores. It is only
        # believed where the middle figure cannot instead be the second
        # fighter's order number.
        interleaved = (middle and after
                       and (middle[0][1] != two["order"] or len(after) == 1))
        if interleaved:
            points, how = (middle[0][1], after[0][1]), "interleaved"
        elif len(after) >= 2:
            points, how = (after[0][1], after[1][1]), "left-to-right"
        elif not after and not middle:
            points, how = ("", ""), "unscored"
        elif len(after) == 1 and not middle and after[0][0] == n1 + 3:
            # "GLANEUR | | AMBAL | 3 par forfait": the score sits in the slot
            # after the second name, and the first fighter's slot is empty.
            points, how = ("", after[0][1]), "second-slot"
        else:
            report.problem(f"{where} row {row + 1}: {one['surname']} v "
                           f"{two['surname']} prints one score and this cannot "
                           f"say whose; stored unresolved")
            points, how = ("", ""), "ambiguous"

    spare = len(after) + len(middle) - (0 if how in ("unscored", "ambiguous")
                                        else 2 if how != "second-slot" else 1)
    if how in ("interleaved", "left-to-right", "second-slot") and spare > 0:
        report.notes.setdefault("spare_figures", []).append(
            f"{where} row {row + 1}: {one['surname']} v {two['surname']} prints "
            f"{spare} figure(s) this reading does not account for")

    red_points = _points(points[0])
    blue_points = _points(points[1])
    detail = ""
    for c in range(n1 - 1, right):
        note = sheet.note(row, c)
        if note:
            detail = note
            break

    winner = loser = ""
    status, came_from = "unresolved", ""
    decision = _decision(detail)
    if red_points != "" and blue_points != "":
        high, low = float(red_points), float(blue_points)
        if high != low:
            winner, loser = ((one, two) if high > low else (two, one))
            status, came_from = "decided", "scoresheet"
        else:
            report.notes.setdefault("drawn_scorelines", []).append(
                f"{where} row {row + 1}: {one['surname']} {red_points} - "
                f"{blue_points} {two['surname']}")

    return Bout(
        tournament=slug,
        bout_id=f"{slug}-{counter.next_bout():04d}",
        category=category, gender=gender,
        age_class=meta.get("age_class", ""),
        weight_kg=kilos, weight_bound=bound,
        phase=phase, poule=poule,
        red=_full(one), red_club=one["club"],
        blue=_full(two), blue_club=two["club"],
        red_points=red_points, blue_points=blue_points,
        winner_corner="",
        winner=_full(winner) if winner else "",
        loser=_full(loser) if loser else "",
        decision=decision, decision_detail=detail,
        status=status, result_source=came_from,
    )


def _points(value):
    """A score as the sheet meant it: 3.0 is "3", and nothing stays nothing."""
    return "" if value in ("", None) else f"{float(value):g}"


def _decision(detail):
    """How the bout ended, in the word the sheet printed beside the score.

    Only the printed word. These sheets print the bareme - 3 to the winner, 1 to
    a loser who finished, 0 to one who did not box, -1 to one thrown out - and a
    scoreline is not a verdict: rules.bout_points scores an abandon 3-1 exactly
    as it scores a points win, and a 3-0 is what the sheet gives both a forfeit
    and a fighter who was there and scored nothing. Reading a decision back out
    of those figures would tell a reader that a bout was uncontested on no more
    evidence than a zero - and seven of the fighters it did that to have points
    from other bouts of the same poule, so they were there and they fought.

    A word beside the score ("3 par forfait") is the sheet speaking, and that is
    read through the shared vocabulary. Anything else leaves decision empty.
    """
    return _decision_word(detail)


def _full(entry):
    return _collapse(f"{entry['surname']} {entry['given']}")


def _emit_placings(entries, slug, meta, report, counter, where,
                   category, gender, kilos, bound):
    ranked = [e for e in entries.values() if e["rank"]]
    seen = {}
    for entry in ranked:
        seen.setdefault(entry["rank"], []).append(entry["surname"])
    for rank, who in sorted(seen.items()):
        limit = 2 if rank == "3" else 1
        if len(who) > limit:
            report.problem(f"{where}: {len(who)} fighters share place {rank} "
                           f"({', '.join(who)}) - the sheet is contradictory")
    out = []
    for entry in sorted(ranked, key=lambda e: (int(e["rank"]), e["surname"])):
        out.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{counter.next_placing():04d}",
            category=category, gender=gender,
            age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound,
            rank=entry["rank"], medal=MEDALS.get(entry["rank"], ""),
            fighter=_full(entry), club=entry["club"],
            country=meta.get("country", ""),
            result_source="reported",
        ))
    unplaced = len(entries) - len(ranked)
    if unplaced:
        report.notes.setdefault("unplaced_entrants", {})[where] = unplaced
    return out


# --------------------------------------------------------- the ranked sheets

# "PLACE CLT" heads the 2007 weigh-in sheets, whose column is a seeding, not a
# result. It is listed so that those sheets are recognised as classifications
# and then thrown out by the repeated-placing check, rather than slipping past
# unrecognised and being read as a draw.
_FLAT_RANK = ("clt", "clt .", "clt.", "classement", "place", "place classement",
              "place clt", "clt place", "rang")
_FLAT_HEADERS = {
    "rank": _FLAT_RANK,
    "surname": ("nom", "noms"),
    "given": ("prenom", "prenoms"),
    "gender": ("sexe", "genre"),
    "club": ("association sportive", "as", "club", "association"),
    "weight": ("poids", "categorie de poids", "cat de poids", "categorie"),
    "kind": ("eq ind", "eq ind.", "eq/ind", "ind eq"),
}


def _flat_sheet(sheet, slug, meta, report, counter, classes):
    """Placings from a flat classification sheet, or None if it is not one."""
    columns = None
    for r in range(min(25, sheet.nrows)):
        keys = {c: _key(sheet.at(r, c)) for c in range(sheet.ncols)}
        if not any(k in _FLAT_RANK for k in keys.values()):
            continue
        if not any(k in ("nom", "noms") for k in keys.values()):
            continue
        columns = _map_columns(keys)
        header_row = r
        break
    if columns is None or "surname" not in columns:
        return None

    where = sheet.name
    printed = ""
    gender_hint, _k, _b = _class_of(sheet.name)
    rows, per_class, unplaced, dropped, other, demos = [], {}, 0, 0, 0, 0
    current = ("", "", "", "")
    # The first class heading of a sheet sits ABOVE its first column header
    # ("JF - 48 KG", then "Clt. | N° de licence | Nom | ..."), so the scan
    # starts at the top of the sheet; only the mapped columns are believed,
    # which keeps the 2009 sheets' floating legend of weight labels out.
    edge = max(columns.values())

    for r in range(0, sheet.nrows):
        if r == header_row:
            continue
        keys = {c: _key(sheet.at(r, c)) for c in range(sheet.ncols)}
        if any(k in _FLAT_RANK for k in keys.values()) and \
                any(k in ("nom", "noms") for k in keys.values()):
            columns = _map_columns(keys)
            edge = max(columns.values())
            continue
        filled = [c for c in range(sheet.ncols) if sheet.at(r, c)]
        if not filled:
            continue
        # A heading row: a cell or two, inside the table's own columns, naming
        # a weight class. A stray legend parked to the right of the table is
        # not one, however much it looks like "- 48 kg".
        if len(filled) <= 2 and columns["surname"] not in filled \
                and filled[0] <= edge:
            text = sheet.at(r, filled[0])
            gender, kilos, bound = _class_of(text, report)
            if kilos:
                printed = text
                if _OTHER_SPORT.search(text):
                    current = ("", "", "", "")
                    other += 1
                    continue
                current = (_category(gender or gender_hint, kilos, bound,
                                     meta.get("age_class", "")),
                           gender or gender_hint, kilos, bound)
                classes.setdefault(current[0], text)
            continue

        if r < header_row:
            continue
        surname = sheet.at(r, columns["surname"])
        if not surname or _key(surname) in ("nom", "total"):
            continue
        if "kind" in columns and _key(sheet.at(r, columns["kind"])) not in ("i", ""):
            dropped += 1
            continue
        line = " ".join(sheet.at(r, c) for c in range(sheet.ncols))
        if _OTHER_SPORT.search(line):
            other += 1
            continue
        if _DEMO.search(line):
            demos += 1
            continue

        category, gender, kilos, bound = current
        if "weight" in columns:
            text = sheet.at(r, columns["weight"]) or printed
            printed = text or printed
            g, k, b = _class_of(text, report)
            if k:
                gender_cell = ""
                if "gender" in columns:
                    gender_cell = {"f": "Women", "m": "Men", "h": "Men"}.get(
                        _key(sheet.at(r, columns["gender"])), "")
                gender = gender_cell or g or gender_hint
                kilos, bound = k, b
                category = _category(gender, kilos, bound,
                                     meta.get("age_class", ""))
                classes.setdefault(category, text)
        if not category:
            report.problem(f"{where} row {r + 1}: {surname!r} sits under no "
                           f"weight class and is skipped")
            continue

        rank = ""
        if "rank" in columns:
            value = sheet.num(r, columns["rank"])
            if value is not None and value == int(value) and 1 <= value <= 12:
                rank = str(int(value))
        if not rank:
            unplaced += 1
            continue

        per_class.setdefault(category, {}).setdefault(rank, []).append(surname)
        given = sheet.at(r, columns["given"]) if "given" in columns else ""
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{counter.next_placing():04d}",
            category=category, gender=gender,
            age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound,
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=_collapse(f"{surname} {given}"),
            club=sheet.at(r, columns["club"]) if "club" in columns else "",
            country=meta.get("country", ""),
            result_source="reported",
        ))

    contradictory = 0
    for category, ranks in per_class.items():
        for rank, who in ranks.items():
            if len(who) > (2 if rank == "3" else 1):
                contradictory += 1
                report.problem(f"{where}: {len(who)} fighters share place {rank} "
                               f"in {category} ({', '.join(who[:6])})")
    if per_class and contradictory >= max(2, len(per_class) // 2):
        report.problem(f"{where}: most classes repeat their placings, so this is "
                       f"an entry list and not a classification - it is dropped")
        return []

    if unplaced:
        report.notes.setdefault("unplaced_entrants", {})[where] = unplaced
    if dropped:
        report.notes.setdefault("team_entries_dropped", {})[where] = dropped
    if other:
        report.notes["other_sport_dropped"] = \
            report.notes.get("other_sport_dropped", 0) + other
        report.problem(f"{where}: {other} row(s) name another sport (canne de "
                       f"combat, chausson, baton or savate forme) and are dropped")
    if demos:
        report.notes["demonstrations_dropped"] = \
            report.notes.get("demonstrations_dropped", 0) + demos
    return rows


def _map_columns(keys):
    out = {}
    taken = set()
    for field, hints in _FLAT_HEADERS.items():
        for c, key in sorted(keys.items()):
            if c in taken or not key:
                continue
            if key in hints:
                out[field] = c
                taken.add(c)
                break
    return out


# ------------------------------------------------------------------ the PDFs

_CARD_CLASS = re.compile(r"^([FM])\s*(\+?)\s*(\d{2,3})$")
_CARD_RANK = re.compile(r"^(\d)\s{2,}(.*(?:champion|place).*)$", re.I)
_IDF_CLASS = re.compile(r"^([-+])\s*(\d{2,3})\s*KG\s+([FM])$", re.I)
_IDF_ROW = re.compile(r"^(\d{1,2})\s+(\S.*?)\s{2,}(\S.*)$")
_TEAM = re.compile(r"\b[ée]quipes?\b|par\s*[ée]quipes?", re.I)


def _read_pdf(path, slug, meta, tournament, report):
    import subprocess

    try:
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=90).stdout
    except (OSError, subprocess.SubprocessError) as e:
        report.problem(f"pdftotext could not read the PDF: {e}")
        return []
    lines = text.splitlines()
    report.read = len(lines)
    if not [l for l in lines if l.strip()]:
        report.problem("the PDF has no text layer - it is a scan, and this "
                       "adapter does not do OCR")
        return []

    head = " ".join(lines[:12])
    if _TEAM.search(head) and not any(_CARD_CLASS.match(l.strip()) for l in lines):
        report.problem("a championnat par equipes sheet: it ranks universities, "
                       "names no fighter, and cannot enter a fighter-keyed "
                       "schema without inventing the bouts behind each score")
        return []

    counter = _Counter()
    classes = {}
    if any(_IDF_CLASS.match(l.strip()) for l in lines):
        rows = _pdf_ranked(lines, slug, meta, report, counter, classes)
    elif any(_CARD_CLASS.match(l.strip()) for l in lines):
        rows = _pdf_cards(lines, slug, meta, report, counter, classes)
    else:
        report.problem("no weight-class heading this adapter recognises "
                       "('F 50' or '-55 KG F') - it is not one of these sheets")
        return []

    report.notes["classes"] = classes
    for line in lines[:6]:
        start, end, city = _dateline([line])
        if start:
            tournament.start_date = tournament.start_date or start
            tournament.end_date = tournament.end_date or end
            tournament.city = tournament.city or city
            break
    return rows


def _not_savate(report, line):
    key = ("demonstrations_dropped" if _DEMO.search(line)
           else "other_sport_dropped")
    report.notes[key] = report.notes.get(key, 0) + 1
    if key == "other_sport_dropped":
        report.problem(f"a line naming another sport is dropped: {line.strip()!r}")


def _pdf_cards(lines, slug, meta, report, counter, classes):
    """The 2022 podium sheet: name, then rank and title, then university."""
    rows = []
    current = ("", "", "", "")
    previous = ""
    per_class = {}
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if re.search(r"podium\s*[ée]quipe", line, re.I):
            break
        if _DEMO.search(line) or _OTHER_SPORT.search(line):
            _not_savate(report, line)
            previous = ""
            continue
        found = _CARD_CLASS.match(line)
        if found:
            gender = "Women" if found.group(1).upper() == "F" else "Men"
            bound = "over" if found.group(2) else "under"
            current = (_category(gender, found.group(3), bound,
                                 meta.get("age_class", "")),
                       gender, found.group(3), bound)
            classes.setdefault(current[0], line)
            previous = ""
            continue
        found = _CARD_RANK.match(line)
        if not found:
            previous = line
            continue
        if not current[0]:
            report.problem(f"a podium card before any weight heading: {line!r}")
            previous = ""
            continue
        name = previous
        previous = ""
        if not name or _CARD_CLASS.match(name) or len(name) < 3:
            report.problem(f"{current[0]}: no name printed above "
                           f"{found.group(2)!r}; the card is skipped")
            continue
        club = ""
        for ahead in lines[i + 1:i + 4]:
            if ahead.strip():
                club = ahead.strip()
                break
        if _CARD_RANK.match(club) or _CARD_CLASS.match(club):
            club = ""
        rank = found.group(1)
        per_class.setdefault(current[0], []).append(rank)
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{counter.next_placing():04d}",
            category=current[0], gender=current[1],
            age_class=meta.get("age_class", ""),
            weight_kg=current[2], weight_bound=current[3],
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=name, club=club,
            country=meta.get("country", ""),
            result_source="reported",
        ))
    for category, ranks in per_class.items():
        if len(set(ranks)) != len(ranks):
            report.problem(f"{category}: a placing is printed twice {ranks}")
    report.notes["one_bronze_per_class"] = (
        "this sheet awards a single third place per class, not savate's usual "
        "two - that is what the document prints")
    return rows


def _pdf_ranked(lines, slug, meta, report, counter, classes):
    """The Ile-de-France sheet: '-55 KG F', then rank, fighter, university."""
    rows = []
    current = ("", "", "", "")
    per_class = {}
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if _DEMO.search(line) or _OTHER_SPORT.search(line):
            _not_savate(report, line)
            continue
        found = _IDF_CLASS.match(line.strip())
        if found:
            gender = "Women" if found.group(3).upper() == "F" else "Men"
            bound = "over" if found.group(1) == "+" else "under"
            current = (_category(gender, found.group(2), bound,
                                 meta.get("age_class", "")),
                       gender, found.group(2), bound)
            classes.setdefault(current[0], line.strip())
            continue
        found = _IDF_ROW.match(line.strip())
        if not found:
            continue
        if not current[0]:
            continue
        rank, fighter, club = found.group(1), found.group(2), found.group(3)
        if not re.search(r"[A-Za-zÀ-ÿ]{2}", fighter):
            continue
        per_class.setdefault(current[0], []).append(rank)
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{counter.next_placing():04d}",
            category=current[0], gender=current[1],
            age_class=meta.get("age_class", ""),
            weight_kg=current[2], weight_bound=current[3],
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=_collapse(fighter), club=_collapse(club),
            country=meta.get("country", ""),
            result_source="reported",
        ))
    for category, ranks in per_class.items():
        if len(set(ranks)) != len(ranks):
            report.problem(f"{category}: a placing is printed twice {ranks}")
    return rows
