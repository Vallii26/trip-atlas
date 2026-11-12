"""Expand an itinerary into individual photo files (real shots and every deliberate breakage)."""

from __future__ import annotations

import bisect
from datetime import datetime, timezone

from .engine_geo import Geo
from .scenes import SCENES, SCREEN_H, SCREEN_W
from .spec import CameraSpec, Mo, TripBuilder
from .util import iso_utc, local_naive, offset_m, rng_of, seed_of
from .writers import round_gps

WA_FOLDER = "WhatsApp Images"
RESET_EPOCH = datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp()


class Clock:
    """True UTC offset over time, plus windows where the phone lagged behind a zone change."""

    def __init__(self, trip: TripBuilder):
        self.changes: list[tuple[float, int]] = []
        self.lags: list[tuple[float, float, int]] = []
        for mo in trip.moments:
            self._add(mo.start, mo.tz)
            if mo.tz_change:
                tc = mo.start + mo.tz_change[0] * (mo.end - mo.start)
                self._add(tc, mo.tz_end)
                if mo.lag_min:
                    self.lags.append((tc, tc + mo.lag_min * 60, mo.tz))
        self._ts = [c[0] for c in self.changes]

    def _add(self, t, off):
        if not self.changes or self.changes[-1][1] != off:
            self.changes.append((t, off))

    def tz(self, t: float) -> int:
        i = bisect.bisect_right(self._ts, t) - 1
        return self.changes[max(0, i)][1]

    def phone_tz(self, t: float) -> int:
        for a, b, off in self.lags:
            if a <= t < b:
                return off
        return self.tz(t)


def _times(R, mo: Mo, k: int, whole_s: bool, min_gap: float = 4.0) -> list[float]:
    if k <= 0:
        return []
    dur = mo.end - mo.start
    lo, hi = mo.start + min(15.0, dur * 0.05), mo.end - min(15.0, dur * 0.05)
    wins = list(mo.when or [(0.0, 1.0)])
    if mo.gap:
        g = min(0.8, mo.gap * 60 / (hi - lo))
        wins = [(0.0, 0.5 - g / 2 - 0.01), (0.5 + g / 2 + 0.01, 1.0)]
    lens = [b - a for a, b in wins]
    tot = sum(lens)
    ts = []
    for _ in range(k):
        u = R.uniform(0, tot)
        for (a, b), ln in zip(wins, lens):
            if u <= ln:
                ts.append(lo + (a + u) * (hi - lo))
                break
            u -= ln
    if mo.gap and k >= 2:  # make sure both sides of the gap have a photo
        ts[0] = lo + R.uniform(wins[0][0], wins[0][1]) * (hi - lo)
        ts[1] = lo + R.uniform(wins[1][0], wins[1][1]) * (hi - lo)
    ts.sort()
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] < min_gap:
            ts[i] = ts[i - 1] + min_gap + R.uniform(0, 2.0)
    if ts[-1] > hi:  # too dense for the span: spread evenly
        ts = [lo + (hi - lo) * (i + 0.5) / k for i in range(k)]
    return [float(int(t)) if whole_s else round(t, 3) for t in ts]


def _scene_for(R, mo: Mo, t: float) -> str:
    scene = mo.scene
    if mo.phases:
        f = (t - mo.start) / (mo.end - mo.start)
        for upto, s in mo.phases:
            if f <= upto:
                scene = s
                break
    if mo.mix:
        u = R.random()
        for s, w in mo.mix.items():
            if u < w:
                return s
            u -= w
    return scene


