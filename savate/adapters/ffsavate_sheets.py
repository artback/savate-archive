"""The FFSavate result sheets the other three French adapters do not read.

The French federation has no house style. Between 2009 and 2026 its competition
secretaries published results as a dozen different pieces of paper, and
`ffsavate_finals`, `ffsavate_finals_wide` and `ffsavate_bouts` between them read
three of those shapes. This module reads the rest. It is one adapter and not
twelve because they are twelve renderings of the same three facts - who fought
whom, who won, how - by one federation, and splitting them by typography would
leave the archive with a dozen modules nobody could tell apart.

So it is a sniffer in front of a dozen small readers. `_sniff` names the layout,
`_LAYOUTS` maps that name to its reader, and a manifest entry may name the
layout itself (`"layout": "poule_table"`) where a guess would be a gamble. The
Report always says which layout ran: a wrong guess should be visible, not silent.

What every reader here refuses to do, because these documents invite all three.

*It does not name a corner.* Five of these layouts print explicit ROUGE and BLEU
columns, so red and blue are read off the page where the page has them and are
printed order where it does not. Not one of them says which corner WON, so
`winner_corner` is empty on every row this module produces. A named winner with
no corner is the normal, supported state.

*It does not turn an order into a result.* Four of these layouts - the wide
two-corner tables, the running order, the cadets sheet - print a pairing and a
verdict TYPE ("majorité", "HC3") without ever saying who it went to. Those bouts
are stored unresolved with their decision recorded, which is the whole fact the
document states. The red corner is not the winner; it is whoever the secretary
typed first, and on these sheets that is sometimes the loser.

*It does not promote a semi-final to a podium.* Placings are emitted only where
the document says the bout was a final, or prints a rank, or prints the word
"Champion". Three of these sheets are semi-finals whose file name says so and
whose body does not, and a round read off a URL is not a fact about a bout.

Two things this module reads that nothing else in the archive does. The French
ordinal rounds - QUART DE FINALE, HUITIEME DE FINALE, ¼ finale, 1/2F - so a bout
lands on the round it was fought in rather than under "final"; and the series
(Elite A, Elite B, Premium, Espoir), which the federation runs as parallel
competitions, so an Elite A -65 kg and an Elite B -65 kg on one sheet do not
collapse into one category.
"""

import re
import unicodedata

from savate.schema import MEDALS, Bout, Placing, Report, Tournament

NAME = "ffsavate_sheets"
DESCRIPTION = "FFSavate sheets: series finals, round tables, poule rankings, palmarès"


# --------------------------------------------------------------------------
# The federation's vocabulary
# --------------------------------------------------------------------------

# How a bout ended, in the words these sheets print. Order matters: the first
# match wins, so the specific forms come before the general ones. "HC" is hors
# combat - the fighter could not continue - which the schema calls an abandon;
# savate.normalize.decision() does not know the abbreviation, nor "jet de
# l'éponge", which is why this list lives here.
_VERDICTS = [
    ("Disqualification", "disqualification",
     r"disqualifi\w*|d[ée]classement|\bdisqua\b|\bdisq\b"),
    ("Forfait", "forfait", r"forfaits?\b|\bforf\b|\bw\.?\s?o\.?(?=\W|$)"),
    ("Jet de l'éponge", "abandon", r"jet\s+(?:de\s+)?l?[’']?\s*[ée]ponge"),
    ("Hors combat", "abandon", r"hors\s+combat|\bh\.?\s?c\.?(?=\W|\d|$)"),
    ("Abandon", "abandon", r"abandons?\b"),
    ("Arrêt", "abandon", r"arr[êe]ts?\b"),
    ("Blessure", "abandon", r"blessure"),
    ("KO", "abandon", r"\bk\.?\s?o\.?(?=\W|$)"),
    ("Unanimité", "points", r"unanimit[ée]s?\b|\buna\b"),
    ("Majorité", "points", r"majorit[ée]s?\b|\bmajo\b"),
    ("Partage", "points", r"partages?\b"),
]
_VERDICT_AT = [(printed, decision, re.compile(pattern, re.I))
               for printed, decision, pattern in _VERDICTS]

# What may sit in front of the verdict: "Victoire à l'unanimité", "Par Forfait",
# "A l’Unanimité", and the 2013 sheet that prints "Victoire à à l’unanimité".
_PREAMBLE = re.compile(
    r"(?:\bvictoire\b\s*)?"
    r"(?:\bpar\b\s+|\bau\b\s+|\b[àa]\b\s+(?:\b[àa]\b\s+)?(?:\bla\b\s+|l[’']\s*)?"
    r"|l[’']\s*)*$", re.I)

# What may follow it: the round it was stopped in - "4e rep", "3ème reprise",
# "2°", or the bare "3" of "HC3". Kept inside the printed verdict, never as a
# separate fact: no other source in this archive records one.
_QUALIFIER = re.compile(
    r"^\s*\d{1,2}\s*(?:[°ºªe]|[èé]?me|[èe]re)?\.?\s*(?:rep\w*|round|reprise)?\s*$",
    re.I)

# The rounds, most specific first. schema.phase_of() cannot be used on these
# sheets: its substring fallback sees "finale" inside "HUITIEME DE FINALE" and
# files a round of sixteen as a final.
_PHASES = [
    ("bronze", r"petite\s+finale|3\s*[èe]?me\s+place|troisi[èe]me\s+place"),
    ("poule", r"tours?\s+de\s+poules?|\bpoules?\b"),
    ("r32", r"seizi[èe]mes?\s+de\s+finale|\b1\s*/\s*16\b"),
    ("r16", r"huiti[èe]mes?\s+de\s+finale|\b1\s*/\s*8\b"),
    ("quarter", r"quarts?\s+de\s+finale|¼\s*(?:de\s*)?finale|\b1\s*/\s*4\b|\bquarts?\b"),
    ("semi", r"demi[-\s]?finales?|\b1\s*/\s*2\s*f|\bdemis?\b"),
    ("final", r"\bfinales?\b"),
]
_PHASE_AT = [(phase, re.compile(pattern, re.I)) for phase, pattern in _PHASES]

# A round printed as the second token of a competitor line: "F52 1/2F JANOLI".
_LEAD_PHASE = re.compile(
    r"^\s*(¼\s*(?:de\s*)?finales?|1\s*/\s*2\s*F(?:inales?)?"
    r"|1\s*/\s*(?:4|8|16)\s*(?:de\s*)?finales?|demi[-\s]?finales?"
    r"|quarts?(?:\s+de\s+finale)?|huiti[èe]mes?(?:\s+de\s+finale)?"
    r"|tour\s+de\s+poule|finales?)\b", re.I)

# A word edge, for a vocabulary that has to survive these text layers. \b is
# not it: poppler hands back "16JUNIOR" where a table's N° cell runs into its
# TYPE cell, and \b sees no boundary between a digit and a letter, so the word
# JUNIOR printed in its own column becomes invisible and a junior bout is filed
# as a senior one. A letter is what may not sit next to one of these words.
_EDGE = r"(?<![^\W\d_])"
_EDGE_ = r"(?![^\W\d_])"


def _word(*forms):
    return "|".join(f"{_EDGE}(?:{form}){_EDGE_}" for form in forms)


# The parallel competitions the federation runs. A series is a label, never an
# age class - ffsavate_bouts drew that line and this keeps it.
_SERIES = [
    ("Elite A", _word(r"[ée]lite\s*[-–]?\s*a", r"elt\s*a")),
    ("Elite B", _word(r"[ée]lite\s*[-–]?\s*b", r"elt\s*b")),
    ("Premium", _word(r"premium")),
    ("2e Série", _word(r"2\s*[èe]?(?:me|e)?\s*s[ée]ries?",
                       r"deuxi[èe]mes?\s+s[ée]ries?")),
    ("1re Série", _word(r"1\s*[èe]?re?\s*s[ée]ries?",
                        r"premi[èe]res?\s+s[ée]ries?")),
]
_AGES = [
    ("Benjamin", _word(r"benjamins?", r"benjamines?", r"ben")),
    ("Minime", _word(r"minimes?", r"min")),
    ("Cadet", _word(r"cadets?", r"cadettes?", r"cad")),
    ("Junior", _word(r"juniors?", r"jun(?:ior)?")),
    ("Espoir", _word(r"espoirs?")),
    ("Veteran", _word(r"v[ée]t[ée]rans?")),
    ("Senior", _word(r"seniors?r?")),
]
_SERIES_AT = [(label, re.compile(pattern, re.I)) for label, pattern in _SERIES]
_AGES_AT = [(label, re.compile(pattern, re.I)) for label, pattern in _AGES]

# The class code: F48, M150, F42J. A trailing J marks the youth ladders.
_CODE = re.compile(r"\b([FM])\s?(\d{2,3})(J?)\b")

# Above this the code is a sentinel for the open class, not a weight - the same
# reading ffsavate_finals makes, and reported on every read the same way.
_SENTINEL = 90

# The club's département, as these sheets print it: "US CRETEIL (94)".
_DEPT = re.compile(r"^\(\s*(\d{2,3})\s*\)$")

# Runs of the dot leaders that hold the 2009-2013 sheets' columns apart.
_LEADER = re.compile(r"[.…](?:\s*[.…]){2,}")

# Lines that are the page, not the result.
_NOISE = re.compile(
    r"^\s*(?:www\.ffsavate|f[ée]d[ée]ration\s+fran[çc]aise|49[,]?\s*,?\s*rue|"
    r"secteur\s+comp[ée]titions?|cnc\b|cnc/|rd/cnc|plateaux\s*/|r[ée]f\s*:|"
    r"ffsavate\s*[-–]|ffsbf\b|"
    r"livret\b|page\s+\d+|t[ée]l[ée]phone|https?:|cp/jk)", re.I)

# The words a heading may be made of, once its class code is taken out. A line
# whose remainder is anything else is a competitor and not a heading, which is
# what stops a club called BF ALLONNES 60 from being read as a weight class.
_STRUCTURAL = set("""
elite élite a b premium espoir espoirs junior juniors cadet cadets cadette
cadettes minime minimes benjamin benjamins benjamine benjamines veteran
veterans vétéran vétérans senior seniors serie série series séries 1ere 1re
2eme 2e 3eme 3e masculin masculine masculins masculines feminin féminin
feminine féminine feminins féminins femmes hommes dames quart quarts huitieme
huitième huitiemes huitièmes seizieme seizième demi demie demis finale finales
de du des la le les et en resultat resultats résultat résultats tour tours
poule poules partie premiere première deuxieme deuxième troisieme troisième
mouches mouche coqs coq plumes plume legeres légères legers légers moyens
moyennes moyen moyenne lourds lourdes lourd mi super s m f grande enceinte sol
dimanche samedi vendredi
""".split())

# A demonstration is not a bout: it has no result and never had one.
_DEMO = re.compile(r"\bd[ée]mo(?:nstration)?s?\b|\bexhibition\b|\bhors\s+comp[ée]tition\b",
                   re.I)

