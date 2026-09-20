#!/usr/bin/env python3
"""Find results documents on a federation's site, living or dead, and test them.

    python3 discover.py ffsavate.com                  # what is out there
    python3 discover.py ffsavate.com --probe          # ...and what parses
    python3 discover.py ffsavate.com --probe --add    # ...and keep the ones that do

Federations reorganise their sites and drop the old results with them, so for
anything older than a season or two the Wayback Machine is not a fallback - it
is the source. This asks its index for every document a domain ever served,
keeps the ones whose names suggest competition results, and - with --probe -
runs each installed adapter against them to find out what they actually are.

Probing rather than guessing is the whole point. A title says nothing reliable
about a document's layout: "pool results" has meant three different generators
in one federation's archive, and half the links are called "Download". The only
way to know what a document holds is to open it, and the adapters already know
how to fail politely on one they do not understand.
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import adapters, sources

# Document names that suggest a competition record, in the languages the
# federations publish in. Generous on purpose: --probe is what decides.
LIKELY = re.compile(
    r"resultat|résultat|result|palmar|classement|championnat|championship|"
    r"medail|medal|poule|pool|tableau|bracket|coupe|cup|open|finale|final|"
    r"tournoi|tournament|champ", re.I)
# Names that are reliably not results.
UNLIKELY = re.compile(
    r"reglement|règlement|rules|statut|licence|affiche|poster|inscription|"
    r"entry|entries|bulletin|convocation|calendrier|calendar|facture|"
    r"formulaire|form|dossier-?medical|assurance|proces-?verbal|"
    r"compte-?rendu|newsletter|organigramme|annuaire", re.I)


def candidates(domain, since=None, limit=20000):
    """[{url, timestamp, name}] - documents on a domain that may hold results."""
    found = sources.snapshots(domain, domain=True, mimetype="application/pdf",
                              limit=limit, since=since)
    out = []
    for snap in found:
        name = snap["url"].rsplit("/", 1)[-1]
        if UNLIKELY.search(name) or not LIKELY.search(name):
            continue
        out.append({"url": snap["url"], "timestamp": snap["timestamp"],
                    "name": name})
    # One document can be captured many times; the newest capture will do.
    newest = {}
    for c in sorted(out, key=lambda c: c["timestamp"]):
        newest[c["url"]] = c
    return sorted(newest.values(), key=lambda c: c["url"])


def probe(candidate, only=None):
    """Which adapter reads this document, and how much it gets out of it.

    The document is fetched once and the adapters are handed the local file.
    Letting each adapter fetch for itself means the same PDF is pulled once per
    adapter, and each pull first tries a live URL that has usually been dead for
    a decade - which turned a probe of ninety documents into an afternoon.
    """
    try:
        path = sources.fetch(sources.WAYBACK.format(
            timestamp=candidate["timestamp"], url=candidate["url"]))
    except Exception:
        return {"adapter": "", "rows": 0, "problems": 0, "error": "unfetchable"}

    best = None
    for name in (only or adapters.names()):
        adapter = adapters.get(name)
        try:
            _, rows, report = adapter.read(path, "probe",
                                           {"year": candidate["timestamp"][:4]})
        except Exception:                            # not a document it knows
            continue
        if rows and (best is None or len(rows) > best["rows"]):
            best = {"adapter": name, "rows": len(rows),
                    "problems": len(report.problems), "path": str(path)}
    return best or {"adapter": "", "rows": 0, "problems": 0}


def year_of(name, timestamp):
    """The competition's year, from the document's name if it says so."""
    years = re.findall(r"(?:19|20)\d{2}", name)
    return years[-1] if years else timestamp[:4]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("domain", help="e.g. ffsavate.com")
    ap.add_argument("--since", help="earliest capture year, e.g. 2000")
    ap.add_argument("--probe", action="store_true", help="try to read each one")
    ap.add_argument("--adapter", nargs="*", help="only these adapters")
    ap.add_argument("--add", action="store_true", help="append what parsed")
    ap.add_argument("--manifest", default="tournaments.json", type=Path)
    ap.add_argument("--limit", type=int, default=400)
    args = ap.parse_args()

    found = candidates(args.domain, since=args.since)
    print(f"{args.domain}: {len(found)} document(s) that look like results")
    if not args.probe:
        for c in found[:args.limit]:
            print(f"  {c['timestamp'][:8]}  {c['name'][:88]}")
        print("\nRe-run with --probe to find out which of these can be read.")
        return

    results, parsed = [], 0
    for i, c in enumerate(found[:args.limit], 1):
        outcome = probe(c, args.adapter)
        results.append(dict(c, **outcome))
        parsed += bool(outcome["rows"])
        print(f"[{i}/{min(len(found), args.limit)}] {c['name'][:62]:62s} -> "
              f"{outcome['rows']:4d} rows {outcome['adapter']}", flush=True)

    print(f"\n{parsed}/{len(results)} readable, "
          f"{sum(r['rows'] for r in results)} rows")
    print("by adapter:", dict(collections.Counter(
        r["adapter"] for r in results if r["rows"])))
    if not args.add:
        return

    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) \
        if args.manifest.exists() else []
    have = {e["source"] for e in manifest}
    slugs = {e["slug"] for e in manifest}
    added = 0
    for r in results:
        if not r["rows"] or r["url"] in have:
            continue
        stem = re.sub(r"\.pdf$", "", r["name"], flags=re.I)
        base = re.sub(r"[^a-z0-9]+", "-",
                      f"{args.domain.split('.')[0]} {stem}".lower()).strip("-")[:56]
        slug, n = base, 2
        while slug in slugs:
            slug, n = f"{base}-{n}", n + 1
        slugs.add(slug)
        manifest.append({
            "slug": slug, "adapter": r["adapter"],
            "source": sources.WAYBACK.format(timestamp=r["timestamp"],
                                             url=r["url"]),
            "meta": {"name": stem.replace("-", " "),
                     "year": year_of(r["name"], r["timestamp"])},
        })
        added += 1
    args.manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"{added} entry(ies) appended to {args.manifest}")


if __name__ == "__main__":
    main()
