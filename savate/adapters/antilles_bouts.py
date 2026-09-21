"""The Ligue de Guadeloupe's results articles: one bout per sentence.

For ten years the Guadeloupe league published its results as prose. A Joomla
article, a paragraph per bout, written by whoever ran the desk that afternoon:

    HUGO CHARLES (gwadaboxingclub) VS POUVAIT HERVICK (boxingclubgoyave)
    vainqueur: HUGO à l'unanimité des juges

There is no table, no column, no export. What there is instead is a grammar
that holds across twenty-odd articles from 2013 to 2022 - two names either side
of VS, a club in brackets after each, then a verdict naming the winner - and
that grammar is the only record of French Caribbean savate in this archive. It
is also the only place Martinique appears at all: KBCM, savate des caps and
aquaboxe travel to Guadeloupe and their fighters are named nowhere else.

The grammar varies more than a regular expression likes, and every variation
below was read off a real article rather than imagined:

    NAME (club) VS NAME (club) vainqueur : SURNAME à l'unanimité des juges
    F-70KG NAME CLUB VS NAME CLUB : SURNAME VAINQUEUR UNANIMITE DES JUGES
    -M-80KG NAME CLUB VS NAME CLUB : VAINQUEUR SURNAME MAJORITE DES JUGES
    - F55 NAME (club) VS NAME (club) gagnante : SURNAME à l'unanimité
    NAME (club) VS NAME (club) : vainqueur à la majorité FORENAME SURNAME M70
    NAME (club) VS NAME (club) , SURNAME à l'unanimité des juges
    NAME (club) VS NAME (club) = SURNAME à l'unanimité
    NAME (club) VS NAME (club)                    <- the verdict is on the NEXT line
    FORENAME SURNAME ... du kana savate gosier VS NAME (club) ; victoire de Nancy

So the winner is named by surname, by forename, or by both; the verdict word
comes before the name, after it, or is missing entirely; the club is bracketed,
or is not; the separator is a colon, a comma, a semicolon, an equals sign or
nothing at all. Rather than enumerate that, this adapter cuts each line into a
pairing and a verdict, reads the two fighters out of the pairing, and then asks
the only question that matters: *which of these two people does the verdict
name?* The winner is scored against the two fighters already read, so a winner
this adapter cannot tie to one of them is not a winner - the bout is stored
unresolved and the article is reported. That is what keeps a typo (VAUCHER for
VAUCHEL, ROSEMEND for ROSEMOND, BANABDELBARI for BENABDELBARI - all real, all in
these articles) from quietly becoming a third person with a career.

Four things in these articles are not bouts, and each one has to be recognised
or the archive gains rows that never happened:

*Demonstrations.* An exhibition has no result. Sometimes they are gathered under
a heading ("EN DEMO", "Pour les démonstrations merci à ;", "2 assauts
démonstration"), sometimes a single line sits in the middle of the real ones
("DEMO BOULATE EMRICK (ying yang) et DDELOUMEAUX NAYAN", "DEMO/ VITALIS CANDICE
VS HOCQUINGHEN ALIA"). They produce no row and are counted in the report.

*Boxe anglaise.* Four of these articles are gala cards carrying English boxing
as well as savate, in identical prose, under their own heading. One of them
prints the boxing first and at greater length than the savate. A parser that
ignores headings files five English-boxing bouts as savate before it reaches a
single real one, so the sport is tracked by heading and non-savate rows are
dropped and counted. Canne de combat, chausson, bâton and savate forme are
dropped the same way.

*Non-decisions.* "NON DECISION (3 avertissements pour les 2 tireuses)" and
"annulé sur problème physique" are real bouts between two real people that no
one won. They are stored unresolved, with their warnings, because a result
nobody published is not the same as a result of zero - and because the warnings
are the second rung of the poule ranking ladder.

*Per-fighter tallies.* Two articles give each competitor's record for the day
("BOULATE JORICK 2 assauts 2 défaites") with no opponents at all. No pairing
exists to reconstruct, and inventing one would be fabrication. They are reported
as unreadable, not parsed.

Corners are not claimed. Red and blue mean corner in this archive and these
articles never say who stood where; red here is simply whoever was named first,
so `winner` is filled and `winner_corner` is left empty.

Six of these cards ran assaut and combat on the same night. A bout row has no
discipline field, so each bout carries it in `category` ("Assaut Women -70 kg",
"Combat Junior Men -65 kg") and the tournament is left without one rather than
being told it was all assaut. Where a caller wants the two halves as separate
competitions, `read(..., discipline="combat")` reads only that half - the same
shape `cesav_ranking` uses to pull one championship off a page holding nine.
"""

import html
import re
import unicodedata
from datetime import date as _calendar_date

from savate import normalize
from savate.schema import Bout, Report, Tournament, check, phase_of

NAME = "antilles_bouts"
DESCRIPTION = "Ligue de Guadeloupe prose bout lines (Joomla articles, 2013-2022)"


# ---------------------------------------------------------------- page ------

_ARTICLE = re.compile(
    r'<div[^>]*itemprop=["\']articleBody["\'][^>]*>(.*?)(?=<div\b|</article)',
    re.S | re.I)
# The same opening tag with nothing recognisable after it. The live pages all
# carry a sibling <div>, but a capture that lost its footer would otherwise read
# as an article with no bouts in it, which looks exactly like an article that
# has none - the one confusion this archive most needs to avoid.
_ARTICLE_TAIL = re.compile(
    r'<div[^>]*itemprop=["\']articleBody["\'][^>]*>(.*)', re.S | re.I)
_HEADLINE = re.compile(r'<h\d[^>]*itemprop=["\']headline["\'][^>]*>(.*?)</h\d>',
                       re.S | re.I)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_BREAK = re.compile(r"<\s*br\s*/?>", re.I)
