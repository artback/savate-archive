"""Repair the strings a federation's PDFs left behind, for display only.

The archive stores what the source printed. That is the right thing for a
record and the wrong thing for a website: a page that renders
"M ICHAT DIM ITRI (Pesé 81,6Kg)" or ": ALAMELLE Jianny, Fédération Française de
Savate Boxe Française" as a competitor's name looks broken, and the reader
blames the page rather than the PDF.

So this module is a lens, not a migration. Nothing here writes to savate.db.
`export_ui.py` puts every name and country through it on the way out, and the
stored value stays exactly as the source printed it.

Three kinds of damage, and what is done about each:

*Spacing.* poppler splits a capital off its word when the glyph pair is kerned
tightly - "M ICHAT DIM ITRI" is MICHAT DIMITRI. The repair only ever rejoins a
lone capital to a following run of capitals, which is a shape no real name has,
and it is applied per word so "DEL M ONTE M ATTEO" comes back as DEL MONTE
MATTEO without disturbing the legitimate two-word surname.

*Annotation.* Names arrive carrying their weigh-in ("(Pesé 82Kg)"), their
country ("(Russie)", "(SER)"), or their whole federation (", Fédération
Italienne de Savate"). Those are not part of the name. They are cut off it and
returned separately, so the page can show a club line it could not show before
rather than silently discarding what the source knew.

*Wreckage.* Some strings are not names at all - "round vs Erick RETAJAC
Ibague,", "Azerbaijan", "-". A mis-segmented document produced them and no
amount of string surgery recovers a person from them. They are reported as
unusable and the caller drops the row. Guessing which fighter was meant would
put a fabricated career in front of someone who would believe it.

The project rule holds here as everywhere: repair what is provably damaged,
surface what is missing, invent nothing.
"""

import re
import unicodedata

from savate import identity

# A lone capital that lost its word: "M ICHAT" -> "MICHAT". Requires the tail to
# be capitals too, so an initial ("J. DUPONT", "A Kovacs") is never swallowed.
_SPLIT_CAP = re.compile(r"\b([A-ZÀ-Þ])\s+([A-ZÀ-Þ]{2,})")

# Trailing weigh-in note the 2025 European sheets print inside the name cell.
_WEIGHT_NOTE = re.compile(r"\s*\(\s*Pes[ée]?\s*[\d.,]+\s*kg\s*\)\s*", re.I)

# A parenthesised country or federation code at the end: "(Russie)", "(SER)".
_PAREN_TAIL = re.compile(r"\s*\(([^()]{2,40})\)\s*$")

# ", Fédération Italienne de Savate" and its Spanish/Galician cousins.
_CLUB_TAIL = re.compile(
    r"\s*,\s*((?:F[ée]d[ée]ration|Federation|Federazione|Federación|Asociacion|"
    r"Asociación|Association|Club|Savate\s+Academy)\b.*)$", re.I)

# An organisation printed where the competitor's name belongs: "Turkey Savate
# Federation Bogaz Efe Ercan", "Savate Association India Karn Priyam". Some
# federations enter their squad under the federation's own name, and the two
# run together into one cell. The organisation is real and worth keeping - it
# is the club field - but it is not who fought.
_ORG_PREFIX = re.compile(
    r"^\s*(?P<org>.{0,40}?\b(?:f[ée]d[ée]ration|federation|association|academy|"
    r"acad[ée]mie|savez|ligue|club|union|team)\b(?:\s+of)?"
    r"(?:\s+\([A-Za-z]{2,4}\))?)\s+(?P<rest>.+)$", re.I)

# Leading punctuation a list marker left on the front: ": ALAMELLE Jianny".
_LEAD_JUNK = re.compile(r"^[\s:;,.\-–—•*]+")
_TRAIL_JUNK = re.compile(r"[\s:;,.\-–—•*]+$")

# A column header or a result word that ran into the name cell: "Medal Onur
# KAYA", "forfait David SZABO TOTH". The word is the sheet's, the rest is the
# competitor's, so these are trimmed rather than treated as wreckage - throwing
# away forty real medallists to avoid one bad row is the wrong trade.
_LEAD_LABEL = re.compile(
    r"^(medal|medalist|medallist|m[ée]daille|forfait|winner|vainqueur|abandon|"
    r"wo|w\.?o\.?)\b[\s:.\-–—]*", re.I)

# Strings that are wreckage rather than damaged names: a fixture line, a pair
# of names joined by "&", a fragment of a bracket caption.
_NOT_A_NAME = re.compile(r"(\bvs\b|\bround\b|&|\bpoule\b|\bfinal\b)", re.I)

# The competition's own title, caught in the name column. "Championnat du Monde"
# split across a cell boundary leaves "du Monde FLORJANIC Valention", which then
# registers as a competitor in his own right and takes a slice of the real
# person's career with him.
_EVENT_WORDS = re.compile(
    r"\b(championnat|championship|prvenstvo|kup|coupe|cup|open|tournoi|"
    r"memorijal|trophy|troph[ée]e|du\s+monde|d.europe|de\s+france|"
    r"world|europe(an)?|national|international)\b", re.I)


def _collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def _rejoin_split_capitals(text):
    """Undo poppler's kerning split wherever a lone capital lost its word.

    Applied repeatedly, so a name split twice - "DEL M ONTE M ATTEO" - comes
    back whole. It cannot reach a split with no lone capital in it: "AM IM ER"
    is AMIMER, and every fragment is two letters, so this pass leaves it and
    `_rejoin_corroborated` gets its turn. A few names survive both, and stay
    visibly imperfect rather than being guessed at.
    """
    previous = None
    while previous != text:
        previous = text
        text = _SPLIT_CAP.sub(r"\1\2", text)
    return text


