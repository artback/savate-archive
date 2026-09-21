"""The Japanese federation's Tokyo Open pages: nine years, eight shapes.

savate.jp publishes one Google Sites page per edition of the Savate Tokyo Open
(called Wcup for its first four years, 2011-2014). Every page says the same
thing - who finished where in each weight class - and almost every page says it
differently. Across 2011-2023 a placing is written as:

    full-width digits   １位 / ２位 / ３位 / ４位
    kanji ordinals      一位 / 二位 / 三位, sometimes every place on one line
                        separated by an ideographic comma 、
    word labels         優勝 champion / 準優勝 runner-up / 第三位 third,
                        each followed by a full-width colon
    Latin script        1st / 2nd / 3rd            (2016 only)

and the weight class as ＜男子-65kg＞, 【男子 Confirme -65kg トーナメント】,
男子 軽量級, Male -60kg, or 一般の部 男子アンダー７０ｋｇトーナメント.

That is one vocabulary in many alphabets, not nine formats, so this is one table
of ordinal forms rather than nine branches. NFKC normalisation collapses most of
the rest: it turns ＜ into <, ： into :, （ into (, １ into 1, ｋｇ into kg and
Ｓａｓａ－Ｐ into Sasa-P, so the same regex reads every year.

Four details of these pages decide how they are read.

*A club can look like a placing.* 三鷹 3rd Place is the name of a gym in
Mitaka, and it is printed beside half the 2021 and 2022 competitors. A Latin
ordinal is therefore only an ordinal at the start of a line, and no ordinal of
any script counts inside parentheses.

*Awards outnumber results.* 最優秀選手賞 (MVP), 敢闘賞 (fighting spirit),
新人賞 (newcomer), 特別賞 (special prize) and Best Bout all print a name in the
same shape as a podium line. None of them is a placing. A name is only read
where an ordinal introduces it.

*The parenthesis is sometimes a country and sometimes a club.* （フランス） is
France; （JSC）, （御殿下）, （Team Risk）, （バトルフィットネス大森） are clubs.
It is decided by lookup against the nations these pages actually name, never by
shape - an unrecognised value is kept as the club it is printed as.

*A ワンマッチ is not a tournament.* 2012 and 2013 label some classes ワンマッチ
(one match) or スペシャルマッチ (special match) and then print a single 優勝.
Filing that as "first place in the class" would turn one bout into a podium, so
those classes are reported rather than ranked; the Report lists every one of
them by name so nothing is lost, only unfiled.

Names are stored exactly as printed. Most are a surname in two kanji, some are
one (袁), several are katakana renderings of a foreign name, and the archive's
own name repair rejects anything under three characters as too short - so
nothing here is sent through it, romanised or given an invented given name.
"""

import html
import re
import unicodedata

from savate import display
from savate.schema import MEDALS, Bout, Placing, Report, Tournament, phase_of

NAME = "savate_jp"
DESCRIPTION = "Savate Tokyo Open / Wcup result pages on savate.jp (2011-2023)"

# ---- the page ----------------------------------------------------------
#
# Google Sites wraps the article in one role="main" region and repeats the
# whole navigation three times outside it. Slicing to that region is the
# difference between reading a results page and reading a site map.
_MAIN = re.compile(r"role=[\"']main[\"'][^>]*>", re.I)
_SCRIPT = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_BREAK = re.compile(r"(?is)<br\s*/?>")
_BLOCK = re.compile(
    r"(?is)</?(p|div|li|tr|h[1-6]|td|section|article|nav|header|footer|ul|ol)[^>]*>")
_TAG = re.compile(r"(?s)<[^>]+>")
# Everything from here down is Google's chrome, not the federation's page.
_FOOTER = ("Report abuse", "Page details", "Page updated")


