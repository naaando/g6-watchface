"""Build the reference-inspired G6 cat gauge from the approved visual references."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "cat-gauge-v2"
ASSETS = OUTPUT / "assets"
SOURCE_IMAGE = ROOT / "cat-gauge" / "reference-inspired-v2.png"
SOURCE_HANDS = ROOT / "decoded_11448"
FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
WHITE = "#eaf5f3"
BLUE = "#64d7fa"
RED = "#fa5e53"


def hand(name: str, color: str) -> Image.Image:
    if name == "arm_second.png":
        asset = Image.new("RGBA", (28, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(asset)
        draw.line((14, 14, 14, 204), fill=color, width=2)
        draw.ellipse((9, 9, 19, 19), fill="#07172c", outline=color, width=2)
        return asset
    original = Image.open(SOURCE_HANDS / name).convert("RGBA")
    tinted = ImageOps.colorize(ImageOps.grayscale(original), "#061224", color).convert("RGBA")
    tinted.putalpha(original.getchannel("A"))
    return tinted


def digit_strip() -> Image.Image:
    strip = Image.new("RGBA", (34, 620), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)
    font = ImageFont.truetype(FONT, 65)
    for number in range(10):
        draw.text((2, number * 62 - 3), str(number), font=font, fill=WHITE)
    return strip


def add_hand(preview: Image.Image, asset: Image.Image, pivot_x: int, pivot_y: int, degrees: float) -> None:
    canvas = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    center = (233, 233)
    canvas.alpha_composite(asset, (center[0] - pivot_x, center[1] - pivot_y))
    canvas = canvas.rotate(-degrees, center=center, resample=Image.Resampling.BICUBIC)
    preview.alpha_composite(canvas)


def make_preview(background: Image.Image, hands: dict[str, Image.Image], digits: Image.Image) -> Image.Image:
    preview = background.convert("RGBA")
    # Original G6 arms point downward at zero rotation; the angles depict 10:08:30.
    add_hand(preview, hands["hour"], 2, 9, 124)
    add_hand(preview, hands["minute"], 2, 8, 228)
    add_hand(preview, hands["second"], 14, 14, 0)
    for value, x in [(1, 278), (0, 310), (0, 360), (8, 392)]:
        preview.alpha_composite(digits.crop((0, value * 62, 34, (value + 1) * 62)), (x, 255))
    return preview.convert("RGB")


def block(kind: str, file_name: str, width: int, height: int, x: int, y: int,
          frames: int = 1, color: str = "RGBA", compression: int = 4,
          center_x: int = 0, center_y: int = 0) -> dict:
    return {"type": kind, "frms": frames, "fname": file_name, "reuse": False,
            "colsp": color, "width": width, "height": height,
            "posx": x, "posy": y, "alnx": 9, "comp": compression,
            "ctx": center_x, "cty": center_y}


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    background = Image.open(SOURCE_IMAGE).convert("RGB").resize((466, 466), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(background)
    d.text((348, 46), "N2O", font=ImageFont.truetype(FONT, 27), fill="#061835")
    d.text((279, 232), "TIME", font=ImageFont.truetype(FONT, 19), fill=BLUE)
    d.text((344, 253), ":", font=ImageFont.truetype(FONT, 59), fill=BLUE)
    background.save(ASSETS / "background.png")

    digits = digit_strip()
    digits.save(ASSETS / "digits.png")
    hands = {
        "hour": hand("arm_hour.png", WHITE),
        "minute": hand("arm_minute.png", BLUE),
        "second": hand("arm_second.png", RED),
    }
    for name, asset in hands.items():
        asset.save(ASSETS / f"arm_{name}.png")
    preview = make_preview(background, hands, digits)
    preview.save(OUTPUT / "preview-large.png")
    preview.resize((280, 280), Image.Resampling.LANCZOS).save(ASSETS / "prev.png")

    blocks = [
        block("BLK_PREV", "prev.png", 280, 280, 0, 0, color="RGB"),
        block("BLK_BACKGROUND", "background.png", 466, 466, 0, 0, color="RGB"),
        block("BLK_ARM_HOUR", "arm_hour.png", 18, 132, 233, 233, compression=0, center_x=2, center_y=9),
        block("BLK_ARM_MINUTE", "arm_minute.png", 16, 182, 233, 233, compression=0, center_x=2, center_y=8),
        block("BLK_ARM_SECOND", "arm_second.png", 28, 256, 233, 233, compression=0, center_x=14, center_y=14),
        block("BLK_HOURH", "digits.png", 34, 62, 278, 255, frames=10),
        block("BLK_HOURL", "digits.png", 34, 62, 310, 255, frames=10),
        block("BLK_MINH", "digits.png", 34, 62, 360, 255, frames=10),
        block("BLK_MINL", "digits.png", 34, 62, 392, 255, frames=10),
    ]
    (ASSETS / "dial_desc.json").write_text(json.dumps({"dial_name": "cat_gauge_v2", "blocks": blocks}, indent=2) + "\n")


if __name__ == "__main__":
    main()
