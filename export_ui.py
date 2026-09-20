#!/usr/bin/env python3
"""Export the archive as one compact file for the web interface.

Columns are written as positional arrays against shared string tables. The same
forty-odd category labels, a couple of hundred nations and a dozen decisions
repeat across three thousand rows, and spelling them out each time triples the
file the page has to load before it can answer anything.

Written as a script that assigns a global, not as JSON the page fetches: a
published artifact may always load a script beside it, while same-origin XHR is
one more thing that can be blocked between here and the browser.

One thing happens on the way out that does not happen in the database.

Poule tables are computed here by `savate.rules.standings`, the same function
the tests check against the federation's own printed sheets, rather than
re-implemented in JavaScript. A second implementation is a second thing to be
wrong, and this one carries what a hand-rolled sort cannot: which rung of the
ladder separated each pair, and which groups no rung could separate at all.

Names and countries are already repaired: `build_db.py` normalises them at the
door, so the database holds the name the source meant rather than the string its
PDF printed. All that is added here is the ISO code behind each nation, because
flag emoji are the only flags a published page is allowed to draw.
"""

import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from savate import competition, display, rules  # noqa: E402

DB = "savate.db"
OUT = "ui/data.js"

# The archive's owner. The interface opens on him, so the export names him
# rather than leaving the page to guess which of 1649 competitors is the reader.
OWNER = "artback jonathan"

# Phases in the order a competition runs them.
PHASE_ORDER = ["poule", "quarter", "semi", "final"]


class Table:
    """A string table: every distinct value once, referenced by index."""

    def __init__(self):
        self.values = []
        self.index = {}

    def __call__(self, value):
        value = value or ""
        if value not in self.index:
            self.index[value] = len(self.values)
            self.values.append(value)
        return self.index[value]


def rows(db, sql, *args):
    return [dict(r) for r in db.execute(sql, args)]


def weight_label(kg, bound):
    """"-80 kg", "+85 kg", or "" - the way a competitor says the category."""
    if not kg:
        return ""
    sign = "+" if bound == "over" else "-"
    kg = str(kg).rstrip("0").rstrip(".") if "." in str(kg) else str(kg)
    return f"{sign}{kg} kg"


