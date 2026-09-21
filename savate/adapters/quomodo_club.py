"""The FFSavate's own result sheets, as hosted on the Quomodo club platform.

Quomodo (f2.quomodo.com) is the site host a large part of French savate runs on
- the national commission, the ligues, individual clubs - and the files served
from it are the FFSavate's house paperwork rather than anything Quomodo itself
produces. So this adapter is written for that paperwork, not for four files: the
same Word-exported sheets turn up under every ligue's upload directory, and the
five shapes below are what they come in.

    A. the dotted finals sheet, two lines to a bout

        F48    Mouches..... RIVIERE Vanessa. ..... LA SAVATE CARAMANAISE (31)
        F48    Mouches..... GUILLOT Ludivine. .... GANT D'HERMINE VANNETAIS (56)
                                                    ......... Victoire à la majorité

       A class code, the federation's French name for the weight, the two
       competitors with their clubs, and the verdict printed at the end of the
       winner's line - which may be either line, and is the only thing that says
       who won. The same shape carries placings instead of verdicts ("Championne",
       "Vice-Championne", "Finaliste 1") on the youth sheets.

    B. the poule sheet, where the winner is red ink and nothing else

        En rouge les vainqueurs de chaque rencontre.
        CHAMANE Samya / DESSE Camille .......................... Unanimité

       Every pairing in a round robin, with the decision, and the winner marked
       only by the colour of their name. `pdftotext` drops colour, which is why
       these have never been readable; this adapter reads the glyph colour out of
       poppler's XML and uses it, and stores the bout unresolved when the ink
       does not say.

    C. the veterans' technique sheet, name and club on one line

        GROS Stéphane - BC FRANOIS SERRE (25)        Champion

    D. the international podium table, one row per medal

        CAT    Résultat          Prénom      NOM         PAYS
        F48    Championne        Kelly       ATANASIO    FRANCE

    E. the European championship's own two lists - a numbered classification
       ("1. DOZDOR Roko (CRO)"), and a list of who reached the final
       ("FINALES  BOUCHER Mathieu (FRA)") with the final itself fought months
       later at a separate gala, whose pairings and dates a sixth sheet gives.

Four things this adapter refuses to do.

*It does not assign corners.* Not one of these sheets says who stood where.
Printed order is printed order; `winner_corner` stays empty and the winner is
named, which is what the schema is built to allow.

*It does not rank a "Finaliste".* The youth sheets list "Finaliste 1" and
"Finaliste 2" below the champion and vice-champion, and the Trophée Denise
Avédiguian rules printed inside the same file score a "finaliste N°3" and a
"finaliste N°4" differently - so the federation does grade them, but under a
numbering that starts at three while the results list numbers from one. Two
readings of the same word, in one document, and nothing that settles it. Those
rows are counted and described in the report and no placing is written for them,
because a fabricated bronze is worse than a missing one.

*It does not turn a fixture into a result.* The "Répartition des finales" sheet
is a schedule, published in July for finals fought in September and December.
Its pairings are real and its dates are real; its outcomes had not happened yet.
They are stored unresolved, and the report says so on every read.

*It does not read a class code it cannot account for.* F100 and M150 sit above
every real savate weight and mark the open class at the top of each ladder, the
same sentinel the 2023-25 sheets use; that reading is reported on every read.
"M+85" is an ordinary over-85 class and is read as one, and the "J" that the
youth sheets suffix ("F42J", "M150J") is the federation's mark for a jeunes
class, not part of the number.
"""

import re
import subprocess

from savate.schema import (MEDALS, Bout, Placing, Report, Tournament, phase_of)

NAME = "quomodo_club"
DESCRIPTION = ("FFSavate sheets on the Quomodo platform: dotted finals, "
               "red-ink poules, podium tables")

# ---------------------------------------------------------------- reading ---
#
# poppler's XML output is used rather than its plain text for one reason: it is
# the only extraction here that keeps the colour of a glyph, and on the poule
# sheets the colour IS the result. It also happens to give cleaner lines than
# `-layout` on these files, because the dot leaders confuse column detection.

_RED = re.compile(r"^#([0-9a-f]{6})$")


def _is_red(colour):
    """Is this a red ink, as against the black body and the blue headings?

    Judged on the channels, not on a list of hexes: the sheets use #ff0000 and
    #da0000 for the same thing, and their headings use several blues.
    """
    found = _RED.match(str(colour or "").strip().lower())
    if not found:
        return False
    value = int(found.group(1), 16)
    red, green, blue = value >> 16, (value >> 8) & 0xFF, value & 0xFF
    return red >= 0x80 and green < 0x60 and blue < 0x60


class _Line:
    """One visual line: its text, and which characters of it were red."""

    __slots__ = ("page", "top", "text", "red")

    def __init__(self, page, top, text, red):
        self.page, self.top, self.text, self.red = page, top, text, red

    def red_between(self, start, end):
        """Is any red ink inside [start, end) of this line's text?"""
        return any(start <= i < end for i in self.red)

    def __repr__(self):
        return f"<{self.page}:{self.top:.0f} {self.text!r}>"


