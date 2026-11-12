"""Seeding, geodesy and gazetteer helpers shared by the generator modules."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

GAZETTEER_DIR = Path(__file__).resolve().parent.parent / "atlas" / "data" / "gazetteer"
R_EARTH = 6_371_008.8


def seed_of(*parts) -> int:
    """Stable 64-bit seed from arbitrary parts (never Python's salted ``hash``)."""
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big")


def rng_of(*parts) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed_of(*parts)))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def offset_m(lat, lon, north_m, east_m) -> tuple[float, float]:
    dlat = math.degrees(north_m / R_EARTH)
    dlon = math.degrees(east_m / (R_EARTH * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def iso_utc(ts: float) -> str:
    """ISO-8601 UTC with millisecond precision and a trailing Z."""
    ms = round(ts * 1000)
    d = datetime.fromtimestamp(ms // 1000, tz=timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + f".{ms % 1000:03d}Z"


def parse_utc(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def local_naive(ts: float, offset_min: int) -> datetime:
    return (utc(ts) + timedelta(minutes=offset_min)).replace(tzinfo=None)


def local_ts(day: str, hhmm: str, offset_min: int) -> float:
    """Epoch seconds of local wall-clock ``hhmm`` (hours may exceed 23) on local ``day``."""
    parts = [int(x) for x in hhmm.split(":")]
    h, m = parts[0], parts[1]
    s = parts[2] if len(parts) > 2 else 0
    base = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return (base + timedelta(hours=h, minutes=m, seconds=s) - timedelta(minutes=offset_min)).timestamp()


@lru_cache(maxsize=1)
def load_gazetteer() -> dict[str, dict]:
    """All POIs keyed by id, read from the same files the pipeline's geocoder uses."""
    index = json.loads((GAZETTEER_DIR / "index.json").read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for reg in index["regions"]:
        data = json.loads((GAZETTEER_DIR / reg["file"]).read_text(encoding="utf-8"))
        for p in data["pois"]:
            if p["id"] in out:
                raise ValueError(f"duplicate gazetteer id {p['id']}")
            out[p["id"]] = p
    return out


class Path3:
    """Polyline of (lat, lon, ele) with arc-length parameterisation."""

    def __init__(self, pts: list[tuple[float, float, float]]):
        self.pts = pts
        self.cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.cum.append(self.cum[-1] + haversine_m(a[0], a[1], b[0], b[1]))
        self.length = self.cum[-1]

    def at(self, frac: float) -> tuple[float, float, float]:
        if self.length <= 0 or len(self.pts) == 1:
            return self.pts[0]
        d = min(max(frac, 0.0), 1.0) * self.length
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= d:
                lo = mid
            else:
                hi = mid
        seg = self.cum[hi] - self.cum[lo]
        f = 0.0 if seg <= 0 else (d - self.cum[lo]) / seg
        a, b = self.pts[lo], self.pts[hi]
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f)

    def ascent(self) -> float:
        return sum(max(0.0, b[2] - a[2]) for a, b in zip(self.pts, self.pts[1:]))


def densify(pts, step_m: float, wiggle_m: float, ele_bump_m: float, rng) -> list[tuple[float, float, float]]:
    """Subdivide a polyline every ``step_m`` and add smooth lateral wiggle / elevation bumps.

    End points and the original vertices stay exactly where they were, so legs meet at POIs.
    """
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d = haversine_m(a[0], a[1], b[0], b[1])
        n = max(1, int(d // step_m))
        ph1, ph2 = rng.uniform(0, 2 * math.pi, 2)
        k1, k2 = rng.integers(1, 4), rng.integers(2, 6)
        # unit normal in local metres
        dn = (b[0] - a[0]) * 111_195.0
        de = (b[1] - a[1]) * 111_195.0 * math.cos(math.radians(a[0]))
        norm = math.hypot(dn, de) or 1.0
        nn, ne = -de / norm, dn / norm
        for i in range(1, n + 1):
            f = i / n
            env = math.sin(math.pi * f)  # zero at both ends
            w = wiggle_m * env * (0.7 * math.sin(k1 * math.pi * f + ph1) + 0.3 * math.sin(k2 * math.pi * f + ph2))
            lat = a[0] + (b[0] - a[0]) * f
            lon = a[1] + (b[1] - a[1]) * f
            lat, lon = offset_m(lat, lon, nn * w, ne * w)
            ele = a[2] + (b[2] - a[2]) * f + ele_bump_m * env * math.sin(k2 * math.pi * f + ph2)
            out.append((lat, lon, ele))
        out[-1] = b
    return out
