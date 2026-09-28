#!/usr/bin/env python3
"""Build a battery gauge strip -- the art for BLK_BATTS (0x18) or the pulse
ring (0x21).

A port of the Fogg designer's BatteryGenerator, so a gauge built here drops
into the same block a gauge built in the designer would have. Defaults are the
designer's own defaults (BatteryGenerator.tsx:67-92).

    python3 make_battery_gauge.py --out battery_strip.png
    python3 make_battery_gauge.py --style circular_ring --frames 6 --color-mode dynamic
    python3 make_battery_gauge.py --levels 5,25,45,65,85,100 --json

The frame count is the thing to get right
-----------------------------------------
Every frame in the strip is a *different charge level*, and the watch picks the
frame from the battery percentage. With six frames the firmware's bands are:

    frame 0:   0- 5%      frame 3:  41-60%
    frame 1:   6-20%      frame 4:  61-80%
    frame 2:  21-40%      frame 5:  81-100%

Those are not evenly spaced, but six evenly spaced levels (0/20/40/60/80/100)
land in the same band every time, which is why the designer gets away with
even spacing. `--levels` takes the percentages explicitly when you need the
bands exactly.

FRAME 0 IS THE EMPTY FRAME, AND IT IS USUALLY RED. A gauge whose frame 0 is
the intended design -- a low-battery icon, say -- will look like a working
gauge all day and then be right by accident at 4%. Design frame 0 as "critical".

Two places this departs from the designer, both deliberate:

* The designer reaches for `ctx.roundRect(..., [0, 2, 2, 0])` and
  `lineCap: 'round'`, neither of which Pillow has. Per-corner radii and round
  caps are built in `_g6canvas`.
* The designer draws the '⚡' placeholder in the middle of `circular_ring` as
  text in a browser sans-serif. A script has to name a font, and most watch
  fonts have no U+26A1 -- Pillow would silently draw a .notdef box, which is
  indistinguishable from a real character on the watch. This script asks the
  font's cmap and refuses to build the strip if the glyph is missing. Pass
  `--no-lightning --show-percentage` if you would rather not draw a bolt.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _g6canvas import (  # noqa: E402
    Canvas,
    alpha_bbox,
    find_missing_glyphs,
    interpolate_color,
    lit_pixels,
    with_alpha,
)

STYLES = ("horizontal_capsule", "vertical_capsule", "circular_ring", "gauge_arc", "pill_dots")

# The designer's useState defaults, BatteryGenerator.tsx:67-92.
DEFAULTS = {
    "frame_width": 84,
    "frame_height": 75,
    "frames": 6,
    "style": "horizontal_capsule",
    "color_mode": "dynamic",
    "solid_color": "#ffffff",
    "low_color": "#ff4d4d",
    "mid_color": "#ffc83b",
    "high_color": "#2ecc71",
    "stroke_width": 3,
    "border_radius": 6,
    "icon_padding": 12,
    "show_percentage": False,
    "show_lightning": True,
    "font_size": 11,
    "bolt_color": "#ffc83b",
    "dot_count": 5,
    "dot_gap": 4,
    "cap_size": 6,   # subtracted from bodyW/right, bodyH/bottom
    "cap_thickness": 5,
}

TRACK = with_alpha((255, 255, 255), 0.08)

# The two block types this generator serves, and the frame count each holds.
EXPECTED_FRAMES = {"BLK_BATTS": {6}, "BLK_UNK_A1": {6}}

BOLT = "⚡"

# The firmware's own band edges, for the docstring above and for tests.
BATTERY_BANDS = ((0, 5), (6, 20), (21, 40), (41, 60), (61, 80), (81, 100))


def band_for(percent):
    for index, (low, high) in enumerate(BATTERY_BANDS):
        if low <= percent <= high:
            return index
    return len(BATTERY_BANDS) - 1


def even_levels(frames):
    """Designer's mapping: frame 0 = 0%, last frame = 100%."""
    if frames <= 1:
        return [100.0]
    return [(i / (frames - 1)) * 100.0 for i in range(frames)]


