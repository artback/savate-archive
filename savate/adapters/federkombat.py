"""The Italian federation's championship classifications.

FIKBMS - the federation that trades as FederKombat - has published its national
savate championships through three different systems in five years, and this
adapter reads all three because they are the same fact in three dresses: a flat
table of finishing positions, one row per medallist, with the competition itself
packed into a coded category. No Italian document in this archive publishes a
bout. Who beat whom is simply not in them, so every row here is a `Placing`.

    Piattaforma Eventi FederKombat (2021, 2022), landscape, eleven columns:
      STILE SERIE CLASSE M/F CAT. P.CLASS. VERD. COGNOME NOME SOCIETA REGIONE
       SA    -     Sr     F   52     1       P   Lo Iacono  Ilaria  Ecole ...

    Piattaforma Gare Online FIKBMS (2018), portrait, five columns under
    "CLASSIFICA ATLETI", the whole category in one cell:
      Assoluti SC SR M 1^ -70   1   Fiore Adriano   N.E.S. -   Lazio

    LPManager (2019), five columns, the licence number beside the name:
      SA Jr M 65   1   PERUGI NICOLO' - (353011)   A.S.D. SAVATE ...   LIGURIA

WHAT THE THREE SHARE, and why one adapter reads them: a competition key made of
a style code, an optional skill tier, an age class, a sex and a weight; a rank;
a competitor; a club; and an Italian region. Only the packing differs.

THE COMPETITION KEY IS THE WHOLE STYLE CODE, TIER INCLUDED. A 2021 file holds
121 rows in 42 competitions, and SPC serie 2 -60 kg and SPC serie 3 -65 kg are
two of them. Collapsing the style, or dropping the serie, would merge separate
championships and manufacture duplicate golds out of nothing. So the label
carries the source's own tokens - "SA Sr F -52 kg", "SC 3 Sr M -75 kg" - and
two rows share a category only when the document put them in one.

WHAT THE STYLE CODE IS NOT EXPANDED TO. The documents print SA, SC, SPA and SPC
and never once say what they stand for; no legend appears in any of the five
files or on the federation's site. The trailing letter tracks a real structural
difference - the SERIE tier column is filled for SC and SPC and is "-" for SA
and SPA, which is how a full-contact discipline is graded and a touch one is
not - but "SP" is unexplained, so nothing here translates a code into a
discipline. The code is kept verbatim in every category label, the tournament's
`discipline` is left to the manifest, and a caller who knows the legend can pass
`style=` to read one style's championship on its own.

WHAT IT REFUSES TO DO.

*It does not rank what the document leaves unranked.* The 2021 file lists two
SPC serie 1 seniors with "-" in the placing column and "NC" as the verdict.
They competed and were not classified. They are counted, reported and dropped,
because a row that appears is indistinguishable from a row that was earned.

*It does not read a medal table as results.* The 2018 file ends with
"MEDAGLIERE PER SOCIETA'" and "MEDAGLIERE PER REGIONE", whose rows are
"1  ECOLE DE SAVATE ...  Liguria  12  3  3" - the same five-cell shape as a
result, with a club where the competitor belongs. A MEDAGLIERE heading closes
the results section, and the row shape is checked besides.

*It does not mistake a club for another sport.* Eighteen rows in these files are
won by the Ecole De Savate Et Ranzo-do Chausson De Rue, and "chausson" in a club
name is not chausson the sport. Another sport would appear as another style
code, so that - and only that - is what is tested; every style code found in all
five documents is one of the four savate ones.

*It does not invent the country.* Every row names an Italian region, which is
not a nation and has nowhere to go in a Placing, so the region is reported as
the club attribute it is (no club in any of these files appears under two
regions) and `country` is left empty rather than stamped with the host's.

HOW THE COLUMNS ARE FOUND. Fixed-width columns in a PDF are words at
coordinates, and none of these files repeat their header after page one, so the
header cannot be the ruler. Instead a row is cut wherever its words leave a gap
wider than a space: inside a cell the gap is 2-4pt, between cells it is never
below 9.4pt in any of the five documents, and the cut is taken at 7pt. A row
that does not then yield the expected number of cells is reported and skipped,
never squeezed - both ways of getting the cut wrong cost a visible row rather
than producing a quiet wrong one.
"""

import collections
import re

from savate import normalize as norm
from savate.schema import MEDALS, Placing, Report, Tournament

