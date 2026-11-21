#!/usr/bin/env python3
"""Event repairs the pipeline and fix_years_names.py did not reach.

Run after fix_years_names.py and before export_ui.py. Idempotent: every
repair asserts the state it fixes, so a second run finds nothing left to
do.

Four repairs, on the tournaments table and its two children (bouts,
placings):

1. A year read from the source document itself. Where the pipeline left
   the year empty, the raw file in raw_sources/ says what the event was:
   the sheet's own date ("july 2021", "Kikinda, 26.09.2020."), the
   season line ("SAISON 2025/2026"), or - for scanned sheets with no
   text layer - the PDF creation date, trusted only when a sibling file
   or the source corpus pins the same event to that year. A season label
   stores its closing year, the way the pipeline already does
   ("Angoulême 2024-25" is 2025).
2. The legacy 2020 ingest batch stored year=2020 on rows whose names
   carry no year. There the printed sheet date is the only evidence, and
   each group is internally consistent (the five 2015 sheets span one
   full season, the two Narbonne rows share a day, the two 2019 rows
   fall in one spring), so the date decides.
3. A printed year that the stored date contradicts wins, and the date is
   cleared - a wrong date is worse than none ("Finales ... Elite B 2020"
   dated 2018-01-27 is a 2020 event with a corrupted date).
4. Events that are not events - a web page scraped into the archive, a
   round fragment with no rows - are deleted together with their child
   rows. None of them carries a bout or a real placing, so nothing is
   lost.

Slugs are never touched. What the repairs cannot reach is printed, not
guessed.
"""

import sqlite3

DB = "savate.db"