def expand(trip: TripBuilder, geo: Geo, clock: Clock, scale: float, px: int) -> list[dict]:
    """Return photo records (dicts) with everything needed for truth and for the render job."""
    cams = {c.id: c for c in trip.cameras}
    phone = next((c for c in trip.cameras if c.id == "phone"), trip.cameras[0])
    camera = next((c for c in trip.cameras if c.id != phone.id), None)
    short = px * 3 // 4
    photos: list[dict] = []
    S = rng_of(trip.seed, "specials")
    no_offset_moments = set()
    for mo in trip.moments:
        if mo.no_offset or rng_of(trip.seed, "nooff", mo.id).random() < trip.no_offset_share:
            no_offset_moments.add(mo.id)

    def new(cam: CameraSpec | None, t: float, mo: Mo | None, scene: str | None, **kw) -> dict:
        p = {"t": t, "cam": cam, "mo": mo, "scene": scene, "kind": "jpeg", "junk": None, "dup_of": None,
             "burst_id": None, "keeper": False, "frame": 0, "breakage": [], "w": px, "h": short,
             "folder": cam.folder if cam else None, "derived": [], "status": "ok", "wrong_date": False}
        p.update(kw)
        if mo is not None and scene is not None:
            g = geo.mgeo[mo.id]
            chunk = int((t - mo.start) / 2400) if g["seg"].kind == "move" else 0
            p["layout_seed"] = seed_of(trip.seed, "layout", mo.id, scene, chunk)
            p["look"] = mo.looks.get(scene, mo.look if scene == mo.scene else {})
        p.setdefault("view_seed", seed_of(trip.seed, "view", cam.id if cam else "-", str(t), len(photos)))
        photos.append(p)
        return p

    for mo in trip.moments:
        R = rng_of(trip.seed, "photos", mo.id)
        n = max(1, round(mo.n * scale)) if mo.n else 0
        c = round(mo.c * scale) if mo.c else 0
        if mo.c and not n:
            c = max(1, c)
        if camera is None:
            n, c = n + c, 0
        for cam, k in ((phone, n), (camera, c)):
            if not k:
                continue
            ts = _times(R, mo, k, not cam.subsec)
            recs = []
            for t in ts:
                p = new(cam, t, mo, _scene_for(R, mo, t))
                if cam is phone and R.random() < trip.portrait:
                    p["w"], p["h"] = short, px
                recs.append(p)
            bk = mo.burst if cam is phone else mo.cburst
            if bk and recs:
                i = int(R.integers(0, len(recs)))
                base = recs[i]
                bid = f"{mo.id}-burst-{cam.id}"
                step = min(0.25, 1.8 / (bk - 1)) if cam.subsec else 0.0
                base.update(burst_id=bid, keeper=True)
                base["breakage"].append("burst")
                span = step * (bk - 1) if cam.subsec else 1.0
                for later in recs[i + 1:]:  # keep ordinary shots clear of the burst
                    if later["t"] < base["t"] + span + 4:
                        later["t"] = round(min(mo.end - 1, later["t"] + span + 4), 3 if cam.subsec else 0)
                for f in range(1, bk):
                    tf = round(base["t"] + step * f, 3) if cam.subsec else base["t"] + (f * 2) // bk
                    q = new(cam, min(tf, mo.end), mo, base["scene"], burst_id=bid, junk="burst_extra", frame=f,
                            view_seed=base["view_seed"], w=base["w"], h=base["h"])
                    q["breakage"].append("burst")

    real = [p for p in photos if p["junk"] is None and not p["burst_id"]]
    phone_real = [p for p in real if p["cam"] is phone]
    cam_real = [p for p in real if camera is not None and p["cam"] is camera]

    def pick(pool: list[dict], k: int) -> list[dict]:
        pool = [p for p in pool if not p.get("used")]
        if not pool or k <= 0:
            return []
        idx = sorted(S.choice(len(pool), size=min(k, len(pool)), replace=False).tolist())
        for i in idx:
            pool[i]["used"] = True
        return [pool[i] for i in idx]

    # HEIC
    for p in pick(phone_real, trip.heic):
        p["kind"] = "heic"
        p["breakage"].append("heic")
    # wrong date (camera reset)
    if trip.wrong_date and cam_real:
        p = pick(cam_real, 1)[0]
        p["wrong_date"] = True
    # exact duplicates
    for i, p in enumerate(pick([q for q in phone_real if q["kind"] == "jpeg"], trip.exact_dups)):
        new(None, p["t"], None, p["scene"], junk="duplicate", dup_of=p, kind="copy", w=p["w"], h=p["h"],
            variant=i % 2, breakage=["exact_copy"])
    # resized / re-encoded near duplicates
    nd = pick([q for q in phone_real if q["kind"] == "jpeg"], max(0, trip.near_dups - (1 if cam_real else 0)))
    for p in nd:
        new(None, p["t"], None, p["scene"], junk="near_duplicate", dup_of=p, kind="resize", breakage=["resized_copy", "stripped_exif"],
            w=round(p["w"] * 0.64), h=round(p["h"] * 0.64))
    if cam_real and trip.near_dups:
        for p in pick(cam_real, 1):
            new(p["cam"], p["t"], None, p["scene"], junk="near_duplicate", dup_of=p, kind="reencode",
                breakage=["reencoded_copy"], w=p["w"], h=p["h"])
    # photos with no EXIF at all, saved from a messaging app
    hosts = [mo for mo in trip.moments if mo.n >= 4]
    if hosts and trip.noexif:
        for i in sorted(S.choice(len(hosts), size=min(trip.noexif, len(hosts)), replace=False).tolist()):
            mo = hosts[i]
            t = _times(S, mo, 1, False)[0]
            new(None, t, mo, _scene_for(S, mo, t), kind="noexif", breakage=["no_exif_time", "stripped_exif", "no_gps"], folder=WA_FOLDER)
    # corrupt files
    for what in trip.corrupt:
        mo = trip.moments[int(S.integers(0, len(trip.moments)))]
        t = _times(S, mo, 1, False)[0]
        if what == "truncated":
            new(phone, t, None, _scene_for(S, mo, t), kind="truncated", junk="corrupt", status="unreadable", breakage=["truncated"],
                layout_seed=seed_of(trip.seed, "layout", mo.id, "truncated", 0), look={})
        elif what == "zero":
            cam = camera or phone
            new(cam, float(int(t)), None, None, kind="zero", junk="corrupt", status="unreadable", breakage=["zero_byte"])
        elif what == "text":
            new(None, None, None, None, kind="text", junk="corrupt", status="unreadable", breakage=["not_an_image"],
                folder="Downloads")
    # screenshots
    for sh in trip.shots:
        new(phone if trip.screenshot_style == "iphone" else None, round(sh["t"], 0), None, None, kind="screenshot",
            junk="screenshot", w=SCREEN_W, h=SCREEN_H, shot=sh, breakage=["screenshot", "no_exif_time", "no_gps"],
            folder=phone.folder if trip.screenshot_style == "iphone" else "Screenshots")

    _name_and_describe(trip, geo, clock, photos, phone, no_offset_moments)
    return photos


