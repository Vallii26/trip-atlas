"""Indoor scene painters (and the food close-up)."""

from __future__ import annotations

import math

from .canvas import Cv, jit, mix, shade

FOODS = {
    "pastry": [(226, 170, 70), (200, 130, 50), (246, 220, 150)],
    "seafood": [(236, 110, 80), (250, 220, 190), (120, 160, 70), (240, 230, 120)],
    "pasta": [(240, 210, 130), (200, 60, 40), (90, 140, 60)],
    "meat": [(150, 80, 50), (220, 180, 90), (110, 150, 70), (240, 230, 210)],
    "salad": [(110, 170, 70), (220, 60, 50), (240, 230, 200), (150, 90, 150)],
    "dessert": [(250, 240, 220), (150, 90, 60), (220, 60, 80)],
    "soup": [(200, 90, 40), (240, 230, 210), (110, 150, 70)],
    "street": [(214, 170, 110), (120, 160, 70), (230, 220, 200), (190, 70, 50)],
}


def _plate(c: Cv, cx, cy, r, dish, rim=(244, 242, 236)):
    L = c.L
    asp = c.H / c.W
    c.ell(cx + 0.006, cy + 0.01, r * asp * 1.03, r * 1.03, (0, 0, 0))
    c.ell(cx, cy, r * asp, r, rim)
    c.ell(cx, cy, r * asp * 0.74, r * 0.74, shade(rim, 0.94))
    cols = FOODS.get(dish, FOODS["meat"])
    if dish == "soup":
        c.ell(cx, cy, r * asp * 0.7, r * 0.7, cols[0])
    n = int(L.integers(7, 16))
    for _ in range(n):
        a, d = L.uniform(0, 2 * math.pi), L.uniform(0, 0.52) * r
        fr = L.uniform(0.1, 0.24) * r
        c.ell(cx + d * math.cos(a) * asp, cy + d * math.sin(a), fr * asp, fr * L.uniform(0.6, 1.0),
              jit(cols[int(L.integers(0, len(cols)))], L, 12))
    if dish == "pastry":
        for k in range(int(L.integers(1, 4))):
            px = cx + (k - 1) * 0.4 * r * asp
            c.ell(px, cy, 0.3 * r * asp, 0.3 * r, (214, 150, 60))
            c.ell(px, cy, 0.22 * r * asp, 0.22 * r, (246, 214, 110))
            c.ell(px + 0.02 * r, cy - 0.04 * r, 0.1 * r * asp, 0.07 * r, (150, 90, 40))


def _cup(c: Cv, cx, cy, r, liquid=(70, 44, 30)):
    asp = c.H / c.W
    c.ell(cx, cy, r * asp * 1.5, r * 1.5, (236, 234, 228))
    c.ell(cx, cy, r * asp, r, (250, 250, 248))
    c.ell(cx, cy, r * asp * 0.8, r * 0.8, liquid)
    c.arc(cx + r * asp, cy, r * asp * 0.5, r * 0.4, 270, 90, (250, 250, 248), 0.012)


def _glass(c: Cv, x, y, s, col):
    c.poly([(x - 0.02 * s, y - 0.1 * s), (x + 0.02 * s, y - 0.1 * s), (x + 0.014 * s, y), (x - 0.014 * s, y)], (220, 230, 236))
    c.poly([(x - 0.018 * s, y - 0.07 * s), (x + 0.018 * s, y - 0.07 * s), (x + 0.013 * s, y - 0.004), (x - 0.013 * s, y - 0.004)], col)


