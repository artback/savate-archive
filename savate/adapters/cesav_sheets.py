"""CESav's blog posts: a championship written out as sentences.

The European confederation keeps its podium tables on one ranking page - that is
`cesav_ranking`'s job - but it also announces results as ordinary articles, and
those articles carry competitions the tables never got. They are prose, not
tables, and three sentence shapes do all the work:

    M-65kg:  Berrou Alan (FRA) won against Leskovic Luka (CRO)     one bout
    F60 Vincis Chiara - ITALIE- Buzuel Atef Maurine - FRANCE  Winner: Buzuel …
    JM-60 / Champion : SHCHERBACHENKO Sergei, RUSSIA               one placing

So this reads lines, not cells. A line is offered to each shape in turn, and a
line no shape claims is prose and is ignored - which is most of the article.

WHAT THIS ADAPTER REFUSES TO DO

*It does not assign corners.* "X won against Y" names a winner, never a corner.
red/blue mean corner in this archive, so `red` and `blue` record only the order
the sentence printed the two fighters in, and `winner_corner` stays empty.

*It does not call a bout a final.* These pages print one bout per weight class
under a heading that says "results", and in a championship that bout is almost
certainly the final - but "almost certainly" is not what a document said. The
phase is left empty and no gold/silver placing is derived from it, because a
podium invented from an unstated round is a podium this archive made up.

*It does not repair a weight class it cannot read.* The 2016 page prints
"M150kg", and there is no 150 kg class in savate. The FFSavate sheets use M150
as a sentinel for the open class, but that is another federation's coding scheme
and this page never says it shares it. The printed code is kept verbatim as the
category, the weight is left empty, and the read reports it.

*It does not file a line that belongs to another occasion.* One 2016 line ends
"… in Savona (Italy) on 23rd October 2016", naming a city and a date that are
neither of the two the article is about. A bout from a different event filed
under this tournament is a wrong row, so the line is dropped and reported with
its text intact, which is the only form in which it is still recoverable.

*It does not file another sport.* Canne de combat, chausson, bâton and savate
forme share these pages' federations and nothing else. Their lines are dropped
and counted. A demonstration bout has no result and is not a bout; it is dropped
and counted too.

*It does not read one article twice because the URL was written twice.* Joomla
routes a blog URL on the number that opens the last path segment and discards
the slug after it: /blog/12-combat-european-championship-2016-results,
/blog/12-europen-championship-combat-2016-results and a slug this archive made
up, /blog/12-this-slug-is-nonsense, all return article 12 - byte-identical
article bodies, SHA-256 5d290eff…. Two URLs are not two competitions, and
reading both would put nine bouts into the archive as eighteen and hand every
fighter on the page a doubled record. `document_id()` is what the site routes
on, and a second URL that lands on an article already read in this run is
reported as what it is.

*It does not settle a disagreement the document has with itself.* The 2016 page
is headed "COMBAT EUROPEAN CHAMPIONSHIP 2016" and opens "The Combat World
Championship was held in two locations in 2016". Both are printed; the document
does not say which is right, so the level is left empty and the disagreement is
reported. Picking the headline would have stored a scope this page contradicts.

*It does not file a qualifying tournament as the championship it qualifies for.*
The 2016 Greek document opens "The qualifying tournament of the 2016 European
Championships"; `competition.FORMATS` has no value for a qualifying tournament,
so the format is left empty and reported, rather than taking "championship" off
the word "Championships" in its own title.

WHAT IT DOES INFER, AND SAYS SO

A subheading dates a group of bouts as "8th October" with no year; the year comes
from the article's own headline or body. Two facts the same document states,
joined - not a guess - but `report.notes["year_from"]` records which one.

A bare class code with no sign ("F60", "M75") is read as the class *under* that
weight, which is how F48 and M85 are read everywhere else in this archive. The
page prints no sign, so this is a reading of a convention; it is noted on every
read that uses it.

Gender comes from the letter in a printed class code - M-65kg is a men's class,
F-48kg a women's - and never from a name. That is reading a code the page
prints, the way FRA is read as France; `report.notes["gender_from"]` says so on
every read that fills the column.

A medal is a thing a document says was awarded. These pages print "Champion"
and "Vice-champion", which are finishing positions and not medals, so the medal
column holds `schema.MEDALS` - the archive's own rank -> medal mapping, which
`schema.check_placing` requires of every ranked row. The read reports this and
`report.notes["medal_from"]` records it, because on a qualifying tournament's
document no medal is mentioned at all.
"""

