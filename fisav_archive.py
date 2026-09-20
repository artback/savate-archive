#!/usr/bin/env python3
"""List the FISav results archive, and turn it into manifest entries.

    python3 fisav_archive.py                     # everything, by year
    python3 fisav_archive.py --year 2025 2023
    python3 fisav_archive.py --bouts --add       # append the useful ones

Only "full results" documents carry bout-by-bout data; the rest are medallist
sheets. --bouts keeps those, and --add appends them to tournaments.json so the
next build reads them.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate.adapters import fisav_pdf


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", nargs="*", help="limit to these years")
    ap.add_argument("--bouts", action="store_true",
                    help="only documents that carry bout-by-bout results")
    ap.add_argument("--add", action="store_true",
                    help="append entries to the manifest")
    ap.add_argument("--manifest", default="tournaments.json", type=Path)
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = ap.parse_args()

    documents = fisav_pdf.index(years=args.year, refresh=args.refresh)
    kinds = collections.Counter(d["kind"] for d in documents)
    years = sorted({d["year"] for d in documents})
    print(f"{len(documents)} documents, {years[0]}-{years[-1]}: "
          + ", ".join(f"{v} {k}" for k, v in kinds.most_common()))

    wanted = [d for d in documents if d["kind"] == "bouts"] if args.bouts \
        else documents
    by_year = collections.defaultdict(list)
    for d in wanted:
        by_year[d["year"]].append(d)
    for year in sorted(by_year, reverse=True):
        print(f"\n{year}")
        for d in by_year[year]:
            print(f"  [{d['kind']:7s}] {d['title']}")

    if not args.add:
        return
    existing = json.loads(args.manifest.read_text(encoding="utf-8")) \
        if args.manifest.exists() else []
    seen = {e["source"] for e in existing}
    added = [fisav_pdf.manifest_entry(d) for d in wanted if d["url"] not in seen]
    # Two documents from one event would otherwise claim the same slug.
    slugs = {e["slug"] for e in existing}
    for entry in added:
        base, n = entry["slug"], 2
        while entry["slug"] in slugs:
            entry["slug"] = f"{base}-{n}"
            n += 1
        slugs.add(entry["slug"])
    args.manifest.write_text(
        json.dumps(existing + added, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"\n{len(added)} entry(ies) appended to {args.manifest}")


if __name__ == "__main__":
    main()
