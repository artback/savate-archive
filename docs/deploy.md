# Deploying the site

## What is a deployment

`ui/` is the whole site: `index.html`, `app.js`, `i18n.js`, `data.js`.
Self-contained, no build step at deploy time, no server-side code, no
accounts, no cookies. Deploying means putting these four files (plus any
static assets they reference) on a static host and pointing a domain at it.

## Pre-deploy checklist

1. **Fresh export.** `ui/data.js` must be newer than the last `tournaments.json`
   change. Rebuild everything, in order:
   ```
   python3 build_db.py
   python3 export_ui.py
   ```
2. **Tests green.**
   ```
   python3 -m pytest -q
   ```
3. **Drift check.** The site must match the database it was built from.
   `tests/test_ui_drift.py` compares `ui/data.js` against `savate.db`
   (events, bouts, placings, slugs, per-event source, no ghost persons) and
   fails on any stale export:
   ```
   python3 -m pytest tests/test_ui_drift.py -q
   ```
4. **No secrets, no raw data.** The deploy carries only `ui/`. Never upload
   `raw_sources/`, `savate.db`, `savate.csv`, `placings.csv` or
   `erasure.json`: the first two are the archive's provenance, and the last
   names the people who asked to be removed.
5. **Contact address.** Replace the placeholder in `ui/app.js`
   (`CONTACT_EMAIL`, currently `archivist@palmares-savate.example`) with the
   real inbox before the first public deploy. `.example` is reserved and can
   never deliver, so a forgotten placeholder is visible, not silent.

## Static host

Any static host works (GitHub Pages, Netlify, Cloudflare Pages, S3+CloudFront,
or a plain nginx/vhost). Requirements:

- **HTTPS only.** Redirect HTTP to HTTPS. This is personal data, even if it is
  personal data that is already public: the transport must not add risk.
- **No server-side processing.** The four files are all there is. If the host
  offers a "server" plan, do not use it — a static bucket is the safer shape.
- **No tracking by default.** No analytics, no ads, no third-party scripts.
  The privacy notice says the site collects nothing; keep it true. Adding a
  tracker later is a privacy change and needs the notice updated first.

## After every publish

- Open the site in a clean browser profile: home, one event page, one fighter
  page, the notice page, in each of the three languages.
- Confirm the footer count matches `export_ui.py`'s last line.
- `git` the `ui/` export into the deploy branch if the host pulls from git;
  otherwise upload the four files and note the date.

## Rollback

A previous `ui/data.js` plus the matching `app.js`/`i18n.js`/`index.html` is a
complete rollback. Because `data.js` is regenerated, never hand-edit it: the
rollback unit is the whole `ui/` directory of a known-good export.