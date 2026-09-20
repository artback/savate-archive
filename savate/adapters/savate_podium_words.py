"""Podiums whose ranks are printed as words, not as a bracket.

Fifteen documents in this archive answer the question "who won?" with a French
(or Spanish) noun rather than a number: *Champion du Monde*, *Vice-championne
de France*, *Finaliste 3*, *3ème Championnat de France*, *Campeón Mundial*.
They come from three federations, span 2007 to 2026, and are laid out five
different ways - a two-column title table, a class-code list, a colon list, a
wide entry-list spreadsheet, a web page. What they share is not a shape. It is
that the rank is a word, and that the words sit next to a name, sometimes a
club, sometimes a country, always under some statement of the weight class.

So this adapter is one vocabulary and several readers. `_rank_in` knows every
wording seen; each `_read_*` knows one printing and hands `_rank_in` a line.
A document that matches no reader yields nothing and says so, which is the
correct answer for the four members of this family that are not podiums at all
(two canne de combat championships - a different sport - an entry list, and an
event prospectus).

WHAT "FINALISTE" MEANS, PER DOCUMENT
    The brief for this family warned that *Finaliste* can mean runner-up or
    losing semi-finalist. In these documents it is never the runner-up: every
    one of them also prints *Vice-champion(ne)* for second place. But it is
    read three different ways even so, and the difference is decided from the
    document, never assumed:

    * France Jeunes 2024 prints a *Rang* column beside the title. The number is
      taken from that column and the word ignored - there, "Finaliste 1" sits
      on rank 3, so reading the word's number would be wrong by two.
    * France Jeunes 2011 prints "Finaliste 3" and "Finaliste 4" with no rank
      column, at most one of each per class, filling exactly the places the
      champion and vice-champion leave empty. There the number IS the rank,
      and the reader checks that claim per class: a class where two people
      claim one rank is reported and dropped, not resolved by guessing.
    * France Jeunes 2023 prints a bare "Finaliste", two to four per class.
      Nothing in the document says which of them finished third, so none of
      them is given a rank. They are counted and reported as unranked, and
      lost - because handing three people a bronze would be fabrication.

WHAT IS NOT CLAIMED
    * No bouts are derived from a podium. A gold medal names a final's winner
      and nothing else; a bronze names no bout at all. The one exception is the
      2023 Amiens sheet, which is headed "Resultados de la Final 56-60Kg" and
      names the ganador and the vicecampeón of that one bout - a final the
      document states, so a final the adapter records.
    * A fighter's country is filled only where a document prints it beside the
      name. The French national sheets print the club and the region instead,
      and "this is a French championship, so everyone is French" is a fact
      about the tournament, which the Tournament row already carries.
    * The France Jeunes 2011 sheet numbers its weight classes 005-020 and
      105-120 and never says what those numbers weigh. The class is therefore
      recorded by the document's own code with no kilos attached. The 0xx/1xx
      split is not used to sex the class either; the gendered title word
      (Champion vs Championne) is, because that is what the page prints.
    * Gender read off a grammatically gendered noun - Championne, Campeón - is
      reported as such in the notes. It is what these documents give.
"""

import collections
import re
import subprocess

from savate import normalize as norm
from savate import pdf
from savate.schema import MEDALS, Bout, Placing, Report, Tournament

NAME = "savate_podium_words"
DESCRIPTION = "podiums stated in words (champion / vice-champion / finaliste)"

# Every wording of a place seen in this family. Order matters twice over:
# "vice-champion" contains "champion", and "3ème Championnat de France" - the
# French wording for a bronze - contains neither as a whole word but would be
# caught by a looser pattern. `\bchampion\b` deliberately does not match
# "Championnat", which is the competition, not the person.
_RANKS = [
    (re.compile(r"vice[\s-]*champion(ne)?s?\b", re.I), "2"),
    (re.compile(r"vice[\s-]*campe[oó]n(a)?\b", re.I), "2"),
    (re.compile(r"(3\s*[èe]me|3e|3rd|troisi[èe]me|bronze)\b", re.I), "3"),
    (re.compile(r"champion(ne)?s?\b", re.I), "1"),
    (re.compile(r"campe[oó]n(a)?\b", re.I), "1"),
]
# "Finalsite 4" appears once in the 2011 sheet; it is a typo for Finaliste and
# is matched here rather than silently dropping a competitor.
_FINALISTE = re.compile(r"(finalist[e]?s?|finalsite)\b", re.I)

