#!/usr/bin/env python3
"""
Scrape the World Championship Savate Assaut bout list and poule sheets.

    pip install requests beautifulsoup4
    python scrape_assaut.py                # refresh (honours --max-age)
    python scrape_assaut.py --fresh        # ignore the cache entirely
    python scrape_assaut.py --offline      # re-parse raw/ without any network

Outputs:
    data.json     the single source of truth: bouts, poules, scores, standings
    bouts.csv     one row per scheduled bout
    poules.csv    one row per pairing in every poule
    raw/          exact HTML of every page fetched, for auditing

Everything is parsed from the page DOM (div.match-item, the two poule tables),
not from flattened text, so a field is either read from the element that owns
it or left empty. Nothing is inferred.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://world-assaut-championship.sport/Acceso/qrcode/QRcodeList.php"
COMP_ID = 3
LANG = "en"
DELAY = 0.35
TIMEOUT = 15          # the site either answers in well under a second, or hangs
RETRIES = 2
BACKOFF = 1.5         # seconds, multiplied by the attempt number
BUDGET = 240          # seconds; past this, stop retrying and lean on the cache
RAW = Path("raw")
DATA = Path("data.json")

# The bout list gives clock times with no time zone and the site never says where
# it is being held, so this cannot be scraped - it is stated here or not at all.
VENUE_TZ = "Europe/Paris"        # Central European, CET/CEST
VENUE_TZ_LABEL = "Central European Time"

# The country filter is mandatory: the listing returns nothing without it.
# One known-good country bootstraps the real list out of the page's own <select>.
SEED_COUNTRY = "France"

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (bout-list-export)"


class Fetcher:
    """GET with an on-disk cache. Pages older than max_age are re-fetched."""

    def __init__(self, max_age=0, offline=False):
        self.max_age = max_age
        self.offline = offline
        self.hits = self.misses = 0
        self.stale = []          # pages served from cache because the fetch failed
        self.started = time.time()

    def __call__(self, params, name):
        RAW.mkdir(exist_ok=True)
        path = RAW / f"{name}.html"
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if self.offline or age <= self.max_age:
                self.hits += 1
                return path.read_text(encoding="utf-8")
        if self.offline:
            raise SystemExit(f"--offline but {path} is missing; run a normal refresh first")

        # The site times out sporadically. Letting one bad page abort the whole
        # run meant a single 30-second hiccup cost the entire refresh - hours of
        # them, in practice. Retry, then fall back to the cached copy and SAY SO,
        # rather than either dying or quietly passing stale data off as fresh.
        # Retrying every slow page turned a 40-second run into an hour-long one,
        # which is useless on a 10-minute schedule. Past the budget, take one
        # shot per page and fall back to cache, so a run always lands.
        tries = RETRIES if (time.time() - self.started) < BUDGET else 1
        last = None
        for attempt in range(tries):
            try:
                r = session.get(BASE, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                r.encoding = r.encoding or "utf-8"
                path.write_text(r.text, encoding="utf-8")
                self.misses += 1
                time.sleep(DELAY)
                return r.text
            except requests.RequestException as e:
                last = e
                if attempt + 1 < tries:
                    time.sleep(BACKOFF * (attempt + 1))

        if path.exists():
            age_min = (time.time() - path.stat().st_mtime) / 60
            self.stale.append(f"{name}: fetch failed ({type(last).__name__}); "
                              f"using cached copy {age_min:.0f} min old")
            self.hits += 1
            return path.read_text(encoding="utf-8")
        raise RuntimeError(f"{name}: fetch failed and no cached copy exists") from last


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def norm(s):
    """Fold a fighter name for matching: the site is inconsistent about
    whitespace (several names carry a stray tab) and letter case."""
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


# --- listing page ----------------------------------------------------------

# "2026-09-10 - Ring: 1 -> 14:33h" then, on later lines, "(2:33 pm) :" and the
# category. Anchored on the DOM element, so only the inside of the <p> is ever
# considered; the am/pm parenthetical is consumed explicitly so it can never be
# mistaken for the category.
HEADER = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Ring:\s*(?P<ring>\d+)\s*"
    r"[→>-]+\s*(?P<time>\d{1,2}:\d{2})\s*h?"
    r"\s*(?:\([^)]*\))?"
    r"\s*:\s*(?P<category>.+)",
    re.S,
)

# The site's own placeholder for a bout that has not happened, in all three
# languages it serves. Matching it is how "pending" is established; a bout is
# never called finished just because no result text was found.
PENDING = re.compile(
    r"has not taken place|n'a pas encore eu lieu|a[uú]n no tuvo lugar", re.I)

# How the site words each corner's outcome, in the three languages it serves,
# and what the losing corner's word says about how the bout ended. The winning
# corner is the one marked WIN; reading it off that word rather than assuming
# the pair is win/lose is what keeps a forfeit from being scored backwards.
WIN = re.compile(r"^(win|victoire|gagne|gana|victoria)", re.I)
DECISION = (
    (re.compile(r"forfait|walkover|w\.?o\.?", re.I), "forfait"),
    (re.compile(r"disqualif|d[ée]classement", re.I), "disqualification"),
    (re.compile(r"loses|perd|pierde|defeat", re.I), "points"),
)


def decision_of(word):
    for pattern, name in DECISION:
        if pattern.search(word):
            return name
    return ""


def corner_outcome(div):
    """(outcome word, points) for one corner's line, or ("", "").

    The outcome lives in the corner's own <strong>, the score in the bare "(3)"
    beside it. Both are read from the element that owns them; a corner with no
    <strong> has no reported outcome, which is not the same as having lost.
    """
    strong = div.find("strong") if div else None
    if not strong:
        return "", ""
    points = re.search(r"\((\d+)\)", clean(div.get_text(" ", strip=True)))
    return clean(strong.get_text()), points.group(1) if points else ""

POULE_QS = ("agecat", "weightcat", "poule")


def poule_key(a):
    """Read the draw key straight out of the bout's own 'View Poule' link.

    This is the site's primary key for a draw. Taking it from the link means a
    bout is attached to its draw exactly, instead of being matched to one by
    fighter name, which is what used to merge unrelated weight classes.
    """
    if not a or not a.get("href"):
        return None
    q = parse_qs(urlparse(a["href"]).query)
    if not all(k in q for k in POULE_QS):
        return None
    return tuple(q[k][0] for k in POULE_QS)


def parse_listing(html, source_country):
    soup = BeautifulSoup(html, "html.parser")
    out, problems = [], []

    for item in soup.select("div.match-item"):
        head = item.find("p")
        m = HEADER.search(clean(head.get_text(" ", strip=True)) if head else "")
        if not m:
            problems.append(f"{source_country}: unparseable header "
                            f"{clean(head.get_text()) [:80] if head else '<missing <p>>'!r}")
            continue

        h2 = item.find("h2")
        red = item.select_one('span[style*="color:red"]')
        blue = item.select_one('span[style*="color:blue"]')
        if not (red and blue):
            problems.append(f"{source_country}: match-item without both corners")
            continue

        # An unfought bout carries the <em> placeholder; a fought one states the
        # outcome in each corner's <strong>. Read the corners first and fall
        # back to the placeholder, so a result is never missed by looking only
        # at the element that means "there is no result".
        body = item.select_one('div[style*="margin: 8px 0"]')
        sides = body.find_all("div", recursive=False) if body else []
        red_word, red_points = corner_outcome(sides[0] if len(sides) > 2 else None)
        blue_word, blue_points = corner_outcome(sides[2] if len(sides) > 2 else None)

        winner = ("red" if WIN.search(red_word) else
                  "blue" if WIN.search(blue_word) else "")
        decision = decision_of(blue_word if winner == "red" else
                               red_word if winner == "blue" else "")
        if winner:
            result = (f"{red_points}-{blue_points}" if decision == "points"
                      and red_points and blue_points else decision)
        else:
            result = ""
            red_points = blue_points = ""
            em = item.find("em")
            placeholder = clean(em.get_text(" ", strip=True)) if em else ""
            if not (placeholder and PENDING.search(placeholder)):
                # Neither an outcome nor the placeholder the site uses for an
                # unfought bout: the markup has moved, and silently calling it
                # pending would hide that.
                problems.append(f"{source_country}: bout at {m.group('date')} "
                                f"{m.group('time')} has neither a corner outcome "
                                f"nor the pending placeholder")
        pk = poule_key(item.find("a", href=True))

        out.append({
            "date": m.group("date"),
            "ring": m.group("ring"),
            "time": m.group("time"),
            "category": clean(m.group("category")),
            "phase": clean(h2.get_text(" ", strip=True)) if h2 else "",
            "red": clean(red.get_text(" ", strip=True)),
            "blue": clean(blue.get_text(" ", strip=True)),
            "result": result,
            "pending": not winner,
            "winner_corner": winner,
            "red_points": red_points,
            "blue_points": blue_points,
            "decision": decision,
            "agecat": pk[0] if pk else "",
            "weightcat": pk[1] if pk else "",
            "poule": pk[2] if pk else "",
            "seen_under": source_country,
        })
    return out, problems


def options(html, select_id):
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", id=select_id)
    if not sel:
        return []
    return [o["value"] for o in sel.find_all("option") if o.get("value")]


# --- poule sheet -----------------------------------------------------------

NAME_COUNTRY = re.compile(r"^(.*?)\s*\(([^)]+)\)$")
NO_STANDINGS = re.compile(
    r"classification will be available|classement est indisponible|"
    r"classement estar[aá] disponible", re.I)


def parse_poule(html, agecat, weightcat, poule):
    """Two tables: the draw (Red | Blue rows) and the scoresheet.

    The scoresheet has two header rows - fighter names spanning two columns
    each, then Points/Warnings - followed by one row per bout in the SAME order
    as the draw table, and a highlighted totals row. A fighter not in a given
    bout has grey (empty) cells, which is how the score is attributed without
    guessing.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    pairs, fighters, warns = [], [], []

    if tables:
        for tr in tables[0].find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) != 2:
                continue
            a, b = (NAME_COUNTRY.match(clean(c)) for c in cells)
            if not (a and b):
                warns.append(f"poule {agecat}/{weightcat}/{poule}: "
                             f"unparseable draw row {cells!r}")
                continue
            pairs.append({"red": clean(a.group(1)), "red_country": clean(a.group(2)),
                          "blue": clean(b.group(1)), "blue_country": clean(b.group(2))})

    scores, totals = [], {}
    if len(tables) > 1:
        trs = tables[1].find_all("tr")
        names = [clean(th.get_text(" ", strip=True))
                 for th in trs[0].find_all("th")] if trs else []
        fighters = names
        body = [tr for tr in trs[2:]] if len(trs) > 2 else []
        for tr in body:
            tds = tr.find_all("td")
            if len(tds) != 2 * len(names):
                continue
            row = {}
            for i, name in enumerate(names):
                pts, av = tds[2 * i], tds[2 * i + 1]
                if "grey" in (pts.get("class") or []):
                    continue        # this fighter sat this bout out
                row[name] = {"points": clean(pts.get_text()),
                             "warnings": clean(av.get_text())}
            if "highlight" in (tr.get("class") or []):
                totals = row
            else:
                scores.append(row)

    if len(scores) != len(pairs) and pairs and scores:
        warns.append(f"poule {agecat}/{weightcat}/{poule}: {len(pairs)} draw rows "
                     f"but {len(scores)} score rows - scores not attached")
        scores = []

    for pair, row in zip(pairs, scores):
        for corner in ("red", "blue"):
            cell = row.get(pair[corner]) or {}
            pair[f"{corner}_points"] = cell.get("points", "")
            pair[f"{corner}_warnings"] = cell.get("warnings", "")

    return {
        "agecat": agecat, "weightcat": weightcat, "poule": poule,
        "pairs": pairs,
        "fighters": fighters,
        "totals": totals,
        "standings_final": not bool(NO_STANDINGS.search(html)),
    }, warns


