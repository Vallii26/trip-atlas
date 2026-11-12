"""Outdoor scene painters. Each takes a canvas (with layout RNG ``c.L``) and look params ``P``."""

from __future__ import annotations

import math

import numpy as np

from .canvas import Cv, jit, mix, ridge_profile, shade

SKIES = {
    "day": [(0, (58, 118, 205)), (0.7, (150, 195, 238)), (1, (205, 226, 244))],
    "overcast": [(0, (138, 148, 162)), (1, (208, 212, 216))],
    "sunset": [(0, (52, 62, 128)), (0.45, (196, 108, 110)), (0.8, (250, 160, 84)), (1, (255, 208, 128))],
    "sunrise": [(0, (84, 104, 168)), (0.5, (226, 160, 170)), (0.85, (255, 196, 150)), (1, (255, 226, 180))],
    "night": [(0, (6, 8, 26)), (0.7, (18, 24, 54)), (1, (40, 44, 78))],
}


def sky(c: Cv, kind: str, yh: float, sun=True):
    L = c.L
    if kind == "day" and L.random() < 0.22:
        kind = "overcast"
    hue = L.integers(-10, 11)
    stops = [(p, (col[0] + hue, col[1], col[2] - hue)) for p, col in SKIES[kind]]
    c.bg(stops, 0, yh)
    sx, sy = L.uniform(0.15, 0.85), 0.0
    if kind == "night":
        n = int(L.integers(60, 140))
        for x, y, b in zip(L.uniform(0, 1, n), L.uniform(0, yh * 0.9, n), L.integers(120, 255, n)):
            c.circ(float(x), float(y), 0.0016, (int(b), int(b), int(min(255, b + 20))))
        if L.random() < 0.7:
            sx, sy = L.uniform(0.1, 0.9), L.uniform(0.08, yh * 0.5)
            c.glow(sx, sy, 0.05, (70, 70, 80), 1.0)
            c.circ(sx, sy, 0.03, (236, 234, 214))
    elif kind in ("sunset", "sunrise"):
        sy = yh - L.uniform(0.02, 0.09)
        c.glow(sx, sy, 0.22, (120, 70, 20), 1.0)
        c.glow(sx, sy, 0.07, (255, 220, 150), 1.0)
        c.circ(sx, sy, 0.032, (255, 244, 214))
    elif kind == "day" and sun and L.random() < 0.6:
        sy = L.uniform(0.06, yh * 0.45)
        c.glow(sx, sy, 0.12, (90, 90, 70), 1.0)
        c.circ(sx, sy, 0.028, (255, 252, 235))
    # clouds
    n = {"day": int(L.integers(0, 6)), "overcast": 9, "sunset": int(L.integers(2, 6)),
         "sunrise": int(L.integers(1, 5)), "night": 0}[kind]
    ccol = {"day": (250, 250, 252), "overcast": (226, 228, 232), "sunset": (255, 176, 140),
            "sunrise": (255, 206, 196), "night": (0, 0, 0)}[kind]
    for _ in range(n):
        cx, cy = L.uniform(0, 1), L.uniform(0.04, max(0.06, yh * 0.75))
        for _k in range(int(L.integers(3, 7))):
            c.ell(cx + L.uniform(-0.08, 0.08), cy + L.uniform(-0.012, 0.012), L.uniform(0.03, 0.09),
                  L.uniform(0.012, 0.03), jit(ccol, L, 6))
    if n:
        c.blur(0.012, (0, 0, 1, yh))
    return kind, (sx, sy)


def ridges(c: Cv, y_top: float, y_bot: float, n: int, far, near, rough=0.5, snow=False):
    """Layered mountain silhouettes from far (pale) to near (dark)."""
    L = c.L
    for i in range(n):
        t = i / max(1, n - 1)
        base = y_top + (y_bot - y_top) * (0.25 + 0.75 * t)
        amp = (y_bot - y_top) * L.uniform(0.35, 0.6) * (1.0 - 0.45 * t)
        prof = ridge_profile(L, 72, rough)
        col = mix(far, near, t)
        pts = [(x, base - amp * p) for x, p in zip(np.linspace(-0.02, 1.02, 72), prof)]
        c.poly(pts + [(1.02, 1.0), (-0.02, 1.0)], col)
        if snow and i == 0:
            cap = [(x, y) for x, y in pts if y < base - amp * 0.72]
            for x, y in cap[::2]:
                c.poly([(x - 0.012, y + 0.035), (x, y), (x + 0.012, y + 0.035)], (240, 242, 248))


def _tod_sky(P, default="day"):
    return P.get("sky", default)


# ---------------------------------------------------------------------------------------------
# city
# ---------------------------------------------------------------------------------------------

ROOFS = {
    "terracotta": ((196, 96, 62), [(244, 236, 220), (236, 214, 170), (226, 190, 180), (200, 214, 226)]),
    "grey": ((92, 98, 110), [(222, 214, 198), (200, 196, 188), (214, 204, 180), (180, 170, 160)]),
    "red": ((150, 62, 52), [(232, 224, 206), (238, 206, 150), (210, 190, 170), (226, 226, 226)]),
}


def _houses(c: Cv, y0: float, y1: float, pal, night=False, rows=7):
    L = c.L
    roof, walls = ROOFS[pal]
    for r in range(rows):
        t = r / (rows - 1)
        yb = y0 + (y1 - y0) * (t ** 0.9) + 0.02
        hh = 0.045 + 0.085 * t
        x = -0.05 + L.uniform(-0.03, 0)
        while x < 1.05:
            w = L.uniform(0.045, 0.1) * (0.6 + 0.8 * t)
            h = hh * L.uniform(0.7, 1.5)
            wall = walls[int(L.integers(0, len(walls)))]
            fade = 0.55 + 0.45 * t
            wall = mix((170, 180, 200), wall, fade)
            rf = mix((170, 170, 190), jit(roof, L, 14), fade)
            if night:
                wall, rf = shade(wall, 0.2), shade(rf, 0.16)
            c.rect(x, yb - h, x + w, yb + 0.02, wall)
            c.poly([(x - 0.004, yb - h), (x + w / 2, yb - h - 0.028 * (0.5 + t)), (x + w + 0.004, yb - h)], rf)
            nw = max(1, int(w / 0.022))
            for k in range(nw):
                for j in range(max(1, int(h / 0.035))):
                    lit = night and L.random() < 0.35
                    if night and not lit:
                        continue
                    wc = (255, 214, 120) if lit else shade(wall, 0.55)
                    wx = x + (k + 0.3) * w / nw
                    wy = yb - h + 0.012 + j * 0.035
                    c.rect(wx, wy, wx + w / nw * 0.4, wy + 0.016, wc)
            x += w + L.uniform(0.0, 0.008)