# Particles that legitimately stand alone before a surname. A join across one
# of these would weld "DEL MONTE" into "DELMONTE", so the repair never crosses
# them however the corpus votes.
_PARTICLES = {
    "de", "del", "della", "di", "da", "dos", "das", "du", "des", "van", "von",
    "der", "den", "le", "la", "lo", "li", "mc", "mac", "ben", "bin", "ibn",
    "al", "el", "abu", "ng", "saint", "st", "san", "santa", "o", "ter", "te",
}

# A fragment shaped like kerning damage: a short all-caps run sitting next to
# another all-caps run. Names carrying one are kept out of the vocabulary, so a
# damaged string cannot vote for its own fragments.
_LOOKS_SPLIT = re.compile(r"\b[A-ZÀ-Þ]{1,3}\s+[A-ZÀ-Þ]{2,}")


def vocabulary(names):
    """Fold a corpus of undamaged names into the set of name-words it attests.

    Used to corroborate the harder half of the kerning damage. A lone capital
    torn off its word ("M ICHAT") is unambiguous, but poppler also splits
    mid-word - "DIM ITRI" is DIMITRI, while "DEL MONTE" is a real two-word
    surname, and the two are the same shape. Nothing in the string itself tells
    them apart.

    So the join is not made on shape. It is made only where the archive
    elsewhere spells the joined form as a whole word: 1649 competitors across
    nineteen years are a corpus, and DIMITRI appearing in it is evidence, where
    a rule about capital letters would only be a guess.

    Names that themselves look split are excluded from the corpus. Otherwise
    "MICHAT DIM ITRI" contributes DIM and ITRI, and those votes block the very
    repair the corpus exists to authorise.
    """
    words = set()
    for raw in names:
        text = _collapse(raw or "")
        if not text or _LOOKS_SPLIT.search(text):
            continue
        for word in re.split(r"[^\w'\u2019-]+", text):
            if len(word) > 1:
                words.add(fold(word))
    return words


def wordforms(names):
    """{folded word: the spelling the corpus uses most often for it}.

    Repairs need to put back the accented form, not a flattened one, so this
    keeps the actual spellings rather than only the folded keys `vocabulary()`
    returns.
    """
    counts = {}
    for raw in names:
        text = _collapse(raw or "")
        if not text or _LOOKS_SPLIT.search(text):
            continue
        for word in re.split(r"[^\w'\u2019-]+", text):
            if len(word) > 1:
                counts.setdefault(fold(word), {}).setdefault(word, 0)
                counts[fold(word)][word] += 1
    # The spelling used most often, and how often the word appears at all. The
    # count matters: a damaged spelling is in the corpus too, and without
    # knowing which of two forms the archive prefers there is no way to tell
    # the repair from the damage.
    #
    # A tie is decided, not left to luck. The corpus arrives from a set, so a
    # plain max() crowns whichever spelling Python happened to iterate first -
    # one build would repair Babid to Babić and the next to BABIC. Prefer the
    # accented form: a text layer can lose or misread a diacritic, never invent
    # one, so its being written at all marks the real name. Then the folded
    # spelling, so the choice is the same on every machine.
    def _preferred(v):
        # A tie is decided, not left to luck: the corpus arrives from a set, so
        # a plain max() crowns whichever spelling Python happened to iterate
        # first - one build repairs Babid to Babić and the next to BABIC.
        # Prefer the accented form (a text layer can lose or misread a
        # diacritic, never invent one, so its being written at all marks the
        # real name), then the title-cased form over an all-caps one, and
        # finally the spelling itself, so the choice is a total order that is
        # the same on every machine.
        def rank(item):
            spelling, n = item
            lower = spelling.lower()
            accented = any(c in "ćčšžđ" for c in lower)
            allcaps = spelling == spelling.upper() and any(c.isalpha() for c in spelling)
            return (-n, 1 if accented else 0, 0 if allcaps else 1, spelling)
        return max(v.items(), key=rank)[0], sum(v.values())
    return {k: _preferred(v) for k, v in counts.items()}


# One generator used by the Croatian and Serbian federations reads ć as d:
# Babić becomes Babid, Košćak becomes Košdak, Florjanić becomes Florjanid -
# 334 rows, and every one of them splits a competitor in two. The fault is in
# the text layer, not in anybody's spelling.
def _repair_c_read_as_d(text, forms):
    """Put back a ć the text layer read as a d - where the corpus agrees.

    The corpus is the gate, and it has to be: David, Dávid and DAVID are real
    names built from those same letters, and no rule about Slavic surnames can
    tell them from a broken Babić. What can tell them apart is whether the
    archive elsewhere spells the same word with a c or a ć. It does for Babić;
    it never does for Davić. A word already attested as printed is left alone,
    and a word with two possible repairs is left alone too - an ambiguous fix
    is a guess wearing a corpus for a hat.
    """
    if not forms:
        return text
    out = []
    for word in text.split(" "):
        folded = fold(word)
        if len(word) < 4 or "d" not in folded:
            out.append(word)
            continue
        # How often the archive prints the word as it stands. A damaged
        # spelling appears too, so the test is not "is this word known" but
        # "does the archive prefer the other one".
        mine = forms.get(folded, ("", 0))[1]
        hits = set()
        for i, ch in enumerate(folded):
            if ch != "d":
                continue
            candidate = folded[:i] + "c" + folded[i + 1:]
            better = forms.get(candidate)
            if not better:
                continue
            # A tie goes to the spelling carrying the diacritic. A text layer
            # can lose a ć or misread it; it cannot invent one, so the accented
            # form being written at all is evidence that it is the real name -
            # where two plain spellings tied would be no evidence either way.
            accented = any(c in "ćčšžđ" for c in better[0].lower())
            if better[1] > mine or (accented and better[1] >= mine):
                hits.add(better[0])
        out.append(hits.pop() if len(hits) == 1 else word)
    return " ".join(out)


