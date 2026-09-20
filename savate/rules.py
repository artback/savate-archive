"""Savate competition rules: scoring, ranking, draws and brackets.

Everything here was derived from a real championship (302 bouts, 61 poules) and
is checked against it in tests/test_rules.py, rather than taken from memory of
how the sport is supposed to work.

Scoring, in assaut. Across 231 poule bouts there were no exceptions:

    decision            winner   loser   loser's warnings
    points                 3       1          0-2
    forfait                3       0           0
    disqualification       3      -1        always 3

Three warnings is not a tie-break input, then - it is a disqualification, and
the -1 is its scoreline.

Ranking a poule: points, then head-to-head, then warnings, then weight, each
rung applied only to the fighters the rung above left level.

Head-to-head sits above warnings on the evidence of the federation's own
standings. In the 2025 world youth championship a fighter with four warnings is
printed above one with three, on equal points, because he won their meeting -
and that ordering is reproduced exactly for all 22 of that event's poules.
Putting warnings first reproduces only 20. Head-to-head is counted as a mini
league among the tied fighters alone: beating someone who finished below the
group says nothing about the group.

Some ties survive every rung. A perfect cycle - A beat B beat C beat A, level on
points and warnings - gives every fighter one win inside the group and cannot be
ordered. Three of the 2026 world championship's 61 poules are exactly that. The
federation's sheets carry a "Poids" column and a tie-break footnote for this
case, so the criterion is weight, and weight is not something this library will
invent. An unresolved group is reported as unresolved: a competition that cannot
rank its own poule needs a weigh-in sheet, not a tidier algorithm.

The order of the rungs is a property of the competition, not of the sport. It is
passed in, so a federation that ranks differently is a different ladder rather
than a fork of this file.
"""

import itertools
from dataclasses import dataclass, field

WIN = 3
LOSS = 1
LOSS_DISQUALIFIED = -1
FORFEIT = 0

# Reaching this many warnings in a bout is a disqualification, not a penalty.
WARNINGS_FOR_DISQUALIFICATION = 3

# The order FISav's own published standings demonstrate. Pass a different one
# for a body that ranks differently; every name must be in CRITERIA.
LADDER = ("points", "head-to-head", "warnings", "weight")


def bout_points(decision):
    """(winner's points, loser's points) for a decided bout.

    An abandon scores as an ordinary defeat, and that is the federation's rule
    rather than a guess: the barème pays a defeat +1, and a fighter who retires
    has fought and lost. The zero belongs to the forfait, where nobody fought at
    all - which is exactly the distinction the two words draw.

    A draw has no entry. Savate's judges may mark a reprise 2-2, but the
    competition rules this archive was derived from never produced a drawn bout,
    so there is no attested scoring for one and none is invented here.
    """
    if decision == "forfait":
        return WIN, FORFEIT
    if decision == "disqualification":
        return WIN, LOSS_DISQUALIFIED
    if decision in ("points", "abandon", ""):
        return WIN, LOSS
    raise ValueError(f"no scoring rule for decision {decision!r}")


def decision_from_points(winner_points, loser_points, loser_warnings=None):
    """The decision a scoreline implies, or "" if it implies none.

    The inverse of bout_points, for sources that print scores but never say how
    a bout ended - which is most paper results.

    The points a disqualification costs are not the same in every competition:
    the 2026 world championship scores it -1, a 2024 sheet scores it -3. The
    warnings are steadier - three is a disqualification wherever it is recorded -
    so they are consulted when the scoreline alone is not one this recognises.
    """
    if winner_points != WIN:
        return ""
    known = {LOSS: "points", FORFEIT: "forfait",
             LOSS_DISQUALIFIED: "disqualification"}.get(loser_points, "")
    if known:
        return known
    if loser_warnings is not None and loser_warnings >= WARNINGS_FOR_DISQUALIFICATION:
        return "disqualification"
    return ""