# The FFSavate class code: a sex letter, a weight, sometimes a J for the youth
# ladder. Codes at or above this weight are the open class, not a weight - the
# convention ffsavate_finals documents, and M150J/F100 are the codes in use.
_CODE = re.compile(r"^([FMJ])\s*\+?\s*(\d{2,3})\s*(J)?$", re.I)
_SENTINEL = 90

# The French federation writes the girls' age class in the feminine -
# "Cadette", "Benjamine" - so both spellings have to be here or half a
# championship silently loses its age class and its categories split in two.
_AGE_WORDS = re.compile(
    r"\b(poussin(e|es|s)?|benjamin(e|es|s)?|minimes?|cadet(te|tes|s)?|"
    r"junior(e|es|s)?|espoirs?|seniors?|v[ée]t[ée]ran(e|es|s)?|masters?|"
    r"jeunes?|youth)\b", re.I)
_AGE_CANON = {"poussin": "Poussin", "benjamin": "Benjamin", "minime": "Minime",
              "cadet": "Cadet", "cadette": "Cadet", "junior": "Junior",
              "juniore": "Junior", "benjamine": "Benjamin",
              "poussine": "Poussin", "espoir": "Espoir", "senior": "Senior",
              "vétéran": "Vétéran", "veteran": "Vétéran", "veterane": "Vétéran",
              "master": "Master", "jeune": "Youth", "youth": "Youth"}

# A women's section is named before a men's one wherever both appear, and
# "femmes" is not what savate/normalize.py's gender patterns are tuned for, so
# the wordings these particular documents use are listed here.
_WOMEN = re.compile(r"\b(femmes?|f[ée]minin(e|es)?|dames?|filles?|women|woman|"
                    r"girls?)\b", re.I)
_MEN = re.compile(r"\b(hommes?|masculins?|masc\b|gar[çc]ons?|men|boys?)\b", re.I)


def _gender_of(text):
    """Men/Women from a section heading, or "" where it does not say."""
    text = str(text or "")
    if _WOMEN.search(text):
        return "Women"
    if _MEN.search(text):
        return "Men"
    return ""


def _age_of(text):
    """A canonical age class from whatever age word a line carries."""
    found = _AGE_WORDS.search(str(text or ""))
    if not found:
        return ""
    word = norm.fold(found.group(1)).rstrip("s")
    return _AGE_CANON.get(word, found.group(1).title())


def _rank_in(text, finaliste=""):
    """(rank, match) for the first place-word in `text`, or ("", None).

    `finaliste` says how this document uses the word: "numbered" when it prints
    the place after it ("Finaliste 3" in 2011), "unranked" when it prints it
    bare, and "" when the document's own rank column is authoritative.
    """
    best = None
    for pattern, rank in _RANKS:
        found = pattern.search(text)
        if found and (best is None or found.start() < best[1].start()):
            best = (rank, found)
    found = _FINALISTE.search(text)
    if found and (best is None or found.start() < best[1].start()):
        if finaliste == "numbered":
            after = re.match(r"\W{0,3}(\d)\b", text[found.end():])
            best = (after.group(1) if after else "", found)
        else:
            best = ("", found)
    return (best[0], best[1]) if best else ("", None)


def _weight(text):
    """(kilos, bound) from any of the ways these documents write a class.

    Returns ("", "") when the text states no weight, and ("", "over") for the
    open class - a class with no upper limit, which is not the same fact as a
    class whose limit was not printed.
    """
    text = " ".join(str(text or "").split())
    rules = [
        (r"moins\s+de\s*(\d{2,3})", "under"),
        (r"plus\s+de\s*(\d{2,3})", "over"),
        (r"(?:\d{2,3})\s*[-–]\s*(\d{2,3})\s*k", "under"),
        (r"\+\s*(\d{2,3})", "over"),
        (r"(\d{2,3})\s*\+", "over"),
        (r"[-–−]\s*(\d{2,3})", "under"),
        (r"^[FMJ]\s*(\d{2,3})", "under"),
        (r"(\d{2,3})\s*k", "under"),
    ]
    for pattern, bound in rules:
        found = re.search(pattern, text, re.I)
        if found:
            kilos = int(found.group(1))
            if kilos >= _SENTINEL:
                return "", "over"
            return str(kilos), bound
    return "", ""


