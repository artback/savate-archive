"""The adapter registry.

An adapter turns one federation's way of publishing results into canonical rows.
There will be many - FISav's PDFs, FFSavate, CESav, a timing system's export, a
spreadsheet a club emails over - and they have nothing in common except what
they produce. So they are discovered, not listed: drop a module in this package
and it is available to the CLI and the manifest with no edit anywhere else.

An adapter module needs exactly three things:

    NAME          the string a manifest entry names it by
    DESCRIPTION   one line, shown when listing adapters
    read(source, slug, meta=None, **options)
                  -> (Tournament, [Bout], Report)

`read` must not raise on bad data. Data from a federation is routinely
incomplete; that is a Report problem and a skipped row, not a crash. Raise only
when the source itself cannot be read at all.
"""

import importlib
import pkgutil

REQUIRED = ("NAME", "DESCRIPTION", "read")

_loaded = None


def discover(reload=False):
    """{name: module} for every adapter in this package."""
    global _loaded
    if _loaded is not None and not reload:
        return _loaded
    found = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        missing = [a for a in REQUIRED if not hasattr(module, a)]
        if missing:
            raise ImportError(
                f"adapter {info.name!r} is missing {', '.join(missing)} - see "
                f"{__name__}.__doc__ for the three things an adapter needs")
        if module.NAME in found:
            raise ImportError(f"two adapters both call themselves {module.NAME!r}")
        found[module.NAME] = module
    _loaded = found
    return found


def get(name):
    adapters = discover()
    if name not in adapters:
        raise KeyError(f"unknown adapter {name!r}; available: {', '.join(names())}")
    return adapters[name]


def names():
    return sorted(discover())


def catalogue():
    return [(name, discover()[name].DESCRIPTION) for name in names()]