def _rejoin_corroborated(text, words):
    """Join adjacent fragments the corpus attests as one word, and only those."""
    if not words:
        return text
    parts = text.split(" ")
    out, i = [], 0
    while i < len(parts):
        if i + 1 < len(parts):
            left, right = parts[i], parts[i + 1]
            if (fold(left) not in _PARTICLES
                    and fold(left + right) in words
                    and fold(left) not in words
                    and fold(right) not in words):
                out.append(left + right)
                i += 2
                continue
        out.append(parts[i])
        i += 1
    return " ".join(out)


def fold(text):
    """Accent- and case-insensitive key for matching and search.

    Shares `identity.LETTERS`, so a name folds the same way here as it does
    when the register decides who is who. Two different foldings would mean
    the search box and the archive disagreed about Đorđević.
    """
    text = "".join(identity.LETTERS.get(c, c) for c in str(text or ""))
    stripped = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return _collapse(stripped.lower())


class Name:
    """A repaired competitor name and whatever was attached to it.

    `usable` is False where the source string was never a name. The caller drops
    those rows; they are counted, not silently swallowed, so the size of the
    problem stays visible.
    """

    __slots__ = ("raw", "text", "country", "club", "weight", "usable", "reason")

    def __init__(self, raw, text="", country="", club="", weight="",
                 usable=True, reason=""):
        self.raw = raw
        self.text = text
        self.country = country
        self.club = club
        self.weight = weight
        self.usable = usable
        self.reason = reason

    def __repr__(self):
        if not self.usable:
            return f"Name({self.raw!r}, unusable: {self.reason})"
        extra = "".join(f" {k}={v!r}" for k, v in
                        (("country", self.country), ("club", self.club),
                         ("weight", self.weight)) if v)
        return f"Name({self.text!r}{extra})"


def club(raw, words=None):
    """Repair a club or federation name.

    Clubs come off the same page as the competitors and carry the same damage -
    "SK Om ega Vž" is SK Omega Vž - but nothing was putting them through the
    repair, so one club appeared twice in the archive and a fighter's affiliation
    looked like two.
    """
    text = _collapse(raw or "")
    if not text:
        return ""
    text = _rejoin_split_capitals(text)
    text = _rejoin_corroborated(text, words)
    return _collapse(text)


def name(raw, words=None, forms=None):
    """Repair one competitor name. Never raises; reports instead.

    `words` is an optional corpus from `vocabulary()`; without it the harder
    mid-word kerning splits are left alone rather than guessed at. `forms` is
    the same corpus from `wordforms()`, which additionally puts back accents a
    text layer dropped.
    """
    if not raw or not raw.strip():
        return Name(raw or "", usable=False, reason="empty")

    text = _collapse(raw)

    weight = ""
    found = _WEIGHT_NOTE.search(text)
    if found:
        weight = _collapse(found.group(0)).strip("()")
        text = _WEIGHT_NOTE.sub(" ", text)

    club = ""
    found = _CLUB_TAIL.search(text)
    if found:
        club = _collapse(found.group(1))
        text = text[:found.start()]

    found = _ORG_PREFIX.match(text)
    if found:
        org, rest = _collapse(found.group("org")), _collapse(found.group("rest"))
        # A country immediately after the keyword belongs to the organisation,
        # not to the person: "Savate Association India Karn Priyam".
        words = rest.split(" ")
        while words and len(words) > 1:
            found_nation = country(words[0])
            if not found_nation.known:
                break
            org = f"{org} {words.pop(0)}"
        rest = " ".join(words)
        if len(rest) >= 4:
            club = club or org
            text = rest

    from_name = ""
    found = _PAREN_TAIL.search(text)
    if found:
        inside = _collapse(found.group(1))
        # A parenthesis holding a fighter's federation is a club, not a country.
        if re.match(r"(?i)(f[ée]d|federa|asoci|club|academy)", inside):
            club = club or inside
        else:
            from_name = inside
        text = text[:found.start()]

    text = _LEAD_JUNK.sub("", text)
    text = _TRAIL_JUNK.sub("", text)
    text = _LEAD_LABEL.sub("", text)
    # A competition title that ran into the name column is the document's, not
    # the competitor's. Cut it and keep what is left, rather than losing the
    # person to the tournament they fought in.
    if _EVENT_WORDS.search(text):
        stripped = _collapse(_LEAD_JUNK.sub("", _EVENT_WORDS.sub(" ", text)))
        if len(stripped) >= 4:
            text = stripped
        elif not stripped:
            # Nothing but the competition's title. That is the document
            # speaking, not a competitor.
            return Name(raw, usable=False, reason="is a competition title")
    text = _rejoin_split_capitals(_collapse(text))
    text = _rejoin_corroborated(text, words)
    text = _repair_c_read_as_d(text, forms)

    if not text:
        return Name(raw, usable=False, reason="nothing left after trimming")
    if _NOT_A_NAME.search(text):
        return Name(raw, usable=False, reason="reads as fixture text, not a name")
    if any(ch.isdigit() for ch in text):
        return Name(raw, usable=False, reason="contains digits")
    if len(text) < 3:
        return Name(raw, usable=False, reason="too short to be a name")

    return Name(raw, text=text, country=from_name, club=club, weight=weight)


