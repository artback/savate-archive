"""The GBSF's British championship pages: a category, then one or two names.

Great Britain has published its national titles on savate.org.uk since 2012, and
has changed how it prints them almost every year. Across fourteen seasons the
same competition appears as a WordPress table, as three-line prose blocks, as
one line per class, as two separate lists joined only by a class code, and as a
category heading with the name on the next line behind an en-dash. The federation
never announced a format; it simply typed the results differently each time.

Underneath, every one of those is the same sentence:

    <category>  <champion>  [<vice-champion>]

so this reads them as one grammar with optional parts rather than as five
parsers. A line is a category when it opens with something that can only be a
weight class - a class code (M75, F60), a printed bound (<56kg, 85kg+), or a
band (70-75kg) - optionally behind a gender word and an age range. Whatever
follows on that line, on the lines below it, or in the next two table cells is a
person. The five shapes then differ only in which of those optional parts is
present:

    2025, 2024   a real <table>:  Age | Category | Champion | Vice Champion
    2019, 2017   category line, then "Champion: X" / "Vice-Champion: Y"
    2018         both medallists on the category's own line
    2015         every champion, then every vice-champion, joined by class code
    2016, 2013   one line per class, champion only
    2012         a category line, then the name behind an en-dash

WHAT THESE DOCUMENTS DO NOT CONTAIN, and what this adapter will therefore never
produce.

*No bouts.* Every British page is a podium. Not one of them prints who fought
whom, so no Bout is returned from any of them - only Placings. A final can be
inferred from a champion and a vice-champion in most sports; it cannot be
inferred here, because the GBSF ran classes with three and four entrants and a
vice-champion is not necessarily the person the champion beat.

*No bronze.* The GBSF publishes gold and silver and stops. Savate awards two
bronzes and this archive stores both where a document names them; these
documents name none, so ranks 1 and 2 are all that is stored. The absence is
reported on every read rather than filled in.

*No nationality, and no country either.* These are national championships,
which makes it tempting to stamp every competitor "Great Britain". The pages do
not say it - the 2025 women's champion is listed out of a club called Formosa -
so no placing carries a country. Neither does the tournament. The phrase "Great
Britain Savate Federation" is on every capture, but only ever in the site's own
furniture: the <title> suffix, the RSS link titles, the logo's aria-label and
the footer's copyright line. That is the publisher's name, not a fact about
where the competition was held - and the 2019 junior post says in its first
sentence that Savate Northern Ireland hosted it, which is in the UK and not in
Great Britain. A masthead is not a dateline, so the country is left empty.

THE SOURCE DEFECTS THIS CARRIES RATHER THAN CORRECTS. Four of the ten pages
print something nobody could have meant:

    2018  "Male 80-65kg"      a band running downwards, printed between 75-80
                              and 85+, so plainly 80-85
    2012  "Female 52.56kg"    a full stop where the band's hyphen belongs
    2019  "Female yrs, 22-24kg"  the age range simply missing
    2013  the post's title says July, its body says 30th January

Each is reported and none is repaired. The category string keeps the federation's
own wording, and where the printed class cannot be read as a bound the weight is
left empty rather than guessed - a class filed under 65 kg that was fought at 85
is worse than a class filed under nothing.

The same holds for one class the site has never explained:

    2025, 2024, 2017  "M150"      a code above every weight savate fights

M150 sits at the top of the men's ladder on all three pages and is very likely
the open class, but "likely" is not "printed": the word "open" appears on none
of them, and if the 150 were ever pounds it would be 68 kg, two classes down
rather than one up. So it is read like the bands above and not like a weight -
the class keeps the federation's own token as its label, and carries neither a
weight nor a bound.

CANNE DE COMBAT IS NOT SAVATE. The 2019 senior page opens with four canne
results under their own heading, before the savate ones. They are a different
sport with a different federation ladder, and filing them here would put two
cannists into savate's competitive record. Sport headings are tracked and
everything under a non-savate one is dropped and counted.
"""

import html
import re

from savate import display
from savate import normalize as norm
from savate.schema import MEDALS, Placing, Report, Tournament

NAME = "british_champions"
DESCRIPTION = "GBSF British championship pages (podium: champion, vice-champion)"