def _xml_lines(path, report):
    """Lines with colour, via pdftohtml -xml. [] if it cannot be run."""
    try:
        done = subprocess.run(
            ["pdftohtml", "-xml", "-i", "-q", "-stdout", "-noroundcoord",
             str(path)], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        report.notes["pdftohtml"] = f"unavailable: {e}"
        return []
    if not done.stdout.strip():
        return []

    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(done.stdout, "xml")
    except Exception:
        # bs4 without lxml. The HTML parser reads this document perfectly well
        # - it is flat, and nothing here depends on XML namespaces - it just
        # says so loudly, which is not the caller's problem.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            soup = BeautifulSoup(done.stdout, "html.parser")
    # Font ids are declared once and referred to from every page after, so the
    # colour table is built across the whole document, not per page.
    colours = {fs.get("id"): (fs.get("color") or "")
               for fs in soup.find_all("fontspec")}

    lines = []
    for number, page in enumerate(soup.find_all("page"), 1):
        runs = []
        for tag in page.find_all("text"):
            text = tag.get_text().replace("\xa0", " ")
            if not text.strip():
                continue
            runs.append((float(tag.get("left") or 0), float(tag.get("width") or 0),
                         float(tag.get("top") or 0), text,
                         _is_red(colours.get(tag.get("font")))))
        rows = []
        for run in sorted(runs, key=lambda r: (r[2], r[0])):
            # Five points of slack: the verdict on a finals sheet is set two
            # points below the name it belongs to.
            if rows and abs(rows[-1][0][2] - run[2]) <= 5:
                rows[-1].append(run)
            else:
                rows.append([run])
        for row in rows:
            row.sort(key=lambda r: r[0])
            text, red = "", set()
            for index, (left, width, _top, piece, is_red) in enumerate(row):
                if index:
                    previous = row[index - 1]
                    gap = left - (previous[0] + previous[1])
                    # A wide gap is a column break and must survive as one: the
                    # verdict column is sometimes the only thing separating the
                    # club from the decision.
                    joiner = "  " if gap > 6 else (" " if gap > 1 else "")
                    if joiner == " " and text.endswith(" "):
                        joiner = ""
                    text += joiner
                if is_red:
                    red.update(range(len(text), len(text) + len(piece)))
                text += piece
            lines.append(_Line(number, row[0][2], text.strip(), red))
    return lines


def _plain_lines(path):
    """Lines without colour, via pdftotext. The fallback, and it is a real loss."""
    try:
        done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return []
    return [_Line(0, index, line.rstrip(), set())
            for index, line in enumerate(done.stdout.splitlines())]


# ------------------------------------------------------- the sheet's words ---

# Runs of dots are the column separator on every one of these sheets - a
# table-of-contents leader, not whitespace. One dot is not a separator: the
# sheets put one at the end of a given name ("Vanessa. ") and inside club
# initials ("A.S.C. BF"), and treating those as column breaks splits names.
_LEADER = re.compile(r"(?:[.…]\s*){2,}")

# A class code: F48, M+85, F42J, M150. The lookahead stops it eating the first
# digits of something longer.
_CLASS = re.compile(r"^\s*([FM])\s*(\+)?\s*(\d{2,3})\s*(J)?(?![\dA-Za-zÀ-ÿ])")

# The federation's French name for a weight, which follows the code and carries
# no information the code does not. Matched so it can be removed; the archive's
# category label is built from the code.
_WEIGHT_WORD = re.compile(
    r"^[\s.…\-–—]*((?:[SM]\s*/\s*){0,2}"
    r"(?:mouches|coqs|plumes|l[ée]g[eè]re?s|moyennes|moyens|lourds))"
    r"[\s.…]*", re.I)

# Above this a code is the open class, not a weight. Real savate classes stop at
# 85 kg for men and 75 for women; F100 and M150 are the federation's sentinels.
_SENTINEL = 90

# How the sheets word a verdict. Order matters where one phrase contains
# another; the printed form is kept because "unanimité" and "majorité" are
# different facts about the same decision.
_VERDICTS = [
    ("Forfait", "forfait", r"\bforfaits?\b|\bw\.?\s?o\.?\b"),
    ("Disqualification", "disqualification", r"\bdisqualif\w*"),
    ("Hors combat", "abandon", r"\bhors\s+combat\b|\bh\.?\s?c\.?\b"),
    ("Arrêt médical", "abandon", r"\barr[êe]ts?\s+m[ée]dical\w*"),
    ("Arrêt de l'arbitre", "abandon",
     r"\barr[êe]ts?\s+(?:de\s+l['’]\s*)?arbitre"),
    ("Jet de l'éponge", "abandon",
     r"\bjet\s+d(?:e|['’])?\s*(?:l['’]\s*)?[ée]ponge"),
    ("Abandon", "abandon", r"\babandons?\b"),
    ("KO", "abandon", r"\bk\.?\s?o\.?\b"),
    ("Blessure", "abandon", r"\bblessure\b"),
    ("Unanimité", "points", r"\bunanimit[ée]\b"),
    ("Majorité", "points", r"\bmajorit[ée]\b"),
    ("Partage", "points", r"\bpartages?\b"),
]

# "Victoire à l'unanimité", "Victoire par Hors Combat 2°", "Vainqueur par
# forfait" - the lead-in, cut off the head of the line once the verdict itself
# has been found.
_VICTOIRE = re.compile(
    r"[\s.\u2026]*(?:victoires?|vainqueur(?:e|s|es)?|gagnante?s?)"
    r"\s*(?:à\s*l[’']?|à\s*la|par|sur|:)?\s*$", re.I)

# What may legitimately trail a verdict: the round it happened in.
_ROUND_TAIL = re.compile(
    r"^(?:[\s.…:,\-–—]|\d{1,2}|°|º|er|ere|[èe]re|[èe]me|e|reprise|round)*$",
    re.I)

# A placing, printed where a verdict would be. "Vice" is tested first because
# "Vice Championne" contains "Championne".
_PLACINGS = [
    ("vice", r"\bvice[\s\-–—]*champion(?:ne)?s?\b"),
    ("finalist", r"\bfinalistes?\s*(?:n\s*[°º]\s*)?(\d+)?\b"),
    ("champion", r"\bchampion(?:ne)?s?\b"),
]

# A demonstration is not a bout. Word-bounded on purpose: DEMOUGEOT Franck
# fought eight real bouts in the 2018 qualifiers and a loose "demo" would delete
# every one of them.
_DEMO = re.compile(r"\bd[ée]mo(?:nstration)?s?\b|\bexhibitions?\b|"
                   r"\bhors\s+comp[ée]tition\b", re.I)

# Sports the FFSavate publishes alongside savate and which are not savate.
_OTHER_SPORT = re.compile(
    r"\bcanne\s+de\s+combat\b|\bcanne[\s-]*b[âa]ton\b|\bchausson\b|"
    r"\bb[âa]tons?\b|\bsavate\s+forme\b|^\s*cannes?\s*$", re.I)

# The running head and foot the commission puts on every page.
_FURNITURE = re.compile(r"^\s*(?:cnc\b|page\s+\d|\d+\s*$)", re.I)

_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
           "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
           "novembre": 11, "decembre": 12}


def _fold(text):
    """Accent- and case-insensitive key."""
    import unicodedata
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _verdict(text):
    """(line without the verdict, schema decision, the word printed).

    A verdict is only accepted where nothing but a round number follows it, so a
    club called KO BOXING is not read as a knockout.
    """
    best = None
    for printed, decision, pattern in _VERDICTS:
        for found in re.finditer(pattern, text, re.I):
            if not _ROUND_TAIL.match(text[found.end():]):
                continue
            if best is None or found.start() < best[0].start():
                best = (found, printed, decision)
            break
    if best is None:
        return text, "", ""
    found, printed, decision = best
    head = _VICTOIRE.sub("", text[:found.start()])
    return re.sub(r"[\s.…]+$", "", head), decision, printed


