"""The one-off federation web pages: four small layouts that live on the web.

`savate_misc` is this archive's leftover pile for PDFs. This is the same idea
for pages: six documents from six different federations, none of which has ever
published twice in the same shape, and none of which is worth a file of its own.
The module sniffs which of the four layouts it is holding and hands the page to
the reader written for it. A page that matches none of them yields no rows and
says so, which is the only honest answer for a pile whose defining property is
that it is a pile.

The four, and what each one actually states:

1. CROATIAN FINALS PARAGRAPH - the Hrvatski savate savez homepage, one line per
   final of the 2025 world combat championship:

       – 52kg – LEE LALIĆ vs CHLOE NANDI – Francuska – POBJEDA
       – 70kg – ANTONIJA ZEC vs MAIMARA LAWSON – Francuska – PORAZ

   The verdict is written from the HOME FIGHTER'S point of view: POBJEDA is a
   win for the Croatian, PORAZ a loss, and the nation printed is the OPPONENT'S,
   not the winner's. So "the first name won" is true of five of these six lines
   and false of the sixth, and a reader that assumed it would file Antonija Zec
   as world champion. The verdict word is read, never the order.

   The page states no gender and no decision. Four of these classes are the
   women's and two the men's - which is corroborated elsewhere in this archive
   and stated nowhere in this document, so `gender` is left empty here. The
   first-named fighter's nation is the one fact taken from the manifest rather
   than the line: the prose says these are "naših reprezentativaca", our
   representatives, and says it once for all six. An entry that does not name
   that delegation gets empty nations, never the host's - see `_home`.

2. BILINGUAL CHAMPIONS LIST - Savate Canada's Weebly page, a four-line block
   per champion under a season heading, in French and English at once:

       Champions Savate Assaut 2015
       Nom/Name: Sherin Al-Safadi
       Titre/Title: championne canadienne
       Catégorie de poids/Weight categorie: 48-52 kg
       Club: JT Savate Combat

   One page, three national championships - 2013, 2014 and 2015 - so a manifest
   entry names the season as well as the URL, the way `cesav_ranking` names its
   event, and an entry that names none READS NOTHING. That refusal is the
   point: `Placing` has no season field, so the three merged into one slug are
   a competition with three gold medallists at -65 kg and Joseph Zefrani
   champion in two weight classes at once. Every row of it would be faithful
   and the championship it describes never happened.

   GOLD ONLY: the page prints champions and never a runner-up, so it cannot
   become a podium, and every read says so. Gender is read from the French,
   which inflects it - championne is a woman, champion a man. The weight is
   printed as a BAND, "48-52 kg", which names two figures and no bound; it is
   read as the class ending at 52, which is the class a savate band describes,
   and the read says that too, because the lower figure is then stored nowhere.

3. DELEGATION MEDAL REPORT - a national federation reporting its own team's
   medals from an international meet. Turkey's and Ukraine's are the same
   document in two languages: a heading per placing tier, then one "name -
   weight" line per medallist.

       Dünya Şampiyonlarımız (World Cup Kategorisi):
       Efe Ercan Boğaz – 85 kg
       🥇 Senior World Cup Winners:
       Nazar Kostiuk — 75 kg

   Two things are true of every document of this shape and neither is a parsing
   problem, so both are reported on every read rather than papered over. It is
   PARTIAL - one delegation's medals, never the competition - and it names the
   competition only in prose, which is a problem when the prose names two. The
   Turkish page is exactly that case: its meet was a World Youth Championship
   and an Uzbekistan Cup at once, and only the gold tier says which of the two
   it belongs to.

4. WIX BOUT ARTICLE - the Ligue de Guadeloupe's successor site, lgsbfda.net.
   The body is `antilles_bouts`' own grammar, down to the club in brackets; the
   only thing that adapter cannot do with it is find the body, because it looks
   for the Joomla articleBody the dead site had and Wix has a Ricos
   content-viewer instead. So this module does not copy that grammar: it lifts
   the Wix body into the shape `antilles_bouts` reads and hands the document to
   it. When that adapter learns to recognise a Wix body, this layout can be
   deleted and the manifest entry pointed straight at it.

   Two things are done to the body on the way past, and both are subtractions
   or repairs, never additions. One sentence WRAPPED: the author pressed return
   after "vainqueur l'unanimité" and Wix made the tail its own paragraph,
   "RAIMBAULT .". That tail is printed text - a plain <p>, id viewer-0372m50 -
   so the two are closed up and the bout is read as decided, which is what the
   article's own "7 assauts avec décision" says it should be. And the class
   letter in "M75" is NOT a gender here: `antilles_bouts` expands it into one
   on the strength of the "F-70KG" forms its own corpus prints, this page
   prints no such form and no word for a gender, and its "+90" line shows the
   letter reads as moins as easily as masculin. So the gender comes off.

Four things this module will not do, anywhere.

*It does not turn a corner into a result.* None of these layouts states a
corner, so `winner_corner` is always empty. The Wix page colours the winner's
name in the winner's corner colour; that is typography, not a verdict, and no
winner here is read from it - the one that looked like it needed to be is
printed in words in the next paragraph.

*It does not infer a class the page did not print.* An unsigned "52kg" is read
as the class ending at 52, which is the convention the rest of this archive
already uses for a printed band; every read says so, naming the figures it did
it to, because the page itself prints no sign.

*It does not put a nationality on a fighter the page did not give one.* The
delegation layouts fill `country` only from an entry's `home_country`, which
is there because the prose names the delegation once for the whole list. A
competition's own `country` is where the meet was HELD and is never borrowed
for this - a delegation report is usually an away meet, and borrowing it filed
twelve Turkish juniors as Uzbeks.

*It does not file another sport.* Canne de combat, chausson, bâton and savate
forme are different sports; a line naming one is dropped and counted. So is a
demonstration, which has no result and is not a bout.
"""

