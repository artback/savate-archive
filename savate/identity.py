"""Deciding when two spellings are one fighter.

A career only exists if the same person can be recognised across sources, and
sources spell people differently: one writes NIHAT GULIYEV, another Nihat
GULIYEV; one puts the surname first, another last; accents survive one export
and not the next.

So a name is reduced to a key that ignores what varies and keeps what does not:
case, accents, punctuation and word order go; the words themselves stay. Two
spellings with the same key are the same name, and are merged.

What is *not* done matters more. Names that merely look similar are left alone.
In this archive the near misses are overwhelmingly siblings and common given
names - CAVROT-WESTERLINCK Noha and CAVROT-WESTERLINCK Ethan, Farzam Fallah and
MohammadHossein Fallah, three unrelated Iranian fighters sharing "Sajjad". A
matcher confident enough to merge those would fabricate careers, and a fabricated
career is worse than a fragmented one: a split record is visibly incomplete,
while a merged one looks authoritative and is wrong.

Anything beyond an exact key match is therefore a *candidate*, reported for a
person to confirm, and recorded in fighters.json once confirmed. The file also
records the opposite - two people who genuinely share a name and must stay
apart - because that is the one case the key gets wrong on its own.
"""

import json
import re
import unicodedata
from pathlib import Path

OVERRIDES = Path("fighters.json")

# Particles that some sources capitalise into the surname and others drop.
# They are kept in the key - dropping them would merge "DE SOUSA" with "SOUSA",
# who are not reliably the same person - but they are ignored when *suggesting*
# candidates, which is where a near miss should surface.
PARTICLES = {"de", "da", "di", "du", "van", "von", "der", "den", "el", "al",
             "la", "le", "ben", "bin", "dos", "das"}


# Letters that are not a base plus an accent, and so survive NFKD untouched.
# Croatian đ is the one that matters here: unlike ć, which decomposes to c and
# a combining acute, đ is its own letter. Folding therefore left it in place
# while the same name printed without the stroke folded to a plain d, and the
# two never met - Patrik Grđan and GRDAN PATRIK were two competitors.
#
# Worse, `tokens()` treats anything outside [a-z0-9] as a separator, so đ did
# not merely survive: it split the word around itself. "Grđan" became "gr" and
# "an", "Srđan" became "sr" and "an", and 79 names were quietly shattered into
# fragments that then keyed nothing like the name they came from.
#
# Each is mapped to the letter the sources use when they drop the diacritic,
# which for this archive is the bare consonant: the Croatian federation prints
# GRDAN, not GRDJAN.
LETTERS = {
    "đ": "d", "Đ": "d", "ð": "d", "Ð": "d",
    "ł": "l", "Ł": "l", "ŀ": "l", "Ŀ": "l",
    "ø": "o", "Ø": "o",
    "ħ": "h", "Ħ": "h", "ŧ": "t", "Ŧ": "t",
    "þ": "th", "Þ": "th", "ß": "ss",
    "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
    "ı": "i", "İ": "i",
}


