"""CLI: ``python -m atlas_synth generate --out DIR [--trip …] [--seed N]`` / ``describe DIR``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .trips import HOSTILE, MAIN, get


def generate(out: Path, trip: str = "all", seed: int | None = None, scale: float = 1.0, px: int | None = None,
             workers: int | None = None, quiet: bool = False) -> dict[str, dict]:
    """Generate one set, ``all`` (the three main trips) or ``everything``. Returns per-slug timing."""
    from .engine import execute, plan

    slugs = MAIN if trip == "all" else (MAIN + HOSTILE if trip == "everything" else [trip])
    results = {}
    prior = None
    for slug in MAIN + HOSTILE:
        if slug == "formats":
            if slug in slugs:
                from .formats import write_formats

                t0 = time.time()
                n = write_formats(out / slug, seed if seed is not None else 77)
                results[slug] = {"seconds": round(time.time() - t0, 1), "files": n}
            continue
        main = slug in MAIN
        if slug not in slugs and not (main and any(s in MAIN and MAIN.index(s) > MAIN.index(slug) for s in slugs)):
            continue
        b = get(slug, seed)
        p = px or (640 if slug == "stress5000" else (1024 if slug == "vintage" else 1600))
        pl = plan(b, scale, p, prior if main else None)
        if main:
            prior = pl["summary"]
        if slug in slugs:
            results[slug] = execute(pl, out / slug, workers)
            results[slug]["photos"] = len(pl["truth"]["photos"])
            if not quiet:
                print(f"{slug:11s} {results[slug]['photos']:5d} photos  {results[slug]['files']:5d} files  {results[slug]['seconds']:6.1f} s")
    if "formats" in results and not quiet:
        print(f"{'formats':11s} {results['formats']['files']:5d} files  {results['formats']['seconds']:6.1f} s")
    return results


def describe(path: Path) -> str:
    t = json.loads((path / "truth.json").read_text(encoding="utf-8"))
    s = t["stats"]
    o = [f"{t['title']}  [{t['slug']}, seed {t['seed']}, scale {t['scale']}, {t['px']} px]",
         f"traveller {t['traveller']['name']} — home {t['home']['locality']} ({t['home']['country_code']}, UTC{t['home']['tz_offset_min'] / 60:+g})",
         "cameras: " + "; ".join(f"{c['id']}={c['make']} {c['model']} (tz {c['tz_mode']}, clock error {c['clock_error_s']} s, "
                                 f"gps {'yes' if c['has_gps'] else 'no'})" for c in t["cameras"]),
         f"{s['days']} days · {s['moments']} moments · {s['photos_total']} files ({s['photos_real']} real photos) · "
         f"{len(t['voice_notes'])} voice notes · track {t['track']['points']} pts, {len(t['track']['gaps'])} gaps",
         f"distance {s['distance_km_total']} km " + json.dumps(s["distance_km_by_mode"]) + f" · ascent {s['ascent_m']:.0f} m · max ele {s['max_ele_m']:.0f} m",
         f"countries {' '.join(s['countries'])} · UTC offsets {s['tz_offsets']}", ""]
    moments = {m["id"]: m for m in t["moments"]}
    for d in t["days"]:
        ms = [moments[i] for i in d["moment_ids"]]
        o.append(f"{d['date']}  UTC{d['tz_offset_min'] / 60:+g}  {len(ms):2d} moments, {sum(m['photo_count'] for m in ms):3d} photos  "
                 f"{', '.join(d['localities'])}")
        for m in ms:
            star = "*" if m["id"] in d["spine"] else " "
            to = f" → {m['to_place']['name']}" if m["to_place"] else ""
            hard = "  [hard]" if m["hard"] else ""
            o.append(f"   {star} {m['start_utc'][11:16]}Z {m['kind']:9s} {m['photo_count']:3d}  {m['place']['name']}{to}{hard}")
        o.append(f"     facts {len(d['facts'])} (must {sum(f['must_mention'] for f in d['facts'])}), forbidden {len(d['forbidden'])}")
    o += ["", "junk:     " + ", ".join(f"{k}={v}" for k, v in s["junk_counts"].items()),
          "breakage: " + ", ".join(f"{k}={v}" for k, v in s["breakage_counts"].items()),
          "hard moments: %d" % sum(m["hard"] for m in t["moments"]),
          "track gaps: " + "; ".join(f"{g['start_utc'][5:16]}–{g['end_utc'][11:16]} {g['reason']}" for g in t["track"]["gaps"]),
          "firsts: " + ", ".join(f"{f['what']}={f['value']}" for f in t["firsts"])]
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="atlas_synth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate synthetic trips")
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--trip", default="all", choices=MAIN + HOSTILE + ["all", "everything"])
    g.add_argument("--seed", type=int, default=None, help="override the trip's built-in seed")
    g.add_argument("--scale", type=float, default=1.0, help="multiply photo counts per moment (tests use ~0.1)")
    g.add_argument("--px", type=int, default=None, help="long edge of photos (default 1600; stress5000 640; vintage 1024)")
    g.add_argument("--workers", type=int, default=None)
    d = sub.add_parser("describe", help="print a human summary of a generated trip")
    d.add_argument("path", type=Path)
    c = sub.add_parser("contact", help="write a contact sheet PNG of a generated trip")
    c.add_argument("path", type=Path)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--n", type=int, default=30)
    a = ap.parse_args(argv)
    if a.cmd == "generate":
        generate(a.out, a.trip, a.seed, a.scale, a.px, a.workers)
    elif a.cmd == "describe":
        print(describe(a.path))
    else:
        from .contact import trip_sheet

        trip_sheet(a.path, a.out, a.n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