import html
import re
from urllib.parse import urlsplit

from savate import competition, display
from savate.schema import MEDALS, Bout, Placing, Report, Tournament

NAME = "cesav_sheets"
DESCRIPTION = "CESav blog articles: prose bout lines and champion/vice-champion lists"

# ---- getting from a Joomla page to the sentences someone actually wrote ----

_BODY = re.compile(r'itemprop="articleBody"(.*)$', re.S | re.I)
# Everything after the article is furniture: the sidebar's search box, the
# footer's contact form. Cutting there stops a menu item being read as a result.
_FURNITURE = re.compile(r'<aside\b|id="g-aside"|<footer\b|rokajaxsearch|'
                        r'class="g-block size-25"', re.I)
_ARTICLE_END = re.compile(r"</div>\s*</div>", re.S | re.I)
_BLOCK = re.compile(r"</(?:p|div|li|h[1-6]|tr|td|blockquote)\s*>|<br\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")
_HEADLINE = re.compile(r'itemprop="headline"[^>]*>(.*?)</', re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


# A superscript ordinal is its own element, so stripping the tags leaves
# "23 rd October". Putting it back is not a reading of the text; it is undoing
# damage the markup did to a word that was printed as one.
_ORDINAL = re.compile(r"(\d)\s+(st|nd|rd|th|er|re|e|ème)\b", re.I)


def _plain(fragment):
    text = html.unescape(_TAGS.sub(" ", fragment or ""))
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return _ORDINAL.sub(r"\1\2", text)


def _article(page):
    """(the article's markup, whether the marker was found)."""
    found = _BODY.search(page or "")
    body = found.group(1) if found else (page or "")
    cut = _FURNITURE.search(body)
    if cut:
        body = body[:cut.start()]
    end = _ARTICLE_END.search(body)
    if end:
        body = body[:end.start()]
    return body, bool(found)


def _lines(markup):
    """One printed line per block element, tags gone, entities resolved."""
    out = []
    for chunk in _BLOCK.split(markup):
        text = _plain(chunk)
        if text and text not in (">", "<"):
            out.append(text)
    return out


def _headline(page):
    for pattern in (_HEADLINE, _TITLE):
        found = pattern.search(page or "")
        if found:
            text = _plain(found.group(1))
            if text:
                return text
    return ""


# ---- which article a URL addresses, whatever slug was written after it -----
#
# Joomla serves /index.php/blog/<id>-<slug> by the id alone. Checked, not
# assumed: /blog/12-combat-european-championship-2016-results,
# /blog/12-europen-championship-combat-2016-results and /blog/12-this-slug-is-
# nonsense all return one article whose extracted body hashes to the same
# SHA-256. So the slug carries no identity and two URLs ending in the same id
# are one document - which is the difference between nine bouts in the archive
# and eighteen.

_ROUTED_ON = re.compile(r"^(\d+)-")

# Articles already read in this process, by identity, with the URL that read
# them. A build reads every manifest entry in one run, so an alias that slipped
# into the manifest is caught here rather than in the finished database.
_READ_DOCUMENTS = {}


def document_id(source):
    """What the site routes this URL on: "host#id", or "" if it is not one."""
    text = str(source or "")
    if not re.match(r"https?://", text):
        return ""
    parts = urlsplit(text)
    tail = [piece for piece in parts.path.split("/") if piece]
    found = _ROUTED_ON.match(tail[-1]) if tail else None
    if not found:
        return ""
    host = parts.netloc.lower().split("@")[-1]
    if host.startswith("www."):
        host = host[4:]
    return f"{host}#{found.group(1)}"


def note_document(source, report):
    """Record which article this is, and say so if it has been read already."""
    ident = document_id(source)
    if not ident:
        return ""
    report.notes["document_id"] = ident
    first = _READ_DOCUMENTS.setdefault(ident, str(source))
    if first != str(source):
        report.problem(
            f"this is the same article as {first}: the site routes on {ident} "
            f"and discards the slug written after it, so both URLs return one "
            f"document and reading both would put every row on it into the "
            f"archive twice")
    return ident


def forget_documents():
    """Forget which articles have been read - for a test, or a second run."""
    _READ_DOCUMENTS.clear()


# ---- the vocabulary of the pages -----------------------------------------

# Canne de combat, chausson, bâton and savate forme are different sports. They
# turn up on the same federations' pages and must never be filed as savate.
_OTHER_SPORT = re.compile(
    r"\bcanne\s*(?:de\s*combat|fleuret)?\b|\bchausson\b|\bb[âa]ton\b|"
    r"\bsavate\s*forme\b|\bdouble\s*canne\b", re.I)

# A demonstration has no result. It is not a bout and must not become one.
_DEMO = re.compile(r"\bd[ée]mo(?:nstration)?\b|\bexhibition\b|\bshow\s*fight\b|"
                   r"\bhors\s*comp[ée]tition\b", re.I)

# "won against", and the other ways these articles have of saying it. Kept
# deliberately narrow: a loose verb list turns prose into bouts.
_BEAT = r"(?:won\s+(?:against|over)|wins\s+against|beats?|defeated|d[ée]fait)"

_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
           "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
           "november": 11, "december": 12,
           "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
           "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
           "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
           "decembre": 12}

