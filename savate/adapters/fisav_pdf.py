"""Adapter for FISav championship results PDFs.

The federation publishes one PDF per championship, one page per weight class,
and each page carries the whole class: the poule cross-tables with points and
warnings, the poule standings, and the knockout bracket through to the winner.

The cross-table is the interesting part. It is a grid with one column pair
(Points, Avert.) per fighter, and one row per pairing, where a row fills exactly
the two columns of the fighters who met. Which column a number sits in is the
only thing that says whose score it is, so this reads positions, not text.

Two things in the page check the reading, and both are used:

  * the table's own totals row must equal the columns it sits under
  * the standings panel beside it states each fighter's points and warnings

An extraction that disagrees with either is reported rather than returned. A
silently mis-read cross-table would produce plausible, wrong history, which is
worse than no history.

Medallist-only documents carry no bouts. They are recognised and skipped with a
note, not forced to yield rows they do not contain.

This reads one of FISav's layouts, not all of them. The archive also carries a
"pool results" family - fighters as rows, slot codes A1/A2/A3, POINTS and AVT in
separate blocks, TOTAL and RANK lines - which is a different generator and
belongs in its own adapter rather than in branches here. A document in that
layout yields no bouts and says so, which is the correct answer for a reader
that does not understand it.
"""

import itertools
import re

from savate import normalize as norm
from savate import pdf
from savate.schema import Bout, Report, Tournament, phase_of

NAME = "fisav_pdf"
DESCRIPTION = "FISav results PDF, poule-grid layout (fighters as columns)"

CATEGORY = re.compile(r"Cat[ée]gorie\s*:\s*(?P<label>.+)")
RANK = re.compile(r"^(\d+)[ºo°]$")
# The bracket's rightmost column names the champion; it is not a round.
WINNER_COLUMN = re.compile(r"vainqueur|winner|ganador", re.I)
# "Country - Fighter Name", as every box and standings row is written.
ENTRANT = re.compile(r"^(?P<country>[^-]+?)\s+-\s+(?P<name>.+)$")
# Furniture that sits inside the same column bands as real data and would
# otherwise be read as part of a fighter's name: the page footer, and the
# tie-break footnote printed under the standings.
FOOTER = re.compile(r"^\d+\s*/\s*\d+$")
FOOTNOTE = re.compile(r"^\(\*\)")


def _is_furniture(text):
    text = " ".join(str(text).split())
    return not text or bool(FOOTER.match(text)) or bool(FOOTNOTE.match(text))


def _cluster(line, gap=12.0):
    """Split one line's words into groups separated by a horizontal gap.

    The bracket's column headings are multi-word ("1/2 finales"), so they cannot
    be read word by word; they are whatever sits together with space around it.
    """
    groups = []
    for w in line:
        if groups and w.x0 - groups[-1][-1].x1 <= gap:
            groups[-1].append(w)
        else:
            groups.append([w])
    return groups


def _bands(anchors, end=10_000.0):
    edges = list(anchors) + [end]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _cell(line, left, right):
    return [w for w in line if pdf.in_band(w, left, right)]


def _number(words):
    text = "".join(w.text for w in words).replace(",", ".")
    try:
        return int(float(text))
    except ValueError:
        return None


def _join_name(sofar, part):
    """Append a name fragment, honouring a hyphen the layout broke a name at.

    A column too narrow for "LECLERE-MESSEBEL" wraps it after the hyphen. Joining
    those fragments with a space invents a name nothing else on the page uses,
    and the fighter then matches no standings row.
    """
    if not sofar:
        return part
    return sofar + part if sofar.endswith("-") else f"{sofar} {part}"


def _split_entrant(text):
    m = ENTRANT.match(" ".join(text.split()))
    return (m.group("country").strip(), m.group("name").strip()) if m else ("", text.strip())