def city_view(c: Cv, P):
    """Rooftops from a viewpoint with a river or hills beyond."""
    kind = _tod_sky(P)
    L = c.L
    yh = L.uniform(0.34, 0.44)
    kind, _ = sky(c, kind, yh)
    night = kind == "night"
    pal = P.get("roofs", "terracotta")
    if P.get("river", True):
        wc = {"day": (96, 150, 196), "overcast": (140, 156, 170), "sunset": (214, 140, 110),
              "sunrise": (220, 170, 160), "night": (16, 22, 46)}[kind]
        c.bg([(0, wc), (1, shade(wc, 0.85))], yh, yh + 0.09)
        c.poly([(0, yh + 0.005), (0.3, yh - 0.012), (0.7, yh - 0.006), (1, yh + 0.004), (1, yh + 0.012), (0, yh + 0.014)],
               shade(wc, 0.6) if not night else (10, 12, 26))
        if night:
            for x in L.uniform(0, 1, 40):
                c.circ(float(x), yh + 0.004, 0.002, (255, 220, 150))
    else:
        ridges(c, yh - 0.1, yh + 0.06, 2, (150, 170, 200), (96, 120, 130))
    c.bg([(0, (150, 150, 160) if not night else (20, 20, 30)), (1, (120, 110, 100) if not night else (10, 10, 16))],
         yh + 0.08, 1.0)
    _houses(c, yh + 0.1, 1.0, pal, night)
    lm = P.get("landmark")
    if lm == "castle":
        col = (150, 130, 100) if not night else (60, 50, 34)
        c.rect(0.55, yh + 0.02, 0.9, yh + 0.1, col)
        for k in range(8):
            c.rect(0.55 + k * 0.045, yh + 0.005, 0.57 + k * 0.045, yh + 0.03, col)
        c.poly([(0.5, yh + 0.14), (0.55, yh + 0.07), (0.9, yh + 0.07), (0.97, yh + 0.14)], (70, 110, 70) if not night else (12, 22, 14))
    elif lm == "dome":
        col = (226, 220, 206) if not night else (70, 64, 50)
        c.rect(0.3, yh + 0.03, 0.42, yh + 0.14, col)
        c.pie(0.36, yh + 0.035, 0.05, 0.06, 180, 360, col)
    elif lm == "tower":
        col = (70, 70, 80) if not night else (30, 30, 40)
        c.poly([(0.69, yh + 0.1), (0.705, yh - 0.2), (0.72, yh + 0.1)], col)
    if kind in ("sunset", "sunrise"):
        c.darken(0.8, yh + 0.08, 1.0)
        c.glow(0.5, yh + 0.1, 0.5, (50, 20, 0), 1.0)


def street(c: Cv, P):
    """Street in one-point perspective; ``night`` / ``tram`` variants via P."""
    L = c.L
    night = P.get("sky") == "night"
    kind, _ = sky(c, P.get("sky", "day"), 0.5, sun=False)
    vx, vy = L.uniform(0.42, 0.58), L.uniform(0.44, 0.52)
    lw, rw = jit((226, 206, 170), L, 30), jit((206, 190, 200), L, 30)
    far = jit((180, 170, 170), L, 20)
    road = (86, 84, 90)
    if night:
        lw, rw, far, road = shade(lw, 0.22), shade(rw, 0.2), shade(far, 0.18), (26, 26, 34)
    c.poly([(0, 1), (0, 0), (0.12, 0), (vx - 0.07, vy - 0.1), (vx - 0.07, vy + 0.03), (0.0, 1.0)], lw)
    c.poly([(1, 1), (1, 0), (0.88, 0), (vx + 0.07, vy - 0.1), (vx + 0.07, vy + 0.03), (1.0, 1.0)], rw)
    c.rect(vx - 0.07, vy - 0.07, vx + 0.07, vy + 0.03, far)
    c.poly([(0, 1), (vx - 0.07, vy + 0.03), (vx + 0.07, vy + 0.03), (1, 1)], road)
    c.poly([(0, 1), (vx - 0.07, vy + 0.03), (vx - 0.05, vy + 0.03), (0.16, 1)], shade(road, 1.5))
    c.poly([(1, 1), (vx + 0.07, vy + 0.03), (vx + 0.05, vy + 0.03), (0.84, 1)], shade(road, 1.5))
    # windows / doors receding on both walls
    for side in (0, 1):
        for i in range(7):
            t0, t1 = 1 - 0.78 ** i, 1 - 0.78 ** (i + 0.6)
            for lvl in range(3):
                def pt(t, v):
                    ex = 0.0 if side == 0 else 1.0
                    wx = vx - 0.07 if side == 0 else vx + 0.07
                    x = ex + (wx - ex) * t
                    ytop = 0.0 + (vy - 0.1) * t
                    ybot = 1.0 + (vy + 0.03 - 1.0) * t
                    return (x, ytop + (ybot - ytop) * v)
                v0 = 0.2 + lvl * 0.2
                lit = night and L.random() < 0.45
                wc = (255, 206, 110) if lit else ((16, 16, 26) if night else shade(lw if side == 0 else rw, 0.5))
                if lvl == 2:
                    wc = jit((120, 60, 40), L, 40) if not night else ((255, 180, 90) if L.random() < 0.6 else (30, 20, 20))
                    c.poly([pt(t0, 0.66), pt(t1, 0.66), pt(t1, 0.9), pt(t0, 0.9)], wc)
                else:
                    c.poly([pt(t0, v0), pt(t1, v0), pt(t1, v0 + 0.1), pt(t0, v0 + 0.1)], wc)
    if P.get("tiles"):
        for i in range(10):
            y = vy + 0.05 + (1 - vy) * (i / 10) ** 1.6
            c.line([(0.1, y), (0.9, y)], shade(road, 1.25), 0.003)
    if P.get("neon") or night:
        for _ in range(int(L.integers(2, 6))):
            x, y = L.uniform(0.05, 0.95), L.uniform(0.3, 0.6)
            col = [(255, 60, 140), (80, 220, 255), (255, 200, 60), (140, 255, 120)][int(L.integers(0, 4))]
            c.glow(x, y, 0.05, shade(col, 0.5), 1.0)
            c.rect(x - 0.02, y - 0.008, x + 0.02, y + 0.008, col)
        for x in (0.2, 0.8):
            c.line([(x, 0.95), (x, 0.36)], (30, 30, 36), 0.006)
            c.glow(x, 0.36, 0.09, (150, 110, 50), 1.0)
            c.circ(x, 0.36, 0.012, (255, 236, 180))
        c.reflect(0.9, 1.0, (20, 20, 30), 0.5, 0.004) if P.get("wet") else None
    if P.get("pink"):
        c.poly([(0.16, 1), (vx - 0.05, vy + 0.03), (vx + 0.05, vy + 0.03), (0.84, 1)], (232, 110, 160) if not night else (120, 40, 80))
    if P.get("tram"):
        tc = P.get("tram_col", (244, 196, 48))
        x0, x1, y0, y1 = 0.3, 0.72, 0.4, 0.84
        c.line([(0.5, 0.0), (0.5, y0)], (40, 40, 40), 0.004)
        c.rect(x0, y0, x1, y1, tc)
        c.rect(x0, y0, x1, y0 + 0.05, (250, 246, 232))
        c.rect(x0, y1 - 0.1, x1, y1, shade(tc, 0.85))
        for k in range(3):
            c.rect(x0 + 0.03 + k * 0.135, y0 + 0.09, x0 + 0.12 + k * 0.135, y0 + 0.24, (70, 90, 110))
        c.circ(x0 + 0.06, y1 - 0.05, 0.014, (255, 250, 220))
        c.circ(x1 - 0.06, y1 - 0.05, 0.014, (255, 250, 220))
        c.rect(0.44, y0 + 0.01, 0.58, y0 + 0.04, (30, 30, 30))
        c.rect(x0 + 0.04, y1, x1 - 0.04, y1 + 0.02, (30, 30, 30))
        c.line([(0.3, 1.0), (0.44, y1 + 0.02)], (150, 150, 150), 0.004)
        c.line([(0.72, 1.0), (0.58, y1 + 0.02)], (150, 150, 150), 0.004)