# ---- countries ---------------------------------------------------------
#
# The same nation is printed a dozen ways across nineteen years and three
# languages: France / FRA / Fr / Francia / Frankreich. Only exact, attested
# spellings are listed - a fuzzy match here would quietly merge two nations.

_ALIASES = {}

# The three-letter federation code a results sheet actually prints - SUI, not
# SWI; NED, not NET. It is never derived from the name, because the derivation
# is wrong for exactly the nations anyone would notice. It is read from the
# first three-letter spelling each nation is registered with below, which is
# the code the sources themselves use.
_CODES = {}


def _alias(canonical, iso, *spellings):
    for spelling in (canonical,) + spellings:
        _ALIASES[fold(spelling)] = (canonical, iso)
    for spelling in spellings:
        if len(spelling) == 3 and spelling.isalpha() and spelling.isupper():
            _CODES.setdefault(canonical, spelling)
            break


_alias("France", "FR", "FRA", "Fr", "Francia", "Frankreich", "Frankrike",
       "Francuska")
_alias("Belgium", "BE", "BEL", "Belgique", "Belgio", "Bel")
_alias("Italy", "IT", "ITA", "Italie", "Italia", "Ita", "Italija")
_alias("Croatia", "HR", "CRO", "Croatie", "Croazia", "Cro", "HRV", "Hrvatska")
_alias("Serbia", "RS", "SER", "Serbie", "Srbija", "Ser", "SRB")
_alias("Slovenia", "SI", "SLO", "Slovenie", "Slovénie", "Slovenija", "SVN")
_alias("Russia", "RU", "RUS", "Russie", "Russian Federation", "Rus")
_alias("Ukraine", "UA", "UKR", "Ukranie", "Ucraina", "Ukr", "UKRAIN",
       "Ukrajina")
_alias("Turkey", "TR", "TUR", "Turquie", "Türkiye", "Turkiye", "Tur")
_alias("Germany", "DE", "GER", "Allemagne", "Deutschland", "DEU", "Ger")
_alias("Greece", "GR", "GRE", "Grece", "Grèce", "Hellas", "GRC")
_alias("Spain", "ES", "ESP", "Espagne", "España", "Espana", "Esp")
_alias("Portugal", "PT", "POR", "Prt")
_alias("Netherlands", "NL", "NED", "Pays-Bas", "Holland", "NLD")
_alias("United Kingdom", "GB", "GBR", "Great Britain", "Grande-Bretagne",
       "England", "Angleterre", "Royaume-Uni", "UK")
_alias("Ireland", "IE", "IRL", "Irlande")
_alias("Switzerland", "CH", "SUI", "Suisse", "Svizzera", "CHE")
_alias("Austria", "AT", "AUT", "Autriche", "Österreich", "Osterreich")
_alias("Hungary", "HU", "HUN", "Hongrie", "Magyarorszag", "Magyarország")
_alias("Romania", "RO", "ROU", "Roumanie", "Romanie", "Romania", "ROM")
_alias("Bulgaria", "BG", "BUL", "Bulgarie", "BGR")
_alias("Poland", "PL", "POL", "Pologne", "Polska")
_alias("Czech Republic", "CZ", "CZE", "Tchequie", "Tchéquie", "Czechia")
_alias("Slovakia", "SK", "SVK", "Slovaquie", "SLK")
_alias("Bosnia and Herzegovina", "BA", "BIH", "Bosnie", "Bosnia",
       "Bosnie-Herzegovine", "B&H", "BiH")
_alias("Montenegro", "ME", "MNE", "Montenegro", "Crna Gora")
_alias("North Macedonia", "MK", "MKD", "Macedonia", "Macedoine", "Macédoine")
_alias("Albania", "AL", "ALB", "Albanie")
_alias("Moldova", "MD", "MDA", "Moldavie")
_alias("Belarus", "BY", "BLR", "Bielorussie", "Biélorussie")
_alias("Lithuania", "LT", "LTU", "Lituanie")
_alias("Latvia", "LV", "LVA", "Lettonie")
_alias("Estonia", "EE", "EST", "Estonie")
_alias("Finland", "FI", "FIN", "Finlande", "Suomi")
_alias("Sweden", "SE", "SWE", "Suede", "Suède", "Sverige")
_alias("Norway", "NO", "NOR", "Norvege", "Norvège", "Norge")
_alias("Denmark", "DK", "DEN", "Danemark", "DNK")
_alias("Iceland", "IS", "ISL", "Islande")
_alias("Armenia", "AM", "ARM", "Armenie", "Arménie")
_alias("Azerbaijan", "AZ", "AZE", "Azerbaidjan", "Azerbaïdjan")
_alias("Georgia", "GE", "GEO", "Georgie", "Géorgie")
_alias("Kazakhstan", "KZ", "KAZ")
_alias("Uzbekistan", "UZ", "UZB", "Ouzbekistan", "Ouzbékistan")
_alias("Kyrgyzstan", "KG", "KGZ", "Kirghizistan")
_alias("Tajikistan", "TJ", "TJK", "Tadjikistan")
_alias("Turkmenistan", "TM", "TKM", "Turkmenistan")
_alias("Iran", "IR", "IRI", "Iran (Islamic Republic of)", "IRN",
       "Islamic Republic of Iran", "Iran, Islamic Republic of")