import html
import re
import tempfile
import urllib.parse
from pathlib import Path

from savate.schema import Bout, Placing, Report, Tournament

NAME = "misc_federations"
DESCRIPTION = ("One-off federation web pages: Croatian finals, Canadian "
               "champions, a delegation medal report, a Wix bout article")


# ------------------------------------------------------------------ page ----

# Tags that end a printed line. Everything else is inline, and a line is
# rebuilt from the text between two of these - which is what puts the Turkish
# page's "Efe Ercan Boğaz" back beside its "– 85 kg" after Word split them into
# neighbouring <span>s, and closes up the newline Word left inside a heading.
_BLOCK = re.compile(r"</?\s*(?:p|div|li|h[1-6]|tr|td|th|br|blockquote|section|"
                    r"article|ul|ol|table|dl|dt|dd|figure|figcaption|header|"
                    r"footer|nav|main|aside|hr|pre)\b[^>]*>", re.I)
_DROP = re.compile(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1\s*>",
                   re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)


def _plain(fragment):
    text = html.unescape(_TAGS.sub(" ", fragment or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")
                  .replace("﻿", "")).strip()


def lines_of(page):
    """One printed line per block element, inline markup closed up."""
    body = _DROP.sub(" ", page or "")
    body = _BLOCK.sub("\x00", body)
    body = html.unescape(_TAGS.sub("", body))
    body = body.replace("\xa0", " ").replace("﻿", "")
    out = []
    for chunk in body.split("\x00"):
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if chunk:
            out.append(chunk)
    return out


# savate.org.ua serves the same 2.6 kB shell for every URL it has: the articles
# live inside the JavaScript bundle the shell loads. The bundle's filename
# carries a build hash and changes whenever the site is rebuilt, so a manifest
# entry names the site root and the bundle is resolved from it on every read.
_SPA_SHELL = re.compile(r'<div\s+id="root"\s*>\s*</div>', re.I)
_MODULE_SRC = re.compile(r'<script[^>]*type="module"[^>]*src="([^"]+\.js)"',
                         re.I)


def _bundle_url(page, source):
    """The JS bundle a single-page-app shell loads, or "" if this is not one."""
    if not _SPA_SHELL.search(page or ""):
        return ""
    found = _MODULE_SRC.search(page)
    if not found:
        return ""
    return urllib.parse.urljoin(str(source), found.group(1))


# A WordPress export baked into that bundle: every article is an object literal
# with its title, its date and its HTML body in backtick strings.
_POST = re.compile(r"\{ID:(\d+),", re.S)


def _field(chunk, name):
    found = re.search(name + r":`((?:[^`\\]|\\.)*)`", chunk, re.S)
    return found.group(1) if found else ""


def posts_in(bundle):
    """[{id, title, date, body}] for every article inside a site bundle."""
    out = []
    # split() on a pattern with one group gives [before, id, after, id, ...].
    parts = _POST.split(bundle)
    for index in range(1, len(parts) - 1, 2):
        ident, chunk = parts[index], parts[index + 1]
        title = _field(chunk, "post_title")
        if not title:
            continue
        out.append({"id": ident, "title": title,
                    "date": _field(chunk, "post_date"),
                    "body": _field(chunk, "post_content").replace("\\n", "\n")})
    return out


# The Wix rich-text body. Everything outside it is a megabyte of site chrome.
_WIX_BODY = re.compile(r'data-id="content-viewer"[^>]*>(.*?)'
                       r'<div\s+type="last"', re.S | re.I)
_WIX_BODY_TAIL = re.compile(r'data-id="content-viewer"[^>]*>(.*)', re.S | re.I)
_WIX_PARA = re.compile(r"<(p|h[1-6])\b[^>]*>(.*?)</\1\s*>", re.S | re.I)


def wix_paragraphs(page):
    """The printed paragraphs of a Wix post, in order, or [] if it is not one."""
    found = _WIX_BODY.search(page or "") or _WIX_BODY_TAIL.search(page or "")
    if not found:
        return []
    return [text for text in (_plain(m.group(2))
                              for m in _WIX_PARA.finditer(found.group(1)))
            if text]


# --------------------------------------------------------------- domain -----

# Different sports that share these federations' pages. A row naming one is
# dropped and counted; savate is not the only thing these people do.
_OTHER_SPORT = re.compile(
    r"\bcanne\s+de\s+combat\b|\bcanne\b|\bla\s+canne\b|\bchausson\b|"
    r"\bb[âa]ton\b|\bsavate\s+forme\b|\bforme\b|\bstick\s+fighting\b|"
    r"\bcane\s+fighting\b", re.I)

# An exhibition. It has no result and it is not a bout.
_DEMO = re.compile(r"\bd[ée]monstra\w*|\bdimostraz\w*|\bdemo\b|"
                   r"\bexhibition\b|\begzibic\w*|\bg[öo]steri\w*|"
                   r"\bpokazn\w*|\bдемонстра\w*|\bпоказов\w*", re.I)

# The weight a line prints. "+85 kg", "85+ kg", "-60 kg", "56 кг".
_KG = re.compile(r"(?P<pre>[-+−])?\s*(?P<kg>\d{2,3})\s*(?P<post>\+)?\s*"
                 r"(?:kgs?|кг)\b", re.I)


# The bound written as a word instead of a sign. The Ukrainian federation
# prints "weight category up to 56 kg", which states the class as plainly as
# "-56 kg" does; the Turkish one prints "85 kg" and states nothing.
_UNDER_WORD = re.compile(r"\bup\s+to\b|\bunder\b|\bbelow\b|"
                         r"\bmoins\s+de\b|\bдо\b", re.I)
_OVER_WORD = re.compile(r"\bover\b|\babove\b|\bplus\s+de\b|\bпонад\b",
                        re.I)


def _weight(text):
    """(kilos, bound, stated) from a printed weight, or ("", "", False).

    `stated` is the whole point of the third value: True when the page printed
    the bound - a sign, or a word for it - and False when it printed a bare
    figure. A bare figure is still read as the class ENDING at it, which is the
    convention the rest of this archive uses, but it is the archive's
    convention and not the document's, so the caller has to say so.
    """
    found = _KG.search(str(text or ""))
    if not found:
        return "", "", False
    head = str(text or "")[:found.start()]
    if found.group("pre") == "+" or found.group("post") == "+" \
            or _OVER_WORD.search(head):
        return found.group("kg"), "over", True
    if found.group("pre") in ("-", "−") or _UNDER_WORD.search(head):
        return found.group("kg"), "under", True
    return found.group("kg"), "under", False


def _label(kilos, bound, extra=""):
    if not kilos:
        return " ".join(extra.split())
    sign = "+" if bound == "over" else "-"
    return " ".join(f"{extra} {sign}{kilos} kg".split())


def _home(meta, options):
    """Whose federation published this, and only if an entry says so.

    Two of these layouts print one country's competitors and no one else's and
    say so once in prose - "naših reprezentativaca", "Millilerimiz" - rather
    than on each line. That country belongs on the fighters, so an entry names
    it with `home_country` and this returns it.

    It used to fall back to the competition's own `country` when no entry named
    one, on the reasoning that a delegation reporting a home meet prints the
    same country twice. That reasoning is false for the documents this layout
    exists to read: a delegation report is almost always an AWAY meet, and
    `Tournament.country` is where the meet was HELD. The fallback therefore
    stamped the HOST nation on a visiting team - give the Turkish report the
    truthful `country="Uzbekistan"` and twelve Turkish juniors came back Uzbek,
    under a report that claimed the page said so. It does not. There is no
    fallback now: unnamed is empty.
    """
    return str((options or {}).get("home_country")
               or meta.get("home_country") or "")


# Particles that legitimately begin lower case inside a name.
_PARTICLES = {"de", "del", "della", "di", "da", "dos", "du", "des", "van",
              "von", "der", "den", "le", "la", "ben", "bin", "al", "el",
              "mc", "mac", "ter", "te", "abu"}


def looks_like_person(text):
    """Is this a printed competitor's name rather than a sentence?

    The delegation reports put their medallists in a bare list with nothing to
    mark one, so the only thing separating "Melnyk Maksym" from "Glory to
    Ukraine!" is the shape of the words. Every name in these documents is set
    in title case or capitals and every sentence contains a word that is not,
    which is enough, and is checked rather than assumed: a line with a lower
    case word in it is prose and is left alone.
    """
    text = " ".join(str(text or "").split())
    if not text or len(text) > 60 or re.search(r"\d|https?:|@", text):
        return False
    words = [w for w in re.split(r"[\s.]+", text) if w]
    if not 2 <= len(words) <= 5:
        return False
    for word in words:
        head = word[:1]
        if not head.isalpha():
            return False
        if not head.isupper() and word.lower().strip("'’") not in _PARTICLES:
            return False
    return True


# ------------------------------------------------------------------ read ----

def read(source, slug, meta=None, **options):
    """(Tournament, [Bout|Placing], Report) from one of the one-off pages."""
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    tournament = _tournament(slug, meta, source)

    try:
        page = sources.text(source, refresh=options.get("refresh", False))
    except Exception as e:                       # a page that will not come
        report.problem(f"could not fetch the page: {e}")
        return tournament, [], report

    wanted = str(options.get("event") or meta.get("event") or "").strip()

    # A single-page app keeps its articles in the bundle its shell loads.
    bundle = _bundle_url(page, source)
    if bundle:
        report.notes["bundle"] = bundle
        try:
            page = sources.text(bundle, refresh=options.get("refresh", False))
        except Exception as e:
            report.problem(f"the site is a single-page app and its bundle "
                           f"{bundle} would not come: {e}")
            return tournament, [], report

    if "post_content:`" in page or "post_content: `" in page:
        return _from_bundle(page, wanted, slug, meta, report, tournament,
                            source, options)

    lines = lines_of(page)
    report.read = len(lines)
    if not lines:
        report.problem("the page yielded no text at all")
        return tournament, [], report

    return _dispatch(page, lines, wanted, slug, meta, report, tournament,
                     source, options)


def _dispatch(page, lines, wanted, slug, meta, report, tournament, source,
              options=None):
    options = options or {}
    layout = _layout(page, lines)
    report.notes["layout"] = layout or "unrecognised"
    if layout is None:
        report.problem("none of this module's four layouts fits this page")
        return tournament, [], report

    if layout == "croatian_finals":
        rows = _croatian_finals(lines, slug, meta, report, tournament,
                                options)
    elif layout == "bilingual_champions":
        rows = _bilingual_champions(lines, wanted, slug, meta, report,
                                    tournament, options)
    elif layout == "wix_bouts":
        return _wix_bouts(page, slug, meta, report, tournament, source)
    else:
        rows = _delegation_medals(lines, slug, meta, report, tournament,
                                  options)

    if not rows:
        report.problem(f"the {layout} reader found nothing to read")
    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    return tournament, rows, report


def _layout(page, lines):
    """Which of the four this page is, or None."""
    if sum(1 for line in lines if _CRO_FINAL.match(line)) >= 2:
        return "croatian_finals"
    if sum(1 for line in lines if _CA_LABEL.match(line)) >= 4:
        return "bilingual_champions"
    if _WIX_BODY.search(page) or _WIX_BODY_TAIL.search(page):
        if any(_VS.search(text) for text in wix_paragraphs(page)):
            return "wix_bouts"
    if _tiers_in(lines):
        return "delegation_medals"
    return None


def _tournament(slug, meta, source, **derived):
    fields = dict(
        slug=slug, name=meta.get("name", slug),
        discipline=meta.get("discipline", ""), level=meta.get("level", ""),
        format=meta.get("format", ""), age_class=meta.get("age_class", ""),
        year=meta.get("year", ""), start_date=meta.get("start_date", ""),
        end_date=meta.get("end_date", ""), city=meta.get("city", ""),
        country=meta.get("country", ""), source=str(source), adapter=NAME)
    for key, value in derived.items():
        if value and not fields.get(key):
            fields[key] = value
    return Tournament(**fields)


# ------------------------------------------------------- layout 1: Croatia --

# "– 52kg – LEE LALIĆ vs CHLOE NANDI – Francuska – POBJEDA". The inner
# separators are matched as dashes with space around them, never as a bare
# hyphen, so a hyphenated surname is never cut in half.
_CRO_FINAL = re.compile(
    r"^\s*[–—-]\s*(?P<sign>[-+−]?)\s*(?P<kg>\d{2,3})\s*kg\s*[–—]\s*"
    r"(?P<home>[^–—]+?)\s+vs\.?\s+(?P<away>[^–—]+?)\s*[–—]\s*"
    r"(?P<nation>[^–—]+?)\s*[–—]\s*(?P<verdict>[^–—]{1,40}?)\s*\.?\s*$", re.I)

# The verdict, from the home fighter's point of view.
_CRO_VERDICT = {"pobjeda": "home", "pobijeda": "home", "poraz": "away"}

# Nations as Croatian prints them. A lookup, never a guess: a spelling that is
# not here is kept exactly as the page printed it, which shows up as a new
# country rather than as a wrong one.
_CRO_NATIONS = {
    "francuska": "France", "italija": "Italy", "tunis": "Tunisia",
    "hrvatska": "Croatia", "srbija": "Serbia", "njemacka": "Germany",
    "madarska": "Hungary", "bugarska": "Bulgaria", "slovenija": "Slovenia",
    "spanjolska": "Spain", "engleska": "England", "rumunjska": "Romania",
    "austrija": "Austria", "turska": "Turkey", "ukrajina": "Ukraine",
    "grcka": "Greece", "belgija": "Belgium", "nizozemska": "Netherlands",
    "svicarska": "Switzerland", "ceska": "Czechia", "poljska": "Poland",
    "rusija": "Russia", "alzir": "Algeria", "maroko": "Morocco",
    "kamerun": "Cameroon", "indija": "India", "kanada": "Canada",
    "sjedinjene americke drzave": "United States", "portugal": "Portugal",
    "senegal": "Senegal", "japan": "Japan", "brazil": "Brazil",
}

_CRO_FINALS_WORD = re.compile(r"\bfinal[aei]\b", re.I)
# A whole date, never the tail of a printed range. The same paragraph carries
# "02.-06.07.2025" for the qualifications in Bulgaria and "03.10.2025." for
# the finals in Split, and a pattern that took the first figures it met would
# date these six finals to the wrong country and the wrong quarter.
_CRO_DATE = re.compile(r"(?<![\d.\-\u2013\u2014])(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")


def _croatian_finals(lines, slug, meta, report, tournament, options=None):
    from savate import normalize as norm

    options = options or {}
    home = _home(meta, options)
    rows = []
    phase, when = "", ""
    dropped_sport, demos = 0, 0
    unsigned = []

    for line in lines:
        found = _CRO_FINAL.match(line)
        if not found:
            # The paragraph above the list dates the finals and says they are
            # finals. Both are facts the page states; neither is assumed.
            if _CRO_FINALS_WORD.search(line):
                phase = "final"
                dated = _CRO_DATE.search(line)
                # The last dated line before the first bout is the one that
                # says when these bouts were held; the ones above it are the
                # rounds that led to them, somewhere else.
                if dated and not rows:
                    when = norm.date(re.sub(r"\s+", "", dated.group(1)))
            continue
        if _OTHER_SPORT.search(line):
            dropped_sport += 1
            continue
        if _DEMO.search(line):
            demos += 1
            continue

        kilos = found.group("kg")
        bound = "over" if found.group("sign") == "+" else "under"
        if not found.group("sign"):
            unsigned.append(f"{kilos}kg")
        home_name = " ".join(found.group("home").split())
        away = " ".join(found.group("away").split())
        printed = " ".join(found.group("nation").split())
        nation = _CRO_NATIONS.get(norm.fold(printed).strip(), printed)
        verdict = _CRO_VERDICT.get(norm.fold(found.group("verdict")).strip(".,"))

        index = len(rows) + 1
        bout = Bout(
            tournament=slug,
            bout_id=f"{slug}-{index:02d}",
            date=when,
            category=_label(kilos, bound), gender="",
            age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound, phase=phase,
            # Printed order. The page never says who stood in which corner.
            red=home_name, red_country=home,
            blue=away, blue_country=nation,
            winner_corner="",
        )
        if verdict == "home":
            bout.winner, bout.loser = home_name, away
        elif verdict == "away":
            bout.winner, bout.loser = away, home_name
        if bout.winner:
            bout.status, bout.result_source = "decided", "reported"
        else:
            bout.status, bout.result_source = "unresolved", "reported"
            report.problem(f"{home_name} vs {away}: the verdict word "
                           f"{found.group('verdict')!r} is not one this reader "
                           f"knows, so the bout is stored unresolved")
        rows.append(bout)

    report.notes.update(other_sport_rows=dropped_sport, demonstrations=demos)
    if dropped_sport:
        report.problem(f"{dropped_sport} line(s) name another sport and are "
                       f"not filed as savate")
    if demos:
        report.problem(f"{demos} line(s) are demonstrations, which have no "
                       f"result and are not bouts")
    if rows:
        report.problem(
            "the page states no gender for any of these classes and this "
            "reader does not infer one from the names")
        if unsigned:
            report.problem(
                f"{len(unsigned)} of these classes are printed without a sign "
                f"({', '.join(sorted(set(unsigned)))}), so each is read as the "
                f"class ending at that figure - this archive's convention, not "
                f"something the page states")
        if home:
            report.problem(
                f"the first-named fighter in each line is taken to be "
                f"{home}'s: the prose says so once, collectively, and the "
                f"lines themselves name only the opponent's nation")
        if not phase:
            report.problem("nothing on the page says these are finals, so no "
                           "phase is claimed")
    if when:
        tournament.start_date = tournament.start_date or when
        tournament.end_date = tournament.end_date or when
        tournament.year = tournament.year or when[:4]
    return rows


# -------------------------------------------------------- layout 2: Canada --

_CA_LABEL = re.compile(
    r"^\s*(?P<label>Nom\s*/\s*Name|Titre\s*/\s*Title|"
    r"Cat[ée]gorie\s+de\s+poids\s*/\s*Weight\s+categorie|Club)"
    r"\s*:\s*(?P<value>.*)$", re.I)
# "Champions Savate Assaut 2015". The discipline is read rather than assumed,
# because this federation runs canne de combat too and a season of it would sit
# under a heading of exactly this shape - and canne is a different sport.
_CA_SEASON = re.compile(
    r"^\s*Champions?\s+(?P<what>[^\d]{2,40}?)\s+(?P<year>(?:19|20)\d{2})\s*$",
    re.I)
# "championne canadienne" is a woman, "champion canadien" a man: the French
# inflects, so the gender is read rather than guessed at from the given name.
_CA_WOMAN = re.compile(r"championne", re.I)
_CA_MAN = re.compile(r"champion(?!ne)", re.I)
_CA_WEIGHTS = [
    (re.compile(r"^\s*\+\s*(\d{2,3})\s*kg", re.I), "over", 1),
    (re.compile(r"^\s*(\d{2,3})\s*et\s*\+", re.I), "over", 1),
    (re.compile(r"^\s*(\d{2,3})\s*[-–]\s*(\d{2,3})\s*kg", re.I), "under", 2),
    (re.compile(r"^\s*-?\s*(\d{2,3})\s*kg", re.I), "under", 1),
]


def _ca_weight(text):
    """(kilos, bound, printed_as) for one of this page's four weight forms.

    `printed_as` is "band" for "48-52 kg", which names two figures and no
    bound. Reading it as the class ending at 52 is right - that is the class
    a savate band describes - but the lower figure is then not stored anywhere
    and the row shows a bound the page never printed, so the caller says so.
    """
    for pattern, bound, group in _CA_WEIGHTS:
        found = pattern.match(" ".join(str(text or "").split()))
        if found:
            if found.lastindex == 2:
                printed_as = "band"
            elif re.search(r"[-+\u2013]|\bet\b", found.group(0)):
                printed_as = "signed"
            else:
                printed_as = "bare"
            return found.group(group), bound, printed_as
    return "", "", ""


def _bilingual_champions(lines, wanted, slug, meta, report, tournament,
                         options=None):
    home = _home(meta, options)
    rows = []
    seasons, season, discipline = [], "", ""
    block = {}
    bands = []
    dropped_sport = 0
    other_sport_season = False
    year_wanted = str(wanted or meta.get("year") or "").strip()

    # One page, three national championships. They are three competitions, not
    # one, and `Placing` carries no season - so merging them produces a single
    # championship with three gold medallists at -65 kg and one man holding
    # gold in two weight classes at once. Every row would be individually
    # faithful and the competition they describe would not exist. Nothing is
    # read until an entry names which season it wants.
    on_page = [(f.group("what"), f.group("year")) for f in
               (_CA_SEASON.match(line) for line in lines) if f]
    if not year_wanted and len(on_page) > 1:
        report.notes["seasons_on_page"] = [f"{w} {y}" for w, y in on_page]
        report.problem(
            f"this page holds {len(on_page)} separate national championships "
            f"({', '.join(f'{w} {y}' for w, y in on_page)}) and no season was "
            f"named; they are different competitions and a placing carries no "
            f"season, so merging them would invent one championship with three "
            f"champions in a class - nothing is read until the entry's "
            f"\"event\" key names one")
        return []

    def flush():
        if not block.get("name"):
            block.clear()
            return
        title = block.get("title", "")
        if (other_sport_season or _OTHER_SPORT.search(title)
                or _OTHER_SPORT.search(block.get("weight", ""))):
            nonlocal dropped_sport
            dropped_sport += 1
            block.clear()
            return
        # "championne canadienne, 3e au World Combat Game" - the clause after
        # the comma is a placing at a DIFFERENT competition. The page's own
        # season heading says what this row is; the rest is reported, not filed.
        head, _, tail = title.partition(",")
        if tail.strip():
            report.problem(
                f"{block['name']}: the title line also claims "
                f"{tail.strip()!r}, which is another competition's result and "
                f"is not filed under this one")
        gender = ("Women" if _CA_WOMAN.search(head) else
                  "Men" if _CA_MAN.search(head) else "")
        if not gender:
            report.problem(f"{block['name']}: the title {head.strip()!r} says "
                           f"neither champion nor championne, so no gender")
        kilos, bound, printed_as = _ca_weight(block.get("weight", ""))
        if printed_as in ("band", "bare"):
            bands.append(" ".join(block.get("weight", "").split()))
        if not kilos:
            report.problem(f"{block['name']}: no weight class could be read "
                           f"from {block.get('weight', '')!r}")
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{len(rows) + 1:03d}",
            category=_label(kilos, bound, gender),
            gender=gender, age_class=meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound,
            rank="1", medal="gold",
            fighter=block["name"],
            country=home,
            club=block.get("club", ""),
            result_source="reported"))
        block.clear()

    for line in lines:
        found = _CA_SEASON.match(line)
        if found:
            flush()
            season, discipline = found.group("year"), found.group("what")
            other_sport_season = bool(_OTHER_SPORT.search(discipline))
            seasons.append(f"{discipline} {season}"
                           + (" [not savate]" if other_sport_season else ""))
            continue
        label = _CA_LABEL.match(line)
        if not label:
            continue
        if year_wanted and season != year_wanted:
            continue
        key = label.group("label").lower()
        value = " ".join(label.group("value").split())
        if key.startswith("nom"):
            flush()
            block["name"] = value
        elif key.startswith("titre"):
            block["title"] = value
        elif key.startswith("club"):
            block["club"] = value
        else:
            block["weight"] = value
    flush()

    report.notes.update(seasons_on_page=seasons, other_sport_rows=dropped_sport,
                        weight_bands=sorted(set(bands)))
    if dropped_sport:
        report.problem(f"{dropped_sport} champion(s) on this page are another "
                       f"sport's, not savate's, and are not filed here")
    if year_wanted and year_wanted not in {s.split()[-1] for s in seasons}:
        report.problem(f"the page carries no season {year_wanted!r}; it holds: "
                       f"{', '.join(seasons) or 'none'}")
    if rows:
        report.problem(
            "this page prints champions only: there is no runner-up and no "
            "bronze on it, so these rows are gold placings and not a podium")
        if bands:
            report.problem(
                f"these weights are printed as a band or a bare figure and "
                f"never as a bound ({', '.join(sorted(set(bands)))}); each is "
                f"read as the class ending at its upper figure, which is the "
                f"class a savate band describes, but the lower figure is not "
                f"stored and the page itself prints no sign")
        if discipline and "assaut" in discipline.lower():
            tournament.discipline = tournament.discipline or "assaut"
        if year_wanted:
            tournament.year = tournament.year or year_wanted
    return rows