def _placing_label(text):
    """(line without the label, rank or "", the word printed).

    A rank of "" with a printed word is a placing the sheet stated and this
    adapter will not number - the "Finaliste N" case the module docstring sets
    out. The caller counts those; it must not invent a number for them.
    """
    for kind, pattern in _PLACINGS:
        for found in re.finditer(pattern, text, re.I):
            if not re.match(r"^[\s.…:,\-–—]*$", text[found.end():]):
                continue
            # The label stands in its own column, reached by a dot leader or
            # a wide gap. Without that a club called SAVATE CHAMPION would
            # read as a gold medal.
            if not re.search(r"(?:[.…]\s*|\s{2,})$", text[:found.start()]):
                continue
            head = re.sub(r"[\s.…\-–—]+$", "", text[:found.start()])
            printed = " ".join(found.group(0).split())
            if kind == "vice":
                return head, "2", printed
            if kind == "champion":
                return head, "1", printed
            return head, "", printed
    return text, "", ""


def _is_caps(word):
    letters = [c for c in word if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


_PARTICLES = {"de", "du", "da", "des", "del", "della", "di", "dos", "le", "la",
              "van", "von", "der", "den", "ben", "el", "al", "y", "et"}


def _split_name_club(text):
    """(competitor, club as printed) from the middle of a competitor's line.

    Two ways, because the sheets use two. Where a dot leader separates the
    columns it is trusted. Where the export lost it - and it often does, leaving
    "BERNARD Hugo NARBONNE SAVATE MEDITERRANEE (11)" - the split falls back on
    the one typographic rule these sheets keep: club names are set in capitals
    throughout and given names are not.
    """
    text = " ".join(str(text or "").split())
    # A dot glued between a name and a club: "Thomas de Dieu.CS CLICHY".
    text = re.sub(r"(?<=[a-zà-ÿ])\.(?=[A-ZÀ-Þ])", ". ", text)

    chunks = [c.strip(" .…") for c in _LEADER.split(text)]
    chunks = [c for c in chunks if c]
    if len(chunks) >= 2:
        name, rest = chunks[0], chunks[1:]
        club = next((c for c in rest if re.search(r"[A-Za-zÀ-ÿ]", c)), "")
    else:
        name, club = _split_on_case(text)

    # A leader that fell in the middle of a person: "NIVAULT-TERNIN-ROZAT ...
    # Alexis MJC SAVATE COTOISE". A capitalised-but-not-capitals word at the
    # front of a club is a given name that lost its column - but a single
    # capital is not: clubs are called "S SAVATITUDE" and "C S CLICHY", and
    # welding their initial onto the competitor invents a middle name.
    while club:
        head = club.split(" ", 1)
        if len(head) < 2:
            break
        word = head[0]
        if (_is_caps(word) or not word[:1].isupper()
                or len([c for c in word if c.isalpha()]) < 2):
            break
        name = f"{name} {word}".strip()
        club = head[1].strip()
    return name.strip(" .…"), club.strip(" .…")


def _split_on_case(text):
    """"BERNARD Hugo NARBONNE SAVATE (11)" -> ("BERNARD Hugo", "NARBONNE ...")."""
    words = text.split()
    if not words:
        return "", ""
    index = 0
    while index < len(words) and _is_caps(words[index]):
        index += 1          # the surname, in capitals
    if index == 0 or index >= len(words):
        return text, ""
    seen_given = False
    while index < len(words):
        word = words[index].strip(".")
        if not word:
            index += 1
            continue
        if _is_caps(word):
            break           # capitals again: the club has started
        if word[:1].isupper() or (seen_given and _fold(word) in _PARTICLES):
            seen_given = True
            index += 1
            continue
        break
    return (" ".join(words[:index]).strip(),
            " ".join(words[index:]).strip(" .…"))


# A club and the département the sheet brackets after it. The brackets are
# sometimes only half printed - "CS MEAUX (77", "PUNCH BLAGNAC 31)" - so one is
# enough, and a club with no bracket at all keeps its figures.
_CLUB = re.compile(r"^(.*?)[\s.…]*(?:\(\s*(\d{2,3})\s*\)?|\(?\s*(\d{2,3})\s*\))$")


def _club(text):
    found = _CLUB.match(" ".join(str(text or "").split()))
    return found.group(1).strip(" .,-") if found else " ".join(str(text or "").split())


def _looks_like_person(text):
    """Two or more words, one of them capitals, no digits. A name, not a club.

    Every word must carry a letter, which is what separates "SICLET-CAVALIE
    Flavie" from "CROATIA - tbd": a hyphen inside a surname has no spaces round
    it, and a word that is only punctuation belongs to a venue line.
    """
    text = " ".join(str(text or "").split())
    if not text or re.search(r"\d", text):
        return False
    words = text.split()
    if len(words) < 2 or not all(re.search(r"[A-Za-zÀ-ÿ]", w) for w in words):
        return False
    return any(_is_caps(w) for w in words)


# ------------------------------------------------------------ the headings ---

_AGE_WORDS = [
    ("Minime", r"\bminimes?\b"),
    ("Cadet", r"\bcadet(?:te)?s?\b"),
    ("Junior", r"\bjuniors?\b"),
    ("Espoir", r"\bespoirs?\b"),
    ("Vétéran", r"\bv[ée]t[ée]rans?\b"),
    ("Senior", r"\bseniors?\b"),
]


def _age_of(text):
    for name, pattern in _AGE_WORDS:
        if re.search(pattern, text, re.I):
            return name
    return ""


_PHASE_WORDS = re.compile(
    r"\bfinales?\b|\bdemi\b|[½¼]|\b1\s*/\s*[248]\b|\b[¼½]\s*finale|"
    r"\bquarts?\b|\bhuiti[èe]mes?\b|\bpoules?\b|\b[ée]liminatoires?\b", re.I)


def _phase_of(text):
    """The round a heading names, or "" - never a guess.

    `schema.phase_of` does the mapping; this only puts the fractions the sheets
    typeset ("½ finales", "¼ de finales") into the wording it knows.
    """
    text = (" ".join(str(text or "").split())
            .replace("½", " 1/2 ").replace("¼", " 1/4 ").replace("⅛", " 1/8 "))
    if re.search(r"\bpoules?\b|\b[ée]liminatoire", text, re.I) \
            and not re.search(r"final", text, re.I):
        return "poule"
    return phase_of(text)


def _headline(lines, tournament, report):
    """Read the title block: what the sheet calls itself, when, and where.

    Only the lines above the first result. A club name can hold a month and a
    competitor's line can hold a town, and either would date the meeting wrong.
    """
    head = []
    for line in lines[:16]:
        if not line.text.strip():
            continue
        if _CLASS.match(line.text) or _FIXTURE.match(line.text):
            break
        head.append(line.text)
    title = ""
    for text in head:
        if not title and re.search(
                r"championnat|coupe|tournoi|open|finales?|r[ée]sultats", text, re.I):
            title = " ".join(text.split())
        when, city = _when(text)
        if when and not tournament.start_date:
            tournament.start_date, tournament.end_date = when
            tournament.year = tournament.year or when[0][:4]
        if city and not tournament.city:
            tournament.city = city
    report.notes["title"] = title
    if not tournament.name:
        tournament.name = title
    if not tournament.start_date:
        report.notes["undated"] = "no date line found in the title block"
    if not tournament.year:
        # "CHAMPIONNAT D'EUROPE COMBAT 2018" dates itself without a day.
        year = re.search(r"\b(?:19|20)\d{2}\b", " ".join(head[:4]))
        if year:
            tournament.year = year.group(0)


_VENUE_WORDS = re.compile(
    r"^(?:l[ae]s?\b|l['’]|un[e]?\b|gymnase|salle|halle|institut|stade|centre|"
    r"complexe|palais|espace|dojo|parc)", re.I)


def _when(text):
    """((start ISO, end ISO), city) from a dated venue line, or ((), "").

    French sheets date themselves in prose, in every shape prose allows:
    "21 février 2015", "les 23/24 MAI 2015", "les 13 et 14 novembre 2021",
    "17 au 21 octobre 2018", "les 31 mars et 1er Avril 2018". Only the days
    printed before the first month name are read; a line that spans two months
    keeps the first, which is the start date and the only part of it that is
    certain.
    """
    text = " ".join(str(text or "").split())
    folded = _fold(text)
    first = None
    for name, number in _MONTHS.items():
        hit = re.search(rf"\b{name}\b", folded)
        if hit and (first is None or hit.start() < first[0].start()):
            first = (hit, number)
    if first is None:
        return (), _city(text)
    hit, month = first
    year = re.search(r"\b(?:19|20)\d{2}\b", text)
    if not year:
        return (), _city(text)
    days = [int(d) for d in
            re.findall(r"\b(\d{1,2})(?:er)?\b", folded[:hit.start()])
            if 1 <= int(d) <= 31]
    if not days:
        return (), _city(text)
    start = f"{year.group(0)}-{month:02d}-{min(days):02d}"
    end = f"{year.group(0)}-{month:02d}-{max(days):02d}"
    return (start, end if end != start else ""), _city(text)


def _city(text):
    """The town a venue line names, where it names one rather than a building."""
    found = re.search(r"\b[àa]\s+([^(,]{2,40})", text)
    if not found:
        return ""
    where = " ".join(found.group(1).split())
    if _VENUE_WORDS.match(where):
        return ""
    # "Paris - Stade Pierre de Coubertin le 13 avril" - the town, then what else
    # the line wanted to say. A hyphen inside a name (ILLE-SUR-TET) is not that.
    where = re.split(r"\s[-–—]\s|\s+(?:le|les|du|de)\s+\d", where)[0].strip()
    return where.title() if where.isupper() else where


# ---------------------------------------------------------------- the rows ---


class _Competitor:
    __slots__ = ("name", "club", "decision", "printed", "rank", "label", "line")

    def __init__(self, name, club, decision, printed, rank, label, line):
        self.name, self.club = name, club
        self.decision, self.printed = decision, printed
        self.rank, self.label, self.line = rank, label, line


def _category(letter, kilos, plus, age, report):
    """(label, gender, kg, bound) for a class code, the open class included."""
    gender = "Women" if letter.upper() == "F" else "Men"
    prefix = f"{age} " if age else ""
    if plus:
        return f"{prefix}{gender} +{kilos} kg", gender, str(kilos), "over"
    if kilos >= _SENTINEL:
        code = f"{letter.upper()}{kilos}"
        seen = report.notes.setdefault("sentinel_classes", [])
        if code not in seen:
            seen.append(code)
        return f"{prefix}{gender} open", gender, "", "over"
    return f"{prefix}{gender} -{kilos} kg", gender, str(kilos), "under"


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) for one FFSavate sheet."""
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    path = sources.fetch(source)

    lines = _xml_lines(path, report)
    if not lines:
        lines = _plain_lines(path)
        if lines:
            report.problem("read without colour: pdftohtml could not be run, so "
                           "any red-ink winner on this sheet is lost")
    if not lines:
        report.problem("no text layer - this is a scan, or poppler is missing")
        bare = _tournament(slug, meta, source)
        bare.name = bare.name or slug
        return bare, [], report

    report.read = len(lines)
    tournament = _tournament(slug, meta, source)
    _headline(lines, tournament, report)
    tournament.name = tournament.name or slug

    body = [line for line in lines if line.text.strip()
            and not _FURNITURE.match(line.text)]

    text = "\n".join(line.text for line in body)
    if re.search(r"\bcat\b.*\br[ée]sultat\b.*\bpays\b", text, re.I):
        rows = _podium_table(body, slug, meta, tournament, report)
    elif len(re.findall(r"^\s*FINALE\s+[FM]\s*\+?\s*\d", text, re.M)) >= 2:
        rows = _fixture_sheet(body, slug, meta, tournament, report)
    elif len(re.findall(r"^\s*(?:FINALES?|BRONZE|\d\s*[.)])\s+.+\([A-Za-z]{2,4}\)\s*$",
                        text, re.M)) >= 3:
        rows = _ranked_list(body, slug, meta, tournament, report)
    else:
        rows = _french_sheet(body, slug, meta, tournament, report)

    _finish(rows, report)
    return tournament, rows, report


def _finish(rows, report):
    from savate import schema

    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    bad = 0
    for row in rows:
        check = schema.check if isinstance(row, Bout) else schema.check_placing
        for complaint in check(row):
            bad += 1
            if bad <= 10:
                report.problem(f"malformed row: {complaint}")
    if bad > 10:
        report.problem(f"...and {bad - 10} more malformed rows")
    if report.notes.get("sentinel_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["sentinel_classes"]) +
            " read as the open class: the code exceeds every real savate weight "
            "and no document states what it stands for")
    if not rows:
        report.problem("no rows found - this may not be a results sheet")


# ------------------------------------------- A/B/C: the French house sheets ---


def _weight_words(lines):
    """{(F|M, the French weight name): (plus, kilos)} as THIS sheet prints it.

    The poule pages of the qualifying sheets head each round robin with the
    weight's French name alone - "Mouches", "Légères", "Lourds" - while the
    quarters and finals of the same file print the code and the name together,
    "F60 ... Légères". The correspondence is therefore stated by the document,
    not supplied from outside it, and reading it is what gives 196 poule bouts
    in the 2018 qualifiers a weight class instead of none.
    """
    table = {}
    for line in lines:
        found = _CLASS.match(line.text)
        if not found:
            continue
        word = _WEIGHT_WORD.match(line.text[found.end():])
        if not word:
            continue
        table.setdefault((found.group(1).upper(), _fold(word.group(1))),
                         (bool(found.group(2)), int(found.group(3))))
    return table


_SEXES = [("F", r"\bf[ée]minin|\bfilles?\b|\bdames?\b|\bfemmes?\b|\bwomen\b|"
                r"\bcadettes\b|\bgirls?\b"),
          ("M", r"\bmasculin|\bgar[çc]ons?\b|\bhommes?\b|\bmen\b|\bboys?\b")]


def _sex_of(text):
    for letter, pattern in _SEXES:
        if re.search(pattern, text, re.I):
            return letter
    return ""


def _french_sheet(lines, slug, meta, tournament, report):
    """The dotted sheets, the red-ink poules, and the veterans' technique list.

    One pass, because a single file mixes them: the 2018 Coupe de France prints
    its poules in red ink and its finals in dots, and the 2021 championship adds
    quarters and semis in between.
    """
    rows = []
    counts = {"demo": 0, "other_sport": 0, "unranked": {}, "unsigned": 0,
              "ambiguous_ink": 0, "routing": 0}
    words = _weight_words(lines)
    state = {"phase": _phase_of(tournament.name),
             "age": _age_of(tournament.name) or meta.get("age_class", ""),
             "sex": "", "class": None, "block": []}

    def flush():
        _emit_block(state, rows, slug, meta, tournament, report, counts)

    def set_class(letter, plus, kilos):
        key = (letter, plus, kilos, state["phase"], state["age"])
        if state["class"] != key:
            flush()
            state["class"] = key

    for line in lines:
        text = line.text
        if _DEMO.search(text):
            counts["demo"] += 1
            continue
        if _OTHER_SPORT.search(text):
            counts["other_sport"] += 1
            continue

        found = _CLASS.match(text)
        rest = text[found.end():] if found else ""
        if found and not re.sub(r"[\s.\u2026\-–—]", "", _WEIGHT_WORD.sub("", rest)):
            # A class banner: "F60", "M60 - Légers". It sets the class for the
            # pairings under it, which carry no code of their own.
            set_class(found.group(1).upper(), bool(found.group(2)),
                      int(found.group(3)))
            continue

        if found and rest.strip():
            competitor = _competitor(_WEIGHT_WORD.sub("", rest), line)
            if competitor:
                set_class(found.group(1).upper(), bool(found.group(2)),
                          int(found.group(3)))
                state["block"].append(competitor)
                continue

        pair = _pair_line(text, line)
        if pair:
            flush()
            # "CHATEL Lucie / LAWSON BOUH-MANA Maïmara ......... finale" - a
            # class with two entries has no round robin, and the sheet says so
            # where a verdict would go. That is a note about the draw, not a
            # result; the bout itself is on the finals page of the same file,
            # and storing this line too would double it.
            if not pair[2] and _phase_of(_LEADER.split(text)[-1].strip()):
                counts["routing"] += 1
                continue
            rows.extend(_pair_rows(pair, state, slug, meta, tournament,
                                   report, counts, len(rows)))
            continue

        technique = _technique_line(text, line)
        if technique:
            state["block"].append(technique)
            continue

        # A weight name standing on its own, over a round robin: the class is
        # whatever this same document pairs that name with, for this sex.
        word = _WEIGHT_WORD.match(text)
        if word and not text[word.end():].strip(" .\u2026-"):
            klass = words.get((state["sex"], _fold(word.group(1))))
            if klass:
                set_class(state["sex"], klass[0], klass[1])
                report.notes.setdefault("weight_words_resolved", [])
                entry = f"{word.group(1)} -> {state['sex']}{klass[1]}"
                if entry not in report.notes["weight_words_resolved"]:
                    report.notes["weight_words_resolved"].append(entry)
            else:
                flush()
                state["class"] = None
                report.notes.setdefault("weight_words_unresolved", [])
                if text not in report.notes["weight_words_unresolved"]:
                    report.notes["weight_words_unresolved"].append(text)
            continue

        # Anything left is furniture or a heading. A heading may move the round,
        # the age group or the sex, and all three must land before the next
        # block is read.
        sex = _sex_of(text)
        phase = _PHASE_WORDS.search(text)
        age = _age_of(text)
        if sex or phase or age:
            flush()
            if phase:
                state["phase"] = _phase_of(text)
            if age:
                state["age"] = age
            if sex:
                state["sex"] = sex
    flush()

    if report.notes.get("weight_words_unresolved"):
        report.problem(
            "weight banner(s) this sheet never pairs with a class code, so the "
            "bouts under them carry no weight class: " +
            ", ".join(report.notes["weight_words_unresolved"]))
    _count_up(report, counts)
    return rows


def _competitor(text, line):
    """One competitor's line, or None if it is not one."""
    body, decision, printed = _verdict(text)
    rank, label = "", ""
    if not decision:
        body, rank, label = _placing_label(body)
    name, club = _split_name_club(body)
    if not name or not re.search(r"[A-Za-zÀ-ÿ]{2}", name):
        return None
    return _Competitor(name, _club(club), decision, printed, rank, label, line)


