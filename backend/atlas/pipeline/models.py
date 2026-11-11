"""Data contracts for every pipeline stage.

These models are the interface between stages (see ARCHITECTURE.md §2). Stages are pure
functions over them; the API layer persists them. Change a field here and you are changing a
contract — update ARCHITECTURE.md and the tests of the stages on both sides.

Conventions
- All instants are timezone-aware UTC datetimes named ``*_utc``.
- ``tz_offset_min`` is the offset of local wall-clock time from UTC, in minutes, at that instant
  and place (e.g. Lisbon in summer = 60).
- "Local day" always means the calendar day at the place where the thing happened.
- Ids are opaque strings. Asset ids derive from content hash; moment/evidence ids are stable
  hashes of their defining content so that re-running the pipeline preserves links.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]

# --------------------------------------------------------------------------------------------
# Stage 1 — assets
# --------------------------------------------------------------------------------------------

AssetKind = Literal["photo", "voice", "video"]
AssetStatus = Literal["ok", "unreadable", "unsupported"]
JunkReason = Literal["screenshot", "duplicate", "near_duplicate", "burst_extra"]

TimeSource = Literal[
    "exif_offset",      # DateTimeOriginal + OffsetTimeOriginal
    "gps_stamp",        # GPSDateStamp/GPSTimeStamp (UTC by definition)
    "gps_timezone",     # local EXIF time + timezone looked up from the photo's own position
    "camera_model",     # local EXIF time corrected by this camera's estimated clock offset
    "neighbors",        # no usable EXIF time; placed between neighbours in its sequence
    "client",           # supplied by the uploading client (e.g. phone recording start time)
    "file_mtime",       # last resort
    "none",
]
GpsSource = Literal["exif", "track", "interpolated", "client", "none"]


class Asset(BaseModel):
    id: str
    kind: AssetKind = "photo"
    path: str                                # path relative to the trip's media root
    filename: str                            # original file name (never shown on public pages)
    sha256: str
    bytes: int = 0
    status: AssetStatus = "ok"
    status_reason: str | None = None

    # as found in the file
    format: str | None = None                # "JPEG", "HEIF", "PNG", "RAW:CR2", "WAV", ...
    width: int | None = None
    height: int | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    camera_id: str | None = None             # normalised make+model(+serial); None for no-EXIF files
    exif_local: datetime | None = None       # naive wall-clock DateTimeOriginal as written
    exif_offset_min: int | None = None       # OffsetTimeOriginal if present
    exif_gps_utc: datetime | None = None     # GPS date/time stamp if present (aware, UTC)
    exif_lat: float | None = None
    exif_lon: float | None = None
    exif_alt: float | None = None
    software: str | None = None
    file_mtime_utc: datetime | None = None
    duration_s: float | None = None          # voice / video

    # stage 1a: derived from pixels
    phash: str | None = None                 # 64-bit perceptual hash, hex
    signature: list[float] | None = None     # small colour/texture vector for visual similarity
    visual_tags: list[str] = Field(default_factory=list)   # from VisionTagger, e.g. ["water","sunset"]
    visual_tag_conf: Confidence = "low"
    junk: JunkReason | None = None
    duplicate_of: str | None = None          # asset id of the kept copy
    burst_id: str | None = None

    # stage 1b: repaired
    taken_utc: datetime | None = None
    tz_offset_min: int | None = None
    time_source: TimeSource = "none"
    time_confidence: Confidence = "low"
    lat: float | None = None
    lon: float | None = None
    gps_source: GpsSource = "none"
    repair_notes: list[str] = Field(default_factory=list)   # human-readable, shown in the UI

    # voice notes
    transcript: str | None = None
    transcript_source: str | None = None     # "sidecar" | "whisper" | "client" | None

    @property
    def usable(self) -> bool:
        """A real photo that should take part in clustering."""
        return self.kind == "photo" and self.status == "ok" and self.junk is None

    @property
    def local_dt(self) -> datetime | None:
        if self.taken_utc is None or self.tz_offset_min is None:
            return None
        from datetime import timedelta

        return (self.taken_utc + timedelta(minutes=self.tz_offset_min)).replace(tzinfo=None)


class TrackPoint(BaseModel):
    t_utc: datetime
    lat: float
    lon: float
    ele: float | None = None
    accuracy_m: float | None = None
    source: Literal["gpx", "device"] = "gpx"


# --------------------------------------------------------------------------------------------
# Stage 2/3 — moments
# --------------------------------------------------------------------------------------------

MomentKind = Literal[
    "sight", "viewpoint", "museum", "market", "meal", "cafe", "bar", "walk", "hike", "summit",
    "beach", "swim", "station", "transit", "lodging", "shop", "park", "wildlife", "event",
    "worship", "unknown",
]
TransportMode = Literal["walk", "hike", "train", "bus", "car", "boat", "tram", "bike", "flight", "unknown"]


class Place(BaseModel):
    name: str | None = None                  # POI or feature name; None when only the area is known
    poi_id: str | None = None                # geocoder's id for the POI
    category: str | None = None              # geocoder category, e.g. "restaurant", "viewpoint"
    locality: str | None = None              # city / town / village
    region: str | None = None
    country: str | None = None
    country_code: str | None = None          # ISO 3166-1 alpha-2, upper case
    distance_m: float | None = None          # moment centroid → POI
    confidence: Confidence = "low"
    approximate: bool = False                # True → say "near <name>", not "at <name>"
    alternatives: list[str] = Field(default_factory=list)   # other plausible names (for the UI)


class Moment(BaseModel):
    id: str
    day: date                                # local calendar day
    start_utc: datetime
    end_utc: datetime
    tz_offset_min: int
    lat: float | None = None
    lon: float | None = None
    spread_m: float | None = None            # spatial extent of the moment
    asset_ids: list[str] = Field(default_factory=list)      # usable photos, chronological
    voice_ids: list[str] = Field(default_factory=list)
    cover_asset_id: str | None = None
    kind: MomentKind = "unknown"
    kind_confidence: Confidence = "low"
    transport: TransportMode | None = None   # for transit / hike / walk
    distance_km: float | None = None         # ground covered during the moment (track or photo path)
    ascent_m: float | None = None
    place: Place = Field(default_factory=Place)
    to_place: Place | None = None            # for transit: destination
    title: str = ""
    visual_tags: list[str] = Field(default_factory=list)    # aggregated over assets
    salience: float = 0.0
    locked: bool = False                     # user-created or user-edited; never dissolved
    hidden: bool = False


class Constraints(BaseModel):
    """User edits that survive re-processing (DECISIONS D6)."""

    pinned: dict[str, str] = Field(default_factory=dict)          # asset id → moment id
    locked_moments: dict[str, dict[str, Any]] = Field(default_factory=dict)  # moment id → locked fields
    unjunk: list[str] = Field(default_factory=list)               # asset ids the user restored
    hidden_assets: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Stage 4 — evidence
# --------------------------------------------------------------------------------------------

EvidenceType = Literal[
    "time",             # {start_local:"HH:MM", end_local:"HH:MM", part_of_day:"morning"|…}
    "place",            # {name, category, locality, country, approximate}
    "locality",         # {locality, region?, country, country_code}  (where the day/moment was)
    "duration",         # {minutes}
    "photo_count",      # {count}
    "movement",         # {mode, distance_km, from?, to?}
    "elevation",        # {ascent_m, max_ele_m?}
    "visual",           # {tags:[…]}
    "note",             # {text}                      the traveller's own words (voice note / caption)
    "transport",        # {mode, from, to, depart_local?, arrive_local?, duration_min?}
    "border",           # {from_country, to_country}
    "timezone_change",  # {from_offset_min, to_offset_min}
    "first",            # {what: "country"|"kind"|…, value, text}
    "sequence",         # {after_moment_id}            ordering fact: this moment followed that one
    "kind",             # {kind}                       what sort of moment this was
]

SourceKind = Literal["asset", "track", "voice", "geocoder", "derived", "user"]


class SourceRef(BaseModel):
    kind: SourceKind
    ref: str                                 # asset id, "track:<i0>-<i1>", geocoder poi id, evidence id…
    detail: str | None = None


class Evidence(BaseModel):
    id: str
    day: date
    moment_id: str | None = None
    type: EvidenceType
    payload: dict[str, Any]
    sources: list[SourceRef]
    confidence: Confidence = "medium"

    @staticmethod
    def make_id(day: date, moment_id: str | None, type_: str, payload: dict[str, Any]) -> str:
        blob = json.dumps([day.isoformat(), moment_id, type_, payload], sort_keys=True, default=str)
        return "ev_" + hashlib.sha1(blob.encode()).hexdigest()[:14]


# --------------------------------------------------------------------------------------------
# Stage 5 — diary
# --------------------------------------------------------------------------------------------

BlockOrigin = Literal["generated", "edited", "user"]
BlockRole = Literal["opener", "spine", "background", "note", "transit", "closer"]


class DiaryBlock(BaseModel):
    id: str
    day: date
    pos: float                               # order within the day; fractional so inserts are cheap
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    moment_ids: list[str] = Field(default_factory=list)
    role: BlockRole = "background"
    origin: BlockOrigin = "generated"
    generated_text: str | None = None        # what the pipeline wrote, kept for voice learning
    hedged: bool = False
    writer: str = "deterministic"            # "deterministic" | "llm:<prompt version>"


class StyleProfile(BaseModel):
    """How this user writes. Fitted from a sample and from their edits; stable across trips."""

    person: Literal["i", "we"] = "i"
    tense: Literal["past", "present"] = "past"
    avg_sentence_words: float = 14.0
    contractions: bool = True
    exclamations: float = 0.0                # share of sentences ending in "!"
    emoji: bool = False
    clock: Literal["24h", "12h"] = "24h"
    units: Literal["metric", "imperial"] = "metric"
    lowercase_start: bool = False
    fragments: float = 0.0                   # share of verbless/clipped sentences ("Then coffee.")
    preferred: dict[str, str] = Field(default_factory=dict)   # learned word swaps: "walked" → "wandered"
    avoid: list[str] = Field(default_factory=list)
    sample_count: int = 0                    # how much text the profile was fitted on
    version: int = 1


# --------------------------------------------------------------------------------------------
# Stage 5b — verification
# --------------------------------------------------------------------------------------------

ClaimKind = Literal[
    "place", "locality", "country", "time", "part_of_day", "duration", "distance", "elevation",
    "count", "activity", "transport", "food", "weather", "people", "feeling", "visual", "first",
    "sequence", "date",
]


class Claim(BaseModel):
    kind: ClaimKind
    text: str                                # the span in the sentence
    value: Any = None                        # normalised value (minutes, km, "HH:MM", name…)
    hedged: bool = False


class ClaimVerdict(BaseModel):
    claim: Claim
    supported: bool
    evidence_id: str | None = None
    reason: str = ""


class BlockVerdict(BaseModel):
    block_id: str
    supported: bool
    verdicts: list[ClaimVerdict] = Field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Stage 6 — stats
# --------------------------------------------------------------------------------------------


class First(BaseModel):
    what: str                                # "country", "kind", "altitude", "longest_walk", …
    value: str
    text: str                                # display text, e.g. "First time in Romania"
    day: date | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TripStats(BaseModel):
    days: int = 0
    photos_total: int = 0
    photos_kept: int = 0
    moments: int = 0
    distance_km: float = 0.0
    distance_by_mode_km: dict[str, float] = Field(default_factory=dict)
    ascent_m: float = 0.0
    max_ele_m: float | None = None
    countries: list[str] = Field(default_factory=list)       # ISO codes in order of first visit
    localities: list[str] = Field(default_factory=list)
    timezones: list[int] = Field(default_factory=list)
    moments_by_kind: dict[str, int] = Field(default_factory=dict)
    earliest_start_local: str | None = None
    latest_end_local: str | None = None
    busiest_day: date | None = None
    firsts: list[First] = Field(default_factory=list)
    layers: dict[str, list[str]] = Field(default_factory=dict)   # atlas layer → moment ids
    patterns: list[str] = Field(default_factory=list)            # evidence-backed observations


class PipelineResult(BaseModel):
    assets: list[Asset]
    track: list[TrackPoint]
    moments: list[Moment]
    evidence: list[Evidence]
    diary: list[DiaryBlock]
    stats: TripStats
    timings_s: dict[str, float] = Field(default_factory=dict)