# --------------------------------------------- layout 3: delegation medals --

# A placing tier, in the federations' own words. Matched against folded text,
# because Turkish "İkincilerimiz" lower-cases to an i with a combining dot that
# no plain pattern for "ikinci" would ever meet.
_TIER_WORDS = [
    (3, r"🥉|\bbronze\b|\bbronz\b|ucuncu|бронз|\b3rd\s+place\b|\b3\.\s*mesto"),
    (2, r"🥈|\bsilver\b|\bgumus\b|ikinci|срібн|сребр|віце|vice.?champion|"
        r"\b2nd\s+place\b"),
    (1, r"🥇|\bgold\b|\baltin\b|sampiyon|champion|winners?\b|чемпіон|переможц|"
        r"володар|\b1st\s+place\b"),
]
_MEDALS = {1: "gold", 2: "silver", 3: "bronze"}
_AGE_WORDS = [("Junior", r"junior|юніор|genc"), ("Senior", r"senior|дорослих|buyuk"),
              ("Young", r"youth|cadet|кадет|yildiz|minim")]
_HEADING_END = re.compile(r"[:：]\s*$")
_MEDAL_EMOJI = re.compile(r"^[\s•*\-–—]*[🥇🥈🥉]")
# " — ", " – ", " - ": the separator between a medallist and their weight. It
# must have space on both sides, so a hyphenated surname is never cut.
_MEDALLIST_SEP = re.compile(r"\s+[–—]\s+|\s+-\s+")