NAME = "federkombat"
DESCRIPTION = "Italian federation championship classifications (FederKombat, FIKBMS, LPManager)"

# Between two cells the gap is never under 9.4pt in any of these documents;
# inside a cell it never exceeds about 4pt. Cutting at 7pt sits between the two
# with room on both sides. Overridable, because the next FIKBMS generator will
# have its own metrics and a wrong cut here should be a knob, not a rewrite.
GAP = 7.0

# The four style codes these documents use. Anything else in the style column is
# either a sport that is not savate or a layout this adapter has misread; either
# way it is reported and dropped rather than filed as savate.
STYLES = ("SA", "SC", "SPA", "SPC")

# Age classes, as FIKBMS abbreviates them. An unknown code is kept exactly as
# printed - a category nobody can read is better than one read wrong.
AGE_CLASSES = {"sr": "Senior", "jr": "Junior", "cad": "Cadet",
               "mstr": "Master", "spe": "Speranze"}
# Only this one is an expansion rather than a universal abbreviation, so a read
# that uses it says so.
INFERRED_AGE = {"spe"}

SEXES = {"m": "Men", "f": "Women"}

MONTHS = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
          "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9,
          "ottobre": 10, "novembre": 11, "dicembre": 12}

# A weight class as the three generators write it: "52", "85+", "-70", "+65".
WEIGHT = re.compile(r"^(?P<lead>[-+])?\s*(?P<kg>\d{2,3})\s*(?P<trail>[-+])?$")

# The skill tier, which only the combat styles carry: "1", "2^", "3".
SERIE = re.compile(r"^(?P<tier>[1-9])\s*\^?$")

# "-" is what these sheets print for a field that does not apply.
BLANK = {"-", "--", "", "/"}

# The club and regional medal tables the 2018 file appends to its results. Their
# rows have a result's shape and a club's content.
MEDAL_TABLE = re.compile(r"medagliere|piazzamento", re.I)
# The heading that opens a results section again, should one ever follow.
RESULTS_SECTION = re.compile(r"classifica\s+atleti|risultati\s+di\s+gara", re.I)

# The generator's own furniture, printed on every page and never data.
FURNITURE = re.compile(
    r"^(piattaforma\s|www\.|powered\s+by\b|risultati\s+di\s+gara$|"
    r"classifica\s+atleti$|\d+\s*/\s*\d+$)", re.I)

# The footer stamp, which carries the day the PDF was generated and would
# otherwise be read as the day the championship was held. The 2021 file was
# printed on 24 May and the competition was on the 23rd.
FOOTER = re.compile(r"^\d{1,2}\s+\w+\s+\d{4},\s*Ore\s+\d", re.I)

# The three header rows, each of which says what its own columns mean. Layout is
# read from these rather than from the generator's name: the header is the
# document telling you how to read it, the strapline is only branding.
HEADERS = (
    ("federkombat", ("stile", "serie", "classe", "cognome", "nome")),
    ("fikbms", ("categoria", "rnk", "nome")),
    ("lpmanager", ("categoria", "podio", "nome", "team", "regione")),
)

# How many cells a data row has in each layout.
WIDTH = {"federkombat": 11, "fikbms": 5, "lpmanager": 5}

# "MARTINI GIORGIA - (364374)": the federal licence number, which only the 2019
# file prints. It is a genuine identity anchor and there is no schema field for
# it, so it is cut off the name and reported rather than left to corrupt it.
LICENCE = re.compile(r"^(?P<name>.*?)\s*-\s*\(\s*(?P<licence>\d{3,10})\s*\)\s*$")

# The 2018 generator marks a space inside a name part with an underscore -
# "Lo_Iacono Ilaria", "Latini Lisa_Andrea". That this is a space and not some
# other character is not a guess: the 2021 and 2022 files print the same two
# competitors with the same parts in separate COGNOME and NOME columns.
UNDERSCORE = re.compile(r"_")

# A single letter before that underscore - "D_Isidoro" - where an apostrophe is
# as likely as a space. One name in one file; it is restored like the rest and
# reported, never repaired into a form the document does not contain.
AMBIGUOUS_UNDERSCORE = re.compile(r"\b[A-Za-z]_")


