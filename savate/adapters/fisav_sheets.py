"""Adapter for FISav's hand-made result sheets - the ones nobody generated.

The international federation has never had one results format. Between 2008 and
2025 it published in whatever its technical director had open at the time: a
Word table of ranks, a bulleted podium, a finals memo signed by hand, a
spreadsheet of poule cross-tables, an HTML news article. The four FISav adapters
already here read the three *generated* layouts - the poule grid, the pool sheet
and the per-category worksheet. This one reads the rest: the sheets a person
typed.

They have nothing in common at the pixel level, so this does not try to be one
parser. It is a set of small readers, each of which recognises its own document
and refuses the others, and a shared vocabulary of the things all of them state:
a weight class, a finishing rank, a fighter and a nation. A document that no
reader recognises yields no rows and says so in the Report, which is the correct
answer for a reader that does not understand a page.

What the readers are, and the one thing each gets wrong if written carelessly:

  medal_words     bulleted podiums - "MEDAILLE D'OR", "Championne du monde :".
                  The separator between a name and its country is an en-dash in
                  one line and a hyphen in the next, and "Jean-Louis Polimon"
                  carries a hyphen of its own, so the split is on the last
                  spaced dash, never on any dash.
  ranked_rows     ranked tables and lists - "-56kg RYSIEWICZ Pierre FRA 1 -
                  World Champion", "-56 Kg MAKOUZA Sydney FRA Champion". The
                  class is printed once and then left blank, so it is carried
                  down; and "Finalist" with no ordinal is not second place, it
                  is a final whose result the sheet never states.
  numbered_list   "1. MOUTAHAMMIS Hanna (FRA)", where savate's second bronze is
                  written as an unnumbered continuation line under the first.
  country_first   "France F -48 MAY Adeline Championne" - nation, sex, class,
                  name, title, in that order and all on one line.
  medal_grid      gold / silver / bronze / bronze across the columns, where one
                  bronze cell sometimes holds both bronzes in parentheses.
  placed_list     "LAZAR KOLDAN - Serbia/SAVATE KLUB IDOS   1", the place in a
                  right-hand column that a long club name pushes onto its own
                  line.
  finals_sheet    one title bout per pair of lines, each with its own date,
                  venue and decision. The only 2007-2011 document that records
                  how a bout ended.
  bat_memo        "X (France) bat Y (Croatie)" - the shortest result there is.
  worksheet       the poule cross-table with points and warnings, in the
                  variants the existing worksheet adapter cannot read: several
                  poules on one sheet, and the row label "Assaut:" rather than
                  "combat :".
  knockout        bracket trees where a name reprinted one column to the right
                  is the whole record of who won.
  champions_html  a news article listing this year's champions and nothing else.

Two of these documents are the only African results in the archive, and they are
the reason this module exists at all: the 2018 CASavate report from Dakar and
the 2025 African championship article. Both are held to the same rule as
everything else - a fact the document does not state is not supplied here.

Several sheets carry more than one competition (three championships in one 2008
PDF, an assaut list and a combat list in one 2025 article). A manifest entry
picks one with `section`, whose words must all appear in that competition's own
heading:

    {"slug": "african-championship-2025-assaut", "adapter": "fisav_sheets",
     "source": "https://fisav.sport/en/news/...", "section": "assaut"}
"""

import re

from savate import display
from savate import normalize as norm
from savate import pdf
from savate import rules
from savate.adapters.fisav_pool_pdf import weight_class
from savate.schema import (MEDALS, Bout, Placing, Report, Tournament,
                           TOURNAMENT_FIELDS)

NAME = "fisav_sheets"
DESCRIPTION = ("FISav's typed result sheets: podiums, ranked tables, finals "
               "memos, poule worksheets and knockout brackets")


# ---- the vocabulary every reader shares ---------------------------------

def _squash(text):
    return " ".join(str(text or "").split())


def _fold(text):
    return norm.fold(_squash(text))


# A finishing position, however the sheet words it. Ordered so that
# "vice-champion" is never read as "champion" and "3rd" is never read as "3
# points": the pattern that would swallow another is tried first.
_RANKS = [
    ("2", r"^vice[\s'-]*champion(?:ne|nat)?\b|^m[ée]daille\s+d[’'`]?\s*argent\b"
          r"|^argent\b|^silver\b|^2\s*(?:[-–—:.]|$)|^2\s*(?:nd|e|[èe]me|º|°)\b"
          r"|^second[e]?\b|^deuxi[èe]me\b"),
    # "Vainqueur" is deliberately absent. On a ranked table it would mean
    # first place; on the group sheets FISav publishes in the same folder it
    # means "winner of group A", and reading those as championship placings
    # turned a whole 2024 bracket into 266 medallists.
    ("1", r"^champion(?:ne)?\b|^m[ée]daille\s+d[’'`]?\s*or\b|^or\b|^gold\b"
          r"|^1\s*(?:[-–—:.]|$)|^1\s*(?:st|er|[èe]re|re|º|°)\b"
          r"|^premi[èe]re?\b"),
    ("3", r"^m[ée]daille\s+(?:de\s+)?bronze\b|^bronze\b"
          r"|^3\s*(?:[-–—:.]|$)|^3\s*(?:rd|e|[èe]me|º|°)\b|^troisi[èe]me\b"),
    ("4", r"^4\s*(?:[-–—:.]|$)|^4\s*(?:th|e|[èe]me|º|°)\b|^quatri[èe]me\b"),
    ("5", r"^5\s*(?:[-–—:.]|$)|^5\s*(?:th|e|[èe]me|º|°)\b|^cinqui[èe]me\b"),
    ("6", r"^6\s*(?:[-–—:.]|$)|^6\s*(?:th|e|[èe]me|º|°)\b|^sixi[èe]me\b"),
    ("7", r"^7\s*(?:[-–—:.]|$)|^7\s*(?:th|e|[èe]me|º|°)\b|^septi[èe]me\b"),
    ("8", r"^8\s*(?:[-–—:.]|$)|^8\s*(?:th|e|[èe]me|º|°)\b"),
]
_RANKS = [(rank, re.compile(pattern, re.I)) for rank, pattern in _RANKS]

# Sports that are not savate. The FISav library files canne de combat, chausson
# and savate forme under the same "results" heading as assaut and combat, and a
# document that mixes them in must not have them filed as savate bouts. None of
# the documents this adapter was written against carries any - the guard is
# here because the cost of missing one is a fabricated savate record, and the
# cost of the guard is a line.
_OTHER_SPORT = re.compile(
    r"canne\s*(?:de\s*combat)?\b|\bchausson\b|\bb[aâ]ton\b|"
    r"savate\s+forme|\bforme\b|double\s*canne|\bpr[ée]-?canne\b", re.I)


# A word the sheets use for a place they did not decide. "Finalist" on both
# lines of a final is not two silver medals - it is a bout whose winner the
# federation never published, and the only honest thing to do with it is to say
# so and store no placing.
_UNDECIDED = re.compile(r"^finalist[e]?\b|non\s+attribu|not\s+awarded", re.I)
# The same words, found anywhere in a cell rather than at its head: the sheets
# write "Finalist - forfait" and "... FRA Finalist" alike.
_UNDECIDED_IN = re.compile(r"\bfinalist[e]?\b|non\s+attribu|not\s+awarded", re.I)


def rank_at(text):
    """(rank, length of the phrase) if `text` opens with a finishing position."""
    text = _squash(text)
    for rank, pattern in _RANKS:
        found = pattern.match(text)
        if found:
            return rank, found.end()
    return "", 0


def rank_in(text):
    """The finishing position stated anywhere in `text`, or ""."""
    text = _squash(text)
    for start in range(len(text)):
        if start and not text[start - 1].isspace():
            continue
        rank, _ = rank_at(text[start:])
        if rank:
            return rank
    return ""


# A weight class as the sheets write it: "-56kg", "56 - 60", "48-52 kg", "85 +",
# "+75kg", "DE 60 Kg", "plus de 85", "M 75+ kg", "M65-70".
_CLASS = re.compile(
    r"""(?P<lead>[-+−]|plus\s+de|more\s+than|de|over|under)?\s*
        (?P<low>\d{2,3})(?:[.,]\d)?(?!\d)\s*(?:kgs?\b)?\s*
        (?:(?P<dash>[-–—])\s*(?P<high>\d{2,3})(?:[.,]\d)?(?!\d)\s*(?:kgs?\b)?)?\s*
        (?P<trail>\+)?""", re.I | re.X)

# What a savate weight class can plausibly be. A four-figure year and a page
# number both match "a number", and a class read out of "2010 European
# Championship" would file a whole event under -201 kg.
_LIGHTEST, _HEAVIEST = 20, 150


def weight_at(text):
    """((kg, bound), length consumed) for a class printed at the start of `text`.

    A band is the class ending at its upper figure, which is what the
    federations mean by "48-52 kg": everyone in it weighed over 48 and at most
    52, and the class is the 52.
    """
    text = _squash(text)
    found = _CLASS.match(text)
    if not found:
        return None, 0
    lead = _fold(found.group("lead") or "")
    over = bool(found.group("trail")) or lead in ("+", "plus de", "more than",
                                                  "over")
    kilos = found.group("high") or found.group("low")
    if not _LIGHTEST <= int(kilos) <= _HEAVIEST:
        return None, 0
    # "56 - 60" is a band; "-56" is an upper bound. The difference is whether a
    # figure follows the dash, which the pattern has already decided.
    return (kilos, "over" if over else "under"), found.end()


# Searched anywhere in a heading, not only at its head: the 2010 European
# sheet writes "SENIORS - FEMMES-WOMEN", where the sex is the second word.
# Women is tried first because "women" contains "men".
_GENDER_WORD = [
    ("Women", r"\b(?:femmes?|f[ée]minin(?:e?s?)?|women|female|girls?|dames?|"
              r"cadettes?|filles?)\b"),
    ("Men", r"\b(?:hommes?|masculins?|men|male|boys?|gar[çc]ons?|cadets?|"
            r"messieurs)\b"),
]
_AGE_WORD = [
    ("Junior", r"junior"),
    ("Cadet", r"\bcadet|\bcadette"),
    ("Young", r"youth|jeunes?\b|young|minime|benjamin|child|enfant|poussin"),
    ("Veteran", r"v[ée]t[ée]ran|master"),
    ("Senior", r"senior"),
]


def _word_match(text, table):
    text = _fold(text)
    for value, pattern in table:
        if re.search(pattern, text, re.I):
            return value
    return ""


def gender_of(text):
    """Women / Men / "" from a section heading or a one-letter column."""
    text = _squash(text)
    if re.fullmatch(r"[FfWw]", text):
        return "Women"
    if re.fullmatch(r"[HhMm]", text):
        return "Men"
    found = _word_match(text, _GENDER_WORD)
    if found:
        return found
    # "F48", "M -60", "JM75": the class code carries the sex in its first
    # letter, after any junior marker.
    letter = re.match(r"^(?:[JSCV])?([FM])\s*[-+]?\s*\d", text, re.I)
    return {"F": "Women", "M": "Men"}.get(letter.group(1).upper(), "") \
        if letter else ""


def age_of(text):
    return _word_match(text, _AGE_WORD)


def category_label(gender, age, kilos, bound):
    prefix = " ".join(x for x in (age, gender) if x)
    # No sign where the source printed none and the figure is not one of
    # savate's classes: "M100" says a hundred kilos and does not say which side
    # of it the class lies, and "-100 kg" would be this adapter saying it.
    if kilos and bound not in ("under", "over"):
        return _squash(f"{prefix} {kilos} kg")
    sign = "+" if bound == "over" else "-"
    return _squash(f"{prefix} {sign}{kilos} kg")


