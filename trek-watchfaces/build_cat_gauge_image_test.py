"""Package the user's gauge image in a known G6 dial block layout for display testing."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "decoded_11448"
OUTPUT = ROOT / "cat-gauge-image-test"
ASSETS = OUTPUT / "assets"
SOURCE = OUTPUT / "source" / "user-reference.png"


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((TEMPLATE / "dial_desc.json").read_text())
    metadata["dial_name"] = "cat_gauge_image_test"

    # Crop only the gauge from the user-supplied image; keep its artwork intact.
    artwork = Image.open(SOURCE).convert("RGB").crop((365, 45, 1005, 685))
    artwork = artwork.resize((466, 466), Image.Resampling.LANCZOS)
    artwork.save(ASSETS / "background.png")
    artwork.save(OUTPUT / "preview-large.png")
    artwork.resize((280, 280), Image.Resampling.LANCZOS).save(ASSETS / "prev.png")

    # Retain every official block type, frame count, size, position, and encoding.
    # These transparent layers allow an image-only display test without overlays.
    for block in metadata["blocks"][2:]:
        size = (block["width"], block["height"] * block["frms"])
        Image.new("RGBA", size, (0, 0, 0, 0)).save(ASSETS / block["fname"])

    (ASSETS / "dial_desc.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
