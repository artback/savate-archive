"""Write one flat table of every bout and its result.

The organisers publish each outcome inline in the bout listing, beside the
corner that earned it: "<strong>Win</strong> (3)" against "<strong>Loses</strong>
(1)", or Forfait / Disqualified where the bout did not go to points. The only
bouts without one carry an <em> placeholder instead ("Match has not taken place
yet."). scrape_assaut.py reads only that <em>, so data.json records an empty
result for all 302 bouts; build_site.py works around it by reading poule
scoresheets and inferring knockout winners from who appears in the next round,
which leaves the finals - nothing follows them - permanently undecided.

This reads the outcome where the source actually states it, joins it to the bout
list and the scoresheets in data.json, and emits results.csv / results.json.
"""

import argparse
import csv
import glob
import json
import os
import re

from bs4 import BeautifulSoup

HEADER = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Ring:\s*(?P<ring>\d+)\s*"
    r"[→>-]+\s*(?P<time>\d{1,2}:\d{2})\s*h?"
    r"\s*(?:\([^)]*\))?"
    r"\s*:\s*(?P<category>.+)",
    re.S,
)

# How the source words the losing corner, and what each means.
DECISION = {"loses": "points", "forfait": "forfait",
            "disqualified": "disqualification"}

FIELDS = ["bout_id", "date", "time", "ring", "category", "agecat", "weightcat",
          "phase", "poule", "red", "red_country", "blue", "blue_country",
          "red_points", "blue_points", "winner_corner", "winner", "loser",
          "decision", "status", "result_source"]


def clean(t):
    return " ".join(t.split())


def norm(n):
    return clean(n).lower()


def key_of(date, time, ring, red, blue):
    return (date, time, ring, norm(red), norm(blue))


def corner_outcome(div):
    """(outcome word, points) for one corner's line, or (None, "")."""
    strong = div.find("strong")
    if not strong:
        return None, ""
    pts = re.search(r"\((\d+)\)", clean(div.get_text(" ", strip=True)))
    return clean(strong.get_text()).lower(), pts.group(1) if pts else ""


def read_listing(raw_dir):
    """Reported outcomes, and the country pages each bout appeared on.

    Every bout is listed on both fighters' country pages and nowhere else, which
    is what lets a fighter missing from the scoresheets still be placed.
    """
    reported, pages = {}, {}
    for path in sorted(glob.glob(os.path.join(raw_dir, "list_*.html"))):
        source_country = os.path.basename(path)[len("list_"):-len(".html")]
        source_country = source_country.replace("_", " ")
        with open(path, encoding="utf-8", errors="replace") as fh:
            soup = BeautifulSoup(fh.read(), "html.parser")
        for item in soup.select("div.match-item"):
            head = item.find("p")
            m = HEADER.search(clean(head.get_text(" ", strip=True))) if head else None
            red = item.select_one('span[style*="color:red"]')
            blue = item.select_one('span[style*="color:blue"]')
            body = item.select_one('div[style*="margin: 8px 0"]')
            if not (m and red and blue and body):
                continue
            sides = body.find_all("div", recursive=False)
            if len(sides) < 3:
                continue
            key = key_of(m.group("date"), m.group("time"), m.group("ring"),
                         red.get_text(), blue.get_text())
            pages.setdefault(key, set()).add(source_country)

            red_res, red_pts = corner_outcome(sides[0])
            blue_res, blue_pts = corner_outcome(sides[2])
            # Exactly one corner is ever marked Win; the other says how it lost.
            # Reading the winner off that word, rather than assuming the corners
            # are Win/Loses, is what keeps a forfeit from being scored backwards.
            if red_res == "win":
                winner, loser_word = "red", blue_res
            elif blue_res == "win":
                winner, loser_word = "blue", red_res
            else:
                continue  # still the "not taken place yet" placeholder
            # The same bout appears on both country pages, worded identically,
            # so a second sighting overwrites the first with the same values.
            reported[key] = {
                "winner_corner": winner,
                "red_points": red_pts,
                "blue_points": blue_pts,
                "decision": DECISION.get(loser_word, loser_word or ""),
            }
    return reported, pages


def scoresheets(data):
    """Poule scoresheet points and fighter countries.

    Keyed by draw *and* fighter pair, never by pair alone: two fighters can meet
    in their poule and again in the final, and the poule's score is not the
    final's. Matching on names only reports the poule bout twice.
    """
    pairs, country = {}, {}
    for poule in data["poules"]:
        draw = (poule["agecat"], poule["weightcat"], poule["poule"])
        for pair in poule["pairs"]:
            for corner in ("red", "blue"):
                country.setdefault(norm(pair[corner]), pair[f"{corner}_country"])
            pairs[draw + (frozenset((norm(pair["red"]), norm(pair["blue"]))),)] = pair
    return pairs, country


