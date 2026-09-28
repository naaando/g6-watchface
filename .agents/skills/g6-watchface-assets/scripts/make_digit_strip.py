#!/usr/bin/env python3
"""Generate a vertical glyph strip for an HK89 dial block.

A Python port of Fogg's `FontGenerator.tsx`, kept behaviour-compatible so a
strip produced here drops into the same block a strip produced in the designer
would have. The designer is the reference; where the two differ it is because
Pillow and canvas measure text differently, and those spots are called out in
the notes below.

    python3 make_digit_strip.py --preset digits --font "DIN Condensed Bold.ttf" \\
        --size 49 --frame-width 36 --frame-height 52 --out hours.png

Every block in a `.bin` expects its frames stacked TOP TO BOTTOM in one image
(width x height*frames), never side by side. That is the single most common
mistake when hand-rolling these, and it looks plausible enough to ship: frame 0
of a battery gauge is a valid-looking gauge.

Frame counts are not arbitrary. Pass --block-type to have them checked:

    BLK_WEEKD    7   SUN..SAT
    BLK_MONTH   10   digits, or 12 for month NAMES
    BLK_BIGYO    1   a single separator glyph
    everything else (BLK_HOUR, BLK_MIN, BLK_SEC, BLK_STEPS, ...)  10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# The designer's AUTO_FIT_PADDING. The cell is padded by this much on each side
# so a stroke or a glow is not flush against the cell edge, which the watch
# would then clip.
AUTO_FIT_PADDING = 6

PRESET_LISTS = {
    "digits": [str(n) for n in range(10)],
    "weekdays_en": ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"],
    "weekdays_es": ["DOM", "LUN", "MAR", "MIE", "JUE", "VIE", "SAB"],
    "months_en": ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
    "months_es": ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
                  "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"],
    "months_fr": ["JAN", "FEV", "MAR", "AVR", "MAI", "JUN",
                  "JUL", "AOU", "SEP", "OCT", "NOV", "DEC"],
}

# (block type, count) pairs the designer enforces. Mirrors the validation in
# FontGenerator.tsx around line 553.
EXPECTED_FRAMES = {
    "BLK_WEEKD": {7},
    "BLK_MONTH": {10, 12},
    "BLK_BIGYO": {1},
}
DEFAULT_FRAMES = 10

# Where to look for a font when --font is a bare name. Fogg pulls webfonts from
# Google; a script cannot, so resolve against these instead.
FONT_DIRS = [
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    str(Path.home() / "Library/Fonts"),
]


def resolve_font(name: str) -> Path:
    """Accept a path, a filename, or a bare family name."""
    direct = Path(name)
    if direct.is_file():
        return direct
    stem = name if name.lower().endswith((".ttf", ".otf")) else f"{name}.ttf"
    for directory in FONT_DIRS:
        candidate = Path(directory) / stem
        if candidate.is_file():
            return candidate
        # Case-insensitive fallback, since macOS is the usual host here.
        if Path(directory).is_dir():
            for entry in Path(directory).iterdir():
                if entry.name.lower() == stem.lower():
                    return entry
    sys.exit(
        f"font not found: {name!r}\n"
        f"Pass a full path, or a name present in one of: {', '.join(FONT_DIRS)}"
    )


def items_from_args(args: argparse.Namespace) -> list[str]:
    if args.items is not None:
        return [line.strip() for line in args.items.splitlines() if line.strip()]
    if args.preset:
        return list(PRESET_LISTS[args.preset])
    sys.exit("give --preset, or --items with one entry per line")


def expected_frames(block_type: str | None, count: int) -> set[int] | None:
    if block_type is None:
        return None
    return EXPECTED_FRAMES.get(block_type, {DEFAULT_FRAMES})


def item_extents(draw: ImageDraw.ImageDraw, text: str,
                 font: ImageFont.FreeTypeFont, stroke_width: int,
                 letter_spacing: int) -> tuple[float, float, float, float] | None:
    """Ink box of one item, stroke included, as (x0, y0, x1, y1).

    Returns None for an item that renders to nothing (an empty string, or a
    glyph the font does not have).
    """
    if not text:
        return None
    kwargs = {"font": font, "stroke_width": stroke_width} if stroke_width else {"font": font}
    if not letter_spacing or len(text) < 2:
        return draw.textbbox((0, 0), text, **kwargs)
    # Letter spacing is drawn by hand, so measure the run of characters and
    # shift each one along.
    boxes = [draw.textbbox((0, 0), ch, **kwargs) for ch in text]
    if all(b is None or b[2] <= b[0] for b in boxes):
        return None
    offset = 0.0
    left, top, right, bottom = None, None, None, None
    for ch, box in zip(text, boxes):
        if box[2] > box[0]:
            left = box[0] + offset if left is None else min(left, box[0] + offset)
            top = box[1] if top is None else min(top, box[1])
            right = box[2] + offset if right is None else max(right, box[2] + offset)
            bottom = box[3] if bottom is None else max(bottom, box[3])
        offset += draw.textlength(ch, font=font) + letter_spacing
    return None if left is None else (left, top, right, bottom)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               stroke_width: int, letter_spacing: int) -> float:
    """Ink width of one item, stroke included.

    Measured from the ink box rather than the advance width, because the ink is
    what the cell has to contain. Canvas `measureText` returns the advance
    width instead, which is why the designer's auto-fit can leave a descender
    or a wide stroke touching the cell edge.
    """
    box = item_extents(draw, text, font, stroke_width, letter_spacing)
    return 0.0 if box is None else float(box[2] - box[0])


def draw_item(draw: ImageDraw.ImageDraw, text: str, centre_x: float, centre_y: float,
              font: ImageFont.FreeTypeFont, fill: str, stroke_width: int,
              stroke_fill: str, letter_spacing: int) -> None:
    """Draw one item with its INK centred on (centre_x, centre_y).

    This is a deliberate departure from the designer, which sets canvas
    `textBaseline = 'middle'` and therefore centres the font's
    ascender-to-descender box. On a face like DIN Condensed those two boxes
    differ by several pixels, and em-box centring leaves the digit visibly
    high in a tight cell. Centring the ink is what `build_silver_cat.py` does
    and what looks right on the device.

    NOTE on letter spacing: Pillow cannot space glyphs, so a multi-character
    item is drawn one character at a time. Single-character items (all digits)
    skip this path entirely and are exact.
    """
    box = item_extents(draw, text, font, stroke_width, letter_spacing)
    if box is None:
        return
    x0, y0, x1, y1 = box
    left = centre_x - (x1 - x0) / 2 - x0
    top = centre_y - (y1 - y0) / 2 - y0

    kwargs = dict(font=font, fill=fill)
    if stroke_width:
        kwargs.update(stroke_width=stroke_width, stroke_fill=stroke_fill)
    # textbbox() takes the font and stroke but not the paint.
    box_kwargs = dict(font=font)
    if stroke_width:
        box_kwargs["stroke_width"] = stroke_width

    if not letter_spacing or len(text) < 2:
        draw.text((left, top), text, **kwargs)
        return

    offset = 0.0
    for ch in text:
        char_box = draw.textbbox((0, 0), ch, **box_kwargs)
        if char_box[2] > char_box[0]:
            char_width = draw.textlength(ch, font=font)
            # Align this character's ink to the run's ink line, which is what
            # the unspaced draw would have produced.
            draw.text((left - x0 + offset, top), ch, **kwargs)
            offset += char_width + letter_spacing


def render(items: list[str], font: ImageFont.FreeTypeFont, frame_width: int,
           frame_height: int, digit_spacing: int, fill: str, background: str,
           stroke_width: int, stroke_fill: str, shadow: dict,
           letter_spacing: int, offset_x: int, offset_y: int) -> Image.Image:
    """The strip, plus the alpha bounding box of every frame."""
    cell_width = max(4, frame_width + digit_spacing)
    strip = Image.new("RGBA", (cell_width, frame_height * len(items)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)
    if background != "transparent":
        draw.rectangle([0, 0, strip.width, strip.height], fill=background)

    for index, item in enumerate(items):
        centre_x = cell_width / 2 + offset_x
        centre_y = index * frame_height + frame_height / 2 + offset_y
        draw_item(draw, item, centre_x, centre_y, font, fill,
                  stroke_width, stroke_fill, letter_spacing)

    if shadow.get("blur", 0) > 0:
        # Canvas applies a shadow behind the glyph. Pillow has no equivalent,
        # so render the glyphs alone, blur that, and lay it underneath.
        shadow_layer = Image.new("RGBA", strip.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        for index, item in enumerate(items):
            draw_item(shadow_draw, item,
                      cell_width / 2 + offset_x + shadow.get("x", 0),
                      index * frame_height + frame_height / 2 + offset_y
                      + shadow.get("y", 0),
                      font, shadow["color"], stroke_width, shadow_fill,
                      letter_spacing)
        shadow_layer = shadow_layer.filter(
            ImageFilter.GaussianBlur(radius=shadow["blur"] / 2))
        strip = Image.alpha_composite(shadow_layer, strip)

    return strip


def covered_codepoints(font_path: Path) -> set[int] | None:
    """The font's cmap, or None if fontTools is not installed.

    This is the authoritative answer to "does this font have this character".
    Comparing rendered pixels works too, but only if the canary character is
    genuinely absent — a Private Use codepoint is not a safe bet, because DIN
    Condensed Bold actually has U+E000.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    try:
        return set(TTFont(str(font_path), lazy=True).getBestCmap())
    except Exception:  # a font fontTools cannot parse; do not block on it
        return None


