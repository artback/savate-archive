#!/usr/bin/env python3
"""Cluster the second-wave passers into events.

The probe passed the filename as the tournament name, so the names it kept
were garbage. Re-read each document without a name and let the adapter find
the championship's own headline; where it cannot, the prettified filename is
the fallback. Two documents are one event when their resolved name, year,
discipline and city agree, or when their filenames agree once version
suffixes (-1, -2, -v07.05, ...) and hash tails are stripped - a federation
re-uploading a livret with the same championship is one event, not several.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import adapters


def norm(s):
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def pretty_file(fname):
    """A readable name from a cache filename: strip hash tails, dots, dashes."""
    name = re.sub(r"[-_][0-9a-f]{8,}(?=\.(pdf|xls|xlsx|doc|html?)?$|$)", "", fname)
    name = re.sub(r"\.(pdf|xls|xlsx|doc|html?)$", "", name, flags=re.I)
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if re.fullmatch(r"[a-z0-9 .-]+", fname, re.I) else name


def file_event_key(fname):
    """Filenames that name the same championship once versions are dropped."""
    name = re.sub(r"[-_][0-9a-f]{8,}(?=\.(pdf|xls|xlsx|doc|html?)?$|$)", "", fname)
    name = re.sub(r"\.(pdf|xls|xlsx|doc|html?)$", "", name, flags=re.I)
    # version markers: -1, -2, -v18.04, -v07.0, -v2, -v190525, (1), -copy
    name = re.sub(r"[-_ ]+\(?\d+\)?$", "", name)
    name = re.sub(r"[-_ ]+v?\d{1,2}\.\d{1,2}$", "", name, flags=re.I)
    name = re.sub(r"[-_ ]+v\d{1,6}$", "", name, flags=re.I)
    name = re.sub(r"[-_ ]+copy\b.*$", "", name, flags=re.I)
    return norm(name)


def main():
    rows = json.loads(Path("probe_wave2.json").read_text(encoding="utf-8"))
    ok = [r for r in rows if r.get("probe")]
    manifest = json.loads(Path("tournaments.json").read_text(encoding="utf-8"))

    man_keys = set()
    for e in manifest:
        m = e.get("meta") or {}
        man_keys.add((m.get("year", ""), m.get("discipline", ""),
                      m.get("level", ""), norm(m.get("name", ""))))

    docs = []
    errors = []
    for i, r in enumerate(ok, 1):
        probe = r["probe"]
        try:
            t, _rows, _report = adapters.get(probe["adapter"]).read(
                r["url"], f"w2-{i}", {"year": r.get("year", "")})
        except Exception as exc:
            errors.append({"file": r["url"], "adapter": probe["adapter"],
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        m = t.as_dict()
        doc_name = (m.get("name") or "").strip()
        # A name that is really the slug we passed back is not a finding.
        if doc_name == f"w2-{i}" or norm(doc_name) == norm(Path(r["url"]).name):
            doc_name = ""
        year = m.get("year") or r.get("year", "")
        docs.append({
            "file": r["url"],
            "fname": Path(r["url"]).name,
            "score": probe["score"],
            "stats": probe["stats"],
            "adapter": probe["adapter"],
            "doc_name": doc_name,
            "file_name": pretty_file(Path(r["url"]).name),
            "year": year,
            "discipline": m.get("discipline", ""),
            "level": m.get("level", ""),
            "city": m.get("city", ""),
            "meta": m,
        })

    # Cluster 1: the championship as the document names it.
    by_event = defaultdict(list)
    for d in docs:
        if d["doc_name"]:
            by_event[(norm(d["doc_name"]), d["year"], d["discipline"],
                      d["level"], norm(d["city"]))].append(d)
    clustered = set(id(d) for recs in by_event.values() for d in recs)

    # Cluster 2: same filename modulo version suffixes (unresolved names).
    by_file = defaultdict(list)
    for d in docs:
        if id(d) in clustered:
            continue
        by_file[file_event_key(d["fname"])].append(d)

    events = []
    for key, recs in by_event.items():
        events.append((recs, key, "document headline"))
    for key, recs in by_file.items():
        if len(recs) > 1:
            events.append((recs, key, "filename (version-stripped)"))

    unclustered = [d for d in docs
                   if id(d) not in clustered
                   and len(by_file.get(file_event_key(d["fname"]), [])) == 1]

    def best(recs):
        recs = sorted(recs, key=lambda x: -x["score"])
        return recs[0], [x["file"] for x in recs[1:]]

    out = []
    matched_manifest = 0
    for recs, key, how in events:
        b, others = best(recs)
        name = b["doc_name"] or b["file_name"]
        keyn = (b["year"], b["discipline"], b["level"], norm(name))
        in_man = keyn in man_keys or (
            how == "document headline" and key in man_keys)
        if in_man:
            matched_manifest += 1
        out.append({
            "how": how,
            "name": name,
            "year": b["year"],
            "discipline": b["discipline"],
            "level": b["level"],
            "city": b["city"],
            "manifest_match": in_man,
            "copies": len(recs),
            "best": b,
            "others": others,
        })

    for d in unclustered:
        name = d["doc_name"] or d["file_name"]
        keyn = (d["year"], d["discipline"], d["level"], norm(name))
        out.append({
            "how": "single",
            "name": name,
            "year": d["year"],
            "discipline": d["discipline"],
            "level": d["level"],
            "city": d["city"],
            "manifest_match": keyn in man_keys,
            "copies": 1,
            "best": d,
            "others": [],
        })

    out.sort(key=lambda c: (c["manifest_match"], -c["best"]["score"]))
    new = [c for c in out if not c["manifest_match"]]
    multi = [c for c in out if c["copies"] > 1]
    print(f"{len(out)} events from {len(docs)} documents (+{len(errors)} re-read errors)")
    print(f"  manifest matches dropped: {matched_manifest}")
    print(f"  multi-copy clusters: {len(multi)} "
          f"(drops {sum(c['copies'] - 1 for c in multi)} duplicate captures)")
    print(f"  new events: {len(new)}")
    print(f"  would add: {sum(c['best']['stats']['bouts'] for c in new)} bouts, "
          f"{sum(c['best']['stats']['placings'] for c in new)} placings")
    named = sum(1 for c in out if c["best"]["doc_name"])
    print(f"  documents with an extracted headline: {named}/{len(docs)}")
    if errors:
        print(f"  re-read errors:")
        for e in errors[:15]:
            print(f"    - {e['file']}: {e['error'][:100]}")
    print("\nmulti-copy clusters:")
    for c in sorted(multi, key=lambda x: -x["copies"]):
        print(f"  x{c['copies']:2} {c['name'][:70]}")

    Path("wave2_events.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n-> wave2_events.json")


if __name__ == "__main__":
    main()