def klass(gender="", age="", kilos="", bound="under", label=""):
    """The five class fields a Bout and a Placing both carry.

    `label` keeps the sheet's own heading where it says more than the class
    does - "cadet2", "senior A cath.", "Combat S2" are all real distinctions a
    rebuilt "Cadet Men -65 kg" would quietly throw away.
    """
    return {"category": _squash(label) or category_label(gender, age, kilos, bound),
            "gender": gender, "age_class": age,
            "weight_kg": kilos, "weight_bound": bound}


# Nations, longest spelling first, for cutting one off the end of a cell.
def _nations():
    out = []
    for canonical in display.countries():
        for spelling in display.spellings(canonical):
            out.append((_fold(spelling), canonical))
    out.sort(key=lambda pair: -len(pair[0]))
    return out


_NATIONS = _nations()


def split_nation(text):
    """("Name", "Nation") where the cell ends in a nation this archive knows.

    The nation is matched as a whole trailing word run, longest first, so
    "Guinea Bissau" is one country and "CASASSA VIGNA Francesca ITALIE" keeps
    its two-word surname. A cell ending in nothing recognised keeps all of
    itself: a surname turned into a country is far worse than a missing one.
    """
    text = _squash(text)
    if not text:
        return "", ""
    words = text.split(" ")
    for take in range(min(4, len(words) - 1), 0, -1):
        tail = _fold(" ".join(words[-take:]))
        for folded, canonical in _NATIONS:
            if folded == tail:
                return " ".join(words[:-take]).strip(" ,;-"), canonical
    return text, ""


# The words a heading uses to name a sex or an age class, and the round format
# it prints beside them ("3x1 min", "3x1,5 min", "7X2").
_CLASS_WORDS = re.compile(
    r"(?i)\b(hommes?|femmes?|masculins?|f[ée]minin(?:es?)?|men|women|male|"
    r"female|boys?|girls?|gar[çc]ons?|filles?|dames?|messieurs|cadett?es?\d?|"
    r"cadets?\d?|juniors?|seniors?|jeunes?|youth|young|child|enfants?|"
    r"v[ée]t[ée]rans?|masters?|minimes?|benjamins?|poussins?)\b")
_ROUND_FORMAT = re.compile(r"(?i)\d+\s*[x\u00d7]\s*\d+(?:[.,]\d+)?\s*(?:min)?")

_PAREN = re.compile(r"\(([^()]{2,40})\)\s*$")
# A spaced dash, which is a separator. A dash inside a word is part of the word.
_SPACED_DASH = re.compile(r"\s+[-–—]+\s*|\s*[-–—]+\s+")


def split_name_country(text):
    """("Name", "Country") from "Name (Country)" or "Name - COUNTRY"."""
    text = _squash(text).strip(" ,;")
    if not text:
        return "", ""
    found = _PAREN.search(text)
    if found:
        return text[:found.start()].strip(" ,;-"), _squash(found.group(1))
    cuts = list(_SPACED_DASH.finditer(text))
    if cuts:
        last = cuts[-1]
        return text[:last.start()].strip(" ,;-"), text[last.end():].strip(" ,;-")
    return split_nation(text)


def country_of(text):
    """One spelling of a nation, resolved where the archive knows it."""
    text = _squash(text)
    if not text:
        return ""
    found = display.country(text)
    return found.name if found.known else text


# ---- the document, read once --------------------------------------------

class Sheet:
    """One source's words, its lines and its plain text."""

    def __init__(self, path, glue=0.0, tolerance=3.0):
        self.path = path
        self.words = pdf.words(path)
        self.lines = pdf.rows(self.words, tolerance=tolerance, glue=glue)
        self.texts = [pdf.text_of(line) for line in self.lines]
        self.plain = "\n".join(self.texts)




# ---- what a competition heading looks like -------------------------------