_TECHNIQUE = re.compile(r"^\s*(.+?)\s+[-–—]\s+(.+)$")


def _technique_line(text, line):
    """"GROS Stéphane - BC FRANOIS SERRE (25)   Champion", or None."""
    body, rank, label = _placing_label(text)
    if not label or body == text:
        return None
    found = _TECHNIQUE.match(body)
    if not found or not _looks_like_person(found.group(1)):
        return None
    return _Competitor(found.group(1).strip(), _club(found.group(2)),
                       "", "", rank, label, line)


def _emit_block(state, rows, slug, meta, tournament, report, counts):
    """Turn one class block into bouts, or into placings, or into nothing."""
    block, key = state["block"], state["class"]
    state["block"] = []
    if not block:
        return
    if key is None:
        key = ("M", False, 0, state["phase"], state["age"])
    letter, plus, kilos, phase, age = key
    label, gender, weight, bound = _category(letter, kilos, plus, age, report)

    if any(c.label for c in block):
        _emit_placings(block, rows, slug, meta, label, gender, age, weight,
                       bound, counts)
        return

    if len(block) % 2:
        report.problem(f"{label} {phase or 'round unknown'}: {len(block)} "
                       f"competitor line(s), which do not pair into bouts; "
                       f"{block[-1].name} left unread")
    for index in range(0, len(block) - 1, 2):
        first, second = block[index], block[index + 1]
        winner = [c for c in (first, second) if c.decision]
        if len(winner) > 1:
            report.problem(f"{label}: both {first.name} and {second.name} carry "
                           f"a verdict; stored unresolved")
            winner = []
        winner = winner[0] if winner else None
        rows.append(_bout(slug, len(rows), label, gender, age, weight, bound,
                          phase, first, second, winner, counts))
        # A decided final is also a podium, and the two facts are worth keeping
        # apart: the bout says who beat whom, the placings say who finished
        # where. Only a final produces them - a semi-final says nothing about
        # where its loser ended up, and savate awards two bronzes for reasons
        # this sheet never prints.
        if phase == "final" and winner is not None:
            loser = second if winner is first else first
            for rank, who in (("1", winner), ("2", loser)):
                rows.append(Placing(
                    tournament=slug,
                    placing_id=f"{slug}-p{len(rows) + 1:03d}",
                    category=label, gender=gender, age_class=age,
                    weight_kg=weight, weight_bound=bound,
                    rank=rank, medal=MEDALS[rank],
                    fighter=who.name, club=who.club,
                    country=meta.get("country", ""),
                    result_source="reported"))