def colour_for(percent, cfg):
    if cfg["color_mode"] == "solid":
        return with_alpha(_rgb(cfg["solid_color"]), 255)
    if cfg["color_mode"] == "dynamic":
        if percent <= 20:
            rgb = _rgb(cfg["low_color"])
        elif percent <= 60:
            rgb = _rgb(cfg["mid_color"])
        else:
            rgb = _rgb(cfg["high_color"])
        return with_alpha(rgb, 255)
    if percent <= 50:
        rgb = interpolate_color(cfg["low_color"], cfg["mid_color"], percent / 50.0)
    else:
        rgb = interpolate_color(cfg["mid_color"], cfg["high_color"], (percent - 50.0) / 50.0)
    return with_alpha(rgb, 255)


def _rgb(value):
    from _g6canvas import hex_to_rgb
    return hex_to_rgb(value)


def draw_bolt(canvas, cx, cy, size, colour):
    """The six-point bolt, from drawLightningBolt at BatteryGenerator.tsx:135.

    The designer sets strokeStyle/lineWidth next to this and never strokes, so
    the contrast outline it appears to set up is dead code; only the fill is
    reproduced.
    """
    canvas.fill_polygon(
        [
            (cx + size * 0.12, cy - size * 0.45),
            (cx - size * 0.28, cy + size * 0.05),
            (cx + size * 0.04, cy + size * 0.05),
            (cx - size * 0.12, cy + size * 0.45),
            (cx + size * 0.28, cy - size * 0.05),
            (cx - size * 0.04, cy - size * 0.05),
        ],
        colour,
    )


def _overlay(canvas, cfg, cx, cy, size, percent, colour):
    """Bolt at 100%, or the percentage, in the capsule and arc styles."""
    if cfg["show_lightning"] and percent >= 100:
        draw_bolt(canvas, cx, cy, size, with_alpha(_rgb(cfg["bolt_color"]), 255))
    elif cfg["show_percentage"] and percent > 0:
        text_colour = (0, 0, 0, 255) if percent > 50 else colour
        canvas.fill_text_centre(
            cx, cy, f"{round(percent)}%", cfg["font"], cfg["font_size"], text_colour
        )


