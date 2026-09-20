#!/usr/bin/env python3
"""
Build a single self-contained HTML page from data.json.

    python build_site.py                    # -> site.html
    python build_site.py --out other.html

Every figure on the page comes from data.json, which comes from the
organisers' own pages. Where the source has not published something yet -
knockout draws, results, final poule classifications - the page says so
instead of projecting it.
"""

import argparse
import json
import re
from pathlib import Path

SRC = Path("data.json")

GENDERS = [("Women", r"\bwomen\b|\bfemmes?\b|\bdames?\b"),
           ("Men", r"\bmen\b|\bhommes?\b")]
WEIGHT = re.compile(r"([-+\u2212])\s*(\d+(?:[.,]\d+)?)\s*kg", re.I)
AGE = re.compile(r"\b(senior|junior|cadet|veteran|master)\w*\b", re.I)
POULE_PHASE = re.compile(r"poule|pool|group", re.I)


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def parse_category(label):
    """'Senior Men Assaut -80 kg' -> structured. Nothing invented: a part that
    isn't in the label comes back empty."""
    gender = next((g for g, pat in GENDERS if re.search(pat, label, re.I)), "")
    age = AGE.search(label)
    m = WEIGHT.search(label)
    sign = m.group(1).replace("\u2212", "\u2212") if m else ""
    kg = float(m.group(2).replace(",", ".")) if m else None
    short = f"{sign}{kg:g} kg" if kg is not None else label
    return {
        "label": label,
        "gender": gender,
        "age": age.group(0).title() if age else "",
        "kg": kg,
        "over": sign == "+",
        "short": short,
        "title": " ".join(p for p in (gender, short) if p) or label,
    }


def build(data):
    bouts = data["bouts"]
    poules = {(q["agecat"], q["weightcat"], q["poule"]): q for q in data["poules"]}

    # country per fighter comes from the poule sheets - the listing has none
    country = {}
    for q in data["poules"]:
        for pair in q["pairs"]:
            country[norm(pair["red"])] = pair["red_country"]
            country[norm(pair["blue"])] = pair["blue_country"]

    def record(b, key):
        return {
            "date": b["date"], "time": b["time"], "ring": b["ring"],
            "red": b["red"], "red_country": country.get(norm(b["red"]), ""),
            "blue": b["blue"], "blue_country": country.get(norm(b["blue"]), ""),
            "result": b["result"], "pending": b["pending"],
            "phase": b["phase"], "poule": b["poule"], "cat": key,
            # the outcome as the source states it, beside the corner that
            # earned it; empty only where the source has posted nothing
            "reported": b.get("winner_corner", ""),
            "decision": b.get("decision", ""),
            "rp": b.get("red_points", ""), "bp": b.get("blue_points", ""),
        }

    # Pass 1: poule bouts. These carry the draw key in their own "View Poule"
    # link, so they define the weight classes and everything hangs off them.
    cats, by_label, cat_of_fighter = {}, {}, {}
    for b in bouts:
        if not (b["poule"] and POULE_PHASE.search(b["phase"] or "poule")):
            continue
        key = f'{b["agecat"]}/{b["weightcat"]}'
        c = cats.setdefault(key, {"key": key, **parse_category(b["category"]),
                                  "poules": {}, "knockout": []})
        by_label.setdefault(norm(b["category"]), key)
        for who in (b["red"], b["blue"]):
            cat_of_fighter[norm(who)] = key
        pl = c["poules"].setdefault(b["poule"], {"name": b["poule"], "bouts": [],
                                                 "fighters": [], "final": False})
        pl["bouts"].append(record(b, key))

    # Pass 2: knockout bouts. A knockout bout has NO poule link, so its agecat
    # and weightcat come back empty - keying on them put every knockout bout in
    # a phantom "/" class while the real weight class still said "none posted".
    # Attach by the category label the bout itself prints, then by fighter.
    for b in bouts:
        if b["poule"] and POULE_PHASE.search(b["phase"] or "poule"):
            continue
        key = (by_label.get(norm(b["category"]))
               or cat_of_fighter.get(norm(b["red"]))
               or cat_of_fighter.get(norm(b["blue"])))
        if key is None:
            key = f'{b["agecat"]}/{b["weightcat"]}'
            cats.setdefault(key, {"key": key, **parse_category(b["category"]),
                                  "poules": {}, "knockout": []})
        rec = record(b, key)
        # knockout bouts have no scoresheet: give them the same shape as poule
        # bouts so the page never has to test for missing fields
        rec.update({"red_points": "", "blue_points": "", "decided": False,
                    "winner": "", "inferred": False})
        cats[key]["knockout"].append(rec)

    for key, c in cats.items():
        agecat, weightcat = key.split("/")
        for name, p in c["poules"].items():
            src = poules.get((agecat, weightcat, name))
            # The scoresheet is the fallback for a poule bout the listing has
            # not yet scored: 0-0 means unfought, anything else means decided,
            # higher points wins. It used to be the only source, on the belief
            # that the bout list's own result line never changed - it does, and
            # reading it is now the primary path.
            by_pair = {}
            for pair in (src or {}).get("pairs", []):
                by_pair[frozenset((norm(pair["red"]), norm(pair["blue"])))] = pair
            for b in p["bouts"]:
                pair = by_pair.get(frozenset((norm(b["red"]), norm(b["blue"]))))
                b["red_points"] = b["blue_points"] = ""
                b["decided"] = False
                b["winner"] = ""
                if b["reported"]:
                    # the bout list now states the outcome itself; the
                    # scoresheet is a second opinion, not the only one
                    b["red_points"], b["blue_points"] = b["rp"], b["bp"]
                    b["decided"], b["winner"] = True, b["reported"]
                    continue
                if not pair:
                    continue
                # the pair is stored red-corner-first as the poule sheet has it,
                # which is not necessarily this bout's corner assignment
                same = norm(pair["red"]) == norm(b["red"])
                rp = pair.get("red_points" if same else "blue_points", "")
                bp = pair.get("blue_points" if same else "red_points", "")
                b["red_points"], b["blue_points"] = rp, bp
                try:
                    ri, bi = int(rp or 0), int(bp or 0)
                except ValueError:
                    continue
                if ri or bi:
                    b["decided"] = True
                    b["winner"] = ("red" if ri > bi else
                                   "blue" if bi > ri else "")
            p["final"] = bool(src and src["standings_final"])
            totals = (src or {}).get("totals") or {}
            order = (src or {}).get("fighters") or []
            # Draw order first; the site's own scoresheet supplies the totals.
            seen = {}
            for pair in (src or {}).get("pairs", []):
                for corner in ("red", "blue"):
                    seen.setdefault(norm(pair[corner]),
                                    (pair[corner], pair[f"{corner}_country"]))
            table = []
            for who in order or [v[0] for v in seen.values()]:
                nm, ctry = seen.get(norm(who), (who, country.get(norm(who), "")))
                cell = totals.get(who) or {}
                table.append({
                    "name": nm, "country": ctry,
                    "points": cell.get("points", ""),
                    "warnings": cell.get("warnings", ""),
                })
            p["fighters"] = table
            p["bouts"].sort(key=lambda x: (x["date"], x["time"].zfill(5)))
        c["poules"] = [c["poules"][k] for k in sorted(c["poules"])]
        c["knockout"].sort(key=lambda x: (x["date"], x["time"].zfill(5)))

    # --- knockout results ------------------------------------------------
    # The bout list states the outcome beside each corner, so a knockout bout
    # is normally read, not deduced. Where the source has posted nothing yet,
    # the one remaining clue is who turns up in the NEXT round: whoever appears
    # there won. That is an inference, never a reported result, and is flagged
    # as such on the page. It was once the only path, which is why the finals -
    # with no round after them - stayed blank for five days after they were
    # decided; reading the corners is what fixed that.
    ROUND_ORDER = ["1/16", "1/8", "1/4", "1/2", "finale", "final"]

    def round_rank(phase):
        pl = (phase or "").strip().lower()
        for i, name in enumerate(ROUND_ORDER):
            if name in pl:
                return i
        if re.search(r"quart", pl):   return 2
        if re.search(r"demi|semi", pl): return 3
        if re.search(r"bronze|3e|3\u00e8|third", pl): return 3.5
        return None

    for c in cats.values():
        ko = c["knockout"]
        if not ko:
            continue
        # who appears in each round, by normalised name
        seen = {}
        for b in ko:
            r = round_rank(b["phase"])
            if r is None:
                continue
            seen.setdefault(r, set()).update((norm(b["red"]), norm(b["blue"])))
        rounds = sorted(seen)
        for b in ko:
            b["inferred"] = False
            if b["reported"]:
                b["decided"], b["winner"] = True, b["reported"]
                b["red_points"], b["blue_points"] = b["rp"], b["bp"]
                continue
            r = round_rank(b["phase"])
            if r is None:
                continue
            later = [x for x in rounds if x > r]
            if not later:
                continue
            # a bout is only readable once the NEXT round exists and names
            # exactly one of its two fighters
            names = set()
            for x in later:
                names |= seen[x]
            red_on, blue_on = norm(b["red"]) in names, norm(b["blue"]) in names
            if red_on == blue_on:        # both or neither - says nothing
                continue
            b["decided"] = True
            b["inferred"] = True
            b["winner"] = "red" if red_on else "blue"

    def order(c):
        return (0 if c["gender"] == "Men" else 1 if c["gender"] == "Women" else 2,
                1 if c["over"] else 0, c["kg"] if c["kg"] is not None else 1e9)

    ordered = sorted(cats.values(), key=order)

    n = 0
    for c in ordered:
        for pl in c["poules"]:
            for b in pl["bouts"]:
                n += 1; b["id"] = f"b{n}"
        for b in c["knockout"]:
            n += 1; b["id"] = f"b{n}"

    flat = []
    for c in ordered:
        for p in c["poules"]:
            for b in p["bouts"]:
                flat.append(b)
        flat += c["knockout"]
    flat.sort(key=lambda b: (b["date"], b["time"].zfill(5), b["ring"]))

    n_fighters = len({norm(b["red"]) for b in bouts} | {norm(b["blue"]) for b in bouts})
    return {
        "fetched_at": data["fetched_at"],
        "changed_at": data.get("changed_at") or data["fetched_at"],
        "venue_tz": data.get("venue_tz") or "",
        "venue_tz_label": data.get("venue_tz_label") or "",
        "source": data["source"],
        "days": data["days"],
        "rings": data["rings"],
        "categories": ordered,
        "bouts": flat,
        "warnings": data.get("warnings", []),
        "schedule_changes": data.get("schedule_changes", []),
        "stats": {
            "bouts": len(flat),
            "results": sum(1 for b in flat if b.get("decided")),
            "poules": sum(len(c["poules"]) for c in ordered),
            "knockout": sum(len(c["knockout"]) for c in ordered),
            "classes": len(ordered),
            "fighters": n_fighters,
            "countries": len(data["countries"]),
        },
    }