_alias("Iraq", "IQ", "IRQ", "Irak")
_alias("India", "IN", "IND", "Inde")
_alias("Pakistan", "PK", "PAK")
_alias("Afghanistan", "AF", "AFG")
_alias("China", "CN", "CHN", "Chine", "Cina")
_alias("Japan", "JP", "JPN", "Japon", "Giappone", "JAP", "Japanska")
_alias("Korea", "KR", "KOR", "South Korea", "Coree", "Corée", "Coree du Sud")
_alias("Vietnam", "VN", "VIE", "Viet Nam", "VNM")
_alias("Thailand", "TH", "THA", "Thailande", "Thaïlande")
_alias("Philippines", "PH", "PHI", "PHL")
_alias("Indonesia", "ID", "INA", "Indonesie", "Indonésie", "IDN")
_alias("Malaysia", "MY", "MAS", "Malaisie", "MYS")
_alias("Cambodia", "KH", "CAM", "Cambodge", "KHM")
_alias("United States", "US", "USA", "Etats-Unis", "États-Unis", "United States of America")
_alias("Canada", "CA", "CAN")
_alias("Mexico", "MX", "MEX", "Mexique")
_alias("Brazil", "BR", "BRA", "Bresil", "Brésil")
_alias("Argentina", "AR", "ARG", "Argentine")
_alias("Colombia", "CO", "COL", "Colombie")
_alias("Chile", "CL", "CHL", "Chili")
_alias("Peru", "PE", "PER", "Perou", "Pérou")
_alias("Venezuela", "VE", "VEN")
_alias("Ecuador", "EC", "ECU", "Equateur", "Équateur")
_alias("Uruguay", "UY", "URU", "URY")
_alias("Cuba", "CU", "CUB")
_alias("Algeria", "DZ", "ALG", "Algerie", "Algérie", "DZA")
_alias("Morocco", "MA", "MAR", "Maroc")
_alias("Tunisia", "TN", "TUN", "Tunisie")
_alias("Egypt", "EG", "EGY", "Egypte", "Égypte")
_alias("Libya", "LY", "LBA", "Libye", "LBY")
_alias("Senegal", "SN", "SEN", "Senegal", "Sénégal")
_alias("Mali", "ML", "MAL", "MLI")
_alias("Ivory Coast", "CI", "CIV", "Cote d'Ivoire", "Côte d'Ivoire")
_alias("Burkina Faso", "BF", "BUR", "BFA")
_alias("Guinea", "GN", "GUI", "Guinee", "Guinée", "Guinea Conakry", "GIN")
_alias("Cameroon", "CM", "CMR", "Cameroun")
_alias("Benin", "BJ", "BEN", "Benin", "Bénin")
_alias("Togo", "TG", "TOG", "TGO")
_alias("Niger", "NE", "NIG", "NER")
_alias("Nigeria", "NG", "NGR", "NGA")
_alias("Ghana", "GH", "GHA")
_alias("Congo", "CG", "CGO", "Congo Brazzaville", "Rep Congo",
       "Republic of the Congo", "Republique du Congo")
_alias("DR Congo", "CD", "COD", "Congo Kinshasa", "RD Congo",
       "Republique Democratique du Congo", "Democratic Republic of Congo")
_alias("Gabon", "GA", "GAB")
_alias("Madagascar", "MG", "MAD", "MDG", "MADA")
_alias("Mauritius", "MU", "MRI", "Maurice", "Ile Maurice", "MUS")
_alias("Reunion", "RE", "REU", "La Reunion", "La Réunion", "Réunion")
# The other French overseas territories, registered the same way Réunion already
# is: each enters savate as its own ligue and its competitors are printed under
# the territory, not under France. Folding them into France would erase the only
# record the archive has of Caribbean savate.
_alias("Martinique", "MQ", "MTQ", "Martinique (972)")
_alias("Guadeloupe", "GP", "GLP", "Guadeloupe (971)")
_alias("French Guiana", "GF", "GUF", "Guyane", "Guyane Francaise",
       "Guyane Française")
_alias("Saint-Martin", "MF", "SMF", "Saint Martin", "St-Martin", "St Martin")
_alias("New Caledonia", "NC", "NCL", "Nouvelle-Caledonie", "Nouvelle Caledonie",
       "Nouvelle-Calédonie")
