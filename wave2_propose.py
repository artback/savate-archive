#!/usr/bin/env python3
"""Propose second-wave manifest entries.

Two failure modes this must not make:

  * Double-count. A federation re-uploads its livret, or the same pool sheet
    arrives under several captures; each must count once. Two documents are
    one event when they share most of their fighters (Jaccard >= 0.5) and
    their years agree - a veteran who fought in both 2023 and 2024 may link
    the two documents, but the year split keeps the two events apart.
    Merging on a handful of shared names welded 268 unrelated documents into
    one cluster; a fifth of the fighters in common is a capture, three names
    is a coincidence.

  * A quiet garbage row. A text adapter handed a binary .doc prints control
    characters into the name field; the judge, who checks structure, not
    character sets, lets it through. So a row whose names carry control
    characters or a table header is rejected at the door.

Documents that name the fighters a manifest event already holds are dropped
as archived duplicates, one document at a time - a cluster's best document
matching the archive says nothing about the documents chained to it.
"""

import itertools
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import adapters
from savate.schema import Bout, Placing

# Adapters that read meta.name while parsing (an age class looked up in the
# name string). For them the meta name must keep the filename's words.
PARSE_AFFECTING = {"ffsavate_bouts", "savate_podium_words"}

JACCARD = 0.5    # captures of one event share most of their fighters
FP_DROP = 0.7    # at this share of identical bouts/placings it is a duplicate
NAME_DROP = 0.98 # at this share of identical names it is a re-capture
MIN_ROWS = 3     # fewer rows than this: not worth the review risk

JUNK_NAME = re.compile(
    r"classement|rang\s?lista|plasman|officiels|ranking|news|actualit"
    r"|ctualites?|actua|haberdetay", re.I)
OTHER_SPORT = re.compile(r"canne|b[aâ]ton|chausson|chauss", re.I)
HEADER_ROW = re.compile(r"\b(cognome|societ|stile|classe|nom|pr[eé]nom)\b", re.I)
WORLD_2022 = {"809", "810", "811", "812", "813", "814", "815", "816",
              "817", "818", "819", "820", "821", "823", "824"}


def norm_name(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def names_of(rows):
    names = set()
    for r in rows:
        if isinstance(r, Bout):
            names.update((r.red, r.blue, r.winner, r.loser))
        elif isinstance(r, Placing):
            names.add(r.fighter)
    out = set()
    for n in names:
        n = norm_name(n)
        if len(n) >= 4 and not n.isdigit():
            out.add(n)
    return out


def dirty(name):
    """A name a text layer could not have printed: control characters, or a
    binary .doc read as text."""
    for ch in name or "":
        o = ord(ch)
        if o < 0x20 and ch not in "\t\n":
            return True
        if o == 0xFFFD:
            return True
    return False


def pretty(fname):
    name = re.sub(r"[-_][0-9a-f]{8,}(?=\.(pdf|xls|xlsx|doc|html?)?$|$)", "", fname)
    name = re.sub(r"\.(pdf|xls|xlsx|doc|html?)$", "", name, flags=re.I)
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:60].strip("-") or "event"


def download_id(fname):
    m = re.search(r"(\d{3,4})[-_]", fname)
    return m.group(1) if m else ""


def base_name(fname):
    """The filename as the site named it: no cache hash, no dot-mangled
    extension (a cached 'page.js' arrives as 'page-js-<hash>')."""
    name = re.sub(r"[-_][0-9a-f]{8,}(?=\.(pdf|xls|xlsx|doc|html?|js|xml)?$|$)",
                  "", fname)
    name = name.replace("-", ".").replace("_", ".")
    return name.lower()


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i, j):
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.p[ri] = rj