def food(c: Cv, P):
    """Top-down close-up of a plate on a table."""
    L = c.L
    table = P.get("table") or [(150, 104, 66), (236, 230, 220), (60, 56, 60), (190, 60, 50), (200, 176, 130)][int(L.integers(0, 5))]
    table = jit(table, L, 10)
    c.bg([(0, shade(table, 1.08)), (1, shade(table, 0.9))], 0, 1.0)
    for k in range(9):
        y = k / 9 + L.uniform(-0.01, 0.01)
        c.line([(0, y), (1, y + L.uniform(-0.01, 0.01))], shade(table, 0.93), 0.004)
    dish = P.get("dish") or list(FOODS)[int(L.integers(0, len(FOODS)))]
    cx, cy = L.uniform(0.42, 0.58), L.uniform(0.45, 0.55)
    _plate(c, cx, cy, 0.3, dish)
    if P.get("second", L.random() < 0.5):
        _plate(c, cx + 0.42, cy - 0.3, 0.2, P.get("dish2", dish))
    if P.get("drink", True):
        col = P.get("drink_col") or [(70, 44, 30), (236, 190, 60), (130, 30, 50), (240, 240, 230)][int(L.integers(0, 4))]
        _cup(c, cx - 0.36, cy - 0.28, 0.07, col)
    c.rect(cx + 0.27, cy - 0.2, cx + 0.282, cy + 0.26, (190, 190, 196))
    c.rect(cx - 0.3, cy - 0.16, cx - 0.288, cy + 0.26, (190, 190, 196))
    c.poly([(0, 0.9), (0.16, 0.84), (0.2, 1.0), (0, 1.0)], (246, 244, 240))
    c.glow(L.uniform(0.2, 0.8), L.uniform(0.1, 0.4), 0.4, (40, 36, 26), 1.0)


def _room(c: Cv, wall, floor, yf=0.62):
    c.bg([(0, shade(wall, 0.82)), (1, wall)], 0, yf)
    c.bg([(0, floor), (1, shade(floor, 0.7))], yf, 1.0)
    c.rect(0, yf - 0.012, 1, yf + 0.008, shade(wall, 0.6))


def _table_set(c: Cv, x, y, s, cloth, dish=None, drink=None):
    c.ell(x, y, 0.16 * s, 0.05 * s, cloth)
    c.rect(x - 0.012 * s, y + 0.03 * s, x + 0.012 * s, y + 0.22 * s, shade(cloth, 0.45))
    c.ell(x, y + 0.22 * s, 0.06 * s, 0.014 * s, shade(cloth, 0.4))
    for k in (-1, 1):
        c.ell(x + k * 0.07 * s, y - 0.004, 0.04 * s, 0.014 * s, (246, 246, 242))
        if dish:
            c.ell(x + k * 0.07 * s, y - 0.006, 0.026 * s, 0.008 * s, FOODS[dish][0])
        if drink:
            _glass(c, x + k * 0.13 * s, y, s * 0.8, drink)
    for k in (-1, 1):  # chairs
        cx = x + k * 0.24 * s
        c.rect(cx - 0.035 * s, y - 0.12 * s, cx + 0.035 * s, y + 0.06 * s, shade(cloth, 0.35))
        c.rect(cx - 0.04 * s, y + 0.05 * s, cx + 0.04 * s, y + 0.075 * s, shade(cloth, 0.3))
        c.rect(cx - 0.036 * s, y + 0.075 * s, cx - 0.028 * s, y + 0.2 * s, shade(cloth, 0.25))
        c.rect(cx + 0.028 * s, y + 0.075 * s, cx + 0.036 * s, y + 0.2 * s, shade(cloth, 0.25))