def _bout(slug, index, label, gender, age, weight, bound, phase,
          first, second, winner, counts):
    if winner is None:
        counts["unsigned"] += 1
    loser = None
    if winner is not None:
        loser = second if winner is first else first
    return Bout(
        tournament=slug,
        bout_id=f"{slug}-{index + 1:03d}",
        category=label, gender=gender, age_class=age,
        weight_kg=weight, weight_bound=bound, phase=phase,
        # Printed order. The sheet never says who stood in which corner and
        # this does not pretend otherwise: winner_corner stays empty.
        red=first.name, red_club=first.club,
        blue=second.name, blue_club=second.club,
        winner=winner.name if winner else "",
        loser=loser.name if loser else "",
        winner_corner="",
        decision=(winner.decision if winner else
                  first.decision or second.decision),
        decision_detail=(winner.printed if winner else
                         first.printed or second.printed),
        status="decided" if winner else "unresolved",
        result_source="reported" if winner else "",
    )


def _emit_placings(block, rows, slug, meta, label, gender, age, weight, bound,
                   counts):
    for competitor in block:
        if not competitor.rank:
            counts["unranked"].setdefault(competitor.label or "?", 0)
            counts["unranked"][competitor.label or "?"] += 1
            continue
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{len(rows) + 1:03d}",
            category=label, gender=gender, age_class=age,
            weight_kg=weight, weight_bound=bound,
            rank=competitor.rank, medal=MEDALS.get(competitor.rank, ""),
            fighter=competitor.name, club=competitor.club,
            country=meta.get("country", ""),
            result_source="reported",
        ))


