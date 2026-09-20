#!/usr/bin/env python3
"""Run every adapter against every candidate document, and judge the result.

A document "parses" only if the rows it yields are believable. That distinction
matters: the 2024 European championships produced 56 bouts through an adapter
that had mis-segmented the whole file, filing men's bouts under Junior Women
-56 kg and pairing one fighter against himself. Rows appeared; none of them were
true. An adapter that fails loudly costs an afternoon, and one that fails
quietly costs the archive its credibility.

So each attempt is scored against the things a real results document cannot do:

  * nobody fights themselves
  * no two bouts share an id
  * a weight class does not hold both genders
  * a fighter does not appear in two weight classes of one championship
  * points, where published, are scores the rulebook allows

Anything that trips one of those is reported as unusable, whatever it produced.
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import adapters
from savate.schema import Bout, Placing

# The scorelines savate's own rules permit; see savate/rules.py.
LEGAL_POINTS = {"0", "1", "3", "-1", ""}


def judge(rows, report):
    """(usable, [complaints], stats) for one adapter's output."""
    bouts = [r for r in rows if isinstance(r, Bout)]
    placings = [r for r in rows if isinstance(r, Placing)]
    complaints = []

    if not bouts and not placings:
        return False, ["no rows"], {}

    ids = collections.Counter(b.bout_id for b in bouts)
    dupes = sum(1 for v in ids.values() if v > 1)
    if dupes:
        complaints.append(f"{dupes} duplicate bout id(s)")

    selfies = [b for b in bouts if b.red and b.red == b.blue]
    if selfies:
        complaints.append(f"{len(selfies)} bout(s) pairing a fighter with themself")

    # A category that holds both genders means the file was mis-segmented.
    by_cat = collections.defaultdict(set)
    for b in bouts:
        if b.gender:
            by_cat[b.category].add(b.gender)
    mixed = [c for c, g in by_cat.items() if len(g) > 1]
    if mixed:
        complaints.append(f"{len(mixed)} category holding both genders")

    # One person, two weight classes, one championship: also mis-segmentation.
    seen = collections.defaultdict(set)
    for b in bouts:
        for who in (b.red, b.blue):
            if who:
                seen[who].add(b.category)
    spread = [n for n, cats in seen.items() if len(cats) > 1]
    if len(spread) > max(2, len(seen) // 20):
        complaints.append(f"{len(spread)} fighter(s) in more than one weight class")

    odd = [b for b in bouts
           if b.red_points not in LEGAL_POINTS or b.blue_points not in LEGAL_POINTS]
    if odd:
        complaints.append(f"{len(odd)} bout(s) with a scoreline the rules do not allow")

    # Placings need the same suspicion as bouts. Three documents passed an
    # earlier version of this check while yielding empty names, fixture text
    # where a name belongs ("P1 A-B MAURO Charlotte AUBRY"), and forty medals
    # filed under one invented category - one of them naming canne de combat,
    # which is a different sport.
    if placings:
        blank = [p for p in placings if not (p.fighter or "").strip()]
        if blank:
            complaints.append(f"{len(blank)} placing(s) with no name")
        fixture = [p for p in placings
                   if re.search(r"\bP\d\b|\b[A-Z]-[A-Z]\b|\bpoule\b", p.fighter or "", re.I)]
        if fixture:
            complaints.append(f"{len(fixture)} placing(s) whose name is fixture text")
        digits = [p for p in placings
                  if (p.country or "").strip() and any(c.isdigit() for c in p.country)]
        if digits:
            complaints.append(f"{len(digits)} placing(s) with digits in the country")
        cats = {p.category for p in placings}
        if len(placings) >= 12 and len(cats) == 1:
            complaints.append("every placing filed under one category")
        other_sport = [c for c in cats if re.search(r"canne|b[aâ]ton|chausson", c or "", re.I)]
        if other_sport:
            complaints.append(f"category names another sport: {other_sport[0]!r}")

    stats = {
        "bouts": len(bouts), "placings": len(placings),
        "categories": len(by_cat) or len({p.category for p in placings}),
        "decided": sum(1 for b in bouts if b.winner_corner),
        "problems": len(report.problems) if report else 0,
    }
    return not complaints, complaints, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--out", type=Path, default=Path("probe_results.json"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    entries = json.loads(args.candidates.read_text(encoding="utf-8"))
    if args.limit:
        entries = entries[: args.limit]

    names = [name for name, _ in adapters.catalogue()]
    results = []
    for i, c in enumerate(entries, 1):
        url = c.get("url", "")
        best = None
        for name in names:
            try:
                adapter = adapters.get(name)
                _t, rows, report = adapter.read(url, f"probe-{i}", {
                    "name": c.get("title", ""), "year": c.get("year", ""),
                })
            except Exception as e:
                continue
            usable, complaints, stats = judge(rows, report)
            score = (stats.get("bouts", 0) * 2 + stats.get("placings", 0)) if usable else 0
            if score and (best is None or score > best["score"]):
                best = {"adapter": name, "score": score, "stats": stats,
                        "complaints": complaints}
        row = dict(c)
        row["probe"] = best
        results.append(row)
        mark = f"{best['adapter']} {best['stats']}" if best else "-"
        print(f"  [{i:3}/{len(entries)}] {c.get('year',''):6} {mark}"
              f"  {c.get('title','')[:46]}", flush=True)

    args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    ok = [r for r in results if r["probe"]]
    print(f"\n{len(ok)}/{len(results)} documents parse into believable rows")
    print(f"  bouts available:   {sum(r['probe']['stats']['bouts'] for r in ok)}")
    print(f"  placings available:{sum(r['probe']['stats']['placings'] for r in ok)}")
    by = collections.Counter(r["probe"]["adapter"] for r in ok)
    for name, n in by.most_common():
        print(f"  {n:4} via {name}")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