def main():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    report = defaultdict(int)

    country_cache = {}

    def nation(raw):
        if raw not in country_cache:
            country_cache[raw] = display.country(raw)
        return country_cache[raw]

    # ---- string tables ---------------------------------------------------
    category, decision, phase, club = Table(), Table(), Table(), Table()

    nations, nation_ix = [], {}

    def nation_index(raw):
        """Index into the nations table, or -1 where nothing resolved."""
        resolved = nation(raw)
        if not resolved.known:
            if not raw or not raw.strip():
                return -1
            # Kept verbatim and flagless: the federation printed something, and
            # blanking it would hide that more surely than showing it.
            key = f"?{display.fold(raw)}"
            if key not in nation_ix:
                nation_ix[key] = len(nations)
                text = display._collapse(raw)
                nations.append([text, "", "", 0, text, text,
                                display.fold(text)])
            return nation_ix[key]
        key = resolved.name
        if key not in nation_ix:
            nation_ix[key] = len(nations)
            en, fr, es = display.names(resolved.name)
            nations.append([
                en, resolved.code, resolved.iso, 1 if resolved.iso else 0,
                fr, es,
                # Every attested spelling, so a reader finds a nation by the
                # name they know it under, whatever the interface language.
                display.fold(" ".join(display.spellings(resolved.name))),
            ])
        return nation_ix[key]

    # ---- events ----------------------------------------------------------
    events, event_ix = [], {}
    for r in rows(db, "SELECT slug, name, year, level, format, age_class,"
                      " discipline, country, city, start_date, end_date, source"
                      " FROM tournaments ORDER BY year DESC, name"):
        event_ix[r["slug"]] = len(events)
        events.append([
            r["name"], r["year"], r["level"], r["discipline"],
            r["start_date"] or "", r["end_date"] or "",
            r["city"] or "", nation_index(r["country"]),
            r["slug"], r["format"] or "", r["age_class"] or "",
            competition.label(r["level"], r["format"]),
            # Where this event came from: the document it was read from. An
            # archive that cannot show its source for a line is a rumour.
            r["source"] or "",
        ])

    # ---- people ----------------------------------------------------------
    # Anything a source printed about a person belongs on their fiche, so the
    # weigh-in follows the club out of the bout rows and onto the person.
    weighed_by_person = defaultdict(set)
    for r in rows(db, """
            SELECT a.fighter_id AS id, b.red_weighed AS kg FROM bouts b
              JOIN fighter_aliases a ON a.alias = b.red WHERE b.red_weighed <> ''
            UNION
            SELECT a.fighter_id, b.blue_weighed FROM bouts b
              JOIN fighter_aliases a ON a.alias = b.blue WHERE b.blue_weighed <> ''
            UNION
            SELECT a.fighter_id, p.weighed FROM placings p
              JOIN fighter_aliases a ON a.alias = p.fighter WHERE p.weighed <> ''"""):
        weighed_by_person[r["id"]].add(r["kg"])

    clubs = {}
    for r in rows(db, """
            SELECT a.fighter_id AS id, p.club FROM placings p
              JOIN fighter_aliases a ON a.alias = p.fighter WHERE p.club <> ''
            UNION
            SELECT a.fighter_id, b.red_club FROM bouts b
              JOIN fighter_aliases a ON a.alias = b.red WHERE b.red_club <> ''
            UNION
            SELECT a.fighter_id, b.blue_club FROM bouts b
              JOIN fighter_aliases a ON a.alias = b.blue WHERE b.blue_club <> ''"""):
        clubs.setdefault(r["id"], club(r["club"]))

    people, person_ix = [], {}
    for r in rows(db, """
            SELECT f.id, f.name, f.countries, f.appearances,
                   (SELECT GROUP_CONCAT(alias, '|') FROM fighter_aliases a
                    WHERE a.fighter_id = f.id) AS aliases
            FROM fighters f ORDER BY f.appearances DESC, f.name"""):
        aliases = [a for a in (r["aliases"] or "").split("|") if a and a != r["name"]]
        countries = [nation_index(c.strip())
                     for c in (r["countries"] or "").split(",") if c.strip()]
        countries = list(dict.fromkeys(i for i in countries if i >= 0))
        shown = r["name"]

        person_ix[r["id"]] = len(people)
        people.append([
            shown, countries, sorted(aliases),
            clubs.get(r["id"], -1),
            display.fold(" ".join([shown] + aliases)),
            r["id"],
            sorted(weighed_by_person.get(r["id"], ())),
        ])

    alias_to_person = {}
    for r in rows(db, "SELECT alias, fighter_id FROM fighter_aliases"):
        if r["fighter_id"] in person_ix:
            alias_to_person[r["alias"]] = person_ix[r["fighter_id"]]

    def person_index(raw_name):
        if raw_name in alias_to_person:
            return alias_to_person[raw_name]
        return person_ix.get(raw_name, -1)

    # ---- bouts -----------------------------------------------------------
    bouts, bout_ix = [], {}
    poule_groups = defaultdict(list)
    for r in rows(db, "SELECT * FROM bouts ORDER BY tournament, date, time, bout_id"):
        red, blue = person_index(r["red"]), person_index(r["blue"])
        if red < 0 or blue < 0 or r["tournament"] not in event_ix:
            report["bouts_dropped"] += 1
            continue
        bout_ix[r["bout_id"]] = len(bouts)
        if r["phase"] == "poule":
            poule_groups[(r["tournament"], r["category"], r["poule"] or "")].append(r)
        # Some sources name the winner and never publish the corner. Both
        # facts ship: the corner where it exists, and the winner either way,
        # so the page can say who won without drawing a corner nobody recorded.
        winner_ix = -1
        if r["winner"]:
            winner_ix = person_index(r["winner"])
        bouts.append([
            event_ix[r["tournament"]], red, blue,
            r["red_points"] or "", r["blue_points"] or "",
            # -1 means the document did not publish a warning count. Coercing
            # it to 0 would print "no warnings given" on 223 bouts nobody
            # counted, which is the one lie this archive must not tell.
            int(r["red_warnings"]) if r["red_warnings"] != "" else -1,
            int(r["blue_warnings"]) if r["blue_warnings"] != "" else -1,
            {"red": 0, "blue": 1}.get(r["winner_corner"], -1),
            decision(r["decision"]), phase(r["phase"]),
            r["poule"] or "", category(r["category"]),
            r["date"] or "", r["time"] or "", r["ring"] or "",
            nation_index(r["red_country"]), nation_index(r["blue_country"]),
            winner_ix, r["decision_detail"] or "",
        ])

    # ---- poule tables ----------------------------------------------------
    # Computed by the engine the tests check, not by the page.
    def weighed(text):
        """"Pesé 81,5Kg" -> 81.5, for the ladder's last rung."""
        match = re.search(r"([\d]+(?:[.,]\d+)?)", str(text or ""))
        return float(match.group(1).replace(",", ".")) if match else None

    poules = []
    for (tournament, cat, letter), group in sorted(poule_groups.items()):
        # The weigh-in is the criterion the federation itself names for a poule
        # no other rung can split, and three of the 2025 European sheets print
        # it beside the name. Where it exists, the ladder gets to use it.
        weights = {}
        for b in group:
            for corner in ("red", "blue"):
                kg = weighed(b[f"{corner}_weighed"])
                if kg is not None:
                    weights[b[corner]] = kg
        try:
            table = rules.standings([dict(b) for b in group],
                                    weights=weights or None)
        except Exception:
            report["poules_failed"] += 1
            continue

        by_display = {}
        for b in group:
            for corner in ("red", "blue"):
                by_display[b[corner]] = person_index(b[corner])

        lines = []
        for s in table.standings:
            idx = by_display.get(s.name, -1)
            if idx < 0:
                continue
            lines.append([idx, s.points, s.warnings, s.wins, s.bouts,
                          s.rank, s.decided_by])
        unresolved = [[by_display.get(n, -1) for n in g]
                      for g in table.unresolved]
        unresolved = [[i for i in g if i >= 0] for g in unresolved]
        if not lines:
            continue
        poules.append([
            event_ix[tournament], category(cat), letter,
            lines, [g for g in unresolved if len(g) > 1],
            1 if table.complete else 0,
        ])
        if table.unresolved:
            report["poules_unresolved"] += 1
    report["poules"] = len(poules)

    # ---- placings --------------------------------------------------------
    placings = []
    for r in rows(db, "SELECT * FROM placings ORDER BY tournament, category, rank"):
        idx = person_index(r["fighter"])
        if idx < 0 or r["tournament"] not in event_ix:
            report["placings_dropped"] += 1
            continue
        placings.append([
            event_ix[r["tournament"]], idx, int(r["rank"]),
            category(r["category"]), nation_index(r["country"]),
        ])

    # ---- category vocabulary --------------------------------------------
    # Each label parsed once here rather than with a regular expression in the
    # page every time a filter changes.
    meta = {}
    for r in rows(db, "SELECT DISTINCT category, gender, age_class, weight_kg,"
                      " weight_bound FROM bouts UNION"
                      " SELECT DISTINCT category, gender, age_class, weight_kg,"
                      " weight_bound FROM placings"):
        if r["category"] and r["category"] not in meta:
            meta[r["category"]] = r
    categories = []
    for label in category.values:
        m = meta.get(label)
        if not m:
            categories.append([label, "", "", "", ""])
            continue
        categories.append([
            label, m["gender"] or "", m["age_class"] or "",
            str(m["weight_kg"] or ""),
            weight_label(m["weight_kg"], m["weight_bound"]),
        ])

    # ---- archive-wide figures --------------------------------------------
    # The notice quotes these. They are computed here, not typed into the
    # interface: the notice is a honesty claim, and a claim that moves every
    # wave must be re-derived at export time, never copied by hand.
    decided = db.execute(
        "SELECT COUNT(*) FROM bouts WHERE winner_corner IN ('red','blue')"
    ).fetchone()[0]
    red_won = db.execute(
        "SELECT COUNT(*) FROM bouts WHERE winner_corner = 'red'"
    ).fetchone()[0]
    report["red_win_pct"] = round(100.0 * red_won / decided, 1) if decided else 0
    report["bouts_no_warnings"] = db.execute(
        "SELECT COUNT(*) FROM bouts"
        " WHERE red_warnings = '' AND blue_warnings = ''"
    ).fetchone()[0]
    report["nations_unmatched"] = sum(1 for n in nations if not n[3])

    payload = {
        "events": events,
        "people": people,
        "bouts": bouts,
        "poules": poules,
        "placings": placings,
        "categories": categories,
        "decisions": decision.values,
        "phases": phase.values,
        "phase_order": PHASE_ORDER,
        "nations": nations,
        "clubs": club.values,
        "owner": person_ix.get(OWNER, -1),
        "scopes": [[s, competition.SCOPE_LABELS[s]] for s in competition.SCOPES],
        "formats": [[f, competition.FORMAT_LABELS[f]] for f in competition.FORMATS],
        "continental": sorted(competition.CONTINENTAL),
        "report": dict(report),
    }

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    Path(OUT).write_text(f"window.SAVATE={body};\n", encoding="utf-8")

    size = Path(OUT).stat().st_size
    print(f"{len(events)} événements · {len(people)} tireurs · {len(bouts)} combats · "
          f"{len(poules)} poules · {len(placings)} places · {len(nations)} nations")
    print(f"  {OUT}  {size / 1024:.0f} KB")
    flagged = sum(1 for n in nations if n[3])
    print(f"  nations résolues {flagged}/{len(nations)}")
    for key, value in sorted(report.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
