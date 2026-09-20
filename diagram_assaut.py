#!/usr/bin/env python3
"""
One mirrored tournament bracket per WEIGHT category, from the CSVs written
by scrape_assaut.py. Two halves converge on a champion node in the centre.

    python diagram_assaut.py                 # -> diagrams/*.svg + index.html
    python diagram_assaut.py --qualify 1     # 1 qualifier per poule (default 2)
    python diagram_assaut.py --debug         # show phase classification

Before the knockout bouts exist the bracket is drawn as an empty skeleton
sized from the poule count; once they appear the real tree is derived from
them instead. Poule schedules and results are listed underneath.

Stdlib only. Reads poules.csv and bouts.csv from the current directory.
"""

import argparse
import csv
import math
import re
from collections import OrderedDict, defaultdict
from html import escape
from pathlib import Path

OUT = Path("diagrams")

RED, BLUE = "#c0392b", "#2265ad"
INK, MUTE, LINE = "#18181b", "#71717a", "#d4d4d8"
CARD, BG, WIN, GHOST = "#ffffff", "#fafafa", "#15803d", "#a1a1aa"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

PAD = 30
BW, BH, HGAP = 248, 50, 52        # bracket box + column gap
OW, OH, CGAP = 148, 76, 34        # champion oval + clearance either side
W_POULE, H_HEAD, H_FIGHTER, H_SEP, H_MATCH, GAP = 340, 32, 22, 12, 36, 22

ROUNDS = [
    ("Poules",        [r"poule", r"pool", r"group"]),
    ("Repechage",     [r"rep[eê]chage", r"repechage"]),
    ("1/16",          [r"1/16"]),
    ("1/8",           [r"1/8", r"huiti[eè]me", r"round of 16"]),
    ("Quarter-final", [r"1/4", r"quart", r"quarter"]),
    ("Semi-final",    [r"1/2", r"demi", r"semi"]),
    ("Final",         [r"^\s*finale?\s*$", r"^\s*final\s*$", r"grande? finale"]),
    ("Bronze",        [r"bronze", r"3[eè]?r?d?e? place", r"third place"]),
]
ROUND_NAMES = [r[0] for r in ROUNDS]

# Last-resort override, keyed "agecat/weightcat" - the site's own draw key.
# Only needed for a draw where NO bout anywhere names its category. The script
# prints the keys it could not resolve, so fill them in here if it ever does:
#     WEIGHTCAT_LABELS = {"5/6": "Men -70 kg", "7/6": "Women -65 kg"}
WEIGHTCAT_LABELS = {}
KO_ROUNDS = [r for r in ROUND_NAMES if r not in ("Poules", "Bronze", "Repechage")]


def classify(phase):
    p = (phase or "").strip()
    if not p:
        return None
    for name, pats in ROUNDS:
        if any(re.search(pat, p, re.I) for pat in pats):
            return name
    return None


GENDERS = [
    ("Women", [r"\bwomen\b", r"\bfemmes?\b", r"\bdames?\b", r"\bfemale\b"]),
    ("Men",   [r"\bmen\b", r"\bhommes?\b", r"\bmale\b"]),
]
WEIGHT = re.compile(r"([-+\u2212<>]?)\s*(\d+(?:[.,]\d+)?)\s*kg", re.I)


def parse_category(label):
    """'Senior Men Assaut -80 kg' -> ('Men -80 kg', 'Men', 80.0). Age dropped."""
    gender = next((n for n, pats in GENDERS
                   if any(re.search(p, label, re.I) for p in pats)), "")
    m = WEIGHT.search(label)
    if not m:
        # compact form, e.g. "M80" / "F 65"
        c = re.search(r"\b([MF])\s?(\d{2,3})\b", label)
        if c:
            g = gender or ("Men" if c.group(1).upper() == "M" else "Women")
            return f"{g} -{c.group(2)} kg", g, float(c.group(2))
        return label.strip(), gender, None
    sign = m.group(1).replace("\u2212", "-")
    kg = float(m.group(2).replace(",", "."))
    return f"{gender} {sign}{kg:g} kg".strip(), gender, kg


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def txt(x, y, s, size=12, fill=INK, anchor="start", weight="400"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
            f'{escape(s)}</text>')


