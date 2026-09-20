#!/bin/sh
# Rebuild the site and publish it to the GitHub Pages repo.
#
#   ./deploy.sh
#
# The public site repo is the default ../palmares-savate next to this
# directory; point SITE_DIR at it if it lives elsewhere.

set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
SITE="${SITE_DIR:-$DIR/../palmares-savate}"

echo "1/4 rebuild"
python3 "$DIR/build_db.py"
python3 "$DIR/export_ui.py"

echo "2/4 drift check"
python3 -m pytest "$DIR/tests/test_ui_drift.py" -q

echo "3/4 publish"
[ -d "$SITE/.git" ] || { echo "site repo not found at $SITE (set SITE_DIR)" >&2; exit 1; }
cp "$DIR"/ui/index.html "$DIR"/ui/app.js "$DIR"/ui/i18n.js "$DIR"/ui/data.js "$SITE/"
git -C "$SITE" add -A
if git -C "$SITE" diff --cached --quiet; then
  echo "    site unchanged"
else
  git -C "$SITE" commit -m "site export $(date -u +%Y-%m-%d)"
fi

echo "4/4 push"
git -C "$SITE" push

echo "done: https://artback.github.io/palmares-savate/"