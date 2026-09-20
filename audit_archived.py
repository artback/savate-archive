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
    c = nn(c)
    c = LOOSE.sub("", c)
    return c

def fp_of(rows):
    b, p = set(), set()
    for x in rows:
        if isinstance(x, Bout):
            b.add((frozenset({nn(x.red), nn(x.blue)}), loose_cat(x.category)))
        elif isinstance(x, Placing):
            p.add((nn(x.fighter), loose_cat(x.category), x.rank or ""))
    return b, p

rows = json.load(open("probe_wave2.json"))
ok = [r for r in rows if r.get("probe")]
db = sqlite3.connect("savate.db")

arch_b, arch_p = {}, {}
for slug, in db.execute("SELECT slug FROM tournaments"):
    b, p = set(), set()
    for r, bl, c in db.execute(
            "SELECT red, blue, category FROM bouts WHERE tournament=?", (slug,)):
        b.add((frozenset({nn(r), nn(bl)}), loose_cat(c)))
    for f, c, rk in db.execute(
            "SELECT fighter, category, rank FROM placings WHERE tournament=?", (slug,)):
        p.add((nn(f), loose_cat(c), rk or ""))
    arch_b[slug], arch_p[slug] = b, p

def ratio(doc_b, doc_p, arch_b, arch_p):
    best, used = 0.0, ""
    if doc_b and arch_b:
        r = len(doc_b & arch_b) / len(doc_b)
        if r >= 0.3:
            best, used = r, "bouts"
    if doc_p and arch_p:
        r = len(doc_p & arch_p) / len(doc_p)
        if r > best:
            best, used = r, "placings"
    return best, used

for i, r in enumerate(ok, 1):
    probe = r["probe"]
    t, ra, rep = adapters.get(probe["adapter"]).read(
        r["url"], f"x-{i}", {"name": r.get("title", ""), "year": r.get("year", "")})
    db_b, db_p = fp_of(ra)
    if not (db_b or db_p):
        continue
    hits = []
    for slug in arch_b:
        rr, used = ratio(db_b, db_p, arch_b[slug], arch_p[slug])
        if rr >= 0.7 and (len(db_b) >= 3 or len(db_p) >= 3):
            hits.append((rr, slug, used))
    if hits:
        hits.sort(reverse=True)
        rr, slug, used = hits[0]
        ty = (t.as_dict().get("year") or r.get("year", ""))
        print(f"{rr:.0%} [{used}] yr={ty:5} {Path(r['url']).name[:42]:44} ~ {slug}")