def _label(age, gender, kilos, bound, fallback=""):
    """A category label specific enough to key an interface on.

    Age class and gender are part of it, always: "Men -60 kg" from a juniors
    sheet and "Men -60 kg" from a seniors sheet are one string, and every
    reader that keys on the label would then merge two competitions.
    """
    if kilos:
        weight = f"{'+' if bound == 'over' else '-'}{kilos} kg"
    elif bound == "over":
        weight = "open"
    else:
        weight = fallback
    return " ".join(p for p in (age, gender, weight) if p).strip()


def _klass(age, gender, kilos, bound, fallback=""):
    return {"category": _label(age, gender, kilos, bound, fallback),
            "gender": gender, "age_class": age,
            "weight_kg": kilos, "weight_bound": bound}


def _clean(name):
    """A printed name with the stray marks these PDFs leave on it."""
    name = " ".join(str(name or "").split())
    name = name.strip(" .,;:-–—>|'’\"")
    return " ".join(name.split())


class _Sheet:
    """One document's growing podium, with the checks every reader needs."""

    def __init__(self, slug, report):
        self.slug = slug
        self.report = report
        self.placings = []
        self.bouts = []
        # Places a document has said out loud that it awards more than once.
        # Savate gives two bronzes - both losing semi-finalists - and the
        # confederation's tables print two "3rd place" columns to say so. A
        # rank repeating anywhere else is a contradiction, not a shared medal.
        self.repeatable = set()
        self._seen = set()
        self._taken = collections.defaultdict(set)

    def add(self, klass, rank, fighter, country="", club=""):
        fighter = _clean(fighter)
        if not rank:
            self.report.problem(
                f"{klass['category']}: {fighter or 'a competitor'} is "
                f"listed without a place the document ranks")
            return
        if not fighter:
            self.report.problem(f"{klass['category']}: a {MEDALS[rank]} with no name")
            return
        key = (klass["category"], rank, norm.fold(fighter))
        if key in self._seen:
            return
        if rank in self._taken[klass["category"]] \
                and rank not in self.repeatable:
            self.report.problem(
                f"{klass['category']}: {fighter} and another competitor both "
                f"claim place {rank}; neither can be trusted, both dropped")
            self._drop(klass["category"], rank)
            return
        self._seen.add(key)
        self._taken[klass["category"]].add(rank)
        self.placings.append(Placing(
            tournament=self.slug,
            placing_id=f"{self.slug}-{len(self.placings) + 1:04d}",
            rank=rank, medal=MEDALS[rank],
            fighter=fighter, country=norm.country(country), club=_clean(club),
            result_source="reported", **klass))

    def _drop(self, category, rank):
        self.placings = [p for p in self.placings
                         if not (p.category == category and p.rank == rank)]


def _text(path):
    """The document's text with its column gaps intact, or "" if unreadable."""
    try:
        done = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=120)
        return done.stdout or ""
    except Exception:
        return ""


# --------------------------------------------------------------------------
# 1. The FISav 2007 title table: Catégorie | place | Nom | Prénom | Nation |
#    Titre | Organisation | Date. The class name and its weight band are
#    printed on two lines of the same block, and the 2007 juniors sheet has
#    slipped its rows so the place digit lands on a line of its own - so a
#    block runs from one "Champion" to the next, and the class is whatever the
#    category column says anywhere inside it.
# --------------------------------------------------------------------------

def _is_title_table(rows):
    for line in rows[:6]:
        text = pdf.text_of(line)
        if re.search(r"cat[ée]gorie", text, re.I) and re.search(r"\btitre\b",
                                                                text, re.I):
            return True
    return False