def landmark(c: Cv, P):
    """A monument on a square; ``shape`` picks the silhouette."""
    L = c.L
    kind, _ = sky(c, P.get("sky", "day"), 0.72)
    night = kind == "night"
    shape = P.get("shape") or ["tower", "arch", "dome", "castle", "palace"][int(L.integers(0, 5))]
    stone = jit(P.get("stone", (224, 208, 176)), L, 10)
    if night:
        stone = mix(shade(stone, 0.55), (200, 150, 70), 0.35)
    dark = shade(stone, 0.55)
    ground = (168, 160, 150) if not night else (34, 32, 40)
    if P.get("lawn"):
        ground = (96, 150, 80) if not night else (16, 34, 20)
    c.bg([(0, shade(ground, 1.1)), (1, shade(ground, 0.8))], 0.7, 1.0)
    for _ in range(int(L.integers(3, 8))):  # distant trees / buildings
        x = L.uniform(0, 1)
        c.ell(x, 0.7, L.uniform(0.04, 0.09), L.uniform(0.03, 0.06), (70, 100, 70) if not night else (14, 22, 18))
    cx = L.uniform(0.42, 0.58)
    if shape == "tower":
        c.rect(cx - 0.1, 0.36, cx + 0.1, 0.72, stone)
        c.rect(cx - 0.06, 0.16, cx + 0.06, 0.36, stone)
        for k in range(5):
            c.rect(cx - 0.1 + k * 0.045, 0.33, cx - 0.08 + k * 0.045, 0.36, stone)
        for k in range(3):
            c.rect(cx - 0.06 + k * 0.045, 0.135, cx - 0.04 + k * 0.045, 0.16, stone)
        for x in (cx - 0.1, cx + 0.1):
            c.ell(x, 0.36, 0.022, 0.03, stone)
        for k in range(3):
            c.pie(cx - 0.055 + k * 0.055, 0.5, 0.016, 0.03, 180, 360, dark)
            c.rect(cx - 0.071 + k * 0.055, 0.5, cx - 0.039 + k * 0.055, 0.54, dark)
        c.rect(cx - 0.012, 0.22, cx + 0.012, 0.28, dark)
        c.rect(cx + 0.1, 0.56, cx + 0.3, 0.72, shade(stone, 0.9))
    elif shape == "arch":
        c.rect(cx - 0.22, 0.2, cx + 0.22, 0.72, stone)
        c.rect(cx - 0.26, 0.17, cx + 0.26, 0.22, shade(stone, 1.05))
        c.poly([(cx - 0.08, 0.17), (cx, 0.06), (cx + 0.08, 0.17)], stone)
        c.pie(cx, 0.42, 0.1, 0.14, 180, 360, (150, 190, 230) if not night else (10, 12, 30))
        c.rect(cx - 0.1, 0.42, cx + 0.1, 0.72, (150, 190, 230) if not night else (10, 12, 30))
        c.rect(cx - 0.1, 0.6, cx + 0.1, 0.72, shade(ground, 1.2))
        for x in (cx - 0.17, cx - 0.13, cx + 0.13, cx + 0.17):
            c.rect(x - 0.012, 0.24, x + 0.012, 0.72, shade(stone, 1.08))
    elif shape in ("dome", "mosque"):
        c.rect(cx - 0.24, 0.46, cx + 0.24, 0.72, stone)
        c.pie(cx, 0.47, 0.17, 0.24, 180, 360, shade(stone, 0.92) if shape == "dome" else (150, 160, 176) if not night else (70, 76, 96))
        c.rect(cx - 0.004, 0.17, cx + 0.004, 0.24, dark)
        for k in (-1, 1):
            c.pie(cx + k * 0.2, 0.48, 0.06, 0.08, 180, 360, shade(stone, 0.9))
        if shape == "mosque":
            for x in (cx - 0.32, cx - 0.27, cx + 0.27, cx + 0.32):
                c.rect(x - 0.008, 0.2, x + 0.008, 0.72, stone)
                c.poly([(x - 0.012, 0.2), (x, 0.12), (x + 0.012, 0.2)], dark)
                c.rect(x - 0.013, 0.34, x + 0.013, 0.35, dark)
        else:
            for x in (cx - 0.21, cx + 0.21):
                c.rect(x - 0.03, 0.3, x + 0.03, 0.72, stone)
                c.poly([(x - 0.034, 0.3), (x, 0.22), (x + 0.034, 0.3)], dark)
        for k in range(7):
            c.pie(cx - 0.18 + k * 0.06, 0.6, 0.016, 0.03, 180, 360, dark)
            c.rect(cx - 0.196 + k * 0.06, 0.6, cx - 0.164 + k * 0.06, 0.66, dark)
    elif shape == "castle":
        c.poly([(0, 0.72), (0.1, 0.6), (0.9, 0.6), (1, 0.72)], (90, 130, 80) if not night else (16, 30, 18))
        c.rect(cx - 0.34, 0.4, cx + 0.34, 0.64, stone)
        for k in range(18):
            c.rect(cx - 0.34 + k * 0.04, 0.375, cx - 0.32 + k * 0.04, 0.4, stone)
        for x in (cx - 0.34, cx - 0.08, cx + 0.2, cx + 0.34):
            c.rect(x - 0.045, 0.28, x + 0.045, 0.64, shade(stone, 0.94))
            for k in range(3):
                c.rect(x - 0.045 + k * 0.035, 0.255, x - 0.025 + k * 0.035, 0.28, shade(stone, 0.94))
            c.rect(x - 0.008, 0.36, x + 0.008, 0.42, dark)
        c.line([(cx - 0.08, 0.255), (cx - 0.08, 0.17)], (60, 60, 60), 0.004)
        c.poly([(cx - 0.08, 0.17), (cx - 0.03, 0.185), (cx - 0.08, 0.2)], (200, 40, 40))
    elif shape == "cathedral":
        c.rect(cx - 0.2, 0.34, cx + 0.2, 0.72, stone)
        for x in (cx - 0.15, cx + 0.15):
            c.rect(x - 0.06, 0.14, x + 0.06, 0.72, shade(stone, 0.96))
            c.poly([(x - 0.06, 0.14), (x, P.get("spire", 0.04)), (x + 0.06, 0.14)], dark if P.get("spire", 0.04) < 0.1 else stone)
            for j in range(3):
                c.rect(x - 0.025, 0.2 + j * 0.12, x + 0.025, 0.28 + j * 0.12, dark)
        c.circ(cx, 0.46, 0.055, dark)
        c.circ(cx, 0.46, 0.04, (90, 110, 160) if not night else (255, 200, 110))
        for k in (-1, 0, 1):
            c.pie(cx + k * 0.1, 0.66, 0.035, 0.07, 180, 360, dark)
            c.rect(cx + k * 0.1 - 0.035, 0.66, cx + k * 0.1 + 0.035, 0.72, dark)
    elif shape == "eiffel":
        iron = (96, 76, 60) if not night else (230, 170, 60)
        c.poly([(cx - 0.17, 0.72), (cx - 0.02, 0.1), (cx + 0.02, 0.1), (cx + 0.17, 0.72), (cx + 0.11, 0.72),
                (cx, 0.5), (cx - 0.11, 0.72)], iron)
        c.rect(cx - 0.1, 0.52, cx + 0.1, 0.545, iron)
        c.rect(cx - 0.055, 0.34, cx + 0.055, 0.36, iron)
        c.rect(cx - 0.003, 0.03, cx + 0.003, 0.1, iron)
        if night:
            c.glow(cx, 0.4, 0.3, (90, 60, 10), 1.0)
    elif shape == "wheel":
        iron = (150, 40, 40) if not night else (255, 120, 80)
        c.circ(cx, 0.4, 0.3, None, outline=iron, width=int(0.012 * c.H))
        for k in range(12):
            a = k * math.pi / 6
            x, y = cx + 0.3 * c.H / c.W * math.cos(a), 0.4 + 0.3 * math.sin(a)
            c.line([(cx, 0.4), (x, y)], iron, 0.003)
            c.rect(x - 0.018, y - 0.015, x + 0.018, y + 0.02, (200, 60, 50) if not night else (255, 210, 120))
        c.poly([(cx - 0.1, 0.72), (cx, 0.4), (cx + 0.1, 0.72), (cx + 0.08, 0.72), (cx, 0.46), (cx - 0.08, 0.72)], iron)
    elif shape == "monument":
        c.poly([(cx - 0.2, 0.72), (cx - 0.16, 0.5), (cx + 0.02, 0.1), (cx + 0.07, 0.1), (cx + 0.1, 0.72)], stone)
        c.poly([(cx - 0.2, 0.72), (cx - 0.3, 0.72), (cx - 0.16, 0.5)], shade(stone, 0.85))
        for k in range(7):
            c.ell(cx - 0.17 + k * 0.03, 0.6 - k * 0.012, 0.012, 0.04, dark)
    else:  # palace
        c.rect(cx - 0.42, 0.42, cx + 0.42, 0.72, stone)
        c.rect(cx - 0.12, 0.34, cx + 0.12, 0.72, shade(stone, 1.04))
        c.poly([(cx - 0.14, 0.34), (cx, 0.26), (cx + 0.14, 0.34)], shade(stone, 0.9))
        c.rect(cx - 0.44, 0.4, cx + 0.44, 0.425, shade(stone, 0.8))
        for k in range(16):
            for j in range(2):
                lit = night and L.random() < 0.5
                c.rect(cx - 0.4 + k * 0.052, 0.47 + j * 0.11, cx - 0.375 + k * 0.052, 0.53 + j * 0.11,
                       (255, 210, 120) if lit else dark)
        if P.get("dome_top"):
            c.pie(cx, 0.3, 0.07, 0.12, 180, 360, (90, 130, 110) if not night else (40, 60, 56))
    if night:
        c.glow(cx, 0.6, 0.35, (70, 45, 10), 1.0)
    for x in L.uniform(0.05, 0.95, int(L.integers(2, 6))):  # lamp posts
        c.line([(float(x), 0.86), (float(x), 0.74)], (40, 40, 44), 0.005)
        if night:
            c.glow(float(x), 0.74, 0.04, (160, 120, 60), 1.0)
        c.circ(float(x), 0.74, 0.008, (255, 240, 200) if night else (230, 230, 220))


