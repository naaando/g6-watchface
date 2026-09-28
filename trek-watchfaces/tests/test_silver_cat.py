"""Check the actual compiled silver-cat dial before it is sent to the G6."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
DIAL = ROOT / "trek-watchfaces" / "silver-cat"
BIN = DIAL / "silver-cat.bin"


class SilverCatDialTest(unittest.TestCase):
    def test_compiled_dial_has_live_time_above_the_unobscured_cat(self):
        self.assertTrue((ROOT / "trek-watchfaces" / "build_silver_cat.py").is_file(), "silver-cat builder is missing")
        subprocess.run(
            [sys.executable, str(ROOT / "trek-watchfaces" / "build_silver_cat.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertTrue(BIN.is_file())

        with tempfile.TemporaryDirectory() as decoded_dir:
            subprocess.run(
                [sys.executable, str(ROOT / "Fogg" / "comp_decomp.py"),
                 str(BIN), decoded_dir],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            decoded = Path(decoded_dir)
            blocks = json.loads((decoded / "dial_desc.json").read_text())["blocks"]
            names = {block["type"]: block for block in blocks}
            self.assertEqual(len(blocks), 16)
            self.assertEqual(names["BLK_BACKGROUND"]["width"], 466)
            self.assertEqual(names["BLK_BACKGROUND"]["height"], 466)

            for name in ("BLK_HOURS", "BLK_MINUTES"):
                block = names[name]
                self.assertEqual(block["frms"], 10)
                self.assertEqual(block["colsp"], "RGBA")
                self.assertLess(block["posy"] + block["height"], 95)
                strip = Image.open(decoded / block["fname"]).convert("RGBA")
                first = strip.crop((0, 0, block["width"], block["height"]))
                second = strip.crop((0, block["height"], block["width"], 2 * block["height"]))
                self.assertIsNotNone(ImageChops.difference(first, second).getbbox())
                self.assertIsNotNone(first.getchannel("A").getbbox())

            for block in blocks:
                if block["type"] in ("BLK_PREV", "BLK_BACKGROUND", "BLK_HOURS", "BLK_MINUTES"):
                    continue
                image = Image.open(decoded / block["fname"]).convert("RGBA")
                self.assertIsNone(image.getchannel("A").getbbox(), block["type"])

            background = Image.open(decoded / "background.png").convert("RGB")
            self.assertLess(max(background.getpixel((233, 20))), 12)
            self.assertGreater(min(background.getpixel((200, 180))), 40)
            colon = background.crop((225, 35, 242, 76))
            self.assertGreater(max(high for _, high in colon.getextrema()), 150)


if __name__ == "__main__":
    unittest.main()