def _read_title_table(rows, sheet, meta):
    header = next(i for i, l in enumerate(rows)
                  if re.search(r"cat[ée]gorie", pdf.text_of(l), re.I))
    place = next((w.x0 for w in rows[header] if w.text.lower() == "place"), None)
    if place is None:
        sheet.report.problem("the table has no 'place' column to split on")
        return
    heading = " ".join(pdf.text_of(l) for l in rows[:header])
    gender = _gender_of(heading)
    age = _age_of(heading) or meta.get("age_class", "")
    if not gender:
        sheet.report.problem(f"the sheet's heading {heading!r} does not say "
                             f"whose championship this is")

    parsed = []
    for line in rows[header + 1:]:
        rank, found = _rank_in(pdf.text_of(line))
        parsed.append((line, rank, found))

    blocks, current = [], []
    for item in parsed:
        if item[1] == "1" and current:
            blocks.append(current)
            current = []
        current.append(item)
    if current:
        blocks.append(current)

    for block in blocks:
        category = " ".join(
            pdf.text_of([w for w in line if w.x0 < place])
            for line, _r, _f in block).strip()
        kilos, bound = _weight(category)
        if not kilos and bound != "over":
            if any(r for _l, r, _f in block):
                sheet.report.problem(f"a block headed {category!r} states no "
                                     f"weight class; its medals are dropped")
            continue
        klass = _klass(age, gender, kilos, bound)
        for line, rank, found in block:
            if not rank:
                continue
            # Everything to the right of the category column and to the left of
            # the title is the place digit, the name and the nation.
            head = [w for w in line if w.x0 >= place]
            cut = next((i for i, w in enumerate(head)
                        if re.match(r"^(vice|champion|campe|finalist)",
                                    w.text, re.I)), len(head))
            head = head[:cut]
            if head and re.fullmatch(r"\d", head[0].text):
                head = head[1:]
            if len(head) < 2:
                sheet.report.problem(f"{klass['category']}: a "
                                     f"{MEDALS.get(rank, rank)} line with no "
                                     f"name and nation")
                continue
            sheet.add(klass, rank, " ".join(w.text for w in head[:-1]),
                      country=head[-1].text)


# --------------------------------------------------------------------------
# 2. France Jeunes 2024: one wide row per competitor, with the place in its own
#    Rang column. The columns hold still across all six pages, so they are read
#    by position; the title word is used only to confirm the number.
# --------------------------------------------------------------------------

_J24 = {"name": (66, 174), "comp": (174, 210), "poids": (210, 246),
        "club": (246, 384), "ligue": (384, 520), "rang": (520, 531),
        "titre": (531, 10 ** 4)}


def _band(line, band):
    left, right = band
    return [w for w in line if left <= w.x0 < right]


def _is_rang_table(rows):
    for line in rows[:8]:
        text = pdf.text_of(line)
        if re.search(r"\brang\b", text, re.I) and re.search(r"\btitre\b",
                                                            text, re.I):
            return True
    return False


def _read_rang_table(rows, sheet, meta):
    held, ages = "", {}
    for line in rows:
        poids = " ".join(w.text for w in _band(line, _J24["poids"]))
        code = _CODE.match(poids.replace(" ", ""))
        name = " ".join(w.text for w in _band(line, _J24["name"]))
        if not code:
            # A name too long for its cell wraps, leaving the rest of the
            # record on the next line. Hold the name and use it there.
            held = name if name and not poids else ""
            continue
        rang = " ".join(w.text for w in _band(line, _J24["rang"]))
        titre = " ".join(w.text for w in _band(line, _J24["titre"]))
        if not name:
            name, held = held, ""
        gender = "Women" if code.group(1).upper() == "F" else "Men"
        # One row's competition cell is swallowed by an over-long name; the
        # age class its class code carried on every other row stands in, which
        # is reading the document rather than guessing at it.
        age = _age_of(" ".join(w.text for w in _band(line, _J24["comp"])))
        key = code.group(0)
        if age:
            ages[key] = age
        else:
            age = ages.get(key, "") or meta.get("age_class", "")
        kilos, bound = _weight(f"{code.group(1)}{code.group(2)}")
        klass = _klass(age, gender, kilos, bound)
        if not re.fullmatch(r"\d{1,2}", rang.strip()):
            sheet.report.problem(f"{klass['category']}: {name or '?'} has no "
                                 f"place in the Rang column")
            continue
        if rang.strip() not in MEDALS:
            continue
        word, _found = _rank_in(titre)
        if word and word != rang.strip():
            sheet.report.notes.setdefault("rang_over_word", 0)
            sheet.report.notes["rang_over_word"] += 1
        club = " ".join(w.text for w in _band(line, _J24["club"]))
        sheet.add(klass, rang.strip(), name, club=club)


# --------------------------------------------------------------------------
# 3. France Jeunes 2023: a class code, the competition's own name, the fighter,
#    the club, the region, the title. Four columns hold still on every page of
#    the file, which is what makes the fighter separable from their club.
# --------------------------------------------------------------------------

_J23 = {"title": (90, 182), "name": (182, 274), "club": (274, 388),
        "ligue": (388, 473), "titre": (473, 10 ** 4)}


def _is_code_rows(rows):
    hits = 0
    for line in rows:
        if line and _CODE.match(line[0].text) and _rank_in(
                pdf.text_of(_band(line, _J23["titre"])))[1]:
            hits += 1
    return hits >= 10


