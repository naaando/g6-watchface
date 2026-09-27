"""Build a G6-compatible analog prototype and visual previews from the blue cat artwork."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "decoded_11448"
ARTWORK = ROOT / "cat-gauge" / "reference-inspired-v2.png"
OUTPUT = ROOT / "cat-gauge-analog-test"
ASSETS = OUTPUT / "assets"
FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"


def tinted_hand(filename: str, highlight: str) -> Image.Image:
    original = Image.open(TEMPLATE / filename).convert("RGBA")
    recolored = ImageOps.colorize(ImageOps.grayscale(original), "#06111b", highlight).convert("RGBA")
    recolored.putalpha(original.getchannel("A"))
    if filename == "arm_second.png":
        alpha = recolored.getchannel("A")
        ImageDraw.Draw(alpha).rectangle((0, 0, recolored.width, 34), fill=0)
        recolored.putalpha(alpha)
    return recolored


def place_hand(canvas: Image.Image, hand: Image.Image, pivot_y: int, angle: float) -> None:
    center = (233, 233)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.alpha_composite(hand, (center[0] - hand.width // 2, center[1] - pivot_y))
    layer = layer.rotate(-angle, resample=Image.Resampling.BICUBIC, center=center)
    canvas.alpha_composite(layer)


def analog_preview(background: Image.Image, hands: dict[str, Image.Image]) -> Image.Image:
    preview = background.convert("RGBA")
    # 10:08:30: the official arm art points upward and pivots near its lower edge.
    place_hand(preview, hands["hour"], 123, 304)
    place_hand(preview, hands["minute"], 174, 48)
    place_hand(preview, hands["second"], 242, 180)
    return preview.convert("RGB")


def digital_concept(analog: Image.Image) -> Image.Image:
    concept = analog.convert("RGBA")
    d = ImageDraw.Draw(concept)
    d.text((280, 232), "TIME", font=ImageFont.truetype(FONT, 19), fill="#69dfff")
    d.text((278, 252), "10:08", font=ImageFont.truetype(FONT, 59), fill="#eaf5f3")
    return concept.convert("RGB")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((TEMPLATE / "dial_desc.json").read_text())
    metadata["dial_name"] = "cat_gauge_analog_test"

    background = Image.open(ARTWORK).convert("RGB").resize((466, 466), Image.Resampling.LANCZOS)
    background.save(ASSETS / "background.png")

    # Keep the known G6 block layout; hide complication graphics that do not fit this artwork.
    for block in metadata["blocks"][2:5]:
        Image.new("RGBA", (block["width"], block["height"] * block["frms"]), (0, 0, 0, 0)).save(ASSETS / block["fname"])

    hands = {
        "hour": tinted_hand("arm_hour.png", "#e9f2f5"),
        "minute": tinted_hand("arm_minute.png", "#65dffc"),
        "second": tinted_hand("arm_second.png", "#e44d58"),
    }
    for name, hand in hands.items():
        hand.save(ASSETS / f"arm_{name}.png")

    analog = analog_preview(background, hands)
    analog.save(OUTPUT / "preview-with-official-hands.png")
    analog.resize((280, 280), Image.Resampling.LANCZOS).save(ASSETS / "prev.png")
    digital_concept(analog).save(OUTPUT / "preview-digital-concept.png")
    (ASSETS / "dial_desc.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