def rows(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"{path} not found - run scrape_assaut.py first")
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- assemble --------------------------------------------------------------

# "33 pm) :" and friends - the old HEADER regex captured the am/pm parenthetical
# instead of the category, producing one bogus "weight class" per minute value.
BAD_CATEGORY = re.compile(r"^\s*\d|\b[ap]m\)", re.I)

STALE = ("\nbouts.csv is stale - it was written by an older scrape_assaut.py.\n"
         "Re-run:  python scrape_assaut.py\n"
         "It re-parses the cached HTML in raw/ and does NOT re-fetch anything.\n")


def check_input(bouts):
    """Refuse to draw rather than emit a wall of mis-keyed brackets."""
    if not bouts:
        raise SystemExit("bouts.csv is empty")
    if "phase" not in bouts[0]:
        raise SystemExit("bouts.csv has no 'phase' column." + STALE)
    bad = sorted({b["category"] for b in bouts if BAD_CATEGORY.search(b["category"])})
    if bad:
        raise SystemExit(
            f"{len(bad)} category labels look like clock fragments, not weight "
            f"classes:\n  " + "\n  ".join(repr(c) for c in bad[:5])
            + (f"\n  ... and {len(bad) - 5} more" if len(bad) > 5 else "") + STALE)


def build(debug=False):
    pairings, bouts = rows("poules.csv"), rows("bouts.csv")
    check_input(bouts)
    sched = {frozenset((norm(b["red"]), norm(b["blue"]))): b for b in bouts}

    # A draw is identified by the site's OWN key, (agecat, weightcat) - the
    # same pair the showpoule URL uses. Keying on weightcat alone merged two
    # unrelated draws that happened to share a weightcat id, which is how one
    # weight class ended up displaying two different "Poule A"s.
    def gkey(p):
        return (p["agecat"], p["weightcat"])

    groups = defaultdict(lambda: {"poules": defaultdict(list),
                                  "rounds": defaultdict(list),
                                  "unknown_phases": set(), "label": None})
    fighter_group, country_of = {}, {}

    for p in pairings:
        k = gkey(p)
        b = sched.get(frozenset((norm(p["red"]), norm(p["blue"]))))
        groups[k]["poules"][p["poule"]].append({
            "red": p["red"], "red_country": p["red_country"],
            "blue": p["blue"], "blue_country": p["blue_country"],
            "date": b["date"] if b else "", "time": b["time"] if b else "",
            "ring": b["ring"] if b else "", "result": b["result"] if b else ""})
        for who, ctry in ((p["red"], p["red_country"]),
                          (p["blue"], p["blue_country"])):
            fighter_group[norm(who)] = k
            country_of[norm(who)] = ctry

    # Name each draw from any bout mentioning one of its fighters. Per fighter,
    # not per pairing: a pairing may be unscheduled or spelled differently on
    # the two pages, but one named fighter is enough to identify the class.
    for b in bouts:
        for who in (b["red"], b["blue"]):
            k = fighter_group.get(norm(who))
            if k and groups[k]["label"] is None:
                groups[k]["label"] = b["category"]
                break

    unresolved = []
    for k, g in groups.items():
        override = WEIGHTCAT_LABELS.get(f"{k[0]}/{k[1]}")
        if override:
            g["label"] = override
        elif g["label"] is None:
            unresolved.append(f"{k[0]}/{k[1]}")
            g["label"] = f"weightcat {k[1]}"

    # Knockout bouts belong to the draw their fighters came out of.
    for b in bouts:
        k = fighter_group.get(norm(b["red"])) or fighter_group.get(norm(b["blue"]))
        if k is None:
            continue
        rnd = classify(b.get("phase", ""))
        if rnd is None:
            if b.get("phase"):
                groups[k]["unknown_phases"].add(b["phase"])
            continue
        if rnd == "Poules":
            continue
        groups[k]["rounds"][rnd].append({
            "red": b["red"], "red_country": country_of.get(norm(b["red"]), ""),
            "blue": b["blue"], "blue_country": country_of.get(norm(b["blue"]), ""),
            "date": b["date"], "time": b["time"], "ring": b["ring"],
            "result": b["result"]})

    # Two draws can legitimately be halves of one class. Merge them only when
    # their poule letters DON'T overlap; overlapping letters mean these are
    # separate draws that merely resolved to the same name, and merging them
    # is exactly the bug this replaces.
    cats = {}
    for k in sorted(groups):
        g = groups[k]
        label, gender, kg = parse_category(g["label"])
        if label in cats and set(cats[label]["poules"]) & set(g["poules"]):
            label = f"{label} [{k[0]}/{k[1]}]"
        c = cats.setdefault(label, {"gender": gender, "kg": kg, "poules": {},
                                    "rounds": defaultdict(list),
                                    "unknown_phases": set(), "source": []})
        c["poules"].update(g["poules"])
        for rnd, ms in g["rounds"].items():
            c["rounds"][rnd] += ms
        c["unknown_phases"] |= g["unknown_phases"]
        c["source"].append(f"{k[0]}/{k[1]}")

    if unresolved:
        print(f"!! could not name draw(s) {sorted(unresolved)} - no bout gives a "
              f"category. Add them to WEIGHTCAT_LABELS, keyed 'agecat/weightcat'.")
    for label, c in cats.items():
        if len(c["source"]) > 1:
            print(f"   '{label}' merged from draws {c['source']} "
                  f"(disjoint poule letters)")

    if debug:
        seen = defaultdict(set)
        for b in bouts:
            seen[classify(b.get("phase", ""))].add(b.get("phase", ""))
        for rnd, labels in seen.items():
            print(f"  {rnd or '** UNRECOGNISED **'}: {sorted(labels)}")
    return cats