def _read_code_rows(rows, sheet, meta):
    unranked = 0
    for line in rows:
        if not line:
            continue
        code = _CODE.match(line[0].text)
        if not code:
            continue
        titre = " ".join(w.text for w in _band(line, _J23["titre"]))
        rank, found = _rank_in(titre, finaliste="unranked")
        if not found:
            continue
        gender = (_gender_of(titre)
                  or ("Women" if code.group(1).upper() == "F" else "Men"))
        age = (_age_of(" ".join(w.text for w in _band(line, _J23["title"])))
               or meta.get("age_class", ""))
        kilos, bound = _weight(f"{code.group(1)}{code.group(2)}")
        klass = _klass(age, gender, kilos, bound)
        name = " ".join(w.text for w in _band(line, _J23["name"]))
        if not rank:
            unranked += 1
            continue
        club = " ".join(w.text for w in _band(line, _J23["club"]))
        sheet.add(klass, rank, name, club=club)
    if unranked:
        sheet.report.notes["unranked_finalistes"] = unranked
        sheet.report.problem(
            f"{unranked} competitor(s) are printed as 'Finaliste' with no "
            f"place and two to four of them per class; the document does not "
            f"say which finished third, so none was given a rank")


# --------------------------------------------------------------------------
# 4. France Jeunes 2011: TYPE | POIDS | NOM | PRENOM | CLUB | ... | TITRE, with
#    the place carried by the title word alone ("Finaliste 3"). The weight
#    classes are numbered 005-020 and 105-120 and the document never says what
#    those numbers weigh, so no kilos are claimed for them.
# --------------------------------------------------------------------------

_J11 = {"type": (0, 65), "poids": (65, 88), "name": (88, 214),
        "titre": (380, 10 ** 4)}
_J11_ROW = re.compile(r"^\d$")


def _is_type_titre_table(rows):
    for line in rows[:8]:
        text = pdf.text_of(line)
        if re.search(r"\bTYPE\b", text) and re.search(r"\bPOIDS\b", text) \
                and re.search(r"\bTITRE\b", text):
            return True
    return False


def _read_type_titre_table(rows, sheet, meta):
    sheet.report.notes["weight_codes_unresolved"] = True
    sheet.report.problem(
        "the sheet numbers its weight classes (005-020, 105-120) and never "
        "says what those numbers weigh, so the classes carry the document's "
        "own code and no kilos")
    # Two passes. The sex of a class is printed only on its gendered title
    # words - "Championne" sexes a class, "Finaliste 3" does not - so the
    # class has to be read whole before any of its rows can be labelled.
    found, sexes = [], collections.defaultdict(set)
    for line in rows:
        head = [w.text for w in _band(line, _J11["type"])]
        if len(head) < 2 or not _J11_ROW.match(head[0]):
            continue
        titre = " ".join(w.text for w in _band(line, _J11["titre"]))
        rank, word = _rank_in(titre, finaliste="numbered")
        if not word:
            continue
        code = " ".join(w.text for w in _band(line, _J11["poids"])).strip()
        if not re.fullmatch(r"\d{3}", code):
            sheet.report.problem(f"a row for {titre!r} carries no weight code")
            continue
        age = _age_of(" ".join(head)) or meta.get("age_class", "")
        name = " ".join(w.text for w in _band(line, _J11["name"]))
        key = (age, code)
        gender = _gender_of_title(titre)
        if gender:
            sexes[key].add(gender)
        found.append((key, rank, name, titre))

    for key, rank, name, titre in found:
        age, code = key
        gender = ""
        if len(sexes[key]) == 1:
            gender = next(iter(sexes[key]))
        elif sexes[key]:
            sheet.report.problem(
                f"{age} poids {code}: its title words name both "
                f"{' and '.join(sorted(sexes[key]))}; the class is left unsexed")
        klass = _klass(age, gender, "", "", fallback=f"poids {code}")
        if rank not in MEDALS:
            if not rank:
                sheet.report.problem(f"{klass['category']}: {name} is listed as "
                                     f"{titre!r}, which states no place")
            continue
        sheet.add(klass, rank, name)


def _gender_of_title(text):
    """Men from "Champion", Women from "Championne" - the noun's own gender.

    This is a reading of French, not of a stated field. It is the only thing
    the 2011 sheet prints about the sex of a class: the weight codes split
    0xx/1xx along the same line, but nothing in the document says so, and a
    coding scheme nobody wrote down is not evidence.
    """
    if re.search(r"championne\b", text, re.I):
        return "Women"
    if re.search(r"champion\b", text, re.I):
        return "Men"
    return ""