# slug -> (year, what the source document says). Applied only where the
# year is still empty.
EVIDENCE = {
    # FISAV "juin 2019" weight-class sheets, World Combat Championships 2019.
    "666-senior-men-60kg": ("2019", "sheet prints 'juin 2019'"),
    "667-senior-men-65kg": ("2019", "sheet prints 'juin 2019'"),
    "668-senior-men-70kg": ("2019", "sheet prints 'juin 2019'"),
    "669-senior-men-75kg": ("2019", "sheet prints 'juin 2019'"),
    "674-senior-women-48kg": ("2019", "sheet prints 'juin 2019'"),
    "676-senior-women-56kg": ("2019", "sheet prints 'juin 2019'"),
    # FISAV "july 2021" weight-class sheets, World Combat Championships 2021.
    "750-world-combat-senior-women-f56": ("2021", "sheet prints 'july 2021'"),
    "751-world-combat-senior-women-f60": ("2021", "sheet prints 'july 2021'"),
    "752-world-combat-junior-j75": ("2021", "sheet prints 'july 2021'"),
    "753-world-combat-senior-men-m56": ("2021", "sheet prints 'july 2021'"),
    "754-world-combat-senior-men-m60": ("2021", "sheet prints 'july 2021'"),
    "755-world-combat-senior-men-m65": ("2021", "sheet prints 'july 2021'"),
    "756-world-combat-senior-men-m70": ("2021", "sheet prints 'july 2021'"),
    "757-world-combat-senior-men-m75": ("2021", "sheet prints 'july 2021'"),
    "758-world-combat-senior-men-m80": ("2021", "sheet prints 'july 2021'"),
    "759-world-combat-senior-men-m85": ("2021", "sheet prints 'july 2021'"),
    "760-world-combat-senior-men-m-85": ("2021", "sheet prints 'july 2021'"),
    # Ruma, Serbia: "28. 03. 2021. RUMA".
    "combatruma-pdf-junior": ("2021", "sheet prints '28. 03. 2021. RUMA'"),
    "combatruma-pdf-senior": ("2021", "sheet prints '28. 03. 2021. RUMA'"),
    # Italian pool sheets: "23 maggio 2021".
    "pool-g1-r1-sc-pdf": ("2021", "sheet prints '23 maggio 2021'"),
    "pool-g1-t1-sdt-pdf": ("2021", "sheet prints '23 maggio 2021'"),
    # World Cup qualifying sheets: "Eliminatoires Championnats du Monde Combat 2015".
    "wcjunior-pdf": ("2015", "sheet prints 'Eliminatoires ... Combat 2015'"),
    "wcsenior-pdf": ("2015", "sheet prints 'Eliminatoires ... Combat 2015'"),
    "wcwomen-pdf": ("2015", "sheet prints 'Eliminatoires ... Combat 2015'"),
    # Serbian youth assemblies, one shared results sheet each.
    "rezultati-kikinda-pdf-cadet": ("2020", "sheet prints 'Kikinda, 26.09.2020'"),
    "rezultati-kikinda-pdf-older-pioneer": ("2020", "sheet prints 'Kikinda, 26.09.2020'"),
    "rezultati-kikinda-pdf-senior": ("2020", "sheet prints 'Kikinda, 26.09.2020'"),
    "rezultati-kikinda-pdf-younger-pioneer": ("2020", "sheet prints 'Kikinda, 26.09.2020'"),
    "rezultati-senta-pdf-cadet": ("2022", "sheet prints 'Senta, 15.05.2022'"),
    "rezultati-senta-pdf-junior": ("2022", "sheet prints 'Senta, 15.05.2022'"),
    "rezultati-senta-pdf-older-pioneer": ("2022", "sheet prints 'Senta, 15.05.2022'"),
    "rezultati-senta-pdf-younger-junior": ("2022", "sheet prints 'Senta, 15.05.2022'"),
    "rezultati-senta-pdf-younger-pioneer": ("2022", "sheet prints 'Senta, 15.05.2022'"),
    # French federation sheets.
    "championnat-de-assaut-m-f": ("2023", "sheet prints 2023"),
    "dossier-20competition-20v9-20-20livret-20open-20v3-pdf":
        ("2023", "dossier of the 'saison 2022-2023'"),
    "varazdincombatwoman-pdf": ("2023", "sheet prints 'Championnat du Monde Savate Combat 2023'"),
    "livret-de-competition-finale-elite-b-maubeuge-pdf": ("2025", "sheet prints 'Le 1er février 2025'"),
    "livret-des-competitions-v1-open-dautomne-pdf": ("2024", "sheet prints 'Les 16 et 17 novembre 2024'"),
    "livret-de-competition-open-assaut-individuel-calais-v2-pdf":
        ("2026", "sheet prints 'SAISON 2025/2026'"),
    "resultats-merignac-pdf": ("2026", "sheet prints '1° Séries 2026'"),
    # Scanned sheets: no text layer, the PDF creation date decides - pinned
    # by a sibling file or the source corpus, never by the date alone.
    "resultats-20veterans-pdf":
        ("2015", "PDF created 2015-07-02; the 2023/2025 veterans sheets are separate files"),
    "resultats-c2m-pdf":
        ("2023", "PDF created 2023-05-02; sibling 'Plateau-Finales-C2M-Merignac-25032023'"),
    "resultats-2s-fm-torreilles-pdf":
        ("2024", "PDF created 2024-12-06, the 2e Série finals week"),
    "resultats-tq-juniors-merignac-1-pdf":
        ("2025", "PDF created 2025-03-03; the same TQ series' Espoirs sheet (Dec 2024) is 2024"),
    # Guadeloupe/Gosier challenge: the name's "04/06/20416" is a mangled
    # 2016, and source document 272 of the Antilles corpus is a 2016
    # document (its sibling 272 prints "Canne de Combat 2016").
    "challenge-timoun-st-felix-gosier-04-06-20416":
        ("2016", "name date '04/06/20416' = 2016; corpus document 272 is 2016"),
    # Corpus document 225 sits between the Dec 2014 and Jun 2015 documents.
    "deplacement-martinique": ("2015", "corpus document 225 brackets 2014-12..2015-06"),
    # "UNIVERSITAIRE 2004" - the 2004 university championship, the same
    # sheets that printed "équipe 1" and "Place" in the nation column.
    "escalade-resultats-pdf": ("2004", "sheet prints 'UNIVERSITAIRE 2004'"),
}

# The legacy 2020 batch: the name carries no year, the stored 2020 is the
# ingest's default, and the printed sheet date is the only evidence.
# slug -> new year. Applied only where the stored year is still "2020".
YEAR_FROM_DATE = {
    "r-sultats-des-finales-des-championnats-de-france-espoirs-m-f": "2015",
    "r-sultats-des-finales-du-championnat-de-france-juniors-2020": "2015",
    "r-sultats-des-finales-des-championnats-de-france-jeunes-mini-cadet": "2015",
    "r-sultats-des-finales-des-championnats-de-france-jeunes-mini-minime": "2015",
    "r-sultats-des-tournois-de-france-seniors-m-f-2020": "2015",
    "r-sultats-des-championnats-de-france-jeunes-narbonne-2020-cadet": "2018",
    "r-sultats-des-championnats-de-france-jeunes-narbonne-2020-minime": "2018",
    "r-sultats-du-tournoi-liminatoire-de-la-coupe-de-france-assau": "2018",
    "finales-du-championnat-de-france-combat-f-minin-2-me-s-rie-2": "2019",
    "finales-du-championnat-de-france-espoirs-2020": "2019",
    "finales-du-championnat-de-france-juniors-2020": "2019",
    "resultats-des-tournois-qualificatifs-assaut-m-f-2020": "2021",
}

