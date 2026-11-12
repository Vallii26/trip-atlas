"""File writers: JPEG/HEIC/PNG photos with EXIF, derived junk copies, GPX, WAV. All deterministic."""

from __future__ import annotations

import hashlib
import io
import math
import os
import wave
from fractions import Fraction
from pathlib import Path

import numpy as np
import piexif
from PIL import Image

from .scenes import render_photo, render_screenshot
from .util import rng_of


def _rat(x: float, den: int = 100) -> tuple[int, int]:
    return (int(round(abs(x) * den)), den)


def _dms(v: float):
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = (v - d - m / 60) * 3600
    return ((d, 1), (m, 1), (int(round(s * 10000)), 10000))


def dms_to_deg(dms) -> float:
    return sum(Fraction(n, d) / k for (n, d), k in zip(dms, (1, 60, 3600)))


def round_gps(lat: float, lon: float) -> tuple[float, float]:
    """The value that survives the EXIF rational encoding (what a reader gets back)."""
    f = lambda v: math.copysign(float(dms_to_deg(_dms(v))), v)  # noqa: E731
    return f(lat), f(lon)


def build_exif(e: dict) -> bytes:
    """EXIF blob from a plain dict (see engine: photo['exifw'])."""
    zeroth: dict = {}
    exif: dict = {}
    gps: dict = {}
    if e.get("make"):
        zeroth[piexif.ImageIFD.Make] = e["make"]
        zeroth[piexif.ImageIFD.Model] = e["model"]
    if e.get("software"):
        zeroth[piexif.ImageIFD.Software] = e["software"]
    zeroth[piexif.ImageIFD.Orientation] = e.get("orientation", 1)
    zeroth[piexif.ImageIFD.XResolution] = (72, 1)
    zeroth[piexif.ImageIFD.YResolution] = (72, 1)
    zeroth[piexif.ImageIFD.ResolutionUnit] = 2
    exif[piexif.ExifIFD.ExifVersion] = e.get("exif_version", b"0232")
    if e.get("dt"):
        zeroth[piexif.ImageIFD.DateTime] = e["dt"]
        exif[piexif.ExifIFD.DateTimeOriginal] = e["dt"]
        exif[piexif.ExifIFD.DateTimeDigitized] = e["dt"]
        if e.get("subsec") is not None:
            exif[piexif.ExifIFD.SubSecTimeOriginal] = e["subsec"]
        if e.get("offset"):
            exif[piexif.ExifIFD.OffsetTime] = e["offset"]
            exif[piexif.ExifIFD.OffsetTimeOriginal] = e["offset"]
            exif[piexif.ExifIFD.OffsetTimeDigitized] = e["offset"]
    if e.get("lens"):
        exif[piexif.ExifIFD.LensModel] = e["lens"]
    if e.get("w"):
        exif[piexif.ExifIFD.PixelXDimension] = e["w"]
        exif[piexif.ExifIFD.PixelYDimension] = e["h"]
    for k, tag, den in (("fnumber", piexif.ExifIFD.FNumber, 10), ("focal", piexif.ExifIFD.FocalLength, 10)):
        if e.get(k):
            exif[tag] = _rat(e[k], den)
    if e.get("iso"):
        exif[piexif.ExifIFD.ISOSpeedRatings] = e["iso"]
    if e.get("exposure"):
        exif[piexif.ExifIFD.ExposureTime] = (1, e["exposure"])
    g = e.get("gps")
    if g:
        gps[piexif.GPSIFD.GPSVersionID] = (2, 3, 0, 0)
        if g.get("lat_ref", "auto") is not None:
            gps[piexif.GPSIFD.GPSLatitudeRef] = g["lat_ref"] if g.get("lat_ref", "auto") != "auto" else ("N" if g["lat"] >= 0 else "S")
        gps[piexif.GPSIFD.GPSLatitude] = _dms(g["lat"])
        if g.get("lon_ref", "auto") is not None:
            gps[piexif.GPSIFD.GPSLongitudeRef] = g["lon_ref"] if g.get("lon_ref", "auto") != "auto" else ("E" if g["lon"] >= 0 else "W")
        gps[piexif.GPSIFD.GPSLongitude] = _dms(g["lon"])
        if g.get("alt") is not None:
            gps[piexif.GPSIFD.GPSAltitudeRef] = 0 if g["alt"] >= 0 else 1
            gps[piexif.GPSIFD.GPSAltitude] = _rat(g["alt"], 100)
        if g.get("date"):
            gps[piexif.GPSIFD.GPSDateStamp] = g["date"]
            h, m, s = g["time"]
            gps[piexif.GPSIFD.GPSTimeStamp] = ((h, 1), (m, 1), (s, 1))
    return piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps, "1st": {}, "thumbnail": None})


def jpeg_bytes(im: Image.Image, quality: int, exif: bytes | None) -> bytes:
    buf = io.BytesIO()
    kw = {"exif": exif} if exif else {}
    im.save(buf, "JPEG", quality=quality, subsampling=2, optimize=False, progressive=False, **kw)
    return buf.getvalue()


def heic_bytes(im: Image.Image, quality: int, exif: bytes | None) -> bytes:
    import pillow_heif

    pillow_heif.register_heif_opener()
    pillow_heif.options.THREADS = 1  # single-threaded encode: deterministic output
    buf = io.BytesIO()
    kw = {"exif": exif} if exif else {}
    im.save(buf, "HEIF", quality=quality, **kw)
    return buf.getvalue()


