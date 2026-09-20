"""What kind of competition a tournament is, read from what it is called.

A world title, a continental title, a national title, a gala and a professional
bout are not the same achievement, and an archive that files them on one shelf
tells a competitor nothing. Beating the European champion in a European final is
a career; beating the same man on a gala card is an evening. The interface has
to be able to say which, so the data has to carry it.

Two axes, because they are genuinely independent:

    scope   how far the field was drawn from - world, continental (and which
            continent), national, regional, club
    format  what was being contested - championship, cup, gala, professional

A national championship and a world championship share a format and differ in
scope. A gala and a championship can both be international and differ in
format. Collapsing them into one "level" column, as this archive did, loses the
distinction the reader most wants.

*Nothing here is invented.* Every value is read out of the text the federation
itself published - "African Savate Championships" says african and championship
in so many words. Where a name says nothing, the field stays empty and the
interface shows it as unstated. A manifest entry that declares its own scope or
format always wins: this module only fills silence.

Savate pro and gala have no entries in the archive yet. They are defined here
anyway, because the vocabulary is what lets an adapter for them be written
without touching anything else - which is the same reason `adapters/` exists.
"""

import re
from urllib.parse import unquote

# Scope, widest first. Order matters: it is the order the interface groups by,
# and the order a tie is broken in when a name mentions two.
SCOPES = ["world", "european", "african", "asian", "panamerican", "oceanian",
          "national", "regional", "club"]

SCOPE_LABELS = {
    "world": "Monde",
    "european": "Europe",
    "african": "Afrique",
    "asian": "Asie",
    "panamerican": "Panaméricain",
    "oceanian": "Océanie",
    "national": "National",
    "regional": "Régional",
    "club": "Club",
}

# The continental scopes, for an interface that wants "continental" as one idea.
CONTINENTAL = {"european", "african", "asian", "panamerican", "oceanian"}

FORMATS = ["championship", "cup", "masterships", "open", "gala", "pro"]

FORMAT_LABELS = {
    "championship": "Championnat",
    "cup": "Coupe",
    "masterships": "Masterships",
    "open": "Open",
    "gala": "Gala",
    "pro": "Savate Pro",
}

# Read in order; the first hit wins, so the more specific patterns come first.
_SCOPE_PATTERNS = [
    ("panamerican", r"\bpan[\s-]?american|\bpanamericain|\bpanaméricain"),
    ("african", r"\bafrican\b|\bafrique\b|\bafricain"),
    ("asian", r"\basian\b|\basie\b|\basiatique"),
    ("oceanian", r"\boceania\b|\boc[ée]anie\b"),
    ("european", r"\beurope\b|\beuropean\b|\beurop[ée]en"),
    ("world", r"\bworld\b|\bmonde\b|\bmondial|\bwm\b"),
    ("national", r"\bnational\b|\bnationaux\b|\bchampionnat de france\b"
                 r"|\bfrance\b(?!\s*\))"),
    ("regional", r"\bregional\b|\br[ée]gional|\bligue\b|\bd[ée]partemental"),
]

_FORMAT_PATTERNS = [
    ("pro", r"\bsavate\s*pro\b|\bprofessional\b|\bprofessionnel"),
    ("gala", r"\bgala\b|\bexhibition\b|\binterclub"),
    ("masterships", r"\bmastership"),
    ("cup", r"\bcup\b|\bcoupe\b"),
    ("open", r"\bopen\b|\btournoi\b|\btournament\b(?!.*\bchampionship)"),
    ("championship", r"\bchampionship|\bchampionnat|\bchamps?\b"),
]

_DISCIPLINE_PATTERNS = [
    ("assaut", r"\bassaut\b"),
    ("combat", r"\bcombat\b|\bfull[\s-]?contact\b"),
]

# Age classes a title states outright.
_AGE_PATTERNS = [
    ("Young", r"\byouth\b|\bjeune|\bcadet|\bminime|\b13\s*(&|and|et)\s*14\b"),
    ("Junior", r"\bjunior\b"),
    ("Senior", r"\bsenior\b"),
]