def cafe(c: Cv, P):
    """Bright café: counter with pastry case, window, small table with cups."""
    L = c.L
    wall = jit(P.get("wall", (232, 214, 186)), L, 14)
    floor = jit(P.get("floor", (120, 90, 66)), L, 12)
    _room(c, wall, floor)
    if P.get("tiles"):
        for k in range(24):
            for j in range(6):
                c.rect(k / 24 + 0.004, j * 0.1 + 0.004, (k + 1) / 24 - 0.004, (j + 1) * 0.1 - 0.004,
                       (236, 240, 246) if (k + j) % 2 else (70, 110, 180))
    wx = L.uniform(0.04, 0.2)
    c.rect(wx, 0.1, wx + 0.26, 0.46, (190, 220, 240))
    c.rect(wx + 0.125, 0.1, wx + 0.135, 0.46, (246, 244, 240))
    c.rect(wx, 0.27, wx + 0.26, 0.28, (246, 244, 240))
    c.glow(wx + 0.13, 0.28, 0.3, (40, 40, 30), 1.0)
    # counter + case + shelf
    cc = jit(P.get("counter", (96, 64, 44)), L, 10)
    c.rect(0.52, 0.44, 1.0, 0.72, cc)
    c.rect(0.5, 0.42, 1.0, 0.45, shade(cc, 1.5))
    c.rect(0.56, 0.3, 0.86, 0.42, (214, 230, 236))
    for k in range(8):
        c.ell(0.59 + k * 0.034, 0.385, 0.014, 0.018, [(226, 170, 70), (200, 130, 50), (246, 220, 150), (150, 90, 60)][k % 4])
    c.rect(0.56, 0.08, 0.98, 0.095, shade(cc, 0.8))
    for k in range(9):
        c.rect(0.58 + k * 0.044, 0.02, 0.6 + k * 0.044, 0.08, jit((140, 150, 120), L, 50))
    c.rect(0.9, 0.3, 0.97, 0.42, (60, 60, 66))  # espresso machine
    for lx in (0.6, 0.76, 0.92):
        c.line([(lx, 0), (lx, 0.16)], (30, 30, 30), 0.003)
        c.glow(lx, 0.18, 0.06, (120, 100, 50), 1.0)
        c.circ(lx, 0.18, 0.016, (255, 236, 180))
    cloth = jit(P.get("cloth", (240, 236, 226)), L, 8)
    _table_set(c, 0.3, 0.8, 1.5, cloth)
    asp = c.H / c.W
    for k in (-1, 1):
        c.ell(0.3 + k * 0.1, 0.795, 0.03 * asp * 1.6, 0.02, (250, 250, 248))
        c.ell(0.3 + k * 0.1, 0.795, 0.02 * asp * 1.6, 0.012, P.get("drink_col", (90, 56, 36)))
    c.ell(0.3, 0.81, 0.04, 0.016, (246, 246, 242))
    c.ell(0.3, 0.807, 0.02, 0.009, (226, 170, 70))