# A printed year the date contradicts wins; the date is cleared.
# slug -> the corrupted date the repair expects to find there.
CLEAR_DATE = {
    "resultats-des-finales-du-championnat-de-france-elite-b-2020": "2018-01-27",
    "resultats-des-tournois-qualificatifs-assaut-m-f-2020-2": "2018-03-31",
    "asorumas-pdf": "2021-03-14",
    "livret-elite-a-vandoeuvre-pdf": "2024-02-03",
}

# Events that are not events. slug -> what it actually is.
DELETE = {
    "resultats-1er-gant-pdf": "a round fragment with no bouts and no placings",
    "livret-2eme-serie-m-resultat-brunoy-pdf": "zero rows parsed; the sheet printed no results",
    "savate-association-india-savate-french-boxing-in-india":
        "a web page scraped in as an event; its single 'placing' is the page title",
}


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    rows = cur.execute(
        "SELECT slug, year, start_date, end_date FROM tournaments"
    ).fetchall()
    state = {slug: (year, start, end) for slug, year, start, end in rows}
    fixed = cleared = deleted = orphans = 0

    for slug, (year, evidence) in sorted(EVIDENCE.items()):
        if slug not in state:
            print("  MISSING | %s" % slug)
            continue
        cur_year = (state[slug][0] or "").strip()
        if cur_year == year:
            continue
        if cur_year:
            print("  CONFLICT | %s | stored %s, evidence says %s (%s)"
                  % (slug, cur_year, year, evidence))
            continue
        cur.execute("UPDATE tournaments SET year = ? WHERE slug = ?",
                    (year, slug))
        fixed += 1
        print("  YEAR | %s -> %s | %s" % (slug, year, evidence))

    for slug, year in sorted(YEAR_FROM_DATE.items()):
        if slug not in state:
            print("  MISSING | %s" % slug)
            continue
        cur_year = (state[slug][0] or "").strip()
        if cur_year == year:
            continue
        if cur_year != "2020":
            print("  SKIP | %s | stored %s, expected the legacy 2020"
                  % (slug, cur_year or "empty"))
            continue
        cur.execute("UPDATE tournaments SET year = ? WHERE slug = ?",
                    (year, slug))
        fixed += 1
        print("  YEAR | %s -> %s | sheet date, name carries no year" % (slug, year))

    for slug, bad_date in sorted(CLEAR_DATE.items()):
        if slug not in state:
            print("  MISSING | %s" % slug)
            continue
        cur_start = state[slug][1] or ""
        if cur_start == "":
            continue
        if cur_start != bad_date:
            print("  SKIP | %s | date is %s, expected %s" % (slug, cur_start, bad_date))
            continue
        cur.execute("UPDATE tournaments SET start_date = NULL, end_date = NULL "
                    "WHERE slug = ?", (slug,))
        cleared += 1
        print("  DATE | %s | cleared %s (name prints its own year)" % (slug, bad_date))

    for slug, what in sorted(DELETE.items()):
        if slug not in state:
            continue
        # The fighters the event holds, so the deletion cannot leave a
        # person with no bout and no placing behind.
        names = [r[0] for r in cur.execute(
            "SELECT DISTINCT fighter FROM placings WHERE tournament = ? "
            "AND fighter <> ''", (slug,))]
        names += [r[0] for r in cur.execute(
            "SELECT DISTINCT red FROM bouts WHERE tournament = ? AND red <> '' "
            "UNION SELECT blue FROM bouts WHERE tournament = ? AND blue <> ''",
            (slug, slug))]
        cur.execute("DELETE FROM placings WHERE tournament = ?", (slug,))
        cur.execute("DELETE FROM bouts WHERE tournament = ?", (slug,))
        cur.execute("DELETE FROM tournaments WHERE slug = ?", (slug,))
        deleted += 1
        print("  DEL | %s | %s" % (slug, what))
        for name in sorted(set(names)):
            marks = ",".join("?" * 3)
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
    print("Summary: %d years set, %d corrupted dates cleared, %d events "
          "deleted, %d ghost fighters removed" % (fixed, cleared, deleted, orphans))


if __name__ == "__main__":
    main()