def draw_frame(canvas, cfg, percent):
    """One frame, filling a canvas of exactly frame_width x frame_height.

    Offsets are the caller's job -- build() gives each frame its own canvas and
    blits it. Translation mirrors BatteryGenerator's drawSingleFrame.
    """
    w, h = cfg["frame_width"], cfg["frame_height"]
    colour = colour_for(percent, cfg)
    style = cfg["style"]
    pad = cfg["icon_padding"]
    sw = cfg["stroke_width"]
    rx = cfg["border_radius"]

    if style == "horizontal_capsule":
        body_w = w - pad * 2 - cfg["cap_size"]
        body_h = h - pad * 2
        cap_w = 5
        cap_h = body_h * 0.35
        with canvas.layer():
            canvas.fill_round_rect(
                pad + body_w, pad + (body_h - cap_h) / 2.0,
                pad + body_w + cap_w, pad + (body_h - cap_h) / 2.0 + cap_h,
                [0, 2, 2, 0], colour,
            )
        with canvas.layer():
            canvas.stroke_round_rect(pad, pad, pad + body_w, pad + body_h, rx, colour, sw)
        margin = sw + 2
        fill_w = (body_w - margin * 2) * (percent / 100.0)
        fill_h = body_h - margin * 2
        if fill_w > 0:
            with canvas.layer():
                canvas.fill_round_rect(
                    pad + margin, pad + margin,
                    pad + margin + fill_w, pad + margin + fill_h,
                    max(0, rx - 2), colour,
                )
        _overlay(canvas, cfg, pad + body_w / 2.0, pad + body_h / 2.0,
                 min(body_w, body_h) * 0.8, percent, colour)

    elif style == "vertical_capsule":
        body_w = w - pad * 2
        body_h = h - pad * 2 - cfg["cap_size"]
        cap_w = body_w * 0.35
        cap_h = cfg["cap_thickness"]
        with canvas.layer():
            canvas.fill_round_rect(
                pad + (body_w - cap_w) / 2.0, pad,
                pad + (body_w - cap_w) / 2.0 + cap_w, pad + cap_h,
                [2, 2, 0, 0], colour,
            )
        with canvas.layer():
            canvas.stroke_round_rect(pad, pad + cap_h, pad + body_w, pad + cap_h + body_h,
                                     rx, colour, sw)
        margin = sw + 2
        fill_h = (body_h - margin * 2) * (percent / 100.0)
        fill_w = body_w - margin * 2
        if fill_h > 0:
            fill_y = pad + cap_h + body_h - margin - fill_h
            with canvas.layer():
                canvas.fill_round_rect(
                    pad + margin, fill_y, pad + margin + fill_w, fill_y + fill_h,
                    max(0, rx - 2), colour,
                )
        _overlay(canvas, cfg, pad + body_w / 2.0, pad + cap_h + body_h / 2.0,
                 min(body_w, body_h) * 0.8, percent, colour)

    elif style == "circular_ring":
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - pad
        with canvas.layer():
            canvas.arc_stroke(cx, cy, radius, 0.0, 2 * math.pi, TRACK, sw, caps="butt")
        if percent > 0:
            with canvas.layer():
                canvas.arc_stroke(cx, cy, radius, -math.pi / 2,
                                  -math.pi / 2 + 2 * math.pi * (percent / 100.0),
                                  colour, sw + 1)
        if cfg["show_lightning"] and percent >= 100:
            draw_bolt(canvas, cx, cy, radius * 0.9, with_alpha(_rgb(cfg["bolt_color"]), 255))
        elif cfg["show_percentage"]:
            canvas.fill_text_centre(cx, cy, f"{round(percent)}%",
                                    cfg["font"], cfg["font_size"], colour)
        else:
            canvas.fill_text_centre(cx, cy, BOLT, cfg["font"],
                                    max(6.0, radius * 0.7), colour)

    elif style == "gauge_arc":
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - pad
        start, total = 0.75 * math.pi, 1.5 * math.pi
        with canvas.layer():
            canvas.arc_stroke(cx, cy, radius, start, start + total, TRACK, sw)
        if percent > 0:
            with canvas.layer():
                canvas.arc_stroke(cx, cy, radius, start,
                                  start + total * (percent / 100.0), colour, sw + 2)
        if cfg["show_lightning"] and percent >= 100:
            draw_bolt(canvas, cx, cy, radius * 0.9, with_alpha(_rgb(cfg["bolt_color"]), 255))
        elif cfg["show_percentage"]:
            canvas.fill_text_centre(cx, cy, f"{round(percent)}%",
                                    cfg["font"], cfg["font_size"], colour)

    elif style == "pill_dots":
        count = cfg["dot_count"]
        gap = cfg["dot_gap"]
        body_w = w - pad * 2
        dot_w = (body_w - (count - 1) * gap) / count
        dot_h = h - pad * 2
        active = math.ceil((percent / 100.0) * count)
        for i in range(count):
            dot_x = pad + i * (dot_w + gap)
            with canvas.layer():
                canvas.fill_round_rect(dot_x, pad, dot_x + dot_w, pad + dot_h, rx,
                                       colour if i < active else TRACK)
        if cfg["show_lightning"] and percent >= 100:
            draw_bolt(canvas, w / 2.0, h / 2.0, min(body_w, dot_h) * 0.9,
                      with_alpha(_rgb(cfg["bolt_color"]), 255))

    else:
        raise ValueError(f"unknown style {style!r}")