# ---- the page ----------------------------------------------------------
#
# Every capture of savate.org.uk, on both the Drupal-era and the WordPress-era
# theme, wraps the post in entry-content. Reading only that is what keeps the
# site's own furniture out of the results: the nav, the "Coming up" teasers a
# 2022 capture of a 2017 post carries, and the footer are all outside it.

_ENTRY = re.compile(r'<div\b[^>]*class="[^"]*\bentry-content\b[^"]*"[^>]*>', re.I)
_DIV = re.compile(r"<(/?)div\b", re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
_ROW = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_CELL = re.compile(r"<t([dh])\b[^>]*>(.*?)</t\1>", re.S | re.I)
_SCRIPT = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BREAK = re.compile(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|td|th|blockquote)>")
_TAG = re.compile(r"<[^>]+>")

# Dashes that a word processor produced and a parser must treat as a hyphen.
# The replacement is one character for one, so a span found in the flattened
# line is the same span in the printed one and a name is never rewritten.
_DASHES = {ord(c): "-" for c in "‐‑‒–—―−"}


def _plain(fragment):
    """The visible lines of an HTML fragment, in the order it prints them."""
    text = _SCRIPT.sub(" ", fragment or "")
    text = _BREAK.sub("\n", text)
    # Tags go before entities, so an escaped "&lt;56kg" survives as text
    # rather than turning into something that looks like markup.
    text = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return [line for line in lines if line]


def _entry(page):
    """The post body, or the whole page where the theme does not mark one."""
    found = _ENTRY.search(page)
    if not found:
        return page
    depth, start = 1, found.end()
    for tag in _DIV.finditer(page, start):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return page[start:tag.start()]
    return page[start:]


# ---- the grammar -------------------------------------------------------

_GENDERS = {"male": "Men", "men": "Men", "boys": "Men", "boy": "Men",
            "female": "Women", "women": "Women", "girls": "Women",
            "girl": "Women", "m": "Men", "f": "Women"}

_GENDER_WORD = re.compile(r"^(male|female|men|women|boys?|girls?)\b[\s,:.]*", re.I)

# "10-11yrs,", "8-10 yrs,", "14-17yr" - and the 2019 junior page's bare "yrs,",
# which is the same token with the ages missing.
_AGE_TOKEN = re.compile(r"^(?:(\d{1,2})\s*-\s*(\d{1,2})\s*)?yrs?\.?[\s,:]*", re.I)

# Every way these pages have printed a weight class, in one token:
#   M75  F60  M150  M85+  <56kg  F<56kg  M85+kg  85kg+  70-75kg  52.56kg
_WEIGHT_TOKEN = re.compile(
    r"^(?:(?P<code>[FM])\s*)?"
    r"(?P<under><|≤)?\s*"
    r"(?P<pre>\+)?\s*"
    r"(?P<low>\d{2,3})"
    r"(?:\s*(?P<sep>[-.])\s*(?P<high>\d{2,3}))?"
    r"\s*(?P<mid>\+)?\s*"
    r"(?P<unit>kgs?|kilos?)?"
    r"\s*(?P<post>\+)?",
    re.I)

# Only these two words. "Winner" is what the same pages call the holder of the
# Phil Read Trophy and the Martin Ross Award, which are not weight-class titles.
_ROLE = re.compile(
    r"^(?:(?P<gender>male|female|men|women|boys?|girls?)\s+)?"
    r"(?P<role>vice[\s-]?champion|champion)"
    r"\s*[:.-]?\s*(?P<who>.+)$", re.I)

# The 2018 shape: both medallists on the category's own line, "Champion" used
# as a bare prefix and the two separated by the same comma a name could hold.
_PAIR = re.compile(
    r"^champion\b\s*[:.-]?\s*(?P<gold>.+?)\s*[,;]?\s*"
    r"\bvice[\s-]?champion\b\s*[:.-]?\s*(?P<silver>.+)$", re.I)
# The 2012 shape: the name on the line below, behind a dash.
_DASH_LINE = re.compile(r"^[-*•]\s*(?P<who>.+)$")

# Sport headings. Canne de combat, baton, chausson and savate forme are
# different sports; anything printed under one of them is not savate's.
_OTHER_SPORT = re.compile(
    r"^(canne(\s+de\s+combat)?|pr[eé]?[-\s]?canne|b[aâ]ton|"
    r"chausson|savate\s+forme|forme)\s*:?\s*$", re.I)
_SAVATE = re.compile(r"^savate(\s+(assaut|combat|bf|boxe))?\s*:?\s*$", re.I)
_OTHER_SPORT_WORD = re.compile(r"canne|b[aâ]ton|chausson|savate\s+forme", re.I)

# Age sections. "SENIORS:" and "JUNIORS:" on the 2018 page; "JUNIOR CHAMPIONS
# 2019 ARE:" on the 2019 junior one.
_AGE_WORDS = r"seniors?|juniors?|cadets?|benjamins?|minimes?|poussins?|v[eé]t[eé]rans?"
_AGE_SECTION = re.compile(rf"^({_AGE_WORDS})\s*:?\s*$", re.I)
_AGE_HEADING = re.compile(rf"^({_AGE_WORDS})\s+champions\b.*$", re.I)
_GENDER_SECTION = re.compile(r"^(male|female|men|women|boys?|girls?)\s*:?\s*$", re.I)

# The 2015 page prints its champions and its vice-champions as two lists. The
# second list is introduced, and nothing else on the line says which medal its
# names won - so the heading is the only thing that can say it.
# The plural is what separates a heading from a result: "Vice-Champions" is
# the list's title, "Vice-Champion: Louisa Furniss" is a person in it.
_SILVER_BLOCK = re.compile(
    r"^(and\s+)?(the\s+|our\s+|congratulations\s+to\s+the\s+)?"
    r"vice[\s-]?champions\b[^:]*:?\s*$", re.I)
_GOLD_BLOCK = re.compile(
    r"^(and\s+)?(congratulations\s+to\s+the\s+|the\s+new\s+\d{4}\s+|"
    r"our\s+\d{4}\s+)?champions\b(?!.*vice)[^:]*:?\s*$", re.I)

# A bout put on to entertain the crowd has no result and is not a bout.
_DEMO = re.compile(r"\bdemo\b|demonstration|exhibition|display|\bshowcase\b", re.I)

# A class code's number is read as kilograms - M75 is the men's 75 kg class -
# and that reading stops where the number stops being a weight anybody could
# make. Savate's heaviest class is +85 kg, so a code at or above this is not a
# weight, and none of these pages says what it is instead.
_NOT_A_WEIGHT = 90

_MONTHS = ("january february march april may june july august september "
           "october november december").split()
_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")\b"
    r"(?:\s*,?\s*(\d{4}))?", re.I)