_BLOCK_END = re.compile(r"</\s*(?:p|div|li|h\d|tr|td|blockquote)\s*>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def _headline(page):
    """What the article calls itself: its own headline, or the page title.

    The site appends " - Ligue de Guadeloupe de Savate Boxe Française" to every
    title; the headline above the article does not carry it, so the headline is
    preferred and the title is trimmed at that dash when it has to stand in.
    """
    found = _HEADLINE.search(page or "")
    if found:
        return _plain(found.group(1))
    found = _TITLE.search(page or "")
    if found:
        return _plain(found.group(1)).split(" - ")[0].strip()
    return ""


def _plain(fragment):
    text = html.unescape(_TAGS.sub(" ", fragment or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _lines(page):
    """The article body, one printed paragraph per line."""
    found = _ARTICLE.search(page) or _ARTICLE_TAIL.search(page)
    fragment = found.group(1) if found else ""
    fragment = _BLOCK_END.sub("\n", _BREAK.sub("\n", fragment))
    fragment = html.unescape(_TAGS.sub("", fragment)).replace("\xa0", " ")
    out = []
    for line in fragment.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line and line not in {".", "-"}:
            out.append(line)
    return out


# ---------------------------------------------------------------- words -----

def _fold(text):
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _key(text):
    return re.sub(r"[^a-z0-9]+", "", _fold(text))


# The pairing separator. The second alternative catches "VSREMACHE BRAHIM",
# where the space after VS was never typed: it still has to begin a word, and
# what follows it has to be capitals, so it cannot cut a name in half. Reading
# it matters even though that one line is English boxing - a pairing this
# adapter cannot see is a pairing it cannot exclude by sport either.
_VS = re.compile(r"(?<![0-9A-Za-zÀ-ÿ])vs(?![0-9A-Za-zÀ-ÿ])|"
                 r"(?<![0-9A-Za-zÀ-ÿ])vs(?=[A-ZÀ-Þ]{3,})", re.I)

# The verdict word, in every spelling these articles use - vainqueur, VAINQUEUR
# and the typo vaibnqueur - plus the feminine gagnante, which four women's
# bouts in the 2019 international gala are announced with and which a parser
# keying only on "vainqueur" loses entirely.
_VERDICT_WORD = re.compile(r"\bva[a-z]{1,3}queure?\b|\bgagnante?\b|\bvictoire\b",
                           re.I)

# What ends the pairing and begins the verdict, outside brackets.
_SEPARATORS = ":;,="

# How the bout ended, in the article's own words. Read in order, so the more
# specific arrêt clauses are recognised before the bare ones. The typos are the
# articles' own: "inanimité", "unamité".
# The patterns match whole words, because what they match is what is stored:
# decision_detail is the source's own word, so a bout the article calls an
# "inanimité" is filed as an inanimité, not as the adapter's tidier spelling.
# The canonical decision beside it comes from normalize.decision(), which is
# the archive's shared reading of this same vocabulary; the fallback here is
# only for "arrêt" standing alone, which that table does not yet know.
_DECISIONS = [
    ("abandon", r"arr[êe]t\s+de\s+l.?\s*arbitre"),
    ("abandon", r"arr[êe]t\s+du\s+d\.?\s*o\.?"),
    ("abandon", r"arr[êe]t\s+(?:de|du)\s+coach"),
    ("abandon", r"jet\s+de\s+l.?\s*[ée]ponge"),
    ("disqualification", r"\bdisqualif\w*"),
    ("forfait", r"\bforfait\b|\bw\.?\s?o\.?\b"),
    ("abandon", r"\babandon\w*"),
    ("abandon", r"\barr[êe]ts?\b"),
    # The article's spelling of "unanimité" varies: inanimité, unamité,
    # unaimité all appear. Keying on the exact word loses four real bouts, so
    # the middle of it is allowed to wander between the un- and the -mité.
    ("points", r"\b[iu]n[a-z]{0,4}mit[ée]s?\b"),
    ("points", r"\bmajorit[ée]s?\b"),
    ("points", r"\bpartages?\b"),
]

# A competitor's record for the day, with no opponent named: "BOULATE JORICK 2
# assauts 2 défaites". Two articles give a whole morning session this way. There
# is no pairing to read and inventing one would be fabrication - but passing
# over them in silence files the competition as the afternoon alone, so they are
# reported. The count has to follow a fighter's name and the line has to say
# how it went, so neither "certain jeunes ont fait 2 assauts, disputés en 3 x 1
# minute" nor a card summary reading "5 assauts dont 4 féminin ... sur une
# défaite" is mistaken for one.
_TALLY = re.compile(r"(?:[A-ZÀ-Þ][A-ZÀ-Þ'\-]{2,}\s+){1,3}"
                    r"(?:\([^)]{0,20}\)\s*)?\d+\s*assauts?\b")
_TALLY_RESULT = re.compile(r"\bvictoires?\b|\bd[ée]faites?\b|\bnuls?\b", re.I)

# "Ont participé aux assauts sans décision :" and the club-by-club lists of
# names under it. Real competitors, in real bouts, whose results nobody
# published - and fifteen of them in one 2022 article.
_UNDECIDED_SECTION = re.compile(r"sans\s+d[ée]cis[io]?on", re.I)
_ROSTER = re.compile(r"^\s*pour\s+l[eas]s?\b[^:]{0,40}:", re.I)

# A bout that happened and that nobody won. Not the same as a demonstration and
# not the same as a missing verdict: the article states the non-result.
_NO_DECISION = re.compile(r"\bnon\s*d[ée]cision|\bsans\s+d[ée]cision|"
                          r"\bannul[ée]|\bpas\s+de\s+d[ée]cision|\bmatch\s+nul",
                          re.I)

# Warnings, but only where the article says plainly that both fighters carried
# the same number. "2 avertissements contre 1" does not say which fighter had
# which, and is reported rather than split by guesswork.
_WARNINGS_BOTH = re.compile(
    r"(\d+)\s*avertissements?\s+(?:pour\s+)?(?:chaque|les\s*2|les\s*deux|"
    r"chacune?|par)\s*(?:tireur|tireuse)?", re.I)
_WARNINGS_UNCLEAR = re.compile(r"\d+\s*avertissements?\s+contre\s+\d+", re.I)

# An exhibition. "DEMO/", "DEMO ", "Démo féminine", "En démonstration".
_DEMO_LINE = re.compile(r"^\s*[-–—•*]?\s*(?:en\s+|\d+\s+)?d[ée]mo", re.I)
_DEMO_WORD = re.compile(r"\bd[ée]mos?\b|\bd[ée]monstration", re.I)
# A run of words set in capitals - how a fighter is written here. Two runs on a
# demonstration line means two people were named, so an exhibition took place
# and is counted; "EN DEMO" or "2 assauts démonstration" name nobody and are
# only the heading over the ones that follow.
_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ][0-9A-Za-zÀ-ÿ'\-]*")

# Sports that are not savate. The gala cards carry English boxing in identical
# prose; the rest are listed because a league that runs them could publish them
# the same way, and a row filed under the wrong sport is worse than no row.
_SPORTS = [
    ("boxe anglaise", r"boxe\s+anglaise|english\s+boxing|boxing\s+anglais"),
    ("canne de combat", r"\bcanne\b|\bb[âa]ton\b|\bchausson\b"),
    ("savate forme", r"savate\s+forme|\bfitness\b"),
    ("savate défense", r"savate\s+d[ée]fense"),
    ("savate", r"boxe\s+fran[çc]aise|\bsavate\b|\bb\.?f\.?\b"),
]

_DISCIPLINES = [("assaut", r"\bassauts?\b"), ("combat", r"\bcombats?\b")]

# Gender as these articles state it: a class ("ASSAUT FEMININ ADULTE", "F-70KG")
# or a plain statement of who fought ("2 tireuses ... ont disputé un assaut",
# "RILCY NANCY notre jeune féminine du jour"). Not "gagnante": that is the
# verdict's own verb, and a bout does not become a women's bout because the
# article conjugated the word for winner. Where this table is read matters as
# much as what is in it - see _fill_category, which keeps it out of the verdict.
_GENDERS = [
    ("Women", r"\bf[ée]minin(?:e|es|s)?\b|\bfilles?\b|\bdames?\b|"
              r"\bfemmes?\b|\btireuses?\b"),
    ("Men", r"\bmasculins?\b|\bgar[çc]ons?\b|\bhommes?\b"),
]

_AGES = [
    ("Poussin", r"\bpoussins?\b"),
    ("Benjamin", r"\bbenjamins?\b"),
    ("Minime", r"\bminimes?\b"),
    ("Cadet", r"\bcadets?\b"),
    ("Junior", r"\bjun[iu]?[uo]?iors?\b"),
    ("Vétéran", r"\bv[ée]t[ée]rans?\b"),
    ("Senior", r"\bs[ée]niors?\b"),
]

# A weight class. The article prints the bound ("-70 kg", "+85"), sometimes with
# the gender glued to the front ("F-70KG", "M65", "F 70"), sometimes with the
# sign on the outside ("-M-80KG"). A bare figure is only read as a weight when
# something corroborates it - a "kg", a gender letter or a sign - so that
# "3x1'30", "16 ans" and "2 avertissements" are not filed as weight classes.
_WEIGHT = re.compile(
    r"(?<![0-9A-Za-zÀ-ÿ])(?P<pre>[-+])?\s*(?P<sex>[FM])?\s*(?P<sign>[-+])?\s*"
    r"(?P<kg>\d{2,3})\s*(?P<unit>k\s?gs?\b|k\s?g\.)?(?![0-9A-Za-zÀ-ÿ])",
    re.I)

_ROUNDS = re.compile(r"\d+\s*x\s*\d+\s*['′]?\s*\d*")

# Words that may stand in front of a fighter's name and are not part of it.
_PREFIX_WORDS = re.compile(
    r"^(?:match|assauts?|combats?|finales?|demi[\s-]?finales?|poules?|"
    r"r[ée]sultats?|cat[ée]gorie|[ée]ducatif|amateurs?|officiels?|exhibition|"
    r"en|un|une|le|la|les|de|du|des|d|et|au|aux|chez|pour|avec|entre|s[ée]rie|"
    r"place|adultes?|jeunes?|mixtes?|"
    r"f[ée]minines?|f[ée]minins?|masculins?|filles?|gar[çc]ons?|dames?|"
    r"hommes?|femmes?|"
    r"poussins?|benjamins?|minimes?|cadets?|jun[iu]?[uo]?iors?|espoirs?|"
    r"v[ée]t[ée]rans?|s[ée]niors?)(?![0-9A-Za-zÀ-ÿ])", re.I)

# A round the line names outright. Bounded, so a fighter called DEMILLE is not
# read as a demi-finale.
_PHASE_HERE = re.compile(r"\bfinales?\b|\b3\s*[èe]me\s+place\b|"
                         r"\bdemi[\s-]?finales?\b", re.I)

_ORDINAL = re.compile(r"^\d{1,2}\s*(?:er|[èe]re|[èe]me|e)(?![0-9A-Za-zÀ-ÿ])",
                      re.I)

# Tokens that carry no evidence about which fighter won, because they are also
# the vocabulary of a verdict. A fighter really called JUNIOR exists in this
# corpus ("BARLAGNE JUNIOR"), so his surname must not be allowed to win a bout
# because the line happened to print "catégorie junior".
_UNHELPFUL = {
    "junior", "senior", "cadet", "minime", "benjamin", "poussin", "veteran",
    "categorie", "combat", "combats", "assaut", "assauts", "feminin", "feminine",
    "masculin", "club", "reprise", "reprises", "juges", "arret", "abandon",
    "disqualification", "unanimite", "majorite", "points", "eponge", "jet",
    "coach", "savate", "boxe", "vainqueur", "gagnante", "gagnant", "victoire",
    "demo", "demonstration", "les", "des", "une", "sur", "par", "pour", "avec",
    "garcon", "garcons", "fille", "filles", "homme", "hommes", "femme",
    "femmes", "dame", "dames", "tireur", "tireurs", "tireuse", "tireuses",
    "adulte", "adultes", "jeune", "jeunes", "finale", "finales", "match",
    "place", "resultat", "resultats", "poule", "non", "decision", "serie",
    "unanimite", "inanimite", "unamite", "majorite", "clubs", "presents",
}

# Clubs these articles name. Most lines put the club in brackets and need none
# of this; the 2017 Karukera challenge prints "MICHELY MANUELLA GWADABOXING
# CLUB" with no punctuation at all, and one 2015 line buries the club in prose
# ("notre jeune féminine du jour du kana savate gosier"). Every spelling here
# was read off these same articles - it is a lexicon of what the source prints,
# not an outside list, and a name it cannot split is left whole rather than cut
# at a guess.
_CLUB_LEXICON = [
    "dynamik contact du gosier", "dynamik contact gosier", "dynamik contact",
    "dynamikcontact", "gwadaboxing club abymes", "gwadaboxing club",
    "gwadaboxingclub", "gwadaboxing des abymes", "gwadaboxing", "gbc",
    "moule savate club", "moule savate", "phenix club basse-terre",
    "phenix boxe", "phenix club", "phenix", "boxing club de goyave",
    "boxingclub goyave", "boxingclubgoyave", "boxing club goyave", "us goyave",
    "karukera fighting system", "karukerafightingsystem", "karu fight system",
    "karufight", "kfs", "savate boxing club 971", "savateboxingclub971",
    "savateboxing971", "samourai kreyol", "samourai krezyol",
    "ying yang control", "ying-yang control", "ying yang",
    "kana savate gosier", "kana savate club", "kana savate",
    "west indies savate", "west indies",
    "kbc martinique", "kbcmartinique", "kbcm", "savate des caps martinique",
    "savate des caps", "aquaboxe martinique", "aqua boxe", "aquaboxe",
    "escouade montreal", "escouademontreal", "club120paris", "badsabox",
    "academie de boxes de charenton", "sainte-anne martinique",
]

_FRENCH_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}
_WEEKDAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4,
             "samedi": 5, "dimanche": 6}
_WEEKDAY_WORD = re.compile(
    r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b", re.I)

_LONG_DATE = re.compile(
    r"(?:\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b\s*)?"
    r"(?<![0-9/])(\d{1,2})(?:er)?\s+"
    r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|"
    r"octobre|novembre|d[ée]cembre)\s+(\d{4,5})(?![0-9])", re.I)
_NUMERIC_DATE = re.compile(r"(?<![0-9])(\d{1,2})[/.](\d{1,2})[/.](\d{4,5})"
                           r"(?![0-9])")
_BARE_YEAR = re.compile(r"(?<![0-9])(20[0-3]\d)(?![0-9])")

_MIN_YEAR, _MAX_YEAR = 2005, 2030


# ------------------------------------------------------------- the date -----

def _make_date(day, month, year_text, weekday, report):
    """(ISO date, was the printed weekday checked here?), or ("", False).

    Two of these articles print a five-digit year: "Samedi 18 avril 20145" and
    a headline reading "04/06/20416". A digit has plainly been typed twice, and
    for a while this adapter deleted one and kept the year that was left - which
    is how nine rows came to be dated 2015 and twelve 2016, in two articles
    where neither string appears anywhere. A typo is not a date. Both are now
    left unread and reported, and the articles keep their bouts and lose their
    year: 20145 is what the source says, and 2015 is what somebody worked out.

    Where a date is whole and the weekday beside it is the wrong one, the date
    is still what the article states; the slip is reported, not repaired.
    """
    if len(year_text) != 4:
        report.problem(
            f"the date is printed as {day}/{month}/{year_text}, and "
            f"{year_text!r} is not a year - a digit has been typed twice. "
            f"Which year was meant is not something this article says, so the "
            f"date is left unread rather than repaired by deleting a digit")
        return "", False
    year = int(year_text)
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        report.problem(f"the year is printed as {year_text!r}, which is outside "
                       f"{_MIN_YEAR}-{_MAX_YEAR}; the date is left unread")
        return "", False
    try:
        when = _calendar_date(year, month, day)
    except ValueError:
        report.problem(f"the date {day}/{month}/{year_text} as printed is not a "
                       f"day of any month; it is left unread")
        return "", False
    if weekday and _WEEKDAYS.get(_fold(weekday)) != when.weekday():
        report.problem(
            f"the article dates itself {when.isoformat()} but calls it a "
            f"{_fold(weekday)}, which it was not; the date is kept as printed")
        return when.isoformat(), True
    return when.isoformat(), bool(weekday)


def _read_date(text, report):
    """(ISO date, was a printed weekday checked against it?)."""
    found = _LONG_DATE.search(text or "")
    if found:
        weekday, day, month, year = found.groups()
        key = _fold(month).replace("û", "u")
        return _make_date(int(day), _FRENCH_MONTHS[_fold(key)], year,
                          weekday, report)
    found = _NUMERIC_DATE.search(text or "")
    if found:
        day, month, year = found.groups()
        if 1 <= int(month) <= 12:
            return _make_date(int(day), int(month), year, "", report)
    return "", False


def _stated_weekdays(lines):
    """The weekdays the article names on their own, in order of appearance.

    A weekday that dates something itself - "Samedi 14 juin 2014" - is not one
    of these: it is read with its date, where it belongs. What is left is the
    article talking about the day it is describing ("en ce samedi apres-midi",
    "un assaut féminin a clôturé ce dimanche de compétition"), which is a fact
    the source states about the date at the top of the page.
    """
    out = []
    for line in lines:
        for found in _WEEKDAY_WORD.finditer(line):
            after = line[found.end():found.end() + 40].strip()
            if _LONG_DATE.match(after) or _NUMERIC_DATE.match(after):
                continue
            name = _fold(found.group(1))
            if name not in out:
                out.append(name)
    return out


def _check_weekday(when, lines, report):
    """Report a date the article's own weekday contradicts.

    This used to run only where the weekday was printed against the date, so
    the long-form articles were checked and the ones dated "22/11/2019" in
    their headline were not - and thirteen rows carried a Friday under a line
    reading "en ce samedi apres-midi", with nothing said. The check belongs to
    the document, not to one way of writing a date down.
    """
    days = _stated_weekdays(lines)
    if len(days) != 1 or days[0] not in _WEEKDAYS:
        return
    printed = _WEEKDAYS[days[0]]
    actual = _calendar_date.fromisoformat(when).weekday()
    if printed != actual:
        was = next(name for name, index in _WEEKDAYS.items() if index == actual)
        report.problem(
            f"the document dates itself {when}, which was a {was}, but its own "
            f"text calls the day a {days[0]}; the date is kept as printed and "
            f"the two do not agree")


# ---------------------------------------------------------------- names -----

def _tidy(text):
    """Trim the punctuation an article leaves round a name or a club.

    The unmatched bracket is not fussiness: one 2019 line prints "TRAMIS
    MATHIEU dynamikcontact) VS ..." with the opening bracket never typed, and a
    club stored as "dynamikcontact)" is a club of its own for ever - it can
    never join the eight other dynamikcontact rows in this archive.
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    for _pass in range(2):
        text = re.sub(r"^[\s:;,.\-–—•*/=]+", "", text)
        text = re.sub(r"[\s:;,.\-–—•*/=]+$", "", text)
        if text.endswith(")") and "(" not in text:
            text = text[:-1]
        if text.startswith("(") and ")" not in text:
            text = text[1:]
        text = text.strip()
    return text


def _destutter(name):
    """"BOULATE BOULATE EMRICK" -> "BOULATE EMRICK".

    A word typed twice in a row is a slip of the keyboard, not a double-barrelled
    name; no fighter in this corpus repeats a name part. Nothing else about the
    name is touched.
    """
    words, out = name.split(), []
    for word in words:
        if out and _key(out[-1]) == _key(word):
            continue
        out.append(word)
    return " ".join(out)


def _looks_like_name(word):
    letters = [c for c in word if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _split_club(text, lexicon):
    """(name, club) - the club is the longest known one the text ends with.

    The club is returned as this article spells it, not as the lexicon does.
    The lexicon exists to find the boundary; what is stored either side of it
    is what the source printed, down to its own capitals and misspellings.
    """
    text = _tidy(text)
    if not text:
        return "", ""
    squeezed = _key(text)
    for folded, _printed in lexicon:
        if len(folded) >= 3 and squeezed.endswith(folded):
            kept, seen = [], 0
            for ch in reversed(text):
                if seen >= len(folded):
                    kept.append(ch)
                elif ch.isalnum():
                    seen += 1
            name = "".join(reversed(kept))
            return _tidy(name), _tidy(text[len(name):])
    return text, ""


def _find_club(text, lexicon):
    """A club named somewhere inside prose, as that prose spells it.

    One 2015 line buries the club in a sentence - "RILCY NANCY notre jeune
    féminine du jour du kana savate gosier VS ..." - where there is no boundary
    to split on, only a club name to recognise.
    """
    places = [i for i, ch in enumerate(text) if ch.isalnum()]
    squeezed = _key(text)
    if len(places) != len(squeezed):
        return ""
    for folded, _printed in lexicon:
        if len(folded) < 5:
            continue
        at = squeezed.find(folded)
        if at < 0:
            continue
        return _tidy(text[places[at]:places[at + len(folded) - 1] + 1])
    return ""


def _competitor(text, lexicon):
    """(name, club) for one side of a pairing.

    Brackets answer it outright where the article uses them. Where it does not,
    the fighter's name is the leading run of words set in capitals - every name
    in this corpus is - and the club is looked up in what follows. A club the
    lexicon does not hold leaves the name whole and unsplit, which is the honest
    answer: a name that may carry a club is better than a name cut at a guess.
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return "", ""
    bracket = re.search(r"\(([^)]*)\)", text)
    if bracket:
        name = _tidy(text[:bracket.start()])
        club = _tidy(bracket.group(1))
        if name:
            return _destutter(name), club
    words = text.split()
    head = []
    for index, word in enumerate(words):
        if _looks_like_name(word):
            head.append(word)
            continue
        break
    else:
        index = len(words)
    name, club = _split_club(" ".join(head), lexicon)
    rest = " ".join(words[index:])
    if not club and rest:
        club = _split_club(rest, lexicon)[1] or _find_club(rest, lexicon)
    if not name:
        name, club2 = _split_club(text, lexicon)
        club = club or club2
    return _destutter(_tidy(name)), club


def _tokens(name):
    """The parts of a name that can carry evidence about who won."""
    out = []
    for word in re.split(r"[^0-9A-Za-zÀ-ÿ]+", _fold(name)):
        if len(word) >= 3 and word not in _UNHELPFUL:
            out.append(word)
    return out


def _distance(a, b):
    """Edit distance between two words, given up once they are far apart."""
    if abs(len(a) - len(b)) > 2:
        return 9
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1,
                           previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]


def _name_the_winner(tail, red, blue):
    """("red"|"blue"|"", how) - which fighter the verdict names.

    The verdict is never trusted to be a clean name. It is compared against the
    two fighters already read, and the side whose name the verdict repeats wins.
    Where neither is repeated exactly, one edit is allowed, because these
    articles misspell the winner often enough that refusing would lose real
    bouts - but only where exactly one fighter is within reach. A tie, or
    nothing at all, means the winner is unknown, and an unknown winner is
    reported, not chosen.
    """
    said = _tokens(tail)
    if not said:
        return "", ""
    scores = {}
    for corner, name in (("red", red), ("blue", blue)):
        scores[corner] = sum(1 for token in _tokens(name) if token in said)
    if scores["red"] != scores["blue"] and max(scores.values()) > 0:
        return ("red" if scores["red"] > scores["blue"] else "blue"), "named"

    if max(scores.values()) == 0:
        near = {}
        for corner, name in (("red", red), ("blue", blue)):
            hits = []
            for token in _tokens(name):
                if len(token) < 5:
                    continue
                for spoken in said:
                    if len(spoken) >= 5 and _distance(token, spoken) == 1:
                        hits.append((spoken, token))
            near[corner] = hits
        if bool(near["red"]) != bool(near["blue"]):
            corner = "red" if near["red"] else "blue"
            spoken, token = near[corner][0]
            return corner, f"{spoken} read as {token}"
    return "", ""


# ------------------------------------------------------------ categories ----

def _weight_of(text):
    """(kg, bound, gender, the matched text) for the first weight class."""
    for found in _WEIGHT.finditer(text or ""):
        pre, sex, sign, kilos, unit = found.group(
            "pre", "sex", "sign", "kg", "unit")
        if not (unit or sex or sign or pre):
            continue
        value = int(kilos)
        if not 20 <= value <= 150:
            continue
        bound = "over" if (sign or pre) == "+" else "under"
        gender = {"F": "Women", "M": "Men"}.get((sex or "").upper(), "")
        return str(value), bound, gender, found.group(0)
    return "", "", "", ""


def _first(table, text):
    for value, pattern in table:
        if re.search(pattern, text or "", re.I):
            return value
    return ""


def _label(context):
    """The category string, built from what the article actually stated."""
    parts = []
    if context.get("discipline"):
        parts.append(context["discipline"].title())
    if context.get("age_class"):
        parts.append(context["age_class"])
    if context.get("gender"):
        parts.append(context["gender"])
    if context.get("weight_kg"):
        sign = "+" if context.get("weight_bound") == "over" else "-"
        parts.append(f"{sign}{context['weight_kg']} kg")
    return " ".join(parts)


# ------------------------------------------------------------ the parser ----

def _fill_category(context, pairing_text, blue_text, tail):
    """Complete the class from wherever else on the line it was printed.

    The prefix is the usual place, but three articles put the class after the
    clubs ("- 85 kg vainqueur FRANCILLETTE"), one puts it at the end of the
    verdict ("vainqueur à la majorité GUEIBA GREGORY M70"), and one states the
    age class inside the verdict ("catégorie junior -85kg"). None of that is
    guessed: each is read from the line, and where the line is silent the field
    stays empty.

    Gender is read from the pairing only - the class in front of it, the two
    fighters and their clubs - and never from the verdict clause. A weight
    class written "F55" states a gender; "NON DECISION (3 avertissements pour
    les 2 tireuses)" is French grammar in a sentence about warnings, and one
    row of eleven was once stamped Women by it while its ten sisters, on the
    same women's card, were not.
    """
    if not context.get("weight_kg"):
        for where in (blue_text, tail):
            kilos, bound, gender, _printed = _weight_of(where)
            if kilos:
                context["weight_kg"] = kilos
                context["weight_bound"] = bound
                context.setdefault("gender", gender or "")
                break
    aged = re.search(r"cat[ée]gorie\s+([A-Za-zÀ-ÿ]+)", tail or "", re.I)
    if aged and not context.get("age_class"):
        context["age_class"] = (_first(_AGES, aged.group(1))
                                or context.get("age_class", ""))
    if not context.get("gender"):
        context["gender"] = _first(_GENDERS, pairing_text) or ""
    return context


def _warnings(tail, report):
    """The warnings both fighters carried, where the article says plainly.

    One article records them: "3 avertissements pour les 2 tireuses", "2
    avertissements pour chaque tireuse". A third phrasing - "2 avertissements
    contre 1" - never says whose is whose, and splitting it would be a coin
    toss dressed up as a record, so it is reported and left unwritten.
    """
    found = _WARNINGS_BOTH.search(tail or "")
    if found:
        return found.group(1)
    if _WARNINGS_UNCLEAR.search(tail or ""):
        report.problem(
            f"warnings are printed as a comparison ('{_tidy(tail)[:60]}') "
            f"without saying which fighter carried which; left unrecorded")
    return ""


def _split_at_vs(line):
    """(left, right) around the single VS, or None."""
    marks = list(_VS.finditer(line))
    if len(marks) != 1:
        return None
    mark = marks[0]
    return line[:mark.start()], line[mark.end():]


def _cut_verdict(right):
    """(the blue fighter's text, the verdict text)."""
    bracket = re.search(r"\(([^)]*)\)", right)
    verdict = _VERDICT_WORD.search(right)
    if bracket and (not verdict or bracket.start() < verdict.start()):
        return right[:bracket.end()], right[bracket.end():]

    depth, cut = 0, None
    for index, ch in enumerate(right):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in _SEPARATORS and depth == 0:
            cut = index
            break
    if verdict and (cut is None or verdict.start() < cut):
        cut = verdict.start()
    if cut is None:
        return right, ""
    return right[:cut], right[cut:]


def _strip_prefix(left):
    """(what is left of the pairing, the tokens read off the front)."""
    found = {}
    text = left
    while True:
        stripped = re.sub(r"^[\s\-–—•*.,;:/]+", "", text)
        if stripped != text:
            text = stripped
            continue
        if not text:
            break
        weight = _WEIGHT.match(text)
        if weight:
            kilos, bound, gender, printed = _weight_of(text[:weight.end()])
            if printed:
                found.setdefault("weight_kg", kilos)
                found.setdefault("weight_bound", bound)
                if gender:
                    found.setdefault("gender", gender)
                text = text[weight.end():]
                continue
        rounds = _ROUNDS.match(text)
        if rounds:
            text = text[rounds.end():]
            continue
        ordinal = _ORDINAL.match(text)
        if ordinal:
            text = text[ordinal.end():]
            continue
        word = _PREFIX_WORDS.match(text)
        if word:
            token = word.group(0)
            for key, table in (("discipline", _DISCIPLINES),
                               ("gender", _GENDERS), ("age_class", _AGES)):
                value = _first(table, token)
                if value:
                    found.setdefault(key, value)
            text = text[word.end():]
            continue
        digits = re.match(r"^\d{1,2}(?![0-9A-Za-zÀ-ÿ])", text)
        if digits:
            text = text[digits.end():]
            continue
        break
    return text, found


def _heading_context(line):
    """What a heading says about the rows under it."""
    found = {}
    sport = _first(_SPORTS, line)
    if sport:
        found["sport"] = sport
    for key, table in (("discipline", _DISCIPLINES), ("gender", _GENDERS),
                       ("age_class", _AGES)):
        value = _first(table, line)
        if value:
            found[key] = value
    kilos, bound, gender, _printed = _weight_of(line)
    if kilos:
        found["weight_kg"] = kilos
        found["weight_bound"] = bound
        if gender and "gender" not in found:
            found["gender"] = gender
    if re.search(r"\bpoules?\b", line, re.I):
        found["poule"] = _tidy(line)
    return found


def _is_heading(line):
    """A section heading rather than prose - short, and not a sentence."""
    if _split_at_vs(line):
        return False
    raw = " ".join(str(line or "").split())
    if not raw or len(raw) > 90:
        return False
    if raw.endswith((":", ";")):
        return True
    text = _tidy(raw)
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        return True
    return bool(re.match(
        r"^\s*[-–—•*]?\s*(?:\d{1,2}\s*(?:er|[èe]re|[èe]me|e)?\s*)?"
        r"(?:en\s+|chez\s+|pour\s+|de\s+)?"
        r"(?:assauts?|combats?|d[ée]mo|r[ée]sultats?|poules?|finales?|"
        r"femmes?|hommes?|gant\b)", text, re.I))


def _names_two_people(line):
    return len(_name_runs(line)) >= 2


def _verdict_only(line):
    """A line that is nothing but the verdict for the pairing above it."""
    if _split_at_vs(line):
        return False
    if not _VERDICT_WORD.search(line):
        return False
    return len(_tidy(line)) <= 140


def _decision_of(text):
    """(canonical decision, the article's own words for it).

    The canonical value is the shared table's, so this adapter agrees with
    every other one about what "arrêt de l'arbitre" means. What is stored
    beside it is the phrase this article printed, because decision_detail is
    the source's own word - a field called detail holding a word the source
    never used is not a detail.
    """
    for decision, pattern in _DECISIONS:
        found = re.search(pattern, text or "", re.I)
        if found:
            printed = " ".join(found.group(0).split())
            return normalize.decision(printed) or decision, printed
    return "", ""


def _lexicon(lines):
    """Club spellings to split names on: the article's own, then the corpus's.

    Longest first, so "moule savate club" is preferred over "moule savate" and
    a fighter is never handed a truncated club.
    """
    seen, out = set(), []
    for line in lines:
        for club in re.findall(r"\(([^)]{2,60})\)", line):
            club = _tidy(club)
            if club and _key(club) not in seen and re.search(r"[A-Za-zÀ-ÿ]",
                                                             club):
                seen.add(_key(club))
                out.append((_key(club), club))
    for club in _CLUB_LEXICON:
        if _key(club) not in seen:
            seen.add(_key(club))
            out.append((_key(club), club))
    out.sort(key=lambda pair: -len(pair[0]))
    return out


def _name_runs(line):
    """Maximal runs of two or more words set in capitals - how names are written.

    A run is cut at anything that is not part of a name: a lowercase word, the
    two-letter VS, a verdict or section word, and any punctuation between two
    words. Without the punctuation cut, "PEZERON VS LADREZEAU : LADREZEAU
    VAINQUEUR" reads as a person called LADREZEAU LADREZEAU and the article
    appears to hold two of him.
    """
    runs, current, end = [], [], None
    for found in _WORD.finditer(line or ""):
        word = found.group(0).strip("'-")
        gap = line[end:found.start()] if end is not None else ""
        end = found.end()
        letters = [c for c in word if c.isalpha()]
        usable = (len(letters) >= 3 and word[:1].isalpha()
                  and all(c.isupper() for c in letters)
                  and _fold(word) not in _UNHELPFUL)
        if usable and (not current or not gap.strip()):
            current.append(word)
            continue
        if len(current) >= 2:
            runs.append(" ".join(current))
        current = [word] if usable else []
    if len(current) >= 2:
        runs.append(" ".join(current))
    return runs


def _name_index(lines):
    index = {}
    for line in lines:
        for run in _name_runs(line):
            key = _key(run.split()[0])
            index.setdefault(key, [])
            if run not in index[key]:
                index[key].append(run)
    return index


def _expand(name, index):
    """A lone surname put back to the full name the same article gave it.

    The knockout lines of the 2013 CREPS poule name their fighters by surname
    alone - "FINALE : PEZERON VS LADREZEAU" - after the earlier lines gave both
    in full. Joining them back is a lookup inside one document, not a guess, and
    it only happens where exactly one full name in the article starts with that
    surname. Anything else is left as printed.
    """
    if not name or " " in name.strip():
        return name, False
    matches = index.get(_key(name)) or []
    if len(matches) == 1:
        return matches[0], True
    return name, False


# ---------------------------------------------------------------- read ------

def read(source, slug, meta=None, **options):
    from savate import sources

    meta = meta or {}
    report = Report(source=str(source), adapter=NAME)
    page = sources.text(source)
    lines = _lines(page)
    headline = _headline(page)

    report.read = len(lines)
    report.notes.update(demonstrations=0, other_sport={}, unresolved=0,
                        expanded_names=[], typo_winners=[], headline=headline,
                        unparsed_results=0)

    tournament = _tournament(slug, meta, source, headline, lines, report)
    wanted = _fold(str(options.get("discipline")
                       or meta.get("only_discipline") or "")).strip()

    lexicon = _lexicon(lines)
    index = _name_index(lines)

    default_discipline = _document_discipline(lines, headline)
    disciplines = set()
    section = {"sport": "savate", "discipline": default_discipline}
    demo_mode = False
    bouts = []
    poule_bouts = []
    poule_name = ""
    roster = False
    skipped = 0

    number = 0
    while number < len(lines):
        line = lines[number]
        number += 1
        pair = _split_at_vs(line)

        if pair is None:
            # Competitors the article accounts for without saying who they met.
            # No row can be read from either, and neither may pass in silence.
            if _TALLY.search(line) and _TALLY_RESULT.search(line):
                _unparsed(report, "a line gives each fighter's record for the "
                                  "day rather than who met whom, so the bouts "
                                  "behind it cannot be read and are not in this "
                                  "archive", line)
                continue
            if roster and _ROSTER.match(line):
                _unparsed(report, "competitors are listed as having taken part "
                                  "with no result published, so nothing is "
                                  "stored for them", line)
                continue
            if _is_heading(line):
                found = _heading_context(line)
                if found.get("sport") and found["sport"] != section["sport"]:
                    _report_poule(poule_bouts, poule_name, report)
                    poule_bouts, poule_name = [], ""
                    section = {"sport": found["sport"],
                               "discipline": default_discipline}
                if _DEMO_LINE.match(line) or (_DEMO_WORD.search(line)
                                              and not found.get("poule")):
                    demo_mode = True
                    if _names_two_people(line):
                        _counted(report, section["sport"])
                    continue
                else:
                    demo_mode = False
                roster = bool(_UNDECIDED_SECTION.search(line))
                if found.get("poule"):
                    _report_poule(poule_bouts, poule_name, report)
                    poule_bouts = []
                    poule_name = found["poule"]
                elif not found.get("poule") and poule_name and found:
                    _report_poule(poule_bouts, poule_name, report)
                    poule_bouts, poule_name = [], ""
                section.update({k: v for k, v in found.items() if k != "sport"})
            elif _DEMO_WORD.search(line) and _names_two_people(line):
                _counted(report, section["sport"])
            continue

        roster = False
        left, right = pair

        # An exhibition: no result, no row, and never a fighter's record.
        verdict_here = _VERDICT_WORD.search(right) or _decision_of(right)[0]
        follows = lines[number] if number < len(lines) else ""
        verdict_next = _verdict_only(follows)
        if _DEMO_LINE.match(line) or (demo_mode and not (verdict_here
                                                         or verdict_next)):
            _counted(report, section["sport"])
            continue
        if verdict_here or verdict_next:
            demo_mode = False

        if section["sport"] != "savate":
            tally = report.notes["other_sport"]
            tally[section["sport"]] = tally.get(section["sport"], 0) + 1
            continue

        pairing, prefix = _strip_prefix(left)
        context = dict(section)
        context.update(prefix)

        blue_text, tail = _cut_verdict(right)
        if not _tidy(tail) and verdict_next:
            tail = follows
            number += 1

        red_name, red_club = _competitor(pairing, lexicon)
        blue_name, blue_club = _competitor(blue_text, lexicon)
        for name, grew in (_expand(red_name, index), _expand(blue_name, index)):
            if grew and name not in report.notes["expanded_names"]:
                report.notes["expanded_names"].append(name)
        red_name = _expand(red_name, index)[0]
        blue_name = _expand(blue_name, index)[0]

        if not (red_name and blue_name):
            skipped += 1
            report.problem(f"a pairing names fewer than two fighters: {line!r}")
            continue

        if wanted and _fold(context.get("discipline", "")) != wanted:
            continue

        _fill_category(context, f"{pairing} {blue_text}", blue_text, tail)
        decision, detail = _decision_of(tail)
        warnings = _warnings(tail, report)
        phase = phase_of(_tidy(left)) if _PHASE_HERE.search(left) else ""

        corner, how = "", ""
        stated = bool(_NO_DECISION.search(tail or ""))
        if not stated and _tidy(tail):
            corner, how = _name_the_winner(tail, red_name, blue_name)

        bout = Bout(
            tournament=slug,
            bout_id=f"{slug}-{len(bouts) + 1:03d}",
            date=tournament.start_date,
            category=_label(context),
            gender=context.get("gender", ""),
            age_class=context.get("age_class", ""),
            weight_kg=context.get("weight_kg", ""),
            weight_bound=context.get("weight_bound", ""),
            phase=phase,
            poule=poule_name,
            red=red_name, red_club=red_club,
            blue=blue_name, blue_club=blue_club,
            red_warnings=warnings, blue_warnings=warnings,
            decision_detail=detail,
            result_source="reported",
        )
        if corner:
            bout.winner = red_name if corner == "red" else blue_name
            bout.loser = blue_name if corner == "red" else red_name
            bout.decision = decision
            bout.status = "decided"
            if how and how != "named":
                report.notes["typo_winners"].append(f"{line!r}: {how}")
        else:
            bout.status = "unresolved"
            bout.decision = ""
            report.notes["unresolved"] += 1
            if stated:
                bout.decision_detail = _tidy(tail)[:80]
            else:
                report.problem(
                    f"no fighter in this bout is named as the winner, so it is "
                    f"stored unresolved: {line!r}")

        complaints = check(bout)
        if complaints:
            skipped += 1
            report.problem(f"a row was dropped ({'; '.join(complaints)}): "
                           f"{line!r}")
            continue
        disciplines.add(context.get("discipline", ""))
        bouts.append(bout)
        if poule_name:
            poule_bouts.append(bout)

    _report_poule(poule_bouts, poule_name, report)

    # A card that ran assaut and combat on the same night is not one discipline
    # and is not given one. The bouts themselves carry it, in `category`.
    tournament.discipline = (meta.get("discipline") or
                             (next(iter(disciplines)) if len(disciplines) == 1
                              else ""))
    report.notes["disciplines"] = sorted(d for d in disciplines if d)
    report.notes["bouts"] = len(bouts)
    report.notes["skipped"] = skipped
    if not bouts:
        report.problem("no bouts read - this article may not list any, or may "
                       "give per-fighter tallies rather than pairings")
    if report.notes["other_sport"]:
        report.problem("dropped as another sport: " + ", ".join(
            f"{count} {sport}" for sport, count
            in report.notes["other_sport"].items()))
    if report.notes["demonstrations"]:
        report.notes["demonstrations_note"] = (
            f"{report.notes['demonstrations']} demonstration(s) excluded - an "
            f"exhibition has no result and is not a bout")
    return tournament, bouts, report


def _unparsed(report, why, line):
    """Say plainly that part of this competition could not be read."""
    report.notes["unparsed_results"] = report.notes.get(
        "unparsed_results", 0) + 1
    report.problem(f"{why}: {_tidy(line)[:130]!r}")


def _counted(report, sport):
    """Record one exhibition - under its own sport where that is not savate."""
    if sport == "savate":
        report.notes["demonstrations"] += 1
        return
    tally = report.notes["other_sport"]
    tally[sport] = tally.get(sport, 0) + 1


def _document_discipline(lines, headline):
    """assaut or combat where the article says one and only one."""
    text = " ".join(lines[:4] + [headline])
    found = {name for name, pattern in _DISCIPLINES
             if re.search(pattern, text, re.I)}
    return found.pop() if len(found) == 1 else ""


def _report_poule(bouts, poule, report):
    """Say that a poule's finishing order is not being stored, and why.

    This adapter used to turn the 2013 CREPS poule into four placings: rank 1
    to 4, and gold, silver and bronze. The order does follow from the poule's
    own final and 3rd-place bout, and a rank worked out from bouts is exactly
    what result_source="inferred" is for - but the medals followed from
    nothing. The article prints a final, a 3rd-place bout and no classification
    at all; nowhere does it say this club challenge handed out a medal of any
    colour, and three of them are now in the archive as fact.

    A placing row cannot say otherwise: schema.check_placing requires the medal
    to match the rank, so ranks one to three cannot be stored medal-free. Until
    it can, the honest record of this poule is its two bouts, which are stored
    and read, plus this note saying what they imply and that the implication is
    not being sold as a result.
    """
    if not poule or not bouts:
        return
    final = next((b for b in bouts
                  if b.phase == "final" and b.status == "decided"), None)
    third = next((b for b in bouts
                  if b.phase == "bronze" and b.status == "decided"), None)
    if not (final and third):
        return
    report.notes.setdefault("poules_unranked", []).append(poule)
    report.problem(
        f"the finishing order of {poule!r} follows from its own final "
        f"({final.winner} beat {final.loser}) and 3rd-place bout "
        f"({third.winner} beat {third.loser}), but the article prints no "
        f"classification and names no medal, so no placing rows are stored")


def _tournament(slug, meta, source, headline, lines, report):
    """The competition this article is about, dated only where it says so.

    Three places count as the article saying so, and they are all printed on
    the page: its own body, its headline, and - where the headline gives a bare
    year and no day - that year. The address it was fetched from is not one of
    them. A URL slug reading "...-04-06-20416" is a filename, and the year
    somebody typed into a filename is not a fact about a competition; where the
    page itself is undated, the competition stays undated and says so.
    """
    when, weekday_checked = "", False
    came_from = ""
    for line in lines[:4]:
        if _split_at_vs(line):
            continue
        when, weekday_checked = _read_date(line, report)
        if when:
            came_from = "the article's own text"
            break
    if not when and headline:
        when, weekday_checked = _read_date(headline, report)
        if when:
            came_from = "the article's headline"
    year = when[:4] if when else ""
    if not year and headline:
        bare = _BARE_YEAR.search(headline)
        if bare:
            year = bare.group(1)
            came_from = "the year in the article's headline"
    if when and not weekday_checked:
        _check_weekday(when, lines, report)
    if came_from:
        report.notes["date_read_from"] = came_from
    if not year:
        report.notes["undated"] = True
        report.problem("the page prints no year this adapter can read, so the "
                       "competition is left undated - its bouts are kept, and "
                       "no date is put on them")
    return Tournament(
        slug=slug,
        name=meta.get("name") or headline or slug,
        discipline=meta.get("discipline", ""),
        level=meta.get("level", ""),
        format=meta.get("format", ""),
        age_class=meta.get("age_class", ""),
        year=meta.get("year") or year,
        start_date=meta.get("start_date") or when,
        end_date=meta.get("end_date") or when,
        city=meta.get("city", ""),
        country=meta.get("country", ""),
        source=str(source), adapter=NAME,
        competition=meta.get("competition", ""),
    )