def put(root: Path, rel: str, data: bytes, mtime: float) -> tuple[str, str, int]:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    os.utime(p, (mtime, mtime))
    return rel, hashlib.sha256(data).hexdigest(), len(data)


def run_job(args) -> list[tuple[str, str, int]]:
    """Render and write one photo job plus its derived files. Runs in a worker process."""
    root, j = args
    root = Path(root)
    out = []
    kind = j["kind"]
    if kind == "screenshot":
        im = render_screenshot(j["shot_kind"], j["view_seed"], j["clock"], j["lines"])
        buf = io.BytesIO()
        im.save(buf, "PNG", compress_level=6)
        return [put(root, j["file"], buf.getvalue(), j["mtime"])]
    if kind == "zero":
        return [put(root, j["file"], b"", j["mtime"])]
    if kind == "text":
        return [put(root, j["file"], j["text"].encode(), j["mtime"])]
    im = render_photo(j["scene"], j["look"], j["layout_seed"], j["view_seed"], j["w"], j["h"], j.get("frame", 0))
    exif = build_exif(j["exifw"]) if j.get("exifw") else None
    if kind == "heic":
        data = heic_bytes(im, 82, exif)
    else:
        data = jpeg_bytes(im, j["quality"], exif)
    if kind == "truncated":
        data = data[: int(len(data) * 0.37)]
    out.append(put(root, j["file"], data, j["mtime"]))
    for d in j.get("derived", []):
        if d["type"] == "copy":
            out.append(put(root, d["file"], data, d["mtime"]))
        elif d["type"] == "resize":
            s = d["px"] / max(im.size)
            small = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
            out.append(put(root, d["file"], jpeg_bytes(small, 70, None), d["mtime"]))
        elif d["type"] == "reencode":
            arr = np.clip(np.asarray(im, dtype=np.float32) * 1.06 + 3, 0, 255).astype(np.uint8)
            out.append(put(root, d["file"], jpeg_bytes(Image.fromarray(arr, "RGB"), 76, exif), d["mtime"]))
    return out


# ---------------------------------------------------------------------------------------------
# GPX
# ---------------------------------------------------------------------------------------------

def gpx_bytes(name: str, segments: list[list[tuple[float, float, float, float]]]) -> bytes:
    from .util import utc

    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<gpx version="1.1" creator="Atlas synthetic generator" xmlns="http://www.topografix.com/GPX/1/1">',
         f"  <trk><name>{name}</name>"]
    for seg in segments:
        o.append("    <trkseg>")
        for t, lat, lon, ele in seg:
            o.append(f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}"><ele>{ele:.1f}</ele>'
                     f'<time>{utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>')
        o.append("    </trkseg>")
    o.append("  </trk>")
    o.append("</gpx>")
    return ("\n".join(o) + "\n").encode()


# ---------------------------------------------------------------------------------------------
# voice notes: speech-like signal (harmonic source through moving formants + fricative noise)
# ---------------------------------------------------------------------------------------------

def wav_bytes(seed: int, duration_s: float, sr: int = 16000) -> bytes:
    R = rng_of("voice", seed)
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    f0_base = R.uniform(105, 190)
    sig = np.zeros(n, dtype=np.float64)
    env = np.zeros(n, dtype=np.float64)
    f0 = np.full(n, f0_base)
    formants = np.zeros((n, 3))
    pos = int(0.25 * sr)
    while pos < n - int(0.3 * sr):
        words = int(R.integers(3, 9))                      # a phrase of a few syllables
        for _ in range(words * 2):
            L = int(R.uniform(0.11, 0.24) * sr)
            if pos + L >= n:
                break
            a = np.hanning(L) ** 0.6 * R.uniform(0.5, 1.0)
            env[pos:pos + L] = np.maximum(env[pos:pos + L], a)
            f0[pos:pos + L] = f0_base * R.uniform(0.85, 1.25) * np.linspace(1.03, 0.95, L)
            F = np.array([R.uniform(300, 850), R.uniform(900, 2300), R.uniform(2400, 3200)])
            formants[pos:pos + L] = F
            if R.random() < 0.35:                          # consonant burst between syllables
                c = int(R.uniform(0.03, 0.07) * sr)
                noise = R.standard_normal(c) * np.hanning(c) * R.uniform(0.05, 0.16)
                sig[pos:pos + c] += np.diff(np.concatenate([[0.0], noise])) * 3
            pos += L + int(R.uniform(0.0, 0.03) * sr)
        pos += int(R.uniform(0.25, 0.7) * sr)              # breath pause
    formants[formants[:, 0] == 0] = (500, 1500, 2500)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    voiced = np.zeros(n)
    for k in range(1, 26):
        fk = f0 * k
        amp = sum(np.exp(-0.5 * ((fk - formants[:, i]) / bw) ** 2) * g
                  for i, (bw, g) in enumerate(((90, 1.0), (130, 0.6), (170, 0.3))))
        voiced += (amp + 0.02) / k ** 0.5 * np.sin(k * phase)
    sig += voiced * env * 0.22
    sig += R.standard_normal(n) * 0.004                    # room tone
    sig *= np.minimum(1.0, np.minimum(t / 0.05, (duration_s - t) / 0.05)).clip(0, 1)
    peak = np.abs(sig).max() or 1.0
    pcm = (sig / peak * 0.8 * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
