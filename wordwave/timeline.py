"""After-Effects-style composition model.

    Composition  = canvas (w, h, fps) + ordered layers
    Layer        = in/out points + opacity track + render()
    Keyframe     = (time, value, easing)
    Track        = interpolates keyframes -> value(t)

KineticTextLayer is the star: it takes timed words and an *animator preset*
(AE "text animator" equivalent: per-word scale/position/opacity/rotation with
staggered timing) and draws word-by-word kinetic typography.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from . import easing

# ---------------------------------------------------------------- fonts

_FONT_DIRS = [
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
]


def _find_font(bold: bool) -> str:
    wants = ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold else \
            ["NotoSans-Regular.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    for d in _FONT_DIRS:
        for w in wants:
            p = os.path.join(d, w)
            if os.path.exists(p):
                return p
    raise RuntimeError("No system font found")


BOLD_FONT = _find_font(True)
REG_FONT = _find_font(False)

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    key = (BOLD_FONT if bold else REG_FONT, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(key[0], size)
    return _font_cache[key]


# ---------------------------------------------------------------- keyframes

@dataclass
class Keyframe:
    time: float
    value: float
    ease: str = "linear"


class Track:
    """Piecewise interpolation between keyframes (like an AE property)."""

    def __init__(self, keyframes: list[Keyframe] | None = None, default: float = 0.0):
        self.keyframes = sorted(keyframes or [], key=lambda k: k.time)
        self.default = default

    def value(self, t: float) -> float:
        kf = self.keyframes
        if not kf:
            return self.default
        if t <= kf[0].time:
            return kf[0].value
        if t >= kf[-1].time:
            return kf[-1].value
        for a, b in zip(kf, kf[1:]):
            if a.time <= t < b.time:
                span = b.time - a.time
                x = (t - a.time) / span if span > 0 else 1.0
                e = easing.get(b.ease)
                return a.value + (b.value - a.value) * e(x)
        return kf[-1].value


# ---------------------------------------------------------------- layers

@dataclass
class ScoredWord:
    text: str
    start: float
    end: float
    keyword: bool = False


@dataclass
class SceneTake:
    words: list[ScoredWord]
    title: bool = False
    start: float = 0.0   # first word visible (lead-in applied)
    end: float = 0.0     # hold-out end


class Layer:
    def __init__(self, name: str, in_point: float = 0.0, out_point: float = float("inf")):
        self.name = name
        self.in_point = in_point
        self.out_point = out_point
        self.opacity = Track(default=1.0)

    def active(self, t: float) -> bool:
        return self.in_point <= t < self.out_point

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, t: float, ctx: dict):
        raise NotImplementedError


# ---------------------------------------------------------------- text animators (AE "text animator" presets)

# Each animator: how a word enters (dur/lead/ease/from-state) + how the
# currently-spoken word is treated. `mode` selects the draw path.
TEXT_ANIMATORS = {
    "pop":      dict(mode="scale", ease="back",    dur=0.34, lead=0.08, scale_from=0.15, dy_from=54,  rot_from=0),
    "rise":     dict(mode="scale", ease="out-expo", dur=0.42, lead=0.10, scale_from=0.85, dy_from=110, rot_from=0),
    "drop":     dict(mode="scale", ease="bounce",  dur=0.55, lead=0.06, scale_from=1.6,  dy_from=-160, rot_from=0),
    "elastic":  dict(mode="scale", ease="elastic", dur=0.70, lead=0.08, scale_from=0.10, dy_from=30,  rot_from=0),
    "swing":    dict(mode="scale", ease="out-expo", dur=0.45, lead=0.08, scale_from=0.6,  dy_from=40,  rot_from=-14),
    "karaoke":  dict(mode="karaoke", ease="linear", dur=0.30, lead=0.10, scale_from=1.0,  dy_from=0,   rot_from=0),
    "typewriter": dict(mode="typewriter", ease="linear", dur=0.30, lead=0.05, scale_from=1.0, dy_from=0, rot_from=0),
}


class KineticTextLayer(Layer):
    """Word-by-word kinetic typography layer."""

    def __init__(self, scenes: list[SceneTake], animator: str = "pop",
                 accent=(255, 45, 149), accent2=(255, 214, 64), name: str = "kinetic-text"):
        super().__init__(name)
        if animator not in TEXT_ANIMATORS:
            raise ValueError(f"Unknown animator '{animator}'. Choose from {sorted(TEXT_ANIMATORS)}")
        self.scenes = scenes
        self.anim = TEXT_ANIMATORS[animator]
        self.animator_name = animator
        self.accent = accent
        self.accent2 = accent2
        self._layout_cache: dict[int, dict] = {}
        self._word_cache: dict[tuple[str, int, tuple], Image.Image] = {}

    # -- layout -------------------------------------------------------
    def _layout(self, scene_idx: int, w: int, h: int) -> dict:
        if scene_idx in self._layout_cache:
            return self._layout_cache[scene_idx]
        scene = self.scenes[scene_idx]
        margin_x = int(w * 0.08)
        max_w = w - 2 * margin_x
        max_h = int(h * (0.60 if scene.title else 0.52))
        size = 150 if scene.title else 108
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        while size > 28:
            fnt = font(True, size)
            lines: list[list[tuple[str, int, int]]] = []  # (text, w, h)
            cur: list[tuple[str, int, int]] = []
            cur_w = 0
            space_w = probe.textlength(" ", font=fnt)
            for wd in scene.words:
                bb = probe.textbbox((0, 0), wd.text, font=fnt)
                ww, wh = bb[2] - bb[0], bb[3] - bb[1]
                if cur and cur_w + space_w + ww > max_w:
                    lines.append(cur)
                    cur, cur_w = [], 0
                cur.append((wd.text, ww, wh))
                cur_w += (space_w if cur_w else 0) + ww
            if cur:
                lines.append(cur)
            line_h = int(size * 1.32)
            total_h = line_h * len(lines)
            widest = max((sum(ww for _, ww, _ in ln) + space_w * (len(ln) - 1)) for ln in lines)
            if total_h <= max_h and widest <= max_w:
                break
            size -= 6
        fnt = font(True, size)
        space_w = probe.textlength(" ", font=fnt)
        line_h = int(size * 1.32)
        total_h = line_h * len(lines)
        y0 = int(h * 0.44) - total_h // 2
        # word images (cached base render for scaling)
        items = []
        y = y0
        for ln in lines:
            lw = sum(ww for _, ww, _ in ln) + space_w * (len(ln) - 1)
            x = (w - lw) / 2
            for j, (txt, ww, wh) in enumerate(ln):
                items.append(dict(text=txt, cx=x + ww / 2, cy=y + line_h / 2,
                                  w=ww, h=wh, size=size))
                x += ww + space_w
            y += line_h
        # attach timing/keyword
        for item, wd in zip(items, scene.words):
            item.update(start=wd.start, end=wd.end, keyword=wd.keyword)
        layout = dict(items=items, size=size, line_h=line_h)
        self._layout_cache[scene_idx] = layout
        return layout

    def _scene_at(self, t: float) -> int | None:
        best = None
        for i, s in enumerate(self.scenes):
            if s.start <= t:
                best = i
            else:
                break
        if best is None:
            return None
        return best if t < self.scenes[best].end else None

    # -- per-word drawing ---------------------------------------------
    def _word_image(self, text: str, size: int, color: tuple) -> Image.Image:
        key = (text, size, color)
        hit = self._word_cache.get(key)
        if hit is not None:
            return hit
        fnt = font(True, size)
        bb = fnt.getbbox(text)
        pad = size // 3 + 8
        img = Image.new("RGBA", (bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((pad - bb[0], pad - bb[1]), text, font=fnt, fill=color + (255,))
        self._word_cache[key] = img
        return img

    def _paste_word(self, img: Image.Image, base: Image.Image, cx: float, cy: float,
                    scale: float, alpha: float, rot: float = 0.0):
        if alpha <= 0.01 or scale <= 0.01:
            return
        w0, h0 = base.size
        nw, nh = max(1, int(w0 * scale)), max(1, int(h0 * scale))
        wimg = base.resize((nw, nh), Image.BICUBIC)
        if abs(rot) > 0.5:
            wimg = wimg.rotate(rot, expand=True, resample=Image.BICUBIC)
        a = wimg.split()[3].point(lambda v: int(v * min(1.0, alpha)))
        wimg.putalpha(a)
        img.alpha_composite(wimg, (int(cx - wimg.width / 2), int(cy - wimg.height / 2)))

    def _glow(self, img: Image.Image, base: Image.Image, cx: float, cy: float,
              scale: float, color: tuple, alpha: float = 0.55):
        w0, h0 = base.size
        # colorize: build solid-color image from the word's alpha mask
        mask = base.split()[3].resize((max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.BICUBIC)
        solid = Image.new("RGBA", mask.size, color + (0,))
        solid.putalpha(mask.point(lambda v: int(v * alpha)))
        solid = solid.filter(ImageFilter.GaussianBlur(14))
        img.alpha_composite(solid, (int(cx - solid.width / 2), int(cy - solid.height / 2)))

    # -- main render ----------------------------------------------------
    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, t: float, ctx: dict):
        si = self._scene_at(t)
        if si is None:
            return
        scene = self.scenes[si]
        w, h = img.size
        lay = self._layout(si, w, h)
        A = self.anim
        mode = A["mode"]
        ease = easing.get(A["ease"])

        # scene fade in/out
        fade = min(1.0, (t - scene.start) / 0.12 if t > scene.start else 0.0,
                   (scene.end - t) / 0.20 if t < scene.end else 0.0)
        fade = max(0.0, min(1.0, fade))

        # find current word
        cur_idx = None
        for k, it in enumerate(lay["items"]):
            if it["start"] <= t < it["end"]:
                cur_idx = k
                break

        for k, it in enumerate(lay["items"]):
            s, e = it["start"], it["end"]
            local = (t - (s - A["lead"])) / A["dur"]
            p = easing.clamp01(local)
            entered = p >= 1.0
            is_cur = (k == cur_idx)

            if mode == "typewriter":
                self._draw_typewriter(img, it, t, s, e, fade, is_cur)
                continue
            if mode == "karaoke":
                self._draw_karaoke(img, it, t, s, e, fade, is_cur, p)
                continue

            if p <= 0:
                continue
            ep = ease(p)
            scale = A["scale_from"] + (1.0 - A["scale_from"]) * ep
            dy = A["dy_from"] * (1.0 - ep)
            rot = A["rot_from"] * (1.0 - ep)
            alpha = p * fade
            if is_cur:
                scale *= 1.10

            color = (255, 255, 255)
            if it["keyword"]:
                color = self.accent2
            base = self._word_image(it["text"], it["size"], color)
            if is_cur and not it["keyword"]:
                # pill highlight + glow behind the spoken word
                self._glow(img, base, it["cx"], it["cy"] + dy, scale, self.accent, 0.6)
                pill = Image.new("RGBA", img.size, (0, 0, 0, 0))
                pd = ImageDraw.Draw(pill)
                pw, ph = base.width * scale, base.height * scale
                pd.rounded_rectangle(
                    [it["cx"] - pw / 2 - 18, it["cy"] + dy - ph / 2 - 10,
                     it["cx"] + pw / 2 + 18, it["cy"] + dy + ph / 2 + 10],
                    radius=26, fill=self.accent + (110,))
                img.alpha_composite(pill)
            elif not entered:
                pass
            if not is_cur and entered and not it["keyword"]:
                # spoken words settle slightly dimmer so the eye follows the voice
                pass
            dim = 0.92 if (entered and not is_cur and not it["keyword"]) else 1.0
            self._paste_word(img, base, it["cx"], it["cy"] + dy, scale, alpha * dim, rot)

    def _draw_karaoke(self, img, it, t, s, e, fade, is_cur, p):
        if p <= 0:
            return
        size = it["size"]
        dim_base = self._word_image(it["text"], size, (255, 255, 255))
        self._paste_word(img, dim_base, it["cx"], it["cy"], 1.0, 0.30 * fade)
        if t < s:
            return
        frac = easing.clamp01((t - s) / max(0.05, e - s))
        hot = self._word_image(it["text"], size, self.accent)
        # clip hot copy to spoken fraction
        cw = int(hot.width * frac)
        if cw > 0:
            clip = hot.crop((0, 0, cw, hot.height))
            tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
            tmp.alpha_composite(clip, (int(it["cx"] - hot.width / 2), int(it["cy"] - hot.height / 2)))
            a = tmp.split()[3].point(lambda v: int(v * fade))
            tmp.putalpha(a)
            img.alpha_composite(tmp)
        if it["keyword"]:
            kw = self._word_image(it["text"], size, self.accent2)
            self._paste_word(img, kw, it["cx"], it["cy"], 1.0, fade)

    def _draw_typewriter(self, img, it, t, s, e, fade, is_cur, _p):
        reveal_t0 = s - 0.05
        chars = len(it["text"])
        n = int(easing.clamp01((t - reveal_t0) / max(0.1, 0.22 + 0.035 * chars)) * chars)
        if n <= 0:
            return
        shown = it["text"][:n]
        color = self.accent2 if it["keyword"] else (255, 255, 255)
        base = self._word_image(shown, it["size"], color)
        # recenter: full word width vs shown width
        full = self._word_image(it["text"], it["size"], color)
        dx = (full.width - base.width) / 2
        self._paste_word(img, base, it["cx"] - dx, it["cy"], 1.0, fade)
        if is_cur and n < chars and int(t * 3) % 2 == 0:
            caret = Image.new("RGBA", (max(2, it["size"] // 14), int(it["size"] * 0.9)), self.accent + (255,))
            img.alpha_composite(caret, (int(it["cx"] - dx + base.width / 2 + 6),
                                       int(it["cy"] - caret.height / 2)))


class ProgressBarLayer(Layer):
    """Thin AE-style progress bar pinned to the bottom."""

    def __init__(self, duration: float, accent=(255, 45, 149), name: str = "progress"):
        super().__init__(name, 0.0, duration)
        self.duration = duration
        self.accent = accent

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, t: float, ctx: dict):
        w, h = img.size
        frac = easing.clamp01(t / self.duration) if self.duration > 0 else 0
        bh = max(4, h // 270)
        y = h - bh - int(h * 0.035)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rounded_rectangle([int(w * 0.08), y, int(w * 0.92), y + bh], radius=bh // 2,
                            fill=(255, 255, 255, 40))
        if frac > 0:
            d.rounded_rectangle([int(w * 0.08), y, int(w * 0.08 + (w * 0.84) * frac), y + bh],
                                radius=bh // 2, fill=self.accent + (255,))
        img.alpha_composite(overlay)


class Composition:
    """Ordered layers composited back-to-front, like an AE comp."""

    def __init__(self, w: int, h: int, fps: int, duration: float):
        self.w, self.h, self.fps = w, h, fps
        self.duration = duration
        self.layers: list[Layer] = []

    def add(self, layer: Layer) -> Layer:
        self.layers.append(layer)
        return layer

    def frame(self, t: float) -> Image.Image:
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)
        ctx = dict(w=self.w, h=self.h, fps=self.fps, duration=self.duration)
        for layer in self.layers:
            if layer.active(t):
                op = layer.opacity.value(t)
                if op <= 0.01:
                    continue
                layer.render(img, draw, t, ctx)
                # (per-layer opacity post-multiply skipped for speed; layers
                # bake their own fades)
        return img.convert("RGB")
