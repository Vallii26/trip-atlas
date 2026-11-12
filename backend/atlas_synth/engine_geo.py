"""True whereabouts of the traveller: dwell at POIs, declared moving moments, implicit legs."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from .spec import Mo, TripBuilder
from .util import Path3, densify, haversine_m, offset_m, rng_of

SPEED = {"walk": 1.25, "hike": 0.9, "car": 7.0, "bus": 6.0, "tram": 4.0, "train": 9.0, "boat": 5.0, "bike": 4.0,
         "flight": 200.0, "unknown": 5.0}
DENSIFY = {"walk": (60, 8, 0), "hike": (80, 22, 5), "train": (2500, 120, 0), "boat": (300, 30, 0),
           "tram": (150, 6, 0), "bus": (200, 10, 0), "car": (200, 10, 0), "bike": (100, 8, 0),
           "flight": (20000, 0, 0), "unknown": (200, 10, 0)}
RADIUS = {"market": 35, "sight": 28, "park": 45, "museum": 22, "viewpoint": 12, "station": 28, "beach": 40,
          "swim": 25, "summit": 12, "wildlife": 15, "worship": 18, "shop": 8}


@dataclass
class Seg:
    t0: float
    t1: float
    kind: str                # dwell | move
    mode: str | None
    indoor: bool
    path: Path3 | None = None
    anchor: tuple | None = None
    radius: float = 6.0
    phase: tuple = (0.0, 0.0, 0.0, 0.0)
    moment: str | None = None

    def at(self, t: float) -> tuple[float, float, float]:
        if self.kind == "move":
            f = 0.0 if self.t1 <= self.t0 else (t - self.t0) / (self.t1 - self.t0)
            return self.path.at(f)
        lat, lon, ele = self.anchor
        a, b, c, d = self.phase
        r = self.radius
        n = r * (0.6 * math.sin(t / 97.0 + a) + 0.4 * math.sin(t / 31.0 + b))
        e = r * (0.6 * math.sin(t / 113.0 + c) + 0.4 * math.sin(t / 37.0 + d))
        la, lo = offset_m(lat, lon, n, e)
        return la, lo, ele


class Geo:
    def __init__(self, trip: TripBuilder):
        self.trip = trip
        self.segs: list[Seg] = []
        self.mgeo: dict[str, dict] = {}
        self.leg_km: dict[str, float] = {}
        self.leg_ascent = 0.0
        self._build()
        self._t0s = [s.t0 for s in self.segs]

    # -- helpers -------------------------------------------------------------------------
    def poi_xyz(self, pid: str) -> tuple[float, float, float]:
        p = self.trip.gaz[pid]
        ele = p.get("ele")
        if ele is None:
            ele = self.trip.ele_default.get(p["locality"], 0.0)
        return (p["lat"], p["lon"], float(ele))

    def _xyz(self, v) -> tuple[float, float, float]:
        if isinstance(v, str):
            return self.poi_xyz(v)
        return (v[0], v[1], float(v[2]) if len(v) > 2 else 0.0)

    def _mo_start_xyz(self, mo: Mo):
        return self._xyz(mo.place_xy) if mo.place_xy else self.poi_xyz(mo.poi)

    def _build(self):
        trip = self.trip
        R = rng_of(trip.seed, "geo")
        anchors: list[dict] = []
        stays = {s.after: s for s in trip.stays}
        for mo in trip.moments:
            a = self._mo_start_xyz(mo)
            indoor = mo.indoor if mo.indoor is not None else ("indoor" in __import__("atlas_synth.scenes", fromlist=["SCENES"]).SCENES[mo.scene])
            if mo.to or mo.via:
                pts = [a] + [self._xyz(v) for v in mo.via] + ([self.poi_xyz(mo.to)] if mo.to else [a])
                mode = mo.transport or "walk"
                if mode == "train":  # interpolate elevations missing on via points given as (lat, lon)
                    pts = [(p[0], p[1], p[2]) for p in pts]
                step, wig, bump = DENSIFY[mode]
                path = Path3(densify(pts, step, wig, bump, rng_of(trip.seed, "path", mo.id)))
                seg = Seg(mo.start, mo.end, "move", mode, indoor, path=path, moment=mo.id)
                end = path.at(1.0)
                dist, asc = path.length, (path.ascent() if mode in ("walk", "hike") else 0.0)
            else:
                r = mo.r if mo.r is not None else RADIUS.get(mo.kind, 6.0)
                seg = Seg(mo.start, mo.end, "dwell", None, indoor, anchor=a, radius=r,
                          phase=tuple(R.uniform(0, 6.283, 4)), moment=mo.id)
                end, dist, asc = a, 0.0, 0.0
            self.mgeo[mo.id] = {"seg": seg, "start": a, "end": end, "dist": dist, "ascent": asc, "indoor": indoor}
            anchors.append({"seg": seg, "start": a, "end": end, "go": mo.go, "id": mo.id})
            if mo.id in stays:
                anchors.append({"stay": stays[mo.id].poi, "id": f"stay-after-{mo.id}"})
        # resolve stays (hidden dwell between two moments)
        for i, an in enumerate(anchors):
            if "stay" not in an:
                continue
            prev, nxt = anchors[i - 1], anchors[i + 1] if i + 1 < len(anchors) else None
            a = self.poi_xyz(an["stay"])
            d1 = self._leg_time(prev["end"], a, None)[1]
            t0 = prev["seg"].t1 + d1 + 90
            t1 = (nxt["seg"].t0 - self._leg_time(a, nxt["start"], nxt.get("go"))[1] - 90) if nxt else t0 + 600
            if t1 < t0 + 60:
                raise ValueError(f"no time to stay at {an['stay']} after {prev['id']}")
            an.update(seg=Seg(t0, t1, "dwell", None, True, anchor=a, radius=4.0, phase=tuple(R.uniform(0, 6.283, 4))),
                      start=a, end=a, go=None)
        # implicit legs
        out: list[Seg] = []
        for i, an in enumerate(anchors):
            if i > 0:
                prev = anchors[i - 1]
                mode, dur, d = self._leg_time(prev["end"], an["start"], an.get("go"))
                avail = an["seg"].t0 - prev["seg"].t1
                if d >= 25:
                    if dur > avail - 20:
                        raise ValueError(f"leg {prev['id']} -> {an['id']}: {d:.0f} m by {mode} needs {dur / 60:.1f} min, "
                                         f"only {avail / 60:.1f} available")
                    t1 = an["seg"].t0 - min(45.0, (avail - dur) / 2)
                    t0 = t1 - dur
                    mid = self._dogleg(prev["end"], an["start"], rng_of(trip.seed, "leg", an["id"]))
                    step, wig, bump = DENSIFY[mode]
                    path = Path3(densify([prev["end"], mid, an["start"]], step, wig, 0, rng_of(trip.seed, "legp", an["id"])))
                    if t0 > prev["seg"].t1:
                        out.append(Seg(prev["seg"].t1, t0, "dwell", None, False, anchor=prev["end"], radius=3.0,
                                       phase=tuple(R.uniform(0, 6.283, 4))))
                    out.append(Seg(t0, t1, "move", mode, False, path=path))
                    if t1 < an["seg"].t0:
                        out.append(Seg(t1, an["seg"].t0, "dwell", None, False, anchor=an["start"], radius=3.0,
                                       phase=tuple(R.uniform(0, 6.283, 4))))
                    self.leg_km[mode] = self.leg_km.get(mode, 0.0) + path.length / 1000
                    if mode in ("walk", "hike"):
                        self.leg_ascent += path.ascent()
                elif avail > 0:
                    out.append(Seg(prev["seg"].t1, an["seg"].t0, "dwell", None, False, anchor=prev["end"], radius=3.0,
                                   phase=tuple(R.uniform(0, 6.283, 4))))
            out.append(an["seg"])
        self.segs = out

    @staticmethod
    def _dogleg(a, b, R):
        f = R.uniform(0.35, 0.65)
        lat, lon = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        d = haversine_m(a[0], a[1], b[0], b[1])
        off = d * R.uniform(0.08, 0.18) * (1 if R.random() < 0.5 else -1)
        ang = math.atan2(b[0] - a[0], (b[1] - a[1]) * math.cos(math.radians(a[0])))
        lat, lon = offset_m(lat, lon, off * math.cos(ang + math.pi / 2) * -1, off * math.sin(ang + math.pi / 2))
        return (lat, lon, a[2] + (b[2] - a[2]) * f)

    @staticmethod
    def _leg_time(a, b, go):
        d = haversine_m(a[0], a[1], b[0], b[1])
        mode = go or ("walk" if d < 1800 else "car")
        dur = max(40.0, d * 1.12 / SPEED[mode]) + (120.0 if mode not in ("walk", "hike") else 0.0)
        return mode, dur, d

    # -- queries -------------------------------------------------------------------------
    def seg_at(self, t: float) -> Seg:
        i = bisect.bisect_right(self._t0s, t) - 1
        return self.segs[max(0, min(i, len(self.segs) - 1))]

    def where(self, t: float) -> tuple[float, float, float]:
        s = self.seg_at(t)
        return s.at(min(max(t, s.t0), s.t1))
