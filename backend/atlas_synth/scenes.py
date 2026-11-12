"""Scene vocabulary and the photo renderer.

``SCENES`` maps every scene name to the closed list of visual tags a tagger should output for a
photo of that scene. ``render_photo`` paints a scene deterministically from two seeds:

- the *layout* seed (per moment + scene): palette, composition, objects → photos of the same
  moment look alike, different moments look different;
- the *view* seed (per photo): crop window, exposure, white balance, grain → small viewpoint and
  exposure perturbation. Burst frames share the view seed and differ by a pixel of jitter + grain.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import scenes_indoor as si
from . import scenes_outdoor as so
from .canvas import Cv
from .util import rng_of

TAGS = [
    "outdoor", "indoor", "night", "sunrise", "sunset", "water", "mountain", "forest", "city",
    "street", "food", "drink", "animal", "train", "station", "market", "museum", "landmark",
    "park", "worship", "lodging", "tram",
]

# scene → (tags, painter, default look params)
_REG: dict[str, tuple[list[str], object, dict]] = {
    "city_view": (["outdoor", "city"], so.city_view, {}),
    "city_sunset": (["outdoor", "city", "sunset"], so.city_view, {"sky": "sunset"}),
    "city_night": (["outdoor", "city", "night"], so.city_view, {"sky": "night"}),
    "street": (["outdoor", "city", "street"], so.street, {}),
    "night_street": (["outdoor", "city", "street", "night"], so.street, {"sky": "night"}),
    "tram": (["outdoor", "city", "street", "tram"], so.street, {"tram": True}),
    "landmark": (["outdoor", "city", "landmark"], so.landmark, {}),
    "landmark_night": (["outdoor", "city", "landmark", "night"], so.landmark, {"sky": "night"}),
    "waterfront": (["outdoor", "water", "city"], so.waterfront, {}),
    "waterfront_sunset": (["outdoor", "water", "city", "sunset"], so.waterfront, {"sky": "sunset"}),
    "waterfront_night": (["outdoor", "water", "city", "night"], so.waterfront, {"sky": "night"}),
    "park": (["outdoor", "park"], so.park, {}),
    "market": (["outdoor", "market"], so.market, {}),
    "market_hall": (["indoor", "market", "food"], si.market_hall, {}),
    "cafe": (["indoor", "drink", "food"], si.cafe, {}),
    "restaurant": (["indoor", "food"], si.restaurant, {}),
    "food": (["food"], si.food, {}),
    "bar": (["indoor", "night", "drink"], si.bar, {}),
    "museum": (["indoor", "museum"], si.museum, {}),
    "church": (["indoor", "worship"], si.church, {}),
    "hotel_room": (["indoor", "lodging"], si.hotel_room, {}),
    "terminal": (["indoor", "station"], si.terminal, {}),
    "station": (["station", "train"], so.station, {}),
    "train_window": (["outdoor", "train"], so.train_window, {}),
    "train_window_sunrise": (["outdoor", "train", "sunrise"], so.train_window, {"sky": "sunrise"}),
    "train_interior": (["indoor", "train"], si.train_interior, {}),
    "baths": (["outdoor", "water"], so.baths, {}),
    "lake": (["outdoor", "water", "mountain"], so.lake, {}),
    "trail": (["outdoor", "mountain"], so.trail, {}),
    "forest": (["outdoor", "forest"], so.forest, {}),
    "summit": (["outdoor", "mountain"], so.summit, {}),
    "mountain_sunrise": (["outdoor", "mountain", "sunrise"], so.summit, {"sky": "sunrise", "cross": False, "terrace": True}),
    "mountain_sunset": (["outdoor", "mountain", "sunset"], so.summit, {"sky": "sunset", "cross": False, "terrace": True}),
    "hut": (["outdoor", "mountain", "lodging"], so.hut, {}),
    "hut_interior": (["indoor", "lodging", "food"], si.hut_interior, {}),
    "wildlife": (["outdoor", "mountain", "animal"], so.wildlife, {}),
}

SCENES: dict[str, list[str]] = {k: v[0] for k, v in _REG.items()}
assert all(t in TAGS for tags in SCENES.values() for t in tags)

OVERSCAN = 1.3


@lru_cache(maxsize=8)
def _vignette(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    return (1.0 - 0.1 * r2).astype(np.float32)[..., None]


def paint_canvas(scene: str, look: dict, layout_seed: int, w: int, h: int) -> Image.Image:
    _, painter, defaults = _REG[scene]
    cw, ch = max(64, int(w / 2 * OVERSCAN)), max(64, int(h / 2 * OVERSCAN))
    cv = Cv(cw, ch, np.random.Generator(np.random.PCG64(layout_seed)))
    painter(cv, {**defaults, **(look or {})})
    return cv.im


def render_photo(scene: str, look: dict, layout_seed: int, view_seed: int, w: int, h: int,
                 frame: int = 0, grain_seed: int | None = None) -> Image.Image:
    """Paint ``scene`` and return the finished w×h RGB photo."""
    im = paint_canvas(scene, look, layout_seed, w, h)
    V = rng_of("view", view_seed)
    f = V.uniform(0.74, 0.98)
    cw, ch = im.size
    bw, bh = cw * f, ch * f
    x0 = V.uniform(0, cw - bw)
    y0 = V.uniform(0, ch - bh)
    gain = V.uniform(0.93, 1.07)
    warm = V.uniform(-0.025, 0.025)
    if frame:
        J = rng_of("burst-jitter", view_seed, frame)
        x0 = min(max(0.0, x0 + J.uniform(-0.6, 0.6)), cw - bw)
        y0 = min(max(0.0, y0 + J.uniform(-0.6, 0.6)), ch - bh)
    out = im.resize((w, h), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))
    arr = np.asarray(out, dtype=np.float32)
    arr = arr * (gain * np.array([1 + warm, 1.0, 1 - warm], dtype=np.float32)) * _vignette(w, h)
    G = rng_of("grain", view_seed if grain_seed is None else grain_seed, frame)
    arr += G.standard_normal((h, w, 1), dtype=np.float32) * 3.2
    arr += G.standard_normal((h // 4 + 1, w // 4 + 1, 3), dtype=np.float32).repeat(4, 0).repeat(4, 1)[:h, :w] * 1.2
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------------------------------------
# screenshots
# ---------------------------------------------------------------------------------------------

SCREEN_W, SCREEN_H = 1170, 2532


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def _rows(d, L, x0, x1, y, n, h=26, gap=30, col=(170, 174, 182)):
    for _ in range(n):
        d.rounded_rectangle([x0, y, x0 + (x1 - x0) * L.uniform(0.35, 1.0), y + h], h // 2, fill=col)
        y += h + gap
    return y


def render_screenshot(kind: str, seed: int, clock: str, lines: list[str] | None = None) -> Image.Image:
    """Phone-screen PNG content: status bar, flat blocks, text-like rows. No camera EXIF."""
    L = rng_of("screenshot", seed)
    W, H = SCREEN_W, SCREEN_H
    dark = kind == "chat" and L.random() < 0.3
    bg = (18, 18, 20) if dark else (247, 247, 250)
    fg = (240, 240, 240) if dark else (20, 20, 24)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.text((70, 52), clock, font=_font(46), fill=fg)
    d.rounded_rectangle([W - 190, 58, W - 90, 100], 12, outline=fg, width=4)
    d.rounded_rectangle([W - 184, 64, W - 120, 94], 8, fill=fg)
    for k in range(4):
        d.rectangle([W - 330 + k * 22, 96 - 10 * (k + 1), W - 316 + k * 22, 96], fill=fg)
    lines = lines or []
    if kind == "boarding_pass":
        accent = [(0, 82, 160), (200, 30, 50), (0, 120, 90), (240, 160, 0)][int(L.integers(0, 4))]
        d.rectangle([0, 150, W, 420], fill=accent)
        d.text((70, 210), lines[0] if lines else "Boarding pass", font=_font(72), fill=(255, 255, 255))
        d.rounded_rectangle([60, 480, W - 60, 2100], 40, fill=(255, 255, 255), outline=(220, 220, 226), width=3)
        d.text((120, 560), lines[1] if len(lines) > 1 else "AAA", font=_font(150), fill=(20, 20, 24))
        d.text((W - 480, 560), lines[2] if len(lines) > 2 else "BBB", font=_font(150), fill=(20, 20, 24))
        d.line([430, 650, W - 520, 650], fill=accent, width=8)
        y = 800
        for i in range(3):
            for j in range(2):
                d.rounded_rectangle([120 + j * 480, y, 300 + j * 480, y + 30], 14, fill=(170, 174, 182))
                txt = lines[3 + i * 2 + j] if len(lines) > 3 + i * 2 + j else ""
                if txt:
                    d.text((120 + j * 480, y + 50), txt, font=_font(64), fill=(20, 20, 24))
                else:
                    d.rounded_rectangle([120 + j * 480, y + 56, 380 + j * 480, y + 110], 20, fill=(40, 40, 46))
            y += 190
        q0x, q0y, n = 285, 1400, 30
        bits = L.random((n, n)) < 0.5
        for i in range(n):
            for j in range(n):
                if bits[i, j] or (i < 7 and j < 7) or (i < 7 and j >= n - 7) or (i >= n - 7 and j < 7):
                    d.rectangle([q0x + j * 20, q0y + i * 20, q0x + j * 20 + 19, q0y + i * 20 + 19], fill=(0, 0, 0))
        d.rounded_rectangle([200, 2200, W - 200, 2330], 60, fill=(20, 20, 24))
    elif kind == "map":
        d.rectangle([0, 150, W, H], fill=(236, 232, 220))
        for _ in range(9):
            x, y = L.uniform(0, W), L.uniform(200, 1900)
            d.ellipse([x - 200, y - 130, x + 200, y + 130], fill=(206, 228, 196))
        d.polygon([(0, 1500), (W, 1250), (W, 1500), (0, 1800)], fill=(170, 208, 240))
        for _ in range(16):
            a = (L.uniform(0, W), L.uniform(150, 2000))
            b = (a[0] + L.uniform(-900, 900), a[1] + L.uniform(-900, 900))
            d.line([a, b], fill=(255, 255, 255), width=int(L.integers(14, 34)))
        pts = [(200 + i * 110 + L.uniform(-40, 40), 1750 - i * 150 + L.uniform(-50, 50)) for i in range(8)]
        d.line(pts, fill=(40, 120, 250), width=18, joint="curve")
        x, y = pts[0]
        d.ellipse([x - 44, y - 44, x + 44, y + 44], fill=(255, 255, 255))
        d.ellipse([x - 30, y - 30, x + 30, y + 30], fill=(40, 120, 250))
        x, y = pts[-1]
        d.polygon([(x, y), (x - 40, y - 90), (x + 40, y - 90)], fill=(230, 50, 50))
        d.ellipse([x - 50, y - 150, x + 50, y - 50], fill=(230, 50, 50))
        d.rounded_rectangle([40, 170, W - 40, 300], 60, fill=(255, 255, 255))
        d.text((110, 205), lines[0] if lines else "Search here", font=_font(54), fill=(90, 90, 96))
        d.rounded_rectangle([0, 2080, W, H + 60], 60, fill=(255, 255, 255))
        d.text((70, 2130), lines[1] if len(lines) > 1 else "12 min", font=_font(80), fill=(20, 20, 24))
        _rows(d, L, 70, W - 200, 2260, 2)
        d.rounded_rectangle([W - 380, 2130, W - 70, 2240], 55, fill=(40, 120, 250))
    else:  # chat
        d.rectangle([0, 150, W, 330], fill=(30, 30, 34) if dark else (236, 236, 240))
        d.ellipse([60, 180, 180, 300], fill=(120, 160, 220))
        d.text((220, 205), lines[0] if lines else "Mum", font=_font(60), fill=fg)
        y = 400
        k = 0
        while y < 2250:
            mine = L.random() < 0.5
            w = L.uniform(300, 760)
            nrow = int(L.integers(1, 4))
            h = 70 + nrow * 56
            x0 = W - 60 - w if mine else 60
            col = (40, 130, 250) if mine else ((50, 50, 56) if dark else (226, 226, 232))
            d.rounded_rectangle([x0, y, x0 + w, y + h], 44, fill=col)
            txt = lines[1 + k] if len(lines) > 1 + k else None
            if txt and w > 500:
                d.text((x0 + 40, y + 36), txt[: int(w / 26)], font=_font(44), fill=(255, 255, 255) if mine or dark else (20, 20, 24))
                k += 1
            else:
                _rows(d, L, x0 + 40, x0 + w - 40, y + 36, nrow, 24, 30,
                      (190, 214, 255) if mine else ((120, 120, 128) if dark else (160, 160, 170)))
            y += h + 40
        d.rounded_rectangle([40, 2330, W - 200, 2440], 55, outline=(150, 150, 156), width=4)
        d.ellipse([W - 170, 2330, W - 60, 2440], fill=(40, 130, 250))
    d.rounded_rectangle([W // 2 - 210, H - 40, W // 2 + 210, H - 26], 7, fill=fg)
    return im