def restaurant(c: Cv, P):
    """Dining room: tables with cloths, plates and glasses, warm lamps."""
    L = c.L
    wall = jit(P.get("wall", (150, 70, 56)), L, 18)
    floor = jit(P.get("floor", (90, 66, 50)), L, 12)
    _room(c, wall, floor, 0.56)
    wood = P.get("wood", False)
    if wood:
        for k in range(16):
            c.rect(k / 16, 0, k / 16 + 0.004, 0.56, shade(wall, 0.8))
    if P.get("tiles"):
        for k in range(20):
            for j in range(3):
                c.rect(k / 20 + 0.003, 0.3 + j * 0.085, (k + 1) / 20 - 0.003, 0.38 + j * 0.085,
                       (236, 240, 246) if (k + j) % 2 else (60, 100, 170))
    for k in range(int(L.integers(1, 4))):  # pictures
        x = L.uniform(0.05, 0.8)
        c.rect(x, 0.12, x + 0.12, 0.3, (60, 46, 30))
        c.rect(x + 0.01, 0.135, x + 0.11, 0.285, jit((170, 180, 170), L, 50))
    if P.get("window", L.random() < 0.5):
        c.rect(0.7, 0.1, 0.96, 0.44, (24, 30, 60) if P.get("evening", True) else (190, 220, 240))
        c.rect(0.827, 0.1, 0.833, 0.44, shade(wall, 0.6))
    cloth = jit(P.get("cloth", (244, 240, 232)), L, 8)
    dish = P.get("dish") or list(FOODS)[int(L.integers(0, len(FOODS)))]
    drink = P.get("drink_col", (130, 30, 50))
    for x, y, s in ((0.18, 0.6, 0.7), (0.52, 0.6, 0.7), (0.86, 0.61, 0.7)):
        _table_set(c, x + L.uniform(-0.03, 0.03), y, s, shade(cloth, 0.85), dish, drink)
    for x in (0.2, 0.5, 0.8):
        c.line([(x, 0), (x, 0.2)], (30, 30, 30), 0.003)
        c.poly([(x - 0.04, 0.26), (x - 0.02, 0.2), (x + 0.02, 0.2), (x + 0.04, 0.26)], P.get("lamp", (200, 150, 60)))
        c.glow(x, 0.3, 0.12, (90, 66, 26), 1.0)
    # foreground table
    c.ell(0.5, 1.0, 0.56, 0.2, cloth)
    asp = c.H / c.W
    for k in (-1, 1):
        px = 0.5 + k * 0.2
        c.ell(px, 0.92, 0.12, 0.05, (250, 250, 248))
        c.ell(px, 0.92, 0.09, 0.036, (238, 238, 234))
        cols = FOODS[dish]
        for _ in range(7):
            c.ell(px + L.uniform(-0.05, 0.05), 0.918 + L.uniform(-0.016, 0.016), 0.02, 0.01, jit(cols[int(L.integers(0, len(cols)))], L, 10))
        _glass(c, px + k * 0.17, 0.9, 1.5, drink)
    c.rect(0.47, 0.83, 0.53, 0.9, (60, 90, 50)) if P.get("bottle", True) else None
    c.rect(0.488, 0.77, 0.512, 0.83, (60, 90, 50)) if P.get("bottle", True) else None
    if asp:
        pass


def bar(c: Cv, P):
    """Dark bar: glowing back shelf of bottles, counter, stools, coloured light."""
    L = c.L
    wall = jit(P.get("wall", (40, 26, 36)), L, 8)
    _room(c, wall, (24, 18, 20), 0.66)
    glowc = P.get("glow") or [(255, 80, 140), (80, 160, 255), (255, 170, 60), (150, 255, 160)][int(L.integers(0, 4))]
    c.rect(0.1, 0.12, 0.9, 0.46, shade(glowc, 0.25))
    for row in range(3):
        y = 0.22 + row * 0.11
        c.rect(0.1, y, 0.9, y + 0.008, (20, 14, 14))
        for k in range(26):
            x = 0.12 + k * 0.03
            h = L.uniform(0.045, 0.08)
            col = jit([(60, 110, 60), (150, 90, 40), (200, 190, 150), (60, 70, 130), (170, 40, 40)][int(L.integers(0, 5))], L, 20)
            c.rect(x, y - h, x + 0.016, y, col)
            c.rect(x + 0.005, y - h - 0.016, x + 0.011, y - h, col)
    c.glow(0.5, 0.28, 0.3, shade(glowc, 0.3), 1.0)
    c.rect(0, 0.6, 1, 0.7, (70, 44, 30))
    c.rect(0, 0.585, 1, 0.61, (130, 90, 56))
    c.rect(0, 0.7, 1, 1.0, (36, 24, 20))
    for k in range(5):
        x = 0.1 + k * 0.2
        c.ell(x, 0.8, 0.045, 0.016, (90, 30, 30))
        c.rect(x - 0.006, 0.8, x + 0.006, 0.98, (120, 120, 126))
    for k in range(int(L.integers(3, 7))):
        _glass(c, L.uniform(0.1, 0.9), 0.6, 0.9, jit((230, 170, 60), L, 40))
    if P.get("stage"):  # fado / live music corner
        c.glow(0.2, 0.4, 0.2, (120, 90, 40), 1.0)
        c.ell(0.2, 0.5, 0.03, 0.05, (16, 12, 12))
        c.rect(0.17, 0.53, 0.23, 0.66, (16, 12, 12))
        c.ell(0.26, 0.58, 0.035, 0.05, (120, 70, 30))
        c.line([(0.26, 0.56), (0.33, 0.44)], (90, 50, 20), 0.008)
    for x in L.uniform(0.05, 0.95, 4):
        c.glow(float(x), L.uniform(0.02, 0.1), 0.05, shade(glowc, 0.5), 1.0)


