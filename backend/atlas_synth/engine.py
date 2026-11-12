"""Turn a declared trip into files on disk plus ``truth.json``."""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import shutil
import time
from pathlib import Path

from . import SCHEMA_VERSION
from .engine_geo import Geo
from .engine_photos import Clock, expand, tags_for
from .scenes import SCENES
from .spec import Mo, TripBuilder
from .truth import Truth, check_consistency
from .util import iso_utc, local_naive, offset_m, rng_of, seed_of
from .writers import gpx_bytes, put, run_job, wav_bytes

FMT = {"jpeg": "JPEG", "heic": "HEIF", "copy": "JPEG", "resize": "JPEG", "reencode": "JPEG", "noexif": "JPEG",
       "truncated": "JPEG", "zero": "NONE", "text": "NONE", "screenshot": "PNG"}
STOP = {"de", "do", "da", "dos", "das", "di", "del", "the", "of", "la", "le", "du", "des", "am", "an", "der", "a", "e", "lui", "cu"}


def _place(trip: TripBuilder, pid: str | None, mo: Mo | None = None) -> dict:
    if mo is not None and mo.place_xy:
        loc, cc, country = mo.place_xy[3], mo.place_xy[4], mo.place_xy[5]
        return {"poi_id": None, "name": mo.place_name, "category": None, "locality": loc, "region": None,
                "country": country, "country_code": cc}
    p = trip.gaz[pid]
    return {"poi_id": p["id"], "name": p["name"], "category": p["category"], "locality": p["locality"],
            "region": p["region"], "country": p["country"], "country_code": p["country_code"]}


def _keywords(name: str) -> list[str]:
    ws = [w.strip("()',.") for w in name.replace("-", " ").split()]
    ws = [w for w in ws if len(w) > 2 and w.lower() not in STOP]
    return ws or [name]


def _track(trip: TripBuilder, geo: Geo):
    if not trip.has_track:
        return [], []
    by_day: dict[str, list[Mo]] = {}
    for mo in trip.moments:
        by_day.setdefault(mo.day_decl, []).append(mo)
    wins, cuts = [], [(a, b, r) for a, b, r in trip.gaps]
    for day, ms in by_day.items():
        w = (ms[0].start - 360, ms[-1].end + 180)
        if day in trip.notrack_days:
            cuts.append((w[0] - 1, w[1] + 1, trip.notrack_days[day]))
        wins.append(w)
    wins.sort()
    merged = [list(wins[0])]
    for a, b in wins[1:]:
        if a <= merged[-1][1] + 300:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for ca, cb, _ in cuts:
        nxt = []
        for a, b in merged:
            if cb <= a or ca >= b:
                nxt.append([a, b])
                continue
            if ca - a > 120:
                nxt.append([a, ca])
            if b - cb > 120:
                nxt.append([cb, b])
        merged = nxt
    R = rng_of(trip.seed, "track")
    segments = []
    for a, b in merged:
        pts, t = [], float(int(a))
        while t < b:
            s = geo.seg_at(t)
            lat, lon, ele = geo.where(t)
            moving = s.kind == "move"
            sig = R.uniform(5, 9) if moving else (R.uniform(9, 15) if s.indoor else R.uniform(5, 10))
            dn, de = R.normal(0, sig), R.normal(0, sig)
            if R.random() < 0.004:
                ang, d = R.uniform(0, 6.283), R.uniform(50, 100)
                dn, de = d * math.cos(ang), d * math.sin(ang)
            lat, lon = offset_m(lat, lon, float(dn), float(de))
            pts.append((t, lat, lon, ele + float(R.normal(0, 4))))
            t += float(int(R.integers(5, 11) if moving else R.integers(15, 31)))
        if pts:
            segments.append(pts)
    gaps = []
    for s0, s1 in zip(segments, segments[1:]):
        g0, g1 = s0[-1][0], s1[0][0]
        mid = (g0 + g1) / 2
        reason = next((r for ca, cb, r in cuts if ca <= mid <= cb), "not recording (overnight)")
        gaps.append({"start_utc": iso_utc(g0), "end_utc": iso_utc(g1), "reason": reason})
    return segments, gaps