# Sports the FFSavate governs that are not savate. A row naming one of them is
# dropped and counted, never filed as a savate bout.
#
# Two spellings are deliberately NOT in the row test. "Canne" on its own is in
# ASLM CANNES, which is a town; and "Savate Forme" is in Savate Forme Body
# Boxing, which is a club that enters ordinary minimes. Both were dropping real
# competitors. They are only recognised in a heading, where a discipline is
# what such a word would mean.
_OTHER_SPORT = re.compile(
    r"canne\s+de\s+combat|canne\s+d[’']armes|\bb[âa]ton\b|\bchausson\b", re.I)
_OTHER_SPORT_HEADING = re.compile(
    r"canne\s+de\s+combat|canne\s+d[’']armes|\bb[âa]tons?\b|\bchaussons?\b|"
    r"\bsavate\s+forme\b|\bcannes?\s+(?:f|m|mixte)\b", re.I)


def _fold(text):
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _clean(text):
    return " ".join(str(text or "").split()).strip(" ,;:-–—")


def _verdict(text):
    """(decision, printed verdict, the text before it) for one printed line.

    The verdict has to end the line, give or take the round the bout was
    stopped in. A club called ARRET mid-line is not a result, and anchoring to
    the end is what keeps it from becoming one.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return "", "", ""
    best = None
    for printed, decision, pattern in _VERDICT_AT:
        for found in pattern.finditer(text):
            rest = text[found.end():]
            if rest.strip() and not _QUALIFIER.match(rest):
                continue
            head = text[:found.start()]
            lead = _PREAMBLE.search(head)
            start = lead.start() if lead else found.start()
            if best is None or start < best[0]:
                best = (start, decision, printed)
            break
    if best is None:
        return "", "", text
    start, decision, printed = best
    return decision, " ".join(text[start:].split()), text[:start].strip()


def _phase(text):
    """The round a heading names, or "" when it names none."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    for phase, pattern in _PHASE_AT:
        if pattern.search(text):
            return phase
    return ""


def _series(text):
    for label, pattern in _SERIES_AT:
        if pattern.search(str(text or "")):
            return label
    return ""


def _age(text):
    for label, pattern in _AGES_AT:
        if pattern.search(str(text or "")):
            return label
    return ""


def _category(letter, kilos, suffix, report, prefix=""):
    """The category fields for one class code.

    The prefix carries whatever the document said this competition was - a
    series, an age class. Without it an Elite A -65 kg and an Elite B -65 kg
    printed on one sheet share a label, and every index keyed on that label
    silently merges two different competitions.

    Two things the code says and this keeps. A code at or above the sentinel is
    not a weight, so no weight and no direction is claimed for it and the
    category carries the code as printed - "Elite A Women F100" - with a youth
    suffix in the same position the weighted rows use it, "Men M150 (J)". The
    sheets print neither the word "open" nor a "+", and reading either off a
    number was the archive stating what the federation did not.

    And the J the federation puts on its youth ladders is kept, because on four
    of these sheets it is the ONLY age marker on the page: without it a cadet
    F48J bout is filed as "Women -48 kg" and is indistinguishable from a senior
    one. It is kept as the letter the document prints - not expanded to cadet,
    minime or benjamin, which the code does not say.
    """
    gender = "Women" if str(letter).upper() == "F" else "Men"
    head = f"{prefix} " if prefix else ""
    code = f"{str(letter).upper()}{kilos}{suffix}"
    if suffix:
        seen = report.notes.setdefault("youth_classes", [])
        if code not in seen:
            seen.append(code)
    if kilos >= _SENTINEL:
        seen = report.notes.setdefault("sentinel_classes", [])
        if code not in seen:
            seen.append(code)
        # The suffix keeps the same form the weighted rows use, so a sentinel
        # cadet class and a weighted one are told apart the same way.
        tail = f" ({suffix})" if suffix else ""
        bare = f"{str(letter).upper()}{kilos}"
        return {"category": f"{head}{gender} {bare}{tail}", "gender": gender,
                "weight_kg": "", "weight_bound": ""}
    tail = f" ({suffix})" if suffix else ""
    return {"category": f"{head}{gender} -{kilos} kg{tail}", "gender": gender,
            "weight_kg": str(kilos), "weight_bound": "under"}


def _class_of(text, report, prefix=""):
    """(fields, code) for the first class code in a string, or (None, "")."""
    found = _CODE.search(str(text or ""))
    if not found:
        return None, ""
    fields = _category(found.group(1), int(found.group(2)),
                       found.group(3).upper(), report, prefix)
    return fields, (f"{found.group(1).upper()}{found.group(2)}"
                    f"{found.group(3).upper()}")


def _prefix(series, age, fallback=""):
    """The label prefix: the age class the sheet named, else its series."""
    return age or series or fallback or ""


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------