# "8th October, Morbihan" - a day, a month, and where it happened.
_OCCASION = re.compile(
    r"^(\d{1,2})\s*(?:st|nd|rd|th|er|e|ème)?\s+([A-Za-zéûôà]+)\s*[,\-–]\s*(.+?)\s*$")

# A class code: an optional J/S age letter, an optional F/M, an optional sign,
# the figure (or a band), and an optional "kg".
_CLASS = re.compile(
    r"^(J|S|V)?\s*([FM])?\s*([-+−])?\s*(\d{2,3}(?:[.,]\d)?)"
    r"(?:\s*[-–]\s*(\d{2,3}(?:[.,]\d)?))?\s*(?:kgs?|kilos?)?\s*$", re.I)

# What a savate weight class can plausibly say. The heaviest bound any
# federation prints is +85 for men; below 20 kg nobody competes. A figure
# outside that is not a weight class and is not read as one.
_MIN_KG, _MAX_KG = 20, 95

# Where a class heading and its two names are printed as one run.
_RANKS = [
    (2, r"^vice[\s-]?champion|^2\b|^2(?:nd|e|ème)\b|^finalist|^runner[\s-]?up|"
        r"^second|^argent|^silver"),
    (1, r"^champion(?:ne)?\b|^1\b|^1(?:st|er|ère)\b|^winner|^gold|^or\b|^vainqueur"),
    (3, r"^3\b|^3(?:rd|e|ème)\b|^bronze|^troisi|^third"),
]
# The separator is a colon, or a dash with space on both sides. A bare dash
# cannot be one: it would split "Vice-champion" into "Vice" and the rest, and
# every runner-up on the page would then be read as an unlabelled line.
_RANK_LINE = re.compile(r"^(.{3,30}?)\s*(?::|\s+[-–]\s+)\s*(.+)$")

# "The qualifying tournament of the 2016 European Championships" - an event
# whose own name contains the name of the competition it is not. Matched as the
# phrase, never on the bare word, so "he qualified" stays prose.
_QUALIFYING = re.compile(
    r"\bqualif\w*\s+(?:\w+\s+){0,2}?(?:tournament|tournoi)\b|"
    r"\b(?:tournament|tournoi)\s+(?:\w+\s+){0,2}?qualif\w*", re.I)

# A word that names a medal, as opposed to a finishing position. "Champion" is
# a position; "gold" is a medal; the archive must not turn one into the other.
_MEDAL_WORD = re.compile(r"\bgold\b|\bsilver\b|\bbronze\b|\bor\b|"
                         r"\bargent\b|m[ée]daille", re.I)

# A title the championship did not award is printed, and is not a competitor.
_NOT_AWARDED = re.compile(r"titre non attribu|non attribu|not awarded|"
                          r"no\s+(?:title|champion)", re.I)


def _rank_of(word):
    for rank, pattern in _RANKS:
        if re.search(pattern, word.strip(), re.I):
            return rank
    return 0


