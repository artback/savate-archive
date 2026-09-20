#!/usr/bin/env python3
"""Add manifest entries only after re-reading every document they name.

An adapter's author is the worst judge of whether their adapter works, and an
agent that wrote one is a worse judge still: the last run reported a document as
parsing when it had produced fifty-six bouts filing men under "Junior Women
-56 kg". So nothing proposed is taken on trust. Every entry is run here, in this
process, against the same judge the probe uses, and only the ones whose rows
survive are written to the manifest.

    python3 add_sources.py proposed.json              # what would be added
    python3 add_sources.py proposed.json --write      # add the ones that pass

The rejects are printed with their reason, because a document that nearly parses
is the most useful thing to look at next.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_candidates import judge
from savate import adapters

MANIFEST = Path("tournaments.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("proposed", type=Path)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    entries = json.loads(args.proposed.read_text(encoding="utf-8"))
    if isinstance(entries, dict):
        entries = entries.get("entries", [])

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    # A source is identified by its URL AND the event named within it: CESav
    # publishes nine European championships on one page, and keying on the URL
    # alone would admit the first and reject the other eight as duplicates.
    def identity(entry):
        return (entry.get("source", ""), str(entry.get("event", "")))

    known_sources = {identity(e) for e in manifest}
    known_slugs = {e["slug"] for e in manifest}

    passed, failed = [], []
    for i, e in enumerate(entries, 1):
        slug, source = e.get("slug", ""), e.get("source", "")
        label = (e.get("meta") or {}).get("name", slug)[:46]
        if identity(e) in known_sources:
            failed.append((label, "already in the manifest"))
            continue
        if not slug or not source or not e.get("adapter"):
            failed.append((label, "entry is missing slug, source or adapter"))
            continue
        # A slug collision would overwrite another event's rows.
        while slug in known_slugs:
            slug = f"{slug}-2"
        e["slug"] = slug

        try:
            adapter = adapters.get(e["adapter"])
        except Exception as exc:
            failed.append((label, f"no such adapter: {exc}"))
            continue
        try:
            _t, rows, report = adapter.read(source, slug, e.get("meta") or {})
        except Exception as exc:
            failed.append((label, f"read raised {type(exc).__name__}: {exc}"))
            continue

        usable, complaints, stats = judge(rows, report)
        if not usable:
            failed.append((label, "; ".join(complaints)))
            continue
        if not (stats.get("bouts") or stats.get("placings")):
            failed.append((label, "no rows"))
            continue

        # Review-only keys (underscore-prefixed) stay out of the manifest:
        # build_db would hand them to the adapter as options.
        passed.append({k: v for k, v in e.items() if not k.startswith("_")})
        known_sources.add(identity(e))
        known_slugs.add(slug)
        print(f"  [{i:3}] ok   b={stats['bouts']:4} p={stats['placings']:4}  {label}")

    print(f"\n{len(passed)} of {len(entries)} entries read into believable rows")
    if failed:
        print(f"\n{len(failed)} rejected:")
        for label, why in failed:
            print(f"  - {label}: {why[:96]}")

    if args.write and passed:
        manifest.extend(passed)
        args.manifest.write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print(f"\nmanifest now holds {len(manifest)} entries -> {args.manifest}")
        print("run: python3 build_db.py && python3 export_ui.py")
    elif passed:
        print("\n(dry run - pass --write to add them)")


if __name__ == "__main__":
    main()