# --- main ------------------------------------------------------------------

def scrape(fetch):
    warnings = []

    seed = fetch({"lang": LANG, "compId": COMP_ID, "country": SEED_COUNTRY,
                  "day": "", "ring": "", "tireur": ""}, f"list_{slug(SEED_COUNTRY)}")
    countries = options(seed, "country")
    days = options(seed, "day")
    rings = options(seed, "ring")
    if not countries:
        raise SystemExit("could not read the country list from the page - "
                         "the site layout has changed; inspect raw/list_France.html")

    bouts, seen = [], {}
    for country in countries:
        html = seed if country == SEED_COUNTRY else fetch(
            {"lang": LANG, "compId": COMP_ID, "country": country,
             "day": "", "ring": "", "tireur": ""}, f"list_{slug(country)}")
        page, probs = parse_listing(html, country)
        warnings += probs
        for b in page:
            # The same bout is listed under both fighters' countries. Identity
            # is the draw key plus the unordered pair - not the time slot,
            # which can legitimately be shared and can also be rescheduled.
            key = (b["agecat"], b["weightcat"], b["poule"], b["phase"],
                   tuple(sorted((norm(b["red"]), norm(b["blue"])))))
            if key in seen:
                prev = seen[key]
                if (prev["date"], prev["time"], prev["ring"]) != \
                   (b["date"], b["time"], b["ring"]):
                    warnings.append(
                        f"{b['red']} vs {b['blue']}: listed twice with different "
                        f"slots ({prev['date']} {prev['time']} ring {prev['ring']} "
                        f"vs {b['date']} {b['time']} ring {b['ring']})")
                continue
            seen[key] = b
            bouts.append(b)

    keys = sorted({(b["agecat"], b["weightcat"], b["poule"])
                   for b in bouts if b["poule"]})
    poules = []
    for agecat, weightcat, poule in keys:
        html = fetch({"showpoule": 1, "compId": COMP_ID, "agecat": agecat,
                      "weightcat": weightcat, "poule": poule, "lang": LANG},
                     f"poule_{agecat}_{weightcat}_{poule}")
        p, warns = parse_poule(html, agecat, weightcat, poule)
        warnings += warns
        poules.append(p)

    warnings += fetch.stale
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": BASE,
        "competition_id": COMP_ID,
        # The organisers publish bare clock times with no zone. This is the zone
        # they are in, supplied by hand because the source never states it.
        "venue_tz": VENUE_TZ,
        "venue_tz_label": VENUE_TZ_LABEL,
        "countries": countries, "days": days, "rings": rings,
        "bouts": sorted(bouts, key=lambda b: (b["date"], b["time"].zfill(5), b["ring"])),
        "poules": poules,
        "warnings": warnings,
    }