def museum(c: Cv, P):
    """Gallery: pale wall, framed works (or tile panels), polished floor, bench."""
    L = c.L
    wall = jit(P.get("wall", (232, 230, 224)), L, 8)
    floor = jit(P.get("floor", (150, 120, 90)), L, 10)
    _room(c, wall, floor, 0.68)
    style = P.get("art", "paintings")
    x = L.uniform(0.02, 0.06)
    while x < 0.95:
        w = L.uniform(0.12, 0.26)
        h = L.uniform(0.2, 0.36)
        y = 0.36 - h / 2
        if style == "tiles":
            n, m = max(2, int(w / 0.03)), max(2, int(h / 0.04))
            for i in range(n):
                for j in range(m):
                    col = [(40, 80, 170), (236, 240, 246), (90, 130, 200), (240, 200, 70)][int(L.integers(0, 4))]
                    c.rect(x + i * w / n, y + j * h / m, x + (i + 1) * w / n - 0.002, y + (j + 1) * h / m - 0.003, col)
        elif style == "statues":
            c.rect(x + w * 0.3, 0.5, x + w * 0.7, 0.68, (200, 196, 188))
            c.ell(x + w * 0.5, 0.36, w * 0.14, 0.13, (236, 232, 222))
            c.circ(x + w * 0.5, 0.2, 0.04, (236, 232, 222))
        else:
            fr = P.get("frame", (150, 116, 50))
            c.rect(x, y, x + w, y + h, fr)
            a, b = jit((120, 110, 100), L, 80), jit((120, 110, 100), L, 80)
            c.rect(x + 0.012, y + 0.016, x + w - 0.012, y + h - 0.016, a)
            c.rect(x + 0.012, y + h * 0.55, x + w - 0.012, y + h - 0.016, b)
            if P.get("gold"):
                c.rect(x + 0.012, y + 0.016, x + w - 0.012, y + h - 0.016, (214, 170, 50))
                c.ell(x + w / 2, y + h * 0.5, w * 0.2, h * 0.3, jit((180, 110, 60), L, 30))
            else:
                c.ell(x + w * L.uniform(0.3, 0.7), y + h * L.uniform(0.3, 0.6), w * 0.16, h * 0.16, jit((200, 180, 150), L, 50))
        c.rect(x + w * 0.4, y + h + 0.02, x + w * 0.6, y + h + 0.035, (250, 250, 250))
        c.glow(x + w / 2, y - 0.02, 0.07, (30, 30, 24), 1.0)
        x += w + L.uniform(0.05, 0.1)
    c.reflect(0.69, 1.0, floor, 0.25, 0.002)
    c.rect(0.3, 0.84, 0.7, 0.875, (50, 46, 46))
    c.rect(0.33, 0.875, 0.345, 0.93, (30, 30, 30))
    c.rect(0.655, 0.875, 0.67, 0.93, (30, 30, 30))