# ---- nations ---------------------------------------------------------------
#
# CESav prints the nation right after the name with nothing but a space, or a
# comma, between them - "PLACE Lorenzo FRANCE". Splitting on the last word makes
# a competitor called FRANCE out of every one of them, so the split is made on
# the longest nation spelling the archive already attests, tested as a suffix.
# The table is display's, the same one that resolves every other country here.

def _nation_suffixes():
    spellings = []
    for canonical in display.countries():
        for spelling in display.spellings(canonical):
            folded = display.fold(spelling).replace(" ", "")
            if len(folded) >= 3:
                spellings.append((folded, canonical))
    spellings.sort(key=lambda pair: -len(pair[0]))
    return spellings


_NATIONS = _nation_suffixes()


def split_nation(text):
    """("NAME", "Nation") - the nation is the longest one the text ends with."""
    text = " ".join(str(text or "").split())
    if not text:
        return "", ""
    squeezed = display.fold(text).replace(" ", "")
    for folded, canonical in _NATIONS:
        if squeezed.endswith(folded):
            kept, seen = [], 0
            for ch in reversed(text):
                if seen >= len(folded):
                    kept.append(ch)
                elif ch.isalnum():
                    seen += 1
            name = "".join(reversed(kept)).strip(" ,;-–")
            if name:
                return name, canonical
            return text, ""
    return text, ""


def _country(printed):
    resolved = display.country(printed)
    return resolved.name if resolved.known else " ".join(str(printed).split())


def _person(raw):
    """(name, "") for a printed competitor, or ("", reason) if it is not one."""
    person = display.name(raw)
    if not person.usable:
        return "", person.reason
    text = person.text.strip(" ,;-–")
    if len(text) < 3 or not re.search(r"[A-Za-zÀ-ÿ]{2}", text):
        return "", "too short to be a name"
    return text, ""


# ---- reading a class code --------------------------------------------------

class _Class:
    """What one printed class code says, and what it refused to say."""

    __slots__ = ("label", "gender", "age_class", "weight_kg", "weight_bound",
                 "printed", "readable")

    def __init__(self, printed, label="", gender="", age_class="",
                 weight_kg="", weight_bound="", readable=True):
        self.printed = printed
        self.label = label or printed
        self.gender = gender
        self.age_class = age_class
        self.weight_kg = weight_kg
        self.weight_bound = weight_bound
        self.readable = readable


def _kg(text):
    text = str(text).replace(",", ".")
    return text.rstrip("0").rstrip(".") if "." in text else text


def read_class(printed, report=None):
    """A class code -> _Class, or None where the text is not a class at all.

    A figure no savate class could carry is not corrected and not dropped: the
    code is kept verbatim as the category and the weight is left empty, so the
    row still says who fought whom and never says a weight nobody printed.
    """
    printed = " ".join(str(printed or "").split())
    found = _CLASS.match(printed)
    if not found:
        return None
    age_letter, sex, sign, low, high = found.groups()
    gender = {"F": "Women", "M": "Men"}.get((sex or "").upper(), "")
    age = {"J": "Junior", "S": "Senior", "V": "Veteran"}.get(
        (age_letter or "").upper(), "")

    # A band "60-65 kg" is the class ending at its upper figure.
    kilos = _kg(high or low)
    try:
        figure = float(kilos)
    except ValueError:
        figure = 0.0
    if not (_MIN_KG <= figure <= _MAX_KG):
        if report is not None:
            report.notes.setdefault("unreadable_classes", [])
            if printed not in report.notes["unreadable_classes"]:
                report.notes["unreadable_classes"].append(printed)
        return _Class(printed, label=printed, gender=gender, age_class=age,
                      readable=False)

    bound = "over" if sign in ("+",) else "under"
    if not sign and report is not None:
        report.notes.setdefault("unsigned_classes", [])
        if printed not in report.notes["unsigned_classes"]:
            report.notes["unsigned_classes"].append(printed)
    words = [w for w in (age, gender) if w]
    sigil = "+" if bound == "over" else "-"
    label = (f"{' '.join(words)} {sigil}{kilos} kg" if words
             else f"{sigil}{kilos} kg")
    return _Class(printed, label=label, gender=gender, age_class=age,
                  weight_kg=kilos, weight_bound=bound)


# ---- the three sentence shapes ---------------------------------------------