class Page:
    """One weight class: its category, its poules, and its bracket."""

    def __init__(self, words, report):
        self.report = report
        self.words = words
        self.lines = pdf.rows(words)
        self.category = ""
        for line in self.lines[:6]:
            m = CATEGORY.search(pdf.text_of(line))
            if m:
                self.category = " ".join(m.group("label").replace("->", " ").split())
                break
        # The standings panel sits to the right of the cross-tables; everything
        # left of it is the grid.
        anchors = [w.x0 for w in words if w.text.startswith("Classement")]
        self.split = min(anchors) - 8 if anchors else 350.0
        self.bracket_top = next((line[0].top for line in self.lines
                                 if WINNER_COLUMN.search(pdf.text_of(line))), None)

    # --- poules ---------------------------------------------------------
    def poule_regions(self):
        """(label, top, bottom) for each poule block on the page."""
        starts = []
        for line in self.lines:
            for i, w in enumerate(line):
                if w.text == "Poule" and i + 1 < len(line):
                    starts.append((line[i + 1].text, w.top))
        out = []
        for i, (label, top) in enumerate(starts):
            bottom = (starts[i + 1][1] if i + 1 < len(starts)
                      else (self.bracket_top if self.bracket_top else 10_000.0))
            out.append((label, top, bottom))
        return out

    def poule(self, label, top, bottom):
        """{names, pairings, totals, standings} for one poule, or None."""
        region = [line for line in self.lines
                  if top <= line[0].top < bottom]
        left = [[w for w in line if w.x1 <= self.split] for line in region]
        left = [line for line in left if line]

        header = next((line for line in left
                       if line and all(w.text in ("Points", "Avert.") for w in line)
                       and any(w.text == "Points" for w in line)), None)
        if not header:
            self.report.problem(f"{self.category} poule {label}: no Points/Avert. "
                                f"header - layout not recognised")
            return None

        anchors = [w.x0 for w in header]
        bands = _bands(anchors, self.split)
        count = sum(1 for w in header if w.text == "Points")
        # Fighter i owns the (Points, Avert.) pair at bands[2i], bands[2i+1].
        points_bands = [bands[2 * i] for i in range(count)]
        warn_bands = [bands[2 * i + 1] for i in range(count)]
        # A fighter's whole column, for reading the name that heads it.
        name_bands = [(points_bands[i][0],
                       points_bands[i + 1][0] if i + 1 < count else self.split)
                      for i in range(count)]

        names = ["" for _ in range(count)]
        for line in left:
            if line[0].top >= header[0].top:
                continue
            if any(w.text == "Poule" for w in line):
                continue        # the block's own label, not a fighter
            for i, (a, b) in enumerate(name_bands):
                part = " ".join(w.text for w in _cell(line, a, b))
                if part:
                    names[i] = _join_name(names[i], part)
        if not all(names):
            self.report.problem(f"{self.category} poule {label}: a column has no "
                                f"fighter name ({names})")
            return None

        body = []
        for line in left:
            if line[0].top <= header[0].top:
                continue
            row = []
            for i in range(count):
                points = _number(_cell(line, *points_bands[i]))
                warnings = _number(_cell(line, *warn_bands[i]))
                row.append(None if points is None else (points, warnings or 0))
            if any(cell is not None for cell in row):
                body.append(row)
        if not body:
            self.report.problem(f"{self.category} poule {label}: no scored rows")
            return None

        totals, pairing_rows = body[-1], body[:-1]
        pairings = []
        for row in pairing_rows:
            filled = [i for i, cell in enumerate(row) if cell is not None]
            if len(filled) != 2:
                self.report.problem(
                    f"{self.category} poule {label}: a row fills {len(filled)} "
                    f"columns, and a bout is between two fighters")
                return None
            a, b = filled
            pairings.append({"red": names[a], "blue": names[b],
                             "red_points": row[a][0], "red_warnings": row[a][1],
                             "blue_points": row[b][0], "blue_warnings": row[b][1]})

        expected = count * (count - 1) // 2
        if len(pairings) != expected:
            self.report.problem(
                f"{self.category} poule {label}: {len(pairings)} pairings read, "
                f"but {count} fighters make {expected}")

        # The totals row is the page checking its own arithmetic; use it.
        for i, name in enumerate(names):
            if totals[i] is None:
                continue
            points = sum(p["red_points"] if p["red"] == name else p["blue_points"]
                         for p in pairings if name in (p["red"], p["blue"]))
            if points != totals[i][0]:
                self.report.problem(
                    f"{self.category} poule {label}: {name} sums to {points} but "
                    f"the sheet's total says {totals[i][0]}")

        return {"label": label, "names": names, "pairings": pairings,
                "standings": self.standings(top, bottom)}

    def standings(self, top, bottom):
        """The printed classement: name -> points, warnings, wins, weight, country.

        This panel is the only place on the page that says which country a
        fighter represents - the cross-table heads its columns with names alone.
        """
        out = {}
        region = [line for line in self.lines if top <= line[0].top < bottom]
        right = [[w for w in line if w.x0 >= self.split] for line in region]
        right = [line for line in right if line]
        header = next((line for line in right
                       if any(w.text == "Pts" for w in line)), None)
        if not header:
            return out
        anchors = {w.text: w.x0 for w in header}
        name_from = anchors.get("Tireur", 0)
        pts_from = anchors.get("Pts", 10_000.0)
        bands = _bands(sorted(anchors.values()), 10_000.0)
        keyed = {t: b for t, b in zip(sorted(anchors, key=lambda k: anchors[k]), bands)}

        current = None
        for line in right:
            if line[0].top <= header[0].top:
                continue
            if FOOTNOTE.match(pdf.text_of(line)):
                break           # everything below is the tie-break footnote
            first = line[0].text
            if RANK.match(first):
                printed = " ".join(w.text for w in _cell(line, name_from, pts_from))
                country, name = _split_entrant(printed)
                current = name
                out[current] = {
                    "country": country,
                    "points": _number(_cell(line, *keyed.get("Pts", (0, 0)))),
                    "warnings": _number(_cell(line, *keyed.get("Aver.", (0, 0)))),
                    "wins": _number(_cell(line, *keyed.get("Vic", (0, 0)))),
                    "weight": None,
                }
                weight = " ".join(w.text for w in _cell(line, *keyed.get("Poids", (0, 0))))
                m = re.search(r"\d+(?:\.\d+)?", weight)
                if m:
                    out[current]["weight"] = float(m.group())
            elif current is not None:
                # a name that wrapped onto a second line
                tail = " ".join(w.text for w in _cell(line, name_from, pts_from))
                if tail and not tail.lower().startswith("kg"):
                    merged = f"{current} {tail}".strip()
                    out[merged] = out.pop(current)
                    current = merged
        return out

    # --- bracket --------------------------------------------------------
    def bracket(self):
        """[(phase, [entrants in vertical order])] left to right."""
        if self.bracket_top is None:
            return []
        header = next(line for line in self.lines
                      if line[0].top == self.bracket_top)
        labels = [(pdf.text_of(g), g[0].x0) for g in _cluster(header)]
        bands = _bands([x for _, x in labels])

        columns = []
        for (label, _), (a, b) in zip(labels, bands):
            entries = []
            for line in self.lines:
                if line[0].top <= self.bracket_top:
                    continue
                text = " ".join(w.text for w in _cell(line, a, b))
                if not _is_furniture(text):
                    entries.append(_split_entrant(text))
            columns.append((label, entries))
        return columns