@dataclass
class Standing:
    """One fighter's line in a poule table."""

    name: str
    country: str = ""
    points: int = 0
    warnings: int = 0
    wins: int = 0
    bouts: int = 0
    weight: float = None
    rank: int = 0
    # Which criterion put this fighter above the next one. "" at the foot of
    # the table; "unresolved" where the ladder ran out.
    decided_by: str = ""


@dataclass
class PouleResult:
    standings: list = field(default_factory=list)
    # Groups of fighters the ladder could not separate, each as a list of names.
    unresolved: list = field(default_factory=list)
    complete: bool = True      # every pairing in the draw has been fought
    # Bouts whose decision this competition has no scoring rule for. They count
    # as wins and not as points, and saying so is the point.
    unscored: list = field(default_factory=list)

    @property
    def ranked(self):
        return [s.name for s in self.standings]


def _tally(bouts, weights=None, unscored=None):
    """Fighter -> running totals, from the bouts of one poule."""
    rows = {}
    if unscored is None:
        unscored = []

    def row(name, country):
        r = rows.setdefault(name, Standing(name=name, country=country))
        if country and not r.country:
            r.country = country
        if weights and name in weights:
            r.weight = weights[name]
        return r

    for b in bouts:
        red = row(b["red"], b.get("red_country", ""))
        blue = row(b["blue"], b.get("blue_country", ""))
        side = _won_side(b)
        if not side:
            continue
        for who, corner in ((red, "red"), (blue, "blue")):
            who.bouts += 1
            who.warnings += int(b.get(f"{corner}_warnings") or 0)
        winner, loser = (red, blue) if side == "red" else (blue, red)
        winner.wins += 1
        try:
            won, lost = bout_points(b.get("decision", "points"))
        except ValueError:
            # A decision this competition has no scoring rule for. The win is
            # still a win - head-to-head and the win column are unaffected -
            # but no points are invented for it, and the caller is told the
            # table is short of a scoreline rather than handed a wrong one.
            unscored.append(b)
            continue
        winner.points += won
        loser.points += lost
    return rows


def _won_side(bout):
    """"red", "blue" or "" - who won, however the source recorded it.

    Not every federation publishes corners. The French national finals sheets
    name the winner and say nothing about who stood where, and a poule read
    only through `winner_corner` would score every one of those bouts as
    unfought: all fighters on zero points, and a table that cannot be ranked
    for want of a fact the document actually printed.
    """
    corner = bout.get("winner_corner")
    if corner in ("red", "blue"):
        return corner
    winner = (bout.get("winner") or "").strip()
    if not winner:
        return ""
    if winner == bout.get("red"):
        return "red"
    if winner == bout.get("blue"):
        return "blue"
    return ""


def _beat(bouts):
    """{(winner, loser)} over the decided bouts, for head-to-head."""
    out = set()
    for b in bouts:
        side = _won_side(b)
        if side == "red":
            out.add((b["red"], b["blue"]))
        elif side == "blue":
            out.add((b["blue"], b["red"]))
    return out


# Each criterion scores a fighter within the group being split; higher is
# better, and None means "this criterion has nothing to say about them", which
# leaves the group for the next rung rather than ordering it on a missing value.
CRITERIA = {
    "points": lambda name, group, rows, beat, weights: rows[name].points,
    "warnings": lambda name, group, rows, beat, weights: -rows[name].warnings,
    "wins": lambda name, group, rows, beat, weights: rows[name].wins,
    # A mini league among the tied fighters only.
    "head-to-head": lambda name, group, rows, beat, weights: sum(
        1 for other in group if (name, other) in beat),
    "weight": lambda name, group, rows, beat, weights: (
        None if not weights or weights.get(name) is None else -weights[name]),
}