# --------------------------------------------------- B: the red-ink poules ---

_PAIR = re.compile(r"^(?P<a>[^/]{3,}?)\s*/\s*(?P<b>[^/]{3,})$")


def _pair_line(text, line):
    """(A, B, decision, printed, line) for "A / B ..... Unanimité", or None."""
    if _CLASS.match(text):
        return None
    body, decision, printed = _verdict(text)
    body = re.sub(r"[\s.…]+$", "", body)
    if body.count("/") != 1:
        return None
    found = _PAIR.match(body)
    if not found:
        return None
    # A leader inside either half is the sheet's column rule, never part of a
    # name, so whatever follows one belongs to some other field.
    first = _LEADER.split(found.group("a"))[0].strip(" .\u2026")
    second = _LEADER.split(found.group("b"))[0].strip(" .\u2026")
    if not (_looks_like_person(first) and _looks_like_person(second)):
        return None
    return first, second, decision, printed, line


def _pair_rows(pair, state, slug, meta, tournament, report, counts, index):
    first, second, decision, printed, line = pair
    # The winner is the name set in red, and nothing else on the page says it.
    # The colour is read off the glyph; where both sides or neither are red, the
    # bout is stored unresolved rather than decided on a coin toss.
    split = line.text.find("/", len(first) - 1)
    if split < 0:
        split = line.text.find("/")
    red_first = line.red_between(0, split)
    red_second = line.red_between(split + 1, len(line.text))
    winner = ""
    if red_first and not red_second:
        winner = first
    elif red_second and not red_first:
        winner = second
    elif red_first and red_second:
        counts["ambiguous_ink"] += 1
    if not winner:
        counts["unsigned"] += 1

    age = state["age"]
    if state["class"]:
        letter, plus, kilos = state["class"][0], state["class"][1], state["class"][2]
        label, gender, weight, bound = _category(letter, kilos, plus, age, report)
    else:
        # A poule sheet that never printed a class banner above this pairing.
        # The class is then genuinely unknown and is left so.
        label, gender, weight, bound = "", "", "", ""
        report.notes.setdefault("classless_pairings", 0)
        report.notes["classless_pairings"] += 1
    return [Bout(
        tournament=slug,
        bout_id=f"{slug}-{index + 1:03d}",
        category=label, gender=gender, age_class=age,
        weight_kg=weight, weight_bound=bound,
        phase=state["phase"] or "poule",
        red=first, blue=second,
        winner=winner, loser=(second if winner == first else first) if winner else "",
        winner_corner="",
        decision=decision, decision_detail=printed,
        status="decided" if winner else "unresolved",
        result_source="reported" if winner else "",
    )]


# ------------------------------------------------- D: the podium table ---

