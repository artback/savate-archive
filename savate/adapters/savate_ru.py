"""The Russian federation's hall-of-fame pages: careers, not competitions.

savate-boxe.ru publishes its record of Russian savate in four pages under
"Зал славы" - the hall of fame. Between them they hold 136 athletes and 251
honours, from the 1991 world championship to 2021, and they are the only thing
this archive has ever found from Russia. They are also, read carefully, not
results documents, and this adapter exists as much to say so as to read them.

WHAT THE PAGES ACTUALLY ARE

Each page is a run of athletes. One athlete is a `div.warrior` holding a name,
a coach, and a small CSS-simulated table - `section.the-css-at-table2`, whose
column header is `display:none` and whose body is a run of `p.tr` paragraphs of
exactly three spans:

    Комба | 2017        | Чемпион мира
    Комба | 2015, 2019  | Вице-чемпион мира
    Ассо  | 2013        | Призер первенства Европы

So a row is one athlete's honour, not one competition's result. The unit the
page is organised by is the person; a Год cell holding two years is the same
honour won twice. The four pages divide the athletes between them by the height
of their best result - champions, youth winners, senior medallists, youth
medallists - and no athlete appears on two of them. That is the decisive fact:
the medallists of any one championship are scattered across all four pages, so
no page, and no combination of a page and a year, holds a podium.

WHY THIS ADAPTER RETURNS NO ROWS

Reading these into Placings would take three inventions, and the archive's first
rule is that it invents nothing.

*The competition.* A row says "world" or "Europe" and a year, and stops. It
names no city, no event and no organiser. The archive already holds most of
those championships from FISav and CESav under their own slugs, with their own
podiums; minting a second tournament per year out of an honours roll would put
two competitions in the table where one was held, and a medal table would count
both.

*The weight class.* 249 of the 251 rows carry none - only the two professional
titles print one. Without it the rows collide in ways a real document cannot:
the 2016 European youth championship alone produces two "Победитель первенства
Европы" rows, which is two golds in one class unless a class nobody printed is
invented to separate them.

*The podium.* Because the pages are partitioned by athlete, a competition read
off any one of them is missing whichever of its medallists were filed elsewhere.
A partial podium stored as a podium reads as a complete one.

None of that makes the register worthless - it is a good identity source, and
its honours are real. It is simply not a competition document, so `read` returns
its parse in the Report, where a human can see it, and returns no rows at all
into the fact tables. The rows are there in `report.notes["honours"]`, one dict
per athlete-honour-year, with everything the page said and nothing it did not.

WHAT IS READ, AND HOW MUCH OF IT IS THE PAGE'S OWN WORD

*Names stay Cyrillic.* "Нарек БАБАДЖАНЯН" is stored exactly as printed. There is
no transliteration here and there must not be one: a romanisation invented at
ingest is a second, wrong name for a person the archive may already hold.

*The parenthesis is a place, never a country.* "(г.Санкт-Петербург)" is a city,
"(Архангельская область)" a region, "(Калужская обл., г.Таруса)" both. Every
athlete on these pages is Russian, and the pages say so nowhere, so the place
goes to the club/city field and the country stays empty.

*The tier words.* Five stems carry the finishing position, in two parallel
ladders that the pages keep strictly apart - the senior one on чемпионат, the
youth one on первенство:

    Чемпион / Чемпионка,   Победитель / Победительница    won it        rank 1
    Вице-чемпион(ка),      Финалист / Финалистка          lost it       rank 2
    Призер / Призерка                                     a medal       rank 3

Финалист and Призер appear on the same athlete in different years, and so do
Победитель and Финалист, so they are three distinct tiers and not three words
for one. Rank 2 for "finalist" and rank 3 for "medallist" are still readings of
the tier ladder rather than positions the page prints, so each honour carries
`rank_stated`, saying whether the page named the place or this inferred it.

*Gender comes from grammar, one way only.* Чемпионка, Призерка, Финалистка,
Вице-чемпионка and Победительница are feminine and name a woman. The masculine
forms are also Russian's unmarked forms, so they are recorded as unmarked and
not as "Men".

CHAUSS'FIGHT IS NOT SAVATE. /champions/ carries one row - "Chauss'fight | 2017 |
Вице-чемпион Европы среди профессионалов (до 75 кг.)". Chausson is a different
sport, and it is dropped and counted rather than filed here.

SOURCE DEFECTS CARRIED, NOT REPAIRED

    Тренеры::                 a doubled colon in the coach label, on 23 blocks
    Финалист перевенства мира a misspelt первенства on /prizery-pervenstv/;
                              matched deliberately so the honour is not lost,
                              and the misspelling kept in `title`
    the menu title            /legends/ is "чемпионы мира и Европы"; the hunt
                              notes had this page's title swapped with
                              /champions/'s. The live <title> is read here.
"""