def fold(text):
    """Accent- and case-free form of a string."""
    text = " ".join(str(text or "").split())
    text = "".join(LETTERS.get(c, c) for c in text)
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def tokens(name):
    """A name's words, normalised: no case, accents, punctuation or order."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", fold(name))
    return tuple(sorted(w for w in cleaned.split() if w))


def key(name):
    """The identity key for a name. Equal keys are the same name."""
    return " ".join(tokens(name))


# Orthographic variation that is the same name written under different
# conventions, not a different name: Patrik and Patrick, Erica and Erika,
# Monica and Monika, Loïc and Loic, Nandi and Nandy. A federation writes a
# competitor the way its own language spells them, and across nineteen years
# and three alphabets the same person is written several ways.
#
# These are substitutions, not similarity. Two names match here only if they
# are IDENTICAL once the convention is set aside - which is why it can be
# trusted to merge, where "looks a bit alike" cannot. CAVROT-WESTERLINCK Noha
# and CAVROT-WESTERLINCK Ethan stay two people, as they must.
_CONVENTION = [
    ("dj", "d"),    # Nadja/Nađa - đ is transliterated dj as often as d
    ("ij", "i"),    # Lidija/Lidia, Antonija/Antonia, Florijanić/Florjanić
    ("ck", "k"),    # Patrick -> Patrik
    ("c", "k"),     # Erica/Erika, Marco/Marko, and ć already folds to c
    ("ph", "f"),    # Sophie/Sofie
    ("y", "i"),     # Nandy -> Nandi
    ("w", "v"),     # Slavic transliteration
    ("z", "s"),     # Elizabeth/Elisabeth
    ("qu", "k"),
    ("x", "ks"),
]


def loose(word):
    """A token with spelling convention set aside, for matching only.

    Never used to display a name, and never used to decide that two people are
    different - only that two spellings of one name are the same spelling.
    """
    out = fold(word)
    for a, b in _CONVENTION:
        out = out.replace(a, b)
    # Doubled letters: Anaelle/Annaelle, Sharon/Sharonn.
    squeezed = []
    for ch in out:
        if not squeezed or squeezed[-1] != ch:
            squeezed.append(ch)
    out = "".join(squeezed)
    # A trailing e that one language writes and another does not.
    return out[:-1] if len(out) > 4 and out.endswith("e") else out


def loose_key(name):
    """The identity key with spelling convention set aside."""
    return " ".join(sorted(loose(w) for w in tokens(name) if loose(w)))


def core(name):
    """The name's words without particles - for suggesting, never for merging."""
    return frozenset(tokens(name)) - PARTICLES


def load_overrides(path=OVERRIDES):
    """{"same": [[...]], "different": [[...]]} - human decisions, not guesses."""
    if not Path(path).exists():
        return {"same": [], "different": []}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"same": data.get("same", []), "different": data.get("different", [])}


