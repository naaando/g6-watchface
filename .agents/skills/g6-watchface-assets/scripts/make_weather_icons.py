#!/usr/bin/env python3
"""Build a weather icon strip -- the art for BLK_WEATHER (0x19).

A port of the Fogg designer's WeatherGenerator, so the 12 frames land in the
same order a designer-built strip would.

    python3 make_weather_icons.py --out weather_strip.png
    python3 make_weather_icons.py --size 46 --stroke-width 2.4 --icon-color "#eef2f8"
    python3 make_weather_icons.py --list
    python3 make_weather_icons.py --json

FRAME ORDER IS THE CONTRACT
---------------------------
The watch picks the frame by weather CODE, not by position, so the array index
has to equal the code:

     0 Other / Desconocido     6 Thundershower / Tormenta con lluvia
     1 Sunny / Soleado         7 High-wind / Viento fuerte
     2 Cloudy / Nuboso         8 Snowy / Nevado
     3 Overcast / Cubierto     9 Foggy / Niebla
     4 Rainy / Lluvioso       10 Sandstorm / Tormenta de arena
     5 Thunder / Tormenta    11 Haze / Neblina

A strip with Sunny at frame 0 shows a cloud for clear skies all day, and
nothing about the rendered image reveals it. `--list` prints the table.

The block is 12 frames, always, and the shipped dial uses 46x46 per frame.

Why the icons are drawn rather than shipped as PNGs
--------------------------------------------------
The designer rasterizes lucide SVG paths through the browser. This script
parses the same paths and strokes them with Pillow, because there is no SVG
rasterizer available here (no cairosvg, no browser, no resvg) and adding a
dependency for twelve icons is not worth it. Two consequences, both
deliberate:

* Curves are flattened to line segments and arcs are sampled, so the result is
  within about half a pixel of the browser's rendering at this size. It is not
  byte-identical and never will be.
* `stroke-width` is in viewBox units and gets scaled with the icon, which is
  what the browser does too. A `--stroke-width 2` on a 24-unit viewBox drawn at
  32px is 2.67px on the watch.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _g6canvas import (  # noqa: E402
    Canvas,
    alpha_bbox,
    hex_to_rgb,
    lit_pixels,
    with_alpha,
)

VIEWBOX = 24.0
FRAMES = 12

# The block type this serves and the frame count it holds.
EXPECTED_FRAMES = {"BLK_WEATHER": {12}}

# WeatherGenerator.tsx:41-114. Paths are lucide icons on a 24x24 viewBox,
# stroke-only, no fill. Kept verbatim so this strip matches a designer-built
# one frame for frame.
ICONS = [
    {"code": 0, "name": "Other (Otro / Desconocido)", "lucide": "HelpCircle", "body": (
        '<circle cx="12" cy="12" r="10" />'
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />'
        '<path d="M12 17h.01" />')},
    {"code": 1, "name": "Sunny (Soleado)", "lucide": "Sun", "body": (
        '<circle cx="12" cy="12" r="4" />'
        '<path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41'
        'M2 12h2m16 0h2M6.34 17.66l-1.41 1.41m12.73-12.73l-1.41 1.41" />')},
    # KNOWN ODDITY in frame 2: the path traces a closed blob rather than a
    # recognisable cloud. It is reproduced as-is on purpose. Verified by
    # walking the geometry: the arc (15.9,10.9)->(9,17) has r=5.5 against a
    # 9.21-unit chord, `h5` closes the bottom to (14,17), and the return arc
    # (14,17)->(14,10) plus a short curve brings it back to (13.7,10.1). That
    # is a lozenge with a notch, not a cloud. Fogg's data, not a flattening
    # bug -- `test_assets.py` checks the arc maths independently.
    {"code": 2, "name": "Cloudy (Nuboso)", "lucide": "CloudSun", "body": (
        '<path d="M12 2v2M4.93 4.93l1.41 1.41M2 12h2M6.34 17.66l-1.41 1.41'
        'M19.07 4.93l-1.41 1.41" />'
        '<path d="M15.9 10.9A5.5 5.5 0 0 0 9 17h5a3.5 3.5 0 1 0 0-7'
        'c-.1 0-.2 0-.3.1" />')},
    {"code": 3, "name": "Overcast (Cubierto)", "lucide": "Cloud", "body": (
        '<path d="M17.5 19A3.5 3.5 0 0 0 21 15.5c0-2.79-2.54-4.5-5-4.5'
        '-.51 0-1-.07-1.5-.2-1-1.89-3-3.8-5.5-3.8A5 5 0 0 0 4 12'
        'c0 .48.06.94.18 1.38A3.5 3.5 0 0 0 3.5 20h14" />')},
    {"code": 4, "name": "Rainy (Lluvioso)", "lucide": "CloudRain", "body": (
        '<path d="M17.5 19A3.5 3.5 0 0 0 21 15.5c0-2.79-2.54-4.5-5-4.5'
        '-.51 0-1-.07-1.5-.2-1-1.89-3-3.8-5.5-3.8A5 5 0 0 0 4 12'
        'c0 .48.06.94.18 1.38A3.5 3.5 0 0 0 3.5 20h14" />'
        '<path d="M8 22v-2m4 2v-2m4 2v-2" />')},
    {"code": 5, "name": "Thunder (Tormenta)", "lucide": "CloudLightning", "body": (
        '<path d="M19 16.9A5 5 0 0 0 18 7h-1.26a8 8 0 1 0-11.62 8.58" />'
        '<path d="M13 11l-4 6h6l-3 5" />')},
    {"code": 6, "name": "Thundershower (Tormenta con lluvia)", "lucide": "CloudLightning", "body": (
        '<path d="M19 16.9A5 5 0 0 0 18 7h-1.26a8 8 0 1 0-11.62 8.58" />'
        '<path d="M13 11l-3 5h4l-2 4" />'
        '<path d="M8 18v2m8-2v2" />')},
    {"code": 7, "name": "High-wind (Viento fuerte)", "lucide": "Wind", "body": (
        '<path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2M9.6 4.6A2 2 0 1 1 11 8H2'
        'M12.6 19.4A2 2 0 1 0 14 16H2" />')},
    {"code": 8, "name": "Snowy (Nevado)", "lucide": "Snowflake", "body": (
        '<path d="M2 12h20M12 2v20m8-4-4-4 4-4M4 8l4 4-4 4m12 4-4-4-4 4M8 4l4 4 4-4" />')},
    {"code": 9, "name": "Foggy (Niebla)", "lucide": "CloudFog", "body": (
        '<path d="M17.5 19A3.5 3.5 0 0 0 21 15.5c0-2.79-2.54-4.5-5-4.5'
        '-.51 0-1-.07-1.5-.2-1-1.89-3-3.8-5.5-3.8A5 5 0 0 0 4 12'
        'c0 .48.06.94.18 1.38A3.5 3.5 0 0 0 3.5 20h14" />'
        '<path d="M4 22h16M6 19h12" />')},
    {"code": 10, "name": "Sandstorm (Tormenta de arena)", "lucide": "Tornado", "body": (
        '<path d="M21 4H3m17 4H4m14 4H6m9 4H9m4 4h-2" />')},
    {"code": 11, "name": "Haze (Neblina)", "lucide": "SunLow", "body": (
        '<path d="M18 10a6 6 0 1 0-12 0" />'
        '<path d="M2 22h20M6 18h12M8 14h8" />')},
]

# Flattening resolution, in viewBox units per segment. The icons are 24 units
# across and render at ~32-48px, so ~0.25 units (about half a pixel) is well
# past the point where flattening shows.
CURVE_STEPS = 16
ARC_STEP_DEGREES = 4.0

_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_TOKEN = re.compile(r"([MmLlHhVvCcAaZzSsQqTt])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")


def _tokenize(path_data: str):
    for match in _TOKEN.finditer(path_data):
        command, number = match.group(1), match.group(2)
        yield command if command else float(number)


def _flatten_cubic(p0, p1, p2, p3, steps=CURVE_STEPS):
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1.0 - t
        a, b, c, d = mt ** 3, 3 * mt * mt * t, 3 * mt * t * t, t ** 3
        points.append((
            a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
        ))
    return points


def _flatten_arc(start, rx, ry, rotation, large_arc, sweep, end, steps=None):
    """SVG endpoint-parameterised elliptical arc -> points.

    The implementation from the SVG spec appendix (F.6.5), not a shortcut.
    Skipping the out-of-range radius correction is the usual shortcut and it
    matters here: `A5.5 5.5` in CloudSun and `A6 6` in Haze are both large
    enough relative to the endpoints that scaling them up changes the visible
    shape of the cloud.
    """
    x1, y1 = start
    x2, y2 = end
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(float(rx)), abs(float(ry))
    if rx == 0 or ry == 0:
        return [end]

    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    # Radii that are too small get scaled up instead of failing, per spec.
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale

    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if bool(large_arc) == bool(sweep):
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle_of(ux, uy):
        return math.atan2(uy, ux)

    theta1 = angle_of((x1p - cxp) / rx, (y1p - cyp) / ry)
    theta2 = angle_of((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    delta = theta2 - theta1
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    if steps is None:
        steps = max(2, int(abs(math.degrees(delta)) / ARC_STEP_DEGREES) + 2)
    points = []
    for i in range(1, steps + 1):
        theta = theta1 + delta * (i / steps)
        px = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + cx
        py = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + cy
        points.append((px, py))
    return points


def parse_path(path_data: str):
    """Path data -> list of subpaths, each a list of (x, y) in viewBox units.

    Supports M m L l H h V v C c A a Z z, which is the whole vocabulary the
    twelve lucide icons use. S/s and Q/q are accepted and promoted to their
    cubic equivalents, so an icon that uses smooth curves does not silently
    lose them.
    """
    tokens = list(_tokenize(path_data))
    subpaths, current = [], []
    cursor = (0.0, 0.0)
    start = (0.0, 0.0)
    command = None
    prev_cubic_control = None
    prev_quad_control = None
    index = 0

    def take(n):
        nonlocal index
        values = tokens[index:index + n]
        index += n
        if len(values) < n or any(isinstance(v, str) for v in values):
            raise ValueError(f"malformed path data near token {index}: {path_data!r}")
        return [float(v) for v in values]

    def flush():
        if len(current) > 1:
            subpaths.append(list(current))
        current.clear()

    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command = token
            index += 1
        elif command is None:
            raise ValueError(f"path data starts with a number: {path_data!r}")
        elif command in "Mm":
            command = "L" if command == "M" else "l"

        if command in "Zz":
            flush()
            cursor = start
            command = None
            continue

        relative = command.islower()
        upper = command.upper()
        if upper == "M":
            x, y = take(2)
            if relative:
                x, y = cursor[0] + x, cursor[1] + y
            flush()
            current.append((x, y))
            cursor = (x, y)
            start = cursor
            prev_cubic_control = prev_quad_control = None
        elif upper == "L":
            x, y = take(2)
            if relative:
                x, y = cursor[0] + x, cursor[1] + y
            current.append((x, y))
            cursor = (x, y)
            prev_cubic_control = prev_quad_control = None
        elif upper == "H":
            (x,) = take(1)
            if relative:
                x = cursor[0] + x
            current.append((x, cursor[1]))
            cursor = (x, cursor[1])
            prev_cubic_control = prev_quad_control = None
        elif upper == "V":
            (y,) = take(1)
            if relative:
                y = cursor[1] + y
            current.append((cursor[0], y))
            cursor = (cursor[0], y)
            prev_cubic_control = prev_quad_control = None
        elif upper == "C":
            x1, y1, x2, y2, x, y = take(6)
            if relative:
                x1, y1 = cursor[0] + x1, cursor[1] + y1
                x2, y2 = cursor[0] + x2, cursor[1] + y2
                x, y = cursor[0] + x, cursor[1] + y
            current.extend(_flatten_cubic(cursor, (x1, y1), (x2, y2), (x, y)))
            prev_cubic_control = (x2, y2)
            prev_quad_control = None
            cursor = (x, y)
        elif upper == "S":
            x2, y2, x, y = take(4)
            if relative:
                x2, y2 = cursor[0] + x2, cursor[1] + y2
                x, y = cursor[0] + x, cursor[1] + y
            if prev_cubic_control is None:
                x1, y1 = cursor
            else:
                x1 = 2 * cursor[0] - prev_cubic_control[0]
                y1 = 2 * cursor[1] - prev_cubic_control[1]
            current.extend(_flatten_cubic(cursor, (x1, y1), (x2, y2), (x, y)))
            prev_cubic_control = (x2, y2)
            prev_quad_control = None
            cursor = (x, y)
        elif upper == "Q":
            qx, qy, x, y = take(4)
            if relative:
                qx, qy = cursor[0] + qx, cursor[1] + qy
                x, y = cursor[0] + x, cursor[1] + y
            # Promote the quadratic to a cubic; the control point moves to the
            # two-thirds point and the implied second control mirrors it.
            c1 = (cursor[0] + 2.0 / 3.0 * (qx - cursor[0]),
                  cursor[1] + 2.0 / 3.0 * (qy - cursor[1]))
            c2 = (x + 2.0 / 3.0 * (qx - x), y + 2.0 / 3.0 * (qy - y))
            current.extend(_flatten_cubic(cursor, c1, c2, (x, y)))
            prev_quad_control = (qx, qy)
            prev_cubic_control = None
            cursor = (x, y)
        elif upper == "A":
            rx, ry, rot, large, sweep, x, y = take(7)
            if relative:
                x, y = cursor[0] + x, cursor[1] + y
            current.extend(_flatten_arc(cursor, rx, ry, rot, bool(int(large)),
                                        bool(int(sweep)), (x, y)))
            cursor = (x, y)
            prev_cubic_control = prev_quad_control = None
        else:
            raise ValueError(f"unsupported path command {command!r} in {path_data!r}")

    flush()
    return subpaths


def icon_subpaths(icon):
    """Every stroked subpath for one icon, circles included as polylines."""
    subpaths = []
    for tag in re.findall(r"<(circle|path)\b([^>]*)>", icon["body"]):
        kind, attrs = tag
        if kind == "path":
            data = re.search(r'\sd="([^"]*)"', attrs)
            if data:
                subpaths.extend(parse_path(data.group(1)))
        else:
            cx = float(re.search(r'\scx="([^"]*)"', attrs).group(1))
            cy = float(re.search(r'\scy="([^"]*)"', attrs).group(1))
            r = float(re.search(r'\sr="([^"]*)"', attrs).group(1))
            points, steps = [], 64
            for i in range(steps + 1):
                t = 2 * math.pi * i / steps
                points.append((cx + r * math.cos(t), cy + r * math.sin(t)))
            subpaths.append(points)
    return subpaths


def build(cfg):
    fw, fh, ss = cfg["frame_width"], cfg["frame_height"], cfg["supersample"]
    size = min(fw, fh) - cfg["icon_padding"] * 2
    if size < 4:
        raise ValueError(
            f"icon size collapses to {size}px: min(frame_width, frame_height) is "
            f"{min(fw, fh)} and icon_padding is {cfg['icon_padding']}"
        )
    # The viewBox is 24 units and stroke-width is in those units, so the stroke
    # scales with the icon. The browser does the same; hard-coding pixels here
    # would make a 46px dial's icons visibly heavier than a 32px one's.
    scale = size / VIEWBOX
    stroke = cfg["stroke_width"] * scale
    colour = with_alpha(hex_to_rgb(cfg["icon_color"]), 255)
    offset_x = (fw - size) / 2.0
    offset_y = (fh - size) / 2.0

    strip = Canvas(fw, fh * FRAMES, ss)
    if cfg["bg_color"] != "transparent":
        strip.fill_rect(0, 0, fw, fh * FRAMES,
                        with_alpha(hex_to_rgb(cfg["bg_color"]), 255))
    for index, icon in enumerate(ICONS):
        frame = Canvas(fw, fh, ss)
        for points in icon_subpaths(icon):
            placed = [(x * scale + offset_x, y * scale + offset_y) for x, y in points]
            frame.stroke_polyline(placed, colour, stroke, caps="round")
        strip.blit_canvas(frame, 0, index * fh)
    return strip.finish()


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Build a 12-frame weather icon strip (vertical: frames stacked top to bottom).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--out", help="output PNG")
    p.add_argument("--frame-width", type=int, default=48)
    p.add_argument("--frame-height", type=int, default=48)
    p.add_argument("--icon-color", default="#ffffff")
    p.add_argument("--bg-color", default="transparent", help="'transparent' or a hex colour")
    p.add_argument("--stroke-width", type=float, default=2.0,
                   help="in viewBox units (24 across), so it scales with the icon")
    p.add_argument("--icon-padding", type=float, default=8)
    p.add_argument("--block-type", default=None, help="validate the frame count")
    p.add_argument("--supersample", type=int, default=4, help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true", help="print a JSON report")
    p.add_argument("--list", action="store_true",
                   help="print the frame order and exit; --out is not required")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.list:
        print("frame  code  name")
        for icon in ICONS:
            print(f"  {icon['code']:>2}   0x{icon['code']:02X}  {icon['name']}")
        print("\nThe watch selects the frame by weather code, so this order is a contract.")
        return 0

    if not args.out:
        print("--out is required (or use --list)", file=sys.stderr)
        return 1
    if args.frame_width < 4 or args.frame_height < 4:
        print("frame size is too small to draw anything", file=sys.stderr)
        return 1

    if args.block_type:
        expected = EXPECTED_FRAMES.get(args.block_type)
        if expected is not None and FRAMES not in expected:
            print(f"{args.block_type} holds {sorted(expected)} frame(s), not {FRAMES}",
                  file=sys.stderr)
            return 1

    cfg = {
        "frame_width": args.frame_width,
        "frame_height": args.frame_height,
        "icon_color": args.icon_color,
        "bg_color": args.bg_color,
        "stroke_width": args.stroke_width,
        "icon_padding": args.icon_padding,
        "supersample": max(1, args.supersample),
    }
    try:
        strip = build(cfg)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)

    report = {
        "out": str(out),
        "width": strip.width,
        "height": strip.height,
        "frame_width": cfg["frame_width"],
        "frame_height": cfg["frame_height"],
        "frames": FRAMES,
        "frames_detail": [],
    }
    for index, icon in enumerate(ICONS):
        frame = strip.crop((0, index * cfg["frame_height"], cfg["frame_width"],
                            (index + 1) * cfg["frame_height"]))
        report["frames_detail"].append({
            "index": index,
            "code": icon["code"],
            "name": icon["name"],
            # Strict box, including the LANCZOS ringing tail. Kept because it is
            # the honest "did anything at all land here" measure.
            "alpha_bbox": alpha_bbox(frame),
            # The box a bounds/clipping check should use -- see alpha_bbox.
            "ink_bbox": alpha_bbox(frame, threshold=8),
            "lit_pixels": lit_pixels(frame),
        })

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{out}  {strip.width}x{strip.height}  {FRAMES} frames")
        for row in report["frames_detail"]:
            print(f"  frame {row['index']:>2}  code {row['code']:>2}  "
                  f"{row['name']:<44} {row['lit_pixels']:>5} px  "
                  f"bbox {row['alpha_bbox']}  ink {row['ink_bbox']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