_alias("Singapore", "SG", "SGP", "Singapour", "Singapur")
_alias("South Africa", "ZA", "RSA", "Afrique du Sud", "ZAF")
_alias("Kenya", "KE", "KEN")
_alias("Ethiopia", "ET", "ETH", "Ethiopie", "Éthiopie")
_alias("Australia", "AU", "AUS", "Australie")
_alias("New Zealand", "NZ", "NZL", "Nouvelle-Zelande", "Nouvelle-Zélande")
_alias("Israel", "IL", "ISR")
_alias("Lebanon", "LB", "LIB", "Liban", "LBN")
_alias("Syria", "SY", "SYR", "Syrie")
_alias("Jordan", "JO", "JOR", "Jordanie")
_alias("Saudi Arabia", "SA", "KSA", "Arabie Saoudite", "SAU")
_alias("United Arab Emirates", "AE", "UAE", "Emirats Arabes Unis", "ARE")
_alias("Qatar", "QA", "QAT")
_alias("Kuwait", "KW", "KUW", "Koweit", "Koweït", "KWT")
_alias("Nepal", "NP", "NEP", "NPL")
_alias("Malta", "MT", "MLT", "Malte")
_alias("Cyprus", "CY", "CYP", "Chypre")
_alias("Chinese Taipei", "TW", "TPE", "Taipei", "Taiwan")
_alias("Hong Kong", "HK", "HKG", "Hong Kong, China")
_alias("Guinea-Bissau", "GW", "GBS", "Guinea Bissau", "Guinee-Bissau")
_alias("Luxembourg", "LU", "LUX")
_alias("Monaco", "MC", "MON", "MCO")
_alias("Sri Lanka", "LK", "SRI", "LKA")
_alias("Bangladesh", "BD", "BAN", "BGD")
_alias("Mongolia", "MN", "MGL", "Mongolie")
_alias("Bolivia", "BO", "BOL", "Bolivie")
_alias("Paraguay", "PY", "PAR", "PRY")
_alias("Costa Rica", "CR", "CRC", "CRI")
_alias("Panama", "PA", "PAN")
_alias("Haiti", "HT", "HAI", "Haïti", "HTI")
_alias("Dominican Republic", "DO", "DOM", "Republique Dominicaine")
_alias("Angola", "AO", "ANG", "AGO")
_alias("Mozambique", "MZ", "MOZ")
_alias("Zimbabwe", "ZW", "ZIM", "ZWE")
_alias("Tanzania", "TZ", "TAN", "Tanzanie", "TZA")
_alias("Uganda", "UG", "UGA", "Ouganda")
_alias("Rwanda", "RW", "RWA")
_alias("Burundi", "BI", "BDI")
_alias("Chad", "TD", "CHA", "Tchad", "TCD")
_alias("Mauritania", "MR", "MTN", "Mauritanie")
_alias("Sudan", "SD", "SUD", "Soudan")
_alias("Seychelles", "SC", "SEY", "SYC")
_alias("Comoros", "KM", "COM", "Comores")
_alias("Djibouti", "DJ", "DJI")
_alias("Sierra Leone", "SL", "SLE")
_alias("Liberia", "LR", "LBR")
_alias("Gambia", "GM", "GAM", "Gambie", "GMB")
_alias("Cape Verde", "CV", "CPV", "Cap-Vert")
_alias("Central African Republic", "CF", "CAF", "Centrafrique")

# Not nations, but not damage either. The federation prints these where a
# nation would go and the page should say so plainly rather than show a flag
# it has no right to show or an "unknown" that reads as a parsing failure.
_FLAGLESS = {
    # "Rsf" is NOT here on purpose. It appears twenty times beside Russian names
    # from 2021 and is almost certainly the Russian Savate Federation competing
    # under a neutral designation - but no document in this archive writes the
    # letters out, and a search of every fetched source found none. Almost is
    # not verified, so it renders as the sheet printed it, without a flag.
    "neutral athlete": "Neutral Athlete",
    "neutral athletes": "Neutral Athlete",
    "individual neutral athlete": "Neutral Athlete",
    "refugee": "Refugee Team",
    "refugee team": "Refugee Team",
}


# The same kerning split that damages names reaches country cells too, where it
# lands mid-word instead of on a capital: "Germ Any", "Denm Ark". Closing every
# space and matching that against the table is safe only because the table is a
# closed list of attested spellings - it can turn a broken cell into a nation it
# already knows, and can never invent one.
_NOSPACE = {}


def _index_nospace():
    for key, value in _ALIASES.items():
        squeezed = key.replace(" ", "")
        # Ambiguity means the repair has no single answer, so it declines.
        if squeezed in _NOSPACE and _NOSPACE[squeezed] != value:
            _NOSPACE[squeezed] = None
        else:
            _NOSPACE.setdefault(squeezed, value)


_index_nospace()

_REGIONAL_A = 0x1F1E6


def flag(iso2):
    """The Unicode regional-indicator pair for an ISO 3166-1 alpha-2 code.

    Flag emoji are the only flags an Artifact can show - the CSP blocks every
    external image, so a flag CDN is not an option. Returns "" for an unknown
    code rather than a box glyph.
    """
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(_REGIONAL_A + ord(c) - ord("A")) for c in iso2.upper())


class Country:
    """A resolved nation: canonical name, codes and flag, or unresolved.

    `known` without an `iso` is the third case: a designation the federation
    prints in the nation column that is not a nation - a neutral athlete, a
    refugee team. It has a name to show and no flag it is entitled to.
    """

    __slots__ = ("raw", "name", "iso", "code", "flag", "known")

    def __init__(self, raw, name="", iso="", known=False):
        self.raw = raw
        self.name = name
        self.iso = iso
        self.code = _CODES.get(name, "")
        self.flag = flag(iso)
        self.known = known

    def __repr__(self):
        return (f"Country({self.name!r}, {self.iso!r})" if self.known
                else f"Country(unresolved {self.raw!r})")


