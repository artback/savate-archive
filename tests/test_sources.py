"""Fetching, and the one URL detail that decides whether old savate exists.

For anything older than a season or two the Wayback Machine is not a fallback,
it is the source - federations reorganise and drop their archives. A capture URL
without a modifier returns the Machine's viewer page, which is HTML wrapped
around the document rather than the document, so a PDF fetched that way arrives
as a styled web page and every adapter fails on it for reasons that look like
the adapter's fault. Eighteen of this archive's twenty unreachable documents
were exactly that.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from savate import sources  # noqa: E402


class TestWaybackCaptures:
    def test_a_bare_capture_url_asks_for_the_original_bytes(self):
        assert sources.as_captured(
            "http://web.archive.org/web/20090815142529/http://x.com/r.pdf"
        ) == "http://web.archive.org/web/20090815142529id_/http://x.com/r.pdf"

    def test_https_captures_too(self):
        assert "20090319id_/" in sources.as_captured(
            "https://web.archive.org/web/20090319/http://x.com/a.html")

    def test_a_url_that_already_asks_is_left_alone(self):
        url = "https://web.archive.org/web/20170625031753id_/http://x.com/r.pdf"
        assert sources.as_captured(url) == url

    def test_other_modifiers_are_not_overwritten(self):
        # "if_" (iframe) and "im_" (image) are the Machine's own; rewriting one
        # would silently ask for something other than what the caller wanted.
        for modifier in ("if_", "im_", "cs_", "js_"):
            url = f"https://web.archive.org/web/20200101{modifier}/http://x.com/a"
            assert sources.as_captured(url) == url

    def test_an_ordinary_url_is_untouched(self):
        for url in ("https://fisav.sport/download.php?id=61",
                    "https://www.ffsavate.com/content/uploads/2024/x.pdf",
                    "/Users/someone/local/file.pdf"):
            assert sources.as_captured(url) == url