_MONTH_WORD = re.compile(r"\b(" + "|".join(_MONTHS) + r")\b", re.I)
_YEAR = re.compile(r"\b(20\d\d)\b")


class _Class:
    """One weight class as a page printed it, and as the archive files it."""

    __slots__ = ("printed", "token", "gender", "age_class", "band", "kilos",
                 "bound")

    def __init__(self, printed, token="", gender="", age_class="", band="",
                 kilos="", bound=""):
        self.printed = printed        # the whole head, as the page set it
        self.token = token or printed  # just the class, for the label
        self.gender = gender
        self.age_class = age_class
        self.band = band
        self.kilos = kilos
        self.bound = bound

    @property
    def label(self):
        parts = [p for p in (self.age_class, self.gender, self.band) if p]
        if self.kilos:
            parts.append(("+" if self.bound == "over" else "-")
                         + self.kilos + " kg")
        else:
            # The printed class could not be read as a bound. Keeping the
            # federation's own wording is what stops the defect disappearing -
            # and is the only label that is still the document's own once the
            # weight has gone.
            parts.append(self.token)
        return " ".join(parts).strip() or self.printed


def _weight(token):
    """(kilos, bound, gender, what to report) for one printed class.

    Three of these pages print a class nobody could have meant - a band running
    downwards, a full stop where the band's hyphen belongs, and a code above
    every weight the sport fights. None is repaired and none is guessed at. The
    weight comes back empty, the bound comes back empty with it, the class keeps
    the federation's own wording, and the caller says so out loud: a class filed
    under 65 kg that was fought at 85 is worse than a class filed under no
    weight at all, and a class filed as "open" that the page never called open
    is a reader's conclusion wearing the archive's clothes.
    """
    code = (token.group("code") or "").upper()
    gender = _GENDERS.get(code.lower(), "") if code else ""
    plus = bool(token.group("pre") or token.group("mid") or token.group("post"))
    under = bool(token.group("under"))
    low, high = token.group("low"), token.group("high")

    if plus:
        return low, "over", gender, ""
    if high is not None and token.group("sep") == ".":
        return ("", "", gender,
                "a full stop stands where the band's separator belongs, so no "
                "weight class was read from it")
    if high is not None:
        if int(high) <= int(low):
            return ("", "", gender,
                    "the band's lower figure is not below its upper, so no "
                    "weight class was read from it")
        # "60-65 kg" is the class ending at its upper figure.
        return high, "under", gender, ""
    if not under and int(low) >= _NOT_A_WEIGHT:
        # Almost certainly the open class: it is printed at the top of the
        # men's ladder, above M85. Almost is not read. The page prints no
        # "open" and no bound, so neither is stored and the label stays the
        # code the federation typed.
        return ("", "", gender,
                "the code is above every weight savate fights, and no document "
                "on the site says what it stands for, so no weight class and "
                "no bound were read from it")
    return low, "under", gender, ""


