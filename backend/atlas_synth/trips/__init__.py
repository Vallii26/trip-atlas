"""Trip declarations. ``get(slug)`` returns the TripBuilder of a trip (the ``formats`` set is not
itinerary-shaped and lives in ``atlas_synth.formats``). ``MAIN`` is the chronological order
used for "firsts"."""

from __future__ import annotations

import importlib

MAIN = ["lisbon", "alps", "rail"]
HOSTILE = ["stress5000", "tiny3", "vintage", "formats"]
_WHERE = {"lisbon": ("lisbon", "define"), "alps": ("alps", "define"), "rail": ("rail", "define"),
          "tiny3": ("hostile", "tiny3"), "vintage": ("hostile", "vintage"), "stress5000": ("hostile", "stress5000")}


def get(slug: str, seed: int | None = None):
    mod, fn = _WHERE[slug]
    f = getattr(importlib.import_module(f"{__name__}.{mod}"), fn)
    return f(seed) if seed is not None else f()