def country(raw):
    """Resolve a printed country string, or report it unresolved.

    An unresolved value is not dropped and not guessed at: the page shows the
    string the source printed, without a flag, which is the honest rendering of
    "the federation wrote something we do not recognise".
    """
    if not raw or not raw.strip():
        return Country(raw or "")

    text = _collapse(raw)
    # "(France)" and "(Fra)" both appear as whole country cells - but strip the
    # brackets only when they wrap the whole cell. Stripping them from either
    # end blinds the table to every name that merely ends in one, which is how
    # the registered spelling "Iran (Islamic Republic of)" went unrecognised.
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = _LEAD_JUNK.sub("", _TRAIL_JUNK.sub("", text))

    key = fold(text)

    hit = _ALIASES.get(key)
    if hit:
        return Country(raw, hit[0], hit[1], known=True)

    label = _FLAGLESS.get(key)
    if label:
        return Country(raw, label, "", known=True)

    # A cell that leaked a fighter name usually still ends in the country:
    # "ABDINOV (Russie)" -> Russie. Only a parenthesised tail is trusted.
    found = _PAREN_TAIL.search(_collapse(raw))
    if found:
        hit = _ALIASES.get(fold(found.group(1)))
        if hit:
            return Country(raw, hit[0], hit[1], known=True)

    # Last resort: the kerning split. "Germ Any" is Germany and nothing else.
    hit = _NOSPACE.get(key.replace(" ", ""))
    if hit:
        return Country(raw, hit[0], hit[1], known=True)

    return Country(raw)


def countries():
    """Every canonical nation this module knows, as {name: iso}."""
    return {name: iso for name, iso in _ALIASES.values()}

# ---- what a nation is called, in the languages the site speaks -----------
#
# The canonical name is English because the federations' own English documents
# are the most consistent, but an interface in French must not print "Croatia"
# and a search for "Croatie" must not come back empty. So each nation carries
# its name in all three, and every spelling ever attested above stays in the
# search key. A reader types what they know; the archive answers.