def _lines(page):
    """The article's visible lines, NFKC-normalised, chrome removed."""
    found = _MAIN.search(page)
    body = page[found.end():] if found else page
    body = _SCRIPT.sub(" ", body)
    body = _BREAK.sub("\n", body)
    body = _BLOCK.sub("\n", body)
    body = _TAG.sub("", body)
    body = html.unescape(body).replace("\xa0", " ")
    out = []
    for raw in body.split("\n"):
        # str.split() treats the ideographic space U+3000 as whitespace, which
        # is what separates the tokens of a Japanese category header.
        line = unicodedata.normalize("NFKC", " ".join(raw.split()))
        if not line:
            continue
        if line in _FOOTER:
            break
        out.append(line)
    return out


# ---- the ordinal vocabulary -------------------------------------------
#
# One table, every script. 準優勝 must be tried before 優勝 or every runner-up
# becomes a champion; the alternation does that by being written first.
_PLACE = re.compile(
    r"(?P<runner>準優勝)"
    r"|(?P<champ>優勝)"
    r"|第?(?P<kanji>[一二三四五六七八])位"
    r"|第?(?P<digit>[1-9])位"
    r"|(?P<latin>[1-9])(?:st|nd|rd|th)(?![A-Za-z])")

_KANJI_RANKS = {"一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8}


def _depths(text):
    """Parenthesis depth at every index, so a club cannot become an ordinal."""
    depth, out = 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        out.append(depth)
        if ch in ")]" and depth:
            depth -= 1
    return out


def _places(line):
    """[(rank, start, end)] for every ordinal this line really states."""
    depth = _depths(line)
    found = []
    for match in _PLACE.finditer(line):
        if depth[match.start()]:
            continue          # inside (三鷹 3rd Place) - a gym, not a podium
        if match.group("latin") and line[:match.start()].strip():
            continue          # "3rd" only ranks when it opens the line
        if match.group("runner"):
            rank = 2
        elif match.group("champ"):
            rank = 1
        elif match.group("kanji"):
            rank = _KANJI_RANKS[match.group("kanji")]
        else:
            rank = int(match.group("digit") or match.group("latin"))
        found.append((rank, match.start(), match.end()))
    return found


# ---- nations, clubs and names ------------------------------------------
#
# Only the nations these pages actually print. A lookup and not a guess: a
# parenthesis this does not recognise stays the club it was printed as, which
# shows up as a new club rather than as a wrong country.
_NATIONS = {
    "フランス": "France", "ベルギー": "Belgium", "オーストラリア": "Australia",
    "ニューカレドニア": "New Caledonia", "アメリカ": "United States",
    "アメリカ合衆国": "United States", "シンガポール": "Singapore",
    "中華台北": "Chinese Taipei", "日本": "Japan",
}

# 選手 means "athlete" and is printed after every name on the 2011-2014 pages.
_ATHLETE = re.compile(r"選手\s*$")
_PAREN = re.compile(r"\(([^()]*)\)\s*$")
_EDGE = " \t:：,、。・-–—"
# The same trim without the dashes. An inline weight opens the 2021 women's
# lines as "-52kg ２位 家城（御殿下）", and the minus sign is the class: trimming
# it turns "under 52 kg" into "52 kg, end unstated".
_EDGE_KEEP_SIGN = " \t:：,、。・"


def _nation(text):
    """The canonical nation a parenthesis names, or "" if it names a club."""
    label = " ".join(str(text or "").split())
    if not label:
        return ""
    english = _NATIONS.get(label, "")
    resolved = display.country(english or label)
    if resolved.known:
        return resolved.name
    # Singapore and New Caledonia are not yet in the archive's nation table;
    # the spelling this page attests is still better than filing them as clubs.
    return english


def _person(raw):
    """One competitor as printed -> (name, country, club)."""
    text = str(raw or "").strip(_EDGE).strip()
    country = club = ""
    found = _PAREN.search(text)
    if found:
        inside = " ".join(found.group(1).split())
        text = text[:found.start()].strip()
        country = _nation(inside)
        if not country:
            club = inside
    text = _ATHLETE.sub("", text).strip(_EDGE).strip()
    return text, country, club


def _split_people(payload):
    """A rank's payload -> the people in it. Savate awards two bronzes."""
    parts, buffer, depth = [], [], 0
    for ch in payload:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch in "、," and not depth:
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(ch)
    parts.append("".join(buffer))
    return [p for p in (part.strip(_EDGE).strip() for part in parts) if p]


# ---- the category header -----------------------------------------------

_BRACKETS = re.compile(r"^[<【\[〔]+\s*|\s*[>】\]〕]+$")
_GENDERS = [("Women", re.compile(r"女子|女性|^女|female|women|girls", re.I)),
            ("Men", re.compile(r"男子|^男|male|men|boys", re.I))]
# "60-65 kg" is the class ending at its upper figure; "-65kg" and "+85kg" say
# which end is open; アンダー / オーバー say it in Japanese.
_BAND = re.compile(r"(?<![-+−])\b(\d{2,3})\s*[-–~]\s*(\d{2,3})\s*kg", re.I)
_KG = re.compile(r"(?P<sign>[-+−])?\s*(?P<word>アンダー|オーバー|under|over)?\s*"
                 r"(?P<kg>\d{2,3}(?:\.\d)?)\s*kg", re.I)
# The format a class was run under. トーナメント bracket, リーグ戦 round-robin,
# ワンマッチ / スペシャルマッチ a single bout and therefore not a placing.
_FORMATS = {"トーナメント": "bracket", "リーグ戦": "round-robin",
            "ワンマッチ": "single bout", "スペシャルマッチ": "special match"}
_SINGLE = ("ワンマッチ", "スペシャルマッチ")
# Canne de combat, chausson, bâton and savate forme are different sports, and
# this federation runs canne too - its own front page lists a World Canne de
# Combat Championship. A class named for one of them is dropped and reported,
# never filed as savate.
_OTHER_SPORT = re.compile(
    r"canne|chausson|b[aâ]ton|forme|カンヌ|カンヌドコンバ|ステッキ|シャッソン",
    re.I)
# Award headings. Every one of these prints a name in podium shape and none of
# them is a result.
_AWARD = re.compile(r"賞|mvp|best bout|stylist", re.I)
# 勝利者賞 - "winner's prize" - is how 2013 names the man who won its
# スペシャルマッチ. It is not an ordinal and the class it sits under is a single
# bout, so it is reported beside the other unranked single bouts rather than
# discarded with the MVPs.
_WINNER_PRIZE = re.compile(r"^(?:勝利者賞|優勝者賞)\s*[:：]?\s*(?P<who>.+)$")


def _weight(label):
    """(kg, bound) the label states, or ("", "") where it names a grade."""
    band = _BAND.search(label)
    if band:
        return band.group(2), "under"
    found = _KG.search(label)
    if not found:
        return "", ""
    sign, word = found.group("sign"), (found.group("word") or "").lower()
    bound = ("over" if sign == "+" or word in ("オーバー", "over")
             else "under" if sign in ("-", "−") or word in ("アンダー", "under")
             else "")
    return found.group("kg"), bound


def _gender(label):
    for value, pattern in _GENDERS:
        if pattern.search(label):
            return value
    return ""


class _Category:
    __slots__ = ("label", "gender", "weight_kg", "weight_bound", "format")

    def __init__(self, label):
        self.label = label
        self.gender = _gender(label)
        self.weight_kg, self.weight_bound = _weight(label)
        self.format = next((v for k, v in _FORMATS.items() if k in label), "")

    @property
    def single_bout(self):
        return any(word in self.label for word in _SINGLE)

    @property
    def other_sport(self):
        return bool(_OTHER_SPORT.search(self.label))


def _header(line):
    """A category header -> _Category; an award heading -> None; else False.

    False means "this line is not a heading at all", which is a different
    answer from "this heading opens no weight class" and has to stay that way:
    the first leaves the current class standing, the second closes it.
    """
    bracketed = bool(re.match(r"^[<【\[〔]", line))
    bare = _BRACKETS.sub("", line).strip()
    if not bare or len(bare) > 40:
        return False
    if _AWARD.search(bare):
        return None
    # A real header names a class and nothing else. Anything carrying a
    # parenthesis or an ideographic comma is a list of people - the 2019 MVP
    # line 男子 浜崎（御殿下）、女子 袁（中華台北） names two genders and is
    # still not a category.
    if not bracketed and re.search(r"[()、]", bare):
        return False
    if _gender(bare) or _weight(bare)[0]:
        return _Category(bare)
    return None if bracketed else False


# ---- a named bout ------------------------------------------------------
#
# "Best Bout / MIMOTO vs BUSHAWAY (-60kg final)" states that two people met.
# It does not state who won, and the podium two lines below is a different
# fact - so the bout is stored unresolved rather than settled from the medals.
_VERSUS = re.compile(r"^(?P<red>[^()]{1,30}?)\s*(?:vs\.?|VS|対)\s*"
                     r"(?P<blue>[^()]{1,30}?)\s*(?:\((?P<note>[^()]*)\))?\s*$",
                     re.I)
_AWARD_LEAD = re.compile(r"^\S*賞[:：]?\s+")

_DATE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
_EVENT = re.compile(r"(W\s*cup\s*\d?|Tokyo\s+Open)", re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def read(source, slug, meta=None, **options):
    from savate import sources

    meta = meta or {}
    report = Report(source=source, adapter=NAME)
    page = sources.text(source)
    lines = _lines(page)
    report.read = len(lines)

    title = ""
    found = _TITLE.search(page)
    if found:
        title = unicodedata.normalize(
            "NFKC", html.unescape(" ".join(_TAG.sub("", found.group(1)).split())))

    year = str(meta.get("year") or "")
    start = ""
    event = ""
    for line in lines:
        if not year and re.fullmatch(r"20\d\d", line):
            year = line
        when = _DATE.search(line)
        if when and not start:
            start = "-".join((when.group(1), f"{int(when.group(2)):02d}",
                              f"{int(when.group(3)):02d}"))
        label = _EVENT.search(line)
        if label and not event:
            event = " ".join(label.group(1).split())
    if start and not year:
        year = start[:4]

    name = meta.get("name") or re.sub(r"\s*-\s*20\d\d\s*$", "", title).strip()
    tournament = Tournament(
        slug=slug,
        name=meta.get("name") or (f"{name} {year}".strip() if name else slug),
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""),
        format=meta.get("format", ""),
        age_class=meta.get("age_class", ""),
        year=year,
        start_date=meta.get("start_date", start),
        end_date=meta.get("end_date", ""),
        city=meta.get("city") or ("Tokyo" if "tokyo" in (title or "").lower()
                                  else ""),
        country=meta.get("country", ""),
        source=source, adapter=NAME,
        competition=meta.get("competition", ""),
    )

    rows, single_bouts, seen_categories, awards = _rows(lines, slug, report)

    report.notes["categories"] = [c.label for c in seen_categories]
    report.notes["category_formats"] = {c.label: c.format
                                        for c in seen_categories if c.format}
    report.notes["event_label"] = event
    report.notes["award_lines_skipped"] = awards
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    if single_bouts:
        report.notes["single_bouts_not_ranked"] = single_bouts
        report.problem(
            f"{len(single_bouts)} class(es) were run as a single bout "
            f"(ワンマッチ / スペシャルマッチ) and are reported, not ranked: "
            + "; ".join(f"{s['category']} -> {s['fighter']}"
                        for s in single_bouts))
    if not rows:
        report.problem("no placings read")
    return tournament, rows, report


def _rows(lines, slug, report):
    """Walk the article once: headers set a class, ordinals fill it."""
    rows, single_bouts, seen, awards = [], [], [], 0
    dropped = []          # rows belonging to another sport entirely
    ranked = 0            # placings emitted, which is what numbers placing_id
    current = None
    pending = None        # a rank whose name is in the next element
    for line in lines:
        try:
            # A named bout comes first: "ベストバウト賞 岡本 vs 伊藤" carries an
            # award word and is still the only record that these two met.
            bout = _bout(line, slug, sum(1 for r in rows if isinstance(r, Bout)))
            if bout is not None:
                rows.append(bout)
                pending = None
                continue

            if current is not None and current.single_bout:
                prize = _WINNER_PRIZE.match(line)
                if prize:
                    who, _, _ = _person(prize.group("who"))
                    if who:
                        single_bouts.append({"category": current.label,
                                             "fighter": who, "rank": ""})
                        continue

            places = _places(line)
            if places:
                if current is None:
                    report.problem("a placing outside any weight class, "
                                   f"skipped: {line!r}")
                    pending = None
                    continue
                made, pending = _placings(line, places, current, slug, ranked)
                ranked += _file(made, current, rows, single_bouts, dropped)
                continue

            head = _header(line)
            if head is False:
                if pending is not None and current is not None:
                    # 2011 and 2012 put the label and the name in separate
                    # elements, so the name arrives on the next line.
                    rank = pending
                    pending = None
                    made, _ = _placings(line, [(rank, 0, 0)], current, slug,
                                        ranked)
                    ranked += _file(made, current, rows, single_bouts, dropped)
                continue
            pending = None
            if head is None:
                current = None            # an award heading closes the class
                awards += 1
                continue
            current = head
            seen.append(head)
        except Exception as exc:          # one bad line costs one line
            report.problem(f"could not read {line!r}: "
                           f"{type(exc).__name__}: {exc}")
            pending = None
    if dropped:
        report.problem(
            f"{len(dropped)} placing(s) dropped: the class names another sport "
            f"(canne de combat, chausson, baton or savate forme), not savate: "
            + ", ".join(dropped))
        report.notes["other_sport_dropped"] = dropped
    return rows, single_bouts, seen, awards


def _file(made, category, rows, single_bouts, dropped):
    """Put a line's placings where they belong. Returns how many were ranked.

    A class run as a single bout, and a class belonging to another sport, are
    reported by name rather than ranked - so the page's own words survive
    without a podium being invented out of one match or out of canne de combat.
    """
    if category.other_sport:
        dropped.extend(placing.fighter for placing in made)
        return 0
    if category.single_bout:
        single_bouts.extend({"category": category.label,
                             "fighter": placing.fighter,
                             "rank": placing.rank} for placing in made)
        return 0
    rows.extend(made)
    return len(made)


def _placings(line, places, category, slug, offset):
    """The placings one line states, plus a rank still waiting for its name."""
    made, pending = [], None
    # 2021 prints the women's class inline: "-52kg ２位 家城（御殿下）".
    lead = line[:places[0][1]].strip(_EDGE_KEEP_SIGN).strip()
    here = category
    if lead and _weight(lead)[0]:
        here = _Category(f"{category.label} {lead}".strip())
    for index, (rank, _, end) in enumerate(places):
        stop = places[index + 1][1] if index + 1 < len(places) else len(line)
        payload = line[end:stop]
        people = _split_people(payload)
        if not people:
            pending = rank
            continue
        for person in people:
            fighter, country, club = _person(person)
            if not fighter:
                continue
            made.append(Placing(
                tournament=slug,
                placing_id=f"{slug}-{offset + len(made) + 1:03d}",
                category=here.label,
                gender=here.gender,
                age_class="",
                weight_kg=here.weight_kg,
                weight_bound=here.weight_bound,
                rank=str(rank),
                medal=MEDALS.get(str(rank), ""),
                fighter=fighter,
                country=country,
                club=club,
                result_source="reported",
            ))
    return made, pending


def _bout(line, slug, offset):
    """An "X vs Y" line as an unresolved bout, or None."""
    text = _AWARD_LEAD.sub("", line).strip()
    found = _VERSUS.match(text)
    if not found:
        return None
    red, _, red_club = _person(found.group("red"))
    blue, _, blue_club = _person(found.group("blue"))
    if not (red and blue) or red == blue:
        return None
    note = " ".join((found.group("note") or "").split())
    kilos, bound = _weight(note)
    return Bout(
        tournament=slug,
        bout_id=f"{slug}-b{offset + 1:03d}",
        category=note,
        gender=_gender(note),
        weight_kg=kilos,
        weight_bound=bound,
        phase=phase_of(note),
        # Red is simply whoever the page named first. It is a corner, not a
        # result, and this page never states either.
        red=red, red_club=red_club,
        blue=blue, blue_club=blue_club,
        status="unresolved",
        result_source="",
    )