def _head(line, report):
    """(_Class, rest of the line, where that rest starts in the line)."""
    rest, gender, band, missing_ages = line, "", "", False

    found = _GENDER_WORD.match(rest)
    if found:
        gender = _GENDERS.get(found.group(1).lower(), "")
        rest = rest[found.end():]

    found = _AGE_TOKEN.match(rest)
    if found:
        if found.group(1) and found.group(2):
            band = f"{found.group(1)}-{found.group(2)} yrs"
        else:
            missing_ages = True
        rest = rest[found.end():]

    token = _WEIGHT_TOKEN.match(rest)
    if not token:
        return None, line, 0
    # A bare number is a number. Only a class code, a printed unit or a bound
    # makes it a weight class, which is what keeps prose out of the results.
    if not (token.group("code") or token.group("unit") or token.group("under")
            or token.group("pre") or token.group("mid") or token.group("post")):
        return None, line, 0

    kilos, bound, code_gender, why = _weight(token)
    at = len(line) - len(rest)
    printed = " ".join(line[:at + token.end()].split())
    class_token = " ".join(token.group(0).split())
    if why:
        report.problem(f"{printed}: {why}")
    if missing_ages:
        report.problem(f"{printed!r}: the age range is missing from the source, "
                       f"so the class is filed without one")

    at += token.end()
    rest = line[at:]
    trimmed = rest.lstrip(" ,:;.")
    at += len(rest) - len(trimmed)
    rest = trimmed
    # "65-70kg Male: Tim Campbell" - the 2013 page puts the gender after the
    # class instead of in front of it.
    trailing = _GENDER_WORD.match(rest)
    if trailing and not gender and not code_gender:
        gender = _GENDERS.get(trailing.group(1).lower(), "")
        at += trailing.end()
        rest = rest[trailing.end():]

    return _Class(printed, class_token, gender or code_gender, "", band, kilos,
                  bound), rest, at


def _person(raw, report, where):
    """(name, club) read off one printed person, or (None, "")."""
    text = " ".join(str(raw or "").split()).strip(" ,;:.-")
    if not text:
        return None, ""
    if _DEMO.search(text):
        return None, ""

    club = ""
    found = re.match(r"^(?P<name>.+?)\s*\((?P<club>[^()]*)\)\s*$", text)
    if found:
        club = found.group("club").strip()
        text = found.group("name").strip()
    elif text.count(",") == 1:
        # The table cells read "<name>, <club>". A name holding more than one
        # comma is not split at all: a club invented out of a middle name is
        # worse than a club the archive does not have.
        left, right = (part.strip() for part in text.split(","))
        if left and right and len(right.split()) <= 5:
            text, club = left, right
    elif "," in text:
        report.problem(f"{where}: {text!r} holds more than one comma, so the "
                       f"club was not split off the name")

    person = display.name(text)
    if not person.usable:
        report.problem(f"{where}: {text!r} is not a competitor name "
                       f"({person.reason})")
        return None, ""
    return person.text, display.club(club) if club else ""


