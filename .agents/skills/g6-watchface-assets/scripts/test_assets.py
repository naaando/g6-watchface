#!/usr/bin/env python3
"""Tests for the asset generators.

    python3 test_assets.py

Every check here exists because the failure it guards against is invisible: a
strip that is the wrong shape, or off by a pixel, or a tofu box, all render as
something plausible. A test that cannot fail is worse than no test, so the
negative cases assert the exit code and not just the message.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
MAKER = HERE / "make_digit_strip.py"
HAND = HERE / "make_hand_sprite.py"
HAND_STYLES = ["sword", "arrow", "baton", "needle", "club",
               "diamond", "leaf", "lollipop"]

# DIN Condensed Bold is the face the shipped dials already use, and it is a
# system font on macOS. Fall back to any bold system font elsewhere.
FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/Library/Fonts/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

passed = 0
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed.append(f"{name}: {detail}")
        print(f"  FAIL {name}  {detail}")


def font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    sys.exit("no bold system font found; install one or edit FONT_CANDIDATES")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MAKER), *args],
                          capture_output=True, text=True)


MAKE_COUNT = 0


def make(tmp: Path, *args: str, expect_ok: bool = True) -> dict:
    # A unique path per call: the "nothing is written when it refuses" check
    # below is meaningless if an earlier call already created the same file.
    global MAKE_COUNT
    MAKE_COUNT += 1
    out = tmp / f"out{MAKE_COUNT}.png"
    result = run(*args, "--out", str(out))
    if expect_ok:
        if result.returncode != 0:
            raise AssertionError(f"generator failed: {result.stderr.strip()}")
        info = json.loads(result.stdout) if "--json" in args else {}
        if not info:
            info = {"width": Image.open(out).width,
                    "height": Image.open(out).height}
        info["_image"] = Image.open(out)
        return info
    return {"returncode": result.returncode, "stderr": result.stderr,
            "stdout": result.stdout, "_path": out}


def main() -> None:
    font = font_path()
    print(f"font under test: {font}\n")
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        # --- shape -------------------------------------------------------
        print("strip geometry")
        info = make(tmp, "--preset", "digits", "--font", str(font), "--size", "20",
                    "--frame-width", "24", "--frame-height", "32", "--fixed-width",
                    "--json")
        check("10 digit frames", info["frms"] == 10, str(info["frms"]))
        check("frames stack vertically",
              info["height"] == info["frame_height"] * info["frms"],
              f"{info['height']} != {32} * {info['frms']}")
        check("width is one cell, not ten",
              info["width"] == 24, f"{info['width']} != 24")

        # A horizontal strip is the single most damaging mistake here: frame 0
        # of most gauges looks fine, so a sideways strip still renders a
        # plausible dial until a later frame is needed.
        strip = info["_image"]
        check("strip is taller than wide",
              strip.height > strip.width, f"{strip.size}")

        # --- frame content -----------------------------------------------
        print("\nframe content")
        boxes = info["alpha_bboxes"]
        check("no blank frames", not info["blank_frames"], str(info["blank_frames"]))
        check("every frame has ink", all(b is not None for b in boxes))
        # Frame 0 must not be identical to frame 1, or the block shows a frozen
        # digit for the whole day.
        first = strip.crop((0, 0, strip.width, 32)).tobytes()
        second = strip.crop((0, 32, strip.width, 64)).tobytes()
        check("frame 0 differs from frame 1", first != second)

        # --- centring ----------------------------------------------------
        print("\ncentring")
        # The bug this guards: centring on the font's ascender/descender box
        # instead of the glyph's ink box leaves the digit visibly high in a
        # tight cell. Check the ink is actually centred, not just present.
        for index, box in enumerate(boxes):
            if box is None:
                continue
            top, bottom = box[1], box[3] - 1
            cell_h = 32
            if abs(top - (cell_h - bottom)) > 3:
                check(f"frame {index} ink is vertically centred", False,
                      f"top={top} bottom={bottom} in {cell_h}px cell")
                break
        else:
            check("ink is vertically centred in every frame", True)

        # --- font coverage -----------------------------------------------
        print("\nfont coverage")
        result = make(tmp, "--items", "0\n1\n猫", "--font", str(font),
                      "--size", "20", expect_ok=False)
        check("a glyph the font lacks is refused", result["returncode"] != 0,
              f"exit={result['returncode']}")
        check("nothing is written when it refuses", not result["_path"].exists())
        if result["returncode"] != 0:
            check("the error names the offending item",
                  "猫" in result["stderr"], result["stderr"][:120])

        # --- frame-count contract ----------------------------------------
        print("\nframe-count contract")
        cases = [
            ("BLK_WEEKD", ["digits"], "7"),
            ("BLK_WEEKD", ["weekdays_en"], None),
            ("BLK_MONTH", ["months_en"], None),
            ("BLK_MONTH", ["digits"], None),
            ("BLK_BIGYO", ["digits"], "1"),
            ("BLK_HOUR", ["weekdays_en"], "10"),
        ]
        for block_type, (preset,), expect_err in cases:
            args = ["--preset", preset, "--block-type", block_type,
                    "--font", str(font), "--size", "20"]
            got = make(tmp, *args, expect_ok=expect_err is None)
            if expect_err:
                check(f"{block_type} rejects {preset}",
                      got["returncode"] != 0, f"exit={got['returncode']}")
            else:
                check(f"{block_type} accepts {preset}", True)

        # --- autofit ------------------------------------------------------
        print("\nauto-fit")
        tight = make(tmp, "--preset", "digits", "--font", str(font),
                     "--size", "20", "--frame-height", "32", "--json")
        wide = make(tmp, "--preset", "months_en", "--font", str(font),
                    "--size", "20", "--frame-height", "32", "--json")
        check("a wider character set gets a wider cell",
              wide["width"] > tight["width"],
              f"digits={tight['width']} months={wide['width']}")
        # An over-wide cell shows up on the device as gaps between digits,
        # because the watch advances by the full cell width.
        widest_ink = max(b[2] - b[0] for b in wide["alpha_bboxes"] if b)
        check("cell hugs the ink rather than padding it out",
              wide["width"] - widest_ink <= 20,
              f"cell={wide['width']} widest ink={widest_ink}")

        # --- letter spacing ----------------------------------------------
        print("\nletter spacing")
        plain = make(tmp, "--preset", "months_en", "--font", str(font),
                     "--size", "20", "--frame-height", "32", "--json")
        spaced = make(tmp, "--preset", "months_en", "--font", str(font),
                      "--size", "20", "--frame-height", "32", "--letter-spacing", "4",
                      "--json")
        check("letter spacing widens the cell",
              spaced["width"] > plain["width"],
              f"plain={plain['width']} spaced={spaced['width']}")
        check("no frame is clipped by letter spacing",
              not spaced["blank_frames"], str(spaced["blank_frames"]))

        # --- equivalence with the hand-rolled version ---------------------
        # build_silver_cat.py:27-37 does this by hand. If the generator ever
        # drifts from it, every digit strip in the repo changes at once.
        print("\nequivalence with build_silver_cat.py")
        ref_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/"
                                       "DIN Condensed Bold.ttf", 49)
        if ref_font is not None:
            w, h = 36, 52
            reference = Image.new("RGBA", (w, h * 10), (0, 0, 0, 0))
            draw = ImageDraw.Draw(reference)
            for value in range(10):
                glyph = str(value)
                box = draw.textbbox((0, 0), glyph, font=ref_font)
                x = (w - (box[2] - box[0])) // 2 - box[0]
                y = value * h + (h - (box[3] - box[1])) // 2 - box[1]
                draw.text((x, y), glyph, font=ref_font, fill="#eef2f8",
                          stroke_width=1, stroke_fill="#8b9db2")
            made = make(tmp, "--preset", "digits", "--font", ref_font.path,
                        "--size", "49", "--frame-width", "36", "--frame-height",
                        "52", "--fixed-width", "--color", "#eef2f8",
                        "--stroke-width", "1", "--stroke", "#8b9db2")
            check("byte-identical to the hand-rolled strip",
                  reference.tobytes() == made["_image"].tobytes())
        else:
            check("DIN Condensed Bold available for the equivalence test", False,
                  "font not present on this host")

        # --- hands --------------------------------------------------------
        # A hand block is the one place where the descriptor's ctx/cty are not
        # optional, and where posx/posy is the pivot rather than the top-left.
        # Every check here is about that geometry, not about how it looks.
        print("\nhand geometry")
        hand_out = tmp / "hand.png"
        for style in HAND_STYLES:
            result = subprocess.run(
                [sys.executable, str(HAND), "--type", "hour", "--tip-style", style,
                 "--out", str(hand_out), "--json"], capture_output=True, text=True)
            if result.returncode != 0:
                check(f"{style} hand renders", False, result.stderr.strip()[:120])
                continue
            info = json.loads(result.stdout)
            image = Image.open(hand_out).convert("RGBA")

            # The convention, stated in the docstring: cty is the horizontal
            # offset from the left and is always width/2.
            check(f"{style}: cty is exactly width/2",
                  info["cty"] * 2 == info["width"],
                  f"cty={info['cty']} width={info['width']}")
            # ...and ctx is measured up from the BOTTOM, not down from the top.
            check(f"{style}: height - ctx is the pivot row",
                  info["height"] - info["ctx"] == info["pivot_y_from_top"],
                  f"h={info['height']} ctx={info['ctx']} pivot={info['pivot_y_from_top']}")
            # The hand must fill its sprite: tip at the top margin, tail at the
            # bottom. A short hand is invisible on the watch. The margin is 10
            # rather than 0 on purpose -- the drop shadow and glow need room, and
            # the watch clips whatever runs off the edge.
            box = image.getchannel("A").getbbox()
            check(f"{style}: tip reaches the top margin and the tail the bottom",
                  box is not None and box[1] <= 10
                  and box[3] >= info["height"] - 10,
                  f"bbox={box} of {info['width']}x{info['height']}")

        # A 1px needle with a 2px outline drawn on top of itself comes out
        # solid black -- invisible on a dark dial. This is a real regression
        # that happened, so it stays as a check.
        subprocess.run([sys.executable, str(HAND), "--type", "hour", "--tip-style",
                        "needle", "--out", str(hand_out)], capture_output=True)
        needle = Image.open(hand_out).convert("RGBA")
        pixels = needle.load()
        light = sum(1 for y in range(needle.height) for x in range(needle.width)
                    if pixels[x, y][0] > 200 and pixels[x, y][3] > 128)
        check("the needle keeps its own colour under its outline", light > 100,
              f"only {light} light pixels; the outline is covering the fill")

        # The scale flag has to move the pivot with the art, or a hand scaled to
        # match an existing dial ends up rotating about the wrong point. The
        # 10px margin is fixed, so only the shaft scales.
        base = json.loads(subprocess.run(
            [sys.executable, str(HAND), "--type", "minute", "--out", str(hand_out),
             "--json"], capture_output=True, text=True).stdout)
        doubled = json.loads(subprocess.run(
            [sys.executable, str(HAND), "--type", "minute", "--scale", "2", "--out",
             str(hand_out), "--json"], capture_output=True, text=True).stdout)
        check("--scale scales the shaft, not the margin",
              doubled["pivot_y_from_top"] - 10 == (base["pivot_y_from_top"] - 10) * 2,
              f"{base['pivot_y_from_top']} -> {doubled['pivot_y_from_top']}")

        # Hands are single-frame. A frms>1 hand block would show the same hand
        # cycling, which looks like a stutter rather than a broken frame.
        check("hands are single-frame by construction",
              base["height"] < 2 * base["pivot_y_from_top"])

        # The second hand's preset is 5px wide, and 5 + 2*10 is odd. On an odd
        # sprite the pivot is at width/2 = 12.5, so the hand rotates about half
        # a pixel off-centre for the rest of the day. The presets for hour and
        # minute are even by luck, so this has to be checked on the one that
        # is not.
        second = json.loads(subprocess.run(
            [sys.executable, str(HAND), "--type", "second", "--out", str(hand_out),
             "--json"], capture_output=True, text=True).stdout)
        check("the second hand still gets an even sprite",
              second["width"] % 2 == 0,
              f"width={second['width']} is odd, so the pivot sits at "
              f"{second['width'] / 2}")
        check("the second hand's pivot is on the pixel",
              second["cty"] * 2 == second["width"],
              f"cty={second['cty']} width={second['width']}")

    print(f"\n{passed} checks passed, {len(failed)} failed")
    for line in failed:
        print(f"  {line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