# A line that starts a new competition inside a document that holds several.
_TITLE = re.compile(
    r"championnat|championship|coupe\b|\bcup\b|world\s+cup|tournoi|open\b|"
    r"ceintures|r[ée]sultats\s+du|results\s+of", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _is_title(text):
    """Is this line the heading of a competition?

    A parenthesised line is not, however it reads. The 2011 world youth sheet
    prints "(including World Cup results)" under its title; taken as a heading
    it makes the file look like two competitions when it is one, and the
    document never separates them.
    """
    text = _squash(text)
    if not text or len(text) >= 120:
        return False
    if text.startswith("(") and text.endswith(")"):
        return False
    return bool(_TITLE.search(text))


def _wanted(title, section):
    """Does this competition heading answer to `section`?

    Every word of the selector must appear in the heading, so "senior" picks
    both "Senior Combat European Championship 2008" and "2008 European
    Championship Senior Combat" while leaving the junior championship alone,
    and no selector has to reproduce a title's word order.
    """
    if not section:
        return True
    haystack = _fold(title)
    return all(word in haystack for word in _fold(section).split())


class Rows:
    """Rows under construction, with the tournament slug and the running class."""

    def __init__(self, slug, report, section=""):
        self.slug = slug
        self.report = report
        self.section = section
        self.rows = []
        self.gender = ""
        self.age = ""
        # What a heading that governs a whole block states, as opposed to what
        # one class heading states about itself. A sheet that prints "SENIORS -
        # FEMMES" once and then a class per line means both for every line
        # under it; a sheet whose headings are "M 85+ kg senior" and then
        # "M80-85 kg Combat S2" means senior for the first and says nothing
        # about the second. Carrying the first heading's age into the second is
        # how the Budapest sheet's S2 rows became senior rows, so a class
        # heading falls back to the block, never to the class before it.
        self.section_gender = ""
        self.section_age = ""
        self.klass = None
        self.title = ""
        self.titles = []
        self.verbatim = False      # keep the sheet's own heading as `category`
        self.on = not section
        self.sport_ok = True       # False under a heading naming another sport
        # Every name this document has stated a class for, with the class it
        # stated, so a later page that contradicts it can be caught.
        self.stated = {}

    def heading(self, text):
        """Note a competition heading, and whether its rows are wanted."""
        self.title = _squash(text)
        if self.title not in self.titles:
            self.titles.append(self.title)
        self.on = _wanted(self.title, self.section)
        self.gender = self.section_gender = ""
        # A title that names an age class states it for everything under it -
        # "Junior Combat European Championship 2008" is junior all the way down.
        self.age = self.section_age = age_of(self.title)
        self.klass = None

    def place(self, rank, fighter, country="", club="", source="reported"):
        fighter = _squash(fighter)
        # Kept whether or not this row is wanted here, because it is what the
        # document states about this person, and a later page of the same
        # document contradicting it is worth catching either way.
        if fighter and self.klass:
            self.stated.setdefault(fighter, []).append((dict(self.klass),
                                                        _squash(country)))
        if not self.keeping:
            return None
        if not fighter:
            self.report.problem(f"{self.where()}: a rank {rank} with no name")
            return None
        if self.klass is None:
            self.report.problem(f"a rank {rank} for {fighter!r} is listed "
                                f"before any weight class")
            return None
        row = Placing(
            tournament=self.slug,
            placing_id=f"{self.slug}-{len(self.rows) + 1:04d}",
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=fighter, country=country_of(country), club=_squash(club),
            result_source=source,
            **self.klass,
        )
        self.rows.append(row)
        return row

    @property
    def keeping(self):
        """Should a row read here be stored at all?

        Two independent reasons not to: it belongs to a competition this entry
        did not ask for, or it belongs to a different sport.
        """
        return self.on and self.sport_ok

    def where(self):
        return self.klass["category"] if self.klass else "no class"

    def complain(self, message):
        """A problem worth reporting only if these rows were wanted.

        A file holding two competitions is read twice, once per `section`, and
        the run that is not reading a page has nothing useful to say about it.
        """
        if self.on:
            self.report.problem(message)

    def set_class(self, kilos, bound, label=""):
        self.klass = klass(self.gender, self.age, kilos, bound,
                           label if self.verbatim else "")


# ---- reader: bulleted podiums -------------------------------------------

# The bullet poppler leaves in front of a list item.
_BULLET = re.compile(r"^[\s•o*•·-]+")
_MEDAL_WORD = re.compile(r"m[ée]daille\s+d[’'`]?\s*(or|argent)\b|"
                         r"m[ée]daille\s+(?:de\s+)?bronze\b", re.I)
_TITLE_WORD = re.compile(r"champion(?:ne)?\s+du\s+monde|champion(?:ne)?\s+"
                         r"d[’'`]europe|^\s*3e\b", re.I)


def sniff_medal_words(sheet):
    return bool(_MEDAL_WORD.search(sheet.plain)) or \
        bool(re.search(r"(?im)^\s*[•o*•·]\s*(vice-?)?champion", sheet.plain))


def read_medal_words(sheet, out):
    """Podiums written as bullets, with the medal either side of the name.

    Two sheets, one shape: the 2018 CASavate report puts the medal at the right
    end of the line and the name at the left, the 2010 world assaut sheet puts
    the title first and the name after a colon. Both are one medallist per line,
    so the only question is which end of the line the medal sits at.
    """
    for text in sheet.texts:
        text = _squash(text)
        if not text:
            continue
        stripped = _BULLET.sub("", text)
        medal = _MEDAL_WORD.search(text)
        if not medal:
            # "Championne du monde : C. Martin (France)"
            rank, used = rank_at(stripped)
            if rank and ":" in stripped[:used + 12]:
                after = stripped.split(":", 1)[1] if ":" in stripped else ""
                name, country = split_name_country(after)
                out.place(rank, name, country)
                continue
            found = _class_heading(text, out)
            if found:
                continue
            continue
        # "o David Sagna - GUINEE BISSAU        MEDAILLE D'OR"
        rank = rank_in(medal.group(0))
        before = _BULLET.sub("", text[:medal.start()])
        name, country = split_name_country(before)
        out.place(rank, name, country)


def _class_heading(text, out):
    """Update the running gender / age / weight class from a heading line.

    A heading has to be almost nothing but the class. "16 ATHLETES DE 5 PAYS
    AFRICAINS" contains a number followed by nothing that makes it a category,
    and reading it as one would file a whole championship under "-16 kg", so
    whatever the weight does not account for has to be class furniture - a
    round format, a unit, a bullet - and not prose.
    """
    text = _squash(text)
    if not text or len(text) > 90:
        return False
    if _OTHER_SPORT.search(text):
        out.sport_ok = False
        out.complain(f"{text[:60]!r} names a sport that is not savate - the "
                     f"rows under it are dropped")
        return True
    naked = re.sub(r"\([^()]*\)", " ", text)
    naked = re.sub(r"^\s*cat[ée]gorie\s*[-\u2013\u2014:]?\s*", "", naked, flags=re.I)
    naked = _squash(_BULLET.sub("", naked))
    gender = gender_of(naked)
    age = age_of(naked)
    body = _squash(_CLASS_WORDS.sub(" ", naked)) if (gender or age) else naked
    found, used = weight_at(body)
    if found is None:
        trimmed = re.sub(r"^[A-Za-z]{1,2}\s*", "", body)
        found, used = weight_at(trimmed)
        body = trimmed
    if found is None:
        # A heading with no class in it is a block heading: it governs
        # everything printed under it until the next one.
        if gender:
            out.gender = out.section_gender = gender
        if age:
            out.age = out.section_age = age
        return bool(gender or age)
    # A class heading states the class it names and nothing about the next one.
    out.gender = gender or out.section_gender
    out.age = age or out.section_age
    out.sport_ok = True
    # What is left once the class is accounted for.
    rest = _squash(_ROUND_FORMAT.sub(" ", body[used:]))
    rest = _squash(re.sub(
        r"(?i)\b(kgs?|cat[ée]gorie|cat[ée]|poids|weight)\b|[-\u2013\u2014.,:;]",
        " ", rest))
    # A short qualifier is part of the class - "senior B cath.", "Combat S2".
    # A sentence is not.
    if len(rest) > 16 or len(rest.split()) > 3:
        return bool(gender or age)
    out.set_class(*found, label=text)
    return True


# ---- reader: ranked tables and ranked lists ------------------------------

# A tail that names a place in a draw rather than a place in the championship:
# "2nd Groups B", "N°1 Poule A", "vainqueur 1/4 final".
_DRAW_LABEL = re.compile(r"\bgroups?\b|\bpoule\b|\bvainqueur\b|\bwinner\b|"
                         r"\b1\s*/\s*[248]\b|\bfinale?s?\b|\bn\s*[°ºo]\b", re.I)
# A line that opens with a draw slot - "A1", "B3". A sheet full of them is a
# group sheet, whatever else it looks like.
_SLOT_LINE = re.compile(r"^[A-Z]\d\b")

# A nation printed as a federation code: FRA, SER, GB, THAI. Three letters is
# the usual, but the sheets also print two and four.
_CODE = re.compile(r"^[A-Z]{2,5}$")


def _looks_like_country(token):
    token = _squash(token).strip(".,")
    if not token:
        return False
    if display.country(token).known:
        return True
    return bool(_CODE.match(token))


def _rank_start(tokens, window=6):
    """Index of the token where the finishing position begins, or None.

    Only the tail of the line is searched. A competitor called "Or" or a
    surname that reads as an ordinal in the middle of a name is not a rank, and
    limiting the search to the last few tokens is what keeps it from becoming
    one.
    """
    first = max(1, len(tokens) - window)
    for i in range(first, len(tokens)):
        tail = " ".join(tokens[i:])
        rank, _ = rank_at(tail)
        if rank and not _DRAW_LABEL.search(tail):
            return i, rank
    return None, ""


def sniff_ranked_rows(sheet):
    if sum(1 for t in sheet.texts if _SLOT_LINE.match(_squash(t))) >= 3:
        return False        # a draw sheet, however much its tails read as ranks
    hits = 0
    for text in sheet.texts:
        tokens = _squash(text).split()
        if len(tokens) < 3:
            continue
        index, _ = _rank_start(tokens)
        if index and _looks_like_country(tokens[index - 1]):
            hits += 1
    return hits >= 8


def _strip_class(text):
    """(rest of the line, class) once a weight printed at its head is taken off."""
    body = _squash(text)
    if not re.match(r"^[-+\u2212\d]", body):
        return body, None
    found, used = weight_at(body)
    if found is None:
        return body, None
    rest = body[used:].strip()
    rest = re.sub(r"^kgs?\b[\s.]*", "", rest, flags=re.I).strip()
    return rest, found


def read_ranked_rows(sheet, out):
    """Ranked lists and ranking tables: name, nation, finishing position.

    The class is carried down, because the 2008 world sheet prints it once at
    the head of a block and leaves the cell empty for everyone under it. The
    2008 European sheet repeats it on every row instead; carrying down handles
    both, since a repeat simply sets the same class again.

    One row in the 2008 European sheet is split in two by the PDF itself - the
    class and the words "Vice Champion" sit 5 points above the name they belong
    to. A rank with no name is therefore held over for the next line rather
    than dropped, which is the only place in this module where two printed
    lines become one row, and it happens only when one line has a rank and no
    name and the next has a name and no rank.
    """
    pending = ""
    for text in sheet.texts:
        text = _squash(text)
        if not text:
            continue
        if _is_title(text):
            out.heading(text)
            pending = ""
            continue
        body, found = _strip_class(text)
        if found is not None:
            out.set_class(*found, label=text)
        if not body:
            continue

        whole, used = rank_at(body)
        if whole and used >= len(body):
            # The line says a place and nothing else: its name is elsewhere.
            pending = whole
            continue

        tokens = body.split()
        if _UNDECIDED_IN.search(" ".join(tokens[-3:])):
            if out.on:
                out.report.problem(
                    f"{out.where()}: {' '.join(tokens[:2])} is listed as "
                    f"{' '.join(tokens[-3:])!r}, a place the sheet never "
                    f"decides - no placing stored")
            pending = ""
            continue

        index, rank = _rank_start(tokens)
        name_tokens = tokens[:index] if index else tokens[:]
        country = ""
        if len(name_tokens) > 1 and _looks_like_country(name_tokens[-1]):
            country = name_tokens[-1]
            name_tokens = name_tokens[:-1]

        if index is not None and name_tokens:
            out.place(rank, " ".join(name_tokens), country)
            pending = ""
        elif pending and country and name_tokens:
            out.place(pending, " ".join(name_tokens), country)
            pending = ""
        elif index is None:
            _class_heading(text, out)
            pending = ""


# A line whose ranking cell says only "Finalist", with no ordinal beside it.
def _undecided_line(text):
    tokens = _squash(text).split()
    return bool(tokens) and bool(_UNDECIDED.search(" ".join(tokens[-3:])))

# ---- reader: numbered placings ------------------------------------------

# The place carries its own punctuation - "1." or "1)". A bare leading number
# is a seat in a draw or a count in a nation table as often as it is a place,
# and reading those as placings files a country as a competitor.
_NUMBERED = re.compile(r"^(\d{1,2})\s*[.)]\s*(\S.*)$")


def sniff_numbered_list(sheet):
    if sum(1 for t in sheet.texts if _SLOT_LINE.match(_squash(t))) >= 3:
        return False
    return sum(1 for t in sheet.texts if _NUMBERED.match(_squash(t))) >= 6


def read_numbered_list(sheet, out):
    """"1. MOUTAHAMMIS Hanna (FRA)", with the second bronze left unnumbered.

    Savate awards two bronzes, and the 2010 European sheet writes the second
    one as a bare name on the line under the first rather than repeating the
    "3.". Carrying the rank down is a reading of the layout and not a reading
    of the document, so the carried row is marked `inferred` and said out loud
    in the Report - a reader who disagrees can see exactly which rows it is.
    """
    last_rank = ""
    for line in sheet.lines:
        text = _squash(pdf.text_of(line))
        if not text:
            continue
        numbered = _NUMBERED.match(text)
        if not numbered:
            if _class_heading(text, out):
                last_rank = ""
                continue
            # A bare "NAME (CRO)" under a numbered line is the same place again.
            name, country = split_name_country(text)
            if (last_rank and country and name and len(text) < 60
                    and not _is_title(text)):
                out.report.problem(
                    f"{out.where()}: {name} is printed under the rank "
                    f"{last_rank} line with no rank of its own - stored as "
                    f"rank {last_rank}, marked inferred")
                out.place(last_rank, name, country, source="inferred")
                continue
            last_rank = ""
            continue
        rank, rest = numbered.group(1), numbered.group(2)
        name, country = split_name_country(rest)
        out.place(rank, name, country)
        last_rank = rank


# ---- reader: nation, sex, class, name, title -----------------------------

_COUNTRY_FIRST = re.compile(
    r"^(?P<country>[A-Za-zÀ-ÿ'’. -]{3,24}?)\s+(?P<sex>[HFMW])\s+"
    r"(?P<sign>[-+−])\s*(?P<kg>\d{2,3})\s+(?P<rest>.+)$")


def sniff_country_first(sheet):
    return sum(1 for t in sheet.texts if _COUNTRY_FIRST.match(_squash(t))) >= 6


def read_country_first(sheet, out):
    """"France F -48 MAY Adeline Championne" - everything on one line."""
    for text in sheet.texts:
        text = _squash(text)
        if not text:
            continue
        if _is_title(text):
            out.heading(text)
            continue
        found = _COUNTRY_FIRST.match(text)
        if not found:
            continue
        rest = found.group("rest").split()
        index, rank = _rank_start(rest, window=4)
        if index is None:
            out.report.problem(f"{text!r} names no finishing position")
            continue
        out.gender = gender_of(found.group("sex"))
        out.set_class(found.group("kg"),
                      "over" if found.group("sign") == "+" else "under")
        out.place(rank, " ".join(rest[:index]), found.group("country"))


# ---- reader: the four-medal grid ----------------------------------------

_MEDAL_COLUMN = re.compile(r"\b(or|gold|argent|silver|bronze)\b", re.I)
# The header of a table that is not a podium. The 2016 European youth sheet
# prints its full entry list under the medal grid, in two columns of
# "N* CATE NOM PRENOM PAYS" - read as medal rows it turns every entrant into a
# champion of a class he merely entered.
_OTHER_TABLE = re.compile(
    r"liste\s+des\s+participants|\bnom\s+prenom\b|"
    r"n\s*[°ºo*]\s+cat[ée]|\bengag[ée]s?\b.*\bpays\b|"
    r"^rappel\s*:|^s[ée]ries\s*:|^tireur\s+\d", re.I)
# Savate's podium is at most four deep: a gold, a silver and two bronzes.
_DEEPEST_PODIUM = 4
# "F48", "M+85", "JM75": the code that is a whole weight class in itself.
# The age marker sits either side of the sex letter: FISav writes "JM75" and
# "FJ52" for the same idea, and both appear inside one 2018 file.
_CODE_CLASS = re.compile(r"^(?P<age>[JSCV]?)(?P<sex>[FM])(?P<age2>[JSCV]?)\s*"
                         r"(?P<over>\+?)\s*(?P<kg>\d{2,3})$")
_CODE_AGE = {"J": "Junior", "C": "Cadet", "V": "Veteran", "S": "Senior", "": ""}
# The weight classes savate actually fights, as these federations print them:
# the senior ladder and the lighter youth rungs below it. A coded class off
# this ladder is not read as an upper bound, because it is not a class.
_LADDER = frozenset((18, 21, 24, 27, 28, 30, 32, 35, 36, 40, 42, 45, 48, 52,
                     56, 60, 65, 70, 75, 80, 85))


def code_class(token):
    """(gender, age, kg, bound) for a class written as a code, or None.

    A bare code carries no sign, so the bound is read from savate's own ladder:
    "M75" is the class that ends at 75 because 75 is a class. "M100" is not -
    savate has no hundred-kilo class, the same federation writes its open class
    "+85" two lines further up, and nothing in the document says whether the
    figure is a ceiling or a floor. The figure is kept, the bound is left empty
    and the caller says so.
    """
    found = _CODE_CLASS.match(_squash(token))
    if not found:
        return None
    kilos = found.group("kg")
    if not _LIGHTEST <= int(kilos) <= _HEAVIEST:
        return None
    if found.group("over"):
        bound = "over"
    elif int(kilos) in _LADDER:
        bound = "under"
    else:
        bound = ""
    return ({"F": "Women", "M": "Men"}[found.group("sex").upper()],
            _CODE_AGE[(found.group("age") or found.group("age2")).upper()],
            kilos, bound)


def coded_class(token, out):
    """`code_class`, with the Report told about a class savate does not have."""
    found = code_class(token)
    if found and not found[3]:
        out.complain(f"{_squash(token)!r}: savate has no {found[2]} kg class, "
                     f"so the figure is stored as printed and no weight bound "
                     f"is recorded")
    return found


def _medallists(tokens):
    """[(name, nation)] from a row of medal cells, split on the nations.

    The cells are not separated by anything the text layer keeps - in one grid
    the gap inside a cell, between a name and its nation, is wider than the gap
    between two cells. What does separate them is that every cell ends in a
    nation, so the row is walked left to right and cut wherever a nation this
    archive recognises completes. A cell that never reaches one is handed back
    unread rather than guessed at.
    """
    cells, buffer = [], []
    for token in tokens:
        buffer.append(token)
        for take in range(min(4, len(buffer)), 0, -1):
            tail = " ".join(buffer[-take:]).strip("()")
            found = display.country(tail)
            if found.known and len(buffer) > take:
                cells.append((" ".join(buffer[:-take]).strip(" ,;-"), found.name))
                buffer = []
                break
    return cells, buffer


def sniff_medal_grid(sheet):
    for text in sheet.texts:
        text = _squash(text)
        if len(text) < 90 and len(_MEDAL_COLUMN.findall(text)) >= 2:
            return True
    return False


def read_medal_grid(sheet, out):
    """Gold / silver / bronze / bronze across the columns, one class per row.

    Savate's two bronzes are two columns, and where a sheet runs out of room it
    writes both into one cell as "NAME (Nation) NAME (Nation)". Either way both
    are rank 3, and neither is a duplicate of the other.
    """
    medals = 0
    for text in sheet.texts:
        text = _squash(text)
        if not text:
            continue
        if _OTHER_TABLE.search(text):
            out.report.problem(
                f"stopped at {text[:48]!r}: what follows is an entry list, "
                f"not a podium")
            break
        columns = len(_MEDAL_COLUMN.findall(text))
        if columns >= 2 and len(text) < 90:
            medals = columns
            continue
        if _is_title(text):
            out.heading(text)
            continue
        tokens = text.split()
        if not tokens:
            continue
        # An entrant count sometimes opens the row; the class always follows it.
        if re.fullmatch(r"\d{1,2}", tokens[0]) and len(tokens) > 1:
            tokens = tokens[1:]
        code = coded_class(tokens[0], out)
        if code:
            gender, age, kilos, bound = code
            out.gender, out.age = gender, age or out.section_age
            out.set_class(kilos, bound)
            rest = tokens[1:]
        else:
            found, used = weight_at(tokens[0])
            if found is None or not _looks_like_class(tokens[0]):
                if not _class_heading(text, out):
                    continue
                continue
            out.set_class(*found)
            rest = tokens[1:]
        if not medals:
            out.report.problem(f"{text[:40]!r}: a medal row before any "
                               f"gold/silver/bronze heading")
            continue
        if _UNDECIDED_IN.search(" ".join(rest)):
            if out.on:
                out.report.problem(f"{out.where()}: the sheet says the title "
                                   f"was not awarded - no placings stored")
            continue
        cells, leftover = _medallists(rest)
        if leftover and out.on:
            out.report.problem(
                f"{out.where()}: {' '.join(leftover)!r} names no nation this "
                f"archive knows, so the medallists after it could not be "
                f"separated - not stored")
        # A three-column header still carries four medallists where both
        # bronzes share the last cell, so the limit is the podium's depth and
        # not the number of headings printed above it.
        limit = max(medals, _DEEPEST_PODIUM) if medals >= 3 else medals
        if len(cells) > limit:
            out.report.problem(
                f"{out.where()}: {len(cells)} medallists in one row, more than "
                f"a savate podium holds - not stored")
            continue
        for column, (name, nation) in enumerate(cells, start=1):
            # Column three and column four are both bronze. Savate awards two.
            out.place("3" if column >= 3 else str(column), name, nation)


def _looks_like_class(token):
    """Is this whole token a weight class, rather than a number inside prose?"""
    found, used = weight_at(token)
    return found is not None and used >= len(_squash(token)) - 3


# ---- reader: entrants with the place in a right-hand column --------------

class _Probe:
    """A stand-in for Rows, for asking whether a line is a class heading.

    `_class_heading` updates every running state a real Rows carries, so the
    probe must carry the same state or a heading that touches it raises.
    Complaints are dropped: the probe only asks a yes/no question.
    """

    def __init__(self):
        self.gender = self.age = ""
        self.section_gender = self.section_age = ""
        self.sport_ok = True
        self.klass = None
        self.verbatim = False

    def set_class(self, kilos, bound, label=""):
        self.klass = (kilos, bound)

    def complain(self, message):
        pass


def _is_class_heading(text):
    probe = _Probe()
    _class_heading(text, probe)
    return probe.klass is not None


_PLACE_ONLY = re.compile(r"^\d{1,2}$")
# The separator between a competitor and where they come from. It is always
# spaced, so a hyphen inside "Szabo-Toth" or "MAKS-FENIKS" is not one.
_ENTRANT_CUT = re.compile(r"\s+[-–—/]{1,2}\s*|\s*[-–—/]{1,2}\s+")


def _place_column(lines):
    """x of the column the finishing places sit in, or None."""
    counts = {}
    for line in lines:
        last = line[-1]
        if _PLACE_ONLY.match(last.text) and (len(line) == 1 or
                                             last.x0 - line[-2].x1 > 6):
            counts[round(last.x0 / 4) * 4] = counts.get(round(last.x0 / 4) * 4, 0) + 1
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return best if counts[best] >= 5 else None


# A sheet that words its places - "Champion", "3rd", "Bronze medallist" - is a
# ranked table whose numbers happen to sit on the right, not a list of bare
# places. The two layouts are otherwise hard to tell apart.
_PLACE_IN_WORDS = re.compile(
    r"(?i)\bchampion|\bbronze\b|m[ée]daill|\btroisi|\bvice\b|"
    r"\b\d(?:st|nd|rd|th)\b")


def sniff_placed_list(sheet):
    if sum(1 for t in sheet.texts if _PLACE_IN_WORDS.search(t)) >= 3:
        return False
    return _place_column(sheet.lines) is not None and \
        sum(1 for t in sheet.texts if _ENTRANT_CUT.search(_squash(t))) >= 10


def read_placed_list(sheet, out):
    """"Ivan Juranko - Croatia/Savate klub X   3", places in the right column.

    A long club name wraps, which pushes the place onto a line of its own and
    the rest of the club onto the line after that. So a competitor is held open
    until the next competitor or the next class heading: a line that is only a
    number gives the open competitor its place, and a line with neither a place
    nor a separator is the tail of the club above it.
    """
    out.verbatim = True
    column = _place_column(sheet.lines)
    if column is None:
        out.report.problem("no column of finishing places found")
        return
    open_row = None

    def close(row):
        if row is None:
            return
        if not row["rank"]:
            out.report.problem(
                f"{out.where()}: {row['text'][:48]!r} has no place beside it - "
                f"not stored")
            return
        name, place = _split_entrant(row["text"])
        country, club = place
        out.place(row["rank"], name, country, club)

    for line in sheet.lines:
        places = [w for w in line if w.x0 >= column - 6 and _PLACE_ONLY.match(w.text)]
        body = _squash(" ".join(w.text for w in line if w not in places))
        if not body:
            if open_row is not None and places:
                open_row["rank"] = open_row["rank"] or places[0].text
            continue
        if not places and _is_class_heading(body):
            # Close the competitor still open BEFORE the class changes, or the
            # last of each class is filed under the next one.
            close(open_row)
            open_row = None
            _class_heading(body, out)
            continue
        if _ENTRANT_CUT.search(body) or display.country(body.split()[-1]).known:
            close(open_row)
            open_row = {"text": body, "rank": places[0].text if places else ""}
            continue
        if open_row is not None:
            open_row["text"] = f"{open_row['text']} {body}"
            if places and not open_row["rank"]:
                open_row["rank"] = places[0].text
    close(open_row)
    _report_repeated_places(out)


def _report_repeated_places(out):
    """Say where a class hands out the same place twice.

    The 2020 Budapest sheet prints two firsts and two seconds in one senior
    class, which is what happens when a category is run as two separate pools
    and the sheet does not say so. Both are stored, because both are printed;
    what is not done is to quietly promote or demote one of them.
    """
    seen = {}
    for row in out.rows:
        seen.setdefault((row.category, row.rank), []).append(row.fighter)
    for (category, rank), people in seen.items():
        if rank in ("1", "2") and len(people) > 1:
            out.report.problem(
                f"{category}: {len(people)} competitors share place {rank} "
                f"({', '.join(people)}) - stored as the sheet prints them")


def _split_entrant(text):
    """("Name", ("Country", "Club")) from "Name - Country/Club"."""
    text = _squash(text)
    cut = _ENTRANT_CUT.search(text)
    if not cut:
        return text, ("", "")
    name = text[:cut.start()].strip(" ,;-")
    where = text[cut.end():].strip(" ,;-")
    if "/" in where:
        country, club = where.split("/", 1)
        return name, (_squash(country), _squash(club))
    # No slash: the cell is either a nation or a club, and the archive's own
    # list of nations is what decides which. A club read as a country would
    # invent a member federation.
    return (name, (where, "")) if display.country(where).known else (name, ("", where))


# ---- dates, in the languages the sheets are written in -------------------

_MONTHS = {
    "janv": 1, "jan": 1, "fevr": 2, "fev": 2, "feb": 2, "mars": 3, "mar": 3,
    "avr": 4, "apr": 4, "mai": 5, "may": 5, "juin": 6, "jun": 6, "juil": 7,
    "jul": 7, "aout": 8, "aug": 8, "sept": 9, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12, "decembre": 12,
}
_SHORT_DATE = re.compile(
    r"\b(\d{1,2})\s*[-/ ]\s*([A-Za-zÀ-ÿ]{3,9})\.?\s*[-/ ]\s*(\d{2,4})\b")
_LONG_DATE = re.compile(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]{3,10})\.?\s+((?:19|20)\d{2})\b")


