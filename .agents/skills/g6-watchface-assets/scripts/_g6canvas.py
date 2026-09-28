"""Shared drawing helpers for the g6-watchface-assets generators.

Why this exists
---------------
The Fogg designer draws with the browser canvas, which gives two things for
free that Pillow does not:

1. **Antialiasing.** Pillow's ImageDraw is aliased. Every diagonal and every
   circle edge comes out stair-stepped. We render 4x and downsample with
   LANCZOS, which lands within a pixel of what the browser produces.
2. **Alpha compositing.** `ImageDraw` on an RGBA image *replaces* pixels, it
   does not blend. So a translucent track under an opaque fill would punch a
   hole instead of showing through, and a stroke drawn twice would be opaque
   where canvas would blend it. `Canvas.layer()` reproduces canvas semantics.

Coordinates are always LOGICAL. A `Canvas(84, 75)` draws at 84x75 whatever the
supersample factor is; the caller never sees the scale factor.

Not a public interface. The generators import from here; if you need a stable
API use `make_digit_strip.py` / `make_hand_sprite.py` /
`make_battery_gauge.py` / `make_weather_icons.py`.
"""

from __future__ import annotations

import math
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 4x is enough that a 2px stroke has 8 device pixels to work with, and cheap
# enough that a 12-frame sheet still builds in well under a second.
SUPERSAMPLE = 4

FONT_DIRS = (
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
)


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

def hex_to_rgb(value):
    """'#abc' or '#aabbcc' -> (r, g, b). Raises on anything else.

    The designer silently falls back to a colour on a parse failure
    (`interpolateColor` wraps itself in try/except and returns color1). We
    raise instead: a typo'd colour that quietly renders as the wrong colour is
    the sort of thing that ships.
    """
    clean = str(value).strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(ch * 2 for ch in clean)
    if len(clean) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    num = int(clean, 16)
    return ((num >> 16) & 255, (num >> 8) & 255, num & 255)


def interpolate_color(start, end, factor):
    """Linear RGB blend. Mirrors the designer's `interpolateColor`."""
    c1, c2 = hex_to_rgb(start), hex_to_rgb(end)
    r = round(c1[0] + factor * (c2[0] - c1[0]))
    g = round(c1[1] + factor * (c2[1] - c1[1]))
    b = round(c1[2] + factor * (c2[2] - c1[2]))
    return (r, g, b)


def with_alpha(rgb, alpha):
    return (rgb[0], rgb[1], rgb[2], int(round(max(0.0, min(1.0, alpha)) * 255)))


# --------------------------------------------------------------------------
# fonts
# --------------------------------------------------------------------------

def resolve_font(name):
    """Find a font file by family name or filename. Returns a Path or None."""
    if not name:
        return None
    direct = Path(name)
    if direct.is_file():
        return direct
    for root in FONT_DIRS:
        root = Path(root)
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.rglob("*.tt[fc]")) + sorted(root.rglob("*.otf"))
        except OSError:
            continue
        for entry in entries:
            if entry.name.lower() == name.lower():
                return entry
            stem = entry.stem.lower()
            if stem == name.lower() or stem == name.lower().replace(" ", ""):
                return entry
    return None