_BOUT_LINE = re.compile(
    r"^(?:(?P<cls>[A-Za-z]{0,2}\s*[-+−]?\s*\d{2,3}(?:\s*[-–]\s*\d{2,3})?\s*"
    r"(?:kgs?)?)\s*[:\-–]\s*)?"
    r"(?P<red>[^()]{3,60}?)\s*\((?P<red_nat>[^()]{2,40})\)\s*"
    rf"{_BEAT}\s*"
    r"(?P<blue>[^()]{3,60}?)\s*\((?P<blue_nat>[^()]{2,40})\)"
    r"\s*(?P<tail>.*)$", re.I)

_WINNER_LINE = re.compile(
    r"^(?P<cls>[A-Za-z]{0,2}\s*[-+−]?\s*\d{2,3}(?:\s*[-–]\s*\d{2,3})?\s*"
    r"(?:kgs?)?)\s*[:\-–]?\s+(?P<body>.+?)\s*"
    r"(?:winner|vainqueur|gagnant)\s*[:\-–]\s*(?P<winner>.+?)\s*$", re.I)

# A tail that names a month or a year is naming another occasion, not this one.
_ANOTHER_OCCASION = re.compile(
    r"\b(?:" + "|".join(_MONTHS) + r")\b|\b(?:19|20)\d{2}\b", re.I)


def _pairs(body):
    """[(name, nation)] from 'A - ITALIE- B - FRANCE'.

    Split on the hyphens, then walk: a piece that resolves to a nation closes
    the competitor before it. Pieces that resolve to nothing are rejoined with
    their hyphen, so Jean-Pierre stays one person.
    """
    out, buffer = [], []
    for piece in re.split(r"\s*[-–]\s*", body):
        piece = piece.strip()
        if not piece:
            continue
        if display.country(piece).known and buffer:
            out.append(("-".join(buffer).strip(), piece))
            buffer = []
        else:
            buffer.append(piece)
    if buffer:
        out.append(("-".join(buffer).strip(), ""))
    return out


def _scope_claims(headline, lines):
    """(what the headline calls this competition, what its sentences do).

    Only a sentence that names a competition is asked what scope it claims -
    "France was successful" is a result, not a claim about the level.
    """
    claimed = set()
    for line in lines:
        if re.search(r"championship|championnat|\bcup\b|\bcoupe\b", line, re.I):
            found = competition.scope(line)
            if found:
                claimed.add(found)
    from_headline = competition.scope(headline)
    others = sorted(claimed - {from_headline}) if from_headline else []
    return from_headline, others


def _level(headline, lines, meta, classified, report):
    """The scope the document states, or "" where it states two.

    A page headed "European Championship" that opens "The Combat World
    Championship was held…" has not said which it is. Taking the headline would
    store a level the same document contradicts, so nothing is stored and the
    disagreement is reported. A manifest that declares a level still wins - a
    human resolving this in writing is a different thing from a parser guessing.
    """
    from_headline, others = _scope_claims(headline, lines)
    report.notes["scope_claims"] = sorted({s for s in [from_headline] + others if s})
    if not others:
        return meta.get("level") or classified.get("level", "")
    said = ", ".join(others)
    if meta.get("level"):
        report.problem(
            f"the headline calls this a {from_headline} competition and the "
            f"article body calls it {said}; the manifest declares "
            f"{meta['level']}, which is kept")
        return meta["level"]
    report.problem(
        f"the headline calls this a {from_headline} competition and the "
        f"article body calls it {said}; the document does not settle which, so "
        f"the level is left unstated")
    return ""


def _format(headline, lines, meta, classified, report):
    """What was contested, except where the document names something the
    vocabulary has no word for.

    "Qualifying Tournament of the European Savate Combat Championships" is a
    qualifying tournament. `competition.FORMATS` has no value for one, and the
    word "Championships" in that title belongs to the competition this event
    qualifies *for*. Reading it as a championship would file a qualifier beside
    the championship itself, so it is left empty and reported.
    """
    stated = meta.get("format") or classified.get("format", "")
    if not (_QUALIFYING.search(headline or "") or
            any(_QUALIFYING.search(line) for line in lines)):
        return stated
    report.notes["calls_itself"] = "a qualifying tournament"
    if meta.get("format"):
        report.problem(
            f"the document calls this a qualifying tournament; the manifest "
            f"declares the format {meta['format']}, which is kept")
        return meta["format"]
    report.problem(
        "the document calls this a qualifying tournament, and the format "
        "vocabulary (" + ", ".join(competition.FORMATS) + ") has no value for "
        "one; the format is left unstated rather than filed as the "
        "championship this event qualifies for")
    return ""