# --------------------------------------------------------------------------
# 5. The FFSavate's European results: a class code on its own line, then the
#    one French medallist in that class, their club in brackets, and the title
#    they took. Only French competitors appear; the rest of the podium is not
#    in the document and is not invented here.
# --------------------------------------------------------------------------

_CLUB_IN_NAME = re.compile(r"^(?P<name>[^(]+)\((?P<club>[^)]*)\)\s*(?P<rest>.*)$")


def _is_class_code_lines(lines):
    hits = 0
    for i, line in enumerate(lines[:-1]):
        if _CODE.match(line.strip()) and _CLUB_IN_NAME.match(lines[i + 1].strip()):
            hits += 1
    return hits >= 4


def _read_class_code_lines(lines, sheet, meta):
    age = meta.get("age_class", "")
    current = None
    for line in lines:
        line = line.strip()
        code = _CODE.match(line)
        if code:
            gender = "Women" if code.group(1).upper() == "F" else "Men"
            kilos, bound = _weight(f"{code.group(1)}{code.group(2)}")
            current = _klass(age, gender, kilos, bound)
            if code.group(3):
                sheet.report.notes["youth_code_suffix"] = True
            continue
        found = _CLUB_IN_NAME.match(line)
        if not found or current is None:
            continue
        rank, word = _rank_in(found.group("rest"))
        if not word:
            continue
        sheet.add(current, rank, found.group("name"), club=found.group("club"))
    if sheet.report.notes.get("youth_code_suffix") and not age:
        sheet.report.problem(
            "the class codes carry a J suffix, which is the federation's mark "
            "for its youth ladder, but the document states no age class and "
            "none was supplied, so the categories carry none")


# --------------------------------------------------------------------------
# 6. The university championship sheet: a section per class, then one line per
#    medal, the title and the name either side of a colon.
# --------------------------------------------------------------------------

_HEADING = re.compile(r"^(f[ée]minin(?:e|es)?|masculins?|femmes?|hommes?|women|"
                      r"men)\s*([-+−]\s*\d{2,3}\s*kg)\s*$", re.I)
_COLON = re.compile(r"^(?P<title>[^:]{3,60}):\s*(?P<name>.+)$")


def _is_colon_list(lines):
    heads = sum(1 for l in lines if _HEADING.match(l.strip()))
    medals = sum(1 for l in lines
                 if _COLON.match(l.strip())
                 and _rank_in(_COLON.match(l.strip()).group("title"))[1])
    return heads >= 3 and medals >= 3


def _read_colon_list(lines, sheet, meta):
    age = meta.get("age_class", "")
    current, teams = None, 0
    for line in lines:
        line = " ".join(line.split())
        head = _HEADING.match(line)
        if head:
            kilos, bound = _weight(head.group(2))
            current = _klass(age, _gender_of(head.group(1)), kilos, bound)
            continue
        found = _COLON.match(line)
        if not found:
            continue
        rank, word = _rank_in(found.group("title"))
        if not word:
            continue
        if re.search(r"\b[ée]quipe", found.group("title"), re.I):
            teams += 1
            continue
        if current is None:
            sheet.report.problem(f"a medal is listed before any weight class: "
                                 f"{line!r}")
            continue
        sheet.add(current, rank, found.group("name"))
    if teams:
        sheet.report.problem(
            f"{teams} team placing(s) are printed at the end of the sheet; a "
            f"team is not a competitor and there is no class to file it under, "
            f"so they are not recorded")


# --------------------------------------------------------------------------
# 7. The 2023 Amiens final, published in Spanish on its own: one bout, headed
#    as a final, with both fighters and both countries.
# --------------------------------------------------------------------------

_FINAL_HEAD = re.compile(r"final(?:e)?\s+(?P<class>[-+0-9\s–]{2,12}k\s*g)", re.I)
_ARROW = re.compile(r"^(?P<title>.+?)(?:->|→|:)\s*(?P<rest>.+)$")


def _is_spanish_final(lines):
    return (any(_FINAL_HEAD.search(l) for l in lines)
            and any(re.search(r"campe[oó]n", l, re.I) for l in lines))