def fingerprint(data):
    """Hash of the parts that carry meaning. Deliberately excludes fetched_at
    and warnings, so re-reading an unchanged source is recognised as unchanged
    rather than looking like fresh news every quarter of an hour.

    Every field the bouts carry is hashed, results included. This once covered
    only the timetable, because results never reached it - so a run that picked
    up eleven decided finals still reported "no change", and did for five days.
    A hash that cannot see the results is not a hash of the news."""
    core = {"bouts": data["bouts"], "poules": data["poules"]}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def slot_key(b):
    return (b["agecat"], b["weightcat"], b["poule"],
            tuple(sorted((norm(b["red"]), norm(b["blue"])))))


def track_reschedules(data, previous):
    """Record any bout whose date, time or ring moved since the last read.

    The organisers publish a fixed timetable and have not revised it, but that
    is an observation, not a guarantee - so every refresh checks, and anything
    that does move is kept and shown rather than silently swapped in.
    """
    history = list((previous or {}).get("schedule_changes") or [])
    if previous:
        was = {slot_key(b): b for b in previous["bouts"]}
        for b in data["bouts"]:
            old = was.get(slot_key(b))
            if not old:
                continue
            before = (old["date"], old["time"], old["ring"])
            after = (b["date"], b["time"], b["ring"])
            if before != after:
                history.append({
                    "noticed_at": data["fetched_at"],
                    "red": b["red"], "blue": b["blue"],
                    "from": {"date": before[0], "time": before[1], "ring": before[2]},
                    "to": {"date": after[0], "time": after[1], "ring": after[2]},
                })
    data["schedule_changes"] = history[-50:]
    return len(history) - len((previous or {}).get("schedule_changes") or [])