def _medal_provenance(placings, rank_words, report):
    """Say where the medal column came from, because it is not the document.

    These pages print "Champion" and "Vice-champion" - finishing positions, and
    on a qualifying tournament's page no medal is mentioned anywhere. The column
    is nonetheless filled from `schema.MEDALS`, because `schema.check_placing`
    refuses a ranked row whose medal does not match its rank. That is the
    archive's mapping and not a fact this document states, so it is reported.
    """
    if not placings:
        return
    printed = sorted({word for word in rank_words if _MEDAL_WORD.search(word)})
    unprinted = sorted({word for word in rank_words
                        if not _MEDAL_WORD.search(word)})
    report.notes["rank_words"] = sorted(set(rank_words))
    if not unprinted:
        report.notes["medal_from"] = "the document's own word"
        return
    report.notes["medal_from"] = "schema.MEDALS, the archive's rank -> medal map"
    report.problem(
        "the document states finishing positions (" + ", ".join(unprinted) +
        ") and never a medal; the medal column holds the archive's rank -> "
        "medal mapping, which schema.check_placing requires of every ranked "
        "row - it is not a fact this document states")


def read(source, slug, meta=None, **options):
    from savate import sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    note_document(source, report)
    page = sources.text(source)
    markup, had_marker = _article(page)
    if not had_marker:
        report.problem("no itemprop=\"articleBody\" on the page; the whole "
                       "document was read, which may pick up page furniture")
    lines = _lines(markup)
    report.read = len(lines)

    headline = _headline(page)
    if not headline:
        report.problem("the page prints no headline, so what this competition "
                       "is called, and its level, format and year, are read "
                       "from the article body or from the manifest and never "
                       "from the URL")
    # Only the printed headline is classified. The slug is the URL's wording,
    # not the document's, and `competition.classify` will read a scope off a
    # hostname if it is given one - so it is not given one.
    classified = competition.classify(headline, "", meta)
    year = str(meta.get("year") or classified.get("year") or "").strip()
    year_from = "manifest" if meta.get("year") else ("headline" if year else "")
    if not year:
        body_year = re.search(r"\b(19[89]\d|20[0-4]\d)\b", " ".join(lines))
        if body_year:
            year, year_from = body_year.group(1), "article body"

    level = _level(headline, lines, meta, classified, report)
    fmt = _format(headline, lines, meta, classified, report)

    tournament = Tournament(
        slug=slug,
        name=meta.get("name") or headline,
        discipline=meta.get("discipline") or classified.get("discipline", ""),
        level=level,
        format=fmt,
        age_class=meta.get("age_class") or classified.get("age_class", ""),
        year=year,
        country=meta.get("country", ""),
        source=source, adapter=NAME,
    )

    bouts, placings = [], []
    rank_words = []           # the words this page called its placings by
    current = None            # the class heading in force
    occasion = ("", "")       # (ISO date, venue) of the subheading in force
    venues, dates = [], []
    demos = other_sport = 0
    skipped = []

    def note_skip(why, line):
        skipped.append(f"{why}: {line}")
        report.problem(f"{why}: {line}")

    for line in lines:
        if _OTHER_SPORT.search(line):
            other_sport += 1
            note_skip("not savate - another sport on the same page", line)
            current = None
            continue
        if _DEMO.search(line):
            demos += 1
            note_skip("a demonstration has no result and is not a bout", line)
            continue

        # 1. "M-65kg: A (FRA) won against B (CRO)"
        found = _BOUT_LINE.match(line)
        if found:
            _bout_line(found, line, slug, current, occasion, bouts, report,
                       note_skip)
            continue

        # 2. "F60 A - ITALIE- B - FRANCE  Winner: A"
        found = _WINNER_LINE.match(line)
        if found:
            _winner_line(found, line, slug, occasion, bouts, report, note_skip)
            continue

        # 3. "Champion : PLACE Lorenzo FRANCE", under a class heading
        found = _RANK_LINE.match(line)
        if found and current is not None:
            rank = _rank_of(found.group(1))
            if rank:
                before = len(placings)
                _placing_line(rank, found.group(2), line, slug, current,
                              placings, report, note_skip)
                if len(placings) > before:
                    rank_words.append(" ".join(found.group(1).split()))
                continue

        # 4. a class heading on its own line
        klass = read_class(line, report)
        if klass is not None:
            current = klass
            continue

        # 5. "8th October, Morbihan"
        when = _OCCASION.match(line)
        if when and when.group(2).lower() in _MONTHS:
            day, month, where = when.groups()
            iso = (f"{year}-{_MONTHS[month.lower()]:02d}-{int(day):02d}"
                   if year else "")
            venue = " ".join(where.split()).strip(" .")
            occasion = (iso, venue)
            if venue and venue not in venues:
                venues.append(venue)
            if iso and iso not in dates:
                dates.append(iso)
            current = None
            continue

        # anything else is prose.

    _finish_tournament(tournament, dates, venues, report)

    _medal_provenance(placings, rank_words, report)
    if any(row.gender for row in bouts + placings):
        report.notes["gender_from"] = ("the letter in the printed class code: "
                                       "M -> Men, F -> Women")

    report.notes.update({
        "bouts": len(bouts), "placings": len(placings),
        "demonstrations_excluded": demos,
        "other_sport_rows_excluded": other_sport,
        "lines_skipped": skipped,
        "venues": venues, "dates": dates,
        "year_from": year_from,
        "headline": headline,
    })
    for code in report.notes.get("unreadable_classes", []):
        report.problem(
            f"class code {code!r} is not a savate weight class and the "
            f"document does not say what it stands for; its rows carry the "
            f"code as printed and no weight")
    if report.notes.get("unsigned_classes"):
        report.problem(
            "class code(s) " + ", ".join(report.notes["unsigned_classes"]) +
            " print no sign; read as the class under that weight, which is how "
            "this archive reads every unsigned code - the page does not say so")
    if not bouts and not placings:
        report.problem("no results read - this may not be a results article")
    _cross_check(bouts, placings, report)
    return tournament, bouts + placings, report


