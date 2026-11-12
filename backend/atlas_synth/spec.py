"""Itinerary DSL: a trip is declared as days of moments in local wall-clock time.

The trip modules (``trips/*.py``) only *declare*; ``engine.build`` turns a declaration into
positions, photos, a track, voice notes and ``truth.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scenes import SCENES
from .truth import MOMENT_KINDS, TRANSPORT_MODES
from .util import load_gazetteer, local_ts


@dataclass
class CameraSpec:
    id: str
    make: str
    model: str
    lens: str
    folder: str
    prefix: str
    ext: str = "JPG"
    start_no: int = 1
    software: str | None = None
    has_gps: bool = False
    writes_offset: bool = False
    subsec: bool = True
    tz_mode: str = "manual"            # auto | manual | stuck_home
    clock_error_s: int = 0
    base_offset_min: int | None = None
    quality: int = 90
    exif_version: bytes = b"0232"
    naming: str = "seq"                # seq | pixel
    notes: str = ""


@dataclass
class Mo:
    id: str
    day_decl: str
    start: float
    end: float
    tz: int
    tz_end: int
    poi: str
    kind: str
    scene: str
    n: int = 0
    c: int = 0
    imp: int = 3
    kw: list[str] | None = None
    to: str | None = None
    via: list = field(default_factory=list)
    transport: str | None = None
    go: str | None = None
    mix: dict[str, float] = field(default_factory=dict)
    phases: list[tuple[float, str]] = field(default_factory=list)
    look: dict = field(default_factory=dict)
    looks: dict[str, dict] = field(default_factory=dict)
    when: list[tuple[float, float]] | None = None
    gap: float | None = None           # minutes without any photo, centred in the moment
    burst: int = 0                     # phone burst frames
    cburst: int = 0                    # camera burst frames
    indoor: bool | None = None
    r: float | None = None
    hard: str | None = None
    kind_alt: list[str] = field(default_factory=list)
    tz_change: tuple[float, int] | None = None   # (fraction of the leg, new offset)
    lag_min: float = 0.0               # phone keeps the old zone this long after tz_change
    nogps: float | None = None
    no_offset: bool = False
    facts: list[tuple] = field(default_factory=list)
    place_name: str | None = None      # for sets without gazetteer POIs
    place_xy: tuple | None = None


@dataclass
class Stay:
    poi: str
    after: str                         # moment id it follows


class TripBuilder:
    def __init__(self, slug, title, seed, home, traveller, cameras, writing_sample, *,
                 sun=(6.0, 20.5), ele_default=None, p_nogps_out=0.03, p_nogps_in=0.5,
                 no_offset_share=0.08, screenshot_style="iphone", heic=5, exact_dups=3, near_dups=4,
                 noexif=3, corrupt=("truncated", "text"), wrong_date=False, has_track=True,
                 portrait=0.25, notes=None):
        self.slug, self.title, self.seed = slug, title, seed
        self.home, self.traveller, self.cameras = home, traveller, cameras
        self.writing_sample = writing_sample
        self.sun, self.ele_default = sun, ele_default or {}
        self.p_nogps_out, self.p_nogps_in, self.no_offset_share = p_nogps_out, p_nogps_in, no_offset_share
        self.screenshot_style, self.heic, self.exact_dups, self.near_dups = screenshot_style, heic, exact_dups, near_dups
        self.noexif, self.corrupt, self.wrong_date, self.has_track = noexif, tuple(corrupt), wrong_date, has_track
        self.portrait = portrait
        self.notes = notes or []
        self.moments: list[Mo] = []
        self.stays: list[Stay] = []
        self.voices: list[dict] = []
        self.shots: list[dict] = []
        self.gaps: list[tuple[float, float, str]] = []
        self.notrack_days: dict[str, str] = {}
        self.forbidden: dict[str, list[tuple[str, list[str]]]] = {}
        self.day_nogps: dict[str, tuple[float, float]] = {}
        self.day_sun: dict[str, tuple[float, float]] = {}
        self.cur_day: str | None = None
        self.cur_tz: int | None = None
        self._n_in_day = 0
        self._day_no = 0
        self.gaz = load_gazetteer()

    # -- declaration ---------------------------------------------------------------------
    def day(self, date: str, tz: int | None = None, nogps: tuple[float, float] | None = None, sun=None):
        self.cur_day = date
        if tz is not None:
            self.cur_tz = tz
        self._day_no += 1
        self._n_in_day = 0
        if nogps:
            self.day_nogps[date] = nogps
        if sun:
            self.day_sun[date] = sun
        self.forbidden.setdefault(date, [])

    def ts(self, hhmm: str) -> float:
        return local_ts(self.cur_day, hhmm, self.cur_tz)

    def m(self, start: str, dur: float, poi: str, kind: str, scene: str, n: int = 0, c: int = 0,
          imp: int = 3, kw=None, **kw_) -> Mo:
        assert kind in MOMENT_KINDS, kind
        assert scene in SCENES, scene
        if poi not in self.gaz and not kw_.get("place_xy"):
            raise KeyError(f"unknown POI {poi}")
        self._n_in_day += 1
        t0 = self.ts(start)
        mo = Mo(id=f"{self.slug}-d{self._day_no:02d}-{self._n_in_day:02d}", day_decl=self.cur_day, start=t0,
                end=t0 + dur * 60, tz=self.cur_tz, tz_end=self.cur_tz, poi=poi, kind=kind, scene=scene,
                n=n, c=c, imp=imp, kw=kw, **kw_)
        for s in list(mo.mix) + [s for _, s in mo.phases]:
            assert s in SCENES, s
        if mo.to and mo.to not in self.gaz:
            raise KeyError(f"unknown POI {mo.to}")
        if mo.transport is None and (mo.to or mo.via):
            mo.transport = {"hike": "hike", "walk": "walk"}.get(kind)
        assert mo.transport is None or mo.transport in TRANSPORT_MODES
        if mo.tz_change:
            mo.tz_end = mo.tz_change[1]
            self.cur_tz = mo.tz_end
        if self.moments and mo.start < self.moments[-1].end + 60:
            raise ValueError(f"{mo.id} starts before {self.moments[-1].id} ended (+1 min)")
        self.moments.append(mo)
        return mo

    def stay(self, poi: str):
        """Traveller spends the time until the next moment at ``poi`` (not a moment)."""
        assert poi in self.gaz, poi
        self.stays.append(Stay(poi, self.moments[-1].id))

    def fact(self, type_: str, text: str, terms: list[str], must: bool = False):
        self.moments[-1].facts.append((type_, text, terms, must))

    def voice(self, hhmm: str, text: str, terms: list[str], fact: str | None = None, must: bool = False):
        mo = self.moments[-1]
        t = self.ts(hhmm) if mo.tz_change is None else None
        if t is None:  # inside a zone-crossing leg: hhmm is given in the zone valid at that instant
            t_new = local_ts(self.cur_day, hhmm, mo.tz_end)
            t_old = local_ts(self.cur_day, hhmm, mo.tz)
            change = mo.start + mo.tz_change[0] * (mo.end - mo.start)
            t = t_new if t_new >= change else t_old
        while t < mo.start:          # legs that run past midnight: time belongs to the next day
            t += 86400
        assert mo.start <= t <= mo.end, f"voice note {hhmm} outside {mo.id}"
        self.voices.append({"t": t, "text": text, "terms": terms, "fact": fact or text, "must": must, "moment": mo.id})

    def shot(self, hhmm: str, kind: str, lines: list[str] | None = None):
        self.shots.append({"t": self.ts(hhmm), "kind": kind, "lines": lines or []})

    def forbid(self, text: str, terms: list[str]):
        self.forbidden[self.cur_day].append((text, terms))

    def gap(self, h1: str, h2: str, reason: str):
        self.gaps.append((self.ts(h1), self.ts(h2), reason))

    def notrack(self, reason: str):
        self.notrack_days[self.cur_day] = reason
