"""Pipeline orchestration: one function that runs the six stages in order.

Each stage is a pure function with the signature fixed below (ARCHITECTURE §2). This module adds
nothing clever: it wires stages, times them, reports progress, and can dump each stage's output
to a work directory so a single stage can be re-run or inspected alone (see ``atlas.cli``).

Stage signatures (the contract every stage module implements):

    ingest.ingest_files(paths, root, *, known=None, vision=None, transcriber=None, derivatives_dir=None,
                        workers=1, progress=None) -> list[Asset]
    timefix.repair(assets, track, *, home_tz_offset_min=None) -> list[Asset]
    cluster.cluster_moments(assets, track, constraints=None) -> list[Moment]
    enrich.enrich_moments(moments, assets, track, geocoder) -> list[Moment]
    evidence.build_evidence(moments, assets, track, *, history=None) -> list[Evidence]
    diary.write_diary(moments, evidence, style, *, narrator=None, keep=None, assets=None) -> list[DiaryBlock]
    stats.compute_stats(assets, moments, track, evidence, *, history=None) -> TripStats
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.pipeline.models import (
    Asset,
    Constraints,
    DiaryBlock,
    PipelineResult,
    StyleProfile,
    TrackPoint,
    TripStats,
)

Progress = Callable[[str, float, str], None]   # (stage, fraction 0..1 of that stage, message)

STAGES = ("ingest", "timefix", "cluster", "enrich", "evidence", "diary", "stats")


@dataclass
class Providers:
    """Everything external the pipeline may call. All optional except the geocoder."""

    geocoder: Any = None
    vision: Any = None
    transcriber: Any = None
    narrator: Any = None      # None → deterministic realizer


@dataclass
class PipelineInput:
    root: Path                                   # media root; Asset.path is relative to it
    paths: Sequence[Path]                        # every media file of the trip (photos + voice)
    track: list[TrackPoint] = field(default_factory=list)
    known_assets: dict[str, Asset] = field(default_factory=dict)   # sha256 → Asset already ingested
    constraints: Constraints = field(default_factory=Constraints)
    style: StyleProfile = field(default_factory=StyleProfile)
    history: list[TripStats] = field(default_factory=list)        # the user's earlier trips
    keep_blocks: list[DiaryBlock] = field(default_factory=list)   # edited / user blocks to preserve
    home_tz_offset_min: int | None = None
    derivatives_dir: Path | None = None          # where thumbnails / view images are written
    workers: int = 1


def _noop(stage: str, frac: float, msg: str) -> None:
    return None


def run_pipeline(inp: PipelineInput, providers: Providers | None = None, *, progress: Progress | None = None,
                 workdir: Path | None = None) -> PipelineResult:
    from atlas.pipeline import cluster, enrich, evidence, ingest, stats, timefix
    from atlas.pipeline import diary as diary_pkg
    from atlas.providers.geocoder import build_geocoder

    providers = providers or Providers()
    geocoder = providers.geocoder or build_geocoder()
    report = progress or _noop
    timings: dict[str, float] = {}

    def timed(name: str, fn: Callable[[], Any]) -> Any:
        report(name, 0.0, "")
        t0 = time.perf_counter()
        out = fn()
        timings[name] = round(time.perf_counter() - t0, 3)
        report(name, 1.0, "")
        if workdir is not None:
            _dump(workdir, name, out)
        return out

    assets = timed("ingest", lambda: ingest.ingest_files(
        list(inp.paths), inp.root, known=inp.known_assets, vision=providers.vision,
        transcriber=providers.transcriber, derivatives_dir=inp.derivatives_dir, workers=inp.workers,
        progress=lambda f, m="": report("ingest", f, m)))
    assets = timed("timefix", lambda: timefix.repair(assets, inp.track, home_tz_offset_min=inp.home_tz_offset_min))
    moments = timed("cluster", lambda: cluster.cluster_moments(assets, inp.track, inp.constraints))
    moments = timed("enrich", lambda: enrich.enrich_moments(moments, assets, inp.track, geocoder))
    ev = timed("evidence", lambda: evidence.build_evidence(moments, assets, inp.track, history=inp.history))
    blocks = timed("diary", lambda: diary_pkg.write_diary(
        moments, ev, inp.style, narrator=providers.narrator, keep=inp.keep_blocks, assets=assets))
    st = timed("stats", lambda: stats.compute_stats(assets, moments, inp.track, ev, history=inp.history))
    return PipelineResult(assets=assets, track=inp.track, moments=moments, evidence=ev, diary=blocks,
                          stats=st, timings_s=timings)


def _dump(workdir: Path, name: str, out: Any) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    if isinstance(out, list):
        data: Any = [o.model_dump(mode="json") for o in out]
    else:
        data = out.model_dump(mode="json")
    (workdir / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