def main():
    rows = json.loads(Path("probe_wave2.json").read_text(encoding="utf-8"))
    ok = [r for r in rows if r.get("probe")]

    docs = []
    errors = []
    for i, r in enumerate(ok, 1):
        probe = r["probe"]
        adapter = adapters.get(probe["adapter"])
        try:
            ta, ra, _rep = adapter.read(r["url"], f"w2-{i}",
                                        {"name": r.get("title", ""),
                                         "year": r.get("year", "")})
            tb, _rb, _rep2 = adapter.read(r["url"], f"w2-{i}",
                                          {"year": r.get("year", "")})
        except Exception as exc:
            errors.append({"file": r["url"],
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        fname = Path(r["url"]).name
        doc_name = (tb.name or "").strip()
        if doc_name == f"w2-{i}" or norm_name(doc_name) == norm_name(fname):
            doc_name = ""
        meta = ta.as_dict()
        year = meta.get("year") or r.get("year", "")
        docs.append({
            "i": i,
            "file": r["url"],
            "fname": fname,
            "score": probe["score"],
            "stats": probe["stats"],
            "adapter": probe["adapter"],
            "doc_name": doc_name,
            "file_name": pretty(fname),
            "year": year,
            "discipline": meta.get("discipline", ""),
            "level": meta.get("level", ""),
            "city": meta.get("city", ""),
            "meta": meta,
            "rows": ra,
            "names": names_of(ra),
        })

    # Archived duplicates, one document at a time. Two signals, because they
    # fail differently: a fingerprint (the same actual bout or medal line) is
    # the safe one - different events may share a whole national team but
    # never an identical bout; a name overlap catches re-captures whose
    # notation drifted ("Men -60 kg" vs "assaut men 56-60 kg", first names
    # vs surnames). 0.98 of the fighter set is one event; the riskiest
    # near-duplicate found in this wave (two Serbian events sharing a youth
    # pool) peaked at 0.91.
    LOOSE = re.compile(
        r"(senior|junior|youth|cadet|young|espoir|benjamin|veteran|master"
        r"|women|woman|female|femmes|hommes|men|male|m|f|w|b)")

    def loose_cat(c):
        return LOOSE.sub("", norm_name(c))

    def fp_of(rows):
        b, p = set(), set()
        for r in rows:
            if isinstance(r, Bout):
                b.add((frozenset({norm_name(r.red), norm_name(r.blue)}),
                       loose_cat(r.category)))
            elif isinstance(r, Placing):
                p.add((norm_name(r.fighter), loose_cat(r.category),
                       str(r.rank or "")))
        return b, p

    db = sqlite3.connect("savate.db")
    arch_names, arch_fp = {}, {}
    for slug, in db.execute("SELECT slug FROM tournaments"):
        names, fb, fp_ = set(), set(), set()
        for (a, b, c) in db.execute(
                "SELECT red, blue, category FROM bouts WHERE tournament = ?",
                (slug,)):
            names.update((norm_name(a), norm_name(b)))
            fb.add((frozenset({norm_name(a), norm_name(b)}), loose_cat(c)))
        for (f, c, rk) in db.execute(
                "SELECT fighter, category, rank FROM placings WHERE tournament = ?",
                (slug,)):
            names.add(norm_name(f))
            fp_.add((norm_name(f), loose_cat(c), str(rk or "")))
        names.discard("")
        arch_names[slug] = names
        arch_fp[slug] = (fb, fp_)

    for d in docs:
        doc_b, doc_p = fp_of(d["rows"])
        best, best_why = None, ""
        if len(d["names"]) >= 10 and (doc_b or doc_p):
            for slug, s in arch_names.items():
                if not s and not arch_fp[slug][0] and not arch_fp[slug][1]:
                    continue
                # The name branch needs a large set: a dozen shared fighters
                # is a shared national pool, not a re-capture.
                over = (len(d["names"] & s) / len(d["names"])
                        if len(d["names"]) >= 20 and s else 0.0)
                rb = (len(doc_b & arch_fp[slug][0]) / len(doc_b)
                      if doc_b and arch_fp[slug][0] else 0.0)
                rp = (len(doc_p & arch_fp[slug][1]) / len(doc_p)
                      if doc_p and arch_fp[slug][1] else 0.0)
                fp_best = max(rb, rp)
                hit = None
                if fp_best >= FP_DROP:
                    hit = f"same {len(doc_b if rb >= rp else doc_p)} row(s) " \
                          f"({fp_best:.0%})"
                elif over >= NAME_DROP:
                    hit = f"{over:.0%} of names, re-capture"
                if hit:
                    d["archived"] = (slug, hit)
                    best, best_why = slug, hit
                    break
        if best is None:
            d["archived"] = None

    # Cluster captures on shared fighters.
    uf = UnionFind(len(docs))
    index = defaultdict(list)
    for i, d in enumerate(docs):
        for n in d["names"]:
            index[n].append(i)
    sizes = {i: len(docs[i]["names"]) for i in range(len(docs))}
    for n, idxs in index.items():
        if not (2 <= len(idxs) <= 60):
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                shared = len(docs[ia]["names"] & docs[ib]["names"])
                if shared < 3:
                    continue
                small = min(sizes[ia], sizes[ib])
                if small and shared / small < JACCARD:
                    continue
                ya, yb = docs[ia]["year"], docs[ib]["year"]
                if ya and yb and ya != yb:
                    continue
                uf.union(ia, ib)

    clusters = defaultdict(list)
    for i, d in enumerate(docs):
        clusters[uf.find(i)].append(i)

    manifest = json.loads(Path("tournaments.json").read_text(encoding="utf-8"))
    known_slugs = {e["slug"] for e in manifest}

    proposed, rejected = [], []

    def reject(d, why):
        rejected.append({"file": d["file"], "label": d["doc_name"] or d["file_name"],
                         "why": why, "stats": d["stats"]})

    for members in clusters.values():
        members = sorted(members, key=lambda i: -docs[i]["score"])
        best = docs[members[0]]
        others = [docs[i]["file"] for i in members[1:]]
        label = best["doc_name"] or best["file_name"]

        if best["archived"]:
            reject(best, f"archived: {best['archived'][0]} "
                  f"({best['archived'][1]})")
            for i in members[1:]:
                reject(docs[i], f"cluster of archived {best['archived'][0]}")
            continue

        if OTHER_SPORT.search(label) or OTHER_SPORT.search(best["fname"]):
            reject(best, "canne de combat / chauss'fight - another sport")
            continue
        if JUNK_NAME.search(label) or JUNK_NAME.search(best["fname"]):
            reject(best, "aggregate ranking, officials list or news page")
            continue
        if base_name(best["fname"]).endswith((".js", ".xml", ".css")) or \
                label.lower() in ("page", "download", "lang french"):
            reject(best, "not a results document (asset or page shell)")
            continue
        if sum(1 for r in best["rows"]
               if isinstance(r, (Bout, Placing))) < MIN_ROWS:
            reject(best, "fewer than 3 rows - review by hand")
            continue
        dirty_names = [getattr(r, f, "") for r in best["rows"]
                       for f in ("red", "blue", "winner", "loser", "fighter")]
        if any(dirty(v) for v in dirty_names):
            reject(best, "names carry control characters - binary file misread")
            continue
        if any(HEADER_ROW.search(v) for v in dirty_names):
            reject(best, "table header parsed as a name")
            continue

        # The 2022 World Assaut pool sheets arrive under the page title
        # "World Championship"; the document's own footer names the event,
        # the year and the city (MILAN, 2022-09-24).
        if label == "World Championship" and best["year"] == "2022" and \
                download_id(best["fname"]) in WORLD_2022:
            label = "World Assaut Championship 2022"
            city = "Milan"
        else:
            city = best["city"]

        name = (best["doc_name"] if best["adapter"] not in PARSE_AFFECTING
                else "") or best["file_name"]
        if name == "World Championship":
            name = "World Assaut Championship 2022"
        slug = slugify(f"{name} {best['year']}").strip("-") or "event"
        while slug in known_slugs:
            slug += "-2"
        known_slugs.add(slug)
        meta = {"name": name, "year": best["year"]}
        for k in ("discipline", "level"):
            v = best["meta"].get(k, "")
            if v:
                meta[k] = v
        if city:
            meta["city"] = city
        proposed.append({
            "slug": slug,
            "adapter": best["adapter"],
            "source": best["file"],
            "meta": meta,
            "_review": {
                "label": label,
                "doc_name": best["doc_name"],
                "file_name": best["file_name"],
                "copies": len(members),
                "others": others,
                "stats": best["stats"],
                "names": len(best["names"]),
            },
        })
        entry = proposed[-1]
        entry["_nameset"] = set(best["names"])

    # One event captured through two different adapters. The adapters name the
    # same fighters differently (one embeds the club or a "FINALES <cc>"
    # wrapper, the other does not), so the Jaccard gate above - which needs
    # identical strings - never sees them as the same people. Substring
    # containment in BOTH directions catches it: 97% of one capture's names
    # surfacing inside the other's is one event, whatever the labels. A
    # one-directional overlap (60% in, 20% back) is a shared league pool
    # across venues and must be left alone. Keep the more complete capture.
    def containment(a, b):
        hit = 0
        for x in a:
            if any(len(x) > 3 and (x in y or y in x) for y in b):
                hit += 1
        return hit / max(1, len(a))

    by_year = defaultdict(list)
    for p in proposed:
        if p["meta"].get("year"):
            by_year[p["meta"]["year"]].append(p)
    for members in by_year.values():
        losers = []
        for a, b in itertools.combinations(members, 2):
            if a["adapter"] == b["adapter"] or id(a) in losers or id(b) in losers:
                continue
            sa, sb = a["_nameset"], b["_nameset"]
            if len(sa) < 8 or len(sb) < 8:
                continue
            if min(containment(sa, sb), containment(sb, sa)) < 0.45:
                continue
            ra = a["_review"]["stats"]["bouts"] + a["_review"]["stats"]["placings"]
            rb = b["_review"]["stats"]["bouts"] + b["_review"]["stats"]["placings"]
            loser, winner = (a, b) if rb >= ra else (b, a)
            losers.append(id(loser))
            proposed.remove(loser)
            rejected.append({
                "file": loser["source"],
                "label": loser["_review"]["label"],
                "why": (f"same event as {winner['slug']} via another adapter "
                        f"({loser['adapter']} vs {winner['adapter']})"),
                "stats": loser["_review"]["stats"],
            })

    for p in proposed:
        p.pop("_nameset", None)

    proposed.sort(key=lambda p: (p["_review"]["label"], p["slug"]))
    total_b = sum(p["_review"]["stats"]["bouts"] for p in proposed)
    total_p = sum(p["_review"]["stats"]["placings"] for p in proposed)
    archived = sum(1 for d in docs if d["archived"])
    print(f"{len(docs)} documents re-read (+{len(errors)} errors)")
    print(f"  archived duplicates: {archived} documents")
    print(f"  clusters: {len(clusters)} -> proposed events: {len(proposed)}")
    print(f"  +{total_b} bouts, +{total_p} placings")
    print(f"  rejected: {len(rejected)}")
    why = defaultdict(int)
    for r in rejected:
        why[r["why"].split(" -")[0][:28]] += 1
    for w, c in sorted(why.items(), key=lambda x: -x[1]):
        print(f"    {c:4} {w}")
    multi = [p for p in proposed if p["_review"]["copies"] > 1]
    print(f"  multi-copy clusters kept: {len(multi)} "
          f"(absorbs {sum(p['_review']['copies'] - 1 for p in multi)} duplicates)")
    for e in errors[:10]:
        print(f"  error {e['file']}: {e['error'][:90]}")

    Path("proposed_wave2.json").write_text(
        json.dumps(proposed, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    Path("wave2_review.json").write_text(
        json.dumps({"proposed": len(proposed), "rejected": rejected,
                    "errors": errors}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("-> proposed_wave2.json, wave2_review.json")


if __name__ == "__main__":
    main()