def place_missing(bouts, pages, country):
    """Fill in a fighter absent from every scoresheet, by elimination.

    A bout is listed on exactly its two fighters' country pages. With one
    fighter's country known, the page that is not theirs is the other's.
    """
    for b in bouts:
        seen = pages.get(key_of(b["date"], b["time"], b["ring"],
                                b["red"], b["blue"]))
        if not seen or len(seen) != 2:
            continue
        for this, other in (("red", "blue"), ("blue", "red")):
            if norm(b[this]) in country or norm(b[other]) not in country:
                continue
            rest = seen - {country[norm(b[other])]}
            if len(rest) == 1:
                country[norm(b[this])] = rest.pop()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--data", default="data.json")
    ap.add_argument("--csv", default="results.csv")
    ap.add_argument("--json", dest="json_out", default="results.json")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)
    reported, pages = read_listing(args.raw)
    pairs, country = scoresheets(data)
    place_missing(data["bouts"], pages, country)

    # Knockout bouts carry no poule link, so no draw key of their own; they
    # borrow the one every poule bout of the same category shares.
    cat_key = {}
    for b in data["bouts"]:
        if b["agecat"]:
            cat_key.setdefault(b["category"], (b["agecat"], b["weightcat"]))

    rows, unresolved = [], []
    for i, b in enumerate(sorted(data["bouts"],
                                 key=lambda x: (x["date"], x["time"].zfill(5),
                                                x["ring"]))):
        rep = reported.get(key_of(b["date"], b["time"], b["ring"],
                                  b["red"], b["blue"]))
        # Only a poule bout has a scoresheet, and only its own draw's.
        sheet = pairs.get((b["agecat"], b["weightcat"], b["poule"],
                           frozenset((norm(b["red"]), norm(b["blue"]))))) \
            if b["phase"] == "poule" else None
        agecat, weightcat = (b["agecat"], b["weightcat"]) if b["agecat"] else \
            cat_key.get(b["category"], ("", ""))

        red_pts = blue_pts = winner_corner = decision = source = ""
        if rep:
            red_pts, blue_pts = rep["red_points"], rep["blue_points"]
            winner_corner, decision = rep["winner_corner"], rep["decision"]
            source = "reported"
        elif sheet:
            # the sheet stores the pair red-corner-first as the draw has it,
            # which is not necessarily this bout's corner assignment
            same = norm(sheet["red"]) == norm(b["red"])
            red_pts = sheet["red_points" if same else "blue_points"]
            blue_pts = sheet["blue_points" if same else "red_points"]
            if (red_pts or "0") != "0" or (blue_pts or "0") != "0":
                winner_corner = "red" if int(red_pts) > int(blue_pts) else "blue"
                decision, source = "points", "scoresheet"
        if not winner_corner:
            red_pts = blue_pts = ""
            unresolved.append(b)

        winner = {"red": b["red"], "blue": b["blue"]}.get(winner_corner, "")
        loser = {"red": b["blue"], "blue": b["red"]}.get(winner_corner, "")
        rows.append(dict(zip(FIELDS, [
            f"b{i + 1:03d}", b["date"], b["time"], b["ring"], b["category"],
            agecat, weightcat, b["phase"], b["poule"],
            b["red"], country.get(norm(b["red"]), ""),
            b["blue"], country.get(norm(b["blue"]), ""),
            red_pts, blue_pts, winner_corner, winner, loser, decision,
            "decided" if winner_corner else "unresolved", source,
        ])))

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump({
            "source": data["source"],
            "fetched_at": data["fetched_at"],
            "changed_at": data["changed_at"],
            "bouts": len(rows),
            "decided": sum(1 for r in rows if r["status"] == "decided"),
            "unresolved": len(unresolved),
            "bout_list": rows,
        }, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"{len(rows)} bouts -> {args.csv}, {args.json_out}")
    print(f"decided {len(rows) - len(unresolved)} "
          f"({sum(1 for r in rows if r['result_source'] == 'reported')} reported, "
          f"{sum(1 for r in rows if r['result_source'] == 'scoresheet')} scoresheet), "
          f"unresolved {len(unresolved)}")
    for b in unresolved:
        print(f"  {b['date']} {b['time']} ring {b['ring']} {b['phase']:6s} "
              f"{b['category']}: {b['red']} vs {b['blue']}")


if __name__ == "__main__":
    main()
