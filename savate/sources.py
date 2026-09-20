"""Fetching a source once and keeping the bytes.

Every federation adapter needs the same thing: pull a document, keep exactly
what was pulled, and do not pull it again while working on the parser. Keeping
the original is not an optimisation - it is what makes a parsing bug
investigable a week later, and what stops a re-run being at the mercy of a site
that has since changed or gone.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path("raw_sources")
# The Wayback Machine's index. Federations reorganise their sites and drop the
# old results with them, so for anything older than a season or two this is not
# a fallback - it is the source.
CDX = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web/{timestamp}id_/{url}"
AGENT = "Mozilla/5.0 (savate-results-archive)"
DELAY = 0.4
TIMEOUT = 60


def is_url(source):
    return bool(re.match(r"https?://", str(source)))


def cache_path(url, suffix="", cache=CACHE):
    """A stable local name for a URL: its tail, plus a hash to keep it unique."""
    tail = re.sub(r"[^\w.-]+", "-", str(url).rsplit("/", 1)[-1])[:60].strip("-")
    digest = hashlib.sha256(str(url).encode()).hexdigest()[:10]
    return Path(cache) / f"{tail or 'page'}-{digest}{suffix}"


# A Wayback capture URL carries a timestamp, optionally followed by a modifier
# that says what to serve. Without one the Machine returns its own viewer page
# with a banner injected, which is HTML wrapped around the document rather than
# the document - so a PDF fetched that way arrives as a styled web page and
# every adapter fails on it. "id_" asks for the bytes exactly as captured.
_WAYBACK = re.compile(r"^(https?://web\.archive\.org/web/)(\d{4,14})(/)", re.I)


def as_captured(url):
    """A Wayback URL that returns the original bytes, not the viewer page."""
    return _WAYBACK.sub(r"\1\2id_\3", str(url))


def fetch(source, cache=CACHE, refresh=False, binary=True):
    """Local path holding `source`, downloading it if it is a URL.

    A local path is returned untouched - an adapter should not care whether its
    document arrived over the network or was sitting on disk.
    """
    source = as_captured(source) if is_url(source) else source
    if not is_url(source):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"{source} does not exist")
        return path

    suffix = ".pdf" if str(source).lower().endswith(".pdf") else ""
    path = cache_path(source, suffix, cache)
    if path.exists() and not refresh:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(str(source), headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read()
        kind = response.headers.get_content_type()
    # A site that answers a missing document with a styled 404 page is common
    # enough that writing the page to a .pdf and failing later is the likelier
    # outcome than a clean error.
    if binary and body[:5] != b"%PDF-" and kind == "text/html":
        raise ValueError(f"{source} returned {kind}, not a document")
    path.write_bytes(body)
    time.sleep(DELAY)
    return path


def text(source, cache=CACHE, refresh=False):
    path = fetch(source, cache, refresh, binary=False)
    return path.read_text(encoding="utf-8", errors="replace")


def snapshots(url, domain=False, mimetype=None, limit=20000, since=None):
    """[{timestamp, url, mimetype}] the Wayback Machine holds for a URL or domain.

    `id_` snapshots are requested when fetching, which return the bytes as they
    were captured rather than the rewritten page the Wayback viewer serves. For
    a PDF the difference is the difference between the document and an HTML
    frame around it.
    """
    query = {"url": url, "output": "json", "collapse": "urlkey",
             "fl": "timestamp,original,mimetype", "limit": str(limit),
             "filter": "statuscode:200"}
    if domain:
        query["matchType"] = "domain"
    if since:
        query["from"] = str(since)
    parts = urllib.parse.urlencode(query)
    if mimetype:
        parts += f"&filter={urllib.parse.quote('mimetype:' + mimetype)}"
    request = urllib.request.Request(f"{CDX}?{parts}",
                                     headers={"User-Agent": AGENT})
    # The index answers 503 under load rather than queueing, and a crawl makes
    # enough calls to meet that regularly. Backing off is the price of using it.
    body = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503, 502, 504) or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    rows = json.loads(body or "[]")
    if not rows:
        return []
    return [{"timestamp": r[0], "url": r[1],
             "mimetype": r[2] if len(r) > 2 else ""} for r in rows[1:]]


def archived(url, timestamp=None):
    """The Wayback URL for a capture of `url`, newest unless one is named."""
    if timestamp is None:
        captures = snapshots(url)
        if not captures:
            raise FileNotFoundError(f"the Wayback Machine has no capture of {url}")
        timestamp = captures[-1]["timestamp"]
    return WAYBACK.format(timestamp=timestamp, url=url)


def fetch_archived(url, timestamp=None, cache=CACHE, refresh=False):
    """A document from the Wayback Machine, cached under its own name.

    Falls back to the live URL first: a document still being served is fresher
    than a capture of it, and leaves the archive's bandwidth for the documents
    that need it.
    """
    try:
        return fetch(url, cache, refresh)
    except (urllib.error.URLError, ValueError, FileNotFoundError):
        return fetch(archived(url, timestamp), cache, refresh)