class Register:
    """Every spelling seen, grouped into fighters.

    A fighter's id is the key of its most common spelling, so it is stable while
    the data is, and readable in a query. The display name is the spelling the
    sources use most - there is no way to know which word is the surname across
    a dozen national conventions, so the archive's own usage decides.
    """

    def __init__(self, overrides=None):
        self.overrides = overrides or {"same": [], "different": []}
        self.seen = {}          # spelling -> {"count": n, "countries": {...}}
        self._merged = {}       # key -> canonical key
        # Pairs merged by spelling convention rather than an exact key match,
        # so a build can print what it did rather than doing it silently.
        self.convention = []
        self.slips = []

    def add(self, name, country="", count=1):
        if not name:
            return
        entry = self.seen.setdefault(name, {"count": 0, "countries": set()})
        entry["count"] += count
        if country:
            entry["countries"].add(country)

    def _link(self):
        """Union-find over keys, seeded by the confirmed "same" overrides."""
        parent = {}

        def find(k):
            parent.setdefault(k, k)
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for name in self.seen:
            find(key(name))
        for group in self.overrides["same"]:
            keys = [key(n) for n in group if n]
            for other in keys[1:]:
                union(keys[0], other)

        # Spellings that are the same name under different conventions, where
        # the nations do not contradict each other. This is a rule, not a list:
        # it carries over to every competitor the archive ever gains, so nobody
        # has to write Patrik and Patrick into a file by hand. The guard is
        # that the loose keys must be EQUAL - a different name is still a
        # different person, however similar it looks.
        by_loose = {}
        for name in self.seen:
            by_loose.setdefault(loose_key(name), []).append(name)
        self.convention = []
        for shared, names in by_loose.items():
            if len(names) < 2 or not shared:
                continue
            exact = {key(n) for n in names}
            if len(exact) < 2:
                continue
            for other in list(names)[1:]:
                first = names[0]
                if not self._compatible(first, other):
                    continue
                if key(first) != key(other):
                    self.convention.append((first, other))
                union(key(first), key(other))
        # A confirmed "different" pair must not be merged by a shared key, so
        # each member is pinned to its own group under its exact spelling.
        # Last, because it weighs how often a name is written and that is only
        # known once the spellings that are plainly one name have been joined.
        # "GOUGET LOIC" alone is written four times; the person is written
        # eleven, and eleven against two is what makes the rare form a slip.
        self.slips = self._slips(union, find)

        pinned = {n for pair in self.overrides["different"] for n in pair}
        return find, pinned

    def _slips(self, union, find):
        """Merge a spelling that is one keystroke from a much commoner one.

        BUGADA Marine appears 22 times and Marine BUGUDA once; GERSTMANN MARCO
        fifteen times and Marcol Gerstmann once. These are not two spellings of
        a name, they are one spelling and one transcription slip, and the
        evidence is the asymmetry: a real variant recurs, because it is how some
        federation writes that person. A slip appears once.

        So the gate is frequency, not similarity. A pair that is one edit apart
        AND whose nations agree AND where one side is rare while the other is
        common is a slip. Two spellings that both recur are left for a human:
        Lidia and Lidija Abazovski, seventeen and six, are a real question.
        """
        # How often the archive writes each person, summed over the spellings
        # already joined to them.
        totals = {}
        for name, entry in self.seen.items():
            totals[find(key(name))] = totals.get(find(key(name)), 0) + entry["count"]
        counts = {n: totals.get(find(key(n)), 0) for n in self.seen}
        index = {}
        for name in self.seen:
            squeezed = key(name).replace(" ", "")
            if len(squeezed) < 6:
                continue
            for i in range(len(squeezed)):
                index.setdefault(squeezed[:i] + squeezed[i + 1:], []).append(name)
            index.setdefault(squeezed, []).append(name)

        merged = []
        for group in index.values():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if key(a) == key(b) or not self._compatible(a, b):
                        continue
                    rare, common = sorted((a, b), key=lambda n: counts.get(n, 0))
                    few, many = counts.get(rare, 0), counts.get(common, 0)
                    # A group already joined to the other is not a slip.
                    if find(key(rare)) == find(key(common)):
                        continue
                    # Rare, and decisively outnumbered. Both thresholds matter:
                    # without the ratio a pair of equals would merge, and
                    # without the cap a busy variant would be swallowed.
                    if few <= 3 and many >= 5 and many >= few * 3:
                        merged.append((common, rare))
                        union(key(rare), key(common))
        return merged

    def _compatible(self, a, b):
        """Could these two spellings be one person, by nation?

        A nation the source never printed is not a contradiction. Most of this
        archive's placings carry no country at all - a national championship
        does not restate everyone's nationality - so treating "unknown" as a
        conflict would refuse almost every merge worth making.
        """
        ca = {c for c in self.seen.get(a, {}).get("countries", ()) if c}
        cb = {c for c in self.seen.get(b, {}).get("countries", ()) if c}
        if not ca or not cb:
            return True
        return bool(ca & cb)

    def fighters(self):
        """[{id, name, aliases, countries, appearances}] - one per person."""
        find, pinned = self._link()
        groups = {}
        for name, entry in self.seen.items():
            group = f"!{name}" if name in pinned else find(key(name))
            groups.setdefault(group, []).append((name, entry))

        out = []
        for group, members in groups.items():
            members.sort(key=lambda m: (-m[1]["count"], m[0]))
            display = members[0][0]
            countries = sorted({c for _, e in members for c in e["countries"]})
            out.append({
                "id": key(display) if not group.startswith("!") else key(display),
                "name": display,
                "aliases": sorted(n for n, _ in members),
                "countries": countries,
                "appearances": sum(e["count"] for _, e in members),
            })
        out.sort(key=lambda f: (-f["appearances"], f["name"]))
        # Two different people can share a key (two Jean Duponts). Ids must stay
        # unique, so a collision is suffixed and reported by candidates().
        used = {}
        for f in out:
            base = f["id"]
            used[base] = used.get(base, 0) + 1
            if used[base] > 1:
                f["id"] = f"{base} #{used[base]}"
        return out

    def index(self):
        """spelling -> fighter id, for keying rows."""
        out = {}
        for f in self.fighters():
            for alias in f["aliases"]:
                out[alias] = f["id"]
        return out