def find_missing_glyphs(items: list[str], font_path: Path) -> list[int]:
    """Indices of items the font does not actually have.

    Pillow does not raise for a character the font lacks. It draws .notdef,
    which for most fonts is a hollow rectangle, and that rectangle is
    indistinguishable from a real glyph by eye. So a strip can ship with a tofu
    box where '5' should be and nothing complains.
    """
    covered = covered_codepoints(font_path)
    if covered is None:
        return []
    return [i for i, item in enumerate(items)
            if any(ord(ch) not in covered for ch in item)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", choices=sorted(PRESET_LISTS),
                        help="built-in character set")
    parser.add_argument("--items", help="one entry per line, overrides --preset")
    parser.add_argument("--block-type",
                        help="check the frame count against this block, e.g. BLK_WEEKD")
    parser.add_argument("--font", default="DIN Condensed Bold.ttf",
                        help="path, filename, or family name")
    parser.add_argument("--size", type=int, default=32)
    parser.add_argument("--frame-width", type=int, default=32,
                        help="cell width before --digit-spacing is added")
    parser.add_argument("--frame-height", type=int, default=48)
    parser.add_argument("--digit-spacing", type=int, default=0,
                        help="extra cell width; this is the gap BETWEEN digits "
                             "the watch renders side by side, not tracking")
    parser.add_argument("--letter-spacing", type=int, default=0,
                        help="tracking INSIDE a multi-character item, e.g. JAN")
    parser.add_argument("--autofit-width", action="store_true",
                        default=True,
                        help="grow/shrink the cell to hug the glyphs (default)")
    parser.add_argument("--fixed-width", dest="autofit_width", action="store_false",
                        help="use --frame-width verbatim")
    parser.add_argument("--color", default="#ffffff")
    parser.add_argument("--bg", default="transparent",
                        help="'transparent' or a hex colour")
    parser.add_argument("--stroke", default="#000000")
    parser.add_argument("--stroke-width", type=int, default=0)
    parser.add_argument("--shadow-color", default="rgba(0,0,0,0.5)")
    parser.add_argument("--shadow-blur", type=int, default=0)
    parser.add_argument("--shadow-x", type=int, default=0)
    parser.add_argument("--shadow-y", type=int, default=0)
    parser.add_argument("--offset-x", type=int, default=0)
    parser.add_argument("--offset-y", type=int, default=0)
    parser.add_argument("--out", required=True, help="PNG to write")
    parser.add_argument("--json", action="store_true",
                        help="print a machine-readable summary")
    args = parser.parse_args()

    items = items_from_args(args)

    allowed = expected_frames(args.block_type, len(items))
    if allowed is not None and len(items) not in allowed:
        wanted = " or ".join(
            f"{n} frame{'s' if n != 1 else ''}" for n in sorted(allowed))
        hint = {
            7: "A weekday block is 7 frames, Sunday first.",
            10: "A 10-frame month block holds digits; a 12-frame one holds names.",
            12: "A 12-frame month block holds month NAMES; a 10-frame one holds digits.",
            1: "A separator block holds exactly one glyph.",
        }.get(sorted(allowed)[0], "")
        sys.exit(f"{args.block_type} expects {wanted}, got {len(items)}."
                 + (f"\n{hint}" if hint else ""))

    font_path = resolve_font(args.font)
    font = ImageFont.truetype(str(font_path), args.size)
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    missing = find_missing_glyphs(items, font_path)
    if missing:
        # Refuse before writing anything, so a failed run leaves no file that
        # looks like a finished asset.
        sys.exit(
            f"font {font_path.name} has no glyph for items {missing}: "
            f"{[items[i] for i in missing]}\n"
            f"Pillow draws a .notdef box for these, which is indistinguishable from "
            f"a real character. Pick a font that covers the text."
        )

    frame_width = args.frame_width
    if args.autofit_width:
        widest = max(text_width(scratch, item, font, args.stroke_width,
                                args.letter_spacing) for item in items)
        # The stroke is already inside the ink box above, so this only has to
        # cover the cell padding. Floor at 4px: a cell narrower than one stroke
        # would silently lose pixels at the cell edge.
        frame_width = max(4, int(widest + AUTO_FIT_PADDING * 2 + 0.999))

    shadow = {"color": args.shadow_color, "blur": args.shadow_blur,
              "x": args.shadow_x, "y": args.shadow_y}
    strip = render(items, font, frame_width, args.frame_height,
                   args.digit_spacing, args.color, args.bg,
                   args.stroke_width, args.stroke, shadow,
                   args.letter_spacing, args.offset_x, args.offset_y)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)

    # Per-frame alpha bbox. The watch advances a digit by the full cell width,
    # so the cell has to be measured, not guessed, when a strip is being lined
    # up against art drawn around it.
    boxes = []
    for index in range(len(items)):
        cell = strip.crop((0, index * args.frame_height,
                           strip.width, (index + 1) * args.frame_height))
        boxes.append(cell.getchannel("A").getbbox())

    summary = {
        "out": str(out),
        "font": str(font_path),
        "size": args.size,
        "width": strip.width,
        "height": strip.height,
        "frame_width": strip.width,
        "frame_height": args.frame_height,
        "frms": len(items),
        "items": items,
        "alpha_bboxes": boxes,
        "blank_frames": [i for i, b in enumerate(boxes) if b is None],
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{out}  {strip.width}x{strip.height}  frms={len(items)} "
              f"cell={strip.width}x{args.frame_height}")
        if summary["blank_frames"]:
            print(f"  WARNING blank frames: {summary['blank_frames']} "
                  f"(a glyph that renders to nothing is a font/size problem, "
                  f"not a strip problem)")


if __name__ == "__main__":
    main()