_LOCAL = {
    "France": ("France", "Francia"),
    "Belgium": ("Belgique", "Bélgica"),
    "Italy": ("Italie", "Italia"),
    "Croatia": ("Croatie", "Croacia"),
    "Serbia": ("Serbie", "Serbia"),
    "Slovenia": ("Slovénie", "Eslovenia"),
    "Russia": ("Russie", "Rusia"),
    "Ukraine": ("Ukraine", "Ucrania"),
    "Turkey": ("Turquie", "Turquía"),
    "Germany": ("Allemagne", "Alemania"),
    "Greece": ("Grèce", "Grecia"),
    "Spain": ("Espagne", "España"),
    "Portugal": ("Portugal", "Portugal"),
    "Netherlands": ("Pays-Bas", "Países Bajos"),
    "United Kingdom": ("Royaume-Uni", "Reino Unido"),
    "Ireland": ("Irlande", "Irlanda"),
    "Switzerland": ("Suisse", "Suiza"),
    "Austria": ("Autriche", "Austria"),
    "Hungary": ("Hongrie", "Hungría"),
    "Romania": ("Roumanie", "Rumanía"),
    "Bulgaria": ("Bulgarie", "Bulgaria"),
    "Poland": ("Pologne", "Polonia"),
    "Czech Republic": ("Tchéquie", "Chequia"),
    "Slovakia": ("Slovaquie", "Eslovaquia"),
    "Bosnia and Herzegovina": ("Bosnie-Herzégovine", "Bosnia y Herzegovina"),
    "Montenegro": ("Monténégro", "Montenegro"),
    "North Macedonia": ("Macédoine du Nord", "Macedonia del Norte"),
    "Albania": ("Albanie", "Albania"),
    "Moldova": ("Moldavie", "Moldavia"),
    "Belarus": ("Biélorussie", "Bielorrusia"),
    "Lithuania": ("Lituanie", "Lituania"),
    "Latvia": ("Lettonie", "Letonia"),
    "Estonia": ("Estonie", "Estonia"),
    "Finland": ("Finlande", "Finlandia"),
    "Sweden": ("Suède", "Suecia"),
    "Norway": ("Norvège", "Noruega"),
    "Denmark": ("Danemark", "Dinamarca"),
    "Iceland": ("Islande", "Islandia"),
    "Armenia": ("Arménie", "Armenia"),
    "Azerbaijan": ("Azerbaïdjan", "Azerbaiyán"),
    "Georgia": ("Géorgie", "Georgia"),
    "Kazakhstan": ("Kazakhstan", "Kazajistán"),
    "Uzbekistan": ("Ouzbékistan", "Uzbekistán"),
    "Kyrgyzstan": ("Kirghizistan", "Kirguistán"),
    "Tajikistan": ("Tadjikistan", "Tayikistán"),
    "Turkmenistan": ("Turkménistan", "Turkmenistán"),
    "Iran": ("Iran", "Irán"),
    "Iraq": ("Irak", "Irak"),
    "India": ("Inde", "India"),
    "Pakistan": ("Pakistan", "Pakistán"),
    "Afghanistan": ("Afghanistan", "Afganistán"),
    "China": ("Chine", "China"),
    "Japan": ("Japon", "Japón"),
    "Korea": ("Corée du Sud", "Corea del Sur"),
    "Vietnam": ("Viêt Nam", "Vietnam"),
    "Thailand": ("Thaïlande", "Tailandia"),
    "Philippines": ("Philippines", "Filipinas"),
    "Indonesia": ("Indonésie", "Indonesia"),
    "Malaysia": ("Malaisie", "Malasia"),
    "Cambodia": ("Cambodge", "Camboya"),
    "United States": ("États-Unis", "Estados Unidos"),
    "Canada": ("Canada", "Canadá"),
    "Mexico": ("Mexique", "México"),
    "Brazil": ("Brésil", "Brasil"),
    "Argentina": ("Argentine", "Argentina"),
    "Colombia": ("Colombie", "Colombia"),
    "Chile": ("Chili", "Chile"),
    "Peru": ("Pérou", "Perú"),
    "Venezuela": ("Venezuela", "Venezuela"),
    "Ecuador": ("Équateur", "Ecuador"),
    "Uruguay": ("Uruguay", "Uruguay"),
    "Cuba": ("Cuba", "Cuba"),
    "Algeria": ("Algérie", "Argelia"),
    "Morocco": ("Maroc", "Marruecos"),
    "Tunisia": ("Tunisie", "Túnez"),
    "Egypt": ("Égypte", "Egipto"),
    "Libya": ("Libye", "Libia"),
    "Senegal": ("Sénégal", "Senegal"),
    "Mali": ("Mali", "Malí"),
    "Ivory Coast": ("Côte d’Ivoire", "Costa de Marfil"),
    "Burkina Faso": ("Burkina Faso", "Burkina Faso"),
    "Guinea": ("Guinée", "Guinea"),
    "Cameroon": ("Cameroun", "Camerún"),
    "Benin": ("Bénin", "Benín"),
    "Togo": ("Togo", "Togo"),
    "Niger": ("Niger", "Níger"),
    "Nigeria": ("Nigeria", "Nigeria"),
    "Ghana": ("Ghana", "Ghana"),
    "Congo": ("Congo", "Congo"),
    "DR Congo": ("RD Congo", "RD Congo"),
    "Gabon": ("Gabon", "Gabón"),
    "Madagascar": ("Madagascar", "Madagascar"),
    "Mauritius": ("Maurice", "Mauricio"),
    "Reunion": ("La Réunion", "La Reunión"),
    "South Africa": ("Afrique du Sud", "Sudáfrica"),
    "Kenya": ("Kenya", "Kenia"),
    "Ethiopia": ("Éthiopie", "Etiopía"),
    "Australia": ("Australie", "Australia"),
    "New Zealand": ("Nouvelle-Zélande", "Nueva Zelanda"),
    "Israel": ("Israël", "Israel"),
    "Lebanon": ("Liban", "Líbano"),
    "Syria": ("Syrie", "Siria"),
    "Jordan": ("Jordanie", "Jordania"),
    "Saudi Arabia": ("Arabie saoudite", "Arabia Saudí"),
    "United Arab Emirates": ("Émirats arabes unis", "Emiratos Árabes Unidos"),
    "Qatar": ("Qatar", "Catar"),
    "Kuwait": ("Koweït", "Kuwait"),
    "Nepal": ("Népal", "Nepal"),
    "Malta": ("Malte", "Malta"),
    "Cyprus": ("Chypre", "Chipre"),
    "Chinese Taipei": ("Taipei chinois", "Taipéi Chino"),
    "Hong Kong": ("Hong Kong", "Hong Kong"),
    "Guinea-Bissau": ("Guinée-Bissau", "Guinea-Bisáu"),
    "Luxembourg": ("Luxembourg", "Luxemburgo"),
    "Monaco": ("Monaco", "Mónaco"),
    "Sri Lanka": ("Sri Lanka", "Sri Lanka"),
    "Bangladesh": ("Bangladesh", "Bangladés"),
    "Mongolia": ("Mongolie", "Mongolia"),
    "Bolivia": ("Bolivie", "Bolivia"),
    "Paraguay": ("Paraguay", "Paraguay"),
    "Costa Rica": ("Costa Rica", "Costa Rica"),
    "Panama": ("Panama", "Panamá"),
    "Haiti": ("Haïti", "Haití"),
    "Dominican Republic": ("République dominicaine", "República Dominicana"),
    "Angola": ("Angola", "Angola"),
    "Mozambique": ("Mozambique", "Mozambique"),
    "Zimbabwe": ("Zimbabwe", "Zimbabue"),
    "Tanzania": ("Tanzanie", "Tanzania"),
    "Uganda": ("Ouganda", "Uganda"),
    "Rwanda": ("Rwanda", "Ruanda"),
    "Burundi": ("Burundi", "Burundi"),
    "Chad": ("Tchad", "Chad"),
    "Mauritania": ("Mauritanie", "Mauritania"),
    "Sudan": ("Soudan", "Sudán"),
    "Seychelles": ("Seychelles", "Seychelles"),
    "Comoros": ("Comores", "Comoras"),
    "Djibouti": ("Djibouti", "Yibuti"),
    "Sierra Leone": ("Sierra Leone", "Sierra Leona"),
    "Liberia": ("Liberia", "Liberia"),
    "Gambia": ("Gambie", "Gambia"),
    "Cape Verde": ("Cap-Vert", "Cabo Verde"),
    "Central African Republic": ("République centrafricaine",
                                 "República Centroafricana"),
    "Neutral Athlete": ("Athlète neutre", "Atleta neutral"),
    "Refugee Team": ("Équipe des réfugiés", "Equipo de refugiados"),
}


def names(canonical):
    """(english, french, spanish) for a nation. Falls back to the English."""
    local = _LOCAL.get(canonical)
    if not local:
        return canonical, canonical, canonical
    return canonical, local[0], local[1]


def spellings(canonical):
    """Every attested spelling of a nation, for a search key.

    Includes the codes and the three display names, so "Croatie", "Kroatien",
    "CRO" and "Croacia" all reach the same row whatever language the reader
    is thinking in.
    """
    found = {canonical}
    for key, (name, _iso) in _ALIASES.items():
        if name == canonical:
            found.add(key)
    found.update(x for x in names(canonical) if x)
    code = _CODES.get(canonical)
    if code:
        found.add(code)
    return sorted(found)