def _cells(row, gap):
    """One row's words cut into cells wherever they leave more than a space."""
    out, current = [], []
    for word in sorted(row, key=lambda w: w.x0):
        if current and word.x0 - current[-1].x1 > gap:
            out.append(current)
            current = []
        current.append(word)
    if current:
        out.append(current)
    return [" ".join(w.text for w in cell) for cell in out]


def _lines(path, gap):
    """[(page, [cell, ...])] for the whole document, in reading order."""
    from savate import pdf

    words = pdf.words(path)
    return [(row[0].page, _cells(row, gap))
            for row in pdf.rows(words, tolerance=3.0) if row]


def _layout(rows):
    """(layout name, the header's row index), or (None, None).

    Matched on the header's own words. A file whose header this does not
    recognise is a layout nobody has read yet, which is a thing to go and look
    at rather than to parse hopefully.
    """
    for index, (_page, cells) in enumerate(rows[:40]):
        flat = norm.fold(" ".join(cells))
        flat = re.sub(r"[^a-z0-9 ]+", " ", flat)
        words = set(flat.split())
        for name, needed in HEADERS:
            if all(w in words for w in needed):
                return name, index
    return None, None


def _date(text):
    """An Italian dateline -> (start, end, city).

    "23 maggio 2021", "19-22 maggio 2022", "4-6 maggio 2018" and the 2019
    file's "14/04/2019 - GENZANO" are all of them, and each is read rather than
    assumed; anything else comes back empty.
    """
    text = " ".join(str(text or "").split())
    found = re.match(r"^(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s+([A-Za-zàè]+)\s+"
                     r"(\d{4})\b", text)
    if found:
        month = MONTHS.get(norm.fold(found.group(3)))
        if month:
            year = int(found.group(4))
            first = f"{year:04d}-{month:02d}-{int(found.group(1)):02d}"
            last = (f"{year:04d}-{month:02d}-{int(found.group(2)):02d}"
                    if found.group(2) else first)
            return first, last, ""
    found = re.match(r"^(\d{1,2}/\d{1,2}/\d{4})\s*(?:[-–]\s*(.*))?$", text)
    if found:
        day = norm.date(found.group(1))
        if day:
            city = " ".join((found.group(2) or "").split())
            return day, day, city.title() if city.isupper() else city
    return "", "", ""


def _heading(rows, header_index):
    """(name, start, end, city) from what the document prints above its table.

    Only above it. The same generators stamp the date they ran on into every
    page footer, and a footer read as a dateline dates the 2021 championship to
    the day after it was held.
    """
    name = start = end = city = ""
    for _page, cells in rows[:header_index]:
        text = " ".join(" ".join(cells).split())
        if not text or FURNITURE.match(text) or FOOTER.match(text):
            continue
        first, last, where = _date(text)
        if first:
            start, end, city = start or first, end or last, city or where
        elif not name:
            name = text
    return name, start, end, city


def _weight(text):
    """A printed weight class -> (kilos, bound), or ("", "") if it is not one.

    An unsigned figure is an upper limit. That is not this adapter's convention
    imported from elsewhere: the same federation's 2018 file writes the same
    classes as "-70" and "+65", and every file that prints a bare number prints
    its open class with a "+".
    """
    found = WEIGHT.match(" ".join(str(text or "").split()))
    if not found:
        return "", ""
    sign = found.group("lead") or found.group("trail") or "-"
    return found.group("kg"), "over" if sign == "+" else "under"


def _age(code):
    """(age class, was it expanded rather than read) for an FIKBMS age code."""
    key = norm.fold(code).strip(". ")
    return AGE_CLASSES.get(key, " ".join(str(code).split())), key in INFERRED_AGE


def _name(surname, forename):
    """Surname then forename, which is the order all three generators print."""
    return " ".join((" ".join(str(surname or "").split()) + " " +
                     " ".join(str(forename or "").split())).split())


class _Row:
    """One line of results, after its layout has been unpacked.

    Every layout produces these same fields, which is what lets one set of
    checks and one Placing builder serve all three.
    """

    __slots__ = ("style", "serie", "age_code", "sex_code", "weight", "rank",
                 "verdict", "fighter", "club", "region", "licence", "ambiguous",
                 "where")

    def __init__(self, **fields):
        for slot in self.__slots__:
            setattr(self, slot, fields.get(slot, ""))


