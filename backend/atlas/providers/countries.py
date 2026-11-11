"""Offline country lookup by point-in-polygon over Natural Earth 1:50m (world-atlas TopoJSON).

Used so that "which country was this?" never depends on the nearest city, which is wrong near
borders. Resolution is ~1 km at the border; callers treat points within ``border_margin_m`` of a
border as lower confidence.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "basemap" / "countries-50m.json"

Ring = list[tuple[float, float]]


def _decode(topo: dict) -> list[tuple[str, str, list[list[Ring]]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs: list[Ring] = []
    for arc in topo["arcs"]:
        x = y = 0
        pts: Ring = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idxs: list[int]) -> Ring:
        out: Ring = []
        for i in idxs:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(seg if not out else seg[1:])
        return out

    feats = []
    for g in topo["objects"]["countries"]["geometries"]:
        if g["type"] == "Polygon":
            polys = [[ring(r) for r in g["arcs"]]]
        elif g["type"] == "MultiPolygon":
            polys = [[ring(r) for r in poly] for poly in g["arcs"]]
        else:
            continue
        feats.append((str(g.get("id", "")), (g.get("properties") or {}).get("name", ""), polys))
    return feats


def _in_ring(x: float, y: float, r: Ring) -> bool:
    inside = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]
        xj, yj = r[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class CountryIndex:
    def __init__(self, path: Path = DATA) -> None:
        import geonamescache

        numeric_to_iso = {}
        for c in geonamescache.GeonamesCache().get_countries().values():
            numeric_to_iso[str(c["isonumeric"]).zfill(3)] = (c["iso"], c["name"])
        self._polys: list[tuple[tuple[float, float, float, float], list[Ring], str, str]] = []
        for num, name, polys in _decode(json.loads(path.read_text(encoding="utf-8"))):
            iso, nice = numeric_to_iso.get(num.zfill(3), ("", name))
            if not iso:
                continue
            for rings in polys:
                xs = [p[0] for p in rings[0]]
                ys = [p[1] for p in rings[0]]
                self._polys.append(((min(xs), min(ys), max(xs), max(ys)), rings, iso, nice))

    def lookup(self, lat: float, lon: float) -> tuple[str, str] | None:
        """(ISO alpha-2, English name) or None for open sea / unknown."""
        for (x0, y0, x1, y1), rings, iso, name in self._polys:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_ring(lon, lat, rings[0]):
                if not any(_in_ring(lon, lat, h) for h in rings[1:]):
                    return iso, name
        return None

    def lookup_near(self, lat: float, lon: float, margin_deg: float = 0.03) -> tuple[str, str] | None:
        """Like lookup, but tolerant of coastline simplification (harbours, piers, lake shores)."""
        hit = self.lookup(lat, lon)
        if hit:
            return hit
        for dlat, dlon in ((margin_deg, 0), (-margin_deg, 0), (0, margin_deg), (0, -margin_deg),
                           (margin_deg, margin_deg), (-margin_deg, -margin_deg),
                           (margin_deg, -margin_deg), (-margin_deg, margin_deg)):
            hit = self.lookup(lat + dlat, lon + dlon)
            if hit:
                return hit
        return None

    def near_border(self, lat: float, lon: float, margin_deg: float = 0.02) -> bool:
        """True if a point ~2 km away falls in a different country (or the sea)."""
        here = self.lookup(lat, lon)
        for dlat, dlon in ((margin_deg, 0), (-margin_deg, 0), (0, margin_deg), (0, -margin_deg)):
            other = self.lookup(lat + dlat, lon + dlon)
            if other is not None and here is not None and other[0] != here[0]:
                return True
        return False


@lru_cache
def country_index() -> CountryIndex:
    return CountryIndex()
