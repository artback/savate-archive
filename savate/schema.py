"""The canonical shape of a savate result, and the vocabularies it is built on.

One tournament's data is only worth keeping if it can sit in the same table as
the next one's. That is the whole job of this module: it defines what a bout row
means, independently of any site, spreadsheet or file format it arrived in.
Sources vary wildly and without warning - this year's championship is scraped
HTML, next year's may be a shared Google Sheet - so nothing here may assume a
source. Adapters map into these fields; the fields never bend to an adapter.

Two rules keep the table honest as sources come and go:

  * A field is either read from the source or left empty. Nothing is invented,
    and "unresolved" is a real, expected state - a result nobody published is
    not the same as a result of zero.
  * Every row records where its outcome came from, in `result_source`. A value
    read off a scoresheet and a value deduced from the next round are both
    useful and must never be confused, so they are labelled, not blended.
"""

from dataclasses import asdict, dataclass, field, fields

# Rounds, smallest bracket first. Adapters map whatever their source calls a
# round onto one of these; PHASE_ALIASES covers the wordings seen so far.
PHASES = ["poule", "r64", "r32", "r16", "quarter", "semi", "bronze", "final"]

PHASE_ALIASES = {
    "poule": "poule", "pool": "poule", "group": "poule", "grupo": "poule",
    "1/32": "r32", "1/16": "r16", "1/8": "r16", "r16": "r16",
    "1/4": "quarter", "quart": "quarter", "quarterfinal": "quarter",
    "quarter-final": "quarter", "cuartos": "quarter",
    "1/2": "semi", "demi": "semi", "semifinal": "semi", "semi-final": "semi",
    "semifinale": "semi", "semis": "semi",
    "bronze": "bronze", "3rd": "bronze", "3e": "bronze", "third": "bronze",
    "petite finale": "bronze",
    "final": "final", "finale": "final", "gold": "final",
}

# How a bout ended. "points" covers any bout scored to a decision; the rest are
# the ways a bout ends without one.
DECISIONS = ["points", "forfait", "disqualification", "abandon", "draw", ""]

# Where the outcome came from. Ranked: a reported result beats a derived one,
# and both beat nothing.
SOURCES = ["reported", "scoresheet", "inferred", ""]

STATUSES = ["decided", "unresolved"]


@dataclass
class Report:
    """What an adapter wants to say about a read, beyond the rows themselves.

    Every adapter returns one, whether or not it has anything to complain about.
    A uniform report is what lets the CLI treat a federation it has never seen
    the same as one it ships with: print the problems, refuse the build if the
    rows do not validate, and never require the caller to know which adapter ran.
    """

    source: str = ""
    adapter: str = ""
    read: int = 0                                  # units the adapter consumed
    problems: list = field(default_factory=list)   # things a human should see
    notes: dict = field(default_factory=dict)      # adapter-specific detail

    def problem(self, message):
        self.problems.append(message)


@dataclass
class Tournament:
    """One competition. `slug` is the key every bout row carries."""

    slug: str
    name: str = ""
    discipline: str = ""      # assaut, combat
    # Scope and format are independent: a gala can be international and a
    # championship can be national. See savate/competition.py.
    level: str = ""           # world, european, african, asian, national, ...
    format: str = ""          # championship, cup, gala, pro, masterships, open
    age_class: str = ""       # Young, Junior, Senior, where a title says
    year: str = ""
    start_date: str = ""
    end_date: str = ""
    city: str = ""
    country: str = ""
    source: str = ""          # URL, file path, sheet id - whatever it came from
    adapter: str = ""         # which adapter read it
    fetched_at: str = ""
    # competition groups multiple stage documents (qualifying, semi-finals,
    # finals) under one championship heading in the UI.  Empty means the
    # tournament is its own competition.  Non-empty means it shares a
    # competition slug with other stages; the *primary* document (usually
    # the finals) carries the championship name in its slug / meta.
    competition: str = ""

    def as_dict(self):
        return asdict(self)


@dataclass
class Bout:
    """One bout. Every field is a string; empty means the source did not say.

    Points stay strings deliberately. A source that writes "3" and one that
    writes "3.0" should not become different numbers, and a source that writes
    nothing must not become a zero.
    """

    tournament: str
    bout_id: str = ""
    date: str = ""
    time: str = ""
    ring: str = ""
    category: str = ""        # the source's own label, kept verbatim
    gender: str = ""
    age_class: str = ""
    weight_kg: str = ""
    weight_bound: str = ""    # under, over
    phase: str = ""           # one of PHASES
    poule: str = ""
    red: str = ""
    red_country: str = ""
    # The club or federation a source printed beside the name, where it printed
    # one. Most do not; the Italian and Galician sheets do, inside the name cell.
    red_club: str = ""
    # The weight actually recorded at the weigh-in, where a sheet printed one
    # beside the name. Not the same fact as weight_kg, which is the class.
    red_weighed: str = ""
    blue: str = ""
    blue_country: str = ""
    blue_club: str = ""
    blue_weighed: str = ""
    red_points: str = ""
    blue_points: str = ""
    # Warnings (avertissements) are not decoration: they are the second rung of
    # the poule ranking ladder, and three of them is a disqualification.
    red_warnings: str = ""
    blue_warnings: str = ""
    winner_corner: str = ""   # red, blue, or empty
    winner: str = ""
    loser: str = ""
    decision: str = ""        # one of DECISIONS
    # How that decision was reached, in the source's own word - "Unanimité",
    # "Majorité", "KO". The field above says a bout ended on points; this says
    # the judges were unanimous about it, which is a different fact and one
    # several federations publish.
    decision_detail: str = ""
    status: str = ""          # one of STATUSES
    result_source: str = ""   # one of SOURCES

    def as_dict(self):
        return asdict(self)