import html
import re

from savate.schema import Report, Tournament

NAME = "savate_ru"
DESCRIPTION = ("savate-boxe.ru hall-of-fame pages (athlete honours rolls - "
               "read and reported, never stored as competitions)")

# ---- the page ----------------------------------------------------------
#
# Not one <table> on any of the four pages: the layout is divs and paragraphs
# styled to look like a table, so the structure is read, not the markup's name
# for it. `\bwarrior\b` deliberately does not match `warrior__name` - the
# underscore is a word character, so the inner blocks keep out of the outer
# block's way.

_WARRIOR = re.compile(r'<div\b[^>]*class="[^"]*\bwarrior\b[^"]*"[^>]*>', re.I)
_HEADER = re.compile(r"<header\b.*?</header>", re.S | re.I)
_FOOTER = re.compile(r"<footer\b", re.I)
_TR = re.compile(r'<p\b[^>]*class="[^"]*\btr\b[^"]*"[^>]*>(.*?)</p>', re.S | re.I)
_SPAN = re.compile(r"<span[^>]*>(.*?)</span>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def _field(css):
    return re.compile(r'<div\b[^>]*class="[^"]*\b' + css + r'\b[^"]*"[^>]*>(.*?)</div>',
                      re.S | re.I)


_NAME_FIELD = _field("warrior__name")
_TRAINER_FIELD = _field("warrior__trainer")


def _plain(fragment):
    """Tag-free, entity-free, whitespace-collapsed text."""
    text = html.unescape(_TAGS.sub(" ", fragment or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# ---- the athlete line --------------------------------------------------
#
# "Фамилия ИМЯ (г.Санкт-Петербург)", sometimes with life dates after the
# parenthesis for an athlete who has died. The parenthesis is a place and the
# dates are not part of the name, so both come off; everything else is kept
# exactly as the page printed it.

_PLACE = re.compile(r"\(([^()]*)\)")
_LIFESPAN = re.compile(r"\d{2}\.\d{2}\.\d{4}\s*[-–—]\s*\d{2}\.\d{2}\.\d{4}")
_CITY_MARK = re.compile(r"\bг\.\s*")
_TRAINER_LABEL = re.compile(r"^\s*Тренер[ыа]?\s*:+\s*", re.I)


def split_name(raw):
    """One athlete line -> {fighter, place, city, lifespan}.

    The name is never touched beyond having the parenthesis and the life dates
    removed: no transliteration, no case change, no reordering.
    """
    text = _plain(raw)
    lifespan = ""
    found = _LIFESPAN.search(text)
    if found:
        lifespan = found.group(0)
        text = text[:found.start()] + text[found.end():]
    place, city = "", ""
    found = _PLACE.search(text)
    if found:
        place = " ".join(found.group(1).split())
        text = (text[:found.start()] + " " + text[found.end():])
        # "г." marks a city inside a place that may also name an oblast. Only
        # the marked segment is a city; an unmarked place is kept whole.
        for part in re.split(r"\s*,\s*", place):
            if _CITY_MARK.match(part):
                city = _CITY_MARK.sub("", part).strip()
        if not city and _CITY_MARK.search(place):
            city = _CITY_MARK.sub("", place).strip()
    return {"fighter": " ".join(text.split()),
            "place": place, "city": city, "lifespan": lifespan}


def _trainers(raw):
    text = _plain(raw)
    text = _TRAINER_LABEL.sub("", text)
    return [t.strip() for t in re.split(r"\s*,\s*", text) if t.strip()]


# ---- the honour line ---------------------------------------------------

# Longest stem first: "Вице-чемпион" contains "чемпион", and the loser of a
# final is not its winner.
_TIERS = [
    ("runner-up", "2", re.compile(r"^\s*вице[-\s]?чемпион(ка)?\b", re.I)),
    ("champion", "1", re.compile(r"^\s*чемпион(ка)?\b", re.I)),
    ("winner", "1", re.compile(r"^\s*победитель(ница)?\b", re.I)),
    ("finalist", "2", re.compile(r"^\s*финалист(ка)?\b", re.I)),
    ("medallist", "3", re.compile(r"^\s*приз[её]р(ка)?\b", re.I)),
]
# Where the page prints the place itself. "Finalist" and "medallist" are read
# off the ladder the page keeps, which is a reading and is flagged as one.
_RANK_STATED = {"champion", "winner", "runner-up"}

# чемпионат is the senior championship, первенство the age-group one. The
# misspelt "перевенства" on /prizery-pervenstv/ is matched on purpose: dropping
# the row would lose a real honour to a typing slip.
_SENIOR = re.compile(r"чемпионат\w*", re.I)
_YOUTH = re.compile(r"пер(?:в|ев)енств\w*", re.I)
_CUP = re.compile(r"\bкуб(?:ок|к\w*)", re.I)
_GAMES = re.compile(r"world\s+combat\s+games", re.I)

_SCOPES = [
    ("mediterranean", re.compile(r"средиземноморск\w*", re.I)),
    ("european", re.compile(r"европ\w*", re.I)),
    ("world", re.compile(r"\bмир[аеу]?\b", re.I)),
]

_PRO = re.compile(r"среди\s+профессионал\w*|сават[-\s]?про", re.I)
_STUDENT = re.compile(r"среди\s+студент\w*", re.I)

# "(до 52 кг.)" - the only weight wording these pages use. "св." (свыше, over)
# is matched too so that a page that starts printing it is not read as under.
_WEIGHT = re.compile(r"\(\s*(до|св\.?|свыше)\s*(\d{2,3}(?:[.,]\d)?)\s*кг", re.I)

_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Sports that are not savate. Chausson (Chauss'fight), canne de combat, baton
# and savate forme have their own federations and ladders; a row of one of them
# filed here would put a cannist in savate's competitive record.
_NOT_SAVATE = re.compile(
    r"chauss|шосс|шосс[оё]н|chausson|\bcanne\b|канн\w*\s+де|\bb[aâ]ton\b|"
    r"батон|savate\s+forme|сават\w*\s+форм", re.I)

_DISCIPLINES = [
    ("combat", re.compile(r"^\s*комба\b", re.I)),
    ("assaut", re.compile(r"^\s*ассо\b", re.I)),
]
_CADET = re.compile(r"кадет\w*", re.I)


def _match(table, text):
    for value, pattern in table:
        if pattern.search(text):
            return value
    return ""


# Every honour has the same keys whether or not it could be read. A row that
# was dropped and a row that was kept must be the same shape, or a consumer
# that filters on `problem` still trips over the one it filtered out.
_BLANK = {"discipline": "", "age_class": "", "age_tier": "", "event": "",
          "event_stated": False, "scope": "", "year": "", "year_shared": False,
          "tier": "", "rank": "", "rank_stated": False, "gender": "",
          "title_form": "", "weight_kg": "", "weight_bound": "",
          "professional": False, "student": False, "sport": "", "problem": ""}


def honour(style, years, title):
    """One p.tr's three cells -> a list of honour dicts, one per year.

    Never raises and never guesses: a cell it cannot read comes back as an
    honour with `problem` set and the three cells kept verbatim, so the row is
    visible rather than silently gone.
    """
    style, years, title = (_plain(style), _plain(years), _plain(title))
    base = dict(_BLANK, style=style, years=years, title=title)

    if _NOT_SAVATE.search(style) or _NOT_SAVATE.search(title):
        return [dict(base, problem="not savate", sport=style or title)]

    discipline = _match(_DISCIPLINES, style)
    if not discipline:
        return [dict(base, problem=f"discipline {style!r} is not one this page uses")]

    tier, rank, feminine = "", "", False
    for label, place, pattern in _TIERS:
        found = pattern.search(title)
        if found:
            tier, rank, feminine = label, place, bool(found.group(1))
            break
    if not tier:
        return [dict(base, problem=f"title {title!r} names no finishing position")]

    event_stated = True
    if _GAMES.search(title):
        event, age_tier = "games", ""
    elif _CUP.search(title):
        event, age_tier = "cup", ""
    elif _YOUTH.search(title):
        event, age_tier = "championship", "youth"
    elif _SENIOR.search(title):
        event, age_tier = "championship", "senior"
    else:
        # "Чемпион мира" with no event noun. The page spells the age-group
        # title out as первенство whenever it means one, so a bare title is the
        # senior championship - read from the page's own habit, and flagged.
        event, age_tier, event_stated = "championship", "senior", False

    scope = _match(_SCOPES, title)
    if _GAMES.search(title) and not scope:
        scope = "world"

    weight, bound = "", ""
    found = _WEIGHT.search(title)
    if found:
        weight = found.group(2).replace(",", ".")
        bound = "over" if found.group(1).lower().startswith("св") else "under"

    found = _YEAR.findall(years)
    if not found:
        return [dict(base, problem=f"year cell {years!r} holds no year")]

    out = []
    for year in found:
        out.append(dict(
            base,
            discipline=discipline,
            age_class="Cadet" if _CADET.search(style) else "",
            age_tier=age_tier,
            event=event,
            event_stated=event_stated,
            scope=scope,
            year=year,
            # One cell naming two years is the same honour won twice, so each
            # year is its own row and the cell is kept to show where it came from.
            year_shared=len(found) > 1,
            tier=tier,
            rank=rank,
            rank_stated=tier in _RANK_STATED,
            gender="Women" if feminine else "",
            title_form="feminine" if feminine else "unmarked",
            weight_kg=weight,
            weight_bound=bound,
            professional=bool(_PRO.search(title)),
            student=bool(_STUDENT.search(title)),
        ))
    return out


# ---- the page as a whole -----------------------------------------------


def athletes(page):
    """[{fighter, place, city, lifespan, trainers, honours, unread}] for a page."""
    starts = [m.start() for m in _WARRIOR.finditer(page)]
    out = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(page)
        tail = _FOOTER.search(page, start, end)
        block = page[start:tail.start() if tail else end]

        found = _NAME_FIELD.search(block)
        if not found:
            continue
        person = split_name(found.group(1))
        found = _TRAINER_FIELD.search(block)
        person["trainers"] = _trainers(found.group(1)) if found else []

        # The column header is display:none and is itself a p.tr. Dropping the
        # <header> first is what keeps "Стиль | Год | Титул" out of the results.
        body = _HEADER.sub(" ", block)
        rows, unread = [], []
        for paragraph in _TR.findall(body):
            cells = [_plain(c) for c in _SPAN.findall(paragraph)]
            if len(cells) < 3:
                unread.append(cells)
                continue
            rows.extend(honour(cells[0], cells[1], cells[2]))
        person["honours"] = rows
        person["unread"] = unread
        out.append(person)
    return out


def roll(page):
    """Every honour on a page, flattened, each carrying its athlete.

    Dropped rows are in here too, carrying `problem`; filter on it rather than
    trusting the list to hold only what could be read.
    """
    out = []
    for person in athletes(page):
        for h in person["honours"]:
            out.append(dict(h, fighter=person["fighter"], city=person["city"],
                            place=person["place"], trainers=person["trainers"]))
    return out


def competitions(honours):
    """{competition key: {rows, golds}} - what the roll claims, aggregated.

    The gold count is the evidence that these rows are not a podium: two people
    hold the same title in the same year, in classes the page does not print.
    Gender is part of the key so that a men's and a women's title in one year
    are not counted as a clash - what is left is a clash whatever the reading.
    """
    tally = {}
    for h in honours:
        if h.get("problem"):
            continue
        key = " ".join(x for x in (h["discipline"], h["scope"], h["age_tier"],
                                   h["event"], h["year"],
                                   h["gender"] or "unmarked") if x)
        seen = tally.setdefault(key, {"rows": 0, "golds": 0, "winners": []})
        seen["rows"] += 1
        if h["rank"] == "1":
            seen["golds"] += 1
            seen["winners"].append(h.get("fighter", ""))
    return tally


def read(source, slug, meta=None, **options):
    """Read one hall-of-fame page. Returns no rows, by design - see the module.

    The honours are in `report.notes`, whole: `honours` is one dict per athlete,
    honour and year; `competitions` is what those rows would claim if anyone
    filed them as podiums, with the collisions that say they must not be.
    """
    from savate import sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    page = sources.text(source)

    found = _TITLE.search(page)
    page_title = _plain(found.group(1)) if found else ""

    tournament = Tournament(
        slug=slug, name=meta.get("name", "") or page_title,
        discipline=meta.get("discipline", ""), level=meta.get("level", ""),
        format=meta.get("format", ""), age_class=meta.get("age_class", ""),
        year=meta.get("year", ""), country=meta.get("country", ""),
        source=source, adapter=NAME,
    )

    people = athletes(page)
    report.read = len(people)
    if not people:
        report.problem("no div.warrior blocks - this is not a savate-boxe.ru "
                       "hall-of-fame page")
        return tournament, [], report

    honours = roll(page)
    good = [h for h in honours if not h.get("problem")]
    other_sport = [h for h in honours if h.get("problem") == "not savate"]
    unreadable = [h for h in honours
                  if h.get("problem") and h.get("problem") != "not savate"]

    report.problem(
        f"{source} is an athlete honours roll, not a competition's results: "
        f"{len(people)} athletes and {len(good)} honours, none of which names a "
        f"competition beyond 'world'/'Europe' and a year. No rows are stored "
        f"and no tournament should be proposed from it.")
    if other_sport:
        report.problem(f"{len(other_sport)} row(s) dropped as another sport: "
                       + "; ".join(sorted({h['title'] for h in other_sport})))
    for h in unreadable:
        report.problem(f"unread: {h['style']!r} | {h['years']!r} | {h['title']!r}"
                       f" - {h['problem']}")
    for person in people:
        for cells in person["unread"]:
            report.problem(f"{person['fighter']}: a row with {len(cells)} cells, "
                           f"not three")

    no_class = [h for h in good if not h["weight_kg"]]
    if no_class:
        report.problem(f"{len(no_class)} of {len(good)} honours print no weight "
                       f"class, so none of them can be attributed to one")
    inferred = [h for h in good if not h["rank_stated"]]
    if inferred:
        report.problem(f"{len(inferred)} of {len(good)} honours give the tier "
                       f"(finalist / medallist) rather than the place; their "
                       f"rank is read off the page's ladder, not printed")
    tally = competitions(good)
    clashes = {k: v for k, v in tally.items() if v["golds"] > 1}
    if clashes:
        report.problem(
            f"{len(clashes)} year(s) carry more than one winner of the same "
            f"title with no class to separate them, e.g. "
            + "; ".join(f"{k}: {', '.join(x for x in v['winners'] if x)}"
                        for k, v in sorted(clashes.items())[:3]))

    report.notes.update({
        "kind": "honours-register",
        "page_title": page_title,
        "athletes": len(people),
        "honours": good,
        "dropped_other_sport": other_sport,
        "unreadable": unreadable,
        "competitions": tally,
        "competitions_claimed": len(tally),
        "professional": sum(1 for h in good if h["professional"]),
        "student": sum(1 for h in good if h["student"]),
        "women": sum(1 for h in good if h["gender"] == "Women"),
    })
    return tournament, [], report
