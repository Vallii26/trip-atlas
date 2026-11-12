"""Contact sheets for eyeballing rendered scenes / generated trips."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def sheet(images: list[Image.Image], cols: int, cell=(320, 240), pad=4) -> Image.Image:
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * (cell[0] + pad) + pad, rows * (cell[1] + pad) + pad), (24, 24, 24))
    for i, im in enumerate(images):
        t = im.convert("RGB").copy()
        t.thumbnail(cell)
        x = pad + (i % cols) * (cell[0] + pad) + (cell[0] - t.width) // 2
        y = pad + (i // cols) * (cell[1] + pad) + (cell[1] - t.height) // 2
        out.paste(t, (x, y))
    return out


def scene_sheet(out: Path, scenes: list[str] | None = None, variants: int = 2, w=800, h=600) -> None:
    from .scenes import SCENES, render_photo

    ims = []
    for s in scenes or list(SCENES):
        for v in range(variants):
            ims.append(render_photo(s, {}, 1000 + v * 77 + len(s), v, w, h))
    sheet(ims, 6).save(out)
