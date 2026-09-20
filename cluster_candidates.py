#!/usr/bin/env python3
"""Group unparsed documents by the shape of their text, not by their titles.

A title is the least reliable thing about a results document: "pool results" has
meant three different generators in one federation's archive, and half of the
links are called "Download". What a document actually IS shows in its text - how
it marks a weight class, whether it prints a grid or a list, whether it names a
club, whether it has a text layer at all.

So each file is reduced to a fingerprint of the features an adapter would key
on, and files sharing a fingerprint are one layout and one adapter's work.
Written down rather than eyeballed because 126 documents is more than anyone
holds in their head, and because the clusters are the plan.
"""

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import sources

# The marks an adapter would look for, each as (name, pattern).
FEATURES = [
    ("class_code_alone", r"^\s*[FMfm]\s*\+?\s*\d{2,3}\s*$"),
    ("weight_kg_heading", r"^\s*[-–+]?\s*\d{2,3}\s*kg\s*$"),
    ("weight_in_line", r"\b\d{2,3}\s*kg\b"),
    ("rank_degree", r"^\s*\d\s*°"),
    ("rank_ordinal_fr", r"\b\d\s*(er|ère|eme|ème|e)\b"),
    ("gold_silver_bronze", r"\b(gold|silver|bronze)\b"),
    ("champion_words", r"champion|vice-?champion|finaliste|vainqueur"),
    ("decision_words", r"unanimit|majorit|abandon|forfait|\bK\.?O\.?\b|arr[êe]t"),
    ("poule_word", r"\bpoule\b|\bpool\b|\bgroupe\b|\bgrupa\b"),
    ("seat_codes", r"\b[ABCD][1-6]\b"),
    ("points_avt", r"\bAVT\b|\bAV\b|\bPOINTS\b|\bTOTAL\b|\bRANK\b"),
    ("club_bracket_dept", r"\(\d{2,3}\)"),
    ("red_blue_corner", r"rouge|bleu|\bred\b|\bblue\b|crveni|plavi"),
    ("vs_pairing", r"\bvs\b|\bcontre\b|\b[-–]\s*\d\s*[-–]\s*\d\b"),
    ("table_header_nom", r"\bnom\b|\bname\b|\bprenom\b|\bpr[ée]nom\b|\bime\b"),
    ("licence_number", r"\b\d{6,9}\b"),
    ("serbian_cyrillic", r"[Ѐ-ӿ]"),
    ("date_dmy", r"\b\d{2}/\d{2}/\d{4}\b"),
]


def text_of(path):
    """The document's text layer, or "" where it has none."""
    for args in (["pdftotext", "-layout", str(path), "-"],
                 ["pdftotext", str(path), "-"]):
        try:
            out = subprocess.run(args, capture_output=True, text=True,
                                 timeout=60).stdout
            if out.strip():
                return out
        except Exception:
            continue
    try:
        raw = Path(path).read_bytes()[:400_000]
        if b"<html" in raw.lower() or b"<table" in raw.lower():
            return raw.decode("utf-8", "replace")
    except Exception:
        pass
    return ""


def fingerprint(text):
    marks = []
    for name, pattern in FEATURES:
        hits = len(re.findall(pattern, text, re.I | re.M))
        if hits:
            marks.append(name)
    return tuple(marks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--out", type=Path, default=Path("clusters.json"))
    ap.add_argument("--skip-parsed", action="store_true",
                    help="ignore documents an adapter already reads")
    args = ap.parse_args()

    entries = json.loads(args.candidates.read_text(encoding="utf-8"))
    rows = []
    for i, c in enumerate(entries, 1):
        if args.skip_parsed and c.get("probe"):
            continue
        url = c.get("url", "")
        try:
            path = sources.fetch(url)
            text = text_of(path)
        except Exception as e:
            rows.append({**c, "chars": 0, "marks": [], "note": f"fetch failed: {e}"})
            print(f"  [{i:3}] FETCH-FAIL  {c.get('title','')[:50]}", flush=True)
            continue
        marks = fingerprint(text)
        rows.append({**c, "chars": len(text), "marks": list(marks),
                     "sample": "\n".join(
                         [l for l in text.splitlines() if l.strip()][:14])})
        print(f"  [{i:3}] {len(text):7}c  {','.join(marks)[:58]:60} "
              f"{c.get('title','')[:34]}", flush=True)

    groups = collections.defaultdict(list)
    for r in rows:
        key = "no text layer" if r["chars"] < 40 else ",".join(r["marks"])
        groups[key].append(r)

    args.out.write_text(json.dumps(
        {"clusters": [{"marks": k, "count": len(v), "documents": v}
                      for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]},
        indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(rows)} documents in {len(groups)} layout families")
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:14]:
        print(f"  {len(v):4}  {k[:92]}")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
