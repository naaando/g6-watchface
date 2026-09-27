"""Build an original cat-themed gauge dial for the 466px G6 display."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent / "cat-gauge"
ASSETS = ROOT / "assets"
SOURCE = Path(__file__).resolve().parent / "decoded_11448"
SIZE = 466
SCALE = 3
CYAN = "#52e5f1"
PALE = "#e1f1f6"
INK = "#07111a"
RED = "#de495b"
FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"


def sc(value: float) -> int:
    return round(value * SCALE)


def box(coords: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(sc(v) for v in coords)


def pt(coords: tuple[float, float]) -> tuple[int, int]:
    return sc(coords[0]), sc(coords[1])


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, sc(size))


def make_background() -> Image.Image:
    im = Image.new("RGB", (sc(SIZE), sc(SIZE)), "#05090f")
    d = ImageDraw.Draw(im)
    d.ellipse(box((2, 2, 464, 464)), fill="#071019", outline="#20343f", width=sc(4))
    d.ellipse(box((18, 18, 448, 448)), fill="#09141e", outline="#142832", width=sc(2))
    d.ellipse(box((44, 44, 422, 422)), outline="#1e3c49", width=sc(3))

    # A tachometer arc, calibrated to the round watch display.
    d.arc(box((33, 33, 433, 433)), 140, 325, fill=CYAN, width=sc(17))
    d.arc(box((57, 57, 409, 409)), 304, 337, fill=RED, width=sc(12))
    for degrees in range(145, 326, 10):
        a = math.radians(degrees)
        outer = 205
        inner = 188 if degrees % 30 == 5 else 196
        p1 = (233 + math.cos(a) * inner, 233 + math.sin(a) * inner)
        p2 = (233 + math.cos(a) * outer, 233 + math.sin(a) * outer)
        d.line((pt(p1), pt(p2)), fill=PALE if degrees % 30 == 5 else "#65a8b6", width=sc(2))

    # The original game gauge has a bright animal face. This cat is drawn anew.
    d.polygon([pt(p) for p in ((103, 174), (96, 79), (184, 137))], fill="#050d16")
    d.polygon([pt(p) for p in ((217, 137), (297, 89), (300, 183))], fill="#050d16")
    d.polygon([pt(p) for p in ((113, 156), (111, 103), (165, 143))], fill="#8db4c2")
    d.polygon([pt(p) for p in ((237, 145), (283, 107), (284, 168))], fill="#8db4c2")
    d.polygon([pt(p) for p in ((119, 153), (119, 119), (150, 142))], fill="#c9687b")
    d.polygon([pt(p) for p in ((252, 143), (278, 123), (278, 157))], fill="#c9687b")
    d.ellipse(box((67, 127, 308, 371)), fill="#b5cbd3", outline="#07111a", width=sc(9))
    d.ellipse(box((78, 136, 260, 313)), fill="#d4e3e8")
    d.ellipse(box((117, 179, 151, 218)), fill=INK)
    d.ellipse(box((124, 184, 134, 199)), fill="#f1fcff")
    d.arc(box((215, 175, 269, 220)), 190, 346, fill=INK, width=sc(7))
    d.polygon([pt(p) for p in ((175, 246), (210, 246), (193, 263))], fill="#273842")
    d.arc(box((147, 246, 196, 295)), 0, 138, fill=INK, width=sc(5))
    d.arc(box((190, 246, 240, 296)), 40, 180, fill=INK, width=sc(5))
    d.ellipse(box((187, 280, 208, 298)), fill="#d77285")
    for x1, y1, x2, y2 in ((104, 258, 59, 249), (104, 272, 59, 277), (274, 259, 320, 249), (275, 273, 321, 282)):
        d.line((pt((x1, y1)), pt((x2, y2))), fill="#223944", width=sc(3))
    d.arc(box((83, 151, 288, 355)), 25, 98, fill="#7c9ca7", width=sc(3))

    # Gauge-style digital readout. The numbers are supplied by live sprite blocks.
    d.rounded_rectangle(box((277, 261, 432, 354)), radius=sc(13), fill="#06111b", outline="#3c7a88", width=sc(2))
    d.text(pt((293, 266)), "TIME", font=font(14), fill=CYAN)
    d.text(pt((353, 294)), ":", font=font(47), fill=CYAN, anchor="lt")
    d.text(pt((291, 348)), "HOURS     MINUTES", font=font(10), fill="#749ba8", anchor="lt")
    d.text(pt((64, 386)), "CAT GAUGE", font=font(20), fill="#bcd5dc")
    d.text(pt((319, 387)), "G6", font=font(16), fill="#6faab7")
    return im.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def make_digits() -> Image.Image:
    width, height = 28, 58
    strip = Image.new("RGBA", (sc(width), sc(height * 10)), (0, 0, 0, 0))
    d = ImageDraw.Draw(strip)
    for digit in range(10):
        d.text(pt((2, digit * height - 1)), str(digit), font=font(60), fill=PALE)
    return strip.resize((width, height * 10), Image.Resampling.LANCZOS)


def make_hand(width: int, height: int, ctx: int, cty: int, color: str, second: bool = False) -> Image.Image:
    im = Image.new("RGBA", (sc(width), sc(height)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = ctx
    if second:
        d.line((pt((x, 6)), pt((x, cty + 15))), fill=color, width=sc(2))
        d.ellipse(box((x - 3, cty - 3, x + 3, cty + 3)), fill=color)
    else:
        d.polygon([pt(p) for p in ((x, 5), (x + 4, cty - 10), (x + 3, cty + 8), (x - 3, cty + 8), (x - 4, cty - 10))], fill=color)
        d.ellipse(box((x - 5, cty - 5, x + 5, cty + 5)), fill="#06111b", outline=color, width=sc(2))
    return im.resize((width, height), Image.Resampling.LANCZOS)


def tint_original_hand(name: str, light_color: str) -> Image.Image:
    """Keep the verified G6 hand geometry and change only its palette."""
    original = Image.open(SOURCE / name).convert("RGBA")
    tinted = ImageOps.colorize(ImageOps.grayscale(original), black="#06111b", white=light_color).convert("RGBA")
    tinted.putalpha(original.getchannel("A"))
    return tinted


def layer(kind: str, fname: str, width: int, height: int, x: int, y: int,
          frames: int = 1, colors: str = "RGBA", align: int = 9,
          compression: int = 4, ctx: int = 0, cty: int = 0) -> dict:
    return {"type": kind, "frms": frames, "fname": fname, "reuse": False,
            "colsp": colors, "width": width, "height": height,
            "posx": x, "posy": y, "alnx": align, "comp": compression,
            "ctx": ctx, "cty": cty}


def make_preview(background: Image.Image, digits: Image.Image, hands: list[tuple[Image.Image, int, int, float]]) -> Image.Image:
    im = background.convert("RGBA")
    cx, cy = 220, 236
    for hand, hx, hy, clockwise in hands:
        canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
        canvas.alpha_composite(hand, (cx - hx, cy - hy))
        canvas = canvas.rotate(-clockwise, resample=Image.Resampling.BICUBIC, center=(cx, cy))
        im.alpha_composite(canvas)
    for digit, x in ((1, 294), (0, 323), (0, 367), (8, 396)):
        frame = digits.crop((0, digit * 58, 28, (digit + 1) * 58))
        im.alpha_composite(frame, (x, 286))
    return im.convert("RGB").resize((280, 280), Image.Resampling.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    background = make_background()
    digits = make_digits()
    preview_hands = [
        (make_hand(24, 126, 12, 108, PALE), 12, 108, 304),
        (make_hand(18, 170, 9, 150, CYAN), 9, 150, 48),
        (make_hand(10, 192, 5, 169, RED, second=True), 5, 169, 35),
    ]
    make_preview(background, digits, preview_hands).save(ASSETS / "prev.png")
    background.save(ASSETS / "background.png")
    digits.save(ASSETS / "digits.png")
    tint_original_hand("arm_hour.png", PALE).save(ASSETS / "arm_hour.png")
    tint_original_hand("arm_minute.png", CYAN).save(ASSETS / "arm_minute.png")
    tint_original_hand("arm_second.png", RED).save(ASSETS / "arm_second.png")

    blocks = [
        layer("BLK_PREV", "prev.png", 280, 280, 0, 0, colors="RGB"),
        layer("BLK_BACKGROUND", "background.png", 466, 466, 0, 0, colors="RGB"),
        layer("BLK_ARM_HOUR", "arm_hour.png", 18, 132, 233, 233, compression=0, ctx=2, cty=9),
        layer("BLK_ARM_MINUTE", "arm_minute.png", 16, 182, 233, 233, compression=0, ctx=2, cty=8),
        layer("BLK_ARM_SECOND", "arm_second.png", 28, 256, 233, 233, compression=0, ctx=44, cty=14),
        layer("BLK_HOURH", "digits.png", 28, 58, 294, 286, frames=10),
        layer("BLK_HOURL", "digits.png", 28, 58, 323, 286, frames=10),
        layer("BLK_MINH", "digits.png", 28, 58, 367, 286, frames=10),
        layer("BLK_MINL", "digits.png", 28, 58, 396, 286, frames=10),
    ]
    (ASSETS / "dial_desc.json").write_text(json.dumps({"dial_name": "cat_gauge", "blocks": blocks}, indent=2) + "\n")


if __name__ == "__main__":
    main()