def covered_codepoints(font_path):
    """Set of codepoints the font has a glyph for, or None without fontTools.

    This is the only trustworthy missing-glyph test. Rendering a canary does
    not work: DIN Condensed Bold *covers* U+E000 and draws a real glyph for it,
    so a canary in the Private Use Area silently passes. Ask the cmap.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    try:
        font = TTFont(str(font_path), lazy=True)
    except Exception:
        return None
    try:
        return set(font.getBestCmap().keys())
    finally:
        try:
            font.close()
        except Exception:
            pass


def find_missing_glyphs(items, font_path):
    """Indices of `items` containing a character the font cannot draw.

    Returns [] when fontTools is unavailable, so the check degrades to off
    rather than to "everything is missing".
    """
    covered = covered_codepoints(font_path)
    if not covered:
        return []
    missing = []
    for index, text in enumerate(items):
        for ch in str(text):
            if ch in " \t\n":
                continue
            if ord(ch) not in covered:
                missing.append(index)
                break
    return missing


def load_font(path_or_name, size):
    """Pillow font at `size` px, falling back to the bitmap default."""
    resolved = resolve_font(path_or_name)
    if resolved is not None:
        return ImageFont.truetype(str(resolved), int(size))
    return ImageFont.load_default()


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def _clamp_radius(radius, extent):
    return max(0.0, min(float(radius), float(extent) / 2.0))


def round_rect_points(x0, y0, x1, y1, radii, samples=8):
    """Points tracing a rounded rectangle, clockwise from the top-left.

    `radii` is a scalar, or [top_left, top_right, bottom_right, bottom_left].
    Per-corner radii are what the designer's `ctx.roundRect(..., [0, 2, 2, 0])`
    does, and Pillow's `rounded_rectangle` only takes a single radius, so the
    path is built here instead.
    """
    if isinstance(radii, (int, float)):
        radii = [radii] * 4
    if len(radii) != 4:
        raise ValueError("radii must be a scalar or exactly 4 values")
    width, height = x1 - x0, y1 - y0
    tl = _clamp_radius(radii[0], width)
    tr = _clamp_radius(radii[1], width)
    br = _clamp_radius(radii[2], width)
    bl = _clamp_radius(radii[3], width)
    # Vertical radii are limited by the height as well, so a very wide short
    # bar cannot ask for a corner taller than itself.
    tl = _clamp_radius(tl, min(width, height))
    tr = _clamp_radius(tr, min(width, height))
    br = _clamp_radius(br, min(width, height))
    bl = _clamp_radius(bl, min(width, height))

    pts = []

    def arc_to(cx, cy, radius, start):
        if radius <= 0:
            pts.append((cx, cy))
            return
        for i in range(samples + 1):
            angle = start + (math.pi / 2) * (i / samples)
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    pts.append((x0 + tl, y0))
    pts.append((x1 - tr, y0))
    arc_to(x1 - tr, y0 + tr, tr, -math.pi / 2)
    pts.append((x1, y1 - br))
    arc_to(x1 - br, y1 - br, br, 0.0)
    pts.append((x0 + bl, y1))
    arc_to(x0 + bl, y1 - bl, bl, math.pi / 2)
    pts.append((x0, y0 + tl))
    arc_to(x0 + tl, y0 + tl, tl, math.pi)
    return pts


def arc_points(cx, cy, rx, ry, start, end, sweep_tolerance=0.6):
    """Sample an elliptical arc. Angles in radians, canvas convention (y down).

    `rx`/`ry` may be negative in SVG; the sign is folded into the rotation
    because Pillow-style canvas arcs only need the geometry.
    """
    points = []
    length = abs(rx + ry) * abs(end - start) / 2.0
    steps = max(2, int(length / max(sweep_tolerance, 0.05)) + 2)
    for i in range(steps + 1):
        t = start + (end - start) * (i / steps)
        points.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return points


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------

class Canvas:
    """A logical-size RGBA canvas that antialiases by supersampling."""

    def __init__(self, width, height, ss=SUPERSAMPLE, background=(0, 0, 0, 0)):
        self.width = int(width)
        self.height = int(height)
        self.ss = int(ss)
        self.image = Image.new("RGBA", (self.width * self.ss, self.height * self.ss), background)

    # -- internals -------------------------------------------------------
    def _draw(self):
        return ImageDraw.Draw(self.image)

    def _px(self, value):
        return float(value) * self.ss

    def _points(self, points):
        return [(self._px(x), self._px(y)) for x, y in points]

    @contextmanager
    def layer(self):
        """Draw onto a transparent layer that is alpha-composited on exit.

        Needed wherever canvas would blend. Without it a translucent track
        under an opaque fill replaces it rather than showing through, and the
        frame is a different colour than the designer produces.
        """
        sub = Canvas(self.width, self.height, self.ss)
        try:
            yield sub
        finally:
            self.image = Image.alpha_composite(self.image, sub.image)

    # -- shapes ----------------------------------------------------------
    def fill_polygon(self, points, colour):
        pts = self._points(points)
        if len(pts) >= 3:
            self._draw().polygon(pts, fill=colour)

    def fill_rect(self, x0, y0, x1, y1, colour):
        self._draw().rectangle(
            [self._px(x0), self._px(y0), self._px(x1) - 1, self._px(y1) - 1], fill=colour
        )

    def fill_round_rect(self, x0, y0, x1, y1, radii, colour):
        self.fill_polygon(round_rect_points(x0, y0, x1, y1, radii), colour)

    def stroke_polyline(self, points, colour, width, closed=False, caps="round"):
        """Round-capped, round-joined stroke.

        Pillow's `line(joint='curve')` rounds the joins but leaves the caps
        square, and the designer always asks for round caps. Caps are therefore
        explicit discs at the two ends.
        """
        pts = self._points(points)
        if len(pts) < 2:
            if pts:
                self._disc(pts[0][0], pts[0][1], self._px(width) / 2.0, colour)
            return
        self._draw().line(pts, fill=colour, width=max(1, int(round(self._px(width)))), joint="curve")
        if caps == "round":
            radius = self._px(width) / 2.0
            for x, y in (pts[0], pts[-1]):
                self._disc(x, y, radius, colour)

    def stroke_round_rect(self, x0, y0, x1, y1, radii, colour, width):
        self.stroke_polyline(
            round_rect_points(x0, y0, x1, y1, radii), colour, width, closed=True, caps="butt"
        )

    def fill_ellipse(self, cx, cy, rx, ry, colour):
        box = [
            self._px(cx - rx), self._px(cy - ry),
            self._px(cx + rx), self._px(cy + ry),
        ]
        if box[2] > box[0] and box[3] > box[1]:
            self._draw().ellipse(box, fill=colour)

    def _disc(self, x, y, radius, colour):
        if radius <= 0:
            return
        self._draw().ellipse([x - radius, y - radius, x + radius, y + radius], fill=colour)

    def arc_stroke(self, cx, cy, radius, start, end, colour, width, caps="round"):
        """Stroked circular arc, round-capped. Angle 0 is +x, growing clockwise
        on screen, which is the canvas convention (y down)."""
        if end <= start or radius <= 0:
            return
        points = arc_points(cx, cy, radius, radius, start, end, self.ss * 0.4)
        self.stroke_polyline(points, colour, width, caps=caps)

    # -- text ------------------------------------------------------------
    def text_metrics(self, text, font):
        draw = self._draw()
        probe = Image.new("RGBA", (1, 1))
        del probe
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return left, top, right, bottom

    def fill_text_centre(self, cx, cy, text, font_path, font_size, colour):
        """Centre text on its INK, matching what `make_digit_strip.py` does.

        The designer uses canvas `textBaseline: 'middle'`, which centres the
        em box; on DIN Condensed that sits a glyph a few px high. Centring the
        ink is what `build_silver_cat.py` does, so the two agree.
        """
        font = load_font(font_path, int(round(font_size * self.ss)))
        left, top, right, bottom = self.text_metrics(text, font)
        x = self._px(cx) - (right - left) / 2.0 - left
        y = self._px(cy) - (bottom - top) / 2.0 - top
        self._draw().text((x, y), text, font=font, fill=colour)

    def text_ink_size(self, text, font_path, font_size):
        """Ink width/height at LOGICAL scale, for layout decisions."""
        font = load_font(font_path, max(1, int(round(font_size))))
        left, top, right, bottom = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox(
            (0, 0), text, font=font
        )
        return right - left, bottom - top

    # -- compositing -----------------------------------------------------
    def paste(self, image, x, y, width, height):
        """Draw a PIL image at logical (x, y, width, height), scaling if needed."""
        target = (max(1, int(round(width))), max(1, int(round(height))))
        if image.size != target:
            image = image.resize(target, Image.LANCZOS)
        big = image.resize((target[0] * self.ss, target[1] * self.ss), Image.LANCZOS)
        self.image.alpha_composite(big, (int(round(x * self.ss)), int(round(y * self.ss))))

    def blit_canvas(self, other, x, y):
        """Composite another Canvas at logical (x, y) without resampling.

        `other.image` is still at supersampled resolution, so this is a 1:1
        alpha_composite -- no upsample, no resample. Pasting a *finished*
        (already downsampled) frame would go through `paste` and throw the
        antialiasing away.
        """
        if other.ss != self.ss:
            raise ValueError("cannot blit canvases with different supersample factors")
        self.image.alpha_composite(other.image, (int(round(x * self.ss)), int(round(y * self.ss))))

    def finish(self):
        """Downsample to logical size. This is where the antialiasing happens."""
        return self.image.resize((self.width, self.height), Image.LANCZOS)


# --------------------------------------------------------------------------
# image analysis, shared by the generators' self-reports
# --------------------------------------------------------------------------

def alpha_bbox(image, threshold=0):
    """Bounding box of pixels whose alpha is at or above `threshold`.

    `threshold=0` is `getbbox()`, i.e. ANY non-transparent pixel. That is
    usually the wrong number: downsampling from the supersampled buffer with
    LANCZOS overshoots at a hard edge and leaves a ringing tail at alpha 1-7
    that reaches one to two pixels past the real ink. Measured on a 46px
    thunder frame, the full-frame box is (5,5,41,40) while the box at
    alpha>=8 is (7,7,39,38) and the true padded box is (8,8,38,38). A clipping
    check on the unthresholded box fails a correct renderer, and the obvious
    "fix" -- loosening the bound until it passes -- hides real clipping.

    Pass `threshold=8` for a bounds check. Leave it at 0 only when you want
    the strictest possible statement, e.g. "is this frame entirely empty".
    """
    if threshold <= 0:
        return image.getchannel("A").getbbox()
    mask = image.getchannel("A").point(lambda v: 255 if v >= threshold else 0)
    return mask.getbbox()


def alpha_histogram(image):
    return image.getchannel("A").histogram()


def lit_pixels(image, threshold=8):
    """Count of pixels whose alpha is at or above `threshold`.

    Thresholded, so it measures "how much of the frame is ink" and is the right
    number for a monotonicity check. It is NOT proportional to drawn area: the
    antialiased fringe under a thin stroke falls below any useful threshold, and
    the smaller the sprite the more of it there is. Use `ink_area` when the
    number has to scale with the drawing.
    """
    return sum(count for value, count in enumerate(alpha_histogram(image)) if value >= threshold)


def ink_area(image):
    """Total coverage in pixels: sum(alpha)/255.

    Unlike `lit_pixels` this is the actual drawn area, so it scales with the
    square of the size and with the stroke width. A 2x size change on a
    stroke-only icon multiplies this by 4.
    """
    return sum(value * count for value, count in enumerate(alpha_histogram(image))) / 255.0


def frame_bboxes(strip, frame_width, frame_height, frames):
    """Per-frame alpha bounding box of a vertical strip."""
    out = []
    for index in range(frames):
        frame = strip.crop((0, index * frame_height, frame_width, (index + 1) * frame_height))
        out.append(alpha_bbox(frame))
    return out


def eprint(*args):
    print(*args, file=sys.stderr)