def plan(trip: TripBuilder, scale: float = 1.0, px: int = 1600, prior: dict | None = None) -> dict:
    """Everything that will be written, as plain data: truth dict (without hashes), jobs, aux files."""
    geo = Geo(trip)
    clock = Clock(trip)
    photos = expand(trip, geo, clock, scale, px)
    sun_default = trip.sun

    # -- moments -------------------------------------------------------------------------
    per_moment: dict[str, list[dict]] = {}
    for p in photos:
        if p["mo"] is not None and p["junk"] is None:
            per_moment.setdefault(p["mo"].id, []).append(p)
    moments, mo_day = [], {}
    for mo in trip.moments:
        g = geo.mgeo[mo.id]
        day = local_naive(mo.start, mo.tz).strftime("%Y-%m-%d")
        assert day == mo.day_decl, f"{mo.id} does not start on its declared day"
        mo_day[mo.id] = day
        # daylight sanity: outdoor day scenes must not be used well after dark
        sr, ss = trip.day_sun.get(day, sun_default)
        for p in per_moment.get(mo.id, []):
            tags = SCENES[p["scene"]]
            h = local_naive(p["t"], p["true"][3])
            hr = h.hour + h.minute / 60
            dark = hr > ss + 0.75 or hr < sr - 0.75
            if "outdoor" in tags and not ({"night", "sunset", "sunrise"} & set(tags)) and dark:
                raise ValueError(f"{mo.id}: daylight scene {p['scene']} at {h:%H:%M}")
            if "night" in tags and "outdoor" in tags and not (hr > ss + 0.3 or hr < sr - 0.3):
                raise ValueError(f"{mo.id}: night scene {p['scene']} at {h:%H:%M}")
        samples = [g["seg"].at(mo.start + (mo.end - mo.start) * i / 20) for i in range(21)]
        ps = per_moment.get(mo.id, [])
        place = _place(trip, mo.poi, mo)
        to_place = _place(trip, mo.to) if mo.to and mo.to != mo.poi else None
        kw = mo.kw or (_keywords(place["name"] or place["locality"]) + (_keywords(to_place["name"]) + [to_place["locality"]] if to_place else []))
        moments.append({
            "id": mo.id, "day": day, "start_utc": iso_utc(mo.start), "end_utc": iso_utc(mo.end),
            "tz_offset_min": mo.tz, "tz_offset_end_min": mo.tz_end, "kind": mo.kind, "kind_alt": mo.kind_alt,
            "transport": mo.transport, "place": place, "to_place": to_place,
            "lat": round(sum(s[0] for s in samples) / 21, 6), "lon": round(sum(s[1] for s in samples) / 21, 6),
            "distance_km": round(g["dist"] / 1000, 3), "ascent_m": round(g["ascent"], 0), "scene": mo.scene,
            "title_keywords": kw, "importance": mo.imp,
            "cameras": sorted({p["cam"].id for p in ps if p["cam"] is not None}),
            "photo_count": len(ps), "track_only": not ps, "hard": bool(mo.hard), "hard_reason": mo.hard,
        })
        g["samples"] = samples

    # -- photos --------------------------------------------------------------------------
    order = sorted(range(len(photos)), key=lambda i: (photos[i]["t"] if photos[i]["t"] is not None else 9e18, photos[i]["file"]))
    tphotos, jobs = [], []
    for i in order:
        p = photos[i]
        lat, lon, ele, off = p["true"]
        tphotos.append({
            "file": p["file"], "camera": p["cam"].id if p["cam"] is not None else None, "format": FMT[p["kind"]],
            "width": p["w"] if p["kind"] not in ("zero", "text") else None,
            "height": p["h"] if p["kind"] not in ("zero", "text") else None,
            "true_utc": iso_utc(p["t"]) if p["t"] is not None else None, "true_tz_offset_min": off,
            "true_lat": lat, "true_lon": lon, "true_ele": ele,
            "moment_id": p["mo"].id if (p["mo"] is not None and p["junk"] in (None, "burst_extra")) else None,
            "scene": p["scene"], "expected_tags": tags_for(p["scene"]), "junk": p["junk"],
            "duplicate_of": p["dup_of"]["file"] if p["dup_of"] else None, "burst_id": p["burst_id"],
            "burst_keeper": p["keeper"], "expected_status": p["status"], "exif": p["exif"],
            "breakage": sorted(set(p["breakage"])), "file_mtime_utc": iso_utc(p["mtime"]),
        })
        k = p["kind"]
        if k in ("copy", "resize", "reencode"):
            p["dup_of"]["derived"].append({"type": k, "file": p["file"], "mtime": p["mtime"], "px": max(p["w"], p["h"])})
            continue
        job = {"kind": k, "file": p["file"], "mtime": p["mtime"], "view_seed": p["view_seed"]}
        if k == "screenshot":
            lt = local_naive(p["t"], clock.phone_tz(p["t"]))
            job.update(shot_kind=p["shot"]["kind"], lines=p["shot"]["lines"], clock=f"{lt:%H:%M}")
        elif k == "text":
            job["text"] = "<!DOCTYPE html>\n<html><head><title>403 Forbidden</title></head>\n<body><h1>Forbidden</h1>" \
                          "<p>The link to this photo has expired.</p></body></html>\n"
        elif k != "zero":
            job.update(scene=p["scene"], look=p["look"], layout_seed=p["layout_seed"], w=p["w"], h=p["h"],
                       frame=p["frame"], exifw=p["exifw"], quality=p["cam"].quality if p["cam"] else 80,
                       derived=p["derived"])
        jobs.append(job)

    # -- track ---------------------------------------------------------------------------
    segments, gaps = _track(trip, geo)
    aux = []
    t_aux = int(trip.moments[0].start)
    npts = sum(len(s) for s in segments)
    if segments:
        aux.append(("track.gpx", gpx_bytes(trip.title, segments), t_aux))
    track = {"file": "track.gpx" if segments else None, "points": npts, "gaps": gaps,
             "start_utc": iso_utc(segments[0][0][0]) if segments else None,
             "end_utc": iso_utc(segments[-1][-1][0]) if segments else None}

    # -- voice ---------------------------------------------------------------------------
    voice = []
    for v in trip.voices:
        t = float(int(v["t"]))
        lt = local_naive(t, clock.phone_tz(t))
        name = f"Recording {lt:%Y-%m-%d %H.%M.%S}"
        dur = round(min(20.0, max(5.0, len(v["text"].split()) / 2.6)), 1)
        aux.append((f"voice/{name}.wav", ("wav", seed_of(trip.seed, "voice", name), dur), int(t)))
        aux.append((f"voice/{name}.transcript.txt", (v["text"] + "\n").encode(), int(t)))
        voice.append({"file": f"voice/{name}.wav", "transcript_file": f"voice/{name}.transcript.txt",
                      "true_utc": iso_utc(t), "true_tz_offset_min": clock.tz(t), "moment_id": v["moment"],
                      "transcript": v["text"], "duration_s": dur, "file_mtime_utc": iso_utc(int(t)),
                      "filename_local": lt.strftime("%Y-%m-%dT%H:%M:%S")})
    aux.append(("writing_sample.txt", (trip.writing_sample.strip() + "\n").encode(), t_aux))

    # -- days ----------------------------------------------------------------------------
    days = []
    mos = {mo.id: mo for mo in trip.moments}
    for day in sorted(set(mo_day.values())):
        ms = [m for m in moments if m["day"] == day]
        top = max(m["importance"] for m in ms)
        spine = [m["id"] for m in ms if m["importance"] == top][:3] if top >= 4 else [max(ms, key=lambda m: m["importance"])["id"]]
        facts = []

        def add(mid, type_, text, terms, must, source="itinerary"):
            facts.append({"id": f"f-{day}-{len(facts) + 1:02d}", "moment_id": mid, "type": type_, "text": text,
                          "terms": terms, "must_mention": bool(must), "source": source})
        locs, ccs, offs = [], [], []
        for m in ms:
            mo = mos[m["id"]]
            for pl in (m["place"], m["to_place"]):
                if pl and pl["locality"] not in locs:
                    locs.append(pl["locality"])
                if pl and pl["country_code"] not in ccs:
                    ccs.append(pl["country_code"])
            for o in (m["tz_offset_min"], m["tz_offset_end_min"]):
                if not offs or offs[-1] != o:
                    offs.append(o)
            if m["kind"] == "transit" and m["to_place"]:
                add(m["id"], "transport", f"Took the {m['transport']} from {m['place']['locality']} "
                    f"({m['place']['name']}) to {m['to_place']['locality']} ({m['to_place']['name']}).",
                    [m["to_place"]["locality"], m["transport"]], m["id"] in spine)
            elif not mo.facts and m["importance"] >= 4 and m["place"]["name"]:
                add(m["id"], "place", f"Was at {m['place']['name']} ({m['kind']}).", m["title_keywords"], m["id"] in spine)
            for ty, text, terms, must in mo.facts:
                add(m["id"], ty, text, terms, must)
        for v in trip.voices:
            if mo_day[v["moment"]] == day:
                add(v["moment"], "note", v["fact"], v["terms"], v["must"], "voice")
        forb = [{"text": t, "terms": terms} for t, terms in trip.forbidden.get(day, [])]
        hay = " ".join([f["text"] + " " + " ".join(f["terms"]) for f in facts] + [v["text"] for v in trip.voices if mo_day[v["moment"]] == day]
                       + [str(m["place"]["name"]) + " " + str(m["to_place"]["name"] if m["to_place"] else "") for m in ms] + locs).lower()
        for f in forb:
            for term in f["terms"]:
                if term.lower() in hay:
                    raise ValueError(f"{trip.slug} {day}: forbidden term {term!r} also appears in the day's truth")
        days.append({"date": day, "tz_offset_min": offs[-1], "tz_offsets": offs, "localities": locs, "countries": ccs,
                     "moment_ids": [m["id"] for m in ms], "spine": spine, "facts": facts, "forbidden": forb})

    # -- stats / firsts ------------------------------------------------------------------
    by_mode = dict(geo.leg_km)
    ascent = geo.leg_ascent
    max_ele = max([p["true"][2] for p in photos if p["true"][2] is not None] or [0.0])
    for mo in trip.moments:
        g = geo.mgeo[mo.id]
        if mo.transport:
            by_mode[mo.transport] = by_mode.get(mo.transport, 0.0) + g["dist"] / 1000
        ascent += g["ascent"]
        max_ele = max(max_ele, max(s[2] for s in g["samples"]))
    junk_counts, brk = {}, {}
    for tp in tphotos:
        if tp["junk"]:
            junk_counts[tp["junk"]] = junk_counts.get(tp["junk"], 0) + 1
        for b in tp["breakage"]:
            brk[b] = brk.get(b, 0) + 1
    countries, localities, kinds = [], [], {}
    for d in days:
        countries += [c for c in d["countries"] if c not in countries]
        localities += [x for x in d["localities"] if x not in localities]
    for m in moments:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    tzs = []
    for d in days:
        tzs += [o for o in d["tz_offsets"] if o not in tzs]
    stats = {"days": len(days), "distance_km_total": round(sum(by_mode.values()), 2),
             "distance_km_by_mode": {k: round(v, 2) for k, v in sorted(by_mode.items())},
             "ascent_m": round(ascent, 0), "max_ele_m": round(max_ele, 0), "countries": countries,
             "localities": localities, "tz_offsets": tzs, "moments": len(moments), "moments_by_kind": dict(sorted(kinds.items())),
             "photos_total": len(tphotos), "photos_real": sum(1 for tp in tphotos if tp["junk"] is None),
             "junk_counts": dict(sorted(junk_counts.items())), "breakage_counts": dict(sorted(brk.items()))}
    prior = prior or {"countries": set(), "kinds": set(), "max_ele": 0.0, "night_train": False, "transports": set()}
    firsts = []
    home_cc = trip.home["country_code"]
    seen_c, seen_k, seen_t = set(prior["countries"]), set(prior["kinds"]), set(prior["transports"])
    night = prior["night_train"]
    for m in moments:
        for pl in (m["place"], m["to_place"]):
            cc = pl["country_code"] if pl else None
            if cc and cc != home_cc and cc not in seen_c:
                seen_c.add(cc)
                firsts.append({"what": "country", "value": cc, "moment_id": m["id"]})
        if m["kind"] not in seen_k and m["kind"] != "unknown":
            seen_k.add(m["kind"])
            firsts.append({"what": "kind", "value": m["kind"], "moment_id": m["id"]})
        if m["transport"] and m["transport"] not in seen_t:
            seen_t.add(m["transport"])
            firsts.append({"what": "transport", "value": m["transport"], "moment_id": m["id"]})
        if (m["kind"] == "transit" and m["transport"] == "train" and not night
                and local_naive(mos[m["id"]].end, m["tz_offset_end_min"]).date() != local_naive(mos[m["id"]].start, m["tz_offset_min"]).date()):
            night = True
            firsts.append({"what": "night_train", "value": f"{m['place']['locality']} → {m['to_place']['locality']}", "moment_id": m["id"]})
    if max_ele > prior["max_ele"] + 1 and max_ele > 1000:
        firsts.append({"what": "altitude", "value": str(int(round(max_ele))), "moment_id": None})
    summary = {"countries": seen_c, "kinds": seen_k, "max_ele": max(prior["max_ele"], max_ele), "night_train": night,
               "transports": seen_t}

    truth = {
        "schema": SCHEMA_VERSION, "set_kind": "trip", "slug": trip.slug, "title": trip.title, "seed": trip.seed,
        "scale": scale, "px": px, "home": trip.home, "traveller": trip.traveller,
        "cameras": [{"id": c.id, "make": c.make, "model": c.model, "folder": c.folder, "has_gps": c.has_gps,
                     "writes_offset": c.writes_offset, "writes_subsec": c.subsec, "tz_mode": c.tz_mode,
                     "clock_error_s": c.clock_error_s, "clock_base_offset_min": c.base_offset_min, "notes": c.notes}
                    for c in trip.cameras],
        "photos": tphotos, "moments": moments, "days": days, "voice_notes": voice, "track": track, "stats": stats,
        "firsts": firsts, "writing_sample": "writing_sample.txt", "notes": trip.notes,
    }
    return {"truth": truth, "jobs": jobs, "aux": aux, "summary": summary}