def _name_and_describe(trip, geo: Geo, clock: Clock, photos, phone, no_offset_moments):
    end_t = trip.moments[-1].end
    # sequence numbers per device folder
    for cam in trip.cameras:
        seq = sorted((p for p in photos if p["cam"] is cam and p["kind"] in
                      ("jpeg", "heic", "truncated", "zero", "screenshot")), key=lambda p: (p["t"], p["frame"]))
        for i, p in enumerate(seq):
            if p["kind"] == "screenshot":
                ext = "PNG"
            elif p["kind"] == "heic":
                ext = "HEIC" if cam.ext.isupper() else "heic"
            else:
                ext = cam.ext
            if cam.naming == "pixel":
                d = datetime.fromtimestamp(int(p["t"]), tz=timezone.utc)
                ms = int(round((p["t"] - int(p["t"])) * 1000)) % 1000
                stem = f"{cam.prefix}{d:%Y%m%d_%H%M%S}{ms:03d}"
                if p["burst_id"]:
                    stem += f".BURST-{p['frame'] + 1:02d}"
            else:
                stem = f"{cam.prefix}{cam.start_no + i:04d}"
            p["file"] = f"photos/{cam.folder}/{stem}.{ext}"
    wa = sorted((p for p in photos if p["kind"] in ("resize", "noexif")), key=lambda p: p["t"])
    for i, p in enumerate(wa):
        d = local_naive(p["t"], clock.tz(p["t"]))
        p["file"] = f"photos/{WA_FOLDER}/IMG-{d:%Y%m%d}-WA{i + 3:04d}.jpg"
    for p in photos:
        k = p["kind"]
        if k == "copy":
            src = p["dup_of"]["file"]
            stem, ext = src.rsplit(".", 1)
            p["file"] = f"{stem} (1).{ext}" if p["variant"] == 0 else f"photos/Downloads/{src.rsplit('/', 1)[1]}"
        elif k == "reencode":
            stem, ext = p["dup_of"]["file"].rsplit(".", 1)
            p["file"] = f"{stem}-edited.{ext.lower()}"
        elif k == "text":
            p["file"] = "photos/Downloads/photo_download.jpg"
        elif k == "screenshot" and "file" not in p:
            d = local_naive(p["t"], clock.phone_tz(p["t"]))
            p["file"] = f"photos/Screenshots/Screenshot_{d:%Y%m%d-%H%M%S}.png"

    for p in photos:
        cam, t, k = p["cam"], p["t"], p["kind"]
        src = p["dup_of"]
        ex = {"has_exif": False, "has_time": False, "has_offset": False, "has_gps": False, "has_gps_time": False}
        p["exifw"] = None
        if t is not None:
            lat, lon, ele = geo.where(t)
            p["true"] = (round(lat, 6), round(lon, 6), round(ele, 1), clock.tz(t))
        else:
            p["true"] = (None, None, None, None)
        p["mtime"] = int(t) if t is not None else int(end_t) + 86400
        if k in ("copy", "reencode"):
            p["exif"] = dict(src["exif"])
            p["mtime"] = int(src["mtime"]) + (3 * 86400 if k == "copy" else 5 * 86400 + 1234)
            if k == "reencode":
                p["breakage"] += [b for b in src["breakage"] if b in ("no_gps", "no_offset", "clock_skew", "stuck_tz")]
            continue
        if k in ("resize", "noexif"):
            p["mtime"] = int(t) + int(rng_of(trip.seed, "wa", p["file"]).integers(1800, 6 * 3600))
            p["exif"] = ex
            continue
        if k in ("screenshot", "zero", "text"):
            p["exif"] = ex
            continue
        # real camera file (jpeg / heic / truncated)
        R = rng_of(trip.seed, "exif", p["file"])
        true_off = clock.tz(t)
        mo = p["mo"]
        indoor = geo.seg_at(t).indoor
        w = {"make": cam.make, "model": cam.model, "lens": cam.lens, "software": cam.software, "w": p["w"], "h": p["h"],
             "exif_version": cam.exif_version, "orientation": 1,
             "fnumber": float(R.choice([1.5, 1.8, 2.8, 4.0, 5.6, 8.0])), "focal": float(R.choice([5.7, 18.0, 23.0, 35.0, 55.0])),
             "iso": int(R.choice([50, 100, 200, 400, 800, 1600])), "exposure": int(R.choice([30, 60, 125, 250, 500, 1000, 2000]))}
        if cam.tz_mode == "auto":
            woff = clock.phone_tz(t)
            local = t + woff * 60
            if woff != true_off:
                p["breakage"].append("phone_tz_lag")
        else:
            base = true_off if cam.tz_mode == "manual" else cam.base_offset_min
            woff = None
            local = t + base * 60 + cam.clock_error_s
            p["breakage"].append("clock_skew")
            if cam.tz_mode == "stuck_home":
                p["breakage"].append("stuck_tz")
        if p["wrong_date"]:
            local = RESET_EPOCH + float(R.integers(5, 900)) + (t - int(t))
            p["breakage"].append("wrong_date")
            p["mtime"] = int(local)
        elif cam.tz_mode != "auto":
            p["mtime"] = int(t + cam.clock_error_s)
        ld = datetime.fromtimestamp(int(local), tz=timezone.utc)
        ms = int(round((local - int(local)) * 1000)) % 1000
        w["dt"] = ld.strftime("%Y:%m:%d %H:%M:%S")
        written_local = ld.strftime("%Y-%m-%dT%H:%M:%S")
        if cam.subsec:
            w["subsec"] = f"{ms:03d}"
            written_local += f".{ms:03d}"
        ex.update(has_exif=True, has_time=True, written_local=written_local, orientation=1)
        has_off = cam.writes_offset and not (mo is not None and mo.id in no_offset_moments)
        if has_off:
            w["offset"] = f"{'+' if woff >= 0 else '-'}{abs(woff) // 60:02d}:{abs(woff) % 60:02d}"
            ex.update(has_offset=True, written_offset_min=woff)
        else:
            p["breakage"].append("no_offset")
        has_gps = False
        if cam.has_gps:
            day = mo.day_decl if mo is not None else None
            p_out, p_in = trip.day_nogps.get(day, (trip.p_nogps_out, trip.p_nogps_in))
            pn = mo.nogps if (mo is not None and mo.nogps is not None) else (p_in if indoor else p_out)
            has_gps = R.random() >= pn
        if has_gps:
            sig = 16.0 if indoor else 7.0
            lat, lon = offset_m(p["true"][0], p["true"][1], float(R.normal(0, sig)), float(R.normal(0, sig)))
            lat, lon = round_gps(lat, lon)
            alt = round(max(0.0, p["true"][2] + float(R.normal(0, 6))), 2)
            g = {"lat": lat, "lon": lon, "alt": alt}
            ex.update(has_gps=True, written_lat=round(lat, 7), written_lon=round(lon, 7), written_alt=alt)
            if R.random() >= 0.03:
                u = datetime.fromtimestamp(int(t), tz=timezone.utc)
                g["date"], g["time"] = u.strftime("%Y:%m:%d"), (u.hour, u.minute, u.second)
                ex.update(has_gps_time=True, written_gps_utc=iso_utc(int(t))[:19] + "Z")
            else:
                p["breakage"].append("no_gps_time")
            w["gps"] = g
        else:
            p["breakage"].append("no_gps")
        p["exifw"], p["exif"] = w, ex
    for p in photos:
        if p["kind"] == "copy":  # same bytes → same EXIF as its source (resolved above for sources)
            p["exif"] = dict(p["dup_of"]["exif"])
            p["breakage"] += [b for b in p["dup_of"]["breakage"] if b not in p["breakage"] and b != "heic"]
        if p["kind"] == "reencode":
            p["exif"] = dict(p["dup_of"]["exif"])


def tags_for(scene: str | None) -> list[str]:
    return list(SCENES[scene]) if scene else []