def _tier_of(folded):
    for rank, pattern in _TIER_WORDS:
        if re.search(pattern, folded, re.I):
            return rank
    return 0


def _is_tier_heading(line):
    from savate import normalize as norm

    text = " ".join(str(line or "").split())
    if not text or len(text) > 90:
        return 0
    if not (_HEADING_END.search(text) or _MEDAL_EMOJI.match(text)):
        return 0
    if _KG.search(text):
        return 0
    return _tier_of(norm.fold(text))


def _tiers_in(lines):
    """The headings that open a placing tier, with a medallist under each."""
    found = []
    for at, line in enumerate(lines):
        rank = _is_tier_heading(line)
        if not rank:
            continue
        if any(_medallist(lines[i])[0] for i in range(at + 1, min(at + 3,
                                                                 len(lines)))):
            found.append((at, rank, " ".join(line.split())))
    return found


def _medallist(line):
    """(name, tail) for a printed medallist line, or ("", "")."""
    text = " ".join(str(line or "").split())
    if not text or _HEADING_END.search(text):
        return "", ""
    text = _MEDAL_EMOJI.sub("", text).strip() if _MEDAL_EMOJI.match(text) \
        else text
    parts = _MEDALLIST_SEP.split(text, maxsplit=1)
    name = parts[0].strip(" .,;")
    tail = parts[1].strip() if len(parts) > 1 else ""
    if not looks_like_person(name):
        return "", ""
    # With no weight beside it, a bare name is only a medallist if nothing
    # else on the line contradicts it.
    if tail and not _KG.search(tail) and len(tail.split()) > 6:
        return "", ""
    return name, tail