def text_items_needed(cfg, levels):
    """Every string this configuration will actually try to draw.

    Derived from the same rules as draw_frame, because a guard that guesses
    wrong is worse than no guard: it lets a .notdef box through and a .notdef
    box is indistinguishable from a real character once it is on the watch.

    The trap this exists for: `circular_ring` has a final `else` that draws the
    bolt as TEXT, and it is reached by *every* frame that is not full and has
    no percentage -- so the glyph is needed even when --show-lightning is on
    and the full frame gets a real drawn bolt. Checking "is the bolt enabled"
    misses it entirely.
    """
    items = set()
    has_full_frame = any(pct >= 100 for pct in levels)
    if cfg["show_percentage"] and any(pct > 0 for pct in levels):
        for pct in levels:
            if pct > 0:
                items.add(f"{round(pct)}%")
    if cfg["style"] == "circular_ring" and not (cfg["show_lightning"] and has_full_frame):
        if not cfg["show_percentage"]:
            items.add(BOLT)
    return sorted(items)


def build(cfg, levels):
    frames = len(levels)
    ss = cfg["supersample"]
    fw, fh = cfg["frame_width"], cfg["frame_height"]
    strip = Canvas(fw, fh * frames, ss)
    if cfg["bg_color"] != "transparent":
        from _g6canvas import hex_to_rgb
        strip.fill_rect(0, 0, fw, fh * frames, with_alpha(hex_to_rgb(cfg["bg_color"]), 255))
    for index, percent in enumerate(levels):
        frame = Canvas(fw, fh, ss)
        draw_frame(frame, cfg, percent)
        strip.blit_canvas(frame, 0, index * fh)
    return strip.finish()


