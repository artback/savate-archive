"""Reading the geometry of a PDF, for adapters that parse federation paperwork.

Federations publish results as PDFs of tables, and a table in a PDF is not a
table - it is words at coordinates that happen to line up. Plain text extraction
loses the alignment that carries the meaning: in a poule cross-table, *which
column* a number sits in is what says whose score it is.

So this exposes words with their positions, and the two operations every such
table needs: grouping words into rows by their vertical position, and assigning
them to columns by their horizontal one. It deliberately does not try to be a
general table extractor. Each federation's layout is its own problem; this is
the shared floor those adapters stand on.

Uses poppler's pdftotext, which emits word boxes as XHTML. That keeps the
dependency list at what the project already has, and poppler is far better at
this than anything that would be added to it.
"""

import shutil
import subprocess
from dataclasses import dataclass

from bs4 import BeautifulSoup


class PdfUnavailable(RuntimeError):
    """pdftotext is not installed, so no PDF source can be read."""


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int

    @property
    def middle(self):
        return (self.x0 + self.x1) / 2


def available():
    return shutil.which("pdftotext") is not None


def words(path, first=None, last=None):
    """Every word in the document, with its box, in reading order.

    `first`/`last` are 1-based page numbers, as pdftotext counts them.
    """
    if not available():
        raise PdfUnavailable(
            "pdftotext (poppler) is required to read PDF sources: "
            "brew install poppler, or apt install poppler-utils")
    argv = ["pdftotext", "-bbox-layout"]
    if first:
        argv += ["-f", str(first)]
    if last:
        argv += ["-l", str(last)]
    argv += [str(path), "-"]
    done = subprocess.run(argv, capture_output=True, text=True)
    if done.returncode != 0:
        raise PdfUnavailable(f"pdftotext failed on {path}: {done.stderr.strip()}")

    soup = BeautifulSoup(done.stdout, "html.parser")
    out = []
    for number, page in enumerate(soup.find_all("page"), first or 1):
        for w in page.find_all("word"):
            text = " ".join(w.get_text().split())
            if not text:
                continue
            out.append(Word(text=text,
                            x0=float(w["xmin"]), x1=float(w["xmax"]),
                            top=float(w["ymin"]), bottom=float(w["ymax"]),
                            page=number))
    return out


def page_count(path):
    done = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True)
    for line in done.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1])
    return 0


def by_page(words_):
    pages = {}
    for w in words_:
        pages.setdefault(w.page, []).append(w)
    return pages


def rows(words_, tolerance=3.0, glue=0.0):
    """Group words into visual lines, top to bottom, each left to right.

    Words on one line rarely share an exact top - superscripts, different font
    sizes and cell padding all shift it - so lines are formed by proximity, not
    equality. The tolerance is in points and suits 8-12pt tables.

    Extraction sometimes breaks a single word in two - "CHAM" and "PIONNE",
    "M" and "ICHAT" - leaving almost no gap between the halves. Passing a `glue`
    width rejoins pairs closer than that, on a shared baseline.

    It is off by default, and deliberately. The margin is thin: a genuine split
    measured 0.60pt in one document where neighbouring cells sat 0.81pt apart.
    A threshold between them repaired a handful of names in one file and lost a
    whole fighter from a poule in another, and losing a competitor is far worse
    than an oddly spelled one - a bad spelling is visible and can be linked by
    hand, while a missing row looks like a bout that never happened. Adapters
    that have checked the trade on their own documents can ask for it.
    """
    # Page first. Page 2's header sits at the same height as page 1's, so
    # grouping on the coordinate alone silently interleaves every page in the
    # document into one set of lines.
    lines = []
    for w in sorted(words_, key=lambda w: (w.page, w.top, w.x0)):
        if (lines and lines[-1][0].page == w.page
                and abs(lines[-1][0].top - w.top) <= tolerance):
            lines[-1].append(w)
        else:
            lines.append([w])

    out = []
    for line in lines:
        joined = []
        for w in sorted(line, key=lambda w: w.x0):
            # `glue > 0` is not redundant: words routinely overlap slightly,
            # which makes their gap negative, so "closer than zero" would join
            # pairs that gluing is switched off for.
            if (glue > 0 and joined and w.x0 - joined[-1].x1 < glue
                    and abs(w.top - joined[-1].top) < 0.5
                    and abs(w.bottom - joined[-1].bottom) < 0.5):
                previous = joined[-1]
                joined[-1] = Word(text=previous.text + w.text,
                                  x0=previous.x0, x1=w.x1,
                                  top=min(previous.top, w.top),
                                  bottom=max(previous.bottom, w.bottom),
                                  page=previous.page)
            else:
                joined.append(w)
        out.append(joined)
    return out


def text_of(line, join=" "):
    return join.join(w.text for w in line)


def in_band(word, left, right):
    """Is a word inside a column band? Judged on its midpoint.

    Midpoint, not edges: a wide word in a narrow cell overhangs both sides, and
    testing its edges would put it in no column at all.
    """
    return left <= word.middle < right


def columns(anchors, page_width):
    """Column bands from the x of each column's anchor word.

    Each band runs from its own anchor to the next, so a value belongs to the
    column it starts under. Returns [(left, right)], one per anchor.
    """
    edges = sorted(anchors) + [page_width]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def find(words_, predicate):
    return [w for w in words_ if predicate(w)]


def below(words_, y, margin=0.0):
    return [w for w in words_ if w.top > y + margin]


def between(words_, top, bottom):
    return [w for w in words_ if top < w.top < bottom]
