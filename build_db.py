#!/usr/bin/env python3
"""Build the savate results database from every source in the manifest.

    python3 build_db.py                      # build from tournaments.json
    python3 build_db.py --inspect <source>   # what would a new table map to?

The manifest lists one entry per tournament: which adapter reads it, where it
lives, and what is true about the competition that its data does not say. Adding
next year's event is an entry, not a rewrite - and if it arrives as a Google
Sheet rather than a website, that is a different adapter behind the same entry.

Always --inspect an unfamiliar table first. It reads nothing into the database;
it prints which column it took for what, and which it ignored, so a mismatched
header is caught while it is still a printout.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import adapters, competition, display, identity, store
from savate.adapters import tabular
from savate.schema import Bout, Placing, check, check_placing

MANIFEST = Path("tournaments.json")

# Keys the runner consumes itself; anything else in an entry is passed to the
# adapter, so an adapter can take its own options without this file knowing.
ENTRY_KEYS = {"slug", "adapter", "source", "meta"}


def load(entry):
    """(Tournament, [Bout], Report) for one manifest entry."""
    try:
        adapter = adapters.get(entry.get("adapter"))
    except KeyError as e:
        raise SystemExit(f"{entry.get('slug')}: {e}")
    options = {k: v for k, v in entry.items() if k not in ENTRY_KEYS}
    return adapter.read(entry["source"], entry["slug"], entry.get("meta"),
                        **options)


NORMALISATION_LOG = Path("normalisation.csv")
ERASURE = Path("erasure.json")


def apply_erasure(bouts, placings, people, register, path):
    """Drop the rows a data subject asked to have erased.

    The request names the person as the site shows them; the register knows
    every spelling that person was written under, so all of their rows in the
    events the request scopes are dropped - from the bouts, the placings and
    the people table alike, because an erasure that leaves one corner of one
    bout behind is not an erasure. Each request is printed, because an erasure
    that cannot be shown to have happened is not one.

    The source documents in raw_sources/ are left untouched: they are the
    federations' publications, and the archive's job is to say where every
    remaining row came from. Whether a subject's request extends to those
    documents is a decision the runbook defers to counsel.
    """
    if not path.exists():
        return bouts, placings, people, 0, 0
    requests = json.loads(path.read_text(encoding="utf-8"))
    if not requests:
        return bouts, placings, people, 0, 0
    index = register.index()
    targets = {}
    for req in requests:
        name = str(req.get("fighter", "")).strip()
        person = next((f for f in people if name in f["aliases"]), None)
        if person is None:
            raise SystemExit(
                f"erasure: {name!r} is not in the register - name the person "
                f"by a spelling the site shows for them")
        scope = set(req.get("events") or [])
        targets[person["id"]] = scope
        where = "all events" if not scope else ", ".join(sorted(scope))
        print(f"erasure: {person['name']} ({where}) - "
              f"{req.get('reason', 'no reason recorded')}")

    def keep_bout(b):
        for side in (b.red, b.blue):
            scope = targets.get(index.get(side))
            if scope is not None and (not scope or b.tournament in scope):
                return False
        return True

    def keep_placing(p):
        scope = targets.get(index.get(p.fighter))
        return not (scope is not None
                    and (not scope or p.tournament in scope))

    kept_b = [b for b in bouts if keep_bout(b)]
    kept_p = [p for p in placings if keep_placing(p)]
    kept_people = [f for f in people
                   if not (f["id"] in targets and not targets[f["id"]])]
    dropped = (len(bouts) - len(kept_b), len(placings) - len(kept_p))
    if dropped != (0, 0):
        print(f"erasure: {dropped[0]} bout(s) and {dropped[1]} placing(s) "
              f"dropped from the build")
    return kept_b, kept_p, kept_people, *dropped


def normalise(bouts, placings, log=NORMALISATION_LOG):
    """Repair what the sources printed, before anything keys on it.

    This runs before the identity register and before deduplication, because
    both of those key on the name string. Left alone, "M EANEY ALEKSIS" - one
    fighter, damaged by a PDF text layer - registers as a separate competitor
    with the id "aleksis eaney m" and an empty career, and no amount of care
    further down the pipeline recovers him. Repairing at the door is the only
    place the repair reaches identity.

    Three things move. A damaged name becomes the name the source meant. A
    country spelled FRA, Fr, Francia or Frankreich becomes France, so a medal
    table counts one nation rather than four. A club or federation printed
    inside the name cell moves into its own field instead of being thrown away
    with the rest of the annotation.

    Every substitution is written to `normalisation.csv`. The archive's ground
    truth is the documents in raw/ and raw_sources/, which are never touched,
    and this file is the diff between what they print and what the database
    holds - so a reader who doubts a name can see exactly what was done to it.
    Rows whose name repairs to nothing are dropped and counted, never guessed.
    """
    names = set()
    for b in bouts:
        names.update((b.red, b.blue, b.winner, b.loser))
    for p in placings:
        names.add(p.fighter)
    names.discard("")

    once = {n: display.name(n) for n in names}
    clean_once = [d.text for d in once.values() if d.usable]
    vocabulary = display.vocabulary(clean_once)
    # Accented spellings as the corpus actually prints them, so a repair can
    # put back the ć a text layer dropped rather than a flattened c.
    forms = display.wordforms(clean_once)
    repaired = {n: display.name(n, vocabulary, forms) for n in names}

    # Clubs come off the same pages and carry the same kerning damage, so they
    # get the same two-pass treatment against their own vocabulary: "SK Om ega
    # Vž" and "SK Omega Vž" are one club, and left alone they are two.
    raw_clubs = set()
    for b in bouts:
        raw_clubs.update((b.red_club, b.blue_club))
    for p in placings:
        raw_clubs.add(p.club)
    raw_clubs.discard("")
    club_words = display.vocabulary(display.club(c) for c in raw_clubs)
    clubs = {c: display.club(c, club_words) for c in raw_clubs}

    def fix_club(raw, row_id, field):
        fixed = clubs.get(raw, raw)
        if raw and fixed != raw:
            changes.append((row_id, field, raw, fixed, "repaired"))
        return fixed

    changes = []

    def fix_name(raw, row_id, field):
        """(name, club, country, weighed) - or None where it is not a name."""
        d = repaired.get(raw)
        if d is None:
            return raw, "", ""
        if not d.usable:
            changes.append((row_id, field, raw, "", f"dropped: {d.reason}"))
            return None
        if d.text != raw:
            changes.append((row_id, field, raw, d.text, "repaired"))
        return d.text, d.club, d.country, d.weight

    def fix_country(raw, row_id, field):
        resolved = display.country(raw)
        if resolved.known and resolved.name != raw:
            changes.append((row_id, field, raw, resolved.name, "resolved"))
            return resolved.name
        if raw and not resolved.known:
            changes.append((row_id, field, raw, raw, "unresolved: kept verbatim"))
        return raw

    kept_bouts, dropped_bouts = [], 0
    for b in bouts:
        red = fix_name(b.red, b.bout_id, "red")
        blue = fix_name(b.blue, b.bout_id, "blue")
        if red is None or blue is None:
            dropped_bouts += 1
            continue
        b.red, red_club, red_country, red_weighed = red
        b.blue, blue_club, blue_country, blue_weighed = blue
        # A country the name cell carried is used only where the row has none
        # of its own; a country column the source filled always wins.
        b.red_country = fix_country(b.red_country or red_country, b.bout_id,
                                    "red_country")
        b.blue_country = fix_country(b.blue_country or blue_country, b.bout_id,
                                     "blue_country")
        # winner and loser name the same people as red and blue, so they have
        # to move with them. Repairing one and not the other leaves a bout
        # whose winner is nobody in it, and every view that reads the winner
        # then quietly drops the result.
        for field in ("winner", "loser"):
            who = getattr(b, field)
            if not who:
                continue
            d = repaired.get(who)
            if d is not None and d.usable and d.text != who:
                changes.append((b.bout_id, field, who, d.text, "repaired"))
                setattr(b, field, d.text)
        b.red_club = fix_club(b.red_club or red_club, b.bout_id, "red_club")
        b.blue_club = fix_club(b.blue_club or blue_club, b.bout_id, "blue_club")
        b.red_weighed = b.red_weighed or red_weighed
        b.blue_weighed = b.blue_weighed or blue_weighed
        kept_bouts.append(b)

    kept_placings, dropped_placings = [], 0
    for p in placings:
        fighter = fix_name(p.fighter, p.placing_id, "fighter")
        if fighter is None:
            dropped_placings += 1
            continue
        p.fighter, club, country, weighed = fighter
        p.country = fix_country(p.country or country, p.placing_id, "country")
        p.club = fix_club(p.club or club, p.placing_id, "club")
        p.weighed = p.weighed or weighed
        kept_placings.append(p)

    if changes:
        import csv as _csv
        with open(log, "w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh)
            writer.writerow(["row", "field", "printed", "stored", "action"])
            writer.writerows(changes)

    counted = {}
    for _, _, _, _, action in changes:
        head = action.split(":")[0]
        counted[head] = counted.get(head, 0) + 1
    notes = []
    if counted:
        notes.append("normalisation: " + ", ".join(
            f"{n} {name}" for name, n in sorted(counted.items())))
    if dropped_bouts or dropped_placings:
        notes.append(f"    dropped {dropped_bouts} bout(s) and "
                     f"{dropped_placings} placing(s) whose name was not a name")
    if changes:
        notes.append(f"    every substitution listed in {log}")
    return kept_bouts, kept_placings, notes


def deduplicate(bouts, placings, tournaments, who):
    """Drop rows that record the same fact twice, and say how many.

    Two quite different things produce them. A document can print the same
    weight class more than once - the 2025 European sheets print all sixteen
    three times, once per language - and a championship can be published as two
    documents whose contents overlap, as the 2011 world combat results were
    under "Senior Men" and "Seniors Men". The first is a repeat inside one
    event; the second is one event arriving as two.

    Both are caught on content rather than on names, because names are exactly
    what differs between them. Doing it here rather than in each adapter is what
    makes the pipeline idempotent: reading a source twice cannot change the
    archive, whichever adapter read it.
    """
    meta = {t.slug: t for t in tournaments}

    def where(slug):
        t = meta.get(slug)
        # The day, not the discipline, tells two meetings apart: the same pair
        # does fight twice in a season (Rousies on the 1st, Ruy-Montceau a
        # fortnight later), and only the date says they are not one bout.
        return (t.year, t.level, t.start_date) if t else (slug, "", "")

    kept, dropped_in, dropped_across = [], 0, 0
    inside, across = set(), set()
    for b in bouts:
        pair = frozenset((who.get(b.red, b.red), who.get(b.blue, b.blue)))
        here = (b.tournament, b.category, b.phase, b.poule, pair)
        if here in inside:
            dropped_in += 1
            continue
        # The same two fighters, in the same category and round, in one year at
        # one level on one day, is one bout however many documents printed it.
        # The day is part of the key, not a precondition: events that state no
        # date still collide on the empty string, so a championship published
        # twice is caught exactly as a reprinted one is.
        there = where(b.tournament) + (b.category, b.phase, b.poule, pair)
        if there in across:
            dropped_across += 1
            continue
        inside.add(here)
        across.add(there)
        kept.append(b)

    kept_p, dropped_pin = [], 0
    inside = set()
    for p in placings:
        person = who.get(p.fighter, p.fighter)
        here = (p.tournament, p.category, p.rank, person)
        if here in inside:
            dropped_pin += 1
            continue
        inside.add(here)
        kept_p.append(p)

    # One championship published as two documents. Their names are exactly what
    # differs - "Senior Men" and "Seniors Men", "Chungju Masterships" and "Asian
    # Championships" for the same tournament inside it - so the overlap in what
    # they record is the evidence, and a shared year is the only name-like thing
    # trusted. Below the threshold they are left alone and stay two events: a
    # duplicated podium is visible and fixable, a wrongly merged one is neither.
    OVERLAP = 0.6
    facts, order = {}, {}
    for p in kept_p:
        facts.setdefault(p.tournament, set()).add(
            (who.get(p.fighter, p.fighter), p.rank))
    for t in tournaments:
        order[t.slug] = t.year
    twins, slugs = {}, [s for s in facts if len(facts[s]) >= 3]
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if order.get(a) != order.get(b) or not order.get(a):
                continue
            ta, tb = meta.get(a), meta.get(b)
            if ta and tb:
                if ta.age_class and tb.age_class and ta.age_class != tb.age_class:
                    continue
                if ta.level and tb.level and ta.level != tb.level:
                    continue
            shared = facts[a] & facts[b]
            if not shared:
                continue
            if len(shared) / min(len(facts[a]), len(facts[b])) >= OVERLAP:
                keep, drop = (a, b) if len(facts[a]) >= len(facts[b]) else (b, a)
                twins.setdefault(drop, keep)
    dropped_pacross = 0
    if twins:
        survivors = []
        for p in kept_p:
            keep = twins.get(p.tournament)
            if keep and (who.get(p.fighter, p.fighter), p.rank) in facts[keep]:
                dropped_pacross += 1
                continue
            survivors.append(p)
        kept_p = survivors

    notes = []
    if dropped_in or dropped_across:
        notes.append(f"combats: {dropped_in} reprinted within an event, "
                     f"{dropped_across} the same event published twice")
    if dropped_pin or dropped_pacross:
        notes.append(f"places: {dropped_pin} reprinted within an event, "
                     f"{dropped_pacross} the same event published twice")
    for drop, keep in sorted(twins.items()):
        notes.append(f"    {drop} duplicates {keep}")
    return kept, kept_p, notes


def split_by_age_class(tournaments, bouts, placings):
    """(tournaments, notes): one event per age class a multi-championship
    document states.

    One document often publishes several championships - the junior title and
    the senior title of one meeting - and a row says which of them it belongs
    to only through the age class it states. Left in one event, that event
    would hand out a junior champion and a senior champion at once, a title no
    federation awards, so the event splits on what its rows state: each
    distinct age class becomes one event named "<age class> <name>", and the
    rows carry it to that event. Rows that state no age class stay where they
    were, because nothing in the source assigns them elsewhere.
    """
    import re
    from dataclasses import replace

    classes = {}
    for b in bouts:
        if b.age_class:
            classes.setdefault(b.tournament, set()).add(b.age_class)
    for p in placings:
        if p.age_class:
            classes.setdefault(p.tournament, set()).add(p.age_class)

    used = {t.slug for t in tournaments}
    out, notes = [], []
    for t in tournaments:
        acs = sorted(classes.get(t.slug, ()))
        if len(acs) < 2:
            out.append(t)
            continue
        unclassed = any(b.tournament == t.slug and not b.age_class for b in bouts) \
            or any(p.tournament == t.slug and not p.age_class for p in placings)
        remap = {}
        for ac in acs:
            base = re.sub(r"[^a-z0-9]+", "-", ac.lower()).strip("-")
            slug = f"{t.slug}-{base}"
            n = 2
            while slug in used:
                slug = f"{t.slug}-{base}-{n}"
                n += 1
            used.add(slug)
            remap[ac] = slug
            out.append(replace(t, slug=slug,
                               name=f"{ac} {t.name}".strip(), age_class=ac))
        if unclassed:
            out.append(t)
        for b in bouts:
            if b.tournament == t.slug and b.age_class in remap:
                b.tournament = remap[b.age_class]
        for p in placings:
            if p.tournament == t.slug and p.age_class in remap:
                p.tournament = remap[p.age_class]
        kept = " (the event itself keeps its rows with no stated age class)" \
            if unclassed else ""
        notes.append(f"split: {t.slug} -> {len(acs)} events by age class "
                     f"({', '.join(acs)}){kept}")
    return out, notes


def inspect(source, mapping=None):
    rows, headers = tabular.read_rows(source)
    columns = tabular.guess_columns(headers)
    columns.update({k: v for k, v in (mapping or {}).items() if v})
    print(f"{source}: {len(rows)} row(s), {len(headers)} column(s)\n")
    width = max((len(f) for f in columns), default=12)
    for field in sorted(columns):
        print(f"  {field:<{width}} <- {columns[field]!r}")
    unused = [h for h in headers if h not in set(columns.values())]
    if unused:
        print(f"\n  ignored: {', '.join(repr(h) for h in unused)}")
    missing = [f for f in ("date", "red", "blue") if f not in columns]
    if missing:
        print(f"\n  NOT FOUND: {', '.join(missing)} - set these in the entry's "
              f'"mapping", or no row will be read.')
    if rows:
        print("\n  first row as mapped:")
        for field in sorted(columns):
            print(f"    {field:<{width}} = {rows[0].get(columns[field], '')!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=MANIFEST, type=Path)
    ap.add_argument("--inspect", metavar="SOURCE",
                    help="print the column mapping for a table and exit")
    ap.add_argument("--adapters", action="store_true",
                    help="list the available adapters and exit")
    ap.add_argument("--csv", default="savate.csv")
    ap.add_argument("--json", dest="json_out", default="savate.json")
    ap.add_argument("--db", default="savate.db")
    args = ap.parse_args()

    if args.adapters:
        for name, description in adapters.catalogue():
            print(f"  {name:16s} {description}")
        return

    if args.inspect:
        inspect(args.inspect)
        return

    if not args.manifest.exists():
        raise SystemExit(f"{args.manifest} not found - it lists the tournaments "
                         f"to build from. See the module docstring.")
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))

    tournaments, bouts, placings, complaints = [], [], [], []
    for entry in entries:
        tournament, rows, report = load(entry)
        tournaments.append(tournament)
        # An adapter returns whichever facts its document holds. A podium
        # yields placings and no bouts; most sources yield the opposite; the
        # runner does not need to know which in advance.
        mine = [r for r in rows if isinstance(r, Bout)]
        theirs = [r for r in rows if isinstance(r, Placing)]
        bouts.extend(mine)
        placings.extend(theirs)
        decided = sum(1 for b in mine if b.status == "decided")
        summary = (f"{len(mine)} bouts, {decided} decided" if mine
                   else f"{len(theirs)} placings")
        print(f"{tournament.slug}: {summary} ({entry['adapter']})")
        for problem in (report.problems if report else [])[:5]:
            print(f"    ! {problem}")
        if report and len(report.problems) > 5:
            print(f"    ! ... and {len(report.problems) - 5} more")
        for b in mine:
            complaints.extend(f"{b.bout_id}: {c}" for c in check(b))
        for p in theirs:
            complaints.extend(f"{p.placing_id}: {c}" for c in check_placing(p))

    # A title states its own competition: "African Savate Championships" is
    # african and a championship, in so many words. Reading that is not
    # inventing it, and a manifest entry that declares either always wins.
    conflicts = []
    for t in tournaments:
        read = competition.classify(t.name, t.source,
                                    {"level": t.level, "format": t.format,
                                     "discipline": t.discipline,
                                     "age_class": t.age_class})
        t.name = read["name"]
        t.level, t.format = read["level"], read["format"]
        t.discipline, t.age_class = read["discipline"], read["age_class"]
        conflicts.extend(f"    {t.slug}: {n}" for n in read["notes"])
    if conflicts:
        print(f"{len(conflicts)} title(s) read or in conflict with the manifest:")
        for line in conflicts:
            print(line)

    # Several championships in one document split on what their rows state:
    # the junior title and the senior title are two events, not one event with
    # two champions.
    tournaments, split_notes = split_by_age_class(tournaments, bouts, placings)
    for line in split_notes:
        print(line)

    bouts, placings, repairs = normalise(bouts, placings)
    for line in repairs:
        print(line)

    seen = set()
    for b in bouts:
        if b.bout_id in seen:
            complaints.append(f"{b.bout_id}: duplicate bout id")
        seen.add(b.bout_id)
    seen = set()
    for p in placings:
        if p.placing_id in seen:
            complaints.append(f"{p.placing_id}: duplicate placing id")
        seen.add(p.placing_id)

    if complaints:
        print(f"\n{len(complaints)} row(s) failed the schema check:")
        for c in complaints[:10]:
            print(f"  ! {c}")
        raise SystemExit("refusing to write a database that does not validate.")

    register = identity.Register(identity.load_overrides())
    for b in bouts:
        register.add(b.red, b.red_country)
        register.add(b.blue, b.blue_country)
    for p in placings:
        register.add(p.fighter, p.country)
    people = register.fighters()
    merged = [p for p in people if len(p["aliases"]) > 1]
    if register.slips:
        print(f"\n{len(register.slips)} spelling(s) merged as a transcription "
              f"slip of a much commoner name:")
        for common, rare in register.slips[:8]:
            print(f"    {common}  <-  {rare}")
        if len(register.slips) > 8:
            print(f"    ... and {len(register.slips) - 8} more")
    if register.convention:
        print(f"\n{len(register.convention)} pair(s) merged as one name under "
              f"different spelling conventions:")
        for a, b in register.convention[:8]:
            print(f"    {a}  =  {b}")
        if len(register.convention) > 8:
            print(f"    ... and {len(register.convention) - 8} more")

    bouts, placings, people, _, _ = apply_erasure(
        bouts, placings, people, register, ERASURE)

    bouts, placings, collapsed = deduplicate(bouts, placings, tournaments,
                                             register.index())
    for line in collapsed:
        print(line)

    store.write_csv(args.csv, bouts)
    store.write_placings_csv("placings.csv", placings)
    store.write_json(args.json_out, tournaments, bouts)
    store.write_db(args.db, tournaments, bouts, people, placings)
    print(f"\n{len(bouts)} bouts and {len(placings)} placings from "
          f"{len(tournaments)} tournament(s) -> {args.csv}, {args.json_out}, "
          f"{args.db}")
    print(f"{len(people)} fighters, {len(merged)} written under more than one "
          f"spelling")
    for person in merged[:5]:
        print(f"    {person['name']}  <-  {', '.join(person['aliases'])}")


if __name__ == "__main__":
    main()
