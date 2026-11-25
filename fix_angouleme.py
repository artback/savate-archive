#!/usr/bin/env python3
"""Angoulême 2e Série finals (14/12/2024): one championship, two documents.

The archive had ingested both documents of the same 2e Série finals:

* the federation's results sheet (V2, published on ffsavate.com, PDF
  created 2024-12-17) - the official record: 15 weight categories, the
  winner listed first, a decision word per final;
* the pre-event program (livret V1, PDF created 2024-12-03, eleven days
  before the event). Its "finals" page is the entry list
  ("liste des inscrits"), and the pipeline parsed it as results:
  registration order became gold/silver, so eight of the fifteen winners
  were wrong (M-56 gold was ANANDY, where the sheet says HASSEINE,
  by forfait; M-60 gold DIEDHOU where the sheet says TITREN; and so on).

The results sheet is the federation's official record, so the repair
keeps that row (the ffsavate one, whose source is the sheet itself) and
rebuilds it with the full fifteen finals, then deletes the livret row
and whatever it orphaned.

Run after fix_events.py and before export_ui.py. Idempotent: a second
run finds the applied state and does nothing.

Slugs are never touched. What the repairs cannot reach is printed, not
guessed.
"""

import sqlite3

DB = "savate.db"

FF = "ffsavate-finales-championnat-de-france-2e-s-rie-angoul-me-202"
LV = "livret-finales-2eme-serie-angouleme-v1-pdf"

# The sheet prints "14/12/2024 ... St Yrieix sur Charente (16)"; the
# ingested year=2025 is the season's closing year, the event's year is 2024.
YEAR = "2024"
DATE = "2024-12-14"

# The fifteen finals of the official sheet. (number, category, gender,
# weight_kg, weight_bound, winner, loser, winner club, loser club, decision).
# Names carry the spellings registered in fighter_aliases ("BREMNAR Kevin",
# "URTIAGA Melody", "HATTAIS (PRAT) Camille"). Decisions use the corpus
# vocabulary: "forfait" for walkovers, "points" for Unanimité/Majorité.
# W-48 ended "hors combat" and the corpus has no KO decision value, so the
# decision stays empty rather than forced into a wrong label.
FINALS = [
    ("01", "Senior Women -48 kg", "Women", "48", "under",
     "MEGE Julie", "AUBERT Yasmine", "SBF TRAMOYES", "BF MASSERAN", ""),
    ("02", "Senior Women -52 kg", "Women", "52", "under",
     "DE SALVO Pema", "QUILVIN Ida",
     "SAVATE BOXING LA CIOTAT ACADEMIE", "COOPYR SPORTIF", "points"),
    ("03", "Senior Women -56 kg", "Women", "56", "under",
     "TRIBOU Ava", "HATTAIS (PRAT) Camille", "SAVATE BOXE ACADEMIE",
     "MENEZ-HOM KRAON BOXING CLUB", "points"),
    ("04", "Senior Women -60 kg", "Women", "60", "under",
     "RAFAEL Bérénice", "COSTA-PICORNELL Cassidy", "BF PARADIS",
     "IMPACT MULTI BOXE", "forfait"),
    ("05", "Senior Women -65 kg", "Women", "65", "under",
     "URTIAGA Melody", "PEREIRA LOPES Philippine",
     "APOLLO SPORTING CLUB VAL D'EUROPE", "GANT D'OR HOUILLES", "points"),
    ("06", "Senior Women -70 kg", "Women", "70", "under",
     "BUGADA Marine", "RECCHIA Pauline", "SBF DE CLUSES",
     "SBF STADE CLERMONTOIS", "points"),
    ("07", "Senior Women -75 kg", "Women", "75", "under",
     "HUREL Jade", "DEFOSSE Cali", "SBF STADE CLERMONTOIS",
     "CENTER TRAINING BOULOGNE SUR MER", "points"),
    ("08", "Senior Men open", "Men", "", "over",
     "TIMON Jacques-Olivier", "MAGNANO Loris", "DAMPMART BOXE FRANCAISE",
     "SAVATE SAINT CHRISTOL", "points"),
    ("09", "Senior Men -56 kg", "Men", "56", "under",
     "HASSEINE Yanis", "ANANDY Jean Enzo", "PROVENCE BF", "JPPDA-TRP",
     "forfait"),
    ("10", "Senior Men -60 kg", "Men", "60", "under",
     "TITREN Nicolas", "DIEDHOU Abdul Christophe", "BAC 9 Savate",
     "BOXE SAVATE CLUB", "points"),
    ("11", "Senior Men -65 kg", "Men", "65", "under",
     "BRARD Arthur", "DELAGE Tim", "BF ALLONES", "ESC BOXING CLUB",
     "points"),
    ("12", "Senior Men -70 kg", "Men", "70", "under",
     "BREMNAR Kevin", "BODIMBOURG Nicolas", "SAVATE PORTELOISE",
     "CLUB SAVATE MACONNAIS", "points"),
    ("13", "Senior Men -75 kg", "Men", "75", "under",
     "CAZAT Enzo", "TIEN-MI-TIEE Emeric", "SAVATE BOXE VICHY",
     "BOXE FRANCAISE MULHOUSE", "points"),
    ("14", "Senior Men -80 kg", "Men", "80", "under",
     "MECHIN Baptiste", "ROUZIER Paul", "PLANETE BORG",
     "SAVATE HYPER FIGHTING", "points"),
    ("15", "Senior Men -85 kg", "Men", "85", "under",
     "BARREAU Paul", "FRAIX-BURNET Maximin", "IMPACTS 33", "LYON SAVATE",
     "points"),
]