def _read_spanish_final(lines, sheet, meta):
    klass, people = None, {}
    for line in lines:
        line = " ".join(line.split())
        head = _FINAL_HEAD.search(line)
        if head and klass is None:
            kilos, bound = _weight(head.group("class"))
            klass = _klass(meta.get("age_class", ""), "", kilos, bound)
        found = _ARROW.match(line)
        if not found or klass is None:
            continue
        rank, word = _rank_in(found.group("title"))
        if not word or rank not in ("1", "2"):
            continue
        body = found.group("rest")
        parts = [p.strip() for p in re.split(r"\s+[-–]\s+", body) if p.strip()]
        name = parts[0] if parts else ""
        country = parts[-1] if len(parts) > 1 else ""
        gender = _gender_of_spanish(found.group("title"))
        if gender and not klass["gender"]:
            klass = dict(klass, gender=gender,
                         category=_label(klass["age_class"], gender,
                                         klass["weight_kg"],
                                         klass["weight_bound"]))
        people[rank] = (name, country)
        sheet.add(klass, rank, name, country=country)
    if "1" in people and "2" in people:
        winner, loser = people["1"], people["2"]
        sheet.bouts.append(Bout(
            tournament=sheet.slug, bout_id=f"{sheet.slug}-final",
            category=klass["category"], gender=klass["gender"],
            age_class=klass["age_class"], weight_kg=klass["weight_kg"],
            weight_bound=klass["weight_bound"], phase="final",
            # Printed order, not a corner: the sheet never says who stood
            # where, and red/blue mean corner in this archive.
            red=_clean(winner[0]), red_country=norm.country(winner[1]),
            blue=_clean(loser[0]), blue_country=norm.country(loser[1]),
            winner=_clean(winner[0]), loser=_clean(loser[0]), winner_corner="",
            status="decided", result_source="reported"))
        sheet.report.notes["final_bout"] = "the sheet is headed 'Final'"


def _gender_of_spanish(text):
    """Men from "Campeón", Women from "Campeona" - the noun's own gender.

    This is a reading of Spanish, not of a stated field, and it is reported.
    """
    if re.search(r"campeona\b", text, re.I):
        return "Women"
    if re.search(r"campe[oó]n\b", text, re.I):
        return "Men"
    return ""


# --------------------------------------------------------------------------
# 8. The European confederation's ranking page: one HTML table per section, in
#    two shapes - four place columns across, or a Result column down. Nine
#    championships sit on the one page, so a read names the one it wants.
# --------------------------------------------------------------------------

_PLACE_HEADER = re.compile(r"(\d)(?:st|nd|rd|th)\s*place", re.I)


def _cells(row):
    out = []
    for cell in row.find_all(["td", "th"]):
        chunks = [" ".join(part.split())
                  for part in cell.get_text("\n").split("\n")]
        out.append([c for c in chunks if c])
    return out


def _read_ranking_html(body, sheet, meta, wanted):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    article = soup.find("div", {"itemprop": "articleBody"}) or soup
    events, event, section = [], "", ""
    for node in article.find_all(["h1", "h2", "h3", "h4", "table"]):
        if node.name == "table":
            if event:
                events.append((event, section, node))
            continue
        text = " ".join(node.get_text(" ").split())
        if node.name == "h4":
            event, section = text, ""
        elif re.search(r"championship|championnat", text, re.I):
            event, section = text, ""
        else:
            section = text
    names = sorted({e for e, _s, _t in events})
    sheet.report.notes["events_on_page"] = names
    if not wanted:
        sheet.report.problem(
            "this page holds " + str(len(names)) + " championships; name one "
            "with the 'event' option. Available: " + "; ".join(names))
        return
    chosen = [e for e in events if norm.fold(wanted) in norm.fold(e[0])]
    if not chosen:
        sheet.report.problem(f"no championship on the page matches "
                             f"{wanted!r}; available: " + "; ".join(names))
        return
    sheet.report.notes["event"] = chosen[0][0]
    for event, section, table in chosen:
        _read_ranking_table(table, sheet, meta, event, section)