def poule_label(cat, key):
    """Poule keys are plain letters now - draws are separated before this."""
    return key


def fighters_of(matches):
    seen = OrderedDict()
    for m in matches:
        for who, ctry in ((m["red"], m["red_country"]), (m["blue"], m["blue_country"])):
            seen.setdefault(norm(who), (who, ctry))
    return list(seen.values())


def winner_of(m):
    for who in (m.get("red"), m.get("blue")):
        if who and re.search(re.escape(who), m.get("result") or "", re.I):
            return norm(who)
    return None


def meta_line(m, with_result=False):
    parts = [m.get("date", ""), f'{m["time"]}h' if m.get("time") else "",
             f'Ring {m["ring"]}' if m.get("ring") else ""]
    if with_result and m.get("result"):
        parts.append(clip(m["result"], 30))
    return " \u00b7 ".join(p for p in parts if p) or "not scheduled"


# --- tree ------------------------------------------------------------------
# node = {"kind": match|empty|slot|poule, "children": [...], ...}

def tree_from_data(cat):
    """Derive the real tree by walking back from the last knockout round."""
    ko = [r for r in KO_ROUNDS if cat["rounds"].get(r)]
    if not ko:
        return None
    per = {r: sorted(cat["rounds"][r], key=lambda m: (m["date"], m["time"]))
           for r in ko}

    def node_for(m, ri):
        n = {"kind": "match", "m": m, "children": []}
        if ri == 0:
            # First knockout round is the outer column. Poules are NOT hung off
            # it: one poule feeds several first-round bouts, so it would be drawn
            # once per qualifier. The poule detail panel below carries them.
            return n
        prev, used = per[ko[ri - 1]], set()
        for who in (m["red"], m["blue"]):
            for j, pm in enumerate(prev):
                if j in used:
                    continue
                if norm(who) in (norm(pm["red"]), norm(pm["blue"])):
                    n["children"].append(node_for(pm, ri - 1))
                    used.add(j)
                    break
        return n

    roots = per[ko[-1]]
    if len(roots) == 1:
        return node_for(roots[0], len(ko) - 1)
    return {"kind": "empty", "m": None,
            "children": [node_for(m, len(ko) - 1) for m in roots]}