def _drop_one(word):
    """Every string one deletion away from `word`."""
    return {word[:i] + word[i + 1:] for i in range(len(word))}


def near_misses(register, max_length_gap=2):
    """Pairs whose names differ by about one character, for a human to rule on.

    `candidates()` finds people who share a whole word. It cannot see the other
    way one person splits in two, which is a single character: Florijanić and
    Florjanić, Valentino and Valention, and Florjanić printed as Florjanid where
    a PDF read the ć as a d. Four spellings, one competitor, four careers.

    A substitution is two deletions apart, so both sides are indexed by their
    drop-one variants and a shared variant means an edit distance of roughly
    one. That is cheap - linear in the number of names - where comparing every
    pair with every other is not, at four thousand people.

    This still only ever suggests. Siblings and shared given names are exactly
    the near misses this archive is full of, and a machine cannot tell
    "Florijanić / Florjanić, one person" from "Cavrot-Westerlinck Noha /
    Cavrot-Westerlinck Ethan, two people" - only a reader can. What it does do
    is put the decision in front of that reader instead of leaving the split
    invisible.
    """
    people = register.fighters()
    index, out, seen = {}, [], set()
    for person in people:
        squeezed = key(person["name"]).replace(" ", "")
        if len(squeezed) < 5:
            continue
        for variant in _drop_one(squeezed) | {squeezed}:
            index.setdefault(variant, []).append((squeezed, person))

    for variant, group in index.items():
        if len(group) < 2:
            continue
        for i, (a_key, a) in enumerate(group):
            for b_key, b in group[i + 1:]:
                if a["id"] == b["id"] or a_key == b_key:
                    continue
                if abs(len(a_key) - len(b_key)) > max_length_gap:
                    continue
                pair = tuple(sorted((a["id"], b["id"])))
                if pair in seen:
                    continue
                seen.add(pair)
                # A nation the source never printed is not a disagreement.
                ca, cb = set(a["countries"]), set(b["countries"])
                shared_country = bool(ca & cb) or not ca or not cb
                out.append({
                    "a": a["name"], "b": b["name"],
                    "a_id": a["id"], "b_id": b["id"],
                    "a_appearances": a["appearances"],
                    "b_appearances": b["appearances"],
                    "same_country": shared_country,
                    "countries": sorted(set(a["countries"]) | set(b["countries"])),
                })
    # Same country and both seen often is the likeliest real split, so it is
    # what a reader should be shown first.
    out.sort(key=lambda r: (not r["same_country"],
                            -(r["a_appearances"] + r["b_appearances"])))
    return out


def candidates(register, minimum_shared=1):
    """Pairs that might be one person, for a human to rule on.

    Deliberately noisy in one direction only: it suggests, and never acts. Each
    suggestion says why, so a sibling pair is obvious at a glance.
    """
    people = register.fighters()
    out = []
    for i, a in enumerate(people):
        for b in people[i + 1:]:
            if a["id"] == b["id"]:
                continue
            shared = core(a["name"]) & core(b["name"])
            if len(shared) < minimum_shared:
                continue
            a_only = core(a["name"]) - shared
            b_only = core(b["name"]) - shared
            # One name being a subset of the other is the interesting case: a
            # dropped middle name, or a particle one source kept. Two names that
            # each have words the other lacks are usually two people.
            if a_only and b_only:
                reason = "share only part of the name - probably two people"
            elif not a_only and not b_only:
                reason = "same words, different key"
            else:
                reason = "one name is the other plus a word"
            same_country = bool(set(a["countries"]) & set(b["countries"]))
            out.append({
                "a": a["name"], "b": b["name"],
                "shared": sorted(shared), "reason": reason,
                "same_country": same_country,
                "confidence": ("review" if a_only and b_only else "likely"),
            })
    order = {"likely": 0, "review": 1}
    out.sort(key=lambda c: (order[c["confidence"]], not c["same_country"], c["a"]))
    return out
