"""Small drawing toolkit used by the scene painters (normalised coordinates on a PIL canvas)."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def jit(col, L, amt=12):
    return tuple(int(min(255, max(0, col[i] + L.integers(-amt, amt + 1)))) for i in range(3))


def shade(col, f):
    return tuple(int(min(255, max(0, c * f))) for c in col)


def gradient(w: int, h: int, stops) -> Image.Image:
    """Vertical gradient; ``stops`` = [(pos 0..1, (r,g,b)), ...]."""
    ys = np.linspace(0.0, 1.0, h)
    pos = [p for p, _ in stops]
    cols = np.stack([np.interp(ys, pos, [c[i] for _, c in stops]) for i in range(3)], axis=1)
    arr = np.repeat(cols[:, None, :], w, axis=1)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


class Cv:
    """Canvas with a layout RNG ``L`` (same for every photo of a moment+scene)."""

    def __init__(self, W: int, H: int, L: np.random.Generator):
        self.W, self.H, self.L = W, H, L
        self.im = Image.new("RGB", (W, H), (0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    # -- coordinates ---------------------------------------------------------------------
    def X(self, x):
        return int(round(x * self.W))

    def Y(self, y):
        return int(round(y * self.H))

    def _redraw(self):
        self.d = ImageDraw.Draw(self.im)

    # -- primitives ----------------------------------------------------------------------
    def bg(self, stops, y0=0.0, y1=1.0):
        h = max(1, self.Y(y1) - self.Y(y0))
        self.im.paste(gradient(self.W, h, stops), (0, self.Y(y0)))
        self._redraw()

    def rect(self, x0, y0, x1, y1, fill, outline=None):
        a, b, c, e = self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)
        if c < a:
            a, c = c, a
        if e < b:
            b, e = e, b
        self.d.rectangle([a, b, c, e], fill=fill, outline=outline)

    def poly(self, pts, fill):
        self.d.polygon([(self.X(x), self.Y(y)) for x, y in pts], fill=fill)

    def ell(self, cx, cy, rx, ry, fill, outline=None, width=1):
        self.d.ellipse([self.X(cx - rx), self.Y(cy - ry), self.X(cx + rx), self.Y(cy + ry)],
                       fill=fill, outline=outline, width=max(1, width))

    def circ(self, cx, cy, r, fill, outline=None, width=1):
        """Circle with radius ``r`` relative to canvas height."""
        rp = r * self.H
        x, y = cx * self.W, cy * self.H
        self.d.ellipse([x - rp, y - rp, x + rp, y + rp], fill=fill, outline=outline, width=max(1, width))

    def line(self, pts, fill, w=0.004):
        self.d.line([(self.X(x), self.Y(y)) for x, y in pts], fill=fill, width=max(1, int(w * self.H)))

    def arc(self, cx, cy, rx, ry, a0, a1, fill, w=0.006):
        self.d.arc([self.X(cx - rx), self.Y(cy - ry), self.X(cx + rx), self.Y(cy + ry)], a0, a1,
                   fill=fill, width=max(1, int(w * self.H)))

    def pie(self, cx, cy, rx, ry, a0, a1, fill):
        self.d.pieslice([self.X(cx - rx), self.Y(cy - ry), self.X(cx + rx), self.Y(cy + ry)], a0, a1, fill=fill)

    # -- effects -------------------------------------------------------------------------
    def glow(self, cx, cy, r, color, strength=1.0):
        """Additive soft light blob (sun, lamp, window light). ``r`` relative to height."""
        rp = max(2.0, r * self.H)
        x, y = cx * self.W, cy * self.H
        x0, y0 = int(max(0, x - 3 * rp)), int(max(0, y - 3 * rp))
        x1, y1 = int(min(self.W, x + 3 * rp)), int(min(self.H, y + 3 * rp))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d2 = ((xx - x) ** 2 + (yy - y) ** 2) / (rp * rp)
        a = (np.exp(-d2 * 1.2) * strength)[..., None]
        box = np.asarray(self.im.crop((x0, y0, x1, y1)), dtype=np.float32)
        box = box + a * np.array(color, dtype=np.float32)
        self.im.paste(Image.fromarray(np.clip(box, 0, 255).astype(np.uint8), "RGB"), (x0, y0))
        self._redraw()

    def blur(self, r, box=None):
        rp = max(0.5, r * self.H)
        if box is None:
            self.im = self.im.filter(ImageFilter.GaussianBlur(rp))
        else:
            b = (self.X(box[0]), self.Y(box[1]), self.X(box[2]), self.Y(box[3]))
            self.im.paste(self.im.crop(b).filter(ImageFilter.GaussianBlur(rp)), b[:2])
        self._redraw()

    def hblur(self, factor, y0=0.0, y1=1.0):
        """Horizontal motion blur of a band."""
        b = (0, self.Y(y0), self.W, self.Y(y1))
        reg = self.im.crop(b)
        small = reg.resize((max(2, int(self.W / factor)), reg.height), Image.BILINEAR)
        self.im.paste(small.resize(reg.size, Image.BILINEAR), b[:2])
        self._redraw()

    def darken(self, f, y0=0.0, y1=1.0):
        b = (0, self.Y(y0), self.W, self.Y(y1))
        arr = np.asarray(self.im.crop(b), dtype=np.float32) * f
        self.im.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), b[:2])
        self._redraw()

    def reflect(self, y_h, y1, tint=(40, 70, 100), strength=0.55, ripple=0.004):
        """Mirror what is above ``y_h`` into the band y_h..y1, tinted and rippled (water)."""
        yh, ye = self.Y(y_h), self.Y(y1)
        h = ye - yh
        if h <= 2:
            return
        src = np.asarray(self.im.crop((0, max(0, yh - h), self.W, yh)), dtype=np.float32)[::-1]
        if src.shape[0] < h:
            src = np.concatenate([src, np.repeat(src[-1:], h - src.shape[0], axis=0)], axis=0)
        rows = np.arange(h)
        shift = (np.sin(rows * 0.9 + self.L.uniform(0, 6)) * ripple * self.W * (0.3 + rows / h)).astype(int)
        out = np.empty_like(src)
        for i in range(h):
            out[i] = np.roll(src[i], shift[i], axis=0)
        t = np.array(tint, dtype=np.float32)
        depth = (rows / h)[:, None, None]
        out = out * (strength * (1 - 0.35 * depth)) + t * (1 - strength * (1 - 0.35 * depth))
        self.im.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), (0, yh))
        self._redraw()

    def speckle(self, x0, y0, x1, y1, n, cols, r=0.004):
        L = self.L
        xs = L.uniform(x0, x1, n)
        ys = L.uniform(y0, y1, n)
        ci = L.integers(0, len(cols), n)
        for x, y, k in zip(xs, ys, ci):
            self.circ(float(x), float(y), r, cols[int(k)])


def ridge_profile(L, n=64, rough=0.5):
    """Mountain-ish profile in 0..1 (n samples), sum of random sines plus jaggedness."""
    x = np.linspace(0, 1, n)
    y = np.zeros(n)
    for k in range(1, 6):
        y += L.uniform(0.3, 1.0) / k * np.sin(2 * math.pi * (k * L.uniform(0.5, 1.5) * x + L.uniform(0, 1)))
    y += rough * L.normal(0, 0.12, n)
    y -= y.min()
    return y / (y.max() or 1.0)