_PODIUM_ROW = re.compile(
    r"^\s*(?:([FM]\s*\+?\s*\d{2,3}J?)\s{1,}|\s*)"
    r"(vice[\s\-]*champion(?:ne)?|champion(?:ne)?)\s{2,}"
    r"(.+?)\s{2,}(.+?)\s{2,}(\S[^\s].*?)\s*$", re.I)


def _podium_table(lines, slug, meta, tournament, report):
    """The world championship's medal table: CAT, Résultat, Prénom, NOM, PAYS.

    The only sheet in the group that prints the given name in its own column,
    and that names a nation. The columns are labelled, so they are read as
    labelled and the name is stored the way the rest of the archive stores one.
    """
    rows, current, age = [], None, _age_of(tournament.name) or meta.get("age_class", "")
    for line in lines:
        found = _PODIUM_ROW.match(line.text)
        if not found:
            continue
        code, result, given, surname, nation = found.groups()
        if code:
            current = code
        if not current:
            report.problem(f"podium row with no weight class: {line.text!r}")
            continue
        klass = _CLASS.match(current)
        label, gender, weight, bound = _category(
            klass.group(1), int(klass.group(3)), bool(klass.group(2)), age, report)
        rank = "2" if re.match(r"vice", result, re.I) else "1"
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-p{len(rows) + 1:03d}",
            category=label, gender=gender, age_class=age,
            weight_kg=weight, weight_bound=bound,
            rank=rank, medal=MEDALS[rank],
            fighter=f"{surname.strip()} {given.strip()}".strip(),
            country=_nation(nation),
            result_source="reported",
        ))
    report.notes["layout"] = "podium table (CAT / Résultat / Prénom / NOM / PAYS)"
    return rows


# ------------------------------------ E: the European championship's lists ---

_NATION = re.compile(r"^(.*?)\s*\(\s*([A-Za-z]{2,4})\s*\)\s*$")
_RANKED = re.compile(r"^\s*(\d)\s*[.)]\s+(.+)$")
_LABELLED = re.compile(
    r"^\s*(finales?|bronzes?|vice[\s\-]*champion(?:ne)?|champion(?:ne)?)\s+(.+)$",
    re.I)


def _ranked_list(lines, slug, meta, tournament, report):
    """The Pamiers sheet: a numbered classification, and a list of finalists.

    "FINALES" names the two who reached the final - not the gold and the silver.
    The final itself was fought months later at a separate gala, so neither of
    them is ranked here and neither is given a rank. They are stored as the
    final, unresolved. "BRONZE" is a finishing position and is stored as one,
    twice per class where the sheet prints it twice, which is correct.
    """
    rows, pending = [], []
    age = _age_of(tournament.name) or meta.get("age_class", "")
    klass = None
    counts = {"finalists": 0}

    def flush():
        if len(pending) == 2 and klass:
            label, gender, weight, bound = klass
            rows.append(Bout(
                tournament=slug, bout_id=f"{slug}-{len(rows) + 1:03d}",
                category=label, gender=gender, age_class=age,
                weight_kg=weight, weight_bound=bound, phase="final",
                red=pending[0][0], red_country=pending[0][1],
                blue=pending[1][0], blue_country=pending[1][1],
                status="unresolved", result_source=""))
            counts["finalists"] += 2
        elif pending:
            report.problem(f"{klass[0] if klass else '?'}: {len(pending)} "
                           f"finalist(s) listed, which is not a final")
        pending.clear()

    for line in lines:
        text = line.text
        found = _CLASS.match(text)
        if found and not text[found.end():].strip(" .…-"):
            flush()
            klass = _category(found.group(1), int(found.group(3)),
                              bool(found.group(2)), age, report)
            continue
        if _age_of(text) and not _RANKED.match(text) and not _LABELLED.match(text):
            flush()
            age = _age_of(text) or age
            continue
        if klass is None:
            continue

        found = _RANKED.match(text)
        if found:
            flush()
            who, nation = _person(found.group(2))
            if who:
                rows.append(_placing(slug, len(rows), klass, age, found.group(1),
                                     who, _nation(nation), meta))
            continue
        found = _LABELLED.match(text)
        if not found:
            continue
        kind, rest = found.group(1).lower(), found.group(2)
        who, nation = _person(rest)
        if not who:
            continue
        if kind.startswith("final"):
            pending.append((who, _nation(nation)))
            continue
        flush()
        rank = ("3" if kind.startswith("bronze")
                else "2" if kind.startswith("vice") else "1")
        rows.append(_placing(slug, len(rows), klass, age, rank, who,
                             _nation(nation), meta))
    flush()

    report.notes["layout"] = "European championship classification"
    if counts["finalists"]:
        report.problem(
            f"{counts['finalists']} competitor(s) listed under FINALES are "
            f"stored as an unresolved final: the sheet says they reached it, "
            f"never which of them won it")
    return rows


def _trim(text):
    """Trim a leader and stray punctuation, but never an initial's full stop.

    "GARCIA PERREIRA M." is a name the sheet abbreviated, and the stop is part
    of it; "DOZDOR Roko ......" is a name with a column rule after it.
    """
    text = re.sub(r"\s*(?:[.\u2026]\s*){2,}\s*$", "", " ".join(str(text or "").split()))
    text = text.strip(" ,;:")
    if text.endswith(".") and not re.search(r"\b[A-ZÀ-Þ]\.$", text):
        text = text[:-1].rstrip()
    return text


def _nation(printed):
    """A nation as the sheet printed it, in the archive's usual spelling.

    A three-letter code is kept exactly as printed - `savate.display` is the
    lens that turns "CRO" into Croatia, and the archive's rule is that the store
    holds what the document said. A country written out in French is mapped,
    because "SERBIE" and "Serbia" have to be one country for a fighter's career
    to join up across sheets.
    """
    from savate import normalize as norm

    text = " ".join(str(printed or "").split())
    if re.fullmatch(r"[A-Za-z]{2,4}", text):
        return text.upper()
    return norm.country(text)


def _person(text):
    """("SURNAME Given", nation as printed) from "SURNAME Given (FRA)"."""
    found = _NATION.match(" ".join(str(text or "").split()))
    if found:
        return _trim(found.group(1)), found.group(2).upper()
    text = _trim(text)
    return (text, "") if _looks_like_person(text) else ("", "")


def _placing(slug, index, klass, age, rank, who, nation, meta):
    label, gender, weight, bound = klass
    return Placing(
        tournament=slug, placing_id=f"{slug}-p{index + 1:03d}",
        category=label, gender=gender, age_class=age,
        weight_kg=weight, weight_bound=bound,
        rank=str(rank), medal=MEDALS.get(str(rank), ""),
        fighter=who, country=nation, club="",
        result_source="reported")