def waterfront(c: Cv, P):
    """River / sea / harbour with far shore; optional bridge, boat rail, lit skyline."""
    L = c.L
    yh = L.uniform(0.4, 0.5)
    kind, _ = sky(c, P.get("sky", "day"), yh)
    night = kind == "night"
    shore = (86, 104, 110) if not night else (12, 14, 26)
    prof = ridge_profile(L, 48, 0.3)
    c.poly([(x, yh - 0.02 - 0.06 * p) for x, p in zip(np.linspace(0, 1, 48), prof)] + [(1, yh), (0, yh)], shore)
    x = 0.0
    while x < 1.0:  # far skyline
        w, h = L.uniform(0.015, 0.05), L.uniform(0.01, 0.07)
        c.rect(x, yh - h, x + w, yh, shade(shore, L.uniform(0.7, 1.2)))
        if night:
            for _ in range(3):
                c.circ(x + L.uniform(0, w), yh - L.uniform(0, h), 0.002, (255, 214, 130))
        x += w + L.uniform(0, 0.02)
    feat = P.get("feature")
    if feat == "bridge":
        bc = (150, 60, 50) if not night else (220, 170, 90)
        c.rect(0, yh - 0.05, 1, yh - 0.04, bc)
        for px in (0.28, 0.72):
            c.rect(px - 0.02, yh - 0.2, px + 0.02, yh, bc)
        for a, b in ((0.0, 0.28), (0.28, 0.72), (0.72, 1.0)):
            pts = [(a + (b - a) * t, yh - 0.19 + 0.14 * (1 - (2 * t - 1) ** 2)) for t in np.linspace(0, 1, 16)]
            c.line(pts, bc, 0.006)
    elif feat == "mosque":
        col = shade(shore, 0.8) if not night else (60, 50, 40)
        c.pie(0.6, yh - 0.03, 0.07, 0.08, 180, 360, col)
        for mx in (0.5, 0.7):
            c.rect(mx - 0.004, yh - 0.17, mx + 0.004, yh, col)
    elif feat == "tower":
        col = shade(shore, 0.9)
        c.rect(0.62, yh - 0.12, 0.68, yh, col)
        c.rect(0.635, yh - 0.17, 0.665, yh - 0.12, col)
    tint = {"day": (60, 110, 150), "overcast": (110, 124, 136), "sunset": (150, 90, 80),
            "sunrise": (170, 130, 130), "night": (8, 12, 30)}[kind]
    c.bg([(0, tint), (1, shade(tint, 0.6))], yh, 1.0)
    c.reflect(yh, 1.0, tint, 0.6 if not night else 0.75, 0.006)
    for _ in range(int(L.integers(0, 4))):  # boats
        bx, by = L.uniform(0.1, 0.9), L.uniform(yh + 0.06, 0.8)
        s = 0.5 + (by - yh) * 2
        c.poly([(bx - 0.05 * s, by), (bx + 0.05 * s, by), (bx + 0.04 * s, by + 0.02 * s), (bx - 0.04 * s, by + 0.02 * s)],
               (240, 240, 236) if not night else (60, 60, 70))
        c.rect(bx - 0.02 * s, by - 0.02 * s, bx + 0.015 * s, by, (200, 60, 50) if not night else (255, 210, 120))
    if P.get("rail", True):
        rc = (40, 44, 50) if not night else (10, 10, 14)
        c.rect(0, 0.9, 1, 1.0, shade(rc, 1.6))
        c.rect(0, 0.84, 1, 0.855, rc)
        for k in range(12):
            c.rect(k / 11 - 0.004, 0.84, k / 11 + 0.004, 1.0, rc)


