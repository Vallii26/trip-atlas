"""Reverse geocoding behind one interface (ARCHITECTURE §3).

``GazetteerGeocoder`` is offline and deterministic: bundled POIs (atlas/data/gazetteer/*.json)
plus the world's cities from ``geonamescache`` for locality/country fallback anywhere on Earth.
``NominatimGeocoder`` talks to an OSM Nominatim server, politely (cache + 1 request/second).
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

GAZETTEER_DIR = Path(__file__).resolve().parents[1] / "data" / "gazetteer"
EARTH_R = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


class GeoCandidate(BaseModel):
    poi_id: str
    name: str
    category: str | None = None
    lat: float
    lon: float
    distance_m: float = 0.0
    locality: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    alt_names: list[str] = Field(default_factory=list)
    source: str = "gazetteer"


class Area(BaseModel):
    """Administrative answer for a point: which town, which country."""

    locality: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    distance_m: float | None = None      # distance to the locality's reference point
    source: str = "gazetteer"


class Geocoder(Protocol):
    name: str

    def nearby(self, lat: float, lon: float, radius_m: float = 300.0, limit: int = 12) -> list[GeoCandidate]:
        """POIs within ``radius_m``, nearest first."""
        ...

    def area(self, lat: float, lon: float) -> Area:
        """Locality and country for a point (never raises; empty Area if unknown)."""
        ...

    def known_names(self) -> set[str]:
        """Every place name this geocoder could return (used by the faithfulness verifier)."""
        ...


class _Grid:
    """Tiny spatial hash; ~1.1 km cells at the equator."""

    def __init__(self, cell_deg: float = 0.01) -> None:
        self.cell = cell_deg
        self.cells: dict[tuple[int, int], list[Any]] = defaultdict(list)

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (math.floor(lat / self.cell), math.floor(lon / self.cell))

    def add(self, lat: float, lon: float, item: Any) -> None:
        self.cells[self._key(lat, lon)].append(item)

    def around(self, lat: float, lon: float, radius_m: float) -> list[Any]:
        dlat = radius_m / 111_320.0
        dlon = radius_m / (111_320.0 * max(0.05, math.cos(math.radians(lat))))
        k0 = self._key(lat - dlat, lon - dlon)
        k1 = self._key(lat + dlat, lon + dlon)
        out: list[Any] = []
        for i in range(k0[0], k1[0] + 1):
            for j in range(k0[1], k1[1] + 1):
                out.extend(self.cells.get((i, j), ()))
        return out


class GazetteerGeocoder:
    name = "gazetteer"

    def __init__(self, directory: Path | None = None, *, world_cities: bool = True) -> None:
        self._pois: list[dict[str, Any]] = []
        self._grid = _Grid(0.01)
        self._city_grid = _Grid(0.5)
        self._countries: dict[str, str] = {}
        directory = directory or GAZETTEER_DIR
        for f in sorted(directory.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data.get("pois") if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue  # index or metadata file
            for p in items:
                if not isinstance(p, dict) or "lat" not in p or "lon" not in p or "name" not in p:
                    continue
                self._pois.append(p)
                self._grid.add(p["lat"], p["lon"], p)
        if world_cities:
            self._load_world()

    def _load_world(self) -> None:
        try:
            import geonamescache
        except ImportError:  # pragma: no cover - dependency is declared
            return
        gc = geonamescache.GeonamesCache()
        self._countries = {c["iso"]: c["name"] for c in gc.get_countries().values()}
        for c in gc.get_cities().values():
            item = {
                "name": c["name"],
                "lat": float(c["latitude"]),
                "lon": float(c["longitude"]),
                "country_code": c["countrycode"],
                "population": int(c.get("population") or 0),
                "admin1": c.get("admin1code"),
            }
            self._city_grid.add(item["lat"], item["lon"], item)

    def nearby(self, lat: float, lon: float, radius_m: float = 300.0, limit: int = 12) -> list[GeoCandidate]:
        out: list[GeoCandidate] = []
        for p in self._grid.around(lat, lon, radius_m):
            d = haversine_m(lat, lon, p["lat"], p["lon"])
            if d <= radius_m:
                out.append(
                    GeoCandidate(
                        poi_id=str(p.get("id") or f"gaz:{p['name']}"),
                        name=p["name"],
                        category=p.get("category"),
                        lat=p["lat"],
                        lon=p["lon"],
                        distance_m=round(d, 1),
                        locality=p.get("locality"),
                        region=p.get("region"),
                        country=p.get("country"),
                        country_code=(p.get("country_code") or "").upper() or None,
                        alt_names=list(p.get("alt_names") or []),
                    )
                )
        out.sort(key=lambda c: (c.distance_m, c.poi_id))
        return out[:limit]

    def area(self, lat: float, lon: float) -> Area:
        # 1. A bundled POI close by knows its own locality better than a city centroid does.
        best_poi, best_d = None, float("inf")
        for p in self._grid.around(lat, lon, 3_000):
            if not p.get("locality"):
                continue
            d = haversine_m(lat, lon, p["lat"], p["lon"])
            if d < best_d:
                best_poi, best_d = p, d
        if best_poi is not None and best_d <= 3_000:
            return Area(
                locality=best_poi.get("locality"),
                region=best_poi.get("region"),
                country=best_poi.get("country"),
                country_code=(best_poi.get("country_code") or "").upper() or None,
                distance_m=round(best_d, 1),
            )
        # 2. Nearest city, lightly preferring larger places; beyond 60 km we only claim the country
        #    of the nearest city if it is within 150 km, and no locality at all.
        best, best_score, best_dist = None, float("inf"), float("inf")
        for c in self._city_grid.around(lat, lon, 150_000):
            d = haversine_m(lat, lon, c["lat"], c["lon"])
            score = d / (1.0 + 0.15 * math.log10(max(c["population"], 1_000) / 1_000))
            if score < best_score:
                best, best_score, best_dist = c, score, d
        # The country comes from border polygons, never from the nearest city (wrong near borders).
        from atlas.providers.countries import country_index

        hit = country_index().lookup_near(lat, lon)
        if best is None:
            if hit is None:
                return Area(source="none")
            return Area(country=hit[1], country_code=hit[0], source="borders")
        cc = hit[0] if hit else best["country_code"]
        same_country = best["country_code"] == cc
        return Area(
            locality=best["name"] if best_dist <= 25_000 and same_country else None,
            country=hit[1] if hit else self._countries.get(cc),
            country_code=cc,
            distance_m=round(best_dist, 1),
            source="world_cities",
        )

    def known_names(self) -> set[str]:
        names: set[str] = set()
        for p in self._pois:
            names.add(p["name"])
            names.update(p.get("alt_names") or [])
            for k in ("locality", "region", "country"):
                if p.get(k):
                    names.add(p[k])
        return names


class NominatimGeocoder:
    """OSM Nominatim adapter. Not exercised against the live service in this repo's tests
    (it is unreachable from the build environment); the response mapping is contract-tested
    against recorded-shape fixtures. Usage policy: identify yourself, max 1 request/second, cache."""

    name = "nominatim"

    # OSM class/type → our closed category vocabulary
    _CATEGORY = {
        ("amenity", "restaurant"): "restaurant", ("amenity", "cafe"): "cafe", ("amenity", "bar"): "bar",
        ("amenity", "pub"): "bar", ("amenity", "marketplace"): "market", ("tourism", "museum"): "museum",
        ("tourism", "viewpoint"): "viewpoint", ("tourism", "hotel"): "hotel", ("tourism", "hostel"): "hostel",
        ("tourism", "alpine_hut"): "alpine_hut", ("tourism", "attraction"): "monument",
        ("railway", "station"): "station", ("railway", "tram_stop"): "tram_stop", ("natural", "peak"): "peak",
        ("natural", "water"): "lake", ("natural", "beach"): "beach", ("leisure", "park"): "park",
        ("amenity", "place_of_worship"): "church", ("historic", "castle"): "castle",
        ("historic", "monument"): "monument", ("aeroway", "aerodrome"): "airport", ("shop", "bakery"): "bakery",
        ("place", "square"): "square", ("mountain_pass", "yes"): "pass",
    }

    def __init__(self, base_url: str, user_agent: str, cache_path: Path | None = None, *, client: Any = None,
                 min_interval_s: float = 1.0) -> None:
        if not user_agent:
            raise ValueError("Nominatim requires an identifying User-Agent (set ATLAS_NOMINATIM_USER_AGENT)")
        import httpx

        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": user_agent})
        self._cache_path = cache_path
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._last = 0.0
        self._min_interval = min_interval_s
        if cache_path and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self._client.get(self._base + path, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception:
                data = None       # a geocoder outage must degrade to "place unknown", never crash a run
            self._last = time.monotonic()
            if data is not None:
                self._cache[key] = data
                if self._cache_path:
                    self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                    self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
            return data

    @classmethod
    def _candidate(cls, item: dict[str, Any], lat: float, lon: float) -> GeoCandidate | None:
        name = item.get("name") or (item.get("namedetails") or {}).get("name")
        if not name:
            return None
        addr = item.get("address") or {}
        plat, plon = float(item["lat"]), float(item["lon"])
        return GeoCandidate(
            poi_id=f"osm:{item.get('osm_type', '?')[0]}{item.get('osm_id', '')}",
            name=name,
            category=cls._CATEGORY.get((item.get("class") or item.get("category"), item.get("type"))) or item.get("type"),
            lat=plat,
            lon=plon,
            distance_m=round(haversine_m(lat, lon, plat, plon), 1),
            locality=addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality"),
            region=addr.get("state") or addr.get("region"),
            country=addr.get("country"),
            country_code=(addr.get("country_code") or "").upper() or None,
            source="nominatim",
        )

    def nearby(self, lat: float, lon: float, radius_m: float = 300.0, limit: int = 12) -> list[GeoCandidate]:
        # Coordinates are rounded to ~11 m so that neighbouring photos share cache entries.
        data = self._get("/reverse", {"lat": round(lat, 4), "lon": round(lon, 4), "format": "jsonv2",
                                      "zoom": 18, "addressdetails": 1, "namedetails": 1})
        if not isinstance(data, dict) or "error" in data:
            return []
        c = self._candidate(data, lat, lon)
        return [c] if c and c.distance_m <= radius_m else []

    def area(self, lat: float, lon: float) -> Area:
        data = self._get("/reverse", {"lat": round(lat, 3), "lon": round(lon, 3), "format": "jsonv2",
                                      "zoom": 10, "addressdetails": 1})
        if not isinstance(data, dict) or "error" in data:
            return Area(source="none")
        addr = data.get("address") or {}
        return Area(
            locality=addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality"),
            region=addr.get("state") or addr.get("region"),
            country=addr.get("country"),
            country_code=(addr.get("country_code") or "").upper() or None,
            source="nominatim",
        )

    def known_names(self) -> set[str]:
        names: set[str] = set()
        for v in self._cache.values():
            if isinstance(v, dict):
                if v.get("name"):
                    names.add(v["name"])
                for x in (v.get("address") or {}).values():
                    if isinstance(x, str):
                        names.add(x)
        return names


def build_geocoder(settings: Any = None) -> Geocoder:
    from atlas.config import get_settings

    s = settings or get_settings()
    if s.effective("geocoder") == "nominatim":
        return NominatimGeocoder(s.nominatim_url, s.nominatim_user_agent, s.data_dir / "cache" / "nominatim.json")
    return GazetteerGeocoder()
