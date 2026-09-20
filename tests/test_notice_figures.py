"""The notice is the archive's honesty claim, so its numbers may not be text.

The notice quotes archive-wide figures (the red corner's share of wins, the
bouts without published warnings, the unmatched country spellings, the pools
shown ex æquo). A figure typed into the text goes stale the day a new sheet
lands, and the one document the reader trusts most becomes the first to lie.
So the export computes the figures (the report block in export_ui.py), the
notice strings carry only placeholders, and this test re-derives each figure
from the database and refuses a notice string that hardcodes a fact about the
data.
"""

import json
import re
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ui" / "data.js"
I18N = ROOT / "ui" / "i18n.js"
DB = ROOT / "savate.db"

# The notice strings that quote archive-wide figures, and the placeholder each
# one must carry. The others quote rules of the sport (the scale, the podium
# era), which do not move when the archive grows.
FIGURED_KEYS = {
    "cornersB": "{redWin}",
    "ladderB": "{poules}",
    "crossB": "{noWarn}",
    "refuseB": "{nations}",
}
# The numbers the sport's rules fix, not the archive. These may stay in text.
ALLOWED_WORD_NUMBERS = ("huit", "eight", "ocho")


def load_ui():
    raw = DATA.read_text(encoding="utf-8")
    prefix = "window.SAVATE="
    return json.loads(raw[len(prefix):raw.rindex("}") + 1])


def notice_strings():
    """Every occurrence of a figured notice string, in all three languages."""
    raw = I18N.read_text(encoding="utf-8")
    out = {}
    for key in FIGURED_KEYS:
        pattern = r'"notice\.%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key)
        out[key] = re.findall(pattern, raw)
    return out


class NoticeFigures(unittest.TestCase):
    def setUp(self):
        if not DATA.exists():
            self.skipTest("ui/data.js has not been exported yet")
        if not I18N.exists():
            self.skipTest("ui/i18n.js is missing")
        if not DB.exists():
            self.skipTest("savate.db has not been built yet")
        self.ui = load_ui()
        self.db = sqlite3.connect(DB)

    def tearDown(self):
        self.db.close()

    def test_the_red_corner_share_matches_the_database(self):
        decisive = self.db.execute(
            "SELECT COUNT(*) FROM bouts WHERE winner_corner IN ('red','blue')"
        ).fetchone()[0]
        red_won = self.db.execute(
            "SELECT COUNT(*) FROM bouts WHERE winner_corner = 'red'"
        ).fetchone()[0]
        expected = round(100.0 * red_won / decisive, 1) if decisive else 0
        self.assertEqual(self.ui["report"]["red_win_pct"], expected)

    def test_bouts_without_published_warnings_match_the_database(self):
        got = self.db.execute(
            "SELECT COUNT(*) FROM bouts"
            " WHERE red_warnings = '' AND blue_warnings = ''"
        ).fetchone()[0]
        self.assertEqual(self.ui["report"]["bouts_no_warnings"], got)

    def test_unmatched_nations_match_the_exported_table(self):
        unmatched = sum(1 for n in self.ui["nations"] if not n[3])
        self.assertEqual(self.ui["report"]["nations_unmatched"], unmatched)

    def test_unresolved_poules_match_the_exported_tables(self):
        unresolved = sum(1 for p in self.ui["poules"] if len(p) > 4 and p[4])
        self.assertEqual(self.ui["report"]["poules_unresolved"], unresolved)

    def test_every_figured_notice_string_is_present_in_all_three_languages(self):
        for key, values in notice_strings().items():
            self.assertEqual(len(values), 3, f"notice.{key} must exist in fr, en, es")

    def test_figured_notice_strings_carry_their_placeholder(self):
        for key, values in notice_strings().items():
            for value in values:
                self.assertIn(FIGURED_KEYS[key], value, f"notice.{key}")

    def test_figured_notice_strings_carry_no_literal_figure(self):
        """A digit in these strings is a dataset fact hardcoded back in, and a
        word-number is the same regression spelled out. Neither survives."""
        for key, values in notice_strings().items():
            for value in values:
                stripped = re.sub(r"\{[a-zA-Z]+\}", " ", value)
                self.assertIsNone(re.search(r"\d", stripped), f"notice.{key}: {stripped!r}")
                for word in ALLOWED_WORD_NUMBERS:
                    self.assertIsNone(
                        re.search(r"\b%s\b" % word, stripped, re.IGNORECASE),
                        f"notice.{key}: literal {word!r}",
                    )


if __name__ == "__main__":
    unittest.main()