# ------------------------------------------------- F: the finals fixtures ---

_FIXTURE = re.compile(r"^\s*FINALES?\s+([FM]\s*\+?\s*\d{2,3})\s+(.*)$", re.I)
_TITLE_LINE = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s*(?:[-–—]|\bà\b)?\s*(.*)$")


def _fixture_sheet(lines, slug, meta, tournament, report):
    """"Répartition des finales": who meets whom, where, and on what day.

    Published months before the finals it lists, so all but one of them had no
    result to publish. They are bouts that were arranged, not bouts that were
    reported: stored unresolved, with the date the sheet gives. The one final
    already fought is named outright ("Championne d'Europe") and is stored
    decided, with its two placings.
    """
    rows, block, klass, age = [], [], None, _age_of(tournament.name)
    scheduled = {"count": 0}

    def flush():
        if klass and block:
            rows.extend(_fixture_rows(block, klass, age, slug, len(rows),
                                      scheduled))
        block.clear()

    for line in lines:
        text = line.text
        found = _FIXTURE.match(text)
        if found:
            flush()
            code = _CLASS.match(found.group(1))
            klass = _category(code.group(1), int(code.group(3)),
                              bool(code.group(2)), age, report)
            block.append(found.group(2).strip())
            continue
        if _age_of(text) and not klass:
            age = _age_of(text) or age
            continue
        if klass and text.strip():
            if _age_of(text) and not re.search(r"\(", text):
                flush()
                klass, age = None, _age_of(text)
                continue
            block.append(text.strip())
    flush()

    report.notes["layout"] = "finals fixture list"
    # These finals were fought at half a dozen separate galas, so the sheet has
    # no one venue and the one it happens to print first is not it.
    tournament.city = ""
    if scheduled["count"]:
        report.problem(
            f"{scheduled['count']} final(s) stored unresolved: this sheet is a "
            f"schedule, published before the finals it lists were fought, so a "
            f"pairing here is an arrangement and not a missing result")
    return rows


_CROWNED = re.compile(r"\b(vice[\s\-]*champion(?:ne)?|champion(?:ne)?)\b", re.I)


def _fixture_rows(block, klass, age, slug, index, scheduled):
    from savate import normalize as norm

    label, gender, weight, bound = klass
    people, when, where = [], "", ""
    for text in block:
        found = _TITLE_LINE.match(text)
        if found and found.group(1):
            when = when or norm.date(found.group(1))
            where = where or re.sub(r"\(.*?\)", "", found.group(2)).strip(" -–—.")
            continue
        for part in re.split(r"\s*/\s*", text):
            part = part.strip()
            if not part:
                continue
            crowned = _CROWNED.search(part)
            rank = ""
            if crowned:
                rank = "2" if re.match(r"vice", crowned.group(0), re.I) else "1"
                part = _CROWNED.sub("", part)
                part = re.sub(r"\bd[’']\s*europe\b", "", part, flags=re.I).strip()
            who, nation = _person(part)
            # On this sheet every competitor carries a nation in brackets, and
            # the lines that do not are the venue: "CROATIA - tbd", "08/12/2018
            # - La Motte Servolex". Requiring the bracket is what keeps a town
            # out of the draw.
            if who and (nation or rank):
                people.append((who, _nation(nation), rank))
    if len(people) != 2:
        return []

    first, second = people
    winner = next((p for p in people if p[2] == "1"), None)
    rows = [Bout(
        tournament=slug, bout_id=f"{slug}-{index + 1:03d}",
        date=when, category=label, gender=gender, age_class=age,
        weight_kg=weight, weight_bound=bound, phase="final",
        red=first[0], red_country=first[1],
        blue=second[0], blue_country=second[1],
        winner=winner[0] if winner else "",
        loser=(second[0] if winner is first else first[0]) if winner else "",
        winner_corner="",
        status="decided" if winner else "unresolved",
        result_source="reported" if winner else "")]
    if not winner:
        scheduled["count"] += 1
        return rows
    for who, nation, rank in people:
        if not rank:
            continue
        rows.append(Placing(
            tournament=slug, placing_id=f"{slug}-p{index + 1:03d}-{rank}",
            category=label, gender=gender, age_class=age,
            weight_kg=weight, weight_bound=bound,
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=who, country=nation, result_source="reported"))
    return rows


# ------------------------------------------------------------- the report ---


def _count_up(report, counts):
    if counts["demo"]:
        report.problem(f"{counts['demo']} demonstration line(s) excluded: a demo "
                       f"has no result and is not a bout")
    if counts["other_sport"]:
        report.problem(f"{counts['other_sport']} line(s) excluded as another "
                       f"sport (canne de combat, chausson, bâton, savate forme)")
    if counts["unsigned"]:
        report.problem(f"{counts['unsigned']} bout(s) stored unresolved: the "
                       f"sheet names both fighters and no winner")
    if counts.get("routing"):
        report.problem(f"{counts['routing']} pairing(s) marked 'finale' instead "
                       f"of a verdict and not stored: the class had two entries "
                       f"and no round robin, and the bout is on this sheet's "
                       f"finals page")
    if counts["ambiguous_ink"]:
        report.problem(f"{counts['ambiguous_ink']} bout(s) print both names in "
                       f"red, so the ink does not say who won")
    if counts["unranked"]:
        detail = ", ".join(f"{count}x {label!r}"
                           for label, count in sorted(counts["unranked"].items()))
        report.notes["unranked_placings"] = counts["unranked"]
        report.problem(
            f"{sum(counts['unranked'].values())} placing(s) not stored, because "
            f"the sheet states a finishing label it does not number: {detail}. "
            f"The Trophée Denise Avédiguian rules printed in the same file score "
            f"a 'finaliste N°3' and a 'finaliste N°4' differently, so these are "
            f"ranked positions - but the results list numbers its finalists from "
            f"one and the trophy numbers them from three, and no document here "
            f"settles which is meant")


def _tournament(slug, meta, source):
    return Tournament(
        slug=slug, name=meta.get("name", ""),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""),
        format=meta.get("format", ""),
        age_class=meta.get("age_class", ""),
        year=meta.get("year", ""),
        country=meta.get("country", "France"),
        source=str(source), adapter=NAME,
        competition=meta.get("competition", ""),
    )