def _read_federkombat(cells):
    """The eleven-column landscape table: 2021 Busalla, 2022 Jesolo."""
    style, serie, age, sex, weight, rank, verdict, surname, forename, club, \
        region = cells
    return _Row(style=style, serie=serie, age_code=age, sex_code=sex,
                weight=weight, rank=rank, verdict=verdict,
                fighter=_name(surname, forename), club=club, region=region)


def _read_fikbms(cells):
    """The 2018 CLASSIFICA ATLETI, whose category is one compound cell.

    "Assoluti SC SR M 1^ -70" is championship, style, age, sex, tier, weight.
    The leading word names the championship, not the class, and the tier is
    there only for the combat styles.
    """
    category, rank, who, club, region = cells
    tokens = category.split()
    if tokens and norm.fold(tokens[0]) not in [s.lower() for s in STYLES]:
        tokens = tokens[1:]                       # "Assoluti", the event's name
    if len(tokens) < 4:
        return None
    style, age, sex = tokens[0], tokens[1], tokens[2]
    rest = tokens[3:]
    serie = ""
    if rest and SERIE.match(rest[0]):
        serie = SERIE.match(rest[0]).group("tier")
        rest = rest[1:]
    if len(rest) != 1:
        return None
    parts = UNDERSCORE.sub(" ", who).split(None, 1)
    fighter = _name(parts[0] if parts else "", parts[1] if len(parts) > 1 else "")
    return _Row(style=style, serie=serie, age_code=age, sex_code=sex,
                weight=rest[0], rank=rank, fighter=fighter, club=club,
                region=region,
                # "D_Isidoro" is the one shape where the underscore could as
                # easily be an apostrophe as a space: every other one joins two
                # whole words. It is restored to a space like the rest, because
                # that is what the sibling documents corroborate, and flagged
                # rather than quietly chosen.
                ambiguous=bool(AMBIGUOUS_UNDERSCORE.search(who)))


def _read_lpmanager(cells):
    """The 2019 Genzano podium list, with a licence number beside each name."""
    category, rank, who, club, region = cells
    tokens = category.split()
    if len(tokens) != 4:
        return None
    style, age, sex, weight = tokens
    licence = ""
    found = LICENCE.match(who)
    if found:
        who, licence = found.group("name"), found.group("licence")
    return _Row(style=style, serie="", age_code=age, sex_code=sex,
                weight=weight, rank=rank, fighter=" ".join(who.split()),
                club=club, region=region, licence=licence)


READERS = {"federkombat": _read_federkombat, "fikbms": _read_fikbms,
           "lpmanager": _read_lpmanager}


def _wanted(style, chosen):
    if not chosen:
        return True
    if isinstance(chosen, str):
        chosen = [chosen]
    return norm.fold(style) in {norm.fold(s) for s in chosen}