def _poule_bouts(page, block, slug, index, report):
    """Canonical bouts from one poule's cross-table."""
    from savate import rules

    standings = block["standings"]
    # The grid and the panel print the same names with different line breaks, so
    # they are matched on a folded key rather than character for character.
    panel = {norm.fold(n).replace(" ", ""): s for n, s in standings.items()}
    country = {n: s.get("country", "") for n, s in standings.items()}
    out = []
    for n, pairing in enumerate(block["pairings"], 1):
        red, blue = pairing["red"], pairing["blue"]
        red_points, blue_points = pairing["red_points"], pairing["blue_points"]
        corner = ("red" if red_points > blue_points else
                  "blue" if blue_points > red_points else "")
        won, lost = ((red_points, blue_points) if corner == "red"
                     else (blue_points, red_points))
        decision = rules.decision_from_points(won, lost) if corner else ""
        if corner and not decision:
            report.problem(f"{page.category} poule {block['label']}: "
                           f"{red} {red_points}-{blue_points} {blue} is not a "
                           f"scoreline this sport produces")
        entry = panel.get(norm.fold(red).replace(" ", ""), {})
        blue_entry = panel.get(norm.fold(blue).replace(" ", ""), {})
        out.append(Bout(
            tournament=slug,
            bout_id=f"{slug}-p{index:02d}-{block['label']}{n:02d}",
            phase="poule", poule=block["label"],
            red=red, red_country=country.get(red) or entry.get("country", ""),
            blue=blue, blue_country=country.get(blue) or blue_entry.get("country", ""),
            red_points=str(red_points), blue_points=str(blue_points),
            red_warnings=str(pairing["red_warnings"]),
            blue_warnings=str(pairing["blue_warnings"]),
            winner_corner=corner,
            winner={"red": red, "blue": blue}.get(corner, ""),
            loser={"red": blue, "blue": red}.get(corner, ""),
            decision=decision,
            status="decided" if corner else "unresolved",
            result_source="reported" if corner else "",
            **norm.category(page.category),
        ))

    # The panel beside the grid states each fighter's totals. Disagreeing with
    # it means the grid was read wrongly, and a wrong history is worse than none.
    for name, printed in standings.items():
        key = norm.fold(name).replace(" ", "")
        mine = sum(p["red_points"] if norm.fold(p["red"]).replace(" ", "") == key
                   else p["blue_points"]
                   for p in block["pairings"]
                   if key in (norm.fold(p["red"]).replace(" ", ""),
                              norm.fold(p["blue"]).replace(" ", "")))
        if printed.get("points") is not None and mine != printed["points"]:
            report.problem(f"{page.category} poule {block['label']}: read {name} "
                           f"on {mine} points, the standings panel says "
                           f"{printed['points']}")
    return out