def write_truth(out: Path, truth: dict, mtime: float) -> Truth:
    model = Truth.model_validate(truth)
    errs = check_consistency(model, SCENES)
    if errs:
        raise ValueError("inconsistent truth:\n  " + "\n  ".join(errs[:30]))
    data = json.dumps(model.model_dump(by_alias=True), ensure_ascii=False, indent=1).encode() + b"\n"
    put(out, "truth.json", data, mtime)
    return model


def execute(pl: dict, out: Path, workers: int | None = None) -> dict:
    """Write every file of a plan into ``out`` (which is wiped first). Returns timing info."""
    t0 = time.time()
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    jobs = [(str(out), j) for j in pl["jobs"]]
    workers = workers or min(os.cpu_count() or 2, 8)
    hashes: dict[str, str] = {}
    if workers > 1 and len(jobs) > 8:
        with mp.get_context("fork").Pool(workers) as pool:
            for res in pool.imap_unordered(run_job, jobs, chunksize=4):
                for rel, sha, _ in res:
                    hashes[rel] = sha
    else:
        for j in jobs:
            for rel, sha, _ in run_job(j):
                hashes[rel] = sha
    for rel, data, mtime in pl["aux"]:
        if isinstance(data, tuple):
            data = wav_bytes(data[1], data[2])
        put(out, rel, data, mtime)
    truth = pl["truth"]
    for p in truth["photos"]:
        p["sha256"] = hashes[p["file"]]
    write_truth(out, truth, pl["aux"][-1][2] if pl["aux"] else 0)
    return {"seconds": round(time.time() - t0, 1), "files": len(hashes) + len(pl["aux"]) + 1}