def tree_skeleton(cat, qualify):
    """No knockout data yet: size an empty bracket from the poule count."""
    names = sorted(cat["poules"])
    if not names:
        return None
    def seed(key, rank):
        return {"kind": "poule", "name": poule_label(cat, key), "rank": rank,
                "fighters": fighters_of(cat["poules"][key]), "children": []}

    def bye():
        return {"kind": "bye", "children": []}

    # Every leaf names the whole poule it will come out of. The qualifier isn't
    # known yet, so the rank is shown as a label rather than picking a fighter.
    seeds = [seed(n, 1) for n in names]
    if qualify >= 2:
        # interleave winners with reversed runners-up so a poule's two
        # qualifiers can't meet in the first knockout round
        ups = [seed(n, 2) for n in names][::-1]
        seeds = [s for pair in zip(seeds, ups) for s in pair]
        seeds += [seed(n, q) for n in names for q in range(3, qualify + 1)]

    if len(seeds) < 2:
        return None

    # Pad to a power of two with explicit byes. Promoting a lone child up a
    # level instead (the old behaviour) left it at leaf depth while its
    # siblings advanced, which put it in the wrong column and skewed every
    # parent above it - that's what made the whole bracket look crooked.
    full = 1
    while full < len(seeds):
        full *= 2
    for k in range(full - len(seeds)):
        # alternate end / middle so both halves get a similar number
        seeds.append(bye()) if k % 2 == 0 else seeds.insert(len(seeds) // 2, bye())

    level = seeds
    while len(level) > 1:
        level = [{"kind": "empty", "m": None, "children": level[i:i + 2]}
                 for i in range(0, len(level), 2)]
    return level[0]


def leaves(n):
    return [n] if not n["children"] else [l for c in n["children"] for l in leaves(c)]


def depth(n):
    return 1 + max((depth(c) for c in n["children"]), default=0)


def rounds_above(n):
    """Rounds between this node and its deepest leaf. Leaves are 0.

    Columns are assigned from this rather than from depth-below-the-root, so
    an unbalanced subtree (a real bracket where one half has an extra round)
    still puts every leaf in the outermost column instead of stranding some
    of them mid-canvas.
    """
    return 0 if not n["children"] else 1 + max(rounds_above(c) for c in n["children"])


def is_box(n):
    """Match/empty nodes render as bracket boxes; slot/poule as leaf cards."""
    return n["kind"] in ("match", "empty")


def leaf_h(n):
    if is_box(n):
        return BH
    if n["kind"] == "bye":
        return 36
    if n["kind"] == "poule":
        return H_HEAD + H_FIGHTER * len(n["fighters"]) + 10
    return 36


# --- render ----------------------------------------------------------------

def render_leaf(n, x, y):
    if n["kind"] == "bye":
        h = 36
        return (f'<g transform="translate({x:.1f},{y:.1f})">'
                f'<rect width="{BW}" height="{h}" rx="7" fill="none" '
                f'stroke="{LINE}" stroke-dasharray="2 4"/>'
                + txt(BW / 2, 23, "bye", 11, GHOST, anchor="middle") + "</g>"), h
    if n["kind"] == "slot":
        h = 36
        return (f'<g transform="translate({x:.1f},{y:.1f})">'
                f'<rect width="{BW}" height="{h}" rx="7" fill="{CARD}" '
                f'stroke="{LINE}" stroke-dasharray="4 3"/>'
                + txt(12, 23, n["label"], 12, GHOST) + "</g>"), h
    h = leaf_h(n)
    rank = n.get("rank")
    o = [f'<g transform="translate({x:.1f},{y:.1f})">',
         f'<rect width="{BW}" height="{h}" rx="7" fill="{CARD}" stroke="{LINE}"'
         + (' stroke-dasharray="4 3"' if rank else '') + '/>',
         txt(12, 21, f'Poule {n["name"]}', 12, INK, weight="700")]
    if rank:
        o.append(txt(BW - 12, 21,
                     "winner" if rank == 1 else f"#{rank}", 10, GHOST, anchor="end"))
    cy = H_HEAD + 12
    for who, ctry in n["fighters"]:
        o += [txt(12, cy, clip(who, 22), 11.5, INK),
              txt(BW - 12, cy, clip(ctry, 12), 9.5, MUTE, anchor="end")]
        cy += H_FIGHTER
    return "\n".join(o + ["</g>"]), h


def render_node(n, x, y):
    """A knockout match box: two corners, one row each."""
    m = n.get("m")
    o = [f'<g transform="translate({x:.1f},{y:.1f})">',
         f'<rect width="{BW}" height="{BH}" rx="7" fill="{CARD}" stroke="{LINE}"'
         + ('' if m else ' stroke-dasharray="4 3"') + '/>',
         f'<line x1="0" y1="{BH/2}" x2="{BW}" y2="{BH/2}" stroke="{LINE}"/>']
    w = winner_of(m) if m else None
    for i in range(2):
        ty = 16 + i * (BH / 2)
        if not m:
            continue
        who = m["red"] if i == 0 else m["blue"]
        ctry = m["red_country"] if i == 0 else m["blue_country"]
        won = w == norm(who)
        o += [txt(12, ty, clip(who, 20), 11.5, WIN if won else (RED if i == 0 else BLUE),
                  weight="700" if won else "400"),
              txt(BW - 12, ty, clip(ctry, 11), 9.5, MUTE, anchor="end")]
    if m:
        o.append(txt(BW / 2, BH + 12, meta_line(m), 9.5, MUTE, anchor="middle"))
    return "\n".join(o + ["</g>"]), BH


def elbow(x1, y1, x2, y2):
    mx = (x1 + x2) / 2
    return (f'<path d="M {x1:.1f} {y1:.1f} H {mx:.1f} V {y2:.1f} H {x2:.1f}" '
            f'fill="none" stroke="{LINE}" stroke-width="1.6"/>')


def render_bracket(cat, root, label):
    D = rounds_above(root)                          # columns needed on each side
    if D < 1:
        return None

    kids = root["children"]
    half = math.ceil(len(kids) / 2) or 1
    sides = [("L", kids[:half]), ("R", kids[half:])]

    slot_h = max(72, max(leaf_h(l) for l in leaves(root)) + 20)
    n_slots = max(sum(len(leaves(k)) for k in s) for _, s in sides if s) or 1
    body_h = n_slots * slot_h
    y0 = PAD + 62

    left_inner = PAD + (D - 1) * (BW + HGAP) + BW
    cx = left_inner + CGAP + OW / 2
    width, height = 2 * cx, y0 + body_h + PAD

    def col_x(n, side):
        xl = PAD + rounds_above(n) * (BW + HGAP)
        return xl if side == "L" else 2 * cx - xl - BW

    pos = []

    def place(n, side, cur):
        if not n["children"]:
            y = y0 + (cur[0] + 0.5) * slot_h
            cur[0] += 1
        else:
            y = sum(place(c, side, cur) for c in n["children"]) / len(n["children"])
        pos.append((n, col_x(n, side), y, rounds_above(n), side))
        return y

    for side, ks in sides:
        cur = [0]
        for k in ks:
            place(k, side, cur)

    boxes, links = [], []
    geom = {}
    for n, x, y, d, side in pos:
        if is_box(n):
            svg, h = render_node(n, x, y - BH / 2)
        else:
            svg, h = render_leaf(n, x, y - leaf_h(n) / 2)
        boxes.append(svg)
        geom[id(n)] = (x, y, h, side)

    for n, x, y, d, side in pos:
        for c in n["children"]:
            cx0, cy0, _, _ = geom[id(c)]
            x_out = cx0 + BW if side == "L" else cx0
            x_in = x if side == "L" else x + BW
            links.append(elbow(x_out, cy0, x_in, y))
    # innermost boxes into the champion node
    for side, ks in sides:
        for k in ks:
            x, y, _, _ = geom[id(k)]
            x_out = x + BW if side == "L" else x
            x_in = cx - OW / 2 if side == "L" else cx + OW / 2
            links.append(elbow(x_out, y, x_in, y0 + body_h / 2))

    fin = root.get("m")
    champ = None
    if fin:
        w = winner_of(fin)
        champ = next((n for n in (fin["red"], fin["blue"]) if norm(n) == w), None)
    oy = y0 + body_h / 2
    centre = [f'<ellipse cx="{cx:.1f}" cy="{oy:.1f}" rx="{OW/2}" ry="{OH/2}" '
              f'fill="{CARD}" stroke="{INK if champ else LINE}" stroke-width="2"'
              + ('' if champ else ' stroke-dasharray="5 4"') + '/>',
              txt(cx, oy - (6 if fin else 0), clip(champ, 16) if champ else "CHAMPION",
                  12.5 if champ else 11.5, WIN if champ else GHOST,
                  anchor="middle", weight="700")]
    if fin and not champ:
        centre.append(txt(cx, oy + 12, meta_line(fin), 9, MUTE, anchor="middle"))

    n_ko = sum(len(v) for v in cat["rounds"].values())
    head = [f'<rect width="{width:.0f}" height="{height:.0f}" fill="{BG}"/>',
            txt(PAD, PAD + 22, label, 20, INK, weight="700"),
            txt(width - PAD, PAD + 22,
                f'{len(cat["poules"])} poule(s) \u00b7 '
                + (f'{n_ko} knockout bouts' if n_ko else 'projected bracket'),
                11.5, MUTE, anchor="end")]
    if cat["unknown_phases"]:
        head.append(txt(PAD, PAD + 40, "unrecognised phase: "
                        + ", ".join(sorted(cat["unknown_phases"])[:3]), 10.5, RED))

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">\n'
            + "\n".join(head + links + boxes + centre) + "\n</svg>\n"), width