def _emit_names(weight_class, rest, at, printed, add, default_rank):
    """Read whatever a category line carries after its class. True if it did.

    The three things that can follow are both medallists ("Champion X,
    Vice-Champion Y"), one of them by name, or a bare name whose medal only the
    list it sits in can say.
    """
    pair = _PAIR.match(rest)
    if pair:
        add(weight_class, 1,
            printed[at + pair.start("gold"):at + pair.end("gold")],
            weight_class.printed)
        add(weight_class, 2,
            printed[at + pair.start("silver"):at + pair.end("silver")],
            weight_class.printed)
        return True
    role = _ROLE.match(rest)
    if role:
        rank = 2 if role.group("role").lower().startswith("vice") else 1
        add(weight_class, rank,
            printed[at + role.start("who"):at + role.end("who")],
            weight_class.printed)
        return True
    # The 2013, 2015 and 2016 shape: the class and one name, nothing else.
    # Which medal it is is not on the line - it is the list the line sits in.
    # A person's name opens with a capital on every one of these pages, and
    # requiring one is what stops a sentence that happens to follow a weight
    # from being filed as a competitor.
    if re.match(r"[A-Z\u00c0-\u00dd]", rest):
        add(weight_class, default_rank, printed[at:], weight_class.printed)
        return True
    return False


# ---- reading -----------------------------------------------------------

def _tournament(source, slug, meta, page, body, report):
    meta = meta or {}
    head = _plain(_H1.search(page).group(1)) if _H1.search(page) else []
    title = _plain(_TITLE.search(page).group(1)) if _TITLE.search(page) else []
    heading = head[0] if head else (title[0] if title else "")

    text = " ".join(body)
    discipline = meta.get("discipline", "")
    if not discipline and re.search(r"\bassaut\b", heading + " " + text, re.I):
        discipline = "assaut"

    age = ""
    stated = {w.lower().rstrip("s") for w in re.findall(_AGE_WORDS, heading, re.I)}
    if len(stated) == 1:
        age = stated.pop().title()

    year = meta.get("year", "")
    if not year:
        found = _YEAR.search(heading) or _YEAR.search(text)
        year = found.group(1) if found else ""

    # No country is read from the page. "Great Britain Savate Federation" is on
    # every capture, and on every one of them it is the site's furniture - the
    # <title> suffix, the RSS link titles, the logo's aria-label, the footer's
    # copyright - never the post. That names the publisher, not the venue, and
    # the 2019 junior post opens by saying Savate Northern Ireland hosted it:
    # the UK, not Great Britain. Whatever the caller was told, the document
    # states nothing, so nothing is added here.
    country = meta.get("country", "")

    return age, Tournament(
        slug=slug,
        name=meta.get("name") or heading or slug,
        discipline=discipline,
        level=meta.get("level", "national"),
        format=meta.get("format", "championship"),
        age_class=meta.get("age_class", age),
        year=year,
        start_date=meta.get("start_date", "") or _date(heading, body, year, report),
        city=meta.get("city", ""),
        country=country,
        source=str(source), adapter=NAME,
        competition=meta.get("competition", ""),
    ), heading


def _date(heading, body, year, report):
    """The event's date where the page states one, "" where it contradicts itself."""
    found = None
    for line in body[:4]:
        found = _DATE.search(line)
        if found:
            break
    if not found:
        return ""
    day, month, stated_year = found.group(1), found.group(2).lower(), found.group(3)
    when = norm.date(f"{day} {month.title()} {stated_year or year}")
    if not when:
        return ""
    # The 2013 post is titled July and dated 30th January in its own body. One
    # of the two is wrong and the page does not say which, so the archive keeps
    # the disagreement instead of choosing a side.
    titled = _MONTH_WORD.search(heading)
    if titled and titled.group(1).lower() != month:
        report.problem(
            f"the page's title says {titled.group(1).title()} and its body says "
            f"{found.group(0)}; the two disagree, so no date was recorded")
        return ""
    return when


