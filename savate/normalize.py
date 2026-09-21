"""Turning a source's own wording into the canonical vocabulary.

Every function here answers with "" when the input does not say. A blank is a
fact about the source; a guess would be a fact about nothing.
"""

import re
import unicodedata

# Women first: "women" contains "men", so the male pattern would claim every
# women's category if it were tried first.
GENDERS = [("Women", r"\bwomen\b|\bgirls?\b|\bf[ée]minin|\bfille|\bdame|"
                     r"\bfemale\b|\bW\b|\bF\b"),
           ("Men", r"\bmen\b|\bboys?\b|\bmasculin|\bgar[çc]on|\bhomme|"
                   r"\bmale\b|\bM\b")]
AGE = re.compile(r"senior|junior|cadet|v[ée]t[ée]ran|master|espoir|youth|young|"
                 r"minime|benjamin", re.I)
WEIGHT = re.compile(r"([-+−])\s*(\d{2,3}(?:[.,]\d)?)\s*k", re.I)

# Order matters: the first pattern that matches wins, so the specific stoppages
# are tested before the general "points" catch-all. Every entry here is a word
# a source actually printed - this is a reading table, never an inference. A
# verdict the table does not recognise comes back "" and the adapter keeps the
# printed words in decision_detail, which is the honest half of the pair.
DECISION_WORDS = [
    (re.compile(r"\bw\.?o\.?\b|\bw\.?a\.?\b|forfait|walkover|withdraw|"
                r"abandon.*before|non.?partant", re.I),
     "forfait"),
    (re.compile(r"\bd\.?q\.?\b|disqualif|d[ée]classement|squalific", re.I),
     "disqualification"),
    # The French stoppage vocabulary, which the Caribbean and FFSavate sheets
    # use constantly and which was previously unreadable: the referee stops it,
    # the doctor or the organising delegate stops it, the corner throws in the
    # sponge, or the fighter's own coach pulls them out. "HC"/"hors combat" is
    # the FFSavate's own word for a fighter who could not continue.
    (re.compile(r"\bab\.?\b|abandon|retire|\brsc\b|stopp|"
                r"arr[êe]t\s+(?:de\s+l['’]?arbitre|du\s+d\.?\s?o\.?|de\s+coach|"
                r"m[ée]dical|de\s+l['’]?assaut)|jet\s+de\s+l['’]?[ée]ponge|"
                # FFSavate writes the round straight onto the verdict - "HC3",
                # "H C 4°" - so no word boundary exists after the C.
                r"hors\s+combat|\bh\.?\s?c\.?\s*\d*\s*°?|\bk\.?\s?o\.?\b", re.I),
     "abandon"),
    (re.compile(r"\bdraw\b|nul\b|empate|\bn\.?c\.?\b|pareggio", re.I), "draw"),
    # The Caribbean league misspells "unanimité" four ways - unanimité,
    # inanimité, unamité, unaimité - and these are one word, not four verdicts.
    (re.compile(r"points|decision|d[ée]cision|unanim|[iu]nanimit|unam|unaim|"
                r"majorit|split|\bpts\b|loses|perd", re.I), "points"),
]

# Federations publish country names in their own language. Linking a fighter's
# 2012 French-language podium to their 2026 English-language bouts needs these
# to be one country, so the spellings actually seen are mapped to one form.
# Deliberately a lookup and not a guess: an unknown country is returned as it
# was written, which shows up as a new country rather than a wrong one.
COUNTRIES = {
    "algerie": "Algeria", "allemagne": "Germany", "angleterre": "England",
    "autriche": "Austria", "azerbaidjan": "Azerbaijan", "belgique": "Belgium",
    "bresil": "Brazil", "bulgarie": "Bulgaria", "cameroun": "Cameroon",
    "canada": "Canada", "croatie": "Croatia", "danemark": "Denmark",
    "espagne": "Spain", "etats unis": "United States", "finlande": "Finland",
    "grande bretagne": "Great Britain", "grece": "Greece", "hongrie": "Hungary",
    "inde": "India", "iran": "Iran", "italie": "Italy", "japon": "Japan",
    "maroc": "Morocco", "maurice": "Mauritius", "ile maurice": "Mauritius",
    "mexique": "Mexico", "norvege": "Norway", "pays bas": "Netherlands",
    "pologne": "Poland", "portugal": "Portugal", "roumanie": "Romania",
    "royaume uni": "Great Britain", "russie": "Russia", "senegal": "Senegal",
    "serbie": "Serbia", "slovenie": "Slovenia", "suede": "Sweden",
    "suisse": "Switzerland", "tchequie": "Czechia", "tunisie": "Tunisia",
    "turquie": "Turkey", "ukraine": "Ukraine", "ouzbekistan": "Uzbekistan",
    "cote d ivoire": "Ivory Coast", "coree": "Korea", "chine": "China",
    "taipei chinois": "Chinese Taipei", "republique tcheque": "Czechia",
    "guinee": "Guinea", "guinee conakry": "Guinea Conakry", "mali": "Mali",
    "nepal": "Nepal", "colombie": "Colombia", "armenie": "Armenia",
    "congo": "Congo", "afrique du sud": "South Africa", "perou": "Peru",
}


def country(name):
    """One spelling of a country, or the original if it is not a known one."""
    text = " ".join(str(name or "").split())
    if not text:
        return ""
    return COUNTRIES.get(re.sub(r"[^a-z ]+", " ", fold(text)).strip(),
                         text.title() if text.isupper() else text)


DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y",
                "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"]


def fold(text):
    """Accent- and case-insensitive key for matching a name against itself."""
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


# Weight classes that must not appear in the archive.
#
# * -76 kg / -82 kg – OCR artefacts for -75 kg and -85 kg that appear in
#   several university championship PDFs and older result sheets.
# * +82 kg – same OCR artefact, but in the heavyweight band.
#
# Note: -50 kg is a legitimate weight class in youth categories (cadet,
# minime, benjamin, junior young age bands). It is *not* a valid senior or
# university class – FFSU uses -48 / -52 / -56 … – but the correction must
# not be applied blindly to youth data.  Each adapter must gate the -50 kg fix
# behind its own domain check.
_INVALID_WEIGHTS = {
    # (kg, bound) -> (corrected_kg, corrected_bound)
    ("76", "under"): ("75", "under"),
    ("82", "under"): ("85", "under"),
    ("82", "over"):  ("85", "over"),
}


def _kg(text):
    """'70' -> '70', '67,5' -> '67.5', '70.0' -> '70'.

    Trailing zeros are only ever stripped after a decimal point. Stripping them
    unconditionally turns every -60 and -70 kg class into 6 and 7.
    """
    text = str(text).replace(",", ".")
    return text.rstrip("0").rstrip(".") if "." in text else text


def weight(kg, bound, gender="", adapter=None):
    """Return (kg, bound) corrected to a valid Savate weight class.

    Parameters
    ----------
    kg : str
        The raw weight class number from the source.
    bound : str
        "under" or "over".
    gender : str
        "Women" or "Men" (optional). Used only for the -50 kg correction.
    adapter : str
        Adapter name, used to gate the -50 kg correction.

    Returns
    -------
    tuple(str, str)
        (corrected_kg, corrected_bound).
    """
    kg = str(kg)
    fixed = _INVALID_WEIGHTS.get((kg, bound))
    if fixed is not None:
        return fixed
    # -50 kg is a valid youth class. Only correct when the adapter explicitly
    # operates at university/senior level.
    if kg == "50" and bound == "under" and adapter in (
        "savate_ranked_list", "savate_weight_list", "universitaire",
        "savate_tabular_pdf", "podium_pdf",
    ):
        # University / FFSU progression: women -48 / -52 / -56 …; men
        # -56 / -60 / -65 …; nobody gets under 48 (women) or 56 (men) kg.
        if gender.lower().startswith("m") or gender.lower().startswith("men"):
            return "56", "under"
        return "48", "under"
    return kg, bound


def category(label):
    """'Senior Men Assaut -75 kg' -> gender, age class, weight, bound."""
    label = " ".join(str(label or "").split())
    gender = next((g for g, pat in GENDERS if re.search(pat, label, re.I)), "")
    age = AGE.search(label)
    weight = WEIGHT.search(label)
    return {
        "category": label,
        "gender": gender,
        "age_class": age.group(0).title() if age else "",
        "weight_kg": _kg(weight.group(2)) if weight else "",
        "weight_bound": ("over" if weight and weight.group(1) == "+"
                         else "under" if weight else ""),
    }


def decision(text):
    """A source's word for how a bout ended -> canonical decision, or ""."""
    text = str(text or "")
    if not text.strip():
        return ""
    for pattern, name in DECISION_WORDS:
        if pattern.search(text):
            return name
    return ""


def date(text):
    """Any of the usual written date orders -> ISO, or "" if unrecognised.

    Ambiguous all-numeric dates are read day-first, which is what every source
    seen so far uses; a source that means otherwise must say so in its mapping.
    """
    from datetime import datetime
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""



# The dated venue line the FFSBF's own result sheets print under their title:
#   "01/02/2025 .......................... ......... Rousies (59)"
# The dots are a table-of-contents leader, the trailing figure the departement.
# Every French sheet carries it and nothing else in the archive states a date,
# so reading it is the difference between an event dated and an event guessed.
# The leader is printed as more than one run - full stops, then a row of
# ellipsis characters - so it is matched as runs, not as one.
_DATELINE = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s*(?:[.\u2026]+\s*){1,}"
                       r"(.+?)\s*(?:\((\d{2,3})\))?\s*$")


def dateline(line):
    """A sheet's dated venue line -> (ISO date, city, departement), or ("","","").

    Returns empty strings rather than raising: a sheet without the line is
    ordinary, and a date the archive does not have is better than one it
    invented.
    """
    found = _DATELINE.match(str(line or ""))
    if not found:
        return "", "", ""
    when, where, dept = found.groups()
    return date(when), " ".join((where or "").split()).title(), dept or ""


def clock(text):
    """'9:05', '09:05h', '9.05', '9:05 PM' -> 'HH:MM', or "" if unreadable."""
    text = " ".join(str(text or "").split())
    m = re.search(r"(\d{1,2})[:.h](\d{2})", text)
    if not m:
        return ""
    hour, minute = int(m.group(1)), m.group(2)
    if re.search(r"\bpm\b", text, re.I) and hour < 12:
        hour += 12
    if re.search(r"\bam\b", text, re.I) and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute}"


def score_pair(text):
    """'3-1', '3:1', '3 - 1' -> ('3', '1'). Anything else -> ('', '')."""
    m = re.search(r"(\d{1,3})\s*[-:/–]\s*(\d{1,3})", str(text or ""))
    return (m.group(1), m.group(2)) if m else ("", "")