def target_bouts():
    return [
        (FF, "%s-%s-final" % (FF, num), DATE, "", "", cat, gender, "Senior",
         wkg, bound, "final", "", w, "", wc, "", l, "", lc, "",
         "", "", "", "", "", w, l, dec, "", "decided", "reported")
        for num, cat, gender, wkg, bound, w, l, wc, lc, dec in FINALS
    ]


def target_placings():
    out = []
    for num, cat, gender, wkg, bound, w, l, wc, lc, dec in FINALS:
        out.append((FF, "%s-%s-1" % (FF, num), cat, gender, "Senior",
                    wkg, bound, "1", "gold", w, "France", wc, "",
                    "reported"))
        out.append((FF, "%s-%s-2" % (FF, num), cat, gender, "Senior",
                    wkg, bound, "2", "silver", l, "France", lc, "",
                    "reported"))
    return out


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    slugs = {r[0] for r in cur.execute("SELECT slug FROM tournaments")}
    if FF not in slugs:
        print("  MISSING | %s | run the pipeline first" % FF)
        return

    want_bouts = {
        (b[1], b[5], b[12], b[16], b[25], b[27])
        for b in target_bouts()}
    have_bouts = {
        tuple(r) for r in cur.execute(
            "SELECT bout_id, category, red, blue, winner, decision "
            "FROM bouts WHERE tournament = ?", (FF,))}
    want_placings = {
        (p[1], p[2], p[7], p[8], p[9], p[11])
        for p in target_placings()}
    have_placings = {
        tuple(r) for r in cur.execute(
            "SELECT placing_id, category, rank, medal, fighter, club "
            "FROM placings WHERE tournament = ?", (FF,))}
    meta = cur.execute(
        "SELECT year, end_date FROM tournaments WHERE slug = ?",
        (FF,)).fetchone()
    if (LV not in slugs
            and have_bouts == want_bouts
            and have_placings == want_placings
            and meta[0] == YEAR and (meta[1] or "") == DATE):
        print("  OK | %s | already the official sheet's fifteen finals" % FF)
        return

    names = set()
    for slug in (LV, FF):
        if slug not in slugs:
            continue
        for col, table in (("fighter", "placings"), ("red", "bouts"),
                           ("blue", "bouts")):
            names.update(r[0] for r in cur.execute(
                "SELECT DISTINCT %s FROM %s WHERE tournament = ? AND %s <> ''"
                % (col, table, col), (slug,)))

    if LV in slugs:
        cur.execute("DELETE FROM placings WHERE tournament = ?", (LV,))
        cur.execute("DELETE FROM bouts WHERE tournament = ?", (LV,))
        cur.execute("DELETE FROM tournaments WHERE slug = ?", (LV,))
        slugs.discard(LV)
        print("  DEL | %s | entry-list parse of the pre-event livret; "
              "eight of fifteen winners wrong" % LV)

    cur.execute("DELETE FROM placings WHERE tournament = ?", (FF,))
    cur.execute("DELETE FROM bouts WHERE tournament = ?", (FF,))
    cur.executemany(
        "INSERT INTO bouts (tournament, bout_id, date, time, ring, category, "
        "gender, age_class, weight_kg, weight_bound, phase, poule, red, "
        "red_country, red_club, red_weighed, blue, blue_country, blue_club, "
        "blue_weighed, red_points, blue_points, red_warnings, blue_warnings, "
        "winner_corner, winner, loser, decision, decision_detail, status, "
        "result_source) VALUES (" + ",".join("?" * 31) + ")",
        target_bouts())
    cur.executemany(
        "INSERT INTO placings (tournament, placing_id, category, gender, "
        "age_class, weight_kg, weight_bound, rank, medal, fighter, country, "
        "club, weighed, result_source) VALUES (" + ",".join("?" * 14) + ")",
        target_placings())
    print("  FIX | %s | rebuilt from the official results sheet: "
          "15 bouts, 30 placings" % FF)

    if (meta[1] or "") != DATE:
        cur.execute("UPDATE tournaments SET end_date = ? WHERE slug = ?",
                    (DATE, FF))
    if meta[0] != YEAR:
        cur.execute("UPDATE tournaments SET year = ? WHERE slug = ?",
                    (YEAR, FF))
        print("  YEAR | %s | %s -> %s | the sheet prints %s"
              % (FF, meta[0] or "empty", YEAR, DATE))

    orphans = 0
    for name in sorted(names):
        refs = cur.execute(
            "SELECT COUNT(*) c FROM (SELECT fighter AS f FROM placings "
            "WHERE fighter = ? "
            "UNION SELECT red AS f FROM bouts WHERE red = ? "
            "UNION SELECT blue AS f FROM bouts WHERE blue = ?)",
            (name, name, name)).fetchone()[0]
        if refs:
            continue
        cur.execute("DELETE FROM fighter_aliases WHERE fighter_id = "
                    "(SELECT id FROM fighters WHERE name = ?)", (name,))
        cur.execute("DELETE FROM fighters WHERE name = ?", (name,))
        orphans += 1
        print("  GHOST | %s | no bout or placing left, removed" % name)

    db.commit()
    print("Summary: one event repaired (15 finals from the official sheet), "
          "one entry-list event deleted, %d ghost fighters removed"
          % orphans)


if __name__ == "__main__":
    main()