def church(c: Cv, P):
    """Dim nave: columns, pointed arches, stained glass, pews."""
    L = c.L
    stone = jit(P.get("stone", (120, 108, 96)), L, 10)
    c.bg([(0, shade(stone, 0.35)), (1, shade(stone, 0.8))], 0, 1.0)
    gold = P.get("gold", False)
    c.pie(0.5, 0.36, 0.14, 0.26, 180, 360, shade(stone, 1.2))
    c.rect(0.36, 0.36, 0.64, 0.7, shade(stone, 1.2))
    cols = [(200, 40, 50), (40, 80, 200), (240, 190, 50), (60, 160, 90), (150, 60, 170)]
    if P.get("dome"):
        c.ell(0.5, 0.1, 0.34, 0.14, mix(stone, (214, 170, 80), 0.5))
        for k in range(12):
            c.circ(0.2 + k * 0.055, 0.14, 0.008, (255, 240, 190))
        c.glow(0.5, 0.12, 0.2, (90, 70, 30), 1.0)
    for k in range(3):
        x = 0.42 + k * 0.08
        c.pie(x, 0.3, 0.025, 0.06, 180, 360, cols[k])
        for j in range(5):
            c.rect(x - 0.025, 0.3 + j * 0.05, x + 0.025, 0.345 + j * 0.05, cols[(k + j) % 5])
        c.glow(x, 0.4, 0.1, shade(cols[k], 0.25), 1.0)
    if gold:
        c.rect(0.4, 0.5, 0.6, 0.7, (214, 170, 60))
        c.glow(0.5, 0.6, 0.16, (90, 66, 10), 1.0)
    for k in range(4):
        t = k / 4
        for side in (-1, 1):
            x = 0.5 + side * (0.46 - 0.26 * t)
            w = 0.04 * (1 - t * 0.6)
            c.rect(x - w, 0.0, x + w, 0.96 - 0.22 * t, shade(stone, 1.0 - 0.12 * k))
            c.rect(x - w * 1.3, 0.94 - 0.22 * t, x + w * 1.3, 0.98 - 0.22 * t, shade(stone, 0.7))
        c.arc(0.5, 0.2 + 0.04 * k, 0.46 - 0.26 * t, 0.2 - 0.03 * k, 180, 360, shade(stone, 0.9), 0.012)
    c.poly([(0.42, 1.0), (0.47, 0.7), (0.53, 0.7), (0.58, 1.0)], (130, 40, 40) if not P.get("carpet") else P["carpet"])
    for k in range(5):
        y = 0.76 + k * 0.05
        s = 0.5 + k * 0.14
        for side in (-1, 1):
            c.rect(0.5 + side * 0.07 * s, y, 0.5 + side * 0.5 * s, y + 0.03, (64, 44, 30))
    for x in (0.3, 0.7):
        c.glow(x, 0.56, 0.05, (120, 90, 40), 1.0)


def hotel_room(c: Cv, P):
    L = c.L
    wall = jit(P.get("wall", (226, 220, 210)), L, 14)
    _room(c, wall, jit((150, 130, 110), L, 14), 0.66)
    wood = P.get("wood", False)
    if wood:
        for k in range(14):
            c.rect(k / 14, 0, k / 14 + 0.004, 0.66, shade(wall, 0.85))
    c.rect(0.06, 0.1, 0.3, 0.52, (176, 212, 236) if not P.get("evening") else (30, 36, 70))
    c.rect(0.02, 0.06, 0.08, 0.64, jit((150, 90, 70), L, 30))
    c.rect(0.28, 0.06, 0.34, 0.64, jit((150, 90, 70), L, 30))
    bed = jit(P.get("bed", (240, 240, 244)), L, 6)
    c.rect(0.4, 0.34, 0.96, 0.56, (90, 66, 50))
    c.poly([(0.36, 0.9), (0.42, 0.56), (0.96, 0.56), (1.0, 0.9)], bed)
    c.rect(0.36, 0.9, 1.0, 1.0, shade(bed, 0.8))
    c.poly([(0.38, 0.9), (0.41, 0.74), (0.97, 0.74), (1.0, 0.9)], jit(P.get("throw", (70, 100, 140)), L, 30))
    for x in (0.52, 0.76):
        c.ell(x, 0.57, 0.1, 0.035, (250, 250, 252))
    c.rect(0.34, 0.5, 0.4, 0.66, (110, 80, 60))
    c.poly([(0.345, 0.44), (0.355, 0.38), (0.385, 0.38), (0.395, 0.44)], (240, 220, 170))
    c.glow(0.37, 0.42, 0.1, (90, 70, 30), 1.0)
    if P.get("bunks"):
        c.rect(0.4, 0.14, 0.96, 0.17, (110, 80, 50))
        c.rect(0.4, 0.17, 0.96, 0.24, (200, 60, 50))
    c.rect(0.1, 0.8, 0.26, 0.94, jit((40, 60, 90), L, 40))  # bag
    c.rect(0.15, 0.77, 0.21, 0.8, (30, 30, 30))


