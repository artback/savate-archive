#!/bin/sh
# Re-read the organisers' pages, rebuild the ringside page, refresh the database.
# Exits non-zero without touching the outputs if the scrape fails, so a bad run
# never replaces good data.
set -e
cd "$(dirname "$0")"
python3 scrape_assaut.py --quiet
python3 build_site.py --out ringside.html
python3 build_results.py            # independent re-parse of raw/, cross-checks the scraper
python3 build_db.py                 # canonical rows -> savate.csv/.json/.db