def french_date(text):
    """"23-oct-09" or "05 juin 2009" -> ISO, or "" if it is neither."""
    text = _squash(text)
    for pattern in (_SHORT_DATE, _LONG_DATE):
        found = pattern.search(text)
        if not found:
            continue
        day, word, year = found.groups()
        month = _MONTHS.get(_fold(word)[:4]) or _MONTHS.get(_fold(word)[:3])
        if not month:
            continue
        year = int(year)
        if year < 100:
            year += 2000 if year < 70 else 1900
        return f"{year:04d}-{month:02d}-{int(day):02d}"
    return ""


# The decisions these sheets print that the shared vocabulary does not yet
# carry. "Majorité" is a judges' decision and belongs with points; "hors
# combat" is a stoppage the canonical list has no word for, so it is left
# unclassified and kept verbatim in decision_detail rather than filed as an
# abandon, which would say the loser retired when in fact he was stopped.
_DECISION_EXTRA = [(re.compile(r"majorit[ée]|majority", re.I), "points")]
_UNCLASSIFIED = re.compile(r"hors\s+combat|\bk\.?o\.?\b", re.I)


def decision_of(text, report=None, where=""):
    """(canonical decision, the sheet's own wording)."""
    printed = _squash(text)
    found = norm.decision(printed)
    if not found:
        for pattern, name in _DECISION_EXTRA:
            if pattern.search(printed):
                found = name
                break
    if not found and _UNCLASSIFIED.search(printed) and report is not None:
        report.problem(
            f"{where}: the sheet says {printed!r}, which the canonical "
            f"decision vocabulary has no word for - kept verbatim, decision "
            f"left empty")
    return found, printed


# ---- reader: the finals sheet -------------------------------------------

_DATELINE = re.compile(r"date\s*:", re.I)
_VENUE = re.compile(r"lieu\s*:|venue\s*:", re.I)


def sniff_finals_sheet(sheet):
    return bool(re.search(r"(?i)\bfinales?\b", sheet.plain)) and \
        sum(1 for t in sheet.texts if _DATELINE.search(t)) >= 2