def park(c: Cv, P):
    L = c.L
    kind, _ = sky(c, P.get("sky", "day"), 0.5)
    c.bg([(0, (120, 176, 96)), (1, (70, 130, 62))], 0.48, 1.0)
    if P.get("palace"):
        st = (236, 208, 120)
        c.rect(0.1, 0.36, 0.9, 0.5, st)
        c.rect(0.42, 0.31, 0.58, 0.5, shade(st, 1.04))
        for k in range(20):
            c.rect(0.12 + k * 0.039, 0.4, 0.14 + k * 0.039, 0.46, shade(st, 0.6))
    for layer in range(2):
        for _ in range(int(L.integers(5, 9))):
            x = L.uniform(0, 1)
            y = 0.5 + layer * 0.1 + L.uniform(-0.02, 0.02)
            s = 0.6 + layer * 0.7
            c.rect(x - 0.006 * s, y - 0.02, x + 0.006 * s, y + 0.07 * s, (84, 60, 40))
            g = jit((50, 120 - layer * 20, 52), L, 16)
            for _k in range(4):
                c.ell(x + L.uniform(-0.03, 0.03) * s, y - 0.05 * s + L.uniform(-0.03, 0.03), 0.05 * s, 0.06 * s, jit(g, L, 10))
    c.poly([(0.36, 1.0), (0.47, 0.52), (0.53, 0.52), (0.64, 1.0)], (214, 196, 160))
    if P.get("pond"):
        c.ell(0.76, 0.8, 0.2, 0.08, (96, 150, 190))
    if P.get("bench", True):
        c.rect(0.12, 0.78, 0.3, 0.8, (110, 76, 46))
        c.rect(0.12, 0.72, 0.3, 0.735, (110, 76, 46))
        c.rect(0.13, 0.8, 0.14, 0.86, (50, 50, 50))
        c.rect(0.28, 0.8, 0.29, 0.86, (50, 50, 50))
    c.speckle(0, 0.6, 1, 1, 60, [(240, 220, 90), (250, 250, 250), (230, 120, 150)], 0.003)


def market(c: Cv, P):
    """Open-air market: rows of stalls with striped awnings and heaps of colourful goods."""
    L = c.L
    sky(c, P.get("sky", "day"), 0.3)
    c.bg([(0, jit((214, 196, 170), L, 14)), (1, (190, 172, 150))], 0.22, 0.4)
    for k in range(9):
        c.rect(0.03 + k * 0.11, 0.26, 0.07 + k * 0.11, 0.33, (80, 70, 70))
    c.bg([(0, (150, 144, 138)), (1, (112, 106, 100))], 0.4, 1.0)
    cols = [(214, 60, 50), (50, 110, 190), (240, 190, 50), (60, 150, 90), (236, 130, 40), (150, 80, 160)]
    goods = [(220, 60, 40), (250, 180, 40), (110, 170, 60), (240, 240, 230), (150, 60, 120), (240, 130, 30), (120, 80, 50)]
    for row in range(3):
        y = 0.4 + row * 0.19
        s = 0.7 + row * 0.35
        x = L.uniform(-0.1, 0.0)
        while x < 1.0:
            w = L.uniform(0.2, 0.3) * s
            a = cols[int(L.integers(0, len(cols)))]
            n = 8
            for k in range(n):
                cc = a if k % 2 == 0 else (246, 242, 232)
                c.poly([(x + k * w / n, y - 0.06 * s), (x + (k + 1) * w / n, y - 0.06 * s),
                        (x + (k + 1) * w / n + 0.01, y + 0.01 * s), (x + k * w / n - 0.01, y + 0.01 * s)], cc)
            c.rect(x + 0.005, y + 0.01 * s, x + 0.012, y + 0.15 * s, (60, 56, 52))
            c.rect(x + w - 0.012, y + 0.01 * s, x + w - 0.005, y + 0.15 * s, (60, 56, 52))
            c.rect(x, y + 0.09 * s, x + w, y + 0.15 * s, jit((120, 90, 60), L, 14))
            for _ in range(int(14 * s)):
                gx, gy = x + L.uniform(0.02, max(0.03, w - 0.02)), y + L.uniform(0.07, 0.1) * s
                c.circ(gx, gy, 0.012 * s, goods[int(L.integers(0, len(goods)))])
            x += w + L.uniform(0.02, 0.07)


