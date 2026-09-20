"""Adapter for the QRcodeList.php bout list used by the 2026 world championship.

Reads the data.json that scrape_assaut.py produces, rather than the HTML, so the
scraping and the canonical mapping stay separable: the scraper owns the site's
markup, this owns what the site's fields mean.
"""

from savate import normalize as norm
from savate.schema import Bout, Report, Tournament, phase_of

NAME = "assaut_qrcode"
DESCRIPTION = "QRcodeList.php bout list, via scrape_assaut.py's data.json"


def read(source, slug, meta=None, **options):
    """(Tournament, [Bout], Report) from one scrape_assaut.py data.json."""
    import json

    path = source
    report = Report(source=str(source), adapter=NAME)

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    country, warnings = {}, {}
    for poule in data.get("poules", []):
        draw = (poule["agecat"], poule["weightcat"], poule["poule"])
        for pair in poule["pairs"]:
            for corner in ("red", "blue"):
                country.setdefault(norm.fold(pair[corner]), pair[f"{corner}_country"])
            # Warnings are only ever published on the scoresheet, never in the
            # bout list, so they have to be carried across by draw and pair.
            warnings[draw + (frozenset((norm.fold(pair["red"]),
                                        norm.fold(pair["blue"]))),)] = pair

    tournament = Tournament(
        slug=slug, source=data.get("source", ""), adapter=NAME,
        fetched_at=data.get("fetched_at", ""), **(meta or {}))
    report.read = len(data.get("bouts", []))

    bouts = []
    for i, b in enumerate(sorted(data["bouts"],
                                 key=lambda x: (x["date"], x["time"].zfill(5),
                                                x["ring"]))):
        winner_corner = b.get("winner_corner", "")
        sheet = warnings.get((b["agecat"], b["weightcat"], b["poule"],
                              frozenset((norm.fold(b["red"]), norm.fold(b["blue"])))))
        same = sheet and norm.fold(sheet["red"]) == norm.fold(b["red"])
        bouts.append(Bout(
            tournament=slug,
            bout_id=f"{slug}-{i + 1:04d}",
            date=b["date"],
            time=norm.clock(b["time"]),
            ring=b["ring"],
            phase=phase_of(b["phase"]),
            poule=b["poule"],
            red=b["red"], red_country=country.get(norm.fold(b["red"]), ""),
            blue=b["blue"], blue_country=country.get(norm.fold(b["blue"]), ""),
            red_points=b.get("red_points", ""),
            blue_points=b.get("blue_points", ""),
            red_warnings=(sheet["red_warnings" if same else "blue_warnings"]
                          if sheet else ""),
            blue_warnings=(sheet["blue_warnings" if same else "red_warnings"]
                           if sheet else ""),
            winner_corner=winner_corner,
            winner={"red": b["red"], "blue": b["blue"]}.get(winner_corner, ""),
            loser={"red": b["blue"], "blue": b["red"]}.get(winner_corner, ""),
            decision=b.get("decision", ""),
            status="decided" if winner_corner else "unresolved",
            result_source="reported" if winner_corner else "",
            **norm.category(b["category"]),
        ))
    for b in bouts:
        if not b.red_country or not b.blue_country:
            report.problem(f"{b.bout_id}: a corner has no country")
    return tournament, bouts, report