def _delegation_medals(lines, slug, meta, report, tournament, options=None):
    from savate import normalize as norm

    home = _home(meta, options)
    rows, headings, unsigned = [], [], []
    dropped_sport, demos = 0, 0
    rank, heading_age, heading_text, sport = 0, "", "", "savate"

    for line in lines:
        tier = _is_tier_heading(line)
        if tier:
            if _OTHER_SPORT.search(line):
                rank, heading_age, sport = 0, "", "other"
                headings.append(" ".join(line.split()) + " [not savate]")
                continue
            sport = "savate"
            rank = tier
            heading_text = " ".join(line.split())
            headings.append(heading_text)
            ages = [age for age, pattern in _AGE_WORDS
                    if re.search(pattern, norm.fold(heading_text), re.I)]
            heading_age = ages[0] if len(ages) == 1 else ""
            if len(ages) > 1:
                report.problem(
                    f"the heading {heading_text!r} names more than one age "
                    f"class, so none is claimed for the medallists under it")
            # A bracket that only repeats the tier ("1st Place (Gold)") says
            # nothing new. One that does not - "(World Cup Kategorisi)" on a
            # page whose meet was a championship AND a cup - is the document
            # telling you these medals are not all from the same competition.
            inner = " ".join(re.findall(r"\(([^)]*)\)", heading_text))
            if inner and _tier_of(norm.fold(inner)) != tier:
                report.problem(
                    f"the heading {heading_text!r} qualifies its tier with "
                    f"{inner!r} - check the page names ONE competition before "
                    f"filing these")
            continue
        name, tail = _medallist(line)
        if sport == "other":
            # A tier heading named another sport. Its medallists are real
            # people with real medals - in a sport this archive does not hold.
            if name:
                dropped_sport += 1
            else:
                sport = "savate"
            continue
        if not rank:
            continue
        if not name:
            rank, heading_age = 0, ""      # the list ended; prose resumed
            continue
        if _OTHER_SPORT.search(line):
            dropped_sport += 1
            continue
        if _DEMO.search(line):
            demos += 1
            continue

        kilos, bound, stated = _weight(tail)
        if kilos and not stated:
            unsigned.append(" ".join(str(tail).split()))
        folded = norm.fold(tail)
        gender = ("Women" if re.search(r"women|femme|жінок|жінк|kadin|kiz",
                                       folded) else
                  "Men" if re.search(r"\bmen\b|homme|чолов|erkek", folded)
                  else "")
        ages = [age for age, pattern in _AGE_WORDS
                if re.search(pattern, folded, re.I)]
        age = ages[0] if len(ages) == 1 else heading_age
        rows.append(Placing(
            tournament=slug,
            placing_id=f"{slug}-{len(rows) + 1:03d}",
            category=_label(kilos, bound, tail if not kilos else ""),
            gender=gender, age_class=age or meta.get("age_class", ""),
            weight_kg=kilos, weight_bound=bound,
            rank=str(rank), medal=_MEDALS[rank],
            fighter=name, country=home,
            result_source="reported"))
        if not kilos:
            report.problem(f"{name}: the page gives no weight class for this "
                           f"medal, so the placing carries none")

    report.notes.update(tier_headings=headings, other_sport_rows=dropped_sport,
                        demonstrations=demos, unsigned_weights=unsigned)
    if dropped_sport:
        report.problem(f"{dropped_sport} medallist line(s) name another sport "
                       f"and are not filed as savate")
    if demos:
        report.problem(f"{demos} line(s) are demonstrations, which have no "
                       f"result and are not placings")
    if unsigned:
        report.problem(
            f"{len(unsigned)} medallist(s) have a weight printed without a "
            f"sign and without a word for the bound "
            f"({', '.join(sorted(set(unsigned)))}); each is read as the class "
            f"ending at that figure, which is "
            f"this archive's convention and not something this page states")
    if rows:
        report.problem(
            "this is one delegation's own medal report: it lists that "
            "federation's medallists and nobody else's, so it is a partial "
            "record of the competition and not its results"
            + (f" - every fighter here is filed as {home}'s, which the page "
               f"states collectively and never line by line" if home else ""))
    return rows