def _bout_line(found, line, slug, current, occasion, bouts, report, note_skip):
    """One 'A (FRA) won against B (CRO)' sentence."""
    tail = (found.group("tail") or "").strip(" .;,")
    if tail and _ANOTHER_OCCASION.search(tail):
        note_skip("names a date or place of its own, so it is not part of "
                  "this competition and is left for a human to file", line)
        return
    red, why = _person(found.group("red"))
    blue, why_blue = _person(found.group("blue"))
    if not red or not blue:
        note_skip(f"a fighter could not be read ({why or why_blue})", line)
        return
    if display.fold(red) == display.fold(blue):
        note_skip("the same person on both sides of the bout", line)
        return

    klass = read_class(found.group("cls"), report) if found.group("cls") else None
    klass = klass or current
    if klass is None:
        report.problem(f"no weight class printed for this bout: {line}")
    if tail:
        report.problem(f"text after the bout was not read: {tail!r} ({line})")

    index = len(bouts) + 1
    bouts.append(Bout(
        tournament=slug,
        bout_id=f"{slug}-b{index:03d}",
        date=occasion[0],
        category=klass.label if klass else "",
        gender=klass.gender if klass else "",
        age_class=klass.age_class if klass else "",
        weight_kg=klass.weight_kg if klass else "",
        weight_bound=klass.weight_bound if klass else "",
        # The sentence's own order, and nothing more. The page never says who
        # stood in which corner, so winner_corner is left empty.
        red=red, red_country=_country(found.group("red_nat")),
        blue=blue, blue_country=_country(found.group("blue_nat")),
        winner=red, loser=blue, winner_corner="",
        # The page says who won and never how. "" is a real decision here.
        decision="", status="decided", result_source="reported",
    ))


