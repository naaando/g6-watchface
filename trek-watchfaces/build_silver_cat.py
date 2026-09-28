"""Build a G6 dial from the supplied silver-cat image and live digital time."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUTPUT = ROOT / "silver-cat"
ASSETS = OUTPUT / "assets"
SOURCE = OUTPUT / "source" / "user-cat.png"
TEMPLATE = ROOT / "0.0_G6_captured_618808.bin"
COMPILER = PROJECT / "Fogg" / "comp_decomp.py"
FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
DIGIT_WIDTH = 36
DIGIT_HEIGHT = 52
DIGIT_Y = 27


def digit_strip() -> Image.Image:
    strip = Image.new("RGBA", (DIGIT_WIDTH, DIGIT_HEIGHT * 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)
    font = ImageFont.truetype(FONT, 49)
    for value in range(10):
        glyph = str(value)
        bounds = draw.textbbox((0, 0), glyph, font=font)
        x = (DIGIT_WIDTH - (bounds[2] - bounds[0])) // 2 - bounds[0]
        y = value * DIGIT_HEIGHT + (DIGIT_HEIGHT - (bounds[3] - bounds[1])) // 2 - bounds[1]
        draw.text((x, y), glyph, font=font, fill="#eef2f8", stroke_width=1, stroke_fill="#8b9db2")
    return strip


def preview(background: Image.Image, strip: Image.Image) -> Image.Image:
    image = background.convert("RGBA")
    # Static thumbnail example; the watch draws the digits from the live clock.
    for value, x in ((1, 151), (0, 187), (0, 243), (8, 279)):
        glyph = strip.crop((0, value * DIGIT_HEIGHT, DIGIT_WIDTH, (value + 1) * DIGIT_HEIGHT))
        image.alpha_composite(glyph, (x, DIGIT_Y))
    return image.convert("RGB")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as template_dir:
        subprocess.run(
            [sys.executable, str(COMPILER), str(TEMPLATE), template_dir],
            check=True, capture_output=True, text=True,
        )
        metadata = json.loads((Path(template_dir) / "dial_desc.json").read_text())

    metadata["dial_name"] = "silver_cat"
    background = Image.open(SOURCE).convert("RGB").resize((466, 466), Image.Resampling.LANCZOS)
    ImageDraw.Draw(background).text(
        (226, 29), ":", font=ImageFont.truetype(FONT, 46), fill="#eef2f8"
    )
    background.save(ASSETS / "background.png")
    strip = digit_strip()
    strip.save(ASSETS / "hours.png")
    strip.save(ASSETS / "minutes.png")

    thumbnail = preview(background, strip)
    thumbnail.save(OUTPUT / "preview-large.png")
    thumbnail.resize((280, 280), Image.Resampling.LANCZOS).save(ASSETS / "prev.png")

    for block in metadata["blocks"]:
        kind = block["type"]
        if kind == "BLK_HOURS":
            block.update(width=DIGIT_WIDTH, height=DIGIT_HEIGHT, posx=151, posy=DIGIT_Y)
        elif kind == "BLK_MINUTES":
            block.update(width=DIGIT_WIDTH, height=DIGIT_HEIGHT, posx=243, posy=DIGIT_Y)
        elif kind not in ("BLK_PREV", "BLK_BACKGROUND"):
            Image.new("RGBA", (block["width"], block["height"] * block["frms"]), (0, 0, 0, 0)).save(
                ASSETS / block["fname"]
            )
    (ASSETS / "dial_desc.json").write_text(json.dumps(metadata, indent=2) + "\n")
    subprocess.run(
        [sys.executable, str(COMPILER), "-c", str(ASSETS), str(OUTPUT / "silver-cat.bin")],
        check=True,
    )


if __name__ == "__main__":
    main()