def render_poule_detail(cat, width):
    """The schedule/results table that the bracket boxes can't carry."""
    names = sorted(cat["poules"])
    if not names:
        return ""
    cols = max(1, int((width - 2 * PAD + GAP) // (W_POULE + GAP)))
    hs = [H_HEAD + H_FIGHTER * len(fighters_of(cat["poules"][n])) + H_SEP
          + H_MATCH * len(cat["poules"][n]) + 14 for n in names]
    cy = [PAD + 40] * cols
    placed = []
    for n, h in zip(names, hs):
        c = min(range(cols), key=lambda i: cy[i])
        placed.append((n, PAD + c * (W_POULE + GAP), cy[c], h))
        cy[c] += h + GAP
    height = max(cy) - GAP + PAD

    o = [f'<rect width="{width:.0f}" height="{height:.0f}" fill="{BG}"/>',
         txt(PAD, PAD + 18, "Poule schedule", 13, MUTE, weight="700")]
    for n, x, y, h in placed:
        ms = cat["poules"][n]
        o += [f'<g transform="translate({x:.1f},{y:.1f})">',
              f'<rect width="{W_POULE}" height="{h}" rx="9" fill="{CARD}" stroke="{LINE}"/>',
              txt(14, 21, f"Poule {poule_label(cat, n)}", 12.5, INK, weight="700")]
        yy = H_HEAD + 6
        for i, (who, ctry) in enumerate(fighters_of(ms), 1):
            o += [txt(14, yy, f"{i}. {clip(who, 24)}", 11.5, INK),
                  txt(W_POULE - 14, yy, clip(ctry, 16), 10, MUTE, anchor="end")]
            yy += H_FIGHTER
        o.append(f'<line x1="14" y1="{yy - 6}" x2="{W_POULE - 14}" y2="{yy - 6}" '
                 f'stroke="{LINE}"/>')
        yy += H_SEP
        for m in ms:
            o += [f'<text x="14" y="{yy}" font-family="{FONT}" font-size="11.5">'
                  f'<tspan fill="{RED}">{escape(clip(m["red"], 17))}</tspan>'
                  f'<tspan fill="{MUTE}"> vs </tspan>'
                  f'<tspan fill="{BLUE}">{escape(clip(m["blue"], 17))}</tspan></text>',
                  txt(14, yy + 14, meta_line(m, True), 10, MUTE)]
            yy += H_MATCH
        o.append("</g>")

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">\n'
            + "\n".join(o) + "\n</svg>\n")


def render_schedule_html(bouts, highlight=()):
    """Every bout, grouped by day then ring, in running order.

    Written as HTML rather than SVG so it stays selectable and searchable -
    this is the view you read on the day, not one you look at.
    """
    hl = {norm(h) for h in highlight}
    days = sorted({b["date"] for b in bouts if b["date"]})
    rings = sorted({b["ring"] for b in bouts if b["ring"]},
                   key=lambda r: (int(r) if r.isdigit() else 99, r))
    if not days or not rings:
        return ""

    out = ['<h2 class="sched">Full schedule by ring</h2>']
    for day in days:
        out.append(f'<h3>{escape(day)}</h3><div class="rings">')
        for ring in rings:
            ms = sorted((b for b in bouts
                         if b["date"] == day and b["ring"] == ring),
                        key=lambda b: b["time"].zfill(5))
            out.append(f'<div class="ring"><h4>Ring {escape(ring)}'
                       f'<span>{len(ms)} bout{"" if len(ms) == 1 else "s"}'
                       f'</span></h4><table>')
            for b in ms:
                label = parse_category(b["category"])[0]
                phase = b.get("phase", "")
                mark = " class='hl'" if (norm(b["red"]) in hl
                                         or norm(b["blue"]) in hl) else ""
                res = b.get("result") or ""
                # the site's placeholder for an unfought bout is noise here
                if re.search(r"pas encore eu lieu|not.*taken place", res, re.I):
                    res = ""
                out.append(
                    f'<tr{mark}><td class="t">{escape(b["time"])}</td><td>'
                    f'<div class="cat">{escape(label)}'
                    + (f' &middot; {escape(phase)}' if phase else '') + '</div>'
                    f'<div class="vs"><span class="r">{escape(b["red"])}</span>'
                    f'<span class="x">v</span>'
                    f'<span class="b">{escape(b["blue"])}</span></div>'
                    + (f'<div class="res">{escape(clip(res, 60))}</div>' if res else '')
                    + '</td></tr>')
            if not ms:
                out.append('<tr><td colspan="2" class="none">no bouts</td></tr>')
            out.append('</table></div>')
        out.append('</div>')
    return "\n".join(out)


SCHED_CSS = (
    "h2.sched{margin-top:56px;border-top:1px solid #d4d4d8;padding-top:28px}"
    "h3{font-size:13px;color:#71717a;margin:26px 0 10px;font-weight:700}"
    ".rings{display:flex;gap:14px;align-items:flex-start}"
    ".ring{flex:1;background:#ffffff;border:1px solid #d4d4d8;border-radius:10px;"
    "overflow:hidden}"
    ".ring h4{margin:0;padding:10px 12px;font-size:12px;background:#fafafa;"
    "border-bottom:1px solid #d4d4d8;display:flex;justify-content:space-between}"
    ".ring h4 span{font-weight:400;color:#a1a1aa}"
    ".ring table{width:100%;border-collapse:collapse}"
    ".ring td{padding:7px 12px;border-top:1px solid #f4f4f5;vertical-align:top}"
    ".ring td.t{width:52px;font-variant-numeric:tabular-nums;color:#71717a;"
    "font-size:12px;white-space:nowrap}"
    ".cat{font-size:10.5px;color:#a1a1aa;margin-bottom:2px}"
    ".vs{font-size:12px;line-height:1.45}"
    # keep each name intact; wrap between the two, never inside one
    ".vs .r,.vs .b{color:#c0392b;white-space:nowrap;display:inline-block}"
    ".vs .b{color:#2265ad}"
    ".vs .x{color:#a1a1aa;margin:0 5px;font-size:10.5px}"
    ".res{font-size:10.5px;color:#15803d;margin-top:2px}"
    ".none{color:#a1a1aa;font-size:12px}"
    "tr.hl td{background:#fffbeb}"
    "tr.hl td.t{box-shadow:inset 3px 0 0 #f59e0b}"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qualify", type=int, default=2,
                    help="qualifiers per poule when projecting an empty bracket")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--highlight", action="append", default=[], metavar="NAME",
                    help="mark this fighter's bouts in the schedule (repeatable)")
    args = ap.parse_args()

    cats = build(debug=args.debug)
    OUT.mkdir(exist_ok=True)

    # This directory is only ever written to, so a category that changes name
    # (or a run with a broken parser) leaves its old svg behind for good.
    # Clear what this script generates - and nothing else.
    stale = [f for f in OUT.iterdir()
             if f.suffix == ".svg" or f.name == "index.html"]
    for f in stale:
        f.unlink()
    if stale:
        print(f"removed {len(stale)} file(s) from a previous run\n")

    index = []

    for label, cat in cats.items():
        root = tree_from_data(cat) or tree_skeleton(cat, args.qualify)
        if root is None:
            print(f"{label}: skipped (nothing to draw)")
            continue
        out = render_bracket(cat, root, label)
        if out is None:
            print(f"{label}: skipped (bracket too shallow)")
            continue
        svg, width = out
        stem = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") or "category"
        (OUT / f"{stem}.svg").write_text(svg, encoding="utf-8")
        detail = render_poule_detail(cat, width)
        if detail:
            (OUT / f"{stem}_poules.svg").write_text(detail, encoding="utf-8")
        index.append((label, stem, cat, bool(cat["rounds"])))
        n_ko = sum(len(v) for v in cat["rounds"].values())
        print(f"{label}: {len(cat['poules'])} poule(s), "
              + (f"{n_ko} knockout bouts" if n_ko else "projected skeleton")
              + (" [!]" if cat["unknown_phases"] else ""))

    index.sort(key=lambda r: (r[2]["gender"] or "zz",
                              r[2]["kg"] if r[2]["kg"] is not None else 1e9))
    cards = "\n".join(
        f'<section><h2>{escape(l)}'
        + ('' if real else ' <em>projected</em>') + '</h2>'
        f'<img src="{s}.svg" alt="{escape(l)}">'
        f'<img src="{s}_poules.svg" alt="{escape(l)} poules" class="d"></section>'
        for l, s, _, real in index)
    schedule = render_schedule_html(rows("bouts.csv"), args.highlight)
    (OUT / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Assaut - brackets</title>"
        f"<style>body{{font-family:{FONT};margin:40px auto;max-width:1300px;"
        f"background:{BG};color:{INK}}}h2{{font-size:15px;margin:36px 0 10px}}"
        f"em{{color:{GHOST};font-style:normal;font-size:12px}}"
        f"img{{width:100%;border:1px solid {LINE};border-radius:10px;"
        f"background:{CARD}}}img.d{{margin-top:10px}}" + SCHED_CSS + "</style>"
        + cards + schedule, encoding="utf-8")
    print(f"\n{len(index)} weight categories -> {OUT}/  (open {OUT}/index.html)")


if __name__ == "__main__":
    main()