def hut_interior(c: Cv, P):
    """Wood-panelled hut dining room with long benches."""
    P = dict(P)
    P.setdefault("wall", (170, 120, 70))
    P.setdefault("floor", (110, 80, 50))
    P.setdefault("cloth", (200, 60, 50))
    P.setdefault("wood", True)
    P.setdefault("drink_col", (236, 190, 60))
    P.setdefault("lamp", (230, 200, 120))
    P.setdefault("evening", False)
    P.setdefault("window", True)
    restaurant(c, P)


def market_hall(c: Cv, P):
    """Food hall: iron roof, rows of counters with signs, communal tables."""
    L = c.L
    c.bg([(0, (60, 64, 70)), (1, (190, 186, 176))], 0, 0.4)
    for k in range(11):
        x = k / 10
        c.line([(x, 0), (0.5 + (x - 0.5) * 0.4, 0.3)], (40, 44, 50), 0.006)
    for k in range(4):
        c.line([(0, 0.07 * k + 0.02), (1, 0.07 * k + 0.02)], (40, 44, 50), 0.004)
    c.glow(0.5, 0.05, 0.3, (80, 80, 70), 1.0)
    c.bg([(0, (120, 112, 104)), (1, (84, 78, 72))], 0.4, 1.0)
    cols = [(20, 20, 24), (200, 50, 40), (240, 190, 50), (40, 110, 90), (230, 230, 226)]
    x = 0.0
    while x < 1.0:
        w = L.uniform(0.14, 0.22)
        sc = cols[int(L.integers(0, len(cols)))]
        c.rect(x, 0.24, x + w - 0.01, 0.31, sc)
        c.rect(x + 0.02, 0.262, x + w * 0.7, 0.285, (250, 250, 250) if sum(sc) < 400 else (20, 20, 20))
        c.rect(x, 0.31, x + w - 0.01, 0.42, (236, 226, 200))
        c.glow(x + w / 2, 0.36, 0.06, (70, 56, 20), 1.0)
        c.rect(x, 0.42, x + w - 0.01, 0.52, jit((70, 60, 56), L, 10))
        for _ in range(6):
            c.circ(x + L.uniform(0.02, w - 0.03), 0.41, 0.012, jit((220, 150, 70), L, 50))
        x += w
    for row in range(2):
        y = 0.66 + row * 0.2
        s = 1 + row * 0.5
        c.poly([(0.08 / s, y), (1 - 0.08 / s, y), (1 - 0.04 / s, y + 0.07 * s), (0.04 / s, y + 0.07 * s)], (190, 150, 100))
        for k in range(int(6 + row * 2)):
            px = 0.14 + k * (0.75 / (5 + row * 2))
            c.ell(px, y + 0.03 * s, 0.035 * s, 0.012 * s, (248, 248, 244))
            c.ell(px, y + 0.028 * s, 0.02 * s, 0.007 * s, jit((200, 120, 60), L, 60))
            _glass(c, px + 0.04 * s, y + 0.025 * s, 0.5 * s, jit((230, 180, 60), L, 30))