def _split(group, rungs, rows, beat, weights, separated):
    """Order a group by the remaining rungs, recording what separated whom.

    `separated` collects the name of the rung that split each subgroup, so a
    standing can say why it sits where it does. A group no rung can split is
    returned in a stable order and reported by the caller as unresolved.
    """
    if len(group) <= 1 or not rungs:
        return [group]
    rung, rest = rungs[0], rungs[1:]
    score = CRITERIA[rung]
    marks = {name: score(name, group, rows, beat, weights) for name in group}
    if any(mark is None for mark in marks.values()):
        return _split(group, rest, rows, beat, weights, separated)

    buckets = {}
    for name in group:
        buckets.setdefault(marks[name], []).append(name)
    if len(buckets) == 1:
        return _split(group, rest, rows, beat, weights, separated)

    # Only the boundaries *between* buckets belong to this rung. The boundaries
    # inside a bucket were set by the deeper rung that actually split it, and
    # recording them here would overwrite the true reason with this one.
    out, previous_tail = [], None
    for mark in sorted(buckets, reverse=True):
        pieces = _split(sorted(buckets[mark]), rest, rows, beat, weights,
                        separated)
        if previous_tail is not None:
            separated[(previous_tail, pieces[0][0])] = rung
        out.extend(pieces)
        previous_tail = pieces[-1][-1]
    return out


def standings(bouts, weights=None, ladder=LADDER, expected_pairings=None):
    """Rank one poule. `bouts` are that poule's bouts, in canonical form.

    `weights` (fighter -> kg) is consulted only by the "weight" rung, and only
    where every fighter in the tied group has one.
    """
    unknown = [rung for rung in ladder if rung not in CRITERIA]
    if unknown:
        raise ValueError(f"no such ranking criterion: {', '.join(unknown)}")

    unscored = []
    rows = _tally(bouts, weights, unscored)
    beat = _beat(bouts)
    decided = [b for b in bouts if _won_side(b)]

    separated = {}
    pieces = _split(sorted(rows), list(ladder), rows, beat, weights, separated)
    ordered, unresolved = [], []
    for piece in pieces:
        if len(piece) > 1:
            unresolved.append(sorted(piece))
        ordered.extend(rows[name] for name in piece)

    for i, s in enumerate(ordered, 1):
        s.rank = i
    for above, below in zip(ordered, ordered[1:]):
        above.decided_by = separated.get((above.name, below.name), "unresolved")
    if ordered:
        ordered[-1].decided_by = ""

    complete = (len(decided) == len(bouts)
                if expected_pairings is None
                else len(decided) == expected_pairings)
    return PouleResult(standings=ordered, unresolved=unresolved,
                       complete=complete, unscored=list(unscored))


def qualifiers(result, places=2):
    """The top `places` of a poule, or fewer if a tie makes it unsafe.

    A tie straddling the qualifying line is not broken by picking one: the
    fighters are returned as far as the table is certain, and the caller is left
    to see the unresolved group. Advancing the wrong fighter is worse than
    advancing late.
    """
    safe = []
    for s in result.standings:
        if len(safe) >= places:
            break
        if any(s.name in group for group in result.unresolved):
            break
        safe.append(s.name)
    return safe


def draw(entries, target=4):
    """Split one weight class into poules, keeping compatriots apart.

    `entries` are dicts with at least "name" and "country". Countries are dealt
    round-robin across the poules, largest contingent first, which is what keeps
    a nation's fighters from meeting each other before the knockout. Poules come
    back sized as evenly as the entry allows.

    This is a sound draw, not a transcription of a federation procedure - no
    published seeding rules were available to check it against, so it is offered
    as a default to override, not as the official method.
    """
    if not entries:
        return []
    count = max(1, round(len(entries) / target))
    while len(entries) / count > target + 1:
        count += 1
    poules = [[] for _ in range(count)]

    by_country = {}
    for e in entries:
        by_country.setdefault(e.get("country", ""), []).append(e)
    # Largest contingent first, so the nation hardest to separate is dealt while
    # every poule is still empty.
    for _, members in sorted(by_country.items(), key=lambda kv: -len(kv[1])):
        for e in members:
            poules.sort(key=len)
            poules[0].append(e)
    return [sorted(p, key=lambda e: e["name"]) for p in poules if p]