@dataclass
class Placing:
    """One medal or placing in one weight class.

    A podium is not a bout and must not be stored as one - it says who finished
    where, not who beat whom, and inventing the bouts that produced it would be
    fabrication. It is worth keeping as its own fact because for most of savate's
    published history it is the only record there is: before 2023 the federations
    printed podiums and nothing else.
    """

    tournament: str
    placing_id: str = ""
    category: str = ""
    gender: str = ""
    age_class: str = ""
    weight_kg: str = ""
    weight_bound: str = ""
    rank: str = ""            # "1", "2", "3"
    medal: str = ""           # gold, silver, bronze
    fighter: str = ""
    country: str = ""
    club: str = ""
    weighed: str = ""
    result_source: str = ""

    def as_dict(self):
        return asdict(self)


MEDALS = {"1": "gold", "2": "silver", "3": "bronze"}

BOUT_FIELDS = [f.name for f in fields(Bout)]
PLACING_FIELDS = [f.name for f in fields(Placing)]
TOURNAMENT_FIELDS = [f.name for f in fields(Tournament)]


def phase_of(label):
    """Map a source's round wording onto a canonical phase, or "" if unknown.

    Unknown is returned rather than guessed: a round this does not recognise is
    something to go and look at, not something to file under "final".
    """
    text = " ".join(str(label or "").split()).lower().strip()
    if not text:
        return ""
    if text in PHASE_ALIASES:
        return PHASE_ALIASES[text]
    for alias, phase in PHASE_ALIASES.items():
        if alias in text:
            return phase
    return ""


def check_placing(placing):
    """Complaints about one placing, as a list."""
    bad = []
    if not placing.tournament:
        bad.append("no tournament")
    if not placing.fighter:
        bad.append("no fighter")
    # A placing is a finishing position, not necessarily a podium one. Most
    # federations print only the top three, but the university championships
    # publish a full classification down to sixth, and discarding fourth place
    # because no medal hangs on it would throw away a result the document
    # states. Ranks beyond third simply carry no medal.
    if not str(placing.rank).isdigit() or int(placing.rank) < 1:
        bad.append(f"rank {placing.rank!r} is not a finishing position")
    elif placing.medal != MEDALS.get(placing.rank, ""):
        bad.append(f"medal {placing.medal!r} does not match rank {placing.rank!r}")
    if placing.result_source not in SOURCES:
        bad.append(f"result_source {placing.result_source!r} is not known")
    return bad


def check(bout):
    """Complaints about one bout, as a list. Empty means it is well formed."""
    bad = []
    if not bout.tournament:
        bad.append("no tournament")
    if not (bout.red and bout.blue):
        bad.append("a corner is missing a fighter")
    if bout.phase and bout.phase not in PHASES:
        bad.append(f"phase {bout.phase!r} is not one of {PHASES}")
    if bout.decision not in DECISIONS:
        bad.append(f"decision {bout.decision!r} is not one of {DECISIONS}")
    if bout.result_source not in SOURCES:
        bad.append(f"result_source {bout.result_source!r} is not known")
    if bout.status not in STATUSES:
        bad.append(f"status {bout.status!r} is not one of {STATUSES}")
    if bout.winner_corner not in ("red", "blue", ""):
        bad.append(f"winner_corner {bout.winner_corner!r} is not a corner")
    # A bout can be decided without the corner being published. The French
    # federation's finals sheets name the winner and never say which corner
    # anyone stood in, and red/blue mean corner in this archive - so filling
    # one in to satisfy a check would be inventing the fact the check exists
    # to protect. Decided therefore means "a winner is known", by corner or by
    # name, and the two are cross-checked only where both are present.
    decided = bout.status == "decided"
    if decided and not (bout.winner_corner or bout.winner):
        bad.append("decided but names neither a winning corner nor a winner")
    if not decided and (bout.winner_corner or bout.winner):
        bad.append("not decided, yet a winner is named")
    if decided and not bout.result_source:
        bad.append("decided but does not say where the result came from")
    if bout.winner_corner:
        expected = {"red": bout.red, "blue": bout.blue}[bout.winner_corner]
        if bout.winner != expected:
            bad.append("winner does not match the winning corner")
    elif bout.winner and bout.winner not in (bout.red, bout.blue):
        bad.append("the winner is not one of the two fighters")
    if bout.red_points and bout.blue_points and bout.winner_corner:
        try:
            higher = "red" if float(bout.red_points) > float(bout.blue_points) \
                else "blue" if float(bout.blue_points) > float(bout.red_points) else ""
        except ValueError:
            higher = ""
            bad.append("points are not numbers")
        if higher and bout.decision == "points" and higher != bout.winner_corner:
            bad.append("the corner with more points is not the winner")
    return bad
