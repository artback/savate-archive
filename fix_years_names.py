#!/usr/bin/env python3
"""Event metadata repairs the pipeline did not do, applied to the database.

Run after build_db.py and before export_ui.py. Idempotent: a second run
finds nothing left to do.

Three repairs, all on the tournaments table only:

1. A missing year is recovered where the document says one - the printed
   name first ("St Christol les Ales 2024"), the sheet dates second.
2. A printed year that contradicts the stored one wins: the federation's
   own title ("Championnat du Monde Assaut 2012") beats a year the ingest
   guessed. A name carrying a season label ("Angoulême 2024-25") names two
   years, neither of them the event's, and is left alone.
3. An event number printed before the name in the source ("724 world
   cadet cup 2021") is stripped from the name. A leading number that is
   the event year itself ("2008 World Savate..."), a day before a month
   name ("11 Mars 2023"), or an ordinal ("1er Gant", "3e tour", "1/2
   finales") is kept.

Slugs and the competition grouping are never touched: the name is what a
reader sees, the slug is a stable key. What the repairs cannot reach -
neither name nor date carrying a year - is printed at the end, not
guessed.
"""

import re
import sqlite3

DB = "savate.db"

# A year is four digits not part of a longer run, so "04/06/20416" yields
# nothing rather than a 2041.
YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
# "2024-25" or "2024-2025": a season, not an event year.
SEASON = re.compile(r"(?:19|20)\d{2}\s*[-–]\s*(?:\d{4}|\d{2})(?!\d)")
# An event number: one to four digits followed by a space, at the start.
PREFIX = re.compile(r"^\d{1,4}\s+")
# A day before a month name is a date, not an event number.
MONTHS = {
    "janvier", "fevrier", "février", "mars", "avril", "mai", "juin",
    "juillet", "aout", "août", "septembre", "octobre", "novembre",
    "decembre", "décembre", "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
}


def repair_year(name, year, start, end):
    """The year the document states, or the stored year, or nothing."""
    if SEASON.search(name or ""):
        return year
    printed = set(YEAR.findall(name or ""))
    if len(printed) == 1:
        return printed.pop()
    if not year:
        for d in (start, end):
            if d and d[:4].isdigit():
                return d[:4]
    return year


def clean_name(name):
    """Strip a leading event number, keeping years, dates and ordinals."""
    m = PREFIX.match(name or "")
    if not m:
        return name
    if re.fullmatch(r"(?:19|20)\d{2}", m.group(0).strip()):
        return name
    rest = name[m.end():]
    first = rest.split(" ", 1)[0].lower() if rest else ""
    if first in MONTHS:
        return name
    return rest


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    rows = cur.execute(
        "SELECT slug, name, year, start_date, end_date FROM tournaments"
    ).fetchall()

    # One name arrived as its URL-encoded source filename: "20" is the
    # encoded space, so "... 20 2013 20FEVRIER 202016 ..." reads
    # "13 fevrier 2016" - the sheet's own date, which the generic year rule
    # misreads as a 2013.
    DECODED = {
        "r-20finales-20espoirs-20mf-20-2013-20fevrier-202016-20billo":
            ("Finales Espoirs M/F 13 Février 2016, Billère", "2016"),
    }

    recovered = corrected = stripped = 0
    unknown = []

    for slug, name, year, start, end in rows:
        name = name or ""
        year = (year or "").strip()

        if slug in DECODED:
            new_name, new_year = DECODED[slug]
        else:
            new_year = repair_year(name, year, start, end)
            new_name = clean_name(name)

        if new_year != year or new_name != name:
            cur.execute("UPDATE tournaments SET year = ?, name = ? "
                        "WHERE slug = ?", (new_year, new_name, slug))
            if year and new_year != year:
                corrected += 1
            elif new_year != year:
                recovered += 1
            if new_name != name:
                stripped += 1
            print("  FIX | %s" % slug)
            if new_year != year:
                print("        year %r -> %r" % (year, new_year))
            if new_name != name:
                print("        name %r -> %r" % (name, new_name))
        if not new_year:
            unknown.append((slug, name))

    db.commit()

    print("Summary: %d years recovered, %d corrected, %d names cleaned, "
          "%d still without a year" %
          (recovered, corrected, stripped, len(unknown)))
    for slug, name in unknown:
        print("  UNKNOWN | %s | %s" % (slug, name))


if __name__ == "__main__":
    main()