# ------------------------------------------------------------ layout 4: Wix --

_VS = re.compile(r"\bvs\b|\bVS\b", re.I)
_DEMO_COUNT = re.compile(r"(\d+)\s+(?:assauts?\s+)?en\s+d[ée]monstration", re.I)

# A bout sentence that announces a winner and then stops: "... VS RAIMBAULT
# ROMAIN (gwadaboxing club) vainqueur l'unanimité" with nothing after it. The
# name that finishes the sentence is on the page - the author pressed return
# mid-sentence and Wix made the tail its own paragraph, "RAIMBAULT ." - and
# joining the two back together prints what the page prints. The test is that
# the verdict word is followed by no capital: a line that names its winner
# ("vainqueur à la majorité CHAUMONT .") does not match and is never joined.
_DANGLING_VERDICT = re.compile(r"\bvainqueur\w*\b[^A-ZÀ-ÖØ-Þ]*$")

# Words that state a gender in French. This league writes its class as a letter
# glued to the figure - "M75", "M70", "+90" - and `antilles_bouts` expands that
# letter into a gender, on the strength of the "F-70KG" and "F 70" forms its
# own corpus prints beside it. THIS page prints neither those forms nor any of
# these words, and on this page alone "M75 ... +90" reads as moins/plus every
# bit as naturally as it reads as masculin. So a gender that came from the
# letter and not from a word is dropped, and the drop is reported.
_GENDER_WORD = re.compile(
    r"\bmasculins?\b|\bf[ée]minins?\b|\bf[ée]minines?\b|\bhommes?\b|"
    r"\bfemmes?\b|\bdames?\b|\bmessieurs\b|\bmesdames\b|"
    r"\bgar[çc]ons?\b|\bfilles?\b|\btireu(?:rs?|ses?)\b", re.I)


