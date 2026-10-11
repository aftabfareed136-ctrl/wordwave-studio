"""Look presets — AE "looks" library: animated backgrounds + accent palettes.

Each preset is a painter: paint(img, draw, t, w, h, seed). Backgrounds are
fully procedural (no stock needed): gradients, perspective grids, drifting
glow orbs and seeded particles — all deterministic per frame.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .timeline import Layer


@lru_cache(maxsize=32)
def _vgradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top_a = np.array(top, dtype=np.float32)[None, None, :]
    bot_a = np.array(bottom, dtype=np.float32)[None, None, :]
    arr = (top_a * (1 - t) + bot_a * t).astype(np.uint8)
    arr = np.repeat(arr, w, axis=1)
    return Image.fromarray(arr, "RGB")


@lru_cache(maxsize=64)
def _radial_glow(w: int, h: int, cx: int, cy: int, radius: int,
                 color: tuple, strength: float = 1.0) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max(radius, 1)
    m = np.clip(1 - d, 0, 1) ** 2 * strength
    arr = np.zeros((h, w, 3), np.uint8)
    for c in range(3):
        arr[:, :, c] = (m * color[c]).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _grid(draw: ImageDraw.ImageDraw, w: int, h: int, t: float,
          color: tuple, alpha: int, horizon: float = 0.52,
          speed: float = 60.0, spacing: int = 90):
    """Perspective floor grid scrolling toward the viewer (synthwave floor)."""
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    hy = int(h * horizon)
    # horizontal lines: exponential spacing, scrolling
    phase = (t * speed) % 1.0
    for i in range(14):
        z = ((i + phase) / 14.0) ** 2.2
        y = hy + int((h - hy) * z)
        a = int(alpha * z)
        d.line([(0, y), (w, y)], fill=color + (a,), width=max(1, int(1 + 3 * z)))
    # vertical rays fanning from horizon center
    for k in range(-8, 9):
        x_top = w / 2 + k * spacing * 0.35
        x_bot = w / 2 + k * spacing * 2.4
        d.line([(x_top, hy), (x_bot, h)], fill=color + (alpha // 3,), width=2)
    d.line([(0, hy), (w, hy)], fill=color + (alpha,), width=3)
    return ov


def _particles(w: int, h: int, t: float, n: int, seed: int,
               colors: list[tuple], size_range=(2, 7), rise: bool = False,
               drift: float = 20.0) -> Image.Image:
    # render at half res, then upscale: identical look, ~4x faster blur
    sw, sh = w // 2, h // 2
    rng = random.Random(seed)
    pts = [(rng.uniform(0, sw), rng.uniform(0, sh), rng.choice(colors),
            rng.uniform(*size_range), rng.uniform(0.2, 1.0), rng.uniform(0, 6.28))
           for _ in range(n)]
    ov = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x, y, col, sz, spd, ph in pts:
        if rise:
            yy = (y - t * 60 * spd) % (sh + 40) - 20
            xx = x + math.sin(t * 0.8 + ph) * drift / 2
        else:
            xx = x + math.sin(t * spd + ph) * drift / 2
            yy = y + math.cos(t * spd * 0.7 + ph) * drift * 0.3
        tw = 0.55 + 0.45 * math.sin(t * 2.2 * spd + ph)
        d.ellipse([xx - sz, yy - sz, xx + sz, yy + sz],
                  fill=col + (int(150 * tw),))
    return ov.filter(ImageFilter.GaussianBlur(1)).resize((w, h), Image.BICUBIC)


def _glow_paste(img: Image.Image, w: int, h: int, cx: float, cy: float,
                radius: float, color: tuple, strength: float):
    """Paste a cached radial glow (coords quantized for cache hits)."""
    glow = _radial_glow(w, h, int(cx), int(cy), int(radius), color, round(strength, 2))
    img.paste(glow, (0, 0), glow.convert("L"))


def _vignette(w: int, h: int, strength: float = 0.55) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
    m = (1 - np.clip(d, 0, 1) ** 2 * strength)
    arr = (m * 255).astype(np.uint8)
    return Image.fromarray(arr, "L")


def paint_cyberpunk(img: Image.Image, draw: ImageDraw.ImageDraw, t: float, w: int, h: int):
    img.paste(_vgradient(w, h, (14, 0, 26), (52, 2, 44)), (0, 0))
    _glow_paste(img, w, h, w * 0.5, h * 0.38, w * 0.75, (255, 45, 149), 0.35)
    grid = _grid(draw, w, h, t, (255, 45, 149), 90, speed=46.0)
    img.alpha_composite(grid.convert("RGBA"))
    parts = _particles(w, h, t, 42, 7, [(255, 45, 149), (0, 229, 255), (255, 120, 200)], (2, 6))
    img.alpha_composite(parts)


def paint_neon(img: Image.Image, draw: ImageDraw.ImageDraw, t: float, w: int, h: int):
    img.paste(_vgradient(w, h, (2, 6, 23), (10, 14, 52)), (0, 0))
    for i, (fx, fy, col) in enumerate([(0.25, 0.3, (0, 229, 255)), (0.75, 0.65, (150, 80, 255))]):
        cx = w * (fx + 0.06 * math.sin(t * 0.4 + i * 2.4))
        cy = h * (fy + 0.05 * math.cos(t * 0.33 + i * 1.7))
        _glow_paste(img, w, h, cx, cy, w * 0.55, col, 0.30)
    grid = _grid(draw, w, h, t, (0, 229, 255), 70, speed=38.0)
    img.alpha_composite(grid.convert("RGBA"))
    img.alpha_composite(_particles(w, h, t, 36, 21, [(0, 229, 255), (150, 120, 255)], (2, 5)))


def paint_ember(img: Image.Image, draw: ImageDraw.ImageDraw, t: float, w: int, h: int):
    img.paste(_vgradient(w, h, (22, 8, 0), (66, 26, 2)), (0, 0))
    _glow_paste(img, w, h, w * 0.5, h * 0.9, w * 0.8, (255, 122, 26), 0.4)
    img.alpha_composite(_particles(w, h, t, 55, 99, [(255, 140, 40), (255, 200, 90), (255, 90, 20)],
                                   (2, 7), rise=True, drift=34.0))


def paint_minimal(img: Image.Image, draw: ImageDraw.ImageDraw, t: float, w: int, h: int):
    img.paste(_vgradient(w, h, (10, 10, 14), (18, 18, 26)), (0, 0))
    _glow_paste(img, w, h, w * 0.5, h * 0.30, w * 0.7, (124, 92, 255), 0.22)
    img.alpha_composite(_particles(w, h, t, 24, 5, [(160, 160, 190)], (1, 3)))


BACKGROUNDS = {
    "cyberpunk": dict(paint=paint_cyberpunk, accent=(255, 45, 149), accent2=(255, 214, 64)),
    "neon":      dict(paint=paint_neon,      accent=(0, 229, 255),   accent2=(255, 214, 64)),
    "ember":     dict(paint=paint_ember,     accent=(255, 122, 26),  accent2=(255, 236, 170)),
    "minimal":   dict(paint=paint_minimal,   accent=(124, 92, 255),  accent2=(255, 255, 255)),
}


class BackgroundLayer(Layer):
    """Procedural animated background (the 'look')."""

    def __init__(self, preset: str = "cyberpunk", name: str = "background"):
        super().__init__(name)
        if preset not in BACKGROUNDS:
            raise ValueError(f"Unknown background '{preset}'. Choose from {sorted(BACKGROUNDS)}")
        self.preset = preset
        self.paint = BACKGROUNDS[preset]["paint"]
        self._vig = None

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, t: float, ctx: dict):
        w, h = img.size
        self.paint(img, draw, t, w, h)
        if self._vig is None or self._vig.size != (w, h):
            self._vig = _vignette(w, h)
        img.paste(Image.new("RGB", (w, h), (0, 0, 0)), (0, 0),
                  self._vig.point(lambda v: 255 - v))
