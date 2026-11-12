"""Ground-truth schema (``truth.json``) for a synthetic trip. Documented in docs/SYNTHETIC_DATA.md.

Everything the pipeline is measured against lives here. ``Truth.model_validate`` checks shapes;
``check_consistency`` checks the cross-references and time/space invariants that the generator
promises (and that the tests re-assert on generated output).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from atlas.pipeline.models import MomentKind, TransportMode

MOMENT_KINDS: tuple[str, ...] = get_args(MomentKind)
TRANSPORT_MODES: tuple[str, ...] = get_args(TransportMode)

Junk = Literal["screenshot", "duplicate", "near_duplicate", "burst_extra", "corrupt"]
TzMode = Literal["auto", "manual", "stuck_home"]
Breakage = Literal[
    "no_gps",           # file carries no GPS position
    "no_gps_time",      # GPS position but no GPSDateStamp/GPSTimeStamp
    "no_offset",        # no OffsetTimeOriginal
    "clock_skew",       # written time differs from true local time by the camera's clock error
    "stuck_tz",         # camera clock still on the home time zone
    "phone_tz_lag",     # phone wrote the previous country's local time + offset (UTC still right)
    "no_exif_time",     # no EXIF time at all
    "stripped_exif",    # no EXIF at all (messaging-app copy)
    "wrong_date",       # camera clock was reset (2010-01-01)
    "heic",             # HEIC container
    "truncated", "zero_byte", "not_an_image",          # corrupt files
    "burst", "exact_copy", "resized_copy", "reencoded_copy", "screenshot",
]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Home(_M):
    lat: float
    lon: float
    tz: str                        # IANA zone name
    tz_offset_min: int             # offset of home during the trip
    locality: str
    country_code: str


class Traveller(_M):
    name: str
    voice: str


class Camera(_M):
    id: str
    make: str
    model: str
    folder: str                    # photos/<folder>/
    has_gps: bool
    writes_offset: bool
    writes_subsec: bool
    tz_mode: TzMode
    # written_local = true_utc + base + clock_error_s, where base is the true local offset
    # ("auto", "manual") or clock_base_offset_min ("stuck_home").
    clock_error_s: int | None
    clock_base_offset_min: int | None = None
    notes: str = ""


class ExifTruth(_M):
    has_exif: bool
    has_time: bool
    has_offset: bool
    has_gps: bool
    has_gps_time: bool
    written_local: str | None = None       # naive ISO, ms precision if SubSec was written
    written_offset_min: int | None = None
    written_lat: float | None = None
    written_lon: float | None = None
    written_alt: float | None = None
    written_gps_utc: str | None = None     # whole seconds
    orientation: int | None = None


class Photo(_M):
    file: str
    camera: str | None                     # None: file carries no camera identity
    format: str                            # JPEG | HEIF | PNG | WEBP | TIFF | RAW | MOV | NONE
    width: int | None
    height: int | None
    true_utc: str | None
    true_tz_offset_min: int | None
    true_lat: float | None
    true_lon: float | None
    true_ele: float | None
    moment_id: str | None
    scene: str | None
    expected_tags: list[str] = Field(default_factory=list)
    junk: Junk | None = None
    duplicate_of: str | None = None
    burst_id: str | None = None
    burst_keeper: bool = False
    expected_status: Literal["ok", "unreadable", "unsupported"] = "ok"
    exif: ExifTruth
    breakage: list[Breakage] = Field(default_factory=list)
    file_mtime_utc: str
    sha256: str | None = None              # filled in after writing
    expect: dict[str, Any] | None = None   # hostile "formats" set: what a correct ingest concludes
    note: str | None = None


class PlaceT(_M):
    poi_id: str | None
    name: str | None
    category: str | None
    locality: str | None
    region: str | None = None
    country: str | None
    country_code: str | None


class MomentT(_M):
    id: str
    day: str                               # local day of the moment's START
    start_utc: str
    end_utc: str
    tz_offset_min: int                     # at the start
    tz_offset_end_min: int                 # differs only for legs that cross a time zone
    kind: str
    kind_alt: list[str] = Field(default_factory=list)   # other kinds a fair grader accepts
    transport: str | None = None
    place: PlaceT
    to_place: PlaceT | None = None
    lat: float                             # mean true position over the moment
    lon: float
    distance_km: float
    ascent_m: float
    scene: str
    title_keywords: list[str]
    importance: int = Field(ge=1, le=5)
    cameras: list[str]
    photo_count: int                       # non-junk photos (incl. one keeper per burst)
    track_only: bool = False
    hard: bool = False
    hard_reason: str | None = None


class Fact(_M):
    id: str
    moment_id: str | None
    type: str                              # place | food | drink | transport | wildlife | note | activity | ...
    text: str
    terms: list[str]
    must_mention: bool = False
    source: Literal["itinerary", "voice"] = "itinerary"


class Forbidden(_M):
    text: str
    terms: list[str]


class DayT(_M):
    date: str
    tz_offset_min: int                     # offset where the day ended
    tz_offsets: list[int]                  # every offset the traveller was in, in order
    localities: list[str]
    countries: list[str]
    moment_ids: list[str]
    spine: list[str]
    facts: list[Fact]
    forbidden: list[Forbidden]


class VoiceNote(_M):
    file: str
    transcript_file: str
    true_utc: str
    true_tz_offset_min: int
    moment_id: str | None
    transcript: str
    duration_s: float
    file_mtime_utc: str
    filename_local: str                    # the local wall-clock time encoded in the file name


class Gap(_M):
    start_utc: str
    end_utc: str
    reason: str


class Track(_M):
    file: str | None
    points: int
    gaps: list[Gap]
    start_utc: str | None = None
    end_utc: str | None = None


class Stats(_M):
    days: int
    distance_km_total: float
    distance_km_by_mode: dict[str, float]
    ascent_m: float
    max_ele_m: float
    countries: list[str]
    localities: list[str]
    tz_offsets: list[int]
    moments: int
    moments_by_kind: dict[str, int]
    photos_total: int
    photos_real: int
    junk_counts: dict[str, int]
    breakage_counts: dict[str, int]


class FirstT(_M):
    what: str
    value: str
    moment_id: str | None = None


class Truth(_M):
    schema_: int = Field(alias="schema")
    set_kind: Literal["trip", "formats"] = "trip"
    slug: str
    title: str
    seed: int
    scale: float
    px: int
    home: Home
    traveller: Traveller
    cameras: list[Camera]
    photos: list[Photo]
    moments: list[MomentT]
    days: list[DayT]
    voice_notes: list[VoiceNote]
    track: Track
    stats: Stats
    firsts: list[FirstT]
    writing_sample: str | None = "writing_sample.txt"
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _local_day(s: str, off: int) -> str:
    d = datetime.fromtimestamp(_ts(s), tz=timezone.utc) + timedelta(minutes=off)
    return d.strftime("%Y-%m-%d")


def check_consistency(t: Truth, scenes: dict[str, list[str]] | None = None) -> list[str]:
    """Return a list of violated invariants (empty = consistent)."""
    errs: list[str] = []
    moments = {m.id: m for m in t.moments}
    if len(moments) != len(t.moments):
        errs.append("duplicate moment ids")
    cams = {c.id for c in t.cameras}
    files = set()
    by_moment: dict[str, int] = {}
    bursts: dict[str, list[Photo]] = {}
    for p in t.photos:
        if p.file in files:
            errs.append(f"duplicate file {p.file}")
        files.add(p.file)
        if p.camera is not None and p.camera not in cams:
            errs.append(f"{p.file}: unknown camera {p.camera}")
        if p.junk in ("duplicate", "near_duplicate") and not p.duplicate_of:
            errs.append(f"{p.file}: duplicate without duplicate_of")
        if p.junk in ("screenshot", "duplicate", "near_duplicate", "corrupt") and p.moment_id is not None:
            errs.append(f"{p.file}: junk must not belong to a moment")
        if p.burst_id:
            bursts.setdefault(p.burst_id, []).append(p)
        if p.moment_id is not None:
            m = moments.get(p.moment_id)
            if m is None:
                errs.append(f"{p.file}: unknown moment {p.moment_id}")
                continue
            if not (_ts(m.start_utc) <= _ts(p.true_utc) <= _ts(m.end_utc)):
                errs.append(f"{p.file}: outside its moment span")
            if p.junk is None:
                by_moment[m.id] = by_moment.get(m.id, 0) + 1
        elif p.junk is None and t.set_kind == "trip":
            errs.append(f"{p.file}: real photo without a moment")
        if scenes is not None and p.scene is not None and sorted(p.expected_tags) != sorted(scenes[p.scene]):
            errs.append(f"{p.file}: expected_tags do not match scene")
    for p in t.photos:
        if p.duplicate_of and p.duplicate_of not in files:
            errs.append(f"{p.file}: duplicate_of missing file")
    for bid, ps in bursts.items():
        if sum(1 for p in ps if p.burst_keeper) != 1:
            errs.append(f"burst {bid}: needs exactly one keeper")
        if any((p.junk != "burst_extra") != p.burst_keeper for p in ps):
            errs.append(f"burst {bid}: non-keepers must be burst_extra")
    prev_end = None
    for m in t.moments:
        if m.kind not in MOMENT_KINDS:
            errs.append(f"{m.id}: bad kind {m.kind}")
        if m.transport is not None and m.transport not in TRANSPORT_MODES:
            errs.append(f"{m.id}: bad transport {m.transport}")
        if _ts(m.end_utc) <= _ts(m.start_utc):
            errs.append(f"{m.id}: empty span")
        if prev_end is not None and _ts(m.start_utc) < prev_end:
            errs.append(f"{m.id}: overlaps previous moment")
        prev_end = _ts(m.end_utc)
        if _local_day(m.start_utc, m.tz_offset_min) != m.day:
            errs.append(f"{m.id}: day is not the local day of its start")
        n = by_moment.get(m.id, 0)
        if n != m.photo_count:
            errs.append(f"{m.id}: photo_count {m.photo_count} != {n}")
        if n == 0 and not m.track_only:
            errs.append(f"{m.id}: no photos and not track_only")
    day_dates = [d.date for d in t.days]
    if day_dates != sorted(set(day_dates)):
        errs.append("days not unique/sorted")
    seen = set()
    for d in t.days:
        for mid in d.moment_ids:
            if mid not in moments or moments[mid].day != d.date:
                errs.append(f"day {d.date}: moment {mid} not of this day")
            seen.add(mid)
        for mid in d.spine:
            if mid not in d.moment_ids:
                errs.append(f"day {d.date}: spine {mid} not in day")
        for f in d.facts:
            if f.moment_id is not None and f.moment_id not in d.moment_ids:
                errs.append(f"day {d.date}: fact {f.id} moment not in day")
    if seen != set(moments):
        errs.append("moments missing from days")
    for v in t.voice_notes:
        if v.moment_id is not None:
            m = moments.get(v.moment_id)
            if m is None or not (_ts(m.start_utc) <= _ts(v.true_utc) <= _ts(m.end_utc)):
                errs.append(f"{v.file}: voice note outside its moment")
    for g in t.track.gaps:
        if _ts(g.end_utc) <= _ts(g.start_utc):
            errs.append("empty track gap")
    return errs