def parse_levels(text, frames):
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    values = [float(p) for p in parts]
    if len(values) != frames:
        raise ValueError(f"--levels lists {len(values)} value(s) but --frames is {frames}")
    for value in values:
        if not 0.0 <= value <= 100.0:
            raise ValueError(f"level {value} is outside 0-100")
    if any(b < a for a, b in zip(values, values[1:])):
        raise ValueError(f"levels must not decrease: {values}")
    return values


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Build a battery gauge strip (vertical: frames stacked top to bottom).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--out", required=True, help="output PNG")
    p.add_argument("--frame-width", type=int, default=DEFAULTS["frame_width"])
    p.add_argument("--frame-height", type=int, default=DEFAULTS["frame_height"])
    p.add_argument("--frames", type=int, default=DEFAULTS["frames"], help="frames in the strip")
    p.add_argument("--style", choices=STYLES, default=DEFAULTS["style"])
    p.add_argument("--color-mode", choices=("solid", "dynamic", "gradient"),
                   default=DEFAULTS["color_mode"])
    p.add_argument("--solid-color", default=DEFAULTS["solid_color"])
    p.add_argument("--low-color", default=DEFAULTS["low_color"])
    p.add_argument("--mid-color", default=DEFAULTS["mid_color"])
    p.add_argument("--high-color", default=DEFAULTS["high_color"])
    p.add_argument("--stroke-width", type=float, default=DEFAULTS["stroke_width"])
    p.add_argument("--border-radius", type=float, default=DEFAULTS["border_radius"])
    p.add_argument("--icon-padding", type=float, default=DEFAULTS["icon_padding"])
    p.add_argument("--bg-color", default="transparent", help="'transparent' or a hex colour")
    p.add_argument("--show-percentage", action="store_true",
                   help="print the percentage inside the gauge")
    p.add_argument("--no-lightning", action="store_true",
                   help="do not draw the bolt on the full frame")
    p.add_argument("--font", default="Arial.ttf", help="font for percentage/bolt text")
    p.add_argument("--font-size", type=float, default=DEFAULTS["font_size"])
    p.add_argument("--levels", default=None,
                   help="comma-separated charge per frame, e.g. 5,25,45,65,85,100. "
                        "Default is even spacing, which is what the designer uses.")
    p.add_argument("--block-type", default=None,
                   help="validate the frame count against this block type")
    p.add_argument("--supersample", type=int, default=4, help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true", help="print a JSON report")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    cfg = {
        "frame_width": args.frame_width,
        "frame_height": args.frame_height,
        "style": args.style,
        "color_mode": args.color_mode,
        "solid_color": args.solid_color,
        "low_color": args.low_color,
        "mid_color": args.mid_color,
        "high_color": args.high_color,
        "stroke_width": args.stroke_width,
        "border_radius": args.border_radius,
        "icon_padding": args.icon_padding,
        "bg_color": args.bg_color,
        "show_percentage": args.show_percentage,
        "show_lightning": not args.no_lightning,
        "font": args.font,
        "font_size": args.font_size,
        "bolt_color": DEFAULTS["bolt_color"],
        "dot_count": DEFAULTS["dot_count"],
        "dot_gap": DEFAULTS["dot_gap"],
        "cap_size": DEFAULTS["cap_size"],
        "cap_thickness": DEFAULTS["cap_thickness"],
        "supersample": max(1, args.supersample),
    }
    if cfg["frame_width"] < 4 or cfg["frame_height"] < 4:
        print("frame size is too small to draw anything", file=sys.stderr)
        return 1
    if args.frames < 1:
        print("--frames must be at least 1", file=sys.stderr)
        return 1

    # Levels have to be resolved before the glyph check, because the strings
    # that get drawn depend on them: the percentage follows the level, and the
    # bolt is only text when no frame is full.
    if args.levels:
        try:
            levels = parse_levels(args.levels, args.frames)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        levels = even_levels(args.frames)

    # A gauge can ask for a bolt or a percentage as text, and a missing glyph
    # is invisible on the watch. Check every string that will be drawn.
    text_items = text_items_needed(cfg, levels)
    if text_items:
        from _g6canvas import resolve_font
        font_path = resolve_font(cfg["font"])
        if font_path is None:
            print(f"cannot find font {cfg['font']!r}", file=sys.stderr)
            return 1
        missing = find_missing_glyphs(text_items, font_path)
        if missing:
            print(
                f"font {font_path.name} has no glyph for items {missing}: "
                f"{[text_items[i] for i in missing]}\n"
                "Pillow draws a .notdef box for these, which is indistinguishable from a "
                "real character. Pass --font with a font that covers the text, or turn "
                "off the element that needs it (--no-lightning, or --show-percentage).",
                file=sys.stderr,
            )
            return 1

    if args.block_type:
        expected = EXPECTED_FRAMES.get(args.block_type)
        if expected is not None and args.frames not in expected:
            print(
                f"{args.block_type} holds {' or '.join(str(n) for n in sorted(expected))} "
                f"frame(s) and this strip has {args.frames}", file=sys.stderr
            )
            return 1

    strip = build(cfg, levels)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)

    report = {
        "out": str(out),
        "style": cfg["style"],
        "width": strip.width,
        "height": strip.height,
        "frame_width": cfg["frame_width"],
        "frame_height": cfg["frame_height"],
        "frames": len(levels),
        "levels": [round(v, 2) for v in levels],
        "firmware_bands": [band_for(v) for v in levels],
        "frames_detail": [],
    }
    for index, percent in enumerate(levels):
        frame = strip.crop(
            (0, index * cfg["frame_height"], cfg["frame_width"],
             (index + 1) * cfg["frame_height"])
        )
        report["frames_detail"].append({
            "index": index,
            "percent": round(percent, 2),
            "band": band_for(percent),
            "alpha_bbox": alpha_bbox(frame),
            "lit_pixels": lit_pixels(frame),
        })

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{out}  {strip.width}x{strip.height}  {len(levels)} frames  style={cfg['style']}")
        for row in report["frames_detail"]:
            print(f"  frame {row['index']}: {row['percent']:>5.1f}%  band {row['band']}  "
                  f"bbox {row['alpha_bbox']}  {row['lit_pixels']} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