class _Doc:
    """One fetched document, in the two forms these readers need.

    `rows` are word boxes grouped into visual lines, because half of these
    layouts are tables whose meaning is in the column a word sits in. `spaced`
    puts the column gaps back into a line as double spaces, because the other
    half are laid out with tab stops and read perfectly well as text.
    """

    def __init__(self, source, report):
        from savate import pdf, sources

        self.report = report
        self.path = sources.fetch(source)
        head = self.path.open("rb").read(5)
        self.is_pdf = head[:4] == b"%PDF"
        self.html = ""
        self.words = []
        self.rows = []
        self.gap = 8.0
        if not self.is_pdf:
            self.html = self.path.read_text(encoding="utf-8", errors="replace")
            return
        self.words = pdf.words(self.path)
        self.rows = [line for line in pdf.rows(self.words) if line]
        gaps = sorted(line[i + 1].x0 - line[i].x1
                      for line in self.rows for i in range(len(line) - 1))
        if gaps:
            near = [g for g in gaps if g > -2]
            middle = near[len(near) // 4] if near else 4.0
            self.gap = max(4.0, min(24.0, middle * 3.0 + 2.0))

    @staticmethod
    def text(words):
        return " ".join(w.text for w in words)

    def spaced(self, words):
        """The line as text, with the column gaps kept as double spaces."""
        out = []
        for at, word in enumerate(words):
            if at:
                out.append("  " if word.x0 - words[at - 1].x1 > self.gap else " ")
            out.append(word.text)
        return "".join(out)

    def dated(self):
        """(ISO date, city) from the sheet's own dated venue line, or ("", "")."""
        from savate import normalize as norm

        for words in self.rows[:14]:
            when, city, _dept = norm.dateline(self.text(words))
            if when:
                return when, city
        return "", ""

    def year(self):
        for words in self.rows[:14]:
            found = re.search(r"\b(19|20)\d{2}\b", self.text(words))
            if found:
                return found.group(0)
        return ""

    def declared_age(self):
        """(age class, the line that names it) from the sheet's own banner.

        The minimes podium sheet prints no age class on any row: its classes
        are F42J..M150J and the only word for what the J is stands in the
        footer of every page, "FFSAVATE - Résultat championnat Avenir minime
        2026". That is the document stating it, in the place documents state
        things that govern a whole sheet, so it is read - and only from a line
        the federation set as its own header or footer, never from a line that
        could be a competitor.
        """
        for words in list(self.rows[:3]) + list(self.rows[-3:]):
            text = self.text(words)
            if not re.search(r"ffsavate|f[ée]d[ée]ration|r[ée]sul", text, re.I):
                continue
            age = _age(text)
            if age:
                return age, _clean(text)
        return "", ""


# --------------------------------------------------------------------------
# Columns, for the layouts that are tables
# --------------------------------------------------------------------------

def _peaks(lines, share=0.5, tolerance=4.0):
    """The x each column of a table starts at, from the rows themselves.

    A table's header is often set somewhere else than its data - centred over a
    left-aligned column, wrapped across three lines - so the columns are taken
    from where the data actually starts, and the header is only used to give
    each one a name. Word starts are clustered rather than matched exactly:
    poppler reports the same column as 31.9 on one row and 32.1 on the next,
    and an exact match finds no column at all.
    """
    if not lines:
        return []
    points = sorted((w.x0, at) for at, line in enumerate(lines) for w in line)
    clusters = []
    for x, row in points:
        if clusters and x - clusters[-1]["at"] <= tolerance:
            clusters[-1]["rows"].add(row)
        else:
            clusters.append({"at": x, "rows": {row}})
    wanted = max(2, int(len(lines) * share))
    return [round(c["at"], 1) for c in clusters if len(c["rows"]) >= wanted]


# The words a header uses to name a field. Looked for anywhere in a header
# word, not only at its front: one of these sheets prints "BleuCLUB" where the
# blue corner's PRENOM cell runs into its CLUB cell.
_FIELD_WORD = re.compile(r"(nom|pr[ée]nom|club|d[ée]cision|r[ée]sultat|cat[ée]?\b|"
                         r"poids|type|niveau|vainqueur)", re.I)


def _header_groups(header, gap, columns=()):
    """[(x, printed text)] - the header's words grouped into its own columns.

    Two headers in this pile overlap their own cells - "PRENOM Rou" runs under
    "CLUB Rouge" - so a group is also cut at any word that names a field AND
    sits over a column of its own. Without the second half of that test the
    2e série sheet's single "Nom Prénom 1" cell would be cut in two.
    """
    groups = []
    for word in sorted(header, key=lambda w: w.x0):
        start = groups[-1][0] if groups else -1e9
        split = (_FIELD_WORD.search(word.text)
                 and any(start + 5 < c and abs(word.x0 - c) <= 60
                         for c in columns))
        if groups and not split and word.x0 - groups[-1][1] <= gap:
            groups[-1][1] = max(groups[-1][1], word.x1)
            groups[-1][2].append(word.text)
        else:
            groups.append([word.x0, word.x1, [word.text]])
    return [(round(x0, 1), " ".join(words)) for x0, _x1, words in groups]


def _align(groups, columns, penalty=300.0, reach=100.0):
    """Match header cells to data columns in order, left to right.

    Nearest-column matching goes wrong on exactly the sheets that need help: a
    header centred over a wide column is nearer its neighbour, and one misread
    label shifts every column after it. Matching in order instead lets a data
    column go unlabelled (it is a continuation of the one before) and lets a
    header cell find no column at all (it names one with nothing under it),
    and picks whichever reading moves the labels least.
    """
    rows, cols = len(groups), len(columns)
    best = [[float("inf")] * (cols + 1) for _ in range(rows + 1)]
    back = [[None] * (cols + 1) for _ in range(rows + 1)]
    best[0][0] = 0.0
    for i in range(rows + 1):
        for j in range(cols + 1):
            here = best[i][j]
            if here == float("inf"):
                continue
            if j < cols and here < best[i][j + 1]:
                best[i][j + 1], back[i][j + 1] = here, ("skip", i, j)
            if i < rows and here + penalty < best[i + 1][j]:
                best[i + 1][j], back[i + 1][j] = here + penalty, ("new", i, j)
            if i < rows and j < cols and abs(groups[i][0] - columns[j]) <= reach:
                # Squared, so that one badly placed label is never traded for
                # several slightly worse ones: a header that has drifted far
                # from its column is far more likely to name a column that is
                # not there at all.
                cost = here + (groups[i][0] - columns[j]) ** 2 / 100.0
                if cost < best[i + 1][j + 1]:
                    best[i + 1][j + 1], back[i + 1][j + 1] = cost, ("match", i, j)
    labels, extra = {}, []
    i, j = rows, cols
    while back[i][j] is not None:
        move, pi, pj = back[i][j]
        if move == "match":
            labels[columns[pj]] = groups[pi][1]
        elif move == "new":
            extra.append(groups[pi])
        i, j = pi, pj
    return labels, extra


def _table_columns(doc, header, data):
    """([column x], {x: (what it holds, which of that kind)}) for one table.

    Columns come from the data, because a header is often set somewhere else
    than the column it names. A header cell with nothing under it - the empty
    Club columns of the 2e série sheet - becomes a column of its own.
    """
    columns = _peaks(data, share=0.8)
    if not columns:
        return [], {}
    groups = [g for g in _header_groups(header, doc.gap, columns)
              if _column_kind(_fold(g[1]))]
    labels, extra = _align(groups, columns)
    for x, text in extra:
        if any(abs(x - c) <= 14 for c in columns):
            continue
        columns.append(x)
        labels[x] = text
    columns.sort()
    # Which corner a name or club column belongs to is decided by where it sits,
    # not by how many of its kind came before it: one of these sheets prints the
    # red corner's whole name in one cell and the blue corner's in two, and
    # counting each kind on its own then hands the blue surname to the red.
    kinds, corner = {}, 0
    for x in columns:
        kind = _column_kind(_fold(labels.get(x, "")))
        if not kind:
            continue
        if kind in ("surname", "name"):
            corner += 1
            kinds[x] = ("surname", corner)
        elif kind in ("given", "club"):
            kinds[x] = (kind, max(corner, 1))
        else:
            kinds[x] = (kind, 1)
    # A column the header does not name is not dropped, it is folded into the
    # one on its left: the bout number belongs with the class code it precedes,
    # and "de poule" belongs with the "Tour" it continues.
    return [x for x in columns if x in kinds], kinds


def _cells(line, columns):
    """{column x: the words that sit under it}, judged on each word's midpoint."""
    out = {x: [] for x in columns}
    for word in line:
        at = 0
        for index, x in enumerate(columns):
            if word.middle >= x - 1.0:
                at = index
        out[columns[at]].append(word)
    return out


def _joined(cells, x):
    return _clean(" ".join(w.text for w in cells.get(x, [])))


# --------------------------------------------------------------------------
# Reading one competitor line
# --------------------------------------------------------------------------

def _dept_of(words):
    """The département at the end of a run of words, and the run without it."""
    if words and _DEPT.match(words[-1].text):
        return _DEPT.match(words[-1].text).group(1), words[:-1]
    return "", list(words)


def _first_words(text, count):
    """The first `count` words of a string, with its own spacing kept."""
    if count <= 0:
        return ""
    end, seen = 0, 0
    for found in re.finditer(r"\S+", text):
        seen += 1
        end = found.end()
        if seen == count:
            break
    return text[:end]


def _cut_verdict(text):
    """Like _verdict, but the text it hands back keeps its column spacing.

    _verdict works on a squeezed line because the vocabulary is easier to match
    there; the readers that split on column gaps need those gaps back.
    """
    decision, printed, head = _verdict(text)
    if not printed:
        return decision, printed, text
    return decision, printed, _first_words(text, len(head.split()))


def _boundary(blocks, gap=8.0):
    """The x the club column starts at, from the columns the block's lines share.

    These sheets set every block to its own tab stops, so there is no
    document-wide answer - but the two lines of one bout are always set to the
    same stops. A word-start that appears on every line of the block is a
    column; the club starts at the third of them, or at the second where the
    surname and the given name share one.
    """
    blocks = [line for line in blocks if line]
    if len(blocks) < 2:
        return None
    starts = [sorted({round(w.x0, 1) for w in line}) for line in blocks]
    shared = [x for x in starts[0]
              if all(any(abs(x - y) <= 3 for y in other) for other in starts[1:])]
    if len(shared) < 2:
        return None
    for index in [2, 1] + list(range(3, len(shared))):
        if index >= len(shared):
            continue
        cut = shared[index]
        ok, widest = True, 0.0
        for line in blocks:
            head = [w for w in line if w.x0 < cut - 1.5]
            tail = [w for w in line if w.x0 >= cut - 1.5]
            dept, tail = _dept_of(tail)
            if not head or not tail or len(head) > 5:
                ok = False
                break
            # A column boundary is a gap, not a coincidence. Two words that
            # happen to start at the same x on both lines - "(63)" under "F" -
            # sit flush against what precedes them and are not a column.
            #
            # The gap is required of the BLOCK and not of every line in it,
            # because a long enough cell closes it: "BRISSO Anne-Laure" reaches
            # to within 5.2pt of the club column that the line above it starts
            # 15.3pt clear of. Demanding the gap on both lines rejected the real
            # column there and cut the bout at the given name instead, filing
            # two competitors under their bare surnames with their given names
            # inside the club. So: no line may sit flush against the cut, and at
            # least one must stand clear of it.
            space = tail[0].x0 - head[-1].x1
            if space < 1.5:
                ok = False
                break
            widest = max(widest, space)
        if ok and widest >= gap:
            return cut
    return None


def _split_gap(words):
    """(name, club) split at the widest gap, for a line with no other clue."""
    if len(words) < 2:
        return _clean(" ".join(w.text for w in words)), ""
    gaps = [(round(words[i + 1].x0 - words[i].x1, 2), i)
            for i in range(len(words) - 1)]
    _width, at = max(gaps)
    return (_clean(" ".join(w.text for w in words[:at + 1])),
            _clean(" ".join(w.text for w in words[at + 1:])))


_PAREN_CLUB = re.compile(r"^(.+?)\s*\(\s*([^)]*[A-Za-zÀ-ÿ][^)]*)\s*\)\s*$")
_DASH_CLUB = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$|^(.+?)[-–—]\s+(.+)$")


def _paren_club(text):
    found = _PAREN_CLUB.match(text)
    if found and not re.fullmatch(r"\d{2,3}", found.group(2).strip()):
        return _clean(found.group(1)), _clean(found.group(2))
    return None


def _dash_club(text):
    found = _DASH_CLUB.match(text)
    if not found:
        return None
    parts = [p for p in found.groups() if p is not None]
    return _clean(parts[0]), _clean(parts[1])


def _block_mode(lines):
    """Which clue separates name from club on EVERY line of this block.

    Decided for the block and not line by line, deliberately. One sheet writes
    "DOUBLET Jonathan - SA MERIGNAC BF" and another writes "FIEUTELOT Nicolas
    Scheffler Boxing Club"; a dash split applied to the second would take the
    hyphen out of a name, and a column split applied to the first would cut the
    club in half. Requiring the clue on both lines is what tells them apart.
    """
    texts = [_clean(_Doc.text(_dept_of(line)[1])) for line in lines if line]
    if not texts:
        return None
    if all(_paren_club(_clean(_Doc.text(line))) for line in lines if line):
        return "paren"
    if all(_dash_club(text) for text in texts):
        return "dash"
    return None


def _competitor(words, mode, cut, report, where):
    """(name, club, département) for one competitor line, by its own clue.

    Four shapes, in the order that makes each unambiguous: a club in brackets,
    a club after a dash - both decided for the whole block - a club column
    found from the block's shared tab stops, and, when none of those is there,
    the widest gap on the line. A line that yields no club at all is kept whole
    as the competitor rather than cut somewhere plausible.
    """
    words = list(words)
    if not words:
        return "", "", ""
    text = _clean(_Doc.text(words))

    if mode == "paren":
        split = _paren_club(text)
        if split:
            return split[0], split[1], ""

    dept, body = _dept_of(words)
    plain = _clean(_Doc.text(body))

    if mode == "dash":
        split = _dash_club(plain)
        if split:
            return split[0], _strip_dept(split[1]), dept

    if cut is not None:
        head = [w for w in body if w.x0 < cut - 1.5]
        tail = [w for w in body if w.x0 >= cut - 1.5]
        if head and tail:
            return (_clean(_Doc.text(head)),
                    _strip_dept(_clean(_Doc.text(tail))), dept)

    name, club = _split_gap(body)
    if not club:
        report.problem(f"{where}: {text!r} has no column the club could sit in, "
                       f"so the line is kept whole as the competitor")
    return name, _strip_dept(club), dept


def _strip_dept(text):
    return _clean(re.sub(r"\(\s*\d{2,3}\s*\)\s*$", "", _clean(text)))


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------

def _structural(text):
    """Is what is left of a heading, once its class code is out, heading words?"""
    for token in re.split(r"[\s/]+", _fold(text)):
        token = token.strip("().,:;-–—¼½'’")
        if not token or token.isdigit():
            continue
        if token in _STRUCTURAL:
            continue
        if re.fullmatch(r"\d+(?:e|er|eme|ere|re)?", token):
            continue
        return False
    return True


def _heading(text):
    """{letter, kilos, suffix, series, age, phase} for a class heading, or None."""
    line = " ".join(str(text or "").split())
    if not line or len(line) > 90:
        return None
    found = _CODE.search(line)
    if not found:
        return None
    rest = (line[:found.start()] + " " + line[found.end():]).strip()
    rest = re.sub(r"^\d{1,2}\s*[/.)]\s*", "", rest).strip()
    if not _structural(rest):
        return None
    return {"letter": found.group(1).upper(), "kilos": int(found.group(2)),
            "suffix": found.group(3).upper(), "series": _series(line),
            "age": _age(line), "phase": _phase(line)}


def _noise(text):
    line = " ".join(str(text or "").split())
    if not line:
        return True
    if _NOISE.search(line):
        return True
    if re.match(r"^\d{2}/\d{2}/\d{4}", line):
        return True
    if re.fullmatch(r"[.…\s–—-]+", line):
        return True
    return False


# --------------------------------------------------------------------------
# Collecting rows
# --------------------------------------------------------------------------

class _Sheet:
    """The rows one read produced, and the counters the Report is built from."""

    def __init__(self, slug, meta, report):
        self.slug = slug
        self.meta = meta or {}
        self.report = report
        self.rows = []
        self.bouts = 0
        self.placings = 0
        self.unresolved = 0
        self.demos = 0
        self.other_sport = 0
        self.date = ""

    def bout(self, **fields):
        self.bouts += 1
        fields.setdefault("bout_id", f"{self.slug}-b{self.bouts:03d}")
        fields.setdefault("tournament", self.slug)
        fields.setdefault("date", self.date)
        row = Bout(**fields)
        if row.status == "unresolved":
            self.unresolved += 1
        self.rows.append(row)
        return row

    def placing(self, **fields):
        self.placings += 1
        fields.setdefault("placing_id", f"{self.slug}-p{self.placings:03d}")
        fields.setdefault("tournament", self.slug)
        fields.setdefault("result_source", "reported")
        fields.setdefault("country", self.meta.get("country", ""))
        rank = str(fields.get("rank", ""))
        fields.setdefault("medal", MEDALS.get(rank, ""))
        row = Placing(**fields)
        self.rows.append(row)
        return row

    def skip(self, text, where):
        """Is this row one of the things that is not a savate bout? Count it."""
        if _DEMO.search(text):
            self.demos += 1
            return True
        if _OTHER_SPORT.search(text) or _OTHER_SPORT_HEADING.search(str(where)):
            self.other_sport += 1
            self.report.problem(f"{where}: {text[:60]!r} is not savate - dropped")
            return True
        return False

    def pair(self, klass, left, right, decision, printed, phase, where,
             winner=None, age="", poule="", time="", podium=None):
        """One bout between two named people, decided or not.

        `winner` is the name the document states won. None means it stated
        none, and the row is stored unresolved - a fact about the document,
        not a claim about the bout.
        """
        fields = dict(klass or {})
        category = fields.pop("category", "")
        gender = fields.get("gender", "")
        kilos = fields.get("weight_kg", "")
        bound = fields.get("weight_bound", "")
        if winner and winner not in (left[0], right[0]):
            self.report.problem(f"{where}: the winner {winner!r} is neither "
                                f"{left[0]!r} nor {right[0]!r} - stored unresolved")
            winner = None
        loser = ""
        if winner:
            loser = right[0] if winner == left[0] else left[0]
        self.bout(
            category=category, gender=gender,
            age_class=age or self.meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound, phase=phase, poule=poule,
            time=time,
            red=left[0], red_club=left[1],
            blue=right[0], blue_club=right[1],
            winner=winner or "", loser=loser, winner_corner="",
            decision=decision, decision_detail=printed,
            status="decided" if winner else "unresolved",
            result_source="reported" if winner else "",
        )
        if not winner:
            return
        if podium is None:
            podium = phase == "final"
        if not podium:
            return
        for rank, who in ((1, winner), (2, loser)):
            if not who:
                continue
            self.placing(category=category, gender=gender,
                         age_class=age or self.meta.get("age_class", ""),
                         weight_kg=kilos, weight_bound=bound,
                         rank=str(rank), fighter=who,
                         club=left[1] if who == left[0] else right[1])


# --------------------------------------------------------------------------
# Layout: a class heading, then the two people who met under it
# --------------------------------------------------------------------------

def _read_heading_blocks(doc, sheet):
    """Covers the 2026 series sheets, the numbered Riaillé sheet, the cadets
    sheet whose club sits in brackets, and the 2023 sheets whose heading names
    the round it was fought in."""
    report = sheet.report
    current, block = None, []

    def flush():
        if not current or not block:
            return
        lines = [words for words, _d, _p in block]
        cut = _boundary(lines, gap=max(6.0, doc.gap * 0.6))
        mode = _block_mode(lines)
        people, verdicts = [], []
        for words, decision, printed in block:
            name, club, _dept = _competitor(words, mode, cut, report,
                                            current["label"])
            if not name:
                continue
            people.append((name, club))
            verdicts.append((decision, printed))
        if len(people) < 2 or len(people) % 2:
            report.problem(f"{current['label']}: {len(people)} competitor line(s) "
                           f"under one heading, which is not a whole number of "
                           f"bouts - not read")
            return
        if len(people) > 2:
            # A heading that covers a round rather than a single bout - the
            # juniors qualifier prints both M60 semi-finals under one. The
            # lines are still two to a bout, in the order they are printed.
            report.problem(f"{current['label']}: {len(people) // 2} bouts under "
                           f"one heading, read as consecutive pairs")
        for at in range(0, len(people), 2):
            couple = people[at:at + 2]
            marks = verdicts[at:at + 2]
            carried = [i for i, (_d, p) in enumerate(marks) if p]
            winner, decision, printed = None, "", ""
            if len(carried) == 1:
                winner = couple[carried[0]][0]
                decision, printed = marks[carried[0]]
            elif len(carried) > 1:
                report.problem(f"{current['label']}: both competitors carry a "
                               f"verdict, so the sheet does not say which of "
                               f"them it went to - stored unresolved")
                decision, printed = marks[0]
            sheet.pair(current["klass"], couple[0], couple[1], decision, printed,
                       current["phase"], current["label"], winner=winner,
                       age=current["age"])

    for words in doc.rows:
        text = doc.spaced(words)
        if _noise(text):
            continue
        head = _heading(text)
        if head:
            flush()
            block = []
            prefix = _prefix(head["series"], head["age"],
                             sheet.meta.get("age_class", ""))
            klass = _category(head["letter"], head["kilos"], head["suffix"],
                              report, prefix)
            label = klass["category"] + (f" {head['phase']}" if head["phase"] else "")
            current = {"klass": klass, "age": head["age"],
                       "phase": head["phase"], "label": label}
            continue
        if _structural(text) and len(text.split()) <= 5:
            # "Première partie", "Deuxième partie", "Résultats" - the sheet
            # talking about itself between two blocks, not a competitor.
            continue
        if current is None:
            continue
        if sheet.skip(text, current["label"]):
            continue
        decision, printed, rest = _verdict(text)
        keep = words[:len(rest.split())] if printed else words
        if not keep:
            continue
        block.append((keep, decision, printed))
    flush()


# --------------------------------------------------------------------------
# Layout: the class code prefixed on every competitor line
# --------------------------------------------------------------------------

def _read_code_lines(doc, sheet):
    """Lines that carry their own class code, paired two by two in order.

    The Open d'Automne prints the round on the winner's line ("F52 1/2F"), the
    Albertville sheet prints it as a sub-heading over a block, and the Elite B
    qualifier prints neither. All three pair the same way, and a pair whose two
    codes disagree is reported rather than joined.
    """
    report = sheet.report
    phase, series, age = "", "", ""
    pending, carry = [], ""

    def flush(force=False):
        # One competitor line is held back, so a surname wrapped onto the next
        # line can still be joined to it before the bout is built.
        while len(pending) >= (2 if force else 3):
            left, right = pending[0], pending[1]
            if left["code"] != right["code"]:
                report.problem(f"{left['code']} {left['name']} and "
                               f"{right['code']} {right['name']} follow each "
                               f"other but are in different classes - not paired")
                pending.pop(0)
                continue
            pending.pop(0)
            pending.pop(0)
            carried = [p for p in (left, right) if p["printed"]]
            winner = carried[0]["name"] if len(carried) == 1 else None
            if len(carried) > 1:
                report.problem(f"{left['code']}: both {left['name']} and "
                               f"{right['name']} carry a verdict - unresolved")
            decision = carried[0]["decision"] if carried else ""
            printed = carried[0]["printed"] if carried else ""
            sheet.pair(left["klass"], (left["name"], left["club"]),
                       (right["name"], right["club"]), decision, printed,
                       left["phase"], left["code"], winner=winner,
                       age=left["age"])
        if force and pending:
            report.problem(f"{len(pending)} competitor line(s) with no partner: "
                           + ", ".join(p["name"] for p in pending))
            del pending[:]

    for words in doc.rows:
        text = doc.spaced(words)
        if _noise(text):
            continue
        found = _CODE.match(text.strip())
        if not found:
            head_phase, head_series, head_age = _phase(text), _series(text), _age(text)
            if head_phase or head_series or head_age:
                flush(force=True)
                phase = head_phase
                series = head_series or series
                age = head_age or age
                carry = ""
                continue
            bare = _clean(text)
            if 3 < len(bare) <= 40 and len(bare.split()) <= 3 and bare == bare.upper():
                head = pending[-1]["name"].split() if pending else []
                if head and head[0].endswith("-"):
                    # "NIVAULT-" on one line, "TERNIN-ROZAT" on the next: the
                    # surname was wrapped, and the second half belongs to its
                    # front, not to the competitor that follows.
                    head[0] = head[0] + bare
                    pending[-1]["name"] = " ".join(head)
                    report.problem(f"{bare!r} was wrapped onto its own line and "
                                   f"is joined back onto {pending[-1]['name']!r}")
                else:
                    carry = bare
                    report.problem(f"{bare!r} sits on a line of its own and is "
                                   f"read as the start of the next "
                                   f"competitor's name")
            continue
        if sheet.skip(text, "line"):
            continue
        body = text[found.end():]
        decision, printed, rest = _cut_verdict(body)
        remainder = rest if printed else body
        line_phase = ""
        lead = _LEAD_PHASE.match(remainder)
        if lead:
            line_phase = _phase(lead.group(1))
            remainder = remainder[lead.end():]
        parts = [p.strip() for p in re.split(r"\s{2,}", remainder) if p.strip()]
        if not parts:
            continue
        if len(parts) == 1:
            name, club = parts[0], ""
            report.problem(f"{parts[0]!r}: one column only, so the club cannot "
                           f"be told from the name - kept whole")
        else:
            name = _clean(" ".join(parts[:-1]))
            club = _clean(parts[-1])
        if carry:
            name = (carry + name) if carry.endswith("-") else f"{carry} {name}"
            carry = ""
        prefix = _prefix(series, age, sheet.meta.get("age_class", ""))
        klass = _category(found.group(1), int(found.group(2)),
                          found.group(3).upper(), report, prefix)
        pending.append({
            "code": f"{found.group(1).upper()}{found.group(2)}{found.group(3).upper()}",
            "klass": klass, "name": name, "club": club, "decision": decision,
            "printed": printed, "phase": line_phase or phase, "age": age})
        flush()
    flush(force=True)


# --------------------------------------------------------------------------
# Layout: the 2009-2013 sheets, whose columns are held apart by dot leaders
# --------------------------------------------------------------------------

def _read_dotted(doc, sheet):
    """"F48....... Mouches....... CANO Sophie....... FL LANESTER (56)....... Victoire"

    Five fields: the class code, the weight class in words, the competitor, the
    club with its département, and - on the winner's line only - the verdict.
    Splitting on the dot runs is what keeps the weight word out of the name;
    splitting on whitespace is what glued them together everywhere else.
    """
    report = sheet.report
    document_phase = ""
    for words in doc.rows[:6]:
        document_phase = _phase(doc.text(words)) or document_phase
        if document_phase:
            break
    pending = []

    def flush(force=False):
        while len(pending) >= 2:
            left, right = pending.pop(0), pending.pop(0)
            if left["code"] != right["code"]:
                report.problem(f"{left['code']} {left['name']} and "
                               f"{right['code']} {right['name']} follow each "
                               f"other in different classes - not paired")
                pending.insert(0, right)
                break
            carried = [p for p in (left, right) if p["printed"]]
            winner = carried[0]["name"] if len(carried) == 1 else None
            if len(carried) > 1:
                report.problem(f"{left['code']}: both lines carry a verdict "
                               f"- unresolved")
            sheet.pair(left["klass"], (left["name"], left["club"]),
                       (right["name"], right["club"]),
                       carried[0]["decision"] if carried else "",
                       carried[0]["printed"] if carried else "",
                       document_phase, left["code"], winner=winner)
        if force and pending:
            report.problem(f"{len(pending)} dotted line(s) with no partner: "
                           + ", ".join(p["name"] for p in pending))
            del pending[:]

    for words in doc.rows:
        text = doc.text(words)
        if _noise(text):
            continue
        parts = [p.strip(" .…") for p in _LEADER.split(text)]
        parts = [p for p in parts if p]
        if len(parts) < 3:
            continue
        klass, code = _class_of(parts[0], report,
                                sheet.meta.get("age_class", ""))
        if not klass or not _CODE.match(parts[0].strip()):
            continue
        if sheet.skip(text, code):
            continue
        rest = parts[1:]
        decision, printed = "", ""
        if rest:
            found_decision, found_printed, _head = _verdict(rest[-1])
            if found_printed and not re.search(r"\(\d{2,3}\)", rest[-1]):
                decision, printed = found_decision, found_printed
                rest = rest[:-1]
        # After the class code comes the weight class in words, then the
        # competitor, then the club. The weight word is dropped rather than
        # guessed at: "Coqs" is the same class as the code already says.
        while rest and _structural(rest[0]):
            rest = rest[1:]
        name = _clean(rest[0]) if rest else ""
        club = _strip_dept(rest[1]) if len(rest) > 1 else ""
        if not name:
            report.problem(f"{code}: no competitor in {text[:70]!r} - skipped")
            continue
        pending.append({"code": code, "klass": klass, "name": name,
                        "club": club, "decision": decision, "printed": printed})
        flush()
    flush(force=True)


# --------------------------------------------------------------------------
# Layout: the wide two-corner tables
# --------------------------------------------------------------------------

_HEADER_WORDS = re.compile(r"\b(nom|pr[ée]nom|club|cat[ée]?|poids|d[ée]cision|"
                           r"r[ée]sultats?|vainqueur|type|niveau)\b", re.I)


def _column_kind(label):
    """What one labelled column of a two-corner table holds."""
    text = _fold(label)
    if not text:
        return ""
    if "vainqueur" in text:
        return "winner"
    if "decision" in text or "resultat" in text:
        return "decision"
    if "niveau" in text:
        return "phase"
    # "prénom" contains "nom": a surname column is one whose "nom" is not the
    # tail of "prenom", and a header cell holding both words - "Nom Prénom 1" -
    # is one cell with the whole name in it.
    given = "prenom" in text
    surname = bool(re.search(r"(?<!pre)nom", text))
    if given and surname:
        return "name"
    if given:
        return "given"
    if surname:
        return "surname"
    if "club" in text:
        return "club"
    if "poids" in text or re.match(r"cat[ée]?\b|cat\.", text):
        return "code"
    if "type" in text:
        return "type"
    return ""


# A surname and a given name that arrived as one token: an upper-case letter
# that follows another upper-case letter and is followed by lower-case ones.
_GLUED = re.compile(r"(?<=[A-ZÀ-ÖØ-Þ])(?=[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ])")


def _unglue(text, given, report, where):
    """The name a two-corner table prints in two cells and extracts as one.

    "COSTA-PICORNELCassidy" is one word in the text layer and two cells on the
    page - the NOM column and the PRENOM column beside it, with the surname
    overflowing into its neighbour. Stored whole it is a person of that name,
    which no document states and no index can match to the COSTA-PICORNEL who
    fought the week before. The space is put back only where the corner's own
    PRENOM cell came out empty, which is what says the two cells merged, and
    the repair is reported every time: it is a reading of the sheet's own
    typography - surnames in capitals, given names capitalised - and not a fact
    the text layer states.
    """
    if given or not text:
        return text
    fixed = _GLUED.sub(" ", text, count=1)
    if fixed == text:
        return text
    report.problem(f"{where}: {text!r} arrived from the text layer as one word "
                   f"with its PRENOM column empty, and is read as {fixed!r} - "
                   f"the sheet sets surnames in capitals and given names "
                   f"capitalised, and the two cells have run together")
    return fixed


def _sections(doc):
    """[(header line, [data lines])] - a wide table may be re-headed per page."""
    out = []
    for words in doc.rows:
        text = doc.text(words)
        hits = len(_HEADER_WORDS.findall(text))
        if hits >= 4 and not re.search(r"\d{2}/\d{2}/\d{4}", text):
            out.append((words, []))
        elif out and not _noise(text):
            out[-1][1].append(words)
    return out


def _read_corner_table(doc, sheet):
    """A bout per row, two corners side by side, and a verdict that names only
    how the bout ended.

    These sheets never say who won. The Décision column holds "majorité",
    "unanimité", "HC", "forfait" - the method, not the winner - so every row
    here is stored unresolved with its decision recorded. Reading the red
    corner as the winner would invent about seventy results from four
    documents, and the two semi-finals one of these sheets does resolve, on a
    later page, show the red corner losing as often as winning.
    """
    report = sheet.report
    for header, lines in _sections(doc):
        data = [line for line in lines if len(line) >= 4]
        columns, kinds = _table_columns(doc, header, data)
        if len(columns) < 5:
            report.problem("a table header was found but its columns could not "
                           "be read - section skipped")
            continue
        wanted = {k for k, _n in kinds.values()}
        if "decision" not in wanted or not ({"surname", "name"} & wanted):
            report.problem(f"a table's columns are {sorted(wanted)} - not a "
                           f"two-corner results table, section skipped")
            continue
        for line in data:
            cells = _cells(line, columns)
            fields = {}
            for x, (kind, index) in kinds.items():
                fields.setdefault(f"{kind}{index}", []).append(_joined(cells, x))
            get = lambda key: _clean(" ".join(fields.get(key, [])))
            code_text = get("code1")
            klass, code = _class_of(code_text, report,
                                    _prefix(_series(get("type1")),
                                            _age(get("type1")),
                                            sheet.meta.get("age_class", "")))
            if not klass:
                continue
            red = _clean(f"{get('surname1')} {get('given1')}" if get("surname1")
                         else get("name1"))
            blue = _clean(f"{get('surname2')} {get('given2')}" if get("surname2")
                          else get("name2"))
            red = _unglue(red, get("given1"), report, code_text or "a row")
            blue = _unglue(blue, get("given2"), report, code_text or "a row")
            if not red or not blue:
                report.problem(f"{code}: a row names {red!r} and {blue!r} - a "
                               f"bout needs two, skipped")
                continue
            whole = doc.text(line)
            if sheet.skip(whole, code):
                continue
            verdict_text = get("decision1")
            decision, printed, leftover = _verdict(verdict_text)
            red_club, blue_club = get("club1"), get("club2")
            if leftover and printed:
                blue_club = _clean(f"{blue_club} {leftover}")
            if not printed and verdict_text:
                report.problem(f"{code} {red} v {blue}: the decision column "
                               f"reads {verdict_text!r}, which is not a verdict "
                               f"this adapter knows")
            sheet.pair(klass, (red, red_club), (blue, blue_club),
                       decision, printed, _phase(get("type1")), code,
                       winner=None, age=_age(get("type1")))
    _resolve_from_blocks(doc, sheet)


def _resolve_from_blocks(doc, sheet):
    """Fill in the winners a two-corner sheet states somewhere else on itself.

    The juniors qualifier prints its table with no winners and then, on its
    last page, prints "Résultats 1/2 Finales Juniors M60" in the ordinary
    two-line finals form, verdict on the winner's line. Those two bouts are
    already in the table as unresolved rows, so they are not added again: the
    row they belong to is found by its own pair of names and resolved, and the
    match is reported. A block that matches no row, or more than one, is
    reported and left alone - a winner attached to the wrong bout would be
    worse than a bout with no winner.
    """
    report = sheet.report
    side = _Sheet(sheet.slug, sheet.meta, Report())
    try:
        _read_heading_blocks(doc, side)
    except Exception as broken:
        report.problem(f"looking for stated winners elsewhere on the sheet "
                       f"stopped on {broken!r}")
        return
    for found in side.rows:
        if not isinstance(found, Bout) or not found.winner:
            continue
        pair = {_fold(found.red), _fold(found.blue)}
        hits = [row for row in sheet.rows
                if isinstance(row, Bout) and row.status == "unresolved"
                and {_fold(row.red), _fold(row.blue)} == pair]
        if len(hits) != 1:
            report.problem(
                f"the sheet states {found.winner} beat "
                f"{found.loser} but {len(hits)} row(s) of the table are that "
                f"pairing - left unresolved")
            continue
        row = hits[0]
        row.winner = found.winner
        row.loser = found.loser
        row.status = "decided"
        row.result_source = "reported"
        row.phase = row.phase or found.phase
        row.decision = row.decision or found.decision
        row.decision_detail = row.decision_detail or found.decision_detail
        report.problem(f"{row.category}: the sheet names {found.winner} the "
                       f"winner over {found.loser} in a block of its own, so "
                       f"that table row is resolved from it")
        sheet.unresolved -= 1


# --------------------------------------------------------------------------
# Layout: a running order, by the clock
# --------------------------------------------------------------------------

_CODE_WORDS = {"MAJO", "UNA", "FORF", "DISQ", "ABAN", "KO", "HC", "HC1", "HC2",
               "HC3", "HC4", "HC5", "NUL"}


def _runs(words, gap):
    out = []
    for word in words:
        if out and word.x0 - out[-1][-1].x1 <= gap:
            out[-1].append(word)
        else:
            out.append([word])
    return out


def _centres(rows, gap, fields=6):
    """The x each field of a centred table is centred on.

    The running order sets every field centred, not flush left, so the column
    a word belongs to cannot be read off its own position - "NICE" starts to
    the left of the name column's own centre. The centres are taken from the
    rows that split cleanly into the right number of fields, and every row is
    then cut on the midpoints between them.
    """
    seen = [[] for _ in range(fields)]
    for words in rows:
        runs = _runs(words, gap)
        if len(runs) != fields:
            continue
        for at, run in enumerate(runs):
            seen[at].append((run[0].x0 + run[-1].x1) / 2)
    if not all(seen):
        return []
    return [sorted(values)[len(values) // 2] for values in seen]


def _continues(row, words):
    """Is this untimed line the tail of `row`, or the next page talking?

    A wrapped club sits on its own baseline immediately under the row it
    belongs to. Anything further away is the page, not the bout - and the
    banner at the top of the NEXT page is the dangerous one: it has no time on
    it, so it was folded word by word into the last timed row of the page
    before, which assembled a competitor called "2024 DOUBLET a Merignac
    Jonathan (33)" out of a year, a town and a real fighter's name. So a line
    is the tail of a row only if it is on the same page and directly below it.
    """
    if not row or not words:
        return False
    if row[0].page != words[0].page:
        return False
    bottom = max(w.bottom for w in row)
    height = max(2.0, max(w.bottom - w.top for w in row))
    top = min(w.top for w in words)
    return -height <= top - bottom <= height * 1.2


def _read_running_order(doc, sheet):
    """Time, class, red corner, blue corner, and an abbreviated verdict.

    The sheet is headed COIN ROUGE and COIN BLEU, so the corners are the
    document's own. The verdict codes - MAJO, UNA, HC3, FORF - say how the bout
    ended and not who it went to, so these rows are unresolved too.
    """
    from savate import normalize as norm

    report = sheet.report
    year = doc.year()
    rows, days = [], []
    day = ""
    for words in doc.rows:
        text = doc.text(words)
        if _noise(text):
            continue
        if not re.match(r"^\s*\d{1,2}\s*[:.]\s*\d{2}\b", text):
            found = re.search(r"\b(\d{1,2})/(\d{1,2})\b(?!\s*/)", text)
            if found and year:
                day = f"{year}-{int(found.group(2)):02d}-{int(found.group(1)):02d}"
            elif (rows and _continues(rows[-1], words)
                  and not any(re.match(r"^\d{1,2}[:.]\d{2}$", w.text)
                              for w in words)):
                # A club that wrapped onto its own line: poppler keeps it on a
                # baseline of its own, so it is folded back into its row.
                rows[-1] = sorted(rows[-1] + list(words), key=lambda w: w.x0)
            continue
        rows.append(sorted(words, key=lambda w: w.x0))
        days.append(day)

    if not rows:
        report.problem("no timed rows found - this may not be a running order")
        return
    bodies, tails = [], []
    for words in rows:
        taken = 0
        for word in reversed(words):
            if word.text.upper().strip(".") in _CODE_WORDS:
                taken += 1
            else:
                break
        bodies.append(words[:len(words) - taken] if taken else list(words))
        tails.append(words[len(words) - taken:] if taken else [])

    centres = _centres(bodies, doc.gap * 2.5)
    if len(centres) != 6:
        report.problem("the six fields of the running order could not be "
                       "located - nothing read")
        return
    edges = [(centres[i] + centres[i + 1]) / 2 for i in range(5)]

    def field(words, at):
        low = edges[at - 1] if at else -1e9
        high = edges[at] if at < 5 else 1e9
        return _clean(" ".join(w.text for w in words
                               if low <= w.middle < high))

    for words, body, tail, when in zip(rows, bodies, tails, days):
        decision, printed, _rest = _verdict(" ".join(w.text for w in tail))
        time = norm.clock(field(body, 0))
        klass_text = field(body, 1)
        red, red_club = field(body, 2), field(body, 3)
        blue, blue_club = field(body, 4), field(body, 5)
        if sheet.skip(doc.text(words), klass_text):
            continue
        klass, code = _class_of(klass_text, report,
                                _prefix(_series(klass_text), _age(klass_text),
                                        sheet.meta.get("age_class", "")))
        if not klass or not red or not blue:
            report.problem(f"{doc.text(words)[:70]!r}: read class {klass_text!r}, "
                           f"{red!r} and {blue!r} - skipped")
            continue
        poule = ""
        found = re.search(r"poule\s*([A-Z])", klass_text, re.I)
        if found:
            poule = found.group(1).upper()
        sheet.pair(klass, (red, red_club), (blue, blue_club), decision, printed,
                   _phase(klass_text), code, winner=None, poule=poule, time=time)
        if when:
            sheet.rows[-1].date = when
        if not printed:
            report.problem(f"{code} at {time or '?'}: no verdict code on the row")


# --------------------------------------------------------------------------
# Layout: the one table that names its winner
# --------------------------------------------------------------------------

def _read_winner_column(doc, sheet):
    """Niveau | Cat. | Nom Prénom 1 | Club 1 | Nom Prénom 2 | Club 2 |
    Vainqueur | Décision - the cleanest sheet the federation ever published,
    and the only one in this group whose rows arrive decided."""
    report = sheet.report
    # The sheet names its own gender and series in its title and gives no
    # weight class at all, so the category is what it does say and no more.
    banner = " ".join(doc.text(words) for words in doc.rows[:4])
    gender = ("Women" if re.search(r"f[ée]minin", banner, re.I)
              else "Men" if re.search(r"masculin", banner, re.I) else "")
    series = _series(banner)
    for header, lines in _sections(doc):
        data = [line for line in lines if len(line) >= 4]
        columns, kinds = _table_columns(doc, header, data)
        if "winner" not in {k for k, _n in kinds.values()}:
            report.problem("a section has no Vainqueur column - skipped")
            continue
        for line in data:
            cells = _cells(line, columns)
            fields = {}
            for x, (kind, index) in kinds.items():
                fields[f"{kind}{index}"] = _joined(cells, x)
            red = _clean(f"{fields.get('surname1', '')} "
                         f"{fields.get('given1', '')}")
            blue = _clean(f"{fields.get('surname2', '')} "
                          f"{fields.get('given2', '')}")
            winner = fields.get("winner1", "")
            whole = doc.text(line)
            if not red or not blue:
                continue
            if sheet.skip(whole, red):
                continue
            if not fields.get("winner1", "") and not fields.get("decision1", ""):
                report.problem(f"a row reading {whole[:60]!r} has neither a "
                               f"winner nor a decision - not read as a bout")
                continue
            label = fields.get("code1", "") or fields.get("type1", "")
            age = _age(label)
            klass, code = _class_of(label, report, _prefix(series, age))
            if not klass:
                # No weight class is printed anywhere on this sheet. The
                # category is then the series and gender it does name, and the
                # weight is left empty rather than filled from the title.
                head = _clean(f"{series} {age}")
                klass = {"category": _clean(f"{head} {gender}"), "gender": gender,
                         "weight_kg": "", "weight_bound": ""}
                code = _clean(label)
            decision, printed, _rest = _verdict(fields.get("decision1", ""))
            if winner and winner not in (red, blue):
                report.problem(f"{code}: the Vainqueur column reads {winner!r}, "
                               f"which is neither {red!r} nor {blue!r} - the "
                               f"bout is stored unresolved")
                winner = ""
            if not winner:
                report.problem(f"{code} {red} v {blue}: no winner named")
            sheet.pair(klass, (red, fields.get("club1", "")),
                       (blue, fields.get("club2", "")), decision, printed,
                       _phase(fields.get("phase1", "")), code,
                       winner=winner or None, age=age)


# --------------------------------------------------------------------------
# Layout: "X bat Y, unanimité"
# --------------------------------------------------------------------------

_BAT = re.compile(r"^\s*combats?\s*n[°ºo]?\s*(\d+)\s+(.+?)\s+bat\s+(.+?)\s*$", re.I)


def _read_bat(doc, sheet):
    """The 2012 Paris sheet: a numbered list with an explicit verb.

    No weight class is printed anywhere on it, so none is claimed; the bout
    rows carry the pairing, the winner and the verdict, and an empty category
    which is what the document supports.
    """
    report = sheet.report
    for words in doc.rows:
        text = _clean(doc.text(words))
        if _noise(text):
            continue
        decision, printed, head = _verdict(text)
        found = _BAT.match(head)
        if not found:
            if re.match(r"^\s*combats?\s*n", text, re.I):
                report.problem(f"{text[:70]!r} looks like a bout line but does "
                               f"not say who beat whom - skipped")
            continue
        if sheet.skip(text, found.group(1)):
            continue
        winner, loser = _clean(found.group(2)), _clean(found.group(3))
        if not winner or not loser:
            continue
        if not printed:
            report.problem(f"bout {found.group(1)}: no verdict printed")
        sheet.pair({"category": "", "gender": "", "weight_kg": "",
                    "weight_bound": ""},
                   (winner, ""), (loser, ""), decision, printed, "",
                   f"bout {found.group(1)}", winner=winner)


# --------------------------------------------------------------------------
# Layout: a poule's own ranking table
# --------------------------------------------------------------------------

_POULE_HEADER = re.compile(r"tireur", re.I)


def _read_poule_table(doc, sheet):
    """Tireur | Club | Rencontres | Points | Avertissements | Classement.

    The federation's own ranking of each minimes poule. Every competitor is
    ranked, so every competitor is a Placing - not only the first three. A
    competitor whose Classement column reads "Forfait" instead of a number is
    reported unranked rather than given a position the sheet withholds.

    The Rencontres, Points and Avertissements columns are read and checked
    against the barème, but the schema's Placing has nowhere to put them, so
    they survive only in the Report. That is a gap worth closing centrally.
    """
    report = sheet.report
    klass, code, columns, kinds = None, "", [], {}
    inherited = False
    counted = {"points": 0, "checked": 0, "odd": 0}
    age, banner = doc.declared_age()
    if age:
        report.notes["age_class_from"] = banner
    age = age or sheet.meta.get("age_class", "")

    for words in doc.rows:
        text = doc.text(words)
        if _noise(text):
            continue
        head = _heading(text)
        if head and len(words) <= 3:
            prefix = _prefix(head["series"], head["age"], age)
            klass = _category(head["letter"], head["kilos"], head["suffix"],
                              report, prefix)
            code = f"{head['letter']}{head['kilos']}{head['suffix']}"
            inherited = bool(columns)
            continue
        if _POULE_HEADER.search(text):
            columns = sorted(round(w.x0, 1) for w in words)
            kinds = {}
            for x, word in zip(columns, sorted(words, key=lambda w: w.x0)):
                kinds[x] = _fold(word.text)
            inherited = False
            continue
        if not klass or not columns:
            continue
        if inherited:
            # One class on this sheet is printed without its own header row.
            # Its figures line up with the class above it, so those columns are
            # used - and said so, because the columns are then an assumption.
            report.problem(f"{code} has no header row of its own and is read "
                           f"in the columns of the class above it")
            inherited = False
        if sheet.skip(text, code):
            continue
        cells = _cells(words, columns)
        got = {kinds.get(x, ""): _joined(cells, x) for x in columns}
        fighter = got.get("tireur", "")
        if not fighter:
            continue
        rank = got.get("classement", "")
        bouts = got.get("rencontres", "")
        points = got.get("points", "")
        warnings = got.get("avertissements", "")
        if not rank.isdigit():
            report.problem(f"{code}: {fighter} is listed with "
                           f"{rank or 'nothing'} where a rank should be - kept "
                           f"out of the standings")
            continue
        counted["points"] += 1
        if bouts.isdigit() and re.fullmatch(r"-?\d+", points or ""):
            counted["checked"] += 1
            low, high = -int(bouts), 3 * int(bouts)
            if not low <= int(points) <= high:
                counted["odd"] += 1
                report.problem(f"{code}: {fighter} has {points} points from "
                               f"{bouts} bouts, which the barème cannot produce")
        sheet.placing(category=klass["category"], gender=klass["gender"],
                      age_class=age,
                      weight_kg=klass["weight_kg"],
                      weight_bound=klass["weight_bound"],
                      rank=rank, fighter=fighter, club=got.get("club", ""))
    if counted["points"]:
        report.notes["poule_columns_dropped"] = (
            "rencontres, points and avertissements were read for "
            f"{counted['checked']} of {counted['points']} competitors and "
            "discarded: schema.Placing has no field for them")


# --------------------------------------------------------------------------
# Layout: the Avenir sheets - one row per competitor, with a rank and a title
# --------------------------------------------------------------------------

# What the Avenir sheets print in the Titre column for a competitor who did
# not fight: a fact about the result, and the one word on the row that a medal
# derived from the rank would contradict.
_FORFEIT = re.compile(r"forfait|\bforf\b|\bw\.?\s?o\.?(?=\W|$)", re.I)

_AVENIR_HEADER = re.compile(
    r"instance|affili|type\s*poids|victoi|d[ée]fait|disqu|\brang\b|\btitre\b|"
    r"ffsavate|r[ée]sulats|nom\s+pr[ée]nom|\bligue\b|\bavt\b", re.I)


def _by_page(lines):
    """[[line]] grouped by page - these sheets re-set their columns per page."""
    pages = {}
    for line in lines:
        pages.setdefault(line[0].page, []).append(line)
    return [pages[page] for page in sorted(pages)]


def _ranked_columns(page):
    """What each column of one page of a ranked sheet holds, or None.

    Neither Avenir sheet has a header a table reader can use - one has none at
    all, the other wraps its own across four lines - and both re-set their tab
    stops from page to page. So the columns are read per page and told apart by
    their contents: the one holding nothing but class codes, the small numbers
    to its right that are the rank, and the wordy columns past those, which are
    the title.
    """
    columns = _peaks(page, share=0.85)
    if len(columns) < 4:
        return None
    values = {x: [] for x in columns}
    for line in page:
        cells = _cells(line, columns)
        for x in columns:
            text = _joined(cells, x)
            if text:
                values[x].append(text)

    def mostly(x, test):
        seen = values.get(x) or []
        return bool(seen) and sum(1 for v in seen if test(v)) >= len(seen) * 0.8

    code_at = next((x for x in columns
                    if mostly(x, lambda v: _CODE.fullmatch(v))), None)
    if code_at is None:
        return None
    title_at = next((x for x in columns if x > code_at
                     and mostly(x, lambda v: len(v) >= 5
                                and re.search(r"[A-Za-zÀ-ÿ]", v))), None)
    ranks = [x for x in columns if code_at < x
             and (title_at is None or x < title_at)
             and mostly(x, lambda v: v.isdigit() and len(v) <= 2)]
    if not ranks:
        return None

    # Where the name-and-club half of the row ends: the club's registration
    # number where the sheet prints one, otherwise the column before the ligue.
    # The number is set flush right, so its column moves with how many digits
    # it has and is looked for in the words rather than in the columns.
    numbers = [w for line in page for w in line
               if re.fullmatch(r"\d{3,6}", w.text) and w.x0 < code_at]
    # The three-letter cell in front of the class code - "BEN", "MIN" - is the
    # sheet's own age column, printed on every row. It is read as the row's age
    # class in preference to the Titre, because the Titre is not an age class:
    # it is what the result was called, and on the rows where it says FORFAIT
    # instead of "Championne de France Avenir Benjamine" an age read out of it
    # is silently lost and one poule comes out split across two categories.
    cat = [x for x in columns if x < code_at
           and mostly(x, lambda v: re.fullmatch(r"[A-Z]{3}", v))]
    limit = None
    if len(numbers) >= len(page) * 0.8:
        limit = min(w.x0 for w in numbers) - 2
    if limit is None and cat:
        before = [x for x in columns if x < cat[-1] and values[x]]
        limit = before[-1] if len(before) >= 2 else cat[-1]
    return {"columns": columns, "code": code_at, "rank": ranks[-1],
            "title": title_at, "age": cat[-1] if cat else None,
            "limit": limit if limit is not None else code_at}


def _ranked_rows(doc, sheet, lines, where):
    """Place every competitor a ranked sheet lists, page by page."""
    report = sheet.report
    for page in _by_page(lines):
        plan = _ranked_columns(page)
        if plan is None:
            report.problem(f"{where}: the columns of page "
                           f"{page[0][0].page} could not be told apart - its "
                           f"{len(page)} row(s) were not read")
            continue
        columns = plan["columns"]
        for words in page:
            cells = _cells(words, columns)
            code_text = _joined(cells, plan["code"])
            if not _CODE.fullmatch(code_text):
                continue
            rank = _joined(cells, plan["rank"])
            title = _clean(" ".join(
                _joined(cells, x) for x in columns
                if plan["title"] is not None and x >= plan["title"]))
            age = _age(_joined(cells, plan["age"])) if plan["age"] else ""
            age = age or _age(title)
            region = [w for w in words if w.middle < plan["limit"]]
            while region and re.fullmatch(r"\d{3,6}", region[-1].text):
                region = region[:-1]
            name, club = _split_gap(region)
            klass, code = _class_of(code_text, report,
                                    _prefix("", age,
                                            sheet.meta.get("age_class", "")))
            if not name or not klass:
                continue
            if not rank.isdigit():
                report.problem(f"{code}: {name} is listed with "
                               f"{rank or 'nothing'} where a rank should be - "
                               f"kept out of the standings")
                continue
            if sheet.skip(_Doc.text(words), code):
                continue
            if _FORFEIT.search(title):
                # The Titre column is where this sheet says what the result was
                # called, and on these rows it says the competitor forfeited.
                # A rank of 1, 2 or 3 would take a medal with it - schema.Placing
                # fills one from the rank and has no way not to - and a bronze
                # medal for a forfeit is a thing the document flatly denies. The
                # rank is reported and the row is left out; places past third
                # carry no medal and are kept, with the forfeit reported.
                report.problem(f"{code}: {name} is placed {rank} with "
                               f"{title!r} where the title should be"
                               + (" - kept out of the standings, because a rank "
                                  "of three or better would carry a medal the "
                                  "sheet contradicts"
                                  if rank in ("1", "2", "3") else
                                  " - the forfeit is recorded nowhere on the "
                                  "row: schema.Placing has no field for it"))
                if rank in ("1", "2", "3"):
                    continue
            sheet.placing(category=klass["category"], gender=klass["gender"],
                          age_class=age or sheet.meta.get("age_class", ""),
                          weight_kg=klass["weight_kg"],
                          weight_bound=klass["weight_bound"],
                          rank=rank, fighter=name, club=club)


def _read_avenir_rows(doc, sheet):
    """One line per competitor: name, club, club number, ligue, class, rank,
    title.

    The 2025 sheet's text layer has lost a handful of accented glyphs - "GAUBE
    Ka?lys" for Kaëlys - and those names are stored exactly as printed and
    listed in the Report. Repairing them would mean choosing between é, è and ë
    on the strength of nothing.
    """
    lines = [words for words in doc.rows
             if len(words) >= 5 and not _noise(_Doc.text(words))
             and _CODE.search(_Doc.text(words))
             and not _AVENIR_HEADER.search(_Doc.text(words))]
    _ranked_rows(doc, sheet, lines, "ranked rows")


def _read_avenir_wide(doc, sheet):
    """The widest sheet in the batch: name, club, ligue, age class, weight
    class, poule, wins, points, defeats, disqualifications, total, warnings,
    rank and title.

    Its rows are two text lines tall and poppler puts the name on one and the
    figures on the other, so a line with nothing in the name column is folded
    into the row above it before anything is read. Only the name, club, class,
    rank and title survive: schema.Placing has no field for a competitor's
    wins, points or warnings, so the barème columns this sheet publishes are
    read and then dropped.
    """
    usable = [words for words in doc.rows
              if not _noise(_Doc.text(words))
              and not _AVENIR_HEADER.search(_Doc.text(words))]
    if not usable:
        return
    left = min(w.x0 for words in usable for w in words)
    merged = []
    for words in usable:
        # A line with nothing in the name column is the rest of the row above
        # it - but only if it is on the same page. The next page's header has
        # nothing in the name column either, and folding it into the last row
        # of the page before cost two competitors their places.
        if (merged and merged[-1][0].page == words[0].page
                and not any(w.x0 <= left + 12 for w in words)):
            merged[-1] = merged[-1] + list(words)
        else:
            merged.append(list(words))
    lines = [sorted(words, key=lambda w: w.x0) for words in merged
             if _CODE.search(_Doc.text(words))]
    _ranked_rows(doc, sheet, lines, "Avenir table")
    sheet.report.notes["barem_columns_dropped"] = (
        "wins, points, defeats, disqualifications, total and warnings are "
        "printed on this sheet and discarded: schema.Placing has no field "
        "for them")


# --------------------------------------------------------------------------
# Layout: the 2010 national standings, two columns to a page
# --------------------------------------------------------------------------

_WEIGHT_HEAD = re.compile(
    r"^(?P<name>[A-Za-zÀ-ÿ/ '’-]{3,24}?)\s*\(\s*(?:moins\s+de\s+)?"
    r"(?P<low>\d{2,3})\s*(?:/\s*(?P<high>\d{2,3}))?\s*kg\s*\)\s*$", re.I)


def _split_page(words):
    """The x that separates a two-column page, or None if it is one column.

    The gutter is the vertical line fewest words cross - not none at all: the
    page's own title is set across the whole width and would otherwise hide
    every gutter under it.
    """
    if not words:
        return None
    left = min(w.x0 for w in words)
    right = max(w.x1 for w in words)
    span = right - left
    if span <= 0:
        return None
    best = None
    step = max(1.0, span / 300.0)
    x = left + span * 0.35
    while x < left + span * 0.65:
        crossings = sum(1 for w in words if w.x0 < x < w.x1)
        distance = abs(x - (left + span / 2))
        if best is None or (crossings, distance) < (best[1], best[2]):
            best = (x, crossings, distance)
        x += step
    if best is None or best[1] > max(3, len(words) * 0.02):
        return None
    return best[0]


def _read_ranking_columns(doc, sheet):
    """A season's national standings, not a competition: each weight class is a
    ranked list, and the page prints two of them side by side, so a linear read
    interleaves two different classes. The page is cut down the white column
    between them and each half read on its own.

    Nothing is stored. The page is read - the classes, the names, the clubs and
    the positions all come out of it correctly - and then refused, because the
    only row this archive has for a position is schema.Placing, and Placing
    fills a medal from the rank: a first place in a season's standings would
    enter the archive as a gold medal, a second as a silver, eighteen of them
    on this one document, none of them won at anything. There is no podium on
    this page and no competition behind it. Until Placing can hold a standing
    that won nothing, a season ranking cannot be stored honestly, and the count
    of what was read and refused is reported so the loss is visible.
    """
    report = sheet.report
    refused = []
    from savate import pdf as pdfmod

    gender = "Women" if re.search(r"f[ée]minin", doc.text(doc.rows[1]) if
                                  len(doc.rows) > 1 else "", re.I) else ""
    for page, words in sorted(pdfmod.by_page(doc.words).items()):
        cut = _split_page(words)
        halves = ([[w for w in words if w.x1 <= cut],
                   [w for w in words if w.x0 >= cut]] if cut else [words])
        for half in halves:
            klass = None
            for line in pdfmod.rows(half):
                text = _clean(pdfmod.text_of(line))
                if _noise(text):
                    continue
                found = _WEIGHT_HEAD.match(text)
                if found:
                    kilos = int(found.group("high") or found.group("low"))
                    klass = _category("F" if gender == "Women" else "M", kilos,
                                      "", report,
                                      sheet.meta.get("age_class", ""))
                    klass["category"] = (f"{_clean(found.group('name'))} "
                                         f"{klass['category']}")
                    continue
                if klass is None:
                    continue
                parts = [p.strip(" .…") for p in _LEADER.split(text)]
                parts = [p for p in parts if p]
                if len(parts) < 3 or not parts[-1].isdigit():
                    continue
                if sheet.skip(text, klass["category"]):
                    continue
                refused.append(f"{klass['category']} {parts[-1]} "
                               f"{_clean(parts[0])}")
    if not refused:
        report.problem("no ranked lines found - this may not be a standings sheet")
        return
    report.notes["standings_refused"] = refused
    report.problem(
        f"{len(refused)} season standings position(s) were read off this sheet "
        f"and none is stored: this is a ranking table, not a competition, and "
        f"schema.Placing attaches gold, silver and bronze to ranks 1, 2 and 3 "
        f"with no way to say that nothing was won. They are listed in the "
        f"report's standings_refused note rather than filed as medals")


# --------------------------------------------------------------------------
# Layout: the palmarès page, in HTML
# --------------------------------------------------------------------------

_PALMARES = re.compile(
    r"cat[ée]gorie\s*:?\s*(?P<code>[FM]\s?\d{2,3})\s*[-–]?\s*(?P<word>[^\n]{0,24}?)\s*"
    r"championn?e?\s+de\s+france\s*:\s*(?P<gold>.*?)\s*"
    r"vice\s*-?\s*championn?e?\s*de\s+france\s*:\s*(?P<silver>.*?)"
    r"(?=cat[ée]gorie|palmares|palmarès|cr[ée]ez\s+votre|$)", re.I | re.S)
_SLASH_CLUB = re.compile(r"^(?P<name>.+?)\s*/\s*(?P<club>.+?)\s*$")


def _read_palmares(doc, sheet):
    """The 2014 Elite A palmarès, as the federation's own site published it.

    Champion, method of victory, vice-champion, per weight class. The method
    wraps across two lines in the markup - "Victoire" then "à la majorité" -
    so the page is flattened to one line before anything is matched.
    """
    from bs4 import BeautifulSoup

    report = sheet.report
    soup = BeautifulSoup(doc.html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    flat = " ".join(soup.get_text(" ").split())
    found = 0
    for match in _PALMARES.finditer(flat):
        found += 1
        klass, code = _class_of(match.group("code"), report,
                                sheet.meta.get("age_class", ""))
        if not klass:
            continue
        gold_text = _clean(match.group("gold"))
        silver_text = _clean(match.group("silver"))
        if sheet.skip(gold_text + " " + silver_text, code):
            continue
        decision, printed, gold_text = _verdict(gold_text)
        gold, gold_club = _name_slash_club(gold_text)
        silver, silver_club = _name_slash_club(silver_text)
        if not gold or not silver:
            report.problem(f"{code}: read {gold!r} and {silver!r} - a final "
                           f"needs two, skipped")
            continue
        if not printed:
            report.problem(f"{code}: no method of victory printed for {gold}")
        sheet.pair(klass, (gold, gold_club), (silver, silver_club),
                   decision, printed, "final", code, winner=gold,
                   age=sheet.meta.get("age_class", ""))
    if not found:
        report.problem("no 'Catégorie ... CHAMPION DE FRANCE' blocks on the "
                       "page - this may not be a palmarès")


def _name_slash_club(text):
    """"NANDI Chloé / US CRETEIL (94)" -> the name and the club."""
    text = _clean(text)
    if not text:
        return "", ""
    found = _SLASH_CLUB.match(text)
    if not found:
        return text, ""
    club = _clean(re.sub(r"\(\s*\d{2,3}\s*\)\s*$", "", found.group("club")))
    return _clean(found.group("name")), club


# --------------------------------------------------------------------------
# Choosing a layout
# --------------------------------------------------------------------------

_LAYOUTS = {
    "heading_blocks": _read_heading_blocks,
    "code_lines": _read_code_lines,
    "dotted": _read_dotted,
    "corner_table": _read_corner_table,
    "running_order": _read_running_order,
    "winner_column": _read_winner_column,
    "bat_list": _read_bat,
    "poule_table": _read_poule_table,
    "avenir_wide": _read_avenir_wide,
    "avenir_rows": _read_avenir_rows,
    "ranking_columns": _read_ranking_columns,
    "palmares_html": _read_palmares,
}


def _sniff(doc):
    """The layout this document is in, on the evidence of the document."""
    if not doc.is_pdf:
        return "palmares_html"
    texts = [doc.text(words) for words in doc.rows]
    joined = "\n".join(texts)
    if re.search(r"\bcombats?\s*n[°ºo]?\s*\d+.*\bbat\b", joined, re.I):
        return "bat_list"
    if re.search(r"\bvainqueur\b", joined, re.I):
        return "winner_column"
    if re.search(r"coin\s+rouge", joined, re.I):
        return "running_order"
    if re.search(r"\btireur\b", joined, re.I) and re.search(r"classement", joined, re.I):
        return "poule_table"
    if re.search(r"instance\s+affili[ée]e", joined, re.I):
        return "avenir_wide"
    leaders = sum(1 for text in texts if len(_LEADER.findall(text)) >= 2)
    if leaders >= 4:
        if re.search(r"\(\s*(?:moins\s+de\s+)?\d{2,3}\s*(?:/\s*\d{2,3})?\s*kg\s*\)",
                     joined, re.I):
            return "ranking_columns"
        return "dotted"
    if sum(1 for text in texts if len(_HEADER_WORDS.findall(text)) >= 4) >= 1:
        return "corner_table"
    if re.search(r"championn?e?\s+de\s+france\b", joined, re.I) and \
            sum(1 for text in texts if _CODE.search(text) and
                re.search(r"\b\d{4,6}\b", text)) >= 4:
        return "avenir_rows"
    headings = sum(1 for text in texts if _heading(text))
    prefixed = sum(1 for text in texts if _CODE.match(text.strip()))
    if prefixed > headings:
        return "code_lines"
    if headings:
        return "heading_blocks"
    return "heading_blocks"


def _tournament(slug, meta, source):
    """The tournament row, out of the manifest and nothing else.

    level and country used to default to "national" and "France" when the
    manifest said nothing, which filed nine-bout club galas as national events
    and stated a country that not every one of these sheets prints. A field the
    manifest does not carry is empty here: the manifest is where a fact read off
    the document is recorded, and a default is not a reading.
    """
    return Tournament(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""),
        format=meta.get("format", ""),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        country=meta.get("country", ""),
        source=str(source), adapter=NAME,
    )


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) for one FFSavate sheet."""
    meta = dict(meta or {})
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)

    doc = _Doc(source, report)
    layout = options.get("layout") or meta.get("layout") or _sniff(doc)
    report.notes["layout"] = layout
    report.notes["layout_from"] = ("the manifest"
                                   if options.get("layout") or meta.get("layout")
                                   else "the document")
    reader = _LAYOUTS.get(layout)
    if reader is None:
        report.problem(f"no reader called {layout!r}; known layouts are "
                       + ", ".join(sorted(_LAYOUTS)))
        return tournament, [], report

    sheet = _Sheet(slug, meta, report)
    if doc.is_pdf:
        when, city = doc.dated()
        if when:
            tournament.start_date = tournament.start_date or when
            tournament.city = tournament.city or city
            tournament.year = tournament.year or when[:4]
            sheet.date = when
        elif not tournament.year:
            tournament.year = doc.year()
    try:
        reader(doc, sheet)
    except Exception as broken:                     # a shape nobody expected
        report.problem(f"{layout}: the reader stopped on {broken!r} - the rows "
                       f"read before that point are kept")

    damaged = set()
    for row in sheet.rows:
        for field in ("red", "blue", "winner", "fighter", "red_club",
                      "blue_club", "club"):
            value = getattr(row, field, "")
            if value and "?" in value:
                damaged.add(value)
    if damaged:
        report.problem(
            f"{len(damaged)} name(s) or club(s) reached the text layer with a "
            f"glyph missing and are stored exactly as printed, because é, è and "
            f"ë cannot be told apart from what is left: "
            + ", ".join(sorted(damaged)[:10]))
    report.notes["damaged_glyphs"] = sorted(damaged)

    report.read = len(doc.rows) if doc.is_pdf else 1
    report.notes["bouts"] = sheet.bouts
    report.notes["placings"] = sheet.placings
    report.notes["unresolved"] = sheet.unresolved
    report.notes["demonstrations_excluded"] = sheet.demos
    report.notes["other_sport_rows_dropped"] = sheet.other_sport
    if sheet.demos:
        report.problem(f"{sheet.demos} demonstration bout(s) excluded: a demo "
                       f"has no result and is not a bout")
    if sheet.unresolved:
        report.problem(f"{sheet.unresolved} of {sheet.bouts} bout(s) name no "
                       f"winner - this sheet publishes the method a bout ended "
                       f"by and not who it went to, so they are unresolved")
    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"])
            + " exceed every real savate weight and are a sentinel for a class "
              "with no weight limit; no document says what the number stands "
              "for, so the code is kept as printed and no weight, and no "
              "direction, is stored for those rows")
    if report.notes.get("youth_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["youth_classes"])
            + " carry the federation's J suffix, which marks a youth ladder. "
              "The J is kept in the category exactly as printed; which youth "
              "class it is - benjamin, minime, cadet - is stated only where a "
              "heading, a title column or the sheet's own footer says so")
    if sheet.placings:
        report.problem(
            f"{sheet.placings} placing(s) carry a medal derived from the rank "
            f"by the archive's convention (1, 2, 3 -> gold, silver, bronze): "
            f"no document in this family prints the word gold, silver or "
            f"bronze, and schema.Placing has no way to store a rank without one")
    if not sheet.rows and not report.notes.get("standings_refused"):
        report.problem(f"no rows read as {layout!r} - the layout guess may be "
                       f"wrong; a manifest entry can name one of "
                       + ", ".join(sorted(_LAYOUTS)))
    return tournament, sheet.rows, report