def station(c: Cv, P):
    """Platform with a train under a station roof."""
    L = c.L
    night = P.get("sky") == "night"
    hall = P.get("hall", L.random() < 0.6)
    if hall:
        c.bg([(0, (70, 76, 84)), (1, (150, 160, 170))] if not night else [(0, (16, 18, 26)), (1, (40, 44, 56))], 0, 0.5)
        for k in range(9):
            x = k / 8
            c.line([(x, 0.0), (0.5 + (x - 0.5) * 0.25, 0.42)], (44, 48, 56), 0.008)
        for k in range(5):
            t = k / 5
            y = 0.4 * (1 - 0.75 ** k)
            c.arc(0.5, 0.42, 0.6 * (1 - t * 0.7), 0.5 * (1 - t * 0.7), 180, 360, (50, 54, 62), 0.01)
            if y:
                pass
        if not night:
            c.glow(0.5, 0.3, 0.3, (90, 90, 80), 1.0)
    else:
        sky(c, P.get("sky", "day"), 0.5)
        c.poly([(0, 0.0), (1, 0.0), (1, 0.1), (0.56, 0.36), (0.44, 0.36), (0, 0.16)], (70, 74, 82))
    vx, vy = 0.5, 0.42
    plat = (176, 172, 164) if not night else (60, 58, 62)
    c.poly([(0.0, 1.0), (vx - 0.02, vy + 0.02), (vx + 0.02, vy + 0.02), (0.62, 1.0)], plat)
    c.poly([(0.56, 1.0), (vx + 0.012, vy + 0.02), (vx + 0.02, vy + 0.02), (0.62, 1.0)], (240, 200, 40))
    c.poly([(0.62, 1.0), (vx + 0.02, vy + 0.02), (vx + 0.06, vy + 0.02), (1.0, 1.0)], (50, 46, 44))
    tc = P.get("train_col") or [(200, 40, 40), (240, 240, 240), (30, 60, 130), (250, 200, 40), (60, 70, 80)][int(L.integers(0, 5))]
    if night:
        tc = shade(tc, 0.5)
    c.poly([(1.0, 0.18), (vx + 0.03, vy - 0.045), (vx + 0.03, vy + 0.02), (1.0, 0.96)], tc)
    c.poly([(1.0, 0.4), (vx + 0.03, vy - 0.02), (vx + 0.03, vy - 0.008), (1.0, 0.56)],
           (30, 36, 46) if not night else (250, 220, 150))
    c.poly([(1.0, 0.7), (vx + 0.03, vy + 0.005), (vx + 0.03, vy + 0.01), (1.0, 0.76)], shade(tc, 0.6))
    for k in range(6):
        t = 1 - 0.7 ** (k + 0.5)
        x = 1.0 + (vx + 0.03 - 1.0) * t
        c.line([(x, 0.18 + (vy - 0.045 - 0.18) * t), (x, 0.96 + (vy + 0.02 - 0.96) * t)], shade(tc, 0.7), 0.004)
    # columns, sign, clock, luggage
    for k in range(4):
        t = 1 - 0.6 ** (k + 0.3)
        x = 0.06 + (vx - 0.03 - 0.06) * t
        c.rect(x - 0.012 * (1 - t), 0.1 * (1 - t) + vy * t - 0.1, x + 0.012 * (1 - t), 1.0 + (vy + 0.02 - 1.0) * t, (60, 64, 72))
    c.rect(0.16, 0.2, 0.4, 0.28, (20, 40, 110) if not P.get("sign_col") else P["sign_col"])
    for j in range(2):
        c.rect(0.175, 0.215 + j * 0.03, 0.3 + 0.06 * j, 0.23 + j * 0.03, (240, 240, 240))
    c.circ(0.47, 0.2, 0.03, (240, 240, 230), outline=(30, 30, 30), width=3)
    c.line([(0.47, 0.2), (0.47, 0.18)], (20, 20, 20), 0.004)
    c.line([(0.47, 0.2), (0.48, 0.21)], (20, 20, 20), 0.004)
    c.rect(0.22, 0.8, 0.3, 0.93, jit((40, 90, 130), L, 40))
    c.rect(0.25, 0.76, 0.27, 0.8, (30, 30, 30))
    if night:
        for x in (0.2, 0.4):
            c.glow(x, 0.1, 0.08, (120, 110, 80), 1.0)


def train_window(c: Cv, P):
    """Landscape streaking past a carriage window."""
    L = c.L
    yh = L.uniform(0.42, 0.52)
    kind, _ = sky(c, P.get("sky", "day"), yh)
    land = P.get("land") or ["fields", "hills", "alps", "plain"][int(L.integers(0, 4))]
    if land == "alps":
        ridges(c, yh - 0.26, yh + 0.04, 3, (170, 186, 214), (70, 100, 90), 0.6, snow=True)
    elif land == "hills":
        ridges(c, yh - 0.12, yh + 0.04, 2, (130, 160, 150), (70, 116, 76), 0.2)
    fcols = [(150, 180, 70), (214, 196, 96), (96, 150, 70), (176, 150, 90), (120, 170, 96), (226, 210, 130)]
    if kind in ("sunset", "sunrise"):
        fcols = [mix(f, (220, 130, 80), 0.4) for f in fcols]
    y = yh
    while y < 1.0:
        h = L.uniform(0.03, 0.1) * (0.5 + (y - yh) * 2)
        c.rect(0, y, 1, y + h + 0.01, jit(fcols[int(L.integers(0, len(fcols)))], L, 10))
        y += h
    for _ in range(int(L.integers(6, 16))):
        x, yy = L.uniform(0, 1), L.uniform(yh - 0.01, yh + 0.2)
        s = 0.4 + (yy - yh) * 4
        c.ell(x, yy, 0.03 * s, 0.05 * s, (50, 90, 50))
    if P.get("village", L.random() < 0.5):
        for k in range(5):
            x = 0.3 + k * 0.05 + L.uniform(-0.01, 0.01)
            c.rect(x, yh - 0.03, x + 0.035, yh + 0.01, (236, 226, 206))
            c.poly([(x - 0.004, yh - 0.03), (x + 0.017, yh - 0.055), (x + 0.039, yh - 0.03)], (170, 80, 60))
    c.hblur(P.get("blur", 7), yh - 0.03, 1.0)
    for k in range(3):  # poles flashing by
        x = L.uniform(0, 1)
        c.rect(x, 0.2, x + 0.012, 1.0, (60, 60, 60))
    c.hblur(22, 0.84, 1.0)
    # window frame + interior
    fr = jit((40, 44, 52), L, 8)
    m = 0.14
    c.rect(0, 0, 1, m, fr)
    c.rect(0, 0, m * 0.75, 1, fr)
    c.rect(1 - m * 0.75, 0, 1, 1, fr)
    c.rect(0, 0.84, 1, 1, fr)
    c.rect(0.0, 0.84, 1.0, 0.87, shade(fr, 2.2))
    c.rect(0.3, 0.9, 0.72, 1.0, jit((150, 140, 124), L, 12))  # table
    c.ell(0.6, 0.93, 0.03, 0.025, (240, 240, 240))
    c.line([(0.2, m), (0.34, 0.84)], (255, 255, 255), 0.002)


def lake(c: Cv, P):
    """Mountain lake with reflection."""
    L = c.L
    yh = L.uniform(0.46, 0.56)
    kind, _ = sky(c, P.get("sky", "day"), yh)
    rock = P.get("rock", (196, 186, 176))
    ridges(c, 0.12, yh, 3, mix(rock, (170, 190, 220), 0.5), mix(rock, (70, 96, 70), 0.6), 0.7)
    for _ in range(int(L.integers(8, 20))):  # shoreline firs
        x = L.uniform(0, 1)
        c.poly([(x - 0.012, yh), (x, yh - L.uniform(0.04, 0.08)), (x + 0.012, yh)], (30, 70, 50))
    tint = P.get("water", (40, 150, 150))
    c.bg([(0, tint), (1, shade(tint, 0.6))], yh, 1.0)
    c.reflect(yh, 1.0, tint, 0.62, 0.003)
    c.poly([(0, 1.0), (0, 0.9), (0.2, 0.93), (0.5, 0.97), (1, 0.92), (1, 1)], (150, 146, 138))
    for _ in range(9):
        c.ell(L.uniform(0, 1), L.uniform(0.93, 1.0), L.uniform(0.02, 0.05), L.uniform(0.012, 0.03), jit((130, 126, 120), L, 20))
    if P.get("swimmer"):
        sx, sy = L.uniform(0.3, 0.7), L.uniform(0.7, 0.8)
        c.ell(sx, sy, 0.07, 0.008, shade(tint, 1.5))
        c.ell(sx, sy + 0.02, 0.1, 0.008, shade(tint, 1.4))
        c.circ(sx, sy - 0.012, 0.014, (226, 170, 140))
    if P.get("boats"):
        for k in range(4):
            bx = 0.2 + k * 0.06
            c.poly([(bx - 0.03, yh + 0.05), (bx + 0.03, yh + 0.05), (bx + 0.022, yh + 0.065), (bx - 0.022, yh + 0.065)], (120, 76, 40))