def _closed_up(paragraphs):
    """(paragraphs, joins), a bout sentence that wrapped put back together."""
    out, joins = [], []
    for text in paragraphs:
        if (out and _VS.search(out[-1]) and not _VS.search(text)
                and _DANGLING_VERDICT.search(out[-1])
                and len(text.split()) <= 4 and not re.search(r"\d", text)):
            joins.append(f"{out[-1]} + {text}")
            out[-1] = f"{out[-1]} {text}"
            continue
        out.append(text)
    return out, joins


def _drop_gender(rows, report):
    """Blank a gender no word on the page states; say which rows lost one."""
    losing = [r for r in rows if getattr(r, "gender", "")]
    if not losing:
        return
    for row in losing:
        row.category = " ".join(w for w in str(row.category).split()
                                if w != row.gender)
        row.gender = ""
    report.problem(
        f"{len(losing)} bout(s) carried a gender read out of the class letter "
        f"in \"M75\", \"M70\" and the rest; this page never writes masculin, "
        f"hommes or any other word for one, and its own \"+90\" line shows the "
        f"letter can as easily be moins - so no gender is kept")


def _wix_bouts(page, slug, meta, report, tournament, source):
    """Hand a Wix post's body to `antilles_bouts`, whose grammar this is.

    The body is rewritten as the Joomla article that adapter was built for -
    one paragraph per printed paragraph, nothing added and nothing reordered -
    so the bouts are read by the reader that already knows this league's
    twenty-odd ways of naming a winner, rather than by a second copy of it that
    would drift out of agreement within a season.
    """
    from savate.adapters import antilles_bouts

    paragraphs = wix_paragraphs(page)
    if not paragraphs:
        report.problem("this looks like a Wix post but its body is empty")
        return tournament, [], report

    paragraphs, joins = _closed_up(paragraphs)
    if joins:
        report.notes["closed_up"] = joins
        report.problem(
            f"{len(joins)} bout sentence(s) wrapped onto the next paragraph "
            f"and were closed up before being read ({'; '.join(joins)}); the "
            f"tail is printed text on the page, not a colour or a guess")

    headline = ""
    found = _H1.search(page) or _TITLE.search(page)
    if found:
        headline = _plain(found.group(1)).split(" | ")[0].strip()

    document = ("<html><body>"
                f"<h1 itemprop=\"headline\">{html.escape(headline)}</h1>"
                "<div itemprop=\"articleBody\">"
                + "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
                + "</div><div></div></body></html>")

    handle = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8")
    try:
        handle.write(document)
        handle.close()
        theirs, rows, their_report = antilles_bouts.read(handle.name, slug,
                                                         meta)
    finally:
        Path(handle.name).unlink(missing_ok=True)

    for problem in their_report.problems:
        report.problem(f"{antilles_bouts.NAME}: {problem}")
    if not _GENDER_WORD.search(" ".join(paragraphs)):
        _drop_gender(rows, report)
    report.notes.update(their_report.notes)
    report.notes["delegated_to"] = antilles_bouts.NAME
    report.read = len(paragraphs)

    # The article counts its own exhibitions without listing them, so no row
    # was dropped for them and none could be - but the count is a fact the
    # document states about itself and is worth keeping.
    claimed = _DEMO_COUNT.search(" ".join(paragraphs))
    if claimed:
        report.notes["demonstrations_claimed"] = int(claimed.group(1))
        report.problem(
            f"the article says {claimed.group(1)} of the assauts were "
            f"demonstrations; it does not list them, so none is in these rows")

    tournament = _tournament(slug, meta, source,
                             name=theirs.name, discipline=theirs.discipline,
                             start_date=theirs.start_date,
                             end_date=theirs.end_date, city=theirs.city,
                             year=theirs.year)
    report.notes["bouts"] = sum(1 for r in rows if isinstance(r, Bout))
    report.notes["placings"] = sum(1 for r in rows if isinstance(r, Placing))
    report.notes["layout"] = "wix_bouts"
    if not rows:
        report.problem("the wix_bouts reader found nothing to read")
    return tournament, rows, report