def read_finals_sheet(sheet, out):
    """One title bout per pair of lines, each block under its own date and venue.

    The winner is stated in words and so is how he won, which makes this the
    only FISav document between 2007 and 2011 that records a bout rather than a
    podium. Nobody's corner is stated, so no corner is claimed: the winner is
    named and `winner_corner` stays empty, which the schema supports and which
    is the truth about the document.
    """
    anchors = _finals_columns(sheet)
    if not anchors:
        out.report.problem("no 'Poids / NOM / Pays' header - not a finals sheet")
        return
    poids_x, nom_x, pays_x = anchors
    date = city = ""
    pending = None

    for line in sheet.lines:
        text = _squash(pdf.text_of(line))
        if not text:
            continue
        if _DATELINE.search(text):
            date = french_date(text)
            found = _VENUE.search(text)
            city = ""
            if found:
                after = text[found.end():].split("Organisateur")[0]
                city = _squash(after).title()
            pending = None
            continue
        rank, used = rank_at(text)
        if not rank or rank not in ("1", "2"):
            continue
        role_words = [w for w in line if w.x0 < nom_x - 4]
        middle = [w for w in role_words if not rank_at(w.text)[0]
                  and w.text not in ("/",)]
        gender = next((gender_of(w.text) for w in middle
                       if len(w.text) == 1), "")
        weight_text = " ".join(w.text for w in middle if len(w.text) > 1)
        name = " ".join(w.text for w in line if nom_x - 4 <= w.x0 < pays_x - 4)
        tail = [w for w in line if w.x0 >= pays_x - 4]
        country = tail[0].text if tail else ""
        detail = " ".join(w.text for w in tail[1:])
        entry = {"rank": rank, "gender": gender, "weight": weight_text,
                 "name": _squash(name), "country": country, "detail": detail,
                 "date": date, "city": city}
        if rank == "1":
            pending = entry
            continue
        if pending is None:
            out.report.problem(f"{text[:48]!r}: a runner-up with no champion "
                               f"above it - no bout stored")
            continue
        _final_bout(out, pending, entry)
        pending = None


def _finals_columns(sheet):
    """(x of Poids, x of NOM, x of Pays) from the sheet's own header row."""
    for line in sheet.lines:
        words = {_fold(w.text): w.x0 for w in line}
        if "poids" in words and "nom" in words and "pays" in words:
            return words["poids"], words["nom"], words["pays"]
    return None


def _final_bout(out, champion, runner_up):
    """One title bout, plus the two placings the sheet states in words."""
    # "plus de" opens the class on the champion's line and the figure lands on
    # the runner-up's, because the two share one merged cell.
    text = _squash(f"{champion['weight']} {runner_up['weight']}")
    found, _ = weight_at(champion["weight"])
    if found is None:
        found, _ = weight_at(text)
    out.gender = champion["gender"] or out.gender
    if found is None:
        out.report.problem(f"{champion['name']}: no weight class printed")
        out.klass = klass(out.gender, out.age)
    else:
        out.set_class(*found)
    decision, printed = decision_of(champion["detail"], out.report,
                                    out.where())
    if not out.keeping:
        return
    index = len([r for r in out.rows if isinstance(r, Bout)]) + 1
    out.rows.append(Bout(
        tournament=out.slug,
        bout_id=f"{out.slug}-final-{index:02d}",
        date=champion["date"],
        phase="final",
        red=champion["name"], red_country=country_of(champion["country"]),
        blue=runner_up["name"], blue_country=country_of(runner_up["country"]),
        # Printed first is not a corner. The sheet never says who stood in red.
        winner=champion["name"], loser=runner_up["name"], winner_corner="",
        decision=decision, decision_detail=printed,
        status="decided", result_source="reported",
        **out.klass,
    ))
    for rank, who in (("1", champion), ("2", runner_up)):
        out.place(rank, who["name"], who["country"])


# ---- reader: the one-line bout memo -------------------------------------

_BEATS = re.compile(r"\s+(bat|beat|batte|d[ée]f[ai]it)\s+", re.I)


def sniff_bat_memo(sheet):
    return sum(1 for t in sheet.texts if _BEATS.search(_squash(t))) >= 1


def read_bat_memo(sheet, out):
    """"Saabar ABDELAZIZ (France) bat Predrag SIMUNEC (Croatie)".

    The shortest result in the archive, and complete: two fighters, their
    nations, and which of them won. What it does not carry is a corner, so
    none is set.
    """
    date = city = ""
    for text in sheet.texts:
        text = _squash(text)
        if not text:
            continue
        found = french_date(text)
        if found and not _BEATS.search(text):
            date = found
            place = re.search(r"\b[àa]\s+(.+)$", text)
            if place:
                city = _squash(re.sub(r"\([^()]*\)", " ", place.group(1))).title()
            continue
        cut = _BEATS.search(text)
        if not cut:
            _class_heading(text, out)
            continue
        winner, winner_country = split_name_country(text[:cut.start()])
        loser, loser_country = split_name_country(text[cut.end():])
        if not (winner and loser):
            out.report.problem(f"{text[:60]!r}: a bout line missing a fighter")
            continue
        if not out.keeping:
            continue
        out.rows.append(Bout(
            tournament=out.slug,
            bout_id=f"{out.slug}-{len(out.rows) + 1:03d}",
            date=date,
            red=winner, red_country=country_of(winner_country),
            blue=loser, blue_country=country_of(loser_country),
            winner=winner, loser=loser, winner_corner="",
            status="decided", result_source="reported",
            **(out.klass or klass(out.gender, out.age)),
        ))


# ---- reader: the champions-only news article ----------------------------

_TAGS = re.compile(r"<[^>]+>")
_DROP = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BREAK = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</td>|</tr>")
_CHAMPIONS_HEADING = re.compile(
    r"champions?\s+in\s+(\w+)|champions?\s+(?:en|de)\s+(\w+)", re.I)
_CODED_LINE = re.compile(r"^(?P<code>[JSCV]?[FM]\s*\+?\s*\d{2,3})\s+(?P<rest>.+)$")


def html_lines(page):
    body = _BREAK.sub("\n", _DROP.sub(" ", page))
    import html as _html
    text = _html.unescape(_TAGS.sub(" ", body))
    return [l for l in (_squash(x) for x in text.splitlines()) if l]


def sniff_champions_html(lines):
    return any(_CHAMPIONS_HEADING.search(l) for l in lines) and \
        sum(1 for l in lines if _CODED_LINE.match(l)) >= 5


def read_champions_html(lines, out):
    """"F48 MENDONG Nadege Cameroon" under "African Champions in Assaut:".

    First place and nothing else - no silver, no bronze, no bouts. It is the
    only record of this competition that exists, so it is worth keeping, and
    the Report says plainly what it does not hold.

    The article lists assaut champions and combat champions one after the
    other, and two fighters are champion in both. Merged into one competition
    they would each hold one class twice, which is why `section` is required
    here: the article is two competitions, not one.
    """
    seen = set()
    for line in lines:
        heading = _CHAMPIONS_HEADING.search(line)
        if heading and len(line) < 80:
            out.heading(line.rstrip(":"))
            continue
        found = _CODED_LINE.match(line)
        if not found:
            continue
        code = coded_class(found.group("code").replace(" ", ""), out)
        if not code:
            continue
        name, nation = split_nation(found.group("rest"))
        if not nation:
            out.report.problem(
                f"{line!r}: no nation this archive recognises at the end of "
                f"the line, so the name could not be told from the country - "
                f"not stored")
            continue
        gender, age, kilos, bound = code
        out.gender, out.age = gender, age
        out.set_class(kilos, bound)
        key = (out.title, out.klass["category"], _fold(name))
        if key in seen:
            continue
        seen.add(key)
        out.place("1", name, nation)


# ---- reader: the poule worksheet ----------------------------------------

_SERIES = re.compile(r"^s[ée]ries\s*:", re.I)
_POULE_NAME = re.compile(r"poule\s+([A-Z])\b", re.I)
# A line that is a poule's own heading, and not the bracket label "N°1 Poule A"
# printed halfway across a competitor's row. Reading the second as the first
# files five fighters under the wrong group.
_POULE_HEADING = re.compile(r"^poule\s+([A-Z])\b(?:\s+pays)?\s*$", re.I)
_BOUT_LABEL = re.compile(r"^(assauts?|combats?)\s*:?$", re.I)
_TIREUR = re.compile(r"^tireurs?$", re.I)
_SEAT = re.compile(r"^tireur\s*(\d{1,2})$", re.I)
# The barème, which the sheets print in their own corner and which is not the
# same every year: 2019 pays a draw 3 points, 2021 pays it 2.
# DOTALL because the legend is a bullet list that the text layer breaks between
# the word and its figure: "\u2022Egalite:" ends one line and "2 points" opens the
# next, and a scale read as missing turns every level scoreline unresolved.
_SCALE = {
    "win": re.compile(r"(?:victoire|victory)\s*[:/].{0,24}?(-?\s?\d+)\s*point",
                      re.I | re.S),
    "draw": re.compile(r"(?:[ée]galit[ée]|draw)\s*[:/].{0,24}?(-?\s?\d+)\s*point",
                       re.I | re.S),
    "loss": re.compile(r"(?:d[ée]faite|defeat)\s*[:/].{0,24}?(-?\s?\d+)\s*point",
                       re.I | re.S),
}