def read(source, slug, meta=None, style=None, gap=GAP, **options):
    """(Tournament, [Placing], Report) from one Italian classification sheet.

    `style` keeps only the named style code or codes - "SA", ["SC", "SPC"] -
    so a manifest can read one style's championship out of a file holding four.
    """
    from savate import sources

    meta = dict(meta or {})
    report = Report(source=str(source), adapter=NAME)
    tournament = Tournament(
        slug=slug, name=meta.get("name", ""),
        discipline=meta.get("discipline", ""), level=meta.get("level", ""),
        format=meta.get("format", ""), age_class=meta.get("age_class", ""),
        year=meta.get("year", ""), start_date=meta.get("start_date", ""),
        end_date=meta.get("end_date", ""), city=meta.get("city", ""),
        country=meta.get("country", ""), source=str(source), adapter=NAME)

    try:
        path = (sources.fetch_archived(str(source)) if options.get("archived")
                else sources.fetch(source, refresh=options.get("refresh", False)))
    except Exception as e:                        # network, 404, wrong type
        report.problem(f"could not fetch the document: {e}")
        return tournament, [], report
    try:
        rows = _lines(path, gap)
    except Exception as e:                        # no pdftotext, not a PDF
        report.problem(f"could not read the document's words: {e}")
        return tournament, [], report

    layout, header_index = _layout(rows)
    report.read = len(rows)
    report.notes["pages"] = len({page for page, _ in rows})
    if layout is None:
        report.problem(
            "no FederKombat, FIKBMS or LPManager results header was found - "
            "this is a layout nobody has read yet, not one to guess at")
        report.notes["first_lines"] = [" | ".join(c) for _p, c in rows[:6]]
        return tournament, [], report
    report.notes["layout"] = layout

    # The manifest wins wherever it says something; the document fills the rest,
    # and what the document printed is reported either way so the two can be
    # compared. Read unconditionally: a manifest that names the event but not
    # its year should still come away with the year the sheet prints.
    printed, start, end, city = _heading(rows, header_index)
    report.notes["printed_title"] = printed
    tournament.name = tournament.name or printed or slug
    tournament.start_date = tournament.start_date or start
    tournament.end_date = tournament.end_date or end
    tournament.city = tournament.city or city
    tournament.year = tournament.year or (tournament.start_date or "")[:4]

    reader, width = READERS[layout], WIDTH[layout]
    placings = []
    counts = collections.Counter()
    verdicts = collections.Counter()
    regions, licences, unreadable, inferred_ages = {}, [], [], set()
    ambiguous = []
    unranked, foreign_styles, excluded_style, mismatched, in_results = \
        [], collections.Counter(), 0, 0, True

    for page, cells in rows[header_index + 1:]:
        text = " ".join(" ".join(cells).split())
        if not text or FURNITURE.match(text) or FOOTER.match(text):
            continue
        if MEDAL_TABLE.search(text):
            in_results = False
            report.notes.setdefault("skipped_sections", []).append(text[:60])
            continue
        if RESULTS_SECTION.search(text):
            in_results = True
            continue
        if not in_results:
            continue
        if len(cells) != width:
            mismatched += 1
            sample = report.notes.setdefault("unsplit_rows", [])
            if len(sample) < 6:
                sample.append(f"p{page}: {text[:80]}")
            continue

        row = reader(cells)
        if row is None:
            unreadable.append(f"p{page}: {text[:80]}")
            continue
        row.where = f"p{page}"

        code = row.style.upper().strip(". ")
        if code not in STYLES:
            # A style column holding something else is either another sport
            # filed in a savate sheet or a row this adapter has misread. Neither
            # is a savate result, and neither is guessed at.
            foreign_styles[row.style] += 1
            continue
        if not _wanted(code, style):
            excluded_style += 1
            continue

        kilos, bound = _weight(row.weight)
        if not kilos:
            unreadable.append(f"p{page}: no weight class in {text[:70]}")
            continue
        age_class, guessed = _age(row.age_code)
        if guessed:
            inferred_ages.add(norm.fold(row.age_code))
        gender = SEXES.get(norm.fold(row.sex_code), "")
        serie = ""
        if row.serie and row.serie.strip() not in BLANK:
            found = SERIE.match(row.serie.strip())
            if found:
                serie = found.group("tier")
            else:
                unreadable.append(f"p{page}: serie {row.serie!r} in {text[:60]}")
                continue

        verdict = " ".join(str(row.verdict or "").split())
        if verdict:
            verdicts[verdict] += 1

        # The codes themselves, not a translation of them - but in one
        # capitalisation. The 2018 generator shouts its age codes and the 2021
        # one does not, and "SA SR F -52 kg" and "SA Sr F -52 kg" being two
        # labels for one class would hide every Italian competition from the
        # one before it. Nothing but letter case is touched.
        label = " ".join(
            [code] + ([serie] if serie else []) +
            ["".join(str(row.age_code).split()).title(),
             str(row.sex_code).strip().upper(),
             f"{'+' if bound == 'over' else '-'}{kilos} kg"])

        rank = str(row.rank).strip()
        if rank in BLANK or not rank.isdigit():
            # The 2021 file's two SPC serie 1 seniors: they fought and the
            # document did not classify them. A place they were not given is
            # not a place this adapter can supply.
            unranked.append(f"{label}: {row.fighter or text[:40]}"
                            + (f" (verdict {verdict})" if verdict else ""))
            continue

        fighter = " ".join(str(row.fighter or "").split())
        if len(fighter) < 3 or not re.search(r"[A-Za-zÀ-ÿ]{2}", fighter):
            unreadable.append(f"p{page}: no readable competitor in {text[:70]}")
            continue

        club = " ".join(str(row.club or "").split())
        region = " ".join(str(row.region or "").split())
        if club and region:
            regions.setdefault(club, set()).add(region)
        if row.licence:
            licences.append(f"{fighter} = {row.licence}")
        if row.ambiguous:
            ambiguous.append(fighter)

        counts[label] += 1
        placings.append(Placing(
            tournament=slug, placing_id=f"{slug}-{len(placings) + 1:04d}",
            category=label, gender=gender, age_class=age_class,
            weight_kg=kilos, weight_bound=bound,
            rank=rank, medal=MEDALS.get(rank, ""),
            fighter=fighter, club=club,
            # Left empty on purpose. These sheets print an Italian region, and a
            # region is not a nation; stamping the host country on every row
            # would be this adapter's fact, not the document's.
            country="",
            result_source="reported"))

    report.notes["placings"] = len(placings)
    report.notes["categories"] = len(counts)
    if verdicts:
        report.notes["verdicts"] = dict(verdicts)
    if regions:
        report.notes["club_regions"] = {c: sorted(r)[0]
                                        for c, r in sorted(regions.items())}
        split = {c: sorted(r) for c, r in regions.items() if len(r) > 1}
        if split:
            report.problem(
                "club(s) printed under more than one region: " +
                "; ".join(f"{c} {r}" for c, r in sorted(split.items())[:4]))
        report.problem(
            f"the document names an Italian region for every row; a region is "
            f"not a country and a Placing has nowhere to keep one, so the "
            f"{len(regions)} club-to-region pairings are in the report's notes "
            f"and `country` is left empty rather than filled with the host's")
    if licences:
        report.notes["licences"] = sorted(set(licences))
        report.problem(
            f"{len(licences)} of {len(placings)} row(s) carry a federal licence "
            f"number ({len(set(licences))} distinct competitors), which a "
            f"Placing has no field for; they are kept in the report's notes "
            f"because they are the archive's only Italian identity anchor")
    if ambiguous:
        report.notes["ambiguous_underscore"] = sorted(set(ambiguous))
        report.problem(
            "this generator marks a space inside a name part with an "
            "underscore, which the 2021 and 2022 sheets corroborate for every "
            "other name; in " + ", ".join(sorted(set(ambiguous))) +
            " a single letter precedes it and an apostrophe is as likely, so "
            "it is stored as a space and flagged rather than repaired")
    if unranked:
        report.notes["unranked"] = unranked
        report.problem(
            f"{len(unranked)} competitor(s) appear with no place in the "
            f"classification column - listed, not ranked, so not stored: " +
            "; ".join(unranked[:4]))
    if foreign_styles:
        report.notes["foreign_styles"] = dict(foreign_styles)
        report.problem(
            "row(s) whose style column is not one of " + "/".join(STYLES) +
            " were dropped rather than filed as savate: " +
            "; ".join(f"{s} x{n}" for s, n in foreign_styles.most_common(4)))
    if excluded_style:
        report.notes["excluded_by_style"] = excluded_style
        report.problem(f"{excluded_style} row(s) belong to a style this entry "
                       f"did not ask for ({style}) and were left for another")
    if mismatched:
        report.notes["unsplit"] = mismatched
        report.problem(
            f"{mismatched} line(s) did not cut into {width} cells at a {gap}pt "
            f"gap and were skipped rather than squeezed into the column count")
    if unreadable:
        report.notes["unreadable"] = unreadable[:20]
        report.problem(f"{len(unreadable)} row(s) had the right shape but "
                       f"unreadable content: " + "; ".join(unreadable[:3]))
    if inferred_ages:
        report.problem(
            "age code(s) " + ", ".join(sorted(inferred_ages)) + " were read as "
            + ", ".join(sorted(AGE_CLASSES[a] for a in inferred_ages)) +
            "; the document prints only the abbreviation, and the raw code is "
            "kept in every category label so the reading can be checked")
    unsigned = len({p.category for p in placings if p.weight_bound == "under"})
    if unsigned:
        report.problem(
            f"{unsigned} weight class(es) are read as an upper limit; where "
            f"this generator prints a bare figure the same federation's other "
            f"sheets print it signed, and the open class is always written '+'")
    twice = sorted(label for label, _n in counts.items()
                   if sum(1 for p in placings
                          if p.category == label and p.rank == "1") > 1)
    if twice:
        report.problem(
            "the same first place is awarded twice in " + ", ".join(twice[:4]) +
            " - two competitions printed under one key, or a place mistyped; "
            "kept exactly as printed rather than reassigned")
    if not placings:
        report.problem("no classification rows were read from this document")
    return tournament, placings, report