def carry_change_stamp(data, previous):
    """Set changed_at to the moment the data last actually differed.

    Checking the source and the source having something new are two different
    events, and conflating them is what makes a quiet page look broken.
    """
    data["content_hash"] = fingerprint(data)
    if previous and previous.get("content_hash") == data["content_hash"]:
        data["changed_at"] = previous.get("changed_at") or data["fetched_at"]
        return False
    data["changed_at"] = data["fetched_at"]
    return True


def country_index(poules):
    """name -> country, from the poule sheets (the listing page has no flags)."""
    out = {}
    for p in poules:
        for pair in p["pairs"]:
            out[norm(pair["red"])] = pair["red_country"]
            out[norm(pair["blue"])] = pair["blue_country"]
    return out


def audit(data):
    """Consistency checks. These describe the data; they do not repair it."""
    b, p = data["bouts"], data["poules"]
    notes = []

    unkeyed = [x for x in b if not x["poule"]]
    if unkeyed:
        notes.append(f"{len(unkeyed)} bout(s) carry no draw key (no poule link) - "
                     f"these are knockout bouts or a layout change")

    drawn = set()
    for q in p:
        for pair in q["pairs"]:
            drawn.add((q["agecat"], q["weightcat"], q["poule"],
                       frozenset((norm(pair["red"]), norm(pair["blue"])))))
    scheduled = {(x["agecat"], x["weightcat"], x["poule"],
                  frozenset((norm(x["red"]), norm(x["blue"]))))
                 for x in b if x["poule"]}
    if drawn - scheduled:
        notes.append(f"{len(drawn - scheduled)} drawn pairing(s) have no scheduled bout")
    if scheduled - drawn:
        notes.append(f"{len(scheduled - drawn)} scheduled bout(s) are not in their "
                     f"poule's draw table")

    idx = country_index(p)
    missing = sorted({x["red"] for x in b if norm(x["red"]) not in idx}
                     | {x["blue"] for x in b if norm(x["blue"]) not in idx})
    if missing:
        notes.append(f"{len(missing)} fighter(s) have no country, e.g. {missing[:3]}")

    phases = Counter(x["phase"] for x in b)
    notes.append("phase labels: " + ", ".join(f"{k!r}x{v}" for k, v in phases.most_common()))
    notes.append(f"{sum(1 for x in b if not x['pending'])}/{len(b)} bouts have a result")
    notes.append(f"{sum(1 for q in p if q['standings_final'])}/{len(p)} poules have "
                 f"final standings")
    return notes


