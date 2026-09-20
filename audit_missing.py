import json, re, sys, sqlite3
sys.path.insert(0, '.')
from pathlib import Path
from savate import adapters
from savate.schema import Bout, Placing

LOOSE = re.compile(
    r"(senior|junior|youth|cadet|young|espoir|benjamin|veteran|master"
    r"|women|woman|female|femmes|hommes|men|male|m|f|w|b)")

def nn(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def loose_cat(c):
    return LOOSE.sub("", nn(c))

def fp_of(rows):
    b, p = set(), set()
    for x in rows:
        if isinstance(x, Bout):
            b.add((frozenset({nn(x.red), nn(x.blue)}), loose_cat(x.category)))
        elif isinstance(x, Placing):
            p.add((nn(x.fighter), loose_cat(x.category), str(x.rank or "")))
    return b, p

rows = json.load(open("probe_wave2.json"))
db = sqlite3.connect("savate.db")

targets = (
    "415-world-assaut-championships-2018-medallists",
    "825-medallists-world-savate-assaut-championships-2022",
    "epmed.pdf",
    "assaut2024.pdf",
    "page-185b6a6db7", "page-f8cc87e701", "page-c0cdf60415",
    "download.php-id-12", "download.php-id-14",
    "20-qualifying-tournament",
)
for slug, in db.execute("SELECT slug FROM tournaments"):
    pass
slugs = [r[0] for r in db.execute("SELECT slug FROM tournaments")]

arch_b, arch_p = {}, {}
for slug in slugs:
    b, p = set(), set()
    for r, bl, c in db.execute(
            "SELECT red, blue, category FROM bouts WHERE tournament=?", (slug,)):
        b.add((frozenset({nn(r), nn(bl)}), loose_cat(c)))
    for f, c, rk in db.execute(
            "SELECT fighter, category, rank FROM placings WHERE tournament=?", (slug,)):
        p.add((nn(f), loose_cat(c), str(rk or "")))
    arch_b[slug], arch_p[slug] = b, p

for r in rows:
    fname = Path(r["url"]).name
    base = re.sub(r"[-_][0-9a-f]{8,}(?=\.(pdf|xls|xlsx|doc|html?)?$|$)", "", fname)
    hitkey = next((k for k in targets if k in base or k in fname), None)
    if not hitkey or not r.get("probe"):
        continue
    probe = r["probe"]
    t, ra, rep = adapters.get(probe["adapter"]).read(
        r["url"], "x", {"name": r.get("title", ""), "year": r.get("year", "")})
    db_b, db_p = fp_of(ra)
    names = set()
    for x in ra:
        if isinstance(x, Bout):
            names.update((nn(x.red), nn(x.blue)))
        elif isinstance(x, Placing):
            names.add(nn(x.fighter))
    print(f"\n=== {fname}")
    print(f"    adapter={probe['adapter']} b={len(db_b)} p={len(db_p)}")
    # name overlap vs target slug
    for slug in slugs:
        an = set()
        for (pair, c) in arch_b[slug]:
            an.update(pair)
        for (f, c, rk) in arch_p[slug]:
            an.add(f)
        if len(names) and len(an):
            ov = len(names & an) / len(names)
            if ov >= 0.4:
                print(f"    name overlap {ov:.0%} vs {slug}")
    # fingerprint ratios vs all slugs
    for slug in slugs:
        rb = (len(db_b & arch_b[slug]) / len(db_b)) if db_b and arch_b[slug] else 0
        rp = (len(db_p & arch_p[slug]) / len(db_p)) if db_p and arch_p[slug] else 0
        if max(rb, rp) >= 0.3:
            print(f"    fp: bouts {rb:.0%}, placings {rp:.0%} vs {slug}")
            if rp > 0.3 and db_p:
                miss = list(db_p - arch_p[slug])[:4]
                arch_sample = list(arch_p[slug])[:4]
                print(f"      doc fp sample:  {list(db_p)[:3]}")
                print(f"      miss sample:    {miss}")
                print(f"      arch fp sample: {arch_sample}")
            if rb > 0.3 and db_b:
                print(f"      doc bout fp:  {list(db_b)[:3]}")
                print(f"      arch bout fp: {list(arch_b[slug])[:3]}")