# ------------------------------------------------------- the site bundle ----

_MONTHS = ("january|february|march|april|may|june|july|august|september|"
           "october|november|december")
_SPAN = re.compile(
    rf"\b(?:from\s+|on\s+)?(?P<month>{_MONTHS})\s+(?P<first>\d{{1,2}})"
    rf"(?:\s*(?:to|through|[-–—])\s*(?P<last>\d{{1,2}}))?,?\s+"
    rf"(?P<year>(?:19|20)\d{{2}})\b", re.I)


def _english_span(text):
    """(start, end) ISO dates from "From October 3 to 5, 2025", or ("", "")."""
    from savate import normalize as norm

    found = _SPAN.search(str(text or ""))
    if not found:
        return "", ""
    month, year = found.group("month"), found.group("year")
    start = norm.date(f"{month} {found.group('first')}, {year}")
    end = norm.date(f"{month} {found.group('last')}, {year}") \
        if found.group("last") else start
    return start, end or start


def _from_bundle(bundle, wanted, slug, meta, report, tournament, source,
                 options=None):
    """One article out of a single-page site's JavaScript bundle."""
    from savate import normalize as norm

    articles = posts_in(bundle)
    report.notes["articles_in_bundle"] = [a["title"] for a in articles]
    report.read = len(articles)
    if not wanted:
        report.problem(
            f"this site keeps {len(articles)} articles in one bundle and no "
            f"article was named - set the entry's \"event\" key to one of "
            f"them")
        return tournament, [], report

    key = norm.fold(wanted)
    hits = [a for a in articles
            if norm.fold(a["title"]) == key or key in norm.fold(a["title"])
            or a["id"] == wanted]
    if not hits:
        report.problem(f"the bundle holds no article matching {wanted!r}")
        return tournament, [], report
    if len(hits) > 1:
        report.problem(
            f"{wanted!r} matches {len(hits)} of the bundle's articles "
            f"({'; '.join(a['title'] for a in hits)}); the first is read")
    article = hits[0]
    report.notes["article"] = article["title"]
    report.notes["article_published"] = article["date"]

    lines = lines_of(article["body"])
    if not lines:
        report.problem(f"the article {article['title']!r} has no text")
        return tournament, [], report

    start, end = _english_span(" ".join(lines[:4]))
    if start:
        tournament.start_date = tournament.start_date or start
        tournament.end_date = tournament.end_date or end
        tournament.year = tournament.year or start[:4]
    else:
        report.problem("the article's prose gives no date this reader can "
                       "read, so the competition is undated")
    tournament.name = tournament.name if meta.get("name") else article["title"]

    return _dispatch(article["body"], lines, "", slug, meta, report,
                     tournament, source, options)