def write_csvs(data):
    b = data["bouts"]
    if not b:
        raise SystemExit("no bouts parsed - refusing to overwrite bouts.csv.\n"
                         "Compare raw/list_France.html against parse_listing().")
    cols = ["date", "time", "ring", "category", "phase", "red", "blue", "result",
            "pending", "winner_corner", "red_points", "blue_points", "decision",
            "agecat", "weightcat", "poule", "seen_under"]
    with open("bouts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(b)

    rows = [dict(agecat=q["agecat"], weightcat=q["weightcat"], poule=q["poule"], **pair)
            for q in data["poules"] for pair in q["pairs"]]
    if rows:
        cols = ["agecat", "weightcat", "poule", "red", "red_country", "blue",
                "blue_country", "red_points", "red_warnings", "blue_points",
                "blue_warnings"]
        with open("poules.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return len(b), len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fresh", action="store_true",
                    help="delete raw/ and re-fetch every page")
    ap.add_argument("--offline", action="store_true",
                    help="parse raw/ only; never touch the network")
    ap.add_argument("--max-age", type=int, default=0, metavar="SEC",
                    help="reuse cached pages younger than this (default 0: "
                         "always re-fetch)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.fresh and RAW.exists():
        shutil.rmtree(RAW)

    previous = None
    if DATA.exists():
        try:
            previous = json.loads(DATA.read_text(encoding="utf-8"))
        except ValueError:
            pass

    fetch = Fetcher(max_age=args.max_age, offline=args.offline)
    t0 = time.time()
    data = scrape(fetch)
    moved = track_reschedules(data, previous)
    changed = carry_change_stamp(data, previous)
    n_bouts, n_pairs = write_csvs(data)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    notes = audit(data)
    if not args.quiet:
        print(f"fetched {fetch.misses} page(s), {fetch.hits} from cache, "
              f"in {time.time() - t0:.1f}s")
        print(f"{n_bouts} bouts, {len(data['poules'])} poules, {n_pairs} pairings "
              f"-> data.json, bouts.csv, poules.csv")
        print(f"  - {moved} bout(s) rescheduled this run; "
              f"{len(data['schedule_changes'])} total today")
        print("  - " + ("source CHANGED this run"
                        if changed else
                        f"no change since {data['changed_at']}"))
        for n in notes:
            print(f"  - {n}")
        for w in data["warnings"][:10]:
            print(f"  !! {w}")
        if len(data["warnings"]) > 10:
            print(f"  !! ... and {len(data['warnings']) - 10} more (see data.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
