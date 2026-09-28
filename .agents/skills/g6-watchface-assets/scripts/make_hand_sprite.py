#!/usr/bin/env python3
"""Generate a hand sprite for an HK89 dial block, with the pivot computed.

A Python port of Fogg's `HandGenerator.tsx`. The designer is the reference; the
geometry below mirrors it exactly so a sprite built here drops into the same
block without adjustment.

    python3 make_hand_sprite.py --type hour --out arm_hour.png

The important part of a hand is not how it looks, it is where the watch thinks
it is pinned. Two conventions, both counter-intuitive, and both verified
against every hand in every dial in the repo:

  * `cty` is the horizontal offset of the pivot from the sprite's LEFT edge,
    and it is always width/2.
  * `ctx` is the distance from the sprite's BOTTOM edge UP TO the pivot, so

        pivot = {x: cty, y: height - ctx}

Not the other way round. The obvious reading puts every hand 180 degrees out,
which is easy to miss because the base still converges on the centre of the
face.

And on a hand block, `posx`/`posy` is where the PIVOT goes on screen -- usually
233, 233 -- not the top-left of the sprite. So a 256px hand at posy=233 is
correct, not a block hanging off the screen.

This script prints `ctx` and `cty` for the sprite it makes. Put them in the
block descriptor. There is no reason to compute them by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Mirrors HAND_STYLES in HandGenerator.tsx.
HAND_STYLES = [
    "sword", "arrow", "baton", "needle", "club", "diamond", "leaf", "lollipop",
]

# Mirrors getDefaults(). Sizes are tuned against real extracted hands on a
# 466px dial: hour ~150 tall, minute ~210, second ~250. A hand much shorter
# than this is invisible on the watch.
DEFAULTS = {
    "hour": dict(width=16, hand_length=120, tail_length=30, tip_style="sword",
                 color="#ffffff", tail_color="#aaaaaa", glow_color="",
                 glow_blur=0, shadow=True, outline=True, outline_color="#000000",
                 outline_width=2, rounded=True),
    "minute": dict(width=12, hand_length=175, tail_length=35, tip_style="sword",
                   color="#ffffff", tail_color="#aaaaaa", glow_color="",
                   glow_blur=0, shadow=True, outline=True,
                   outline_color="#000000", outline_width=2, rounded=True),
    "second": dict(width=5, hand_length=205, tail_length=45, tip_style="needle",
                   color="#ff4444", tail_color="#ff2222", glow_color="#ff0000",
                   glow_blur=6, shadow=False, outline=False,
                   outline_color="#000000", outline_width=1, rounded=False),
}

# The designer adds this much padding on every side so the tip is not flush
# against the sprite edge, which the watch would clip.
PADDING = 10


def parse_color(value: str) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 6:
        value += "ff"
    if len(value) != 8:
        raise argparse.ArgumentTypeError(f"not a hex colour: {value!r}")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a hex colour: {value!r}") from None


def shade(colour: tuple[int, int, int, int], amount: int) -> tuple[int, int, int, int]:
    """Lighten (positive) or darken (negative) by a percentage, as the designer does."""
    r, g, b, a = colour
    if amount >= 0:
        f = lambda v: round(v + (255 - v) * amount / 100)  # noqa: E731
    else:
        f = lambda v: round(v * (1 + amount / 100))          # noqa: E731
    return (f(r), f(g), f(b), a)


def _cubic(p0: tuple[float, float], p1: tuple[float, float],
           p2: tuple[float, float], p3: tuple[float, float],
           steps: int = 24) -> list[tuple[float, float]]:
    """Sample a cubic bezier into points.

    Pillow has no bezier primitive, so the leaf outline -- which the designer
    draws with ctx.bezierCurveTo -- is sampled and handed to polygon(). More
    points than the shape needs is harmless; too few turns a leaf into a
    triangle.
    """
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        ))
    return out


def tip_polygon(style: str, cx: float, tip_y: float, pivot_y: float,
                tail_y: float, hw: float, tail_hw: float, tip_len: int,
                w: float) -> list[list[tuple[float, float]]]:
    """The hand's outline as one or more polygons, tip pointing UP.

    Returned as separate polygons rather than one path because a diamond or leaf
    hand is genuinely two disjoint shapes, and the designer fills each.
    """
    style = style.lower()
    if style == "sword":
        return [[(cx, tip_y),
                 (cx + 0.5, tail_y), (cx - 0.5, tail_y)],
                [(cx, tip_y),
                 (cx + hw, pivot_y - tip_len * 0.2),
                 (cx + tail_hw, pivot_y), (cx + tail_hw, tail_y),
                 (cx - tail_hw, tail_y), (cx - tail_hw, pivot_y),
                 (cx - hw, pivot_y - tip_len * 0.2)]]
    if style == "arrow":
        return [[(cx, tip_y),
                 (cx + hw, pivot_y - tip_len * 0.35),
                 (cx + hw * 0.4, pivot_y - tip_len * 0.35),
                 (cx + tail_hw, pivot_y), (cx + tail_hw, tail_y),
                 (cx - tail_hw, tail_y), (cx - tail_hw, pivot_y),
                 (cx - hw * 0.4, pivot_y - tip_len * 0.35),
                 (cx - hw, pivot_y - tip_len * 0.35)]]
    if style == "baton":
        # A plain rectangle, so one code path can draw it. The designer rounds
        # the ends with roundRect; render() uses rounded_rectangle for this.
        return [[(cx - hw, tip_y), (cx + hw, tip_y),
                 (cx + hw, tail_y), (cx - hw, tail_y)]]
    if style == "needle":
        return [[(cx, tip_y), (cx + 0.5, tail_y), (cx - 0.5, tail_y)]]
    if style == "club":
        return [[(cx, tip_y),
                 (cx + hw, tip_y + tip_len * 0.6), (cx + tail_hw, pivot_y),
                 (cx + tail_hw, tail_y), (cx - tail_hw, tail_y),
                 (cx - tail_hw, pivot_y), (cx - hw, tip_y + tip_len * 0.6)]]
    if style == "diamond":
        return [[(cx, tip_y), (cx + hw, pivot_y - tip_len * 0.5),
                 (cx, pivot_y - tip_len * 0.1), (cx - hw, pivot_y - tip_len * 0.5)],
                [(cx - tail_hw, pivot_y), (cx + tail_hw, pivot_y),
                 (cx + tail_hw, tail_y), (cx - tail_hw, tail_y)]]
    if style == "leaf":
        # A proper leaf: two mirrored bezier lobes, not a triangle.
        right = _cubic((cx, tip_y), (cx + hw * 1.5, tip_y + tip_len * 0.3),
                       (cx + hw, pivot_y - tip_len * 0.15), (cx, pivot_y))
        left = _cubic((cx, pivot_y), (cx - hw, pivot_y - tip_len * 0.15),
                      (cx - hw * 1.5, tip_y + tip_len * 0.3), (cx, tip_y))
        return [right + left,
                [(cx - tail_hw * 0.7, pivot_y), (cx + tail_hw * 0.7, pivot_y),
                 (cx + tail_hw * 0.5, tail_y), (cx - tail_hw * 0.5, tail_y)]]
    if style == "lollipop":
        return [[(cx - hw, tip_y), (cx + hw, tip_y), (cx + hw, tip_y + hw * 2),
                 (cx + tail_hw * 0.6, tip_y + hw * 2),
                 (cx + tail_hw * 0.6, tail_y),
                 (cx - tail_hw * 0.6, tail_y),
                 (cx - tail_hw * 0.6, tip_y + hw * 2), (cx - hw, tip_y + hw * 2)]]
    raise argparse.ArgumentTypeError(
        f"unknown tip style {style!r}; choose from {', '.join(HAND_STYLES)}")


def _draw_shapes(draw: ImageDraw.ImageDraw, polygons: list, style: str,
                 fill, cw: int, ch: int, w: float, hw: float, rounded: bool,
                 total_h: int, tip_y: float) -> None:
    """Fill the hand's shape(s).

    Only the baton differs: the designer rounds its ends with roundRect, and
    every other style is a polygon. Pillow's rounded_rectangle takes integer
    corners, so a 3px hand rounds to a lozenge either way.
    """
    if style == "baton" and rounded:
        draw.rounded_rectangle([cw / 2 - hw, tip_y, cw / 2 + hw, tip_y + total_h],
                               radius=max(1, round(hw)), fill=fill)
        return
    for poly in polygons:
        draw.polygon(poly, fill=fill)


def render(cfg: dict, scale: int = 1) -> tuple[Image.Image, dict]:
    w = round(cfg["width"] * scale)
    tip_len = round(cfg["hand_length"] * scale)
    tail_len = round(cfg["tail_length"] * scale)
    total_h = tip_len + tail_len
    cw = w + PADDING * 2
    # Force an even width. The pivot sits at width/2, and on an odd-width sprite
    # that is a half pixel, so the hand is off-centre by 0.5px once the watch
    # rotates it. Every hand in every real dial has an even width. (The designer
    # does not enforce this; a 5px-wide second hand gets a 25px sprite and a
    # pivot at 12.5.)
    if cw % 2:
        cw += 1
    ch = total_h + PADDING * 2

    # The designer's layout: the pivot sits 10px below the top of the sprite,
    # the tip reaches the top edge, and the tail hangs below the pivot.
    cx = cw / 2
    pivot_y = tip_len + PADDING
    tip_y = PADDING
    tail_y = pivot_y + tail_len

    hw = w / 2
    tail_w = max(w * 0.4, 2)
    tail_hw = tail_w / 2

    image = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    colour = parse_color(cfg["color"])
    polygons = tip_polygon(cfg["tip_style"], cx, tip_y, pivot_y, tail_y,
                           hw, tail_hw, tip_len, w)

    if cfg["glow_color"] and cfg["glow_blur"]:
        glow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        _draw_shapes(gdraw, polygons, cfg["tip_style"],
                     parse_color(cfg["glow_color"]), cw, ch, w, hw,
                     cfg["rounded"], total_h, tip_y)
        image.alpha_composite(
            glow.filter(ImageFilter.GaussianBlur(cfg["glow_blur"])))

    if cfg["shadow"]:
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        _draw_shapes(sdraw, polygons, cfg["tip_style"], (0, 0, 0, 153),
                     cw, ch, w, hw, cfg["rounded"], total_h, tip_y)
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(4)), (1, 1))

    # Outline BEFORE fill, the opposite of the designer. A 1px-wide needle with
    # a 2px black outline stroked on top of itself comes out solid black -- a
    # hand that is invisible against a dark dial. Stroking first and filling
    # over leaves the outline visible on the outside and the colour intact.
    if cfg["outline"] and cfg["outline_width"] > 0:
        outline = parse_color(cfg["outline_color"])
        if cfg["tip_style"] == "baton" and cfg["rounded"]:
            draw.rounded_rectangle(
                [cw / 2 - hw, tip_y, cw / 2 + hw, tip_y + total_h],
                radius=max(1, round(hw)), outline=outline,
                width=cfg["outline_width"])
        else:
            for poly in polygons:
                draw.line(poly + [poly[0]], fill=outline,
                          width=cfg["outline_width"])

    _draw_shapes(draw, polygons, cfg["tip_style"], colour, cw, ch, w, hw,
                 cfg["rounded"], total_h, tip_y)

    # The pivot, in the terms the block descriptor uses. cty from the left,
    # ctx from the BOTTOM -- see the module docstring.
    info = {
        "width": cw,
        "height": ch,
        "ctx": ch - pivot_y,
        "cty": round(cx),
        "pivot": {"x": round(cx), "y": round(pivot_y)},
        "pivot_y_from_top": round(pivot_y),
        "tip_reaches": {"top": round(tip_y), "tail_end": round(tail_y)},
    }
    return image, info


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", default="hour", choices=sorted(DEFAULTS),
                        help="preset geometry, and what the tip style defaults to")
    parser.add_argument("--tip-style", choices=HAND_STYLES,
                        help="override the preset's tip shape")
    parser.add_argument("--width", type=int, help="shaft width in px")
    parser.add_argument("--hand-length", type=int, help="pivot to tip, in px")
    parser.add_argument("--tail-length", type=int, help="pivot to tail end, in px")
    parser.add_argument("--scale", type=int, default=1,
                        help="multiply every length; use to match an existing dial")
    parser.add_argument("--color", help="hex, e.g. '#eef2f8'")
    parser.add_argument("--outline", dest="outline", action="store_true", default=None)
    parser.add_argument("--no-outline", dest="outline", action="store_false")
    parser.add_argument("--outline-color")
    parser.add_argument("--outline-width", type=int)
    parser.add_argument("--out", required=True, help="PNG to write")
    parser.add_argument("--json", action="store_true",
                        help="print the geometry as JSON")
    args = parser.parse_args()

    cfg = dict(DEFAULTS[args.type])
    if args.tip_style:
        cfg["tip_style"] = args.tip_style
    for key in ("width", "hand_length", "tail_length", "color",
                "outline_color", "outline_width"):
        value = getattr(args, key)
        if value is not None:
            cfg[key] = value
    if args.outline is not None:
        cfg["outline"] = args.outline

    image, info = render(cfg, args.scale)
    image.save(args.out)

    if args.json:
        print(json.dumps({"out": args.out, **info}, indent=2))
    else:
        print(f"{args.out}  {info['width']}x{info['height']}  "
              f"ctx={info['ctx']} cty={info['cty']}  "
              f"(pivot {info['pivot']['x']},{info['pivot']['y']})")
        print(f"  the block descriptor wants posx=233 posy=233 for the pivot, "
              f"frms=1, and these ctx/cty.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except argparse.ArgumentTypeError as exc:
        sys.exit(f"error: {exc}")