def trail(c: Cv, P):
    """Hiking path through alpine meadow / scree with peaks beyond."""
    L = c.L
    yh = L.uniform(0.42, 0.55)
    kind, _ = sky(c, P.get("sky", "day"), yh)
    rock = P.get("rock", (200, 190, 178))
    ridges(c, 0.1, yh + 0.05, 3, mix(rock, (176, 196, 224), 0.45), mix(rock, (90, 100, 90), 0.5), 0.75)
    scree = P.get("scree", L.random() < 0.35)
    g0, g1 = ((168, 162, 154), (130, 124, 118)) if scree else (jit((120, 160, 80), L, 14), (80, 124, 60))
    c.bg([(0, g0), (1, g1)], yh + 0.02, 1.0)
    prof = ridge_profile(L, 32, 0.2)
    c.poly([(x, yh + 0.06 - 0.05 * p) for x, p in zip(np.linspace(0, 1, 32), prof)] + [(1, yh + 0.1), (0, yh + 0.1)], g0)
    # winding path
    px = L.uniform(0.3, 0.7)
    pts_l, pts_r = [], []
    for t in np.linspace(0, 1, 14):
        y = 1.0 - (1.0 - yh - 0.05) * t
        x = px + 0.16 * math.sin(t * 5 + L.uniform(0, 0.01)) * (1 - t) + (0.5 - px) * t
        w = 0.07 * (1 - t) ** 1.5 + 0.004
        pts_l.append((x - w, y))
        pts_r.append((x + w, y))
    c.poly(pts_l + pts_r[::-1], (206, 190, 160) if not scree else (196, 192, 186))
    for _ in range(int(L.integers(8, 18))):
        bx, by = L.uniform(0, 1), L.uniform(yh + 0.1, 1.0)
        s = 0.3 + (by - yh) * 1.6
        c.ell(bx, by, 0.035 * s, 0.022 * s, jit((150, 146, 140), L, 18))
        c.ell(bx - 0.006 * s, by - 0.006 * s, 0.02 * s, 0.01 * s, (190, 186, 180))
    if not scree:
        c.speckle(0, yh + 0.12, 1, 1, 90, [(250, 220, 70), (250, 250, 250), (200, 110, 190)], 0.003)
    if P.get("sign", L.random() < 0.4):
        sx = L.uniform(0.1, 0.9)
        c.rect(sx, 0.62, sx + 0.008, 0.84, (90, 70, 50))
        c.rect(sx - 0.05, 0.64, sx + 0.06, 0.68, (236, 220, 60))
        c.rect(sx - 0.05, 0.69, sx + 0.04, 0.725, (220, 50, 40))
    if P.get("hut"):
        _hut(c, 0.62, yh + 0.07, 0.6)


def _hut(c: Cv, x, y, s):
    c.rect(x, y - 0.07 * s, x + 0.2 * s, y + 0.03 * s, (206, 196, 180))
    c.rect(x, y - 0.02 * s, x + 0.2 * s, y + 0.03 * s, (150, 144, 136))
    c.poly([(x - 0.015 * s, y - 0.07 * s), (x + 0.1 * s, y - 0.14 * s), (x + 0.215 * s, y - 0.07 * s)], (110, 60, 46))
    for k in range(4):
        wx = x + (0.02 + k * 0.045) * s
        c.rect(wx, y - 0.055 * s, wx + 0.025 * s, y - 0.028 * s, (60, 60, 70))
        c.rect(wx - 0.006 * s, y - 0.055 * s, wx, y - 0.028 * s, (190, 40, 40))
        c.rect(wx + 0.025 * s, y - 0.055 * s, wx + 0.031 * s, y - 0.028 * s, (190, 40, 40))


def hut(c: Cv, P):
    L = c.L
    yh = 0.56
    kind, _ = sky(c, P.get("sky", "day"), yh)
    rock = P.get("rock", (200, 190, 178))
    ridges(c, 0.14, yh + 0.04, 2, mix(rock, (176, 196, 224), 0.4), mix(rock, (96, 100, 96), 0.4), 0.8)
    c.bg([(0, (150, 150, 140)), (1, (120, 136, 96))], yh, 1.0)
    _hut(c, L.uniform(0.18, 0.3), 0.7, 2.3)
    fx = L.uniform(0.76, 0.9)
    c.rect(fx, 0.4, fx + 0.006, 0.75, (220, 220, 220))
    c.poly([(fx + 0.006, 0.4), (fx + 0.09, 0.42), (fx + 0.006, 0.46)], P.get("flag", (0, 140, 70)))
    for k in range(3):
        c.rect(0.1 + k * 0.28, 0.86, 0.3 + k * 0.28, 0.875, (130, 96, 60))
        c.rect(0.12 + k * 0.28, 0.875, 0.13 + k * 0.28, 0.93, (90, 66, 40))
        c.rect(0.27 + k * 0.28, 0.875, 0.28 + k * 0.28, 0.93, (90, 66, 40))
    if kind in ("sunset", "sunrise"):
        c.glow(0.5, 0.6, 0.6, (50, 22, 0), 1.0)


def forest(c: Cv, P):
    L = c.L
    c.bg([(0, (150, 196, 150)), (0.5, (70, 130, 80)), (1, (40, 70, 44))], 0, 1.0)
    c.glow(L.uniform(0.3, 0.7), 0.1, 0.35, (110, 110, 60), 1.0)
    for layer in range(3):
        n = [22, 14, 8][layer]
        for _ in range(n):
            x = L.uniform(0, 1)
            w = [0.012, 0.022, 0.045][layer] * L.uniform(0.7, 1.3)
            tc = [(60, 80, 60), (56, 50, 40), (40, 32, 26)][layer]
            c.rect(x - w, 0.0, x + w, 0.72 + layer * 0.12, jit(tc, L, 8))
            for _k in range(3):
                yy = L.uniform(0.0, 0.5)
                g = jit([(70, 130, 80), (40, 100, 56), (26, 70, 40)][layer], L, 12)
                c.poly([(x - w * 7, yy + 0.12), (x, yy), (x + w * 7, yy + 0.12)], g)
        if layer < 2:
            c.blur(0.004 * (2 - layer))
    c.bg([(0, (70, 90, 50)), (1, (50, 60, 36))], 0.86, 1.0)
    c.poly([(0.3, 1.0), (0.46, 0.8), (0.54, 0.8), (0.72, 1.0)], (150, 124, 90))
    c.speckle(0, 0.86, 1, 1, 60, [(120, 150, 70), (90, 70, 40), (200, 190, 120)], 0.004)