def _table_rows(fragment, report):
    """[(age, category, champion cell, vice cell)] from a champions table."""
    out = []
    for table in _TABLE.findall(fragment):
        rows = _ROW.findall(table)
        columns, body = None, []
        for row in rows:
            cells = [" ".join(_plain(c)) for _tag, c in _CELL.findall(row)]
            if columns is None:
                low = [c.lower() for c in cells]
                if any("champion" in c for c in low):
                    columns = {}
                    for i, c in enumerate(low):
                        if "vice" in c or "runner" in c:
                            columns["silver"] = i
                        elif "champion" in c or "winner" in c:
                            columns.setdefault("gold", i)
                        elif c.startswith("age"):
                            columns["age"] = i
                        elif "categ" in c or "class" in c or "weight" in c:
                            columns["category"] = i
                    continue
                columns = None
            if columns is None:
                continue
            body.append(cells)
        if not columns or "gold" not in columns or "category" not in columns:
            continue
        for cells in body:
            def cell(key):
                i = columns.get(key)
                return cells[i].strip() if i is not None and i < len(cells) else ""
            out.append((cell("age"), cell("category"), cell("gold"),
                        cell("silver")))
    return out


def read(source, slug, meta=None, **options):
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    page = sources.text(source)
    # These are web pages and nothing else. Saying so keeps the adapter from
    # claiming a PDF whose decoded bytes happen to hold a line that reads like
    # a weight class - a probe runs every adapter against every document.
    if not re.search(r"</(p|div|td|tr|li|table|body|h[1-6])>", page, re.I):
        report.problem("this source is not an HTML page, so it was not read")
        return Tournament(slug=slug, name=meta.get("name", slug),
                          source=str(source), adapter=NAME,
                          competition=meta.get("competition", "")), [], report
    body = _plain(_entry(page))
    stated_age, tournament, heading = _tournament(source, slug, meta, page,
                                                  body, report)
    # An age class the page's own title states - "Junior Savate Assaut
    # Championships 2019" - belongs on the rows as much as on the tournament.
    # A page whose title names two ("Senior and Junior") states neither, and
    # its own section headings say which is which further down.
    default_age = meta.get("age_class") or stated_age

    placings = []
    seen = {}
    dropped_other_sport = 0
    dropped_demo = 0
    classes = []

    def add(weight_class, rank, raw, where):
        nonlocal dropped_demo
        if _DEMO.search(str(raw or "")):
            dropped_demo += 1
            report.problem(f"{where}: {raw!r} reads as a demonstration, which "
                           f"has no result and is not stored")
            return
        fighter, club = _person(raw, report, where)
        if not fighter:
            return
        label = weight_class.label
        key = (label, str(rank))
        if key in seen:
            report.problem(f"{label}: a second rank-{rank} was printed "
                           f"({seen[key]} then {fighter}); the later one is kept "
                           f"out of the archive")
            return
        seen[key] = fighter
        if label not in classes:
            classes.append(label)
        placings.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{len(placings) + 1:03d}",
            category=label,
            gender=weight_class.gender,
            age_class=weight_class.age_class,
            weight_kg=weight_class.kilos,
            weight_bound=weight_class.bound,
            rank=str(rank), medal=MEDALS.get(str(rank), ""),
            fighter=fighter,
            # A national championship is not a statement of nationality. The
            # page never prints one, so the placing does not carry one.
            country="",
            club=club,
            result_source="reported",
        ))

    # ---- the table pages -----------------------------------------------
    for age, category, gold, silver in _table_rows(_entry(page), report):
        flat = category.translate(_DASHES)
        weight_class, rest, _at = _head(flat, report)
        if not weight_class:
            report.problem(f"table row {category!r}: not a weight class, so the "
                           f"row was not read")
            continue
        if rest.strip():
            report.problem(f"table row {category!r}: {rest.strip()!r} was left "
                           f"over after the class was read")
        found = _AGE_SECTION.match(age.strip()) if age else None
        weight_class.age_class = (found.group(1).rstrip("sS").title() if found
                                  else default_age)
        if age and not found:
            report.problem(f"table row {category!r}: age {age!r} is not an age "
                           f"class this archive knows, so it was not recorded")
        add(weight_class, 1, gold, f"table row {category!r}")
        if silver:
            add(weight_class, 2, silver, f"table row {category!r}")

    # ---- the prose pages -----------------------------------------------
    table_free = _TABLE.sub(" ", _entry(page))
    sport = "savate"
    section_age = default_age
    carried_gender = ""
    default_rank = 1
    pending = None

    for printed in _plain(table_free):
        line = printed.translate(_DASHES)

        if _OTHER_SPORT.match(line):
            sport = "other"
            pending, carried_gender = None, ""
            continue
        if _SAVATE.match(line):
            sport = "savate"
            pending, carried_gender = None, ""
            continue

        found = _AGE_SECTION.match(line) or _AGE_HEADING.match(line)
        if found:
            section_age = found.group(1).rstrip("sS").title()
            pending, carried_gender = None, ""
            continue
        found = _GENDER_SECTION.match(line)
        if found:
            carried_gender = _GENDERS.get(found.group(1).lower(), "")
            pending = None
            continue
        weight_class, rest, at = _head(line, report)
        if weight_class:
            if sport != "savate":
                dropped_other_sport += 1
                pending = None
                continue
            weight_class.age_class = section_age
            weight_class.gender = weight_class.gender or carried_gender
            if not rest.strip():
                pending = weight_class
                continue
            pending = None
            # Spans are taken from `printed`, the line exactly as the page set
            # it. `line` differs from it only where a dash was flattened, and
            # that swap is one character for one, so the two stay in step.
            if not _emit_names(weight_class, rest, at, printed, add,
                               default_rank):
                report.problem(f"{weight_class.printed}: {rest.strip()!r} does "
                               f"not read as a competitor, so it was not read")
            continue

        role = _ROLE.match(line)
        if role:
            if sport != "savate":
                dropped_other_sport += 1
                continue
            if not pending:
                report.problem(f"{line!r}: a champion with no weight class "
                               f"above it, so it was not read")
                continue
            rank = 2 if role.group("role").lower().startswith("vice") else 1
            add(pending, rank,
                printed[role.start("who"):role.end("who")], pending.printed)
            continue

        dash = _DASH_LINE.match(line)
        if dash and pending:
            if sport != "savate":
                dropped_other_sport += 1
                continue
            add(pending, default_rank,
                printed[dash.start("who"):dash.end("who")], pending.printed)
            continue

        # Tried last, so that a line naming a person is read as that person
        # before it is read as the heading of a list of people.
        if _SILVER_BLOCK.match(line):
            default_rank, pending = 2, None
            continue
        if _GOLD_BLOCK.match(line):
            default_rank, pending = 1, None
            continue

    # ---- what the read has to say --------------------------------------
    report.read = len(body)
    report.notes["categories"] = len(classes)
    report.notes["placings"] = len(placings)
    report.notes["ranks"] = sorted({p.rank for p in placings})
    report.notes["heading"] = heading
    if body:
        report.notes["venue_line"] = body[0]
    if dropped_other_sport:
        report.notes["other_sport_rows_dropped"] = dropped_other_sport
        report.problem(f"{dropped_other_sport} result(s) printed under a "
                       f"non-savate heading (canne de combat and its relatives) "
                       f"were dropped: a different sport")
    # A page can talk about canne de combat without publishing any: the 2012
    # report describes a canne DISPLAY between the bouts. A display has no
    # result and is not a competition, so there is nothing to drop - but the
    # mention is kept where a reader can see it, in the sentence that made it.
    mentions = []
    for line in body:
        if _OTHER_SPORT.match(line.translate(_DASHES)):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if _OTHER_SPORT_WORD.search(sentence):
                mentions.append(sentence.strip())
    if mentions:
        report.notes["other_sport_mentioned"] = mentions
    report.notes["demonstration_rows_dropped"] = dropped_demo
    if not placings:
        report.problem("no podium rows read - this may not be a results page")
        return tournament, placings, report

    solo = [label for label in classes
            if (label, "1") in seen and (label, "2") not in seen]
    if solo:
        report.notes["gold_only_classes"] = solo
    # Savate awards two bronzes. Not one British page prints a third place, so
    # every class here is short two medallists - said out loud on every read so
    # that a reader does not take the podium for a complete one.
    report.problem(
        f"podium only: {len(classes)} class(es), "
        + (f"{len(solo)} of them naming a champion and nobody else, "
           if solo else "")
        + "and no third place anywhere, though savate awards two bronzes. "
          "No bronze is synthesised")
    report.problem("no bouts: the page publishes a podium and never says who "
                   "fought whom")
    return tournament, placings, report