def _bracket_bouts(page, columns, slug, index, report):
    """Canonical bouts from the knockout bracket.

    Column n holds the fighters of a round and column n+1 holds that round's
    winners, so a round is read by pairing its entrants two at a time and taking
    the winner from the column to its right.
    """
    out = []
    rounds = [(label, entries) for label, entries in columns
              if not WINNER_COLUMN.search(label)]
    winners = [entries for label, entries in columns
               if WINNER_COLUMN.search(label)]
    following = [entries for _, entries in rounds[1:]] + winners

    for r, ((label, entries), next_round) in enumerate(zip(rounds, following)):
        phase = phase_of(label)
        if not phase:
            report.problem(f"{page.category}: bracket column {label!r} is not a "
                           f"round this understands")
            continue
        if len(entries) != 2 * len(next_round):
            report.problem(f"{page.category} {label}: {len(entries)} fighters "
                           f"cannot produce {len(next_round)} winners")
            continue
        for n, (a, b) in enumerate(zip(entries[::2], entries[1::2])):
            (a_country, a_name), (b_country, b_name) = a, b
            winner = next_round[n][1] if n < len(next_round) else ""
            corner = ("red" if winner == a_name else
                      "blue" if winner == b_name else "")
            if not corner:
                report.problem(f"{page.category} {label}: {winner!r} won a bout "
                               f"between {a_name!r} and {b_name!r}")
            out.append(Bout(
                tournament=slug,
                bout_id=f"{slug}-p{index:02d}-{phase}{n + 1:02d}",
                phase=phase,
                red=a_name, red_country=a_country,
                blue=b_name, blue_country=b_country,
                winner_corner=corner,
                winner={"red": a_name, "blue": b_name}.get(corner, ""),
                loser={"red": b_name, "blue": a_name}.get(corner, ""),
                status="decided" if corner else "unresolved",
                result_source="reported" if corner else "",
                **norm.category(page.category),
            ))
    return out


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout], Report) from one FISav results PDF."""
    from savate import sources

    report = Report(source=str(source), adapter=NAME)
    path = (sources.fetch_archived(str(source))
        if options.get("archived")
        else sources.fetch(source, refresh=options.get("refresh", False)))
    tournament = Tournament(slug=slug, source=str(source), adapter=NAME,
                            **(meta or {}))

    pages = pdf.by_page(pdf.words(path))
    report.read = len(pages)
    bouts, classes = [], 0
    for index in sorted(pages):
        page = Page(pages[index], report)
        if not page.category:
            continue        # a cover, a medal table, or a page of signatures
        classes += 1
        for label, top, bottom in page.poule_regions():
            block = page.poule(label, top, bottom)
            if block:
                bouts.extend(_poule_bouts(page, block, slug, index, report))
        bouts.extend(_bracket_bouts(page, page.bracket(), slug, index, report))

    report.notes["weight_classes"] = classes
    if not bouts:
        report.notes["kind"] = "no bouts found - probably a medallists document"
    return tournament, bouts, report


# --- the published archive -------------------------------------------------
# One folder per year, each listing that year's documents. Crawling it is how a
# manifest gets written without transcribing 200-odd links by hand.

ARCHIVE = "https://fisavate.org/index.php/en/informations/championnats-results"

# A title is a hint, never a verdict. The archive titles the same kind of
# document a dozen ways, and the only thing that reliably says whether a PDF
# holds bouts is opening it and looking for a poule grid - which is what read()
# does. These patterns order the queue; they do not decide anything.
LIKELY_BOUTS = re.compile(r"full results|pool results|r[ée]sultats|results?\b",
                          re.I)
LIKELY_MEDALS = re.compile(r"medal|m[ée]dail|podium|classement g[ée]n[ée]ral", re.I)
NOT_RESULTS = re.compile(r"inscription|entr(y|ies)|draw sheet|programme|rules?\b",
                         re.I)


def classify(title):
    """What a title suggests: "medals", "bouts", "other", or "unknown"."""
    if NOT_RESULTS.search(title):
        return "other"
    if LIKELY_MEDALS.search(title):
        return "medals"
    if LIKELY_BOUTS.search(title):
        return "bouts"
    return "unknown"


def index(archive=ARCHIVE, years=None, refresh=False):
    """[{year, title, url, kind}] for every document in the FISav archive.

    Reads the year folders, not a hard-coded list, so a year the federation adds
    later appears without a code change.
    """
    from urllib.parse import urljoin

    from bs4 import BeautifulSoup

    from savate import sources

    root = urljoin(archive, "/")
    page = BeautifulSoup(sources.text(archive, refresh=refresh), "html.parser")
    folders = {}
    for a in page.find_all("a", href=True):
        m = re.search(r"/category/\d+-(\d{4})\b", a["href"])
        if m and (years is None or m.group(1) in set(years)):
            folders[m.group(1)] = urljoin(root, a["href"])

    # Each document is linked twice - once by title, once by a "Download"
    # button - so the listing is keyed by URL and the informative title wins.
    documents = {}
    for year in sorted(folders, reverse=True):
        listing = BeautifulSoup(sources.text(folders[year], refresh=refresh),
                                "html.parser")
        for a in listing.find_all("a", href=True):
            if "/send/" not in a["href"]:
                continue
            title = " ".join(a.get_text().split())
            url = urljoin(root, a["href"])
            known = documents.get(url, {}).get("title", "")
            if title.lower() == "download" and known:
                continue
            if not title:
                continue
            # The slug in the URL is a better name than "Download".
            if title.lower() == "download":
                title = re.sub(r"^\d+-", "", url.rsplit("/", 1)[-1])
                title = title.replace("-", " ").strip().title()
            documents[url] = {"year": year, "title": title, "url": url,
                              "kind": classify(title)}
    return sorted(documents.values(),
                  key=lambda d: (d["year"], d["title"]), reverse=True)


def manifest_entry(document, slug=None):
    """A tournaments.json entry for one indexed document."""
    title = document["title"]
    slug = slug or re.sub(r"[^a-z0-9]+", "-",
                          f"fisav {title}".lower()).strip("-")[:60]
    level = ("world" if re.search(r"world", title, re.I) else
             "european" if re.search(r"europ", title, re.I) else "")
    discipline = ("assaut" if re.search(r"assaut", title, re.I) else
                  "combat" if re.search(r"combat", title, re.I) else "")
    return {"slug": slug, "adapter": NAME, "source": document["url"],
            "meta": {"name": title, "year": document["year"],
                     "level": level, "discipline": discipline}}