# A source domain is evidence of scope when the title is silent: the French
# federation publishes its own national results, and labels the international
# ones as world or european in the title. So an ffsavate document that names
# neither is the national championship - and one that names either is not.
_DOMAIN_SCOPE = {
    "ffsavate": "national",
    "ffsbf": "national",
}

_YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def clean_title(name):
    """Undo URL encoding and collapse whitespace in a published title."""
    text = unquote(str(name or ""))
    text = text.replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _first(patterns, text):
    for value, pattern in patterns:
        if re.search(pattern, text, re.I):
            return value
    return ""


def scope(name, source=""):
    """Where the field was drawn from, or "" if the name does not say."""
    found = _first(_SCOPE_PATTERNS, clean_title(name))
    if found:
        return found
    for marker, value in _DOMAIN_SCOPE.items():
        if marker in str(source or "").lower():
            return value
    return ""


def competition_format(name):
    """What was being contested, or "" if the name does not say."""
    return _first(_FORMAT_PATTERNS, clean_title(name))


def discipline(name):
    """assaut or combat, where the title states one."""
    return _first(_DISCIPLINE_PATTERNS, clean_title(name))


def age_class(name):
    """Young, Junior or Senior, where the title states one."""
    return _first(_AGE_PATTERNS, clean_title(name))


def stated_year(name):
    """The latest year printed in a title, or "".

    A results document names its own competition year, and that is better
    evidence than a manifest field a human typed. The latest is taken because
    titles like "World Youth 2023 - Pool Results" carry one year, while a
    re-publication may carry two.
    """
    years = _YEAR.findall(clean_title(name))
    return max(years) if years else ""


def classify(name, source="", declared=None):
    """Everything readable from a tournament's own title.

    `declared` is the manifest's own metadata. Anything it states is kept
    exactly; this only fills what it left empty, and reports where the title
    disagrees with it so a human can look rather than be overruled silently.
    """
    declared = declared or {}
    title = clean_title(name)

    out = {
        "name": title,
        "level": declared.get("level") or scope(name, source),
        "format": declared.get("format") or competition_format(name),
        "discipline": declared.get("discipline") or discipline(name),
        "age_class": declared.get("age_class") or age_class(name),
        "year": declared.get("year") or stated_year(name),
    }

    notes = []
    if title != str(name or "").strip():
        notes.append(f"title repaired: {name!r} -> {title!r}")
    printed = stated_year(name)
    if printed and declared.get("year") and printed != declared["year"]:
        notes.append(f"year: manifest says {declared['year']}, "
                     f"the document is titled {printed}")
    out["notes"] = notes
    return out


# How each scope attaches to a format in French. Most take a complement
# ("Championnat du Monde"); panamerican and the domestic scopes take an
# adjective instead ("Championnat panaméricain"), which is why this is a table
# and not a rule with an apostrophe in it.
_SCOPE_SUFFIX = {
    "world": "du Monde",
    "european": "d'Europe",
    "african": "d'Afrique",
    "asian": "d'Asie",
    "oceanian": "d'Océanie",
    "panamerican": "panaméricain",
    "national": "national",
    "regional": "régional",
    "club": "interclubs",
}


def label(level, fmt):
    """How the interface names a competition: "Championnat du Monde".

    Savate Pro and a gala name themselves. Neither is a scope's title to award,
    so neither takes one: a professional card in Paris is Savate Pro, not
    "Savate Pro national".
    """
    if fmt in ("pro", "gala"):
        return FORMAT_LABELS[fmt]

    scope_name = SCOPE_LABELS.get(level, "")
    format_name = FORMAT_LABELS.get(fmt, "")
    suffix = _SCOPE_SUFFIX.get(level, "")

    if not format_name:
        return scope_name
    if not suffix:
        return format_name
    return f"{format_name} {suffix}"