def summit(c: Cv, P):
    """Looking out from a summit: wide sky, sea of lower ridges, cross and cairn in front."""
    L = c.L
    yh = L.uniform(0.5, 0.6)
    kind, _ = sky(c, P.get("sky", "day"), yh)
    rock = P.get("rock", (200, 190, 178))
    far = {"sunset": (150, 110, 140), "sunrise": (190, 150, 170)}.get(kind, (166, 188, 222))
    near = {"sunset": (60, 44, 70), "sunrise": (96, 76, 100)}.get(kind, (88, 104, 124))
    ridges(c, yh - 0.14, 0.92, 5, far, near, 0.6, snow=P.get("snow", False))
    if kind in ("sunset", "sunrise"):
        c.glow(0.5, yh, 0.5, (60, 26, 0), 1.0)
    fg = mix(rock, (120, 110, 100), 0.5) if kind == "day" else shade(rock, 0.4)
    prof = ridge_profile(L, 24, 0.5)
    c.poly([(x, 0.9 - 0.1 * p) for x, p in zip(np.linspace(0, 1, 24), prof)] + [(1, 1), (0, 1)], fg)
    if P.get("cross", True):
        cx = L.uniform(0.2, 0.8)
        cc = (70, 60, 50) if kind == "day" else (24, 20, 20)
        c.rect(cx - 0.007, 0.56, cx + 0.007, 0.88, cc)
        c.rect(cx - 0.05, 0.63, cx + 0.05, 0.65, cc)
    if P.get("terrace"):
        c.rect(0, 0.9, 1, 1.0, (120, 90, 60) if kind == "day" else (40, 30, 24))
        c.rect(0, 0.8, 1, 0.812, (60, 50, 44))
        for k in range(10):
            c.rect(k / 9 - 0.004, 0.8, k / 9 + 0.004, 0.92, (60, 50, 44))
    for _ in range(5):
        c.ell(L.uniform(0, 1), L.uniform(0.9, 1.0), L.uniform(0.03, 0.08), L.uniform(0.02, 0.04), shade(fg, L.uniform(0.7, 1.2)))


def wildlife(c: Cv, P):
    """Animal silhouette on an alpine slope."""
    L = c.L
    yh = L.uniform(0.3, 0.4)
    sky(c, P.get("sky", "day"), yh)
    rock = P.get("rock", (200, 190, 178))
    ridges(c, 0.08, yh + 0.08, 2, mix(rock, (176, 196, 224), 0.4), mix(rock, (100, 104, 100), 0.4), 0.8)
    animal = P.get("animal", "ibex")
    grass = animal != "ibex"
    c.bg([(0, (136, 168, 90) if grass else (176, 170, 160)), (1, (96, 130, 66) if grass else (136, 130, 122))], yh + 0.04, 1.0)
    c.blur(0.002)
    for _ in range(12):
        c.ell(L.uniform(0, 1), L.uniform(0.6, 1.0), L.uniform(0.04, 0.12), L.uniform(0.02, 0.05), jit((150, 146, 140), L, 16))
    ax, ay = L.uniform(0.4, 0.6), L.uniform(0.6, 0.68)
    if animal == "ibex":
        b = (96, 76, 58)
        c.ell(ax, ay, 0.11, 0.065, b)
        c.poly([(ax + 0.06, ay - 0.03), (ax + 0.12, ay - 0.13), (ax + 0.16, ay - 0.1), (ax + 0.1, ay + 0.01)], b)
        c.ell(ax + 0.15, ay - 0.12, 0.035, 0.028, b)
        c.poly([(ax + 0.17, ay - 0.11), (ax + 0.2, ay - 0.09), (ax + 0.165, ay - 0.085)], shade(b, 0.8))
        for lx in (-0.08, -0.05, 0.05, 0.08):
            c.rect(ax + lx - 0.008, ay + 0.03, ax + lx + 0.008, ay + 0.17, shade(b, 0.8))
        c.arc(ax + 0.07, ay - 0.13, 0.08, 0.1, 190, 330, (60, 50, 44), 0.012)
        c.arc(ax + 0.085, ay - 0.12, 0.08, 0.1, 190, 320, (70, 60, 50), 0.01)
        c.ell(ax, ay + 0.02, 0.07, 0.03, (150, 130, 104))
        c.poly([(ax - 0.1, ay - 0.02), (ax - 0.13, ay - 0.04), (ax - 0.11, ay + 0.01)], b)
    else:
        b = (140, 104, 70)
        n = int(P.get("count", 2))
        for k in range(n):
            mx, my = ax - 0.14 + k * 0.24, ay + 0.06 + 0.03 * k
            c.ell(mx, my + 0.13, 0.12, 0.04, (150, 146, 140))
            c.ell(mx, my + 0.03, 0.05, 0.1, b)
            c.ell(mx, my + 0.05, 0.03, 0.06, (190, 160, 120))
            c.circ(mx + 0.005, my - 0.08, 0.04, b)
            c.circ(mx - 0.025, my - 0.11, 0.01, shade(b, 0.7))
            c.circ(mx + 0.03, my - 0.115, 0.01, shade(b, 0.7))
            c.circ(mx + 0.02, my - 0.085, 0.006, (20, 20, 20))
            c.ell(mx + 0.035, my - 0.065, 0.012, 0.008, (60, 40, 30))
    c.speckle(0, 0.75, 1, 1, 50, [(250, 220, 70), (250, 250, 250)] if grass else [(120, 120, 116)], 0.003)


def baths(c: Cv, P):
    """Thermal baths: ochre palace wings around a steaming turquoise pool."""
    L = c.L
    sky(c, P.get("sky", "day"), 0.4)
    st = jit((240, 200, 90), L, 8)
    c.rect(0, 0.26, 1, 0.56, st)
    c.pie(0.5, 0.27, 0.12, 0.16, 180, 360, (90, 130, 110))
    c.rect(0.36, 0.2, 0.64, 0.56, shade(st, 1.05))
    for k in range(14):
        c.pie(0.03 + k * 0.072, 0.42, 0.022, 0.05, 180, 360, shade(st, 0.55))
        c.rect(0.008 + k * 0.072, 0.42, 0.052 + k * 0.072, 0.5, shade(st, 0.55))
    c.rect(0, 0.54, 1, 0.6, (236, 232, 224))
    c.bg([(0, (70, 190, 206)), (1, (30, 140, 176))], 0.6, 1.0)
    c.reflect(0.6, 1.0, (50, 170, 196), 0.35, 0.004)
    for _ in range(9):
        hx, hy = L.uniform(0.05, 0.95), L.uniform(0.68, 0.95)
        c.circ(hx, hy, 0.012, (226, 180, 150))
        c.ell(hx, hy + 0.016, 0.03, 0.006, (120, 220, 230))
    for _ in range(6):
        c.glow(L.uniform(0, 1), L.uniform(0.56, 0.7), 0.08, (50, 50, 50), 1.0)