def bracket(qualified):
    """Knockout pairings from poule qualifiers.

    `qualified` is a list of per-poule lists, each already in finishing order.
    Winners are drawn against runners-up from a different poule, and a field
    that is not a power of two gives byes to the best-placed fighters, which is
    the conventional shape. Returns rounds as lists of (a, b) pairs; `b` is None
    for a bye.
    """
    firsts = [p[0] for p in qualified if len(p) > 0]
    seconds = [p[1] for p in qualified if len(p) > 1]
    field_ = firsts + seconds
    if len(field_) < 2:
        return []

    size = 1
    while size < len(field_):
        size *= 2
    byes = size - len(field_)

    # Pair each winner with a runner-up from another poule where possible.
    pairs, pool = [], list(seconds)
    for i, a in enumerate(firsts):
        if i < byes:
            pairs.append((a, None))
            continue
        opponent = next((x for x in pool if _poule_of(x, qualified)
                         != _poule_of(a, qualified)), None)
        opponent = opponent if opponent is not None else (pool[0] if pool else None)
        if opponent is not None:
            pool.remove(opponent)
        pairs.append((a, opponent))
    while len(pool) > 1:
        pairs.append((pool.pop(0), pool.pop(0)))
    if pool:
        pairs.append((pool.pop(), None))
    return [pairs]


def _poule_of(name, qualified):
    for i, p in enumerate(qualified):
        if name in p:
            return i
    return -1


def check(bouts, entries=None):
    """Integrity complaints about a competition, as a list of strings.

    These are the failures actually seen in the 2026 world championship: a
    fighter who appeared in a bout but on no scoresheet, which corrupted a
    qualification; bouts left without a result; and poules whose table cannot be
    ranked. Each is cheap to detect and expensive to discover afterwards.
    """
    problems = []
    named = {e["name"] for e in entries} if entries else None
    seen = set()
    for b in bouts:
        for corner in ("red", "blue"):
            seen.add(b[corner])
            if named is not None and b[corner] not in named:
                problems.append(f"{b[corner]!r} fights in {b.get('bout_id') or 'a bout'} "
                                f"but is not in the entry list")
    if named:
        for name in sorted(named - seen):
            problems.append(f"{name!r} is entered but has no bout")

    for b in bouts:
        if not b.get("winner_corner"):
            problems.append(f"{b.get('bout_id') or 'bout'} "
                            f"({b['red']} vs {b['blue']}) has no result")
        # The bout that broke Men -75 kg B was a poule bout belonging to no
        # poule: it could not reach a scoresheet, so it could not be scored,
        # so the class it belonged to was ranked without it.
        if b.get("phase") == "poule" and not b.get("poule"):
            problems.append(f"{b.get('bout_id') or 'bout'} "
                            f"({b['red']} vs {b['blue']}) is a poule bout but "
                            f"belongs to no poule")

    # A poule is identified by its weight class AND its letter. Grouping on the
    # letter alone silently merges poule A of every class into one table, which
    # then "cannot be ranked" - a wrong answer that looks like a finding.
    by_poule = {}
    for b in bouts:
        if b.get("poule"):
            key = (b.get("tournament", ""), b.get("category", ""), b["poule"])
            by_poule.setdefault(key, []).append(b)
    for (_, category, name), group in sorted(by_poule.items()):
        result = standings(group)
        for tied in result.unresolved:
            where = f"{category} poule {name}" if category else f"poule {name}"
            problems.append(f"{where}: {' / '.join(tied)} cannot be separated "
                            f"on points, warnings or head-to-head - a further "
                            f"criterion (weight) is needed")
    return problems