def terminal(c: Cv, P):
    """Airport / concourse hall: glass wall, departure board, barriers."""
    L = c.L
    c.bg([(0, (236, 238, 240)), (1, (206, 210, 214))], 0, 0.6)
    for k in range(13):
        c.line([(k / 12, 0), (k / 12, 0.6)], (150, 156, 164), 0.004)
    c.rect(0, 0.16, 1, 0.5, (170, 206, 232))
    for k in range(9):
        c.rect(k / 8 - 0.006, 0.16, k / 8 + 0.006, 0.5, (236, 238, 240))
    c.bg([(0, (196, 196, 200)), (1, (150, 150, 156))], 0.6, 1.0)
    c.reflect(0.6, 1.0, (170, 170, 176), 0.3, 0.002)
    bx = L.uniform(0.1, 0.5)
    c.rect(bx, 0.06, bx + 0.4, 0.3, (16, 18, 24))
    for j in range(7):
        c.rect(bx + 0.015, 0.08 + j * 0.03, bx + 0.1, 0.095 + j * 0.03, (250, 210, 60))
        c.rect(bx + 0.12, 0.08 + j * 0.03, bx + 0.26 + L.uniform(-0.04, 0.04), 0.095 + j * 0.03, (240, 240, 240))
        c.rect(bx + 0.33, 0.08 + j * 0.03, bx + 0.38, 0.095 + j * 0.03, (90, 220, 110) if L.random() < 0.7 else (240, 80, 60))
    sc = P.get("sign_col", (250, 200, 40))
    c.rect(0.66, 0.34, 0.94, 0.42, sc)
    c.rect(0.68, 0.36, 0.72, 0.4, (20, 20, 20))
    c.rect(0.74, 0.365, 0.9, 0.39, (20, 20, 20))
    for k in range(5):
        x = 0.1 + k * 0.2
        c.rect(x - 0.006, 0.7, x + 0.006, 0.86, (60, 60, 66))
        if k < 4:
            c.rect(x, 0.72, x + 0.2, 0.74, (30, 60, 140))
    c.rect(0.74, 0.76, 0.84, 0.94, jit((190, 60, 50), L, 50))
    c.rect(0.78, 0.68, 0.8, 0.76, (40, 40, 40))


def train_interior(c: Cv, P):
    """Night-train compartment / carriage interior with a dark window."""
    L = c.L
    wall = jit(P.get("wall", (190, 180, 160)), L, 10)
    c.bg([(0, shade(wall, 0.9)), (1, wall)], 0, 1.0)
    dark = P.get("window", (10, 14, 34))
    c.rect(0.3, 0.14, 0.7, 0.56, (50, 50, 56))
    c.rect(0.32, 0.165, 0.68, 0.535, dark)
    if sum(dark) < 120:
        for _ in range(7):
            x = L.uniform(0.34, 0.66)
            c.glow(x, L.uniform(0.3, 0.5), 0.015, (200, 170, 90), 1.0)
        c.hblur(5, 0.17, 0.53)
        c.rect(0.0, 0.14, 0.3, 0.56, wall)
        c.rect(0.7, 0.14, 1.0, 0.56, wall)
        c.rect(0.3, 0.14, 0.32, 0.56, (50, 50, 56))
        c.rect(0.68, 0.14, 0.7, 0.56, (50, 50, 56))
    seat = jit(P.get("seat", (40, 70, 130)), L, 20)
    for side in (0, 1):
        x0, x1 = (0.0, 0.27) if side == 0 else (0.73, 1.0)
        c.rect(x0, 0.3, x1, 0.74, seat)
        c.rect(x0, 0.74, x1, 0.86, shade(seat, 0.8))
        c.rect(x0, 0.24, x1, 0.31, shade(seat, 1.2))
        if P.get("bunks", True):
            c.rect(x0, 0.04, x1, 0.12, (236, 236, 240))
            c.rect(x0, 0.12, x1, 0.14, shade(wall, 0.6))
    c.rect(0.36, 0.6, 0.64, 0.63, (120, 100, 80))
    c.rect(0.49, 0.63, 0.51, 0.86, (80, 80, 84))
    c.ell(0.44, 0.595, 0.02, 0.012, (250, 250, 250))
    c.rect(0.54, 0.54, 0.565, 0.6, (60, 110, 70))
    c.bg([(0, (70, 66, 70)), (1, (50, 46, 50))], 0.86, 1.0)
    c.glow(0.5, 0.05, 0.2, (70, 64, 40), 1.0)