def _numeric(text):
    try:
        return int(float(str(text).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def sniff_worksheet(sheet):
    labelled = sum(1 for line in sheet.lines
                   if line and _BOUT_LABEL.match(line[0].text))
    headers = sum(1 for line in sheet.lines
                  if sum(1 for w in line if _TIREUR.match(w.text)) >= 2)
    return labelled >= 2 and headers >= 1


def read_worksheet(sheet, out):
    """FISav's per-category worksheet: poule cross-tables, then the bracket.

    The layout the existing worksheet adapter reads, in the variants it does
    not: the row label says "Assaut:" as often as "combat :", one sheet can
    carry six poules rather than one, and one file can carry a whole
    championship - thirteen classes over thirteen pages, two of which belong to
    a different competition printed in the same PDF.

    So the file is cut into worksheets first, at every page that opens with a
    weight-class code of its own, and each is read as if it were the only thing
    in the document. Read as one, the thirteen rosters merge, the bracket
    columns of page four splice into those of page five, and the sheet's own
    bout count stops agreeing with anything.

    Which column a number sits in is the whole meaning of the cross-table, so
    the columns are taken from the sheet's own repeated header - each fighter
    named once over the points block and once over the warnings block - and the
    values are found at a fixed offset to its right, measured rather than
    assumed.

    A pairing with no numbers beside it is stored unresolved. In the 2021
    Austrian world cup one poule bout was never scored, and the totals row
    proves it: the three fighters between them hold eight points where three
    fought bouts would pay twelve.
    """
    sheets, spare = _worksheet_pages(sheet)
    if not sheets:
        out.complain("no weight-class code opens any page - nothing read")
        return
    # A file that opens with a medal table and then gives a worksheet per class
    # is one competition twice over - its podium and the bouts behind it - and
    # both belong to the same tournament. The 2018 Loverval file is that shape.
    if spare and sniff_medal_grid(_Pages(spare)):
        out.complain("this file opens with a medal table; its podium is "
                           "read as well as its bouts")
        read_medal_grid(_Pages(spare), out)
        out.gender = out.age = ""
        out.klass = None
    for title, lines in sheets:
        before = len([r for r in out.rows if isinstance(r, Bout)])
        if title:
            out.heading(title)
        code = _class_code(lines[:4], out)
        if code:
            gender, age, kilos, bound = code
            out.gender, out.age = gender, age or out.section_age
            out.set_class(kilos, bound)
        else:
            out.complain("no weight-class code on this worksheet - rows "
                               "carry no class")
            out.klass = klass(out.gender, out.age)
        roster = _roster(lines, out.report)
        if code:
            _check_coded_class(out, roster, code)
        scale = _barème(lines, out, out.where())
        for entry in roster.values():
            out.report.notes.setdefault("roster", {})[entry["name"]] = \
                entry["country"]
        for poule, block in _poule_blocks(lines):
            _poule_bouts(out, poule, block, roster, scale)
        _bracket(out, lines, roster)
        _check_total(out, lines, len(roster), before)


def _same_person(one, other):
    """Is this the same competitor, named at two lengths by one document?

    A medal table prints "REFLA SAMUEL" where the worksheet beside it prints
    "REFLA". Either may be the shorter, and only a whole leading name counts -
    "MAR" is not "MARQUEZ".
    """
    one, other = _fold(one), _fold(other)
    if not one or not other:
        return False
    return one == other or one.startswith(other + " ") or \
        other.startswith(one + " ")


def _check_coded_class(out, roster, code):
    """Hold a worksheet's class code against what the document says elsewhere.

    The 2018 Loverval file heads one worksheet "FJ52" and prints its three
    competitors two pages earlier under "Coupe d'Europe assaut jeunes ...
    Inscrits Masculins / 48-52 JOVANOV Petar, REFLA SAMUEL, MESZAROS MATYAS".
    A code read as Female and a list printed as Masculins cannot both be right,
    and the letter is an abbreviation where the list is a word - so the
    contradiction is reported and the contradicted fields are left empty rather
    than decided in the code's favour.
    """
    gender, age, kilos, _ = code
    for entry in roster.values():
        for name, stated in out.stated.items():
            if not _same_person(entry["name"], name):
                continue
            for klass_, country in stated:
                if klass_["weight_kg"] != kilos:
                    continue
                if gender and klass_["gender"] and klass_["gender"] != gender:
                    out.complain(
                        f"the worksheet's class code reads {gender} where this "
                        f"document lists {name} at the same weight as "
                        f"{klass_['gender']} - no gender or age is stored for "
                        f"these bouts")
                    out.gender, out.age = "", out.section_age
                    out.set_class(kilos, code[3])
                    return
                if (country and entry["country"]
                        and country_of(country) != country_of(entry["country"])):
                    out.complain(
                        f"{name} is {country_of(country)} in this document's "
                        f"medal table and {country_of(entry['country'])} on "
                        f"its worksheet - each row keeps what its own line says")


class _Pages:
    """A slice of a document, shaped like a Sheet for the other readers."""

    def __init__(self, lines):
        self.lines = lines
        self.texts = [pdf.text_of(line) for line in lines]
        self.plain = "\n".join(self.texts)
        self.words = [w for line in lines for w in line]


def _worksheet_pages(sheet):
    """([(title, lines)], the pages before the first worksheet).

    A page opens a new worksheet when a class code is printed in its first few
    lines. A page that does not is a continuation: the 2018 Plovdiv sheets run
    their poules across two pages and print the code only on the first. Pages
    before the first worksheet are handed back rather than dropped - in one
    file they are the championship's medal table.
    """
    pages = {}
    for line in sheet.lines:
        pages.setdefault(line[0].page, []).append(line)
    out, spare = [], []
    for number in sorted(pages):
        lines = pages[number]
        if _class_code(lines[:4]) is None:
            if out:
                out[-1][1].extend(lines)
            else:
                spare.extend(lines)
            continue
        title = next((_squash(pdf.text_of(l)) for l in lines[:3]
                      if _is_title(_squash(pdf.text_of(l)))), "")
        out.append((title, list(lines)))
    return out, spare


_SYSTEM = re.compile(r"syst[èe]me\s+[àa]\s+(\d{1,3})\s+(?:assauts?|combats?)", re.I)
_ENTRANTS = re.compile(r"(\d{1,3})\s+athl[èe]tes", re.I)


def _check_total(out, lines, roster_size, before):
    """Hold the rows against the two totals the sheet prints about itself.

    These worksheets state how many competitors entered and how many bouts the
    format comes to - "19 athletes", "systeme a 26 assauts". Both are the
    federation's own arithmetic, so a reading that does not reproduce them is a
    reading to go and look at.
    """
    bouts = len([r for r in out.rows if isinstance(r, Bout)]) - before
    out.report.notes.setdefault("bouts", {})[out.where()] = bouts
    text = _text_of(lines)
    found = _SYSTEM.search(text)
    if found and int(found.group(1)) != bouts:
        out.complain(
            f"{out.where()}: the sheet says its format comes to "
            f"{found.group(1)} bouts; {bouts} were read")
    found = _ENTRANTS.search(text)
    if found and int(found.group(1)) != roster_size:
        out.complain(
            f"{out.where()}: the sheet says {found.group(1)} competitors "
            f"entered; {roster_size} are listed")


def _text_of(lines):
    return "\n".join(_squash(pdf.text_of(line)) for line in lines)


def _barème(lines, out, where=""):
    """{win, draw, loss} points, as the sheet prints them in its own corner."""
    scale = {"win": 3, "draw": None, "loss": 1}
    text = _text_of(lines)
    for key, pattern in _SCALE.items():
        found = pattern.search(text)
        if found:
            scale[key] = int(found.group(1).replace(" ", ""))
    if scale["draw"] is None:
        out.complain(
            f"{where}: the sheet does not print its scoring scale, so a level "
            f"scoreline is stored unresolved rather than called a draw")
    return scale


def _class_code(lines, out=None):
    """The weight class, from the code printed in the sheet's top corner."""
    for line in lines:
        for word in line:
            found = code_class(word.text) if out is None \
                else coded_class(word.text, out)
            if found:
                return found
    return None


def _roster(lines, report=None):
    """{index: {name, country, poule, seat}} from the "tireur N" list.

    Keyed by the order printed, not by the seat number: the 2018 M75 sheet
    numbers two different fighters "tireur 16", and keying on the seat would
    lose one of them silently.
    """
    out, poule, seats = {}, "", set()
    for line in lines:
        text = _squash(pdf.text_of(line))
        found = _POULE_HEADING.match(text)
        if found:
            poule = found.group(1).upper()
        seat, rest = None, []
        for index, word in enumerate(line):
            if index + 1 < len(line) and _SEAT.match(
                    f"{word.text} {line[index + 1].text}"):
                seat = int(line[index + 1].text)
                rest = line[index + 2:]
                break
            if _SEAT.match(word.text):
                seat = int(re.sub(r"\D", "", word.text))
                rest = line[index + 1:]
                break
        if seat is None:
            continue
        name, country = _entrant(rest)
        if not name:
            continue
        if seat in seats and report is not None:
            report.problem(f"the sheet numbers two competitors 'tireur {seat}' "
                           f"- both are kept")
        seats.add(seat)
        out[len(out) + 1] = {"name": name, "country": country,
                             "poule": poule, "seat": seat}
    return out



# The gap that separates two columns of a roster row. Within a cell the words
# sit a few points apart ("MONTEIRO CE", "Great Britain"); between the name,
# the nation and the bracket printed further right the gap is tens of points.
_COLUMN_GAP = 20.0


def _entrant(words):
    """("NAME", "Country") from the words to the right of a seat number.

    A roster row does not end at its nation: the knockout tree is printed
    across the same rows, so the row continues with names and labels that
    belong to the bracket. Only the first two cells are the competitor, and a
    cell is a run of words with no column-sized gap in it.
    """
    if not words:
        return "", ""
    cells, run = [], [words[0]]
    for previous, word in zip(words, words[1:]):
        if word.x0 - previous.x1 > _COLUMN_GAP:
            cells.append(run)
            run = [word]
        else:
            run.append(word)
    cells.append(run)
    name = _squash(" ".join(w.text for w in cells[0]))
    country = _squash(" ".join(w.text for w in cells[1])) if len(cells) > 1 else ""
    if not country:
        return split_nation(name)
    return name, country


def _poule_blocks(source):
    """[(poule letter, its lines)] - one sheet can hold six of them."""
    blocks, poule, lines = [], None, None
    for line in source:
        text = _squash(pdf.text_of(line))
        if _SERIES.match(text):
            if lines:
                blocks.append((poule, lines))
            found = _POULE_NAME.search(text)
            poule = found.group(1).upper() if found else ""
            lines = []
            continue
        if lines is not None:
            lines.append(line)
    if lines:
        blocks.append((poule, lines))
    return blocks


def _poule_bouts(out, poule, lines, roster, scale):
    """The bouts of one poule, from its cross-table."""
    header = next((l for l in lines
                   if sum(1 for w in l if _TIREUR.match(w.text)) >= 2), None)
    rows = [l for l in lines if l and _BOUT_LABEL.match(l[0].text)]
    if header is None or not rows:
        return
    # Where the numbers begin. Taken from the header rather than guessed at a
    # fixed distance from the fighter column: one 2018 poule prints the surname
    # "GONZALEZ ALBAR", whose second half sits further right than any fixed
    # allowance, and cutting there loses half of a competitor's name and files
    # his two bouts under two different people.
    tireurs = [w for w in header if _TIREUR.match(w.text)]
    after = [w.x0 for w in header
             if not _TIREUR.match(w.text) and w.x0 > max(t.x0 for t in tireurs)]
    limit = min(after) - 10 if after else None

    named = []
    for line in rows:
        words = [w for w in line[1:] if w.text != ":"]
        named.append([w for w in words if _numeric(w.text) is None
                      and (limit is None or w.x0 < limit)])
    blue_x = _blue_column(named)
    if blue_x is None:
        out.complain(f"poule {poule or '?'}: the two fighter columns "
                           f"could not be told apart - no bouts stored")
        return

    pairings = []
    for line, names in zip(rows, named):
        red = _squash(" ".join(w.text for w in names if w.x0 < blue_x - 4))
        blue = _squash(" ".join(w.text for w in names if w.x0 >= blue_x - 4))
        red = _as_rostered(red, roster, out)
        blue = _as_rostered(blue, roster, out)
        pairings.append((line, red, blue))

    order = []
    for _, red, blue in pairings:
        for who in (red, blue):
            if who and who not in order:
                order.append(who)
    points_x, warn_x = _value_columns(header, order, rows, out.report, poule)
    if points_x is None:
        return

    for line, red, blue in pairings:
        if not red or not blue:
            out.complain(f"poule {poule or '?'}: a bout line names "
                               f"{len([x for x in (red, blue) if x])} fighter(s) "
                               f"- not stored")
            continue
        if _fold(red) == _fold(blue):
            out.complain(f"poule {poule or '?'}: a bout line names "
                               f"{red} on both sides - not stored")
            continue
        points, warnings = {}, {}
        centres = points_x + warn_x
        for word in line:
            value = _numeric(word.text)
            if value is None:
                continue
            index = _nearest_column(word.x0, centres)
            if index is None:
                continue
            if index < len(points_x):
                points[order[index]] = value
            else:
                warnings[order[index - len(points_x)]] = value
        _store_poule_bout(out, poule, red, blue, points, warnings, roster, scale)


def _store_poule_bout(out, poule, red, blue, points, warnings, roster, scale):
    red_points, blue_points = points.get(red), points.get(blue)
    red_warn, blue_warn = warnings.get(red), warnings.get(blue)
    countries = {e["name"]: e["country"] for e in roster.values()}
    if not out.keeping:
        return
    index = len([r for r in out.rows if isinstance(r, Bout)]) + 1
    if red_points is None and blue_points is None:
        # A pairing printed with no score is a bout the sheet does not resolve.
        # It is still a bout: the two names are there and the draw put them
        # together. Storing it unresolved keeps the pairing and claims nothing.
        out.complain(
            f"poule {poule or '?'}: {red} v {blue} carries no points - stored "
            f"unresolved")
        corner, decision = "", ""
    else:
        red_points = red_points if red_points is not None else 0
        blue_points = blue_points if blue_points is not None else 0
        drawn = (scale["draw"] is not None
                 and red_points == blue_points == scale["draw"])
        corner = ("" if drawn else
                  "red" if red_points > blue_points else
                  "blue" if blue_points > red_points else "")
        if drawn:
            decision = "draw"
        elif corner:
            decision = rules.decision_from_points(
                max(red_points, blue_points), min(red_points, blue_points),
                (blue_warn if corner == "red" else red_warn))
        else:
            decision = ""
            out.complain(
                f"poule {poule or '?'}: {red} {red_points} - {blue} "
                f"{blue_points} is level but the sheet's scale does not call "
                f"it a draw - stored unresolved")
    out.rows.append(Bout(
        tournament=out.slug,
        bout_id=f"{out.slug}-{poule or 'x'}{index:03d}",
        phase="poule", poule=poule,
        red=red, red_country=country_of(countries.get(red, "")),
        blue=blue, blue_country=country_of(countries.get(blue, "")),
        red_points="" if red_points is None else str(red_points),
        blue_points="" if blue_points is None else str(blue_points),
        red_warnings="" if red_warn is None else str(red_warn),
        blue_warnings="" if blue_warn is None else str(blue_warn),
        winner_corner=corner,
        winner={"red": red, "blue": blue}.get(corner, ""),
        loser={"red": blue, "blue": red}.get(corner, ""),
        decision=decision,
        status="decided" if corner else "unresolved",
        result_source="scoresheet" if corner else "",
        **out.klass,
    ))


def _as_rostered(name, roster, out):
    """A truncated name put back together from the sheet's own entry list.

    Only where the sheet itself settles it: the name read off the table must be
    the opening of exactly one name on the roster. Two candidates, or none, and
    it is left as it was read - a name half-repaired towards the wrong person
    is worse than a name that is visibly short.
    """
    if not name or not roster:
        return name
    listed = [e["name"] for e in roster.values()]
    if any(_fold(n) == _fold(name) for n in listed):
        return name
    starts = [n for n in listed
              if _fold(n).startswith(_fold(name) + " ")]
    if len(starts) != 1:
        return name
    out.complain(f"the table prints {name!r} where the entry list says "
                 f"{starts[0]!r} - stored as the entry list has it")
    return starts[0]


def _blue_column(named):
    """x of the second fighter column: the x every bout line has in common.

    One column is left-aligned and the other is not, and which is which moves
    from sheet to sheet, so neither can be assumed. What does hold is that the
    right-hand column starts at the same x on every line of the poule, so the
    rightmost x shared by all of them is that column.
    """
    shared = None
    for names in named:
        here = {round(w.x0) for w in names}
        shared = here if shared is None else (shared & here)
    if not shared:
        return None
    return max(shared)


def _value_columns(header, order, rows, report, poule):
    """(points column centres, warnings column centres), in roster order."""
    names = [w for w in header if not _TIREUR.match(w.text)]
    anchors = {}
    for who in order:
        first = who.split(" ")[0]
        seen = [w.x0 for w in names if w.text == first]
        if len(seen) != 2:
            report.problem(
                f"poule {poule or '?'}: {who} appears {len(seen)} times in the "
                f"column header, not twice - no bouts stored for this poule")
            return None, None
        anchors[who] = sorted(seen)
    shift = _offset([x for pair in anchors.values() for x in pair], rows)
    points = [anchors[who][0] + shift for who in order]
    warnings = [anchors[who][1] + shift for who in order]
    return points, warnings


def _offset(anchors, rows):
    """How far right of its heading a column's values sit, measured, not assumed."""
    import statistics
    gaps = []
    for line in rows:
        for word in line:
            if _numeric(word.text) is None:
                continue
            left = [a for a in anchors if 0 <= word.x0 - a < 90]
            if left:
                gaps.append(word.x0 - max(left))
    return statistics.median(gaps) if gaps else 12.0


def _nearest_column(x, centres):
    """Index of the column a value sits in, or None if it sits in none.

    The tolerance is taken from the sheet's own column spacing rather than
    fixed: a four-fighter table is laid out more tightly than a three-fighter
    one, and a tolerance that suits one puts every value of the other in the
    wrong column.
    """
    if len(centres) < 2:
        return None
    spacing = min(b - a for a, b in zip(sorted(centres), sorted(centres)[1:])
                  if b > a) if len(set(centres)) > 1 else 40
    tolerance = max(6.0, spacing * 0.45)
    best = min(range(len(centres)), key=lambda i: abs(x - centres[i]))
    return best if abs(x - centres[best]) <= tolerance else None


# ---- brackets: a name reprinted to the right is a name that won ----------

# Rounds, rightmost first. A bracket is read from its final backwards, because
# that is the only end of it whose meaning is fixed.
_PHASES_RIGHT_TO_LEFT = ["final", "semi", "quarter", "r16", "r32", "r64"]


def _sightings(lines, names, skip_x=None, tolerance=8.0):
    """[(name, x0, x1, y)] for every place one of `names` is printed.

    Longest name first at each position, so "DOS SANTOS Ronaldo" is one
    sighting and not three.
    """
    ordered = sorted(names, key=lambda n: -len(n.split()))
    out = []
    for line in lines:
        index = 0
        while index < len(line):
            hit = None
            for name in ordered:
                parts = name.split()
                if index + len(parts) > len(line):
                    continue
                run = line[index:index + len(parts)]
                if [w.text for w in run] != parts:
                    continue
                # A name is one cell. Two words a column apart are two cells,
                # however well they spell somebody's name together.
                if any(b.x0 - a.x1 > _COLUMN_GAP for a, b in zip(run, run[1:])):
                    continue
                hit = (name, len(parts))
                break
            if hit is None:
                index += 1
                continue
            word = line[index]
            end = line[index + hit[1] - 1]
            if skip_x is None or abs(word.x0 - skip_x) > tolerance:
                out.append((hit[0], word.x0, end.x1, word.top))
            index += hit[1]
    return out


def _x_columns(sightings, overlap=4.0):
    """Sightings grouped into vertical columns, left to right.

    Grouped by whether the printed names overlap horizontally, not by where
    they start. One 2018 sheet sets its final column flush right, so "BARBARO
    Gianni" begins forty points left of "DAHIE" in the same column; grouped on
    their starting x the final becomes two columns and its bout disappears.
    """
    columns, reach = [], None
    for sighting in sorted(sightings, key=lambda s: s[1]):
        x0, x1 = sighting[1], sighting[2]
        if columns and x0 <= reach - overlap:
            columns[-1].append(sighting)
            reach = max(reach, x1)
        else:
            columns.append([sighting])
            reach = x1
    return columns


def _drop_result_markers(column):
    """A name reprinted inside its own column, between two others, is a result.

    The 2018 worksheets fold the champion back into the final's column, so that
    column holds three entries: two finalists and the winner, printed a second
    time halfway between them. Paired naively that is a fighter against
    himself, which is the one row this archive must never produce.

    Only an interior duplicate is a marker - a name at the top or the bottom of
    its column is a competitor, because nothing is printed beyond it for it to
    be the result of. Where a name repeats and more than one of its copies is
    interior the shape is not understood, and nothing is dropped.
    """
    markers = []
    groups = {}
    for entry in column:
        groups.setdefault(entry[0], []).append(entry)
    for name, group in groups.items():
        if len(group) < 2:
            continue
        inside = [e for e in group
                  if any(o[3] < e[3] - 2 for o in column)
                  and any(o[3] > e[3] + 2 for o in column)]
        if len(inside) == 1:
            markers.append(inside[0])
    keep = [e for e in column if e not in markers]
    return keep, markers


def _bracket_bouts(out, lines, entrants, skip_x=None, first_is_seeding=False):
    """Bouts from a bracket tree, and the placings its final states.

    Each column is the entrants of one round, top to bottom, so neighbours are
    opponents. The winner is whichever of the two is printed again further
    right, at a height between them - that repetition is the whole record. A
    pair with no reprinted name is a bout the sheet leaves open, and it is
    stored that way rather than handed to the fighter listed first.
    """
    names = {e["name"]: e.get("country", "") for e in entrants}
    if not names:
        return []
    columns = _x_columns(_sightings(lines, names, skip_x))
    if first_is_seeding and columns:
        columns = columns[1:]
    trimmed = []
    for column in columns:
        keep, markers = _drop_result_markers(sorted(column, key=lambda e: e[3]))
        trimmed.append((keep, markers))
    pairable = [i for i, (keep, _) in enumerate(trimmed) if len(keep) >= 2]
    if not pairable:
        return []
    phases = {}
    for depth, index in enumerate(reversed(pairable)):
        phases[index] = (_PHASES_RIGHT_TO_LEFT[depth]
                         if depth < len(_PHASES_RIGHT_TO_LEFT) else "")
    everything = [e for column in columns for e in column]

    made = []
    for index in pairable:
        keep, _ = trimmed[index]
        if len(keep) % 2:
            out.complain(
                f"{phases[index]}: {len(keep)} names in one bracket column, "
                f"which cannot be paired - no bouts stored for that round")
            continue
        column_x = min(e[1] for e in keep)
        for first, second in zip(keep[0::2], keep[1::2]):
            if _fold(first[0]) == _fold(second[0]):
                out.complain(
                    f"{phases[index]}: {first[0]} is printed against himself - "
                    f"not stored")
                continue
            top, bottom = first[3], second[3]
            winners = [e for e in everything
                       if e[1] > column_x + 10 and top + 2 < e[3] < bottom - 2
                       and e[0] in (first[0], second[0])]
            winners += [e for e in trimmed[index][1]
                        if top + 2 < e[3] < bottom - 2
                        and e[0] in (first[0], second[0])]
            winner = winners[0][0] if winners else ""
            made.append((phases[index], first[0], second[0], winner))

    # Two fighters meet once in a knockout tree. Where the same pair comes out
    # of two rounds the tree was printed twice - one 2018 file repeats each
    # finalist's cell beside itself, with a spreadsheet's #REF! between them -
    # and the later round is the real one.
    latest = {}
    for entry in made:
        latest[frozenset((entry[1], entry[2]))] = entry
    if len(latest) < len(made):
        out.complain(
            f"{len(made) - len(latest)} bracket pairing(s) are printed twice "
            f"in this tree; only the later round of each is stored")
    made = [e for e in made if latest[frozenset((e[1], e[2]))] is e]

    for phase, red, blue, winner in made:
        if not out.keeping:
            break
        number = len([r for r in out.rows if isinstance(r, Bout)]) + 1
        if not winner:
            out.complain(
                f"{phase}: {red} v {blue} - the sheet reprints neither name "
                f"further right, so the winner is unknown; stored unresolved")
        out.rows.append(Bout(
            tournament=out.slug,
            bout_id=f"{out.slug}-{phase or 'ko'}-{number:03d}",
            phase=phase,
            red=red, red_country=country_of(names.get(red, "")),
            blue=blue, blue_country=country_of(names.get(blue, "")),
            # A bracket prints a tree, not corners.
            winner=winner, winner_corner="",
            loser=({red, blue} - {winner}).pop() if winner else "",
            status="decided" if winner else "unresolved",
            result_source="reported" if winner else "",
            **out.klass,
        ))
    return made


def _bracket(out, source, roster):
    """The knockout tree a worksheet prints above its cross-tables.

    The tree is drawn across the same rows as the entry list, so the entry
    list's own name column has to be left out of it - otherwise every
    competitor is sighted once in a column that is not part of the bracket at
    all, and the tree gains a round nobody fought.
    """
    head = []
    for line in source:
        text = _squash(pdf.text_of(line))
        if _SERIES.match(text) or re.match(r"^r[ée]sultats\s*:", text, re.I):
            break
        head.append(line)
    if not roster:
        return
    starts = {}
    for line in head:
        if not _SEAT.match(_squash(" ".join(w.text for w in line[:2]))):
            continue
        if len(line) > 2:
            starts[round(line[2].x0)] = starts.get(round(line[2].x0), 0) + 1
    entry_column = max(starts, key=starts.get) if starts else None
    _bracket_bouts(out, head, list(roster.values()), skip_x=entry_column)


# ---- reader: group tables with a knockout tree beside them ---------------

# The 2022 Milan sheets are set in a font whose capital M is kerned so tightly
# that poppler puts a space after it: "M EDHI LAURENT", "M AURITIUS", "CHAM
# PION", "SAM UEL". Left alone the archive gains a fighter called EDHI LAURENT
# and a nation called AURITIUS. The repair is narrow on purpose - only a
# fragment that ends in M, only across a gap far below any real word space
# (the real ones on these sheets measure 1.05pt and up), and never across the
# overlapping pair that the same defect also produces.
_KERNED_GAP = 0.9


def _rejoin_kerned(lines):
    from savate.pdf import Word

    out = []
    for line in lines:
        joined = []
        for word in line:
            previous = joined[-1] if joined else None
            gap = word.x0 - previous.x1 if previous else None
            if (previous is not None and 0 <= gap < _KERNED_GAP
                    and previous.text.endswith("M")
                    and previous.text.isupper() and word.text.isupper()
                    and abs(word.top - previous.top) < 0.5):
                joined[-1] = Word(text=previous.text + word.text,
                                  x0=previous.x0, x1=word.x1,
                                  top=min(previous.top, word.top),
                                  bottom=max(previous.bottom, word.bottom),
                                  page=previous.page)
            else:
                joined.append(word)
        out.append(joined)
    return out


_SLOT = re.compile(r"^[A-Z]\d{1,2}$")
_GROUP_HEADING = re.compile(r"\bgroups?\b", re.I)
_FOOTER = re.compile(
    r"^(?P<code>[JSCV]?[FM]\s*\+?\s*\d{2,3})\s*-\s*(?P<name>.+?)\s*-\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*(?P<city>.+)$")


def sniff_knockout_groups(sheet):
    head = " ".join(sheet.texts[:3])
    return bool(_GROUP_HEADING.search(head)) and \
        sum(1 for line in sheet.lines if line and _SLOT.match(line[0].text)) >= 3


def read_knockout_groups(sheet, out, tournament=None):
    """Seeded groups on the left, the knockout path drawn to the right.

    The group bouts themselves are not printed - only who came first and second
    out of each group - so none are stored. What the sheet does record, and
    completely, is every knockout bout: each winner is printed again one column
    to the right, at the height of the bout he won.
    """
    lines = _rejoin_kerned(sheet.lines)
    seeds, seed_x = [], None
    for line in lines:
        if not line or not _SLOT.match(line[0].text):
            continue
        if _FOOTER.match(_squash(pdf.text_of(line))):
            continue        # the footer opens with the class code, not a slot
        rest = line[1:]
        if seed_x is None and rest:
            seed_x = rest[0].x0
        cells, _ = _medallists([w.text for w in rest])
        if not cells:
            out.report.problem(
                f"{_squash(pdf.text_of(line))[:60]!r}: no nation this archive "
                f"recognises, so the competitor could not be told from the "
                f"country - not stored")
            continue
        seeds.append({"name": cells[0][0], "country": cells[0][1],
                      "slot": line[0].text})
    footer = None
    for text in sheet.texts:
        found = _FOOTER.match(_squash(text))
        if found:
            footer = found
    if footer:
        code = coded_class(footer.group("code").replace(" ", ""), out)
        if code:
            gender, age, kilos, bound = code
            out.gender, out.age = gender, age or out.section_age
            out.set_class(kilos, bound)
        if tournament is not None:
            tournament.name = tournament.name or _squash(footer.group("name")).title()
            tournament.city = tournament.city or _squash(footer.group("city")).title()
            tournament.start_date = tournament.start_date or footer.group("date")
            tournament.year = tournament.year or footer.group("date")[:4]
    if out.klass is None:
        out.report.problem("no weight class printed - rows carry none")
        out.klass = klass(out.gender, out.age)
    out.report.notes["groups"] = [s["slot"] for s in seeds]
    out.report.problem("the group bouts are not printed on this sheet, only "
                       "who came first and second out of each group - no "
                       "group bouts stored")
    _bracket_bouts(out, lines, seeds, skip_x=seed_x)


# ---- reader: Score Fighting Manager bracket sheets -----------------------

_SFM = re.compile(r"score\s+fighting\s+manager", re.I)
_SPECIALITE = re.compile(r"sp[ée]cialit[ée]", re.I)
_POULE_SEED = re.compile(r"^\d{1,2}$")


def sniff_sfm(sheet):
    return bool(_SFM.search(sheet.plain))


def read_sfm(sheet, out, tournament=None):
    """One page per weight class, a seeded poule list and a bracket tree.

    The poule bouts are not on the page - the header's "A/Sav" column counts
    them and nothing prints them - so only the bracket is read. Each page is
    its own class and its own tree, so the pages are read one at a time: two
    pages share the same heights, and read together their trees would be
    spliced into each other.
    """
    pages = {}
    for line in sheet.lines:
        pages.setdefault(line[0].page, []).append(line)
    for number in sorted(pages):
        lines = pages[number]
        out.klass = None
        _sfm_class(lines, out)
        if out.klass is None:
            out.report.problem(f"page {number}: no weight class printed - "
                               f"no bouts stored")
            continue
        entrants, name_x = _sfm_entrants(lines)
        if not entrants:
            out.report.problem(f"page {number}: no poule list - no bouts stored")
            continue
        _bracket_bouts(out, lines, entrants, skip_x=name_x)
    out.report.problem("the poule bouts are not printed on these sheets - only "
                       "the knockout tree is stored")


def _sfm_class(lines, out):
    """The class from the sheet's own "Spécialité: Juniors M -56" header."""
    for index, line in enumerate(lines):
        anchor = next((w for w in line if _SPECIALITE.search(w.text)), None)
        if anchor is None:
            continue
        limit = next((w.x0 for w in line if w.x0 > anchor.x0 + 20), None)
        for below in lines[index + 1:index + 3]:
            cell = [w for w in below
                    if w.x0 >= anchor.x0 - 4 and (limit is None or w.x0 < limit - 4)]
            text = _squash(" ".join(w.text for w in cell))
            if not text:
                continue
            out.age = age_of(text) or out.age
            out.gender = next((gender_of(w.text) for w in cell
                               if len(w.text) == 1), "") or out.gender
            found, _ = weight_at(re.sub(r"(?i)[a-zà-ÿ]+", " ", text).strip())
            if found:
                out.set_class(*found)
                return


def _sfm_entrants(lines):
    """([{name, country}], x of the name column) from the seeded poule lists.

    The column is found before anything is read out of it. The bracket is drawn
    across the same rows, so the first poule line also carries a name from the
    tree; parsed before the column is known, that name is swallowed into the
    first competitor's country.
    """
    seeded = [line for line in lines
              if len(line) >= 3 and _POULE_SEED.match(line[0].text)]
    if not seeded:
        return [], None
    counts = {}
    for line in seeded:
        counts[round(line[1].x0)] = counts.get(round(line[1].x0), 0) + 1
    name_x = max(counts, key=counts.get)

    entrants = []
    for line in seeded:
        rest = line[1:]
        if abs(rest[0].x0 - name_x) > 6:
            continue
        cell = [w for w in rest if w.x0 < name_x + 120]
        text = _squash(" ".join(w.text for w in cell))
        if "," not in text:
            continue
        name, country = text.split(",", 1)
        name, country = _squash(name), _squash(country)
        if not name or not country:
            continue
        entrants.append({"name": name, "country": country})
    return entrants, name_x


# ---- which reader a document answers to ---------------------------------

# Order matters where two sniffs could both fire. The specific layouts go
# first: a Score Fighting Manager page also looks a little like a poule list,
# and a sheet whose places are bare numbers in a right-hand column also looks a
# little like a ranked table.
LAYOUTS = [
    ("sfm", sniff_sfm, read_sfm),
    ("knockout_groups", sniff_knockout_groups, read_knockout_groups),
    ("worksheet", sniff_worksheet, read_worksheet),
    ("finals_sheet", sniff_finals_sheet, read_finals_sheet),
    ("bat_memo", sniff_bat_memo, read_bat_memo),
    ("medal_grid", sniff_medal_grid, read_medal_grid),
    ("medal_words", sniff_medal_words, read_medal_words),
    ("placed_list", sniff_placed_list, read_placed_list),
    ("country_first", sniff_country_first, read_country_first),
    ("numbered_list", sniff_numbered_list, read_numbered_list),
    ("ranked_rows", sniff_ranked_rows, read_ranked_rows),
]
# Readers that want to fill in the tournament from the sheet's own footer.
_WANTS_TOURNAMENT = {"sfm", "knockout_groups"}
# The row tolerance each layout is read at. The worksheets need a looser one:
# their "tireur 3" label and the name beside it are printed three points apart,
# and read as two lines the roster loses every nation on the sheet.
_TOLERANCE = {"worksheet": 4.0}


def layouts():
    return [name for name, _, _ in LAYOUTS]


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout | Placing], Report) from one FISav sheet."""
    from savate import sources

    meta = dict(meta or {})
    section = str(options.get("section") or meta.pop("section", "") or "").strip()
    forced = str(options.get("layout") or meta.pop("layout", "") or "").strip()
    report = Report(source=str(source), adapter=NAME)
    tournament = Tournament(
        slug=slug, source=str(source), adapter=NAME,
        **{k: v for k, v in meta.items() if k in TOURNAMENT_FIELDS})
    for key in meta:
        if key not in TOURNAMENT_FIELDS:
            report.problem(f"meta key {key!r} is not a tournament field - ignored")

    path = (sources.fetch_archived(str(source)) if options.get("archived")
            else sources.fetch(source, refresh=options.get("refresh", False),
                               binary=False))
    body = path.read_bytes()
    out = Rows(slug, report, section)

    if not body.startswith(b"%PDF"):
        lines = html_lines(body.decode("utf-8", errors="replace"))
        report.read = len(lines)
        if not sniff_champions_html(lines):
            report.notes["kind"] = "not a PDF and not a champions article"
            report.problem("this page is not a document this adapter reads")
            return tournament, [], report
        report.notes["layout"] = "champions_html"
        try:
            read_champions_html(lines, out)
        except Exception as e:                       # noqa: BLE001 - see below
            report.problem(f"champions_html failed on this page: {e!r}")
        return _finish(tournament, out, report, section)

    chosen = None
    probe = Sheet(path)
    report.read = len({w.page for w in probe.words})
    for name, sniff, reader in LAYOUTS:
        if forced and name != forced:
            continue
        try:
            if forced or sniff(probe):
                chosen = (name, reader)
                break
        except Exception as e:                       # noqa: BLE001
            report.problem(f"the {name} test failed on this document: {e!r}")
    if chosen is None:
        report.notes["kind"] = "no reader in this adapter recognises this sheet"
        report.problem("no reader in this adapter recognises this document")
        return tournament, [], report

    name, reader = chosen
    report.notes["layout"] = name
    sheet = (probe if name not in _TOLERANCE
             else Sheet(path, tolerance=_TOLERANCE[name]))
    try:
        # Federation paperwork is routinely malformed, and a reader that trips
        # over one page must still hand back the rows it read from the others.
        if name in _WANTS_TOURNAMENT:
            reader(sheet, out, tournament)
        else:
            reader(sheet, out)
    except Exception as e:                           # noqa: BLE001
        report.problem(f"the {name} reader stopped on this document: {e!r}")
    return _finish(tournament, out, report, section)


def _finish(tournament, out, report, section):
    report.notes["competitions"] = out.titles
    report.notes["rows"] = len(out.rows)
    if section and out.titles and not any(_wanted(t, section) for t in out.titles):
        report.problem(
            f"this document carries no competition matching section "
            f"{section!r}; it holds: {', '.join(out.titles) or 'one unnamed'}")
    if not section and len(out.titles) > 1:
        report.problem(
            f"this document carries {len(out.titles)} competitions and no "
            f"`section` was given, so all of them were read together: "
            f"{', '.join(out.titles)}")
    if not out.rows:
        report.problem("no rows read")
    return tournament, out.rows, report