def _winner_line(found, line, slug, occasion, bouts, report, note_skip):
    """One 'A - ITALIE- B - FRANCE  Winner: A' line."""
    pairs = _pairs(found.group("body"))
    people = []
    for raw, nation in pairs:
        who, _why = _person(raw)
        if who:
            people.append((who, nation))
    if len(people) != 2:
        note_skip(f"{len(people)} fighter(s) readable where a bout needs two",
                  line)
        return
    if display.fold(people[0][0]) == display.fold(people[1][0]):
        note_skip("the same person on both sides of the bout", line)
        return

    klass = read_class(found.group("cls"), report)
    stated = " ".join((found.group("winner") or "").split()).strip(" .;,")
    winner = next((p[0] for p in people if display.fold(p[0]) == display.fold(stated)),
                  "")
    decided = bool(winner)
    if not decided:
        report.problem(
            f"the stated winner {stated!r} is neither fighter, so the bout is "
            f"stored unresolved: {line}")
    loser = ""
    if decided:
        loser = next(p[0] for p in people if p[0] != winner)

    index = len(bouts) + 1
    bouts.append(Bout(
        tournament=slug,
        bout_id=f"{slug}-b{index:03d}",
        date=occasion[0],
        category=klass.label if klass else "",
        gender=klass.gender if klass else "",
        age_class=klass.age_class if klass else "",
        weight_kg=klass.weight_kg if klass else "",
        weight_bound=klass.weight_bound if klass else "",
        red=people[0][0], red_country=_country(people[0][1]),
        blue=people[1][0], blue_country=_country(people[1][1]),
        winner=winner, loser=loser, winner_corner="",
        decision="", status="decided" if decided else "unresolved",
        result_source="reported" if decided else "",
    ))


def _placing_line(rank, body, line, slug, klass, placings, report, note_skip):
    """One 'Champion : PLACE Lorenzo FRANCE' line under a class heading."""
    if _NOT_AWARDED.search(body):
        report.problem(f"{klass.label}: the title was not awarded ({line})")
        return
    name, nation = split_nation(body)
    who, why = _person(name)
    if not who:
        note_skip(f"a competitor could not be read ({why})", line)
        return
    placings.append(Placing(
        tournament=slug,
        placing_id=f"{slug}-p{len(placings) + 1:03d}",
        category=klass.label, gender=klass.gender, age_class=klass.age_class,
        weight_kg=klass.weight_kg, weight_bound=klass.weight_bound,
        # Not a reading: the document prints a position, and MEDALS is the
        # archive's own mapping from one to the other. _medal_provenance says
        # so on every read that fills this column.
        rank=str(rank), medal=MEDALS.get(str(rank), ""),
        fighter=who, country=_country(nation) if nation else "",
        result_source="reported",
    ))


def _finish_tournament(tournament, dates, venues, report):
    if dates:
        tournament.start_date = min(dates)
        tournament.end_date = max(dates)
        if not tournament.year:
            tournament.year = tournament.start_date[:4]
    # One competition, two venues, and one city field. Writing either of them
    # in would say the whole event happened there, so neither is written.
    if len(venues) == 1:
        tournament.city = venues[0]
    elif len(venues) > 1:
        report.problem(
            "the article spreads this competition over " +
            ", ".join(venues) + "; the tournament holds one city, so it is "
            "left empty and the venues are in the report")


def _cross_check(bouts, placings, report):
    """The things that would be wrong without ever raising.

    None of these change a row. They put in front of a human the disagreements
    the page itself contains, which is the only place they can be resolved.
    What the document disagrees with itself about - its level, its format - is
    read and withheld in `_level` and `_format`, before the tournament exists.
    """
    # A page that labels some classes by age and not others is a page that has
    # not said what the unlabelled ones are.
    rows = list(bouts) + list(placings)
    aged = {bool(r.age_class) for r in rows if r.category}
    if len(aged) > 1:
        bare = sorted({r.category for r in rows if r.category and not r.age_class})
        report.problem(
            "some classes state an age class and these do not: " +
            ", ".join(bare) + "; their age class is left empty")

    # Nobody is in two weight classes of one competition, and nobody fights
    # themselves. If either happens the page was mis-segmented.
    where = {}
    for bout in bouts:
        for who in (bout.red, bout.blue):
            where.setdefault(display.fold(who), set()).add(bout.category)
    for placing in placings:
        where.setdefault(display.fold(placing.fighter), set()).add(placing.category)
    spread = sorted(k for k, cats in where.items() if len(cats) > 1)
    if spread:
        report.problem(
            f"{len(spread)} competitor(s) read into more than one weight "
            f"class, which one competition cannot do: {', '.join(spread)}")
