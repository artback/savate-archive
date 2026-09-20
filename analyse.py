#!/usr/bin/env python3
"""Ask the savate database questions.

    python3 analyse.py                          # what is loaded, and what it supports
    python3 analyse.py fighter "Artback"        # one fighter's career, bout by bout
    python3 analyse.py head-to-head "Pavicic"   # everyone they have met
    python3 analyse.py form                     # time of day, rest, bout of the day
    python3 analyse.py honours "Dahie"          # medals across every year loaded
    python3 analyse.py champions
    python3 analyse.py names                    # spellings merged, and pairs to rule on
    python3 analyse.py sql "SELECT ..."         # anything else

Names are matched loosely and without accents, so "Pavicic" finds "Pavičić", and
a search finds a fighter under any spelling a source has used for them.

A word on reading the numbers. Every bout has one winner and one loser, so a win
rate over any large slice of the database is 50% by construction - what moves is
warnings, disqualifications and margins, not who won. And a championship gives a
fighter three to five bouts, so a single fighter's split by time of day is noise
until many more events are loaded. Sample sizes are printed for that reason.
"""

import argparse
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DB = "savate.db"


def fold(text):
    text = unicodedata.normalize("NFKD", " ".join(str(text or "").split()))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def connect(path):
    if not Path(path).exists():
        raise SystemExit(f"{path} not found - run build_db.py first")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.create_function("fold", 1, fold)
    return db


def table(rows, title=None):
    if title:
        print(f"\n{title}")
    rows = [dict(r) for r in rows]
    if not rows:
        print("  (nothing)")
        return
    cols = list(rows[0])
    width = {c: max(len(str(c)), max(len(str(r[c])) for r in rows)) for c in cols}
    print("  " + "  ".join(f"{c:<{width[c]}}" for c in cols))
    print("  " + "  ".join("-" * width[c] for c in cols))
    for r in rows:
        print("  " + "  ".join(f"{'' if r[c] is None else r[c]!s:<{width[c]}}"
                               for c in cols))


def resolve(db, name):
    """Every fighter matching a loose name, most active first.

    Searches the aliases, not just the display name: a fighter written one way
    by one federation and another way by the next must be findable under both.
    """
    rows = db.execute("""
        SELECT r.fighter_id, r.fighter, r.bouts FROM fighter_record r
        WHERE fold(r.fighter) LIKE '%' || fold(?) || '%'
           OR r.fighter_id IN (SELECT fighter_id FROM fighter_aliases
                               WHERE fold(alias) LIKE '%' || fold(?) || '%')
        ORDER BY r.bouts DESC, r.fighter
    """, (name, name)).fetchall()
    return [(r["fighter_id"], r["fighter"]) for r in rows]


def overview(db):
    table(db.execute("SELECT slug, name, year, level, discipline FROM tournaments"),
          "Tournaments loaded")
    table(db.execute(
        "SELECT t.year, COUNT(DISTINCT t.slug) events, "
        "SUM(t.slug IN (SELECT tournament FROM bouts)) with_bouts, "
        "(SELECT COUNT(*) FROM bouts b WHERE b.tournament IN "
        "  (SELECT slug FROM tournaments x WHERE x.year = t.year)) bouts, "
        "(SELECT COUNT(*) FROM placings p WHERE p.tournament IN "
        "  (SELECT slug FROM tournaments x WHERE x.year = t.year)) placings "
        "FROM tournaments t GROUP BY t.year ORDER BY t.year DESC"),
        "By year (bouts where they were published, placings where they were not)")
    counts = db.execute(
        "SELECT COUNT(*) AS bouts, COUNT(DISTINCT fighter) AS fighters "
        "FROM appearances").fetchone()
    print(f"\n  {counts['bouts'] // 2} bouts, {counts['fighters']} fighters")
    table(db.execute(
        "SELECT fighter, country, bouts, wins, win_pct, tournaments "
        "FROM fighter_record WHERE tournaments > 1 ORDER BY bouts DESC LIMIT 10"),
        "Fighters appearing in more than one tournament (career data starts here)")


def fighter(db, name):
    matches = resolve(db, name)
    if not matches:
        raise SystemExit(f"no fighter matching {name!r}")
    if len(matches) > 1:
        print(f"{len(matches)} fighters match {name!r}: "
              f"{', '.join(n for _, n in matches[:8])}")
    who, shown = matches[0]
    table(db.execute("SELECT * FROM fighter_record WHERE fighter_id = ?", (who,)),
          f"{shown}")
    aliases = db.execute("SELECT alias FROM fighter_aliases WHERE fighter_id = ?",
                         (who,)).fetchall()
    if len(aliases) > 1:
        print(f"  also written as: {', '.join(a['alias'] for a in aliases)}")
    table(db.execute(
        "SELECT tournament, date, time, part_of_day, phase, poule, opponent, "
        "opponent_country, points_for, points_against, warnings, decision, "
        "outcome, minutes_rested FROM fighter_bouts WHERE fighter_id = ? "
        "ORDER BY tournament, date, time, bout_id", (who,)), "Every bout")


def head_to_head(db, name):
    matches = resolve(db, name)
    if not matches:
        raise SystemExit(f"no fighter matching {name!r}")
    who, shown = matches[0]
    table(db.execute(
        "SELECT opponent, meetings, wins, meetings - wins AS losses, tournaments "
        "FROM head_to_head WHERE fighter_id = ? ORDER BY meetings DESC, opponent",
        (who,)), f"{shown} has met")