HTML = """<title>Assaut Worlds Ringside</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --paper:#f7f4f0; --surface:#fffdfb; --sunk:#efe9e3;
  --ink:#1b1a19; --ink-2:#54514e; --ink-3:#8a8580;
  --rule:#ded6ce; --rule-2:#eae3dc;
  --red:#b0282c; --red-soft:#f6e6e4;
  --blue:#1d4e93; --blue-soft:#e3eaf5;
  --live:#a8690a; --live-soft:#f8eeda;
  --done:#2b7350; --done-soft:#e2efe7;
  --focus:#1d4e93;
  --shadow:0 1px 2px rgba(60,40,25,.06),0 6px 18px rgba(60,40,25,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#141416; --surface:#1c1c1f; --sunk:#242427;
  --ink:#ece9e6; --ink-2:#a8a29c; --ink-3:#767069;
  --rule:#33322f; --rule-2:#28282a;
  --red:#e8706e; --red-soft:#38201f;
  --blue:#7aa6e8; --blue-soft:#1b2536;
  --live:#e0a63c; --live-soft:#332715;
  --done:#5fb98a; --done-soft:#16291f;
  --focus:#7aa6e8;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.3);
}}
:root[data-theme="dark"]{
  --paper:#141416; --surface:#1c1c1f; --sunk:#242427;
  --ink:#ece9e6; --ink-2:#a8a29c; --ink-3:#767069;
  --rule:#33322f; --rule-2:#28282a;
  --red:#e8706e; --red-soft:#38201f;
  --blue:#7aa6e8; --blue-soft:#1b2536;
  --live:#e0a63c; --live-soft:#332715;
  --done:#5fb98a; --done-soft:#16291f;
  --focus:#7aa6e8;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.3);
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px;line-height:1.5;-webkit-text-size-adjust:100%}
h1,h2,h3,h4{font-family:Archivo,"IBM Plex Sans",sans-serif;margin:0;
  text-wrap:balance;letter-spacing:-.015em}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}

/* --- masthead ------------------------------------------------------- */
header{border-bottom:1px solid var(--rule);background:var(--surface)}
.mast{display:flex;flex-wrap:wrap;gap:14px 20px;align-items:flex-end;
  padding:22px 0 18px}
.mast h1{font-size:clamp(21px,4.4vw,29px);font-weight:700;line-height:1.05}
.mast .sub{color:var(--ink-2);font-size:12.5px;margin-top:5px;
  letter-spacing:.06em;text-transform:uppercase}
.freshness{margin-left:auto;display:flex;flex-direction:column;
  align-items:flex-start;gap:4px;font-size:12px;color:var(--ink-2);max-width:270px}
#changed{font-weight:600;color:var(--ink)}
#tznote{color:var(--ink-3);font-size:11.5px;line-height:1.35}
.bout .clock small{display:block;color:var(--ink-3);font-size:10px;font-weight:400;
  letter-spacing:.02em}
.stamp{display:inline-flex;align-items:center;gap:7px;font-weight:600;
  padding:4px 10px;border-radius:999px;background:var(--done-soft);
  color:var(--done);font-size:12px}
.stamp.stale{background:var(--live-soft);color:var(--live)}
.stamp .dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.figures{display:flex;gap:0;flex-wrap:wrap;border-top:1px solid var(--rule-2);
  padding:12px 0 4px;margin-top:2px}
.fig{padding-right:26px;margin-right:26px;border-right:1px solid var(--rule-2)}
.fig:last-child{border-right:0}
.fig b{font-family:Archivo,sans-serif;font-size:19px;font-weight:700;display:block;
  font-variant-numeric:tabular-nums}
.fig span{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3)}

/* --- controls ------------------------------------------------------- */
.bar{position:sticky;top:0;z-index:30;background:var(--surface);
  border-bottom:1px solid var(--rule);padding:9px 0}
.bar .wrap{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tabs{display:flex;background:var(--sunk);border-radius:9px;padding:3px;gap:2px}
.tabs button{appearance:none;border:0;background:none;cursor:pointer;
  font:600 13px/1 Archivo,sans-serif;color:var(--ink-2);
  padding:8px 13px;border-radius:6px;white-space:nowrap}
.tabs button[aria-selected="true"]{background:var(--surface);color:var(--ink);
  box-shadow:var(--shadow)}
input[type=search]{flex:1;min-width:150px;appearance:none;font:400 14px/1 inherit;
  padding:9px 12px;border:1px solid var(--rule);border-radius:9px;
  background:var(--paper);color:var(--ink)}
input[type=search]::placeholder{color:var(--ink-3)}
.filt{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;
  color:var(--ink-2);white-space:nowrap;cursor:pointer;user-select:none;
  padding:8px 11px;border:1px solid var(--rule);border-radius:9px;background:var(--paper)}
.filt input{accent-color:var(--focus);margin:0;width:14px;height:14px}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}

/* --- generic -------------------------------------------------------- */
main{padding:22px 0 60px}
.view[hidden]{display:none}
.dayhead{display:flex;align-items:baseline;gap:12px;margin:26px 0 12px}
.dayhead:first-child{margin-top:4px}
.dayhead h2{font-size:16px;font-weight:700}
.dayhead .n{font-size:12px;color:var(--ink-3);letter-spacing:.05em;
  text-transform:uppercase}
.rings{display:grid;gap:14px;grid-template-columns:1fr}
@media(min-width:760px){.rings{grid-template-columns:repeat(3,1fr)}}
.ring{background:var(--surface);border:1px solid var(--rule);border-radius:12px;
  overflow:hidden}
.ring>h3{display:flex;justify-content:space-between;align-items:center;
  padding:10px 14px;font-size:12px;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;background:var(--sunk);border-bottom:1px solid var(--rule)}
.ring>h3 em{font-style:normal;color:var(--ink-3);font-weight:500;letter-spacing:0;
  text-transform:none;font-size:11.5px}

/* --- bout row ------------------------------------------------------- */
.bout{display:grid;grid-template-columns:52px 1fr;gap:0 12px;
  padding:10px 14px;border-top:1px solid var(--rule-2);align-items:start}
.ring .bout:first-of-type{border-top:0}
.bout .clock{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;
  font-size:13px;font-weight:500;color:var(--ink-2);padding-top:1px}
.bout .meta{font-size:11px;color:var(--ink-3);letter-spacing:.02em;
  display:flex;gap:7px;align-items:flex-start}
.bout .meta .tags{display:flex;gap:7px;flex-wrap:wrap;align-items:center;flex:1;min-width:0}
.corner{display:flex;gap:8px;align-items:baseline;margin-top:3px;font-size:14px}
.corner .tag{width:9px;height:9px;border-radius:2px;flex:none;
  transform:translateY(-1px)}
.corner.r .tag{background:var(--red)} .corner.b .tag{background:var(--blue)}
.corner .who{font-weight:500}
.corner.r .who{color:var(--red)} .corner.b .who{color:var(--blue)}
.corner .who{min-width:0}
.corner .ctry{color:var(--ink-3);font-size:11.5px;margin-left:auto;flex:none;
  max-width:40%;padding-left:10px;text-align:right;line-height:1.3}
.corner .pts{font-size:9.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--done);background:var(--done-soft);
  padding:2px 5px;border-radius:4px;margin-left:8px;flex:none}
.corner.won .who{font-weight:700}
.corner.won .pts{color:var(--done)}
.corner.won .tag{box-shadow:0 0 0 2px var(--done)}
.bout.pin{background:var(--live-soft)}
.bout.pin .clock{color:var(--live);font-weight:600}
.chip{display:inline-block;font-size:10px;font-weight:600;letter-spacing:.06em;
  text-transform:uppercase;padding:2px 6px;border-radius:4px;
  background:var(--sunk);color:var(--ink-3)}
.chip.done{background:var(--done-soft);color:var(--done)}
.chip.inf{background:var(--blue-soft);color:var(--blue)}
.corner .pts.inf{background:var(--blue-soft);color:var(--blue)}
.corner.won .pts.inf{color:var(--blue)}
.chip.next{background:var(--live-soft);color:var(--live)}
.result{font-size:12px;color:var(--done);margin-top:3px}
.star{appearance:none;border:0;background:none;cursor:pointer;padding:0 0 0 8px;
  color:var(--ink-3);font-size:14px;line-height:1;margin-left:auto}
.star[aria-pressed="true"]{color:var(--live)}

/* --- where we are now ----------------------------------------------- */
.now{display:grid;gap:12px;grid-template-columns:1fr;margin-bottom:6px}
@media(min-width:760px){.now{grid-template-columns:repeat(3,1fr)}}
.nowcard{background:var(--surface);border:1px solid var(--rule);border-radius:12px;
  padding:12px 14px 13px}
.nowcard h3{font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-3);display:flex;justify-content:space-between;margin-bottom:9px}
.slot{padding:7px 0;border-top:1px solid var(--rule-2)}
.slot:first-of-type{border-top:0;padding-top:0}
.slot .lab{font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  font-weight:600;color:var(--ink-3);display:flex;gap:7px;align-items:center}
.slot.due .lab{color:var(--live)}
.slot.brk .lab{color:var(--blue)}
.slot.brk{background:var(--blue-soft);margin:0 -14px;padding:8px 14px}
.slot .pair{font-size:13.5px;line-height:1.4;margin-top:2px}
.slot .pair .r{color:var(--red)} .slot .pair .b{color:var(--blue)}
.slot .pair .v{color:var(--ink-3);font-size:11px;margin:0 5px}
.slot .when{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--ink-3)}
.slot .sc{font-weight:600;color:var(--done);font-size:11px;letter-spacing:0;
  text-transform:none;margin-left:auto;text-align:right}
.lag{font-size:11.5px;color:var(--live);background:var(--live-soft);
  border-radius:7px;padding:6px 9px;margin-top:9px;line-height:1.4}
.nowhead{display:flex;align-items:baseline;gap:12px;margin:4px 0 12px}
.nowhead h2{font-size:16px;font-weight:700}
.nowhead .n{font-size:12px;color:var(--ink-3)}

/* --- weight classes ------------------------------------------------- */
.classes{display:grid;gap:14px;grid-template-columns:1fr}
@media(min-width:700px){.classes{grid-template-columns:1fr 1fr}}
details.cls{background:var(--surface);border:1px solid var(--rule);
  border-radius:12px;overflow:hidden}
details.cls>summary{list-style:none;cursor:pointer;padding:13px 15px;
  display:flex;align-items:center;gap:10px}
details.cls>summary::-webkit-details-marker{display:none}
details.cls>summary h3{font-size:16px;font-weight:700}
details.cls>summary .n{margin-left:auto;font-size:11.5px;color:var(--ink-3);
  text-align:right;line-height:1.35}
details.cls>summary .caret{color:var(--ink-3);font-size:11px;transition:transform .15s}
details.cls[open]>summary .caret{transform:rotate(90deg)}
details.cls[open]>summary{border-bottom:1px solid var(--rule)}
.clsbody{padding:4px 15px 15px}
.poule{border-top:1px solid var(--rule-2);padding:14px 0 4px}
.poule:first-child{border-top:0}
.poule h4{font-size:12px;letter-spacing:.09em;text-transform:uppercase;
  display:flex;align-items:center;gap:9px;margin-bottom:9px}
table.stand{width:100%;border-collapse:collapse;font-size:13.5px}
table.stand th{font:600 10.5px/1 "IBM Plex Sans",sans-serif;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ink-3);text-align:right;padding:0 0 5px}
table.stand th:first-child{text-align:left}
table.stand td{padding:5px 0;border-top:1px solid var(--rule-2);text-align:right;
  font-variant-numeric:tabular-nums}
table.stand td:first-child{text-align:left}
table.stand td.ctry{color:var(--ink-3);font-size:11.5px;text-align:left;
  width:1%;white-space:nowrap;padding-left:10px}
table.stand td.num{font-family:"IBM Plex Mono",monospace;width:44px;color:var(--ink-2)}
.fixtures{margin-top:9px;font-size:13px}
.fx{display:flex;gap:8px;align-items:baseline;padding:4px 0;
  border-top:1px solid var(--rule-2);flex-wrap:wrap}
.fx .clock{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3);
  white-space:nowrap}
.fx .r{color:var(--red)} .fx .b{color:var(--blue)} .fx .v{color:var(--ink-3);font-size:11px}
.fx .score{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:600;
  color:var(--done);margin-left:auto}
.note{font-size:12.5px;color:var(--ink-2);background:var(--sunk);
  border-radius:9px;padding:11px 13px;margin-top:14px}
.note b{color:var(--ink);font-weight:600}

/* --- fighters ------------------------------------------------------- */
.people{display:grid;gap:9px;grid-template-columns:1fr}
@media(min-width:640px){.people{grid-template-columns:1fr 1fr}}
.person{background:var(--surface);border:1px solid var(--rule);border-radius:10px;
  padding:11px 13px;display:flex;align-items:center;gap:10px}
.person .nm{font-weight:500}
.person .cy{color:var(--ink-3);font-size:12px}
.person .cl{margin-left:auto;font-size:11.5px;color:var(--ink-3);text-align:right}
.empty{color:var(--ink-3);font-size:13.5px;padding:26px 0;text-align:center}

/* --- detail sheet --------------------------------------------------- */
.sheet{position:fixed;inset:0;z-index:60;background:rgba(20,16,12,.45);
  display:flex;align-items:flex-end;justify-content:center;padding:0}
@media(min-width:640px){.sheet{align-items:center;padding:24px}}
.sheetcard{position:relative;background:var(--surface);width:100%;max-width:560px;
  max-height:88vh;overflow-y:auto;border:1px solid var(--rule);
  border-radius:16px 16px 0 0;padding:20px 18px 26px;box-shadow:var(--shadow)}
@media(min-width:640px){.sheetcard{border-radius:16px}}
#sheetclose{position:absolute;top:12px;right:12px;appearance:none;border:0;
  background:var(--sunk);color:var(--ink-2);width:30px;height:30px;border-radius:50%;
  cursor:pointer;font-size:13px;line-height:1}
.sheet h3{font-size:19px;font-weight:700;padding-right:34px}
.sheet .sub{color:var(--ink-2);font-size:12.5px;margin-top:3px}
.sheet h4{font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-3);margin:20px 0 8px}
.sheet .rec{display:flex;gap:8px;margin-top:12px}
.sheet .rec div{flex:1;background:var(--sunk);border-radius:9px;padding:9px 11px}
.sheet .rec b{font-family:Archivo,sans-serif;font-size:18px;display:block;
  font-variant-numeric:tabular-nums}
.sheet .rec span{font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink-3)}
.sheet .bl{border-top:1px solid var(--rule-2);padding:8px 0;font-size:13.5px}
.sheet .bl .when{font-family:"IBM Plex Mono",monospace;font-size:11.5px;
  color:var(--ink-3)}
.sheet .bl .r{color:var(--red)} .sheet .bl .b{color:var(--blue)}
.sheet .bl .w{font-weight:700}
.sheet .bl .out{font-size:11.5px;margin-top:2px}
.sheet .bl .out.win{color:var(--done);font-weight:600}
.sheet .bl .out.lose{color:var(--ink-3)}
table.stand td.rk{width:22px;color:var(--ink-3);font-size:11.5px;text-align:left}
tr.me td{background:var(--live-soft)}
.tap{cursor:pointer}
.bout.tap:hover,.person.tap:hover{background:var(--sunk)}

/* --- provenance ----------------------------------------------------- */
footer{border-top:1px solid var(--rule);margin-top:40px;padding:22px 0 46px;
  font-size:12.5px;color:var(--ink-2)}
footer h4{font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:8px}
footer ul{margin:0;padding-left:18px} footer li{margin:3px 0}
footer a{color:var(--focus)}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<header><div class="wrap">
  <div class="mast">
    <div>
      <h1>World Championship<br>Savate Assaut</h1>
      <div class="sub" id="subline"></div>
    </div>
    <div class="freshness">
      <span class="stamp" id="stamp"><span class="dot"></span><span id="stamptext">—</span></span>
      <span id="changed"></span>
      <span id="tznote"></span>
    </div>
  </div>
  <div class="figures" id="figures"></div>
</div></header>

<div class="bar"><div class="wrap">
  <div class="tabs" role="tablist">
    <button role="tab" data-view="schedule" aria-selected="true">Schedule</button>
    <button role="tab" data-view="classes" aria-selected="false">Weight classes</button>
    <button role="tab" data-view="people" aria-selected="false">Fighters</button>
  </div>
  <input type="search" id="q" placeholder="Search fighter, country or class" autocomplete="off">
  <label class="filt"><input type="checkbox" id="hidedone"> Hide decided</label>
</div></div>

<main class="wrap">
  <section class="view" id="v-schedule"></section>
  <section class="view" id="v-classes" hidden></section>
  <section class="view" id="v-people" hidden></section>
</main>

<div id="sheet" class="sheet" hidden role="dialog" aria-modal="true" aria-label="Details">
  <div class="sheetcard">
    <button id="sheetclose" aria-label="Close">&#10005;</button>
    <div id="sheetbody"></div>
  </div>
</div>

<footer class="wrap">
  <h4>Where these figures come from</h4>
  <ul id="prov"></ul>
</footer>

<script id="payload" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById("payload").textContent);
var $ = function(s){ return document.querySelector(s); };
var esc = function(s){ var d=document.createElement("div"); d.textContent=s==null?"":s; return d.innerHTML; };
var fold = function(s){ return (s||"").normalize("NFD").replace(/[\\u0300-\\u036f]/g,"").replace(/\\s+/g," ").trim().toLowerCase(); };

/* pinned fighters live only in this browser */
var PIN="assaut.pins", pins=new Set();
try{ pins=new Set(JSON.parse(localStorage.getItem(PIN)||"[]")); }catch(e){}
function savePins(){ try{ localStorage.setItem(PIN, JSON.stringify([].concat(Array.from(pins)))); }catch(e){} }
function isPinned(b){ return pins.has(fold(b.red)) || pins.has(fold(b.blue)); }

/* ---- freshness ---------------------------------------------------- */
var fetched = new Date(D.fetched_at);
var changed = new Date(D.changed_at);
function since(d){
  var m = Math.max(0, Math.round((Date.now()-d.getTime())/60000));
  return m<1 ? "just now" : m<60 ? (m+" min ago")
    : m<1440 ? (Math.round(m/60)+" h ago") : (Math.round(m/1440)+" d ago");
}
function hhmm(d){ return d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}); }
function ago(){
  var mins = Math.max(0, Math.round((Date.now()-fetched.getTime())/60000));
  /* Two different facts, kept apart on purpose: when this page last LOOKED at
     the organisers' site, and when what it found last CHANGED. A quiet source
     should read as quiet, not as a broken page. */
  $("#stamptext").textContent = "Checked "+since(fetched);
  /* amber means "we have stopped checking", never "the source is quiet" */
  $("#stamp").classList.toggle("stale", mins>40);
  $("#changed").textContent = (changed.getTime()===fetched.getTime() && mins<2)
    ? "Data just changed"
    : "No change since "+hhmm(changed)+" \u00b7 "+since(changed);
}
ago(); setInterval(ago, 30000);

/* The organisers publish bare clock times; D.venue_tz says which zone they are
   in. Where the viewer's device agrees, times are shown untouched. Where it does
   not, the venue clock stays primary and the device time is added beneath it -
   the venue clock is the one called out at the ring. */
var VTZ = D.venue_tz || "";
var here = (Intl.DateTimeFormat().resolvedOptions().timeZone) || "";
function tzOffset(d, tz){
  var f = new Intl.DateTimeFormat("en-US",{timeZone:tz,hour12:false,year:"numeric",
    month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit"});
  var p={}; f.formatToParts(d).forEach(function(x){ p[x.type]=x.value; });
  return Date.UTC(+p.year,+p.month-1,+p.day,+p.hour%24,+p.minute,+p.second) - d.getTime();
}
function instantOf(date, time){
  var guess = new Date(date+"T"+time+":00Z");
  return new Date(guess.getTime() - tzOffset(guess, VTZ));
}
var SAME = true, TZLABEL = "";
try{
  if(VTZ){
    var probe = instantOf(D.days[0], "12:00");
    /* "Central European Time" reads better at a venue than "GMT+2"; fall back
       to the offset form where the browser has no generic name for the zone. */
    /* a stated name beats the browser's guess: Intl calls Europe/Paris
       "France Time", which is not what anyone at the venue says. */
    TZLABEL = D.venue_tz_label || ["shortGeneric","short"].map(function(style){
      try{
        return new Intl.DateTimeFormat([], {timeZone:VTZ, timeZoneName:style})
          .formatToParts(probe).filter(function(x){ return x.type==="timeZoneName"; })
          .map(function(x){ return x.value; })[0];
      }catch(e){ return ""; }
    }).filter(Boolean)[0] || VTZ;
    TZLABEL = TZLABEL || VTZ;
    SAME = tzOffset(probe, VTZ) === tzOffset(probe, here);
  }
}catch(e){ SAME = true; }
function localClock(b){
  if(SAME || !VTZ) return "";
  try{ return instantOf(b.date, b.time)
    .toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}); }catch(e){ return ""; }
}
$("#tznote").textContent = !VTZ ? "Times as published by the organisers."
  : SAME ? ("All times "+TZLABEL+" \u2014 same as this device.")
  : ("Bout times are venue time ("+TZLABEL+"); your device time is shown beneath each.");

$("#subline").textContent = D.days.join("  \\u2013  ") + "  \\u00b7  " + D.rings.length + " rings";
var S=D.stats;
$("#figures").innerHTML = [
  [S.bouts,"bouts"],[S.classes,"weight classes"],[S.poules,"poules"],
  [S.fighters,"fighters"],[S.countries,"countries"],
  [S.results+" / "+S.bouts,"bouts decided"]
].map(function(f){ return '<div class="fig"><b>'+f[0]+'</b><span>'+f[1]+'</span></div>'; }).join("");

/* ---- shared bits --------------------------------------------------- */
function catOf(k){ for(var i=0;i<D.categories.length;i++){ if(D.categories[i].key===k) return D.categories[i]; } return null; }
function boutMatches(b,q){
  if(!q) return true;
  var c=catOf(b.cat)||{};
  return [b.red,b.blue,b.red_country,b.blue_country,c.title,c.label,b.poule,b.ring]
    .some(function(x){ return fold(x).indexOf(q)>=0; });
}
function starBtn(b){
  var on = isPinned(b);
  return '<button class="star" aria-pressed="'+on+'" data-pin="'+esc(fold(b.red))+'|'+esc(fold(b.blue))+'" '+
         'title="Follow these fighters">'+(on?"\\u2605":"\\u2606")+'</button>';
}
/* The source names knockout rounds in French shorthand ("1/4"). A pool bout
   has a letter; a knockout bout has none, so it names its round instead of
   printing a bare "Poule". */
var ROUNDS = [[/1\\/16/, "Round of 32"], [/1\\/8|huiti/i, "Round of 16"],
              [/1\\/4|quart/i, "Quarter-final"], [/1\\/2|demi|semi/i, "Semi-final"],
              [/bronze|third|3\\s*[eè]/i, "Third place"],
              [/^\\s*finale?\\s*$/i, "Final"], [/rep[eê]chage/i, "Repechage"]];
function roundOf(b){
  if(b.poule) return "Poule "+b.poule;
  var ph = b.phase || "";
  for(var i=0;i<ROUNDS.length;i++) if(ROUNDS[i][0].test(ph)) return ROUNDS[i][1];
  return ph || "Knockout";
}
function corner(b, side){
  var who  = side==="r" ? b.red : b.blue;
  var ctry = side==="r" ? b.red_country : b.blue_country;
  var won  = b.decided && b.winner===side;
  /* The source publishes poule classification points (3 for a win, 1 for a
     loss), never a bout score. Printing "3-1" beside the names reads like a
     scoreline and tells the reader something the organisers never said, so
     the outcome is shown as what it actually is: who won. */
  return '<div class="corner '+side+(won?" won":"")+'"><span class="tag"></span>'+
    '<span class="who">'+esc(who)+'</span>'+
    (won ? '<span class="pts'+(b.inferred?" inf":"")+'">'+
           (b.inferred?"advanced":"won"+esc(manner(b)))+'</span>' : '')+
    '<span class="ctry">'+esc(ctry)+'</span></div>';
}
function boutRow(b, showCat){
  var c=catOf(b.cat)||{}, tags=[];
  if(showCat!==false) tags.push('<span>'+esc(c.title||c.label)+'</span>');
  tags.push('<span>'+esc(roundOf(b))+'</span>');
  var late = !b.decided && whenOf(b) < Date.now();
  tags.push('<span class="chip'+(b.inferred?" inf":b.decided?" done":late?" next":"")+'">'+
    (b.inferred?"Advanced":b.decided?"Decided":late?"No result yet":"Scheduled")+'</span>');
  var loc = localClock(b);
  return '<div class="bout tap'+(isPinned(b)?" pin":"")+'" data-bout="'+esc(b.id)+'" '+
    'role="button" tabindex="0">'+
    '<div class="clock">'+esc(b.time)+(loc?'<small>'+esc(loc)+' here</small>':'')+
    '</div><div>'+
      '<div class="meta"><span class="tags">'+tags.join("")+'</span>'+starBtn(b)+'</div>'+
      corner(b,"r")+corner(b,"b")+
      (b.result?'<div class="result">'+esc(b.result)+'</div>':'')+
    '</div></div>';
}

/* ---- where we are now ---------------------------------------------
   Two different answers, shown side by side on purpose:
   the CLOCK says which bout is due, the RESULTS say what has been posted.
   The organisers post results in batches, so the ring routinely runs ahead
   of the scoresheet. Collapsing the two into one "current bout" would be a
   guess; showing both is what is actually known. */
function whenOf(b){ try{ return instantOf(b.date, b.time).getTime(); }catch(e){ return 0; } }

function pairHTML(b){
  return '<span class="r">'+esc(b.red)+'</span><span class="v">v</span>'+
         '<span class="b">'+esc(b.blue)+'</span>';
}
function slot(cls, label, b, extra){
  var c = catOf(b.cat)||{};
  return '<div class="slot'+(cls?" "+cls:"")+'">'+
    '<div class="lab">'+esc(label)+'<span class="when">'+esc(b.time)+'</span>'+
    (extra||'')+'</div>'+
    '<div class="pair">'+pairHTML(b)+'</div>'+
    '<div class="when">'+esc(c.title||"")+' \u00b7 '+esc(roundOf(b))+'</div></div>';
}

function renderNow(){
  var now = Date.now();
  var today = D.days.filter(function(d){
    var b = D.bouts.filter(function(x){ return x.date===d; });
    if(!b.length) return false;
    var first = whenOf(b[0]), last = whenOf(b[b.length-1]);
    return now >= first - 3*3600e3 && now <= last + 3*3600e3;
  })[0];

  if(!today){
    var upcoming = D.bouts.filter(function(b){ return whenOf(b) > now; });
    if(!upcoming.length) return '<div class="note"><b>The championship is over.</b> '+
      'Every bout below is in the past; results are as the organisers last posted them.</div>';
    var d0 = new Date(upcoming[0].date+"T12:00:00");
    return '<div class="note"><b>Not under way yet.</b> First bouts are on '+
      esc(d0.toLocaleDateString([], {weekday:"long", day:"numeric", month:"long"}))+
      ', from '+esc(upcoming[0].time)+'.</div>';
  }

  var cards = D.rings.map(function(ring){
    var ms = D.bouts.filter(function(b){ return b.date===today && b.ring===ring; })
                    .sort(function(a,b){ return whenOf(a)-whenOf(b); });
    if(!ms.length) return '';
    var decided = ms.filter(function(b){ return b.decided; });

    /* Where the SCHEDULE has got to: the latest slot that has come round,
       decided or not. Taking the oldest bout with no posted result instead
       pointed at something fought an hour ago, because results are posted
       late - that is a backlog, not the current bout. */
    var past = ms.filter(function(b){ return whenOf(b) <= now; });
    var atNow = past.length ? past[past.length-1] : null;
    var next  = ms.filter(function(b){ return whenOf(b) > now; });

    /* Slots that have come and gone with nothing posted. Not "in the ring" -
       either fought and unposted, or the ring is behind. */
    var awaiting = ms.filter(function(b){
      return !b.decided && atNow && whenOf(b) < whenOf(atNow); });

    /* The timetable runs on a steady 13-minute cadence with deliberate gaps -
       a 73-minute lunch break across all three rings today. Inside such a gap
       the last slot that came round is NOT the current bout, so say what is
       actually happening: nothing, until the ring restarts. */
    var GAP = 25*60e3;
    var inBreak = atNow && next.length &&
      (whenOf(next[0]) - whenOf(atNow) >= GAP) &&
      (now - whenOf(atNow) >= 15*60e3) && (whenOf(next[0]) - now > 60e3);

    var body = "";
    if(inBreak){
      var mins = Math.round((whenOf(next[0]) - now)/60000);
      body += '<div class="slot brk"><div class="lab">Scheduled break'+
        '<span class="when">restarts '+esc(next[0].time)+'</span></div>'+
        '<div class="when">No bouts scheduled for another '+mins+' min.</div></div>';
    }
    if(atNow && !inBreak){
      body += slot(atNow.decided?"":"due", "On the clock now", atNow,
        atNow.decided ? '<span class="sc">'+
          esc(atNow.winner==="red"?atNow.red:
              atNow.winner==="blue"?atNow.blue:"drawn")+
          (atNow.winner?' won':'')+'</span>' : '');
    }
    if(next.length) body += slot("", (atNow && !inBreak)?"Next up":
                                     inBreak?"First after the break":"First up", next[0]);
    if(next.length>1) body += slot("", "After that", next[1]);
    if(!atNow && !next.length)
      body += '<div class="slot"><div class="lab">Finished</div>'+
              '<div class="when">No bouts left on this ring today.</div></div>';

    if(awaiting.length){
      body += '<div class="slot"><div class="lab">Past their slot, no result'+
        '<span class="when">'+awaiting.length+' bout'+(awaiting.length===1?"":"s")+
        '</span></div><div class="when">'+
        awaiting.map(function(b){ return esc(b.time); }).join(", ")+
        '</div></div>';
    }

    var last = decided[decided.length-1];
    if(last) body += slot("", "Last posted", last,
      '<span class="sc">'+esc(last.winner==="red"?last.red:
                             last.winner==="blue"?last.blue:"drawn")+
      (last.winner?' won':'')+'</span>');

    /* Two equally plausible explanations for a slot with no result, and the
       source distinguishes neither: the ring is running late, or the bout was
       fought and the scoresheet has not caught up. Saying "most likely fought"
       was wrong - rings here do run behind. State the fact, not a guess. */
    var note = awaiting.length
      ? '<div class="lag">'+awaiting.length+' earlier slot'+
        (awaiting.length===1?" has":"s have")+' passed with no result posted. '+
        'That means either the ring is running behind, or the bout was fought and '+
        'the scoresheet has not caught up \u2014 the source shows only the planned '+
        'time and the posted result, never what is happening in the ring.</div>'
      : "";

    return '<div class="nowcard"><h3>Ring '+esc(ring)+
      '<span>'+decided.length+'/'+ms.length+' decided</span></h3>'+body+note+'</div>';
  }).filter(Boolean).join("");

  var d = new Date(today+"T12:00:00");
  var moved = (D.schedule_changes||[]).length
    ? '<div class="lag" style="margin:0 0 12px"><b>'+D.schedule_changes.length+
      ' bout'+(D.schedule_changes.length===1?"":"s")+' rescheduled</b> since this page '+
      'started watching: '+D.schedule_changes.slice(-3).map(function(c){
        return esc(c.red)+' v '+esc(c.blue)+' moved from '+esc(c.from.time)+
               ' ring '+esc(c.from.ring)+' to '+esc(c.to.time)+' ring '+esc(c.to.ring);
      }).join('; ')+'.</div>'
    : "";
  return '<div class="nowhead"><h2>Where we are</h2><span class="n">'+
    esc(d.toLocaleDateString([], {weekday:"long", day:"numeric", month:"long"}))+
    ' \u00b7 '+hhmm(new Date())+' '+esc(TZLABEL)+'</span></div>'+
    moved+'<div class="now">'+cards+'</div>'+
    '<div class="note"><b>Every time here is the planned time</b>, exactly as the '+
    'organisers published it \u2014 they do not revise it when a ring runs late. '+
    '\u201cOn the clock now\u201d is the slot the timetable has reached, not a bout '+
    'confirmed to be under way, and a bout is only marked decided once a result '+
    'appears on the poule scoresheet.</div>';
}

/* ---- schedule ------------------------------------------------------ */
function renderSchedule(q){
  var out=[], any=false;
  if(!q) out.push(renderNow());
  D.days.forEach(function(day){
    var dayB = D.bouts.filter(function(b){
      /* a decided bout stays visible while it is pinned - following a fighter
         is exactly when you want to see how their earlier bouts went */
      if(hideDone && b.decided && !isPinned(b)) return false;
      return b.date===day && boutMatches(b,q);
    });
    if(!dayB.length) return;
    any=true;
    var d=new Date(day+"T12:00:00");
    out.push('<div class="dayhead"><h2>'+d.toLocaleDateString([], {weekday:"long", day:"numeric", month:"long"})+
      '</h2><span class="n">'+dayB.length+(hideDone?' still to come':' bouts')+
      '</span></div><div class="rings">');
    D.rings.forEach(function(ring){
      var ms = dayB.filter(function(b){ return b.ring===ring; });
      out.push('<div class="ring"><h3>Ring '+esc(ring)+'<em>'+ms.length+
        (hideDone?' to come':' bouts')+'</em></h3>'+
        (ms.length ? ms.map(function(b){ return boutRow(b); }).join("")
                   : '<div class="empty">'+(hideDone?"All decided":"No bouts")+'</div>')+
        '</div>');
    });
    out.push('</div>');
  });
  if(!any) out.push('<div class="empty">Nothing matches \\u201c'+esc(q)+'\\u201d</div>');
  $("#v-schedule").innerHTML = out.join("");
}

/* ---- weight classes ------------------------------------------------ */
function renderClasses(q){
  var out=['<div class="classes">'], any=false;
  D.categories.forEach(function(c){
    var bts = D.bouts.filter(function(b){ return b.cat===c.key && boutMatches(b,q); });
    if(q && !bts.length) return;
    any=true;
    var open = !!q;
    out.push('<details class="cls"'+(open?" open":"")+'><summary><span class="caret">\\u25b8</span>'+
      '<h3>'+esc(c.title)+'</h3><span class="n">'+c.poules.length+' poules<br>'+
      c.poules.reduce(function(n,p){ return n+p.fighters.length; },0)+' fighters</span></summary>'+
      '<div class="clsbody">');
    c.poules.forEach(function(p){
      out.push('<div class="poule"><h4>Poule '+esc(p.name)+
        '<span class="chip'+(p.final?" done":"")+'">'+(p.final?"Final":"Provisional")+'</span></h4>');
      out.push('<table class="stand"><thead><tr><th>Fighter</th><th></th><th title="Poule points: 3 for a win, 1 for a loss">Pts</th><th>Warn</th></tr></thead><tbody>'+
        p.fighters.map(function(f){
          return '<tr><td>'+esc(f.name)+'</td><td class="ctry">'+esc(f.country)+
            '</td><td class="num">'+esc(f.points===""?"\\u2013":f.points)+
            '</td><td class="num">'+esc(f.warnings===""?"\\u2013":f.warnings)+'</td></tr>';
        }).join("")+'</tbody></table>');
      out.push('<div class="fixtures">'+p.bouts.map(function(b){
        return '<div class="fx tap" data-bout="'+esc(b.id)+'" role="button" tabindex="0">'+
          '<span class="clock">'+esc(b.date.slice(5))+' '+esc(b.time)+
          ' \\u00b7 R'+esc(b.ring)+'</span><span class="r">'+esc(b.red)+
          '</span><span class="v">v</span><span class="b">'+esc(b.blue)+'</span>'+
          (b.decided?'<span class="score">'+
            esc(b.winner==="red"?b.red:b.winner==="blue"?b.blue:"drawn")+
            (b.winner?' won'+esc(manner(b)):'')+'</span>':'')+'</div>';
      }).join("")+'</div></div>');
    });
    if(c.knockout.length){
      out.push('<div class="poule"><h4>Knockout</h4>'+
        c.knockout.map(function(b){ return boutRow(b,false); }).join("")+'</div>');
    }else{
      out.push('<div class="note"><b>No knockout bouts published yet.</b> Under the '+
        'FISav 2026 championship rules the pools <b>select the four semi-finalists</b> '+
        'for each category \\u2014 so this class resolves to semi-finals, a final and a '+
        'third-place bout, all of which are always contested. How '+c.poules.length+
        ' pool'+(c.poules.length===1?"":"s")+' reduce to four is not stated in the rules, '+
        'and no draw has been posted, so nothing is guessed here.</div>');
    }
    out.push('</div></details>');
  });
  out.push('</div>');
  $("#v-classes").innerHTML = any ? out.join("")
    : '<div class="empty">Nothing matches \\u201c'+esc(q)+'\\u201d</div>';
}

/* ---- poule ranking -------------------------------------------------
   From the FISav 2026 World Championship Assaut rules, section 2.6.3.
   Pool scale: victory 3, defeat 1, draw 2, abandon/forfeit -1,
   disqualification -3. Ties at the end of a pool break on, in order:
     1) the assaut the tied athletes contested
     2) fewest warnings received
     3) most victories
     4) lightest at the weigh-in
     5) drawing lots
   The first three are computable from what the organisers publish. Weigh-in
   weights are not published, so a tie surviving all three is shown as tied
   rather than ordered on a guess. */
function pouleOf(catKey, name){
  var c = catOf(catKey); if(!c) return null;
  for(var i=0;i<c.poules.length;i++){
    var p=c.poules[i];
    for(var j=0;j<p.fighters.length;j++)
      if(fold(p.fighters[j].name)===fold(name)) return p;
  }
  return null;
}
function ranked(p){
  var rows = p.fighters.map(function(f){
    return {name:f.name, country:f.country,
            pts:parseInt(f.points||"0",10)||0,
            warn:parseInt(f.warnings||"0",10)||0};
  });
  function h2h(a,b){
    for(var i=0;i<p.bouts.length;i++){
      var m=p.bouts[i];
      if(!m.decided || !m.winner) continue;
      var pair=[fold(m.red),fold(m.blue)];
      if(pair.indexOf(fold(a.name))<0 || pair.indexOf(fold(b.name))<0) continue;
      var w=fold(m.winner==="red"?m.red:m.blue);
      return w===fold(a.name) ? -1 : 1;
    }
    return 0;
  }
  function wins(x){
    var n=0;
    for(var i=0;i<p.bouts.length;i++){
      var m=p.bouts[i];
      if(!m.decided || !m.winner) continue;
      if(fold(m.winner==="red"?m.red:m.blue)===fold(x.name)) n++;
    }
    return n;
  }
  rows.forEach(function(r){ r.wins = wins(r); });
  rows.sort(function(a,b){
    if(a.pts!==b.pts) return b.pts-a.pts;
    var d=h2h(a,b); if(d) return d;
    if(a.warn!==b.warn) return a.warn-b.warn;
    if(a.wins!==b.wins) return b.wins-a.wins;   /* criterion 3 */
    return 0;
  });
  function level(a,b){
    return a && b && a.pts===b.pts && h2h(a,b)===0 && a.warn===b.warn
           && a.wins===b.wins;
  }
  var rank=0;
  rows.forEach(function(r,i){
    if(!level(rows[i-1], r)) rank=i+1;
    r.rank = rank;
    /* tied with EITHER neighbour: a fighter level with the field must not be
       shown as 1st just for sorting first. Everyone in a tie group reads "=". */
    r.tied = level(rows[i-1], r) || level(r, rows[i+1]);
  });
  return rows;
}

/* ---- detail sheet -------------------------------------------------- */
var sheet=$("#sheet"), sheetBody=$("#sheetbody");
function closeSheet(){ sheet.hidden=true; }
$("#sheetclose").addEventListener("click", closeSheet);
sheet.addEventListener("click", function(e){ if(e.target===sheet) closeSheet(); });
document.addEventListener("keydown", function(e){ if(e.key==="Escape") closeSheet(); });
function openSheet(html){ sheetBody.innerHTML=html; sheet.hidden=false; sheet.scrollTop=0;
  sheetBody.parentNode.scrollTop=0; }

function standTable(p, highlight){
  return '<table class="stand"><thead><tr><th></th><th>Fighter</th><th></th>'+
    '<th>Pts</th><th>Warn</th></tr></thead><tbody>'+
    ranked(p).map(function(r){
      return '<tr'+(highlight&&fold(r.name)===fold(highlight)?' class="me"':'')+'>'+
        '<td class="rk">'+(r.tied?"=":r.rank)+'</td><td>'+esc(r.name)+'</td>'+
        '<td class="ctry">'+esc(r.country)+'</td>'+
        '<td class="num">'+r.pts+'</td><td class="num">'+r.warn+'</td></tr>';
    }).join("")+'</tbody></table>';
}
/* The loser's points say how the bout ended. 1 is a plain decision. Every -1
   in this competition sits beside exactly three warnings, and the third warning
   disqualifies - so -1 is read as a disqualification, even though the 2026
   scale prints -3 for one. 0 is not on the published scale at all; it appears
   where an athlete did not fight, so it is described that way rather than
   labelled with a rule it does not match. */
function manner(b){
  if(!b.decided || !b.winner || b.inferred) return "";
  var lose = b.winner==="red" ? b.blue_points : b.red_points;
  return lose==="-1" ? " \u2014 opponent disqualified"
       : lose==="0"  ? " \u2014 opponent did not fight" : "";
}
function boutLine(b, who){
  var out="";
  if(b.decided){
    var w = b.winner==="red"?b.red:b.blue;
    var m = manner(b);
    /* the same fact reads differently depending on whose page you are on:
       the loser was disqualified, not their opponent */
    var mine = m.replace(" \\u2014 opponent ", " \\u2014 ");
    if(b.inferred){
      out = who
        ? (fold(w)===fold(who)
            ? '<div class="out win">Advanced \\u2014 named in the next round</div>'
            : '<div class="out lose">Out \\u2014 '+esc(w)+' went through</div>')
        : '<div class="out win">'+esc(w)+' advanced \\u2014 named in the next round</div>';
    } else {
      out = who ? (fold(w)===fold(who)
              ? '<div class="out win">Won'+m+'</div>'
              : '<div class="out lose">Lost to '+esc(w)+mine+'</div>')
            : '<div class="out win">'+esc(w)+' won'+m+'</div>';
    }
  } else {
    out = '<div class="out lose">'+
      (whenOf(b)<Date.now() ? "No result posted yet" : "Not yet fought")+'</div>';
  }
  return '<div class="bl"><div class="when">'+esc(b.date.slice(5))+' \u00b7 '+
    esc(b.time)+' \u00b7 Ring '+esc(b.ring)+'</div>'+
    '<span class="r'+(b.decided&&b.winner==="red"?" w":"")+'">'+esc(b.red)+'</span>'+
    ' <span class="when">v</span> '+
    '<span class="b'+(b.decided&&b.winner==="blue"?" w":"")+'">'+esc(b.blue)+'</span>'+
    out+'</div>';
}
function openBout(id){
  var b=null;
  for(var i=0;i<D.bouts.length;i++) if(D.bouts[i].id===id) b=D.bouts[i];
  if(!b) return;
  var c=catOf(b.cat)||{}, p=pouleOf(b.cat,b.red);
  openSheet('<h3>'+esc(b.red)+' v '+esc(b.blue)+'</h3>'+
    '<div class="sub">'+esc(c.title||"")+' \u00b7 '+esc(roundOf(b))+' \u00b7 '+
      esc(b.date)+' at '+esc(b.time)+', Ring '+esc(b.ring)+'</div>'+
    boutLine(b)+
    (p?'<h4>Poule '+esc(p.name)+' standing</h4>'+standTable(p)+
       '<h4>All bouts in this poule</h4>'+p.bouts.map(function(m){
          return boutLine(m); }).join(""):""));
}
function openFighter(name){
  var bouts=D.bouts.filter(function(b){
    return fold(b.red)===fold(name)||fold(b.blue)===fold(name); });
  if(!bouts.length) return;
  var b0=bouts[0], c=catOf(b0.cat)||{}, p=pouleOf(b0.cat,name);
  var ctry = fold(b0.red)===fold(name)?b0.red_country:b0.blue_country;
  var real = fold(b0.red)===fold(name)?b0.red:b0.blue;
  var won=0, lost=0;
  bouts.forEach(function(b){
    if(!b.decided) return;
    var w=b.winner==="red"?b.red:b.blue;
    if(fold(w)===fold(name)) won++; else lost++;
  });
  var me = p ? ranked(p).filter(function(r){ return fold(r.name)===fold(name); })[0] : null;
  openSheet('<h3>'+esc(real)+'</h3>'+
    '<div class="sub">'+esc(ctry)+' \u00b7 '+esc(c.title||"")+
      (p?' \u00b7 Poule '+esc(p.name):'')+'</div>'+
    '<div class="rec">'+
      '<div><b>'+won+'\u2013'+lost+'</b><span>won \u2013 lost</span></div>'+
      '<div><b>'+(me?me.pts:0)+'</b><span>poule points</span></div>'+
      '<div><b>'+(me?me.warn:0)+'</b><span>warnings</span></div>'+
      '<div><b>'+(me?(me.tied?"=":me.rank):"\u2013")+'</b><span>place</span></div>'+
    '</div>'+
    '<h4>Their bouts</h4>'+bouts.map(function(b){ return boutLine(b,name); }).join("")+
    (p?'<h4>Poule '+esc(p.name)+' standing</h4>'+standTable(p,name):""));
}

/* ---- fighters ------------------------------------------------------ */
var PEOPLE = (function(){
  var m = {};
  D.bouts.forEach(function(b){
    [[b.red,b.red_country],[b.blue,b.blue_country]].forEach(function(x){
      var k = fold(x[0]);
      if(!m[k]) m[k] = {name:x[0], country:x[1], cats:{}, n:0};
      m[k].cats[b.cat] = 1; m[k].n++;
    });
  });
  return Object.keys(m).map(function(k){ return m[k]; })
    .sort(function(a,b){ return a.name.localeCompare(b.name); });
})();

function renderPeople(q){
  var list = PEOPLE.filter(function(p){
    if(!q) return true;
    var cs = Object.keys(p.cats).map(function(k){ return (catOf(k)||{}).title; }).join(" ");
    return fold(p.name+" "+p.country+" "+cs).indexOf(q)>=0;
  });
  var pinned = PEOPLE.filter(function(p){ return pins.has(fold(p.name)); });
  var head = pinned.length
    ? '<div class="dayhead"><h2>Following</h2><span class="n">'+pinned.length+'</span></div>'+
      '<div class="people">'+pinned.map(card).join("")+'</div>'
    : '<div class="note"><b>Tap the star</b> on any bout to follow a fighter. '+
      'Their bouts are highlighted throughout and collected here. Stored on this device only.</div>';
  $("#v-people").innerHTML = head +
    '<div class="dayhead"><h2>All fighters</h2><span class="n">'+list.length+'</span></div>' +
    (list.length ? '<div class="people">'+list.map(card).join("")+'</div>'
                 : '<div class="empty">Nothing matches \\u201c'+esc(q)+'\\u201d</div>');
  function card(p){
    var cs = Object.keys(p.cats).map(function(k){ return (catOf(k)||{}).title; }).join(", ");
    var on = pins.has(fold(p.name));
    return '<div class="person tap" data-fighter="'+esc(p.name)+'" role="button" '+
      'tabindex="0"><div><div class="nm">'+esc(p.name)+'</div>'+
      '<div class="cy">'+esc(p.country)+'</div></div>'+
      '<div class="cl">'+esc(cs)+'<br>'+p.n+' bout'+(p.n===1?"":"s")+'</div>'+
      '<button class="star" aria-pressed="'+on+'" data-pin="'+esc(fold(p.name))+'">'+
      (on?"\\u2605":"\\u2606")+'</button></div>';
  }
}

/* ---- provenance ---------------------------------------------------- */
$("#prov").innerHTML = [
  'Read directly from the organisers\\u2019 published bout list at <a href="'+esc(D.source)+
    '" rel="noopener noreferrer" target="_blank">world-assaut-championship.sport</a>, one page per country plus every poule sheet.',
  'Every field is taken from the element that owns it in the source page. Blank means the source is blank \\u2014 nothing on this page is estimated, seeded or projected.',
  S.knockout ? (S.knockout+' knockout bouts published so far.')
    : 'All '+S.bouts+' published bouts are poule stage. No knockout draw has been posted yet, so none is shown.',
  '<b>The organisers publish no bout score.</b> The points column is the FISav 2026 '+
    'championship pool scale (rules 2.6.3): <b>victory 3, defeat 1, draw 2, '+
    'abandon or forfeit \\u22121, disqualification \\u22123</b>. It tells you who won, '+
    'never how close it was.',
  'Two values in the live data sit outside that scale, and are described rather than '+
    'relabelled. Every <b>\\u22121</b> appears beside exactly three warnings \\u2014 the '+
    'third warning disqualifies \\u2014 yet the published scale prints \\u22123 for a '+
    'disqualification. And <b>0</b> is not on the scale at all; it appears where an '+
    'athlete did not fight. A bout where neither athlete is awarded anything is '+
    'indistinguishable from one not yet fought, and is shown as having no result.',
  'Pool places follow the championship tie-breaks in order: points, then the assaut the '+
    'tied athletes contested, then fewest warnings, then most victories. The last two '+
    'official criteria \\u2014 lightest at the weigh-in, then drawing lots \\u2014 rely on '+
    'weigh-in figures the organisers do not publish, so anyone still level is shown as '+
    '<b>=</b> rather than ordered on a guess.',
  'Format, scale and tie-breaks are quoted from the <b>FISav 2026 World Championship '+
    'Assaut rules</b>, the regulations for this event, not from national rulebooks.',
  '<b>Knockout results are not published anywhere.</b> A knockout bout has no poule '+
    'sheet, and the bout list\u2019s result line never changes, so the only evidence the '+
    'source gives is who appears in the NEXT round. A bout marked <b>Advanced</b> was '+
    'read that way \u2014 the fighter named in a later round went through. That is an '+
    'inference from the draw, not a reported result, and never a score.',
  '<b>Results come from the official poule scoresheet</b>, not from the bout list\u2019s '+
    'own result line \u2014 that line still reads \u201cMatch has not taken place yet\u201d even '+
    'after a bout has been fought and scored, so trusting it would hide every result. '+
    'A bout showing 0\u20130 has not been fought; otherwise the higher points wins.',
  S.results+' of '+S.bouts+' bouts are decided so far. Poule standings stay marked '+
    '<b>Provisional</b> until the source declares the classification final.',
  D.warnings.length
    ? ('<b>'+D.warnings.length+' page(s) could not be re-read this cycle</b> and were served from the previous copy, so a few figures may lag behind the ring: '+
    esc(D.warnings.slice(0,3).join('; '))+'.')
    : 'The scrape reported no inconsistencies: every bout is keyed to a poule, and every drawn pairing has a scheduled bout.'
].map(function(t){ return "<li>"+t+"</li>"; }).join("");

/* ---- wiring -------------------------------------------------------- */
var view="schedule", q="";
/* default to hiding what is already settled once anything has been decided:
   on the day, the useful page is the one showing what has not happened yet */
var hideDone = D.stats.results > 0;
$("#hidedone").checked = hideDone;
$("#hidedone").addEventListener("change", function(e){ hideDone = e.target.checked; draw(); });
setInterval(function(){ if(view==="schedule" && !q) draw(); }, 60000);
function draw(){
  if(view==="schedule") renderSchedule(q);
  else if(view==="classes") renderClasses(q);
  else renderPeople(q);
}
document.querySelectorAll('.tabs button').forEach(function(btn){
  btn.addEventListener("click", function(){
    document.querySelectorAll('.tabs button').forEach(function(b){
      b.setAttribute("aria-selected", String(b===btn)); });
    view = btn.dataset.view;
    ["schedule","classes","people"].forEach(function(v){
      document.getElementById("v-"+v).hidden = (v!==view); });
    draw();
  });
});
var timer;
$("#q").addEventListener("input", function(e){
  clearTimeout(timer);
  var val = fold(e.target.value);
  timer = setTimeout(function(){ q=val; draw(); }, 120);
});
document.addEventListener("click", function(e){
  if(!e.target.closest("[data-pin]")){
    var fb = e.target.closest("[data-bout]");
    if(fb){ openBout(fb.dataset.bout); return; }
    var ff = e.target.closest("[data-fighter]");
    if(ff){ openFighter(ff.dataset.fighter); return; }
  }
  var btn = e.target.closest("[data-pin]");
  if(!btn) return;
  btn.dataset.pin.split("|").forEach(function(n){
    if(!n) return;
    if(pins.has(n)) pins.delete(n); else pins.add(n);
  });
  savePins(); draw();
});
document.addEventListener("keydown", function(e){
  if(e.key!=="Enter" && e.key!==" ") return;
  var t=e.target.closest("[data-bout],[data-fighter]");
  if(!t) return;
  e.preventDefault();
  if(t.dataset.bout) openBout(t.dataset.bout); else openFighter(t.dataset.fighter);
});

draw();
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="site.html")
    args = ap.parse_args()

    if not SRC.exists():
        raise SystemExit(f"{SRC} not found - run scrape_assaut.py first")
    payload = build(json.loads(SRC.read_text(encoding="utf-8")))
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # the payload sits in a <script type="application/json">; only "</" can end it
    blob = blob.replace("</", "<\\/")
    Path(args.out).write_text(HTML.replace("__DATA__", blob), encoding="utf-8")
    s = payload["stats"]
    print(f"{args.out}: {s['classes']} classes, {s['poules']} poules, "
          f"{s['bouts']} bouts ({s['results']} with results), "
          f"{s['knockout']} knockout bouts, {s['fighters']} fighters")


if __name__ == "__main__":
    main()