def _read_ranking_table(table, sheet, meta, event, section):
    rows = table.find_all("tr")
    if not rows:
        return
    header = [" ".join(c) for c in _cells(rows[0])]
    places = [(_PLACE_HEADER.search(h).group(1) if _PLACE_HEADER.search(h)
               else "") for h in header]
    down = any(re.fullmatch(r"result", h, re.I) for h in header)
    if places.count("3") > 1:
        # Two bronze columns: the document awards the place twice.
        sheet.repeatable.add("3")
    gender = _gender_of(section) or _gender_of(event)
    age = (_age_of(section) or _age_of(event) or _age_of(meta.get("name", ""))
           or meta.get("age_class", ""))
    klass, unawarded = None, 0

    for row in rows[1:]:
        cells = _cells(row)
        if not cells:
            continue
        first = " ".join(cells[0])
        if first:
            kilos, bound = _weight(first)
            # The weight cell itself is often the only thing that sexes a
            # class: "F48 kg", "M-60 kg", "J60 kg" in the older tables.
            code = re.match(r"^\s*([FMJ])\s*[-+ ]?\s*\d", first)
            letter = code.group(1).upper() if code else ""
            sexed = gender or _gender_of(first) or (
                "Women" if letter == "F" else "Men" if letter in "MJ" else "")
            aged = age or ("Junior" if letter == "J" else "")
            if not kilos and bound != "over":
                klass = None
                continue
            klass = _klass(aged, sexed, kilos, bound)
        if klass is None:
            continue
        if down:
            # Weight | Result | Name | Country, two rows to a class.
            if len(cells) < 4:
                continue
            rank, word = _rank_in(" ".join(cells[1]))
            if not word:
                continue
            sheet.add(klass, rank, " ".join(cells[2]),
                      country=" ".join(cells[3]))
            continue
        for column, cell in enumerate(cells[1:], start=1):
            rank = places[column] if column < len(places) else ""
            if not rank or not cell:
                continue
            if re.search(r"non\s+attribu", " ".join(cell), re.I):
                unawarded += 1
                continue
            country = cell[-1] if len(cell) > 1 else ""
            name = " ".join(cell[:-1]) if len(cell) > 1 else cell[0]
            if len(cell) == 1:
                sheet.report.problem(f"{klass['category']}: {cell[0]!r} is "
                                     f"printed without a country")
            sheet.add(klass, rank, name, country=country)
    if unawarded:
        sheet.report.notes["titles_not_awarded"] = unawarded


# --------------------------------------------------------------------------

def read(source, slug, meta=None, **options):
    """(Tournament, [Placing|Bout], Report) from one word-ranked podium."""
    from savate import sources

    meta = dict(meta or {})
    report = Report(source=str(source), adapter=NAME)
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME, **meta)
    sheet = _Sheet(slug, report)

    try:
        path = sources.fetch(source, refresh=options.get("refresh", False),
                             binary=False)
        head = path.open("rb").read(5)
    except Exception as e:
        report.problem(f"the document could not be fetched: {e}")
        return tournament, [], report

    if head != b"%PDF-":
        body = path.read_text(encoding="utf-8", errors="replace")
        if "<html" not in body.lower():
            report.problem("the document is neither a PDF nor a web page")
            return tournament, [], report
        report.read = 1
        try:
            _read_ranking_html(body, sheet, meta, options.get("event", ""))
        except Exception as e:
            report.problem(f"the page could not be read: {e}")
        return tournament, sheet.placings + sheet.bouts, report

    try:
        words = pdf.words(path)
    except Exception as e:
        report.problem(f"the PDF has no readable text: {e}")
        return tournament, [], report
    rows = pdf.rows(words)
    report.read = len({w.page for w in words})
    lines = _text(path).splitlines()

    readers = [
        (_is_title_table, _read_title_table, rows, "title table"),
        (_is_rang_table, _read_rang_table, rows, "rank-column table"),
        (_is_type_titre_table, _read_type_titre_table, rows, "coded table"),
        (_is_code_rows, _read_code_rows, rows, "class-code rows"),
        (_is_class_code_lines, _read_class_code_lines, lines, "class-code list"),
        (_is_colon_list, _read_colon_list, lines, "colon list"),
        (_is_spanish_final, _read_spanish_final, lines, "single final"),
    ]
    for matches, run, body, kind in readers:
        try:
            if not matches(body):
                continue
        except Exception:
            continue
        report.notes["layout"] = kind
        try:
            run(body, sheet, meta)
        except Exception as e:
            report.problem(f"the {kind} could not be read past its start: {e}")
        break
    else:
        report.problem("no podium wording was found in this document - it is "
                       "not one of the layouts this adapter reads")

    report.notes["placings"] = len(sheet.placings)
    if sheet.bouts:
        report.notes["bouts"] = len(sheet.bouts)
    return tournament, sheet.placings + sheet.bouts, report