def form(db):
    table(db.execute("SELECT * FROM form_by_part_of_day ORDER BY bouts DESC"),
          "By time of day (win rate is omitted: it is 50% by construction)")
    table(db.execute("SELECT * FROM form_by_bout_of_day ORDER BY bout_of_day"),
          "By how many bouts the fighter had already had that day")
    table(db.execute("SELECT * FROM form_by_rest ORDER BY appearances DESC"),
          "By rest since their previous bout")
    table(db.execute(
        "SELECT fighter, country, part_of_day, bouts, wins, win_pct "
        "FROM fighter_by_part_of_day WHERE bouts >= 3 "
        "ORDER BY bouts DESC, win_pct DESC LIMIT 12"),
        "Per fighter, 3+ bouts in a slot (still too few to mean much)")


def names(db):
    """What identity resolution did, and what it is leaving to a human."""
    from savate import identity

    table(db.execute(
        "SELECT f.name, f.countries, f.appearances, "
        "GROUP_CONCAT(a.alias, ' | ') AS spellings FROM fighters f "
        "JOIN fighter_aliases a ON a.fighter_id = f.id "
        "GROUP BY f.id HAVING COUNT(a.alias) > 1 ORDER BY f.appearances DESC"),
        "Merged automatically (same name, different spelling)")

    # Every spelling the archive holds, not only the ones that fought a bout.
    # `raw_appearances` is built from bouts, and two thirds of this archive is
    # podium lists - reading candidates from it alone was blind to most of the
    # people in it.
    register = identity.Register(identity.load_overrides())
    for r in db.execute("""
            SELECT red AS fighter, red_country AS country, COUNT(*) n
              FROM bouts GROUP BY 1, 2
            UNION ALL
            SELECT blue, blue_country, COUNT(*) FROM bouts GROUP BY 1, 2
            UNION ALL
            SELECT fighter, country, COUNT(*) FROM placings GROUP BY 1, 2"""):
        register.add(r["fighter"], r["country"], r["n"])
    pairs = [c for c in identity.candidates(register) if c["same_country"]]
    likely = [c for c in pairs if c["confidence"] == "likely"]
    review = [c for c in pairs if c["confidence"] != "likely"]
    table([{"a": c["a"], "b": c["b"], "shared": " ".join(c["shared"]),
            "why": c["reason"]} for c in likely[:20]],
          "Possibly one person - confirm in fighters.json before they are merged")
    print(f"\n  {len(review)} further pairs share part of a name and are almost "
          f"certainly different people; see analyse.py sql or identity.candidates().")

    # The other way one person splits in two is a single character, which
    # sharing a whole word cannot see: Florijanić and Florjanić, Valentino and
    # Valention. Those are shown separately because they are the likelier real
    # splits, and because a reader can rule on them quickly.
    close = [c for c in identity.near_misses(register) if c["same_country"]]
    table([{"a": c["a"], "b": c["b"],
            "appearances": f"{c['a_appearances']} + {c['b_appearances']}",
            "country": ", ".join(c["countries"])} for c in close[:25]],
          "Nearly the same name, same country - one character apart")
    if len(close) > 25:
        print(f"\n  {len(close) - 25} more such pairs; "
              f"identity.near_misses() lists them all.")
    print("  To record a decision, create fighters.json:")
    print('    {"same": [["Spelling A", "Spelling B"]], "different": [["X", "X"]]}')


def honours(db, name):
    matches = resolve(db, name)
    if not matches:
        raise SystemExit(f"no fighter matching {name!r}")
    who, shown = matches[0]
    table(db.execute("SELECT * FROM fighter_medals WHERE fighter_id = ?", (who,)),
          f"{shown}")
    table(db.execute(
        "SELECT year, event, level, discipline, category, medal, country "
        "FROM podium WHERE fighter_id = ? ORDER BY year DESC, event", (who,)),
        "Every placing")


def champions(db):
    table(db.execute(
        "SELECT year, event, gender, weight_kg, fighter, country FROM podium "
        "WHERE medal = 'gold' ORDER BY year DESC, event, "
        "gender, CAST(weight_kg AS REAL) LIMIT 40"),
        "Most recent champions (podium records)")
    table(db.execute("SELECT * FROM medal_table ORDER BY medals DESC LIMIT 20"),
          "Nations by medal, across every year loaded")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="overview",
                    choices=["overview", "fighter", "head-to-head", "form",
                             "champions", "honours", "names", "sql"])
    ap.add_argument("argument", nargs="?")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    db = connect(args.db)
    if args.command in ("fighter", "head-to-head", "honours", "sql") \
            and not args.argument:
        raise SystemExit(f"{args.command} needs an argument")
    if args.command == "overview":
        overview(db)
    elif args.command == "fighter":
        fighter(db, args.argument)
    elif args.command == "head-to-head":
        head_to_head(db, args.argument)
    elif args.command == "form":
        form(db)
    elif args.command == "honours":
        honours(db, args.argument)
    elif args.command == "names":
        names(db)
    elif args.command == "champions":
        champions(db)
    elif args.command == "sql":
        table(db.execute(args.argument))


if __name__ == "__main__":
    main()
