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
BATTERY = HERE / "make_battery_gauge.py"
WEATHER = HERE / "make_weather_icons.py"
HAND_STYLES = ["sword", "arrow", "baton", "needle", "club",
               "diamond", "leaf", "lollipop"]
BATTERY_STYLES = ["horizontal_capsule", "vertical_capsule", "circular_ring",
                  "gauge_arc", "pill_dots"]

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


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)


def _render(tmp: Path, name: str, args: list[str]) -> Path:
    out = tmp / name
    result = _run(WEATHER, *args, "--out", str(out))
    if result.returncode != 0:
        raise AssertionError(f"weather generator failed: {result.stderr.strip()}")
    return out


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

        # --- battery gauges ----------------------------------------------
        # Every frame is a different charge level and the watch picks the frame
        # from the percentage, so the two things that can go wrong are both
        # silent: a strip laid out sideways (frame 0 looks fine on its own) and
        # frames that do not change (the gauge freezes at one level).
        print("\nbattery gauges")
        for style in BATTERY_STYLES:
            result = subprocess.run(
                [sys.executable, str(BATTERY), "--style", style, "--out",
                 str(tmp / "batt.png"), "--json"], capture_output=True, text=True)
            if result.returncode != 0:
                check(f"{style} renders", False, result.stderr.strip()[:140])
                continue
            info = json.loads(result.stdout)
            image = Image.open(tmp / "batt.png").convert("RGBA")

            check(f"{style}: six frames, stacked vertically",
                  info["frames"] == 6
                  and image.height == info["frame_height"] * 6
                  and image.width == info["frame_width"],
                  f"{image.size} for {info['frames']} frames")

            frames = [image.crop((0, i * info["frame_height"], image.width,
                                  (i + 1) * info["frame_height"])).tobytes()
                      for i in range(6)]
            # A sideways strip would make every crop identical.
            check(f"{style}: each frame differs from the one above",
                  len(set(frames)) == 6,
                  f"{len(set(frames))} distinct of 6 -- "
                  + ("a horizontal strip slices to the same image every time"
                     if len(set(frames)) == 1 else "two frames are identical"))

            # The gauge must actually read as filling up. Counting lit pixels
            # per frame is crude but it is the property that matters, and it
            # cannot be satisfied by a static drawing.
            lit = [row["lit_pixels"] for row in info["frames_detail"]]
            check(f"{style}: ink grows with charge", lit == sorted(lit),
                  f"{lit}")

        # The firmware's band edges are not evenly spaced (0-5, 6-20, 21-40,
        # 41-60, 61-80, 81-100). Evenly spaced levels -- what the designer
        # emits -- must still land in a distinct band per frame, or two frames
        # are never used and the gauge has dead levels.
        print("\nbattery band mapping")
        bands = json.loads(subprocess.run(
            [sys.executable, str(BATTERY), "--style", "horizontal_capsule", "--out",
             str(tmp / "batt.png"), "--json"], capture_output=True, text=True).stdout)
        check("evenly spaced levels use six distinct bands",
              bands["firmware_bands"] == [0, 1, 2, 3, 4, 5],
              str(bands["firmware_bands"]))

        exact = json.loads(subprocess.run(
            [sys.executable, str(BATTERY), "--style", "horizontal_capsule",
             "--levels", "5,20,40,60,80,100", "--out", str(tmp / "batt.png"),
             "--json"], capture_output=True, text=True).stdout)
        check("--levels can hit the exact band edges",
              exact["firmware_bands"] == [0, 1, 2, 3, 4, 5],
              str(exact["firmware_bands"]))

        # Frame 0 is the empty frame and it is usually red. A gauge whose first
        # frame is the "intended" design looks like a working gauge all day.
        zero = json.loads(subprocess.run(
            [sys.executable, str(BATTERY), "--style", "horizontal_capsule",
             "--color-mode", "dynamic", "--out", str(tmp / "batt.png"), "--json"],
            capture_output=True, text=True).stdout)
        check("frame 0 is drawn, not transparent", zero["frames_detail"][0]["lit_pixels"] > 0,
              "an empty frame 0 means the block shows nothing at 0%")

        # --- battery frame-count contract --------------------------------
        # BLK_BATTS (0x18) and the 0x21 pulse ring both hold exactly 6 frames.
        # A 4-frame gauge is the shape the designer defaults to for other
        # blocks, and it renders perfectly -- on the watch it just never uses
        # the last two levels.
        print("\nbattery frame-count contract")
        for block_type in ("BLK_BATTS", "BLK_UNK_A1"):
            good = subprocess.run(
                [sys.executable, str(BATTERY), "--block-type", block_type, "--frames",
                 "6", "--out", str(tmp / "batt.png")], capture_output=True, text=True)
            check(f"{block_type} accepts 6 frames", good.returncode == 0,
                  good.stderr.strip()[:120])
            bad = subprocess.run(
                [sys.executable, str(BATTERY), "--block-type", block_type, "--frames",
                 "4", "--out", str(tmp / "batt.png")], capture_output=True, text=True)
            check(f"{block_type} rejects 4 frames", bad.returncode != 0,
                  f"exit={bad.returncode}")

        # --- battery levels validation ------------------------------------
        print("\nbattery level validation")
        # --frames is pinned to 6 for every case so that a count mismatch is
        # what is being tested, rather than --frames following --levels.
        for bad_levels, why in [
            ("5,20,40", "a list shorter than --frames"),
            ("5,20,40,60,80", "a list shorter than --frames"),
            ("5,20,40,60,80,100,110", "a list longer than --frames"),
            ("5,20,40,60,80,120", "a level above 100"),
            ("-5,20,40,60,80,100", "a level below 0"),
            ("80,20,40,60,80,100", "levels that decrease"),
        ]:
            result = subprocess.run(
                [sys.executable, str(BATTERY), "--levels", bad_levels, "--frames",
                 "6", "--out", str(tmp / "batt.png")],
                capture_output=True, text=True)
            check(f"--levels refuses {why}", result.returncode != 0,
                  f"exit={result.returncode} for {bad_levels}")

        # --- battery glyph coverage ---------------------------------------
        # circular_ring falls through to drawing the bolt as TEXT in every
        # non-full frame when no percentage is shown. Arial has no U+26A1, and
        # Pillow draws a .notdef box for it -- which on the watch is
        # indistinguishable from a real character. The first version of this
        # guard checked the wrong conditions and let the boxes through.
        print("\nbattery glyph coverage")
        for args, why in [
            (["--style", "circular_ring", "--no-lightning"], "bolt text with no glyph"),
            (["--style", "circular_ring", "--show-percentage", "--font", str(font)],
             None),
        ]:
            result = subprocess.run(
                [sys.executable, str(BATTERY), *args, "--out", str(tmp / "batt.png")],
                capture_output=True, text=True)
            if why:
                check(f"refuses to draw {why}", result.returncode != 0,
                      f"exit={result.returncode}")
            else:
                check("draws a percentage with a font that has the digits",
                      result.returncode == 0, result.stderr.strip()[:120])

        # And the escape hatch: the same gauge with the percentage showing
        # needs no U+26A1, so it must build.
        pct = subprocess.run(
            [sys.executable, str(BATTERY), "--style", "circular_ring", "--no-lightning",
             "--show-percentage", "--font", str(font), "--out", str(tmp / "batt.png")],
            capture_output=True, text=True)
        check("--show-percentage avoids the missing bolt", pct.returncode == 0,
              pct.stderr.strip()[:120])

        # --- weather icons -----------------------------------------------
        # The frame index IS the weather code, so a wrong order renders
        # perfectly and shows the wrong sky. Nothing in the image reveals it,
        # which is why the order is checked against the codes and not by
        # looking at the output.
        print("\nweather icons")
        wx = json.loads(subprocess.run(
            [sys.executable, str(WEATHER), "--out", str(tmp / "weather.png"),
             "--frame-width", "46", "--frame-height", "46", "--json"],
            capture_output=True, text=True).stdout)
        image = Image.open(tmp / "weather.png").convert("RGBA")
        check("twelve frames, stacked vertically",
              wx["frames"] == 12 and image.height == 46 * 12 and image.width == 46,
              f"{image.size} for {wx['frames']} frames")
        check("frames stack top to bottom, not sideways", image.height > image.width,
              f"{image.size}")

        codes = [row["code"] for row in wx["frames_detail"]]
        check("frame index equals weather code", codes == list(range(12)), str(codes))

        # The names are the documentation of that order; a rename that breaks
        # the pairing is the failure this catches.
        expected_names = ["Other", "Sunny", "Cloudy", "Overcast", "Rainy", "Thunder",
                          "Thundershower", "High-wind", "Snowy", "Foggy",
                          "Sandstorm", "Haze"]
        names = [row["name"] for row in wx["frames_detail"]]
        check("each frame's name is the one for its code",
              all(name.startswith(want) for name, want in zip(names, expected_names)),
              str(names))

        frames = [image.crop((0, i * 46, 46, (i + 1) * 46)).tobytes() for i in range(12)]
        check("no two frames are identical", len(set(frames)) == 12,
              f"{len(set(frames))} distinct of 12 -- a parser that returns "
              "nothing makes every frame the same blank")

        boxes = [row["alpha_bbox"] for row in wx["frames_detail"]]
        check("no blank frames", all(b is not None for b in boxes),
              f"blank: {[i for i, b in enumerate(boxes) if b is None]}")

        # The icon has to be drawn inside the frame and centred, or the watch
        # clips it against the bezel. The ink legitimately extends past the
        # padded box by half the stroke -- the stroke is centred on the path,
        # and the 24-unit viewBox has its own 2-unit margin built in. So the
        # bound is the padded box grown by half a stroke, plus a pixel for the
        # antialiasing the LANCZOS downsample spreads.
        #
        # Measured with ink_bbox (alpha >= 8), not the strict alpha_bbox. The
        # strict box is inflated by LANCZOS ringing at alpha 1-7 that reaches
        # ~2px past the real ink, so on the thunder frames it reads
        # (5,5,41,40) where the true ink is (8,8,38,37) -- inside the bound.
        # Using the strict box here fails a correct renderer and tempts a fix
        # that loosens the bound until real clipping stops being caught.
        size = 46 - 8 * 2
        half_stroke = 2.0 * (size / 24.0) / 2.0
        slack = half_stroke + 1.5
        off_frame = []
        off_centre = []
        for row in wx["frames_detail"]:
            b = row["ink_bbox"]
            if b is None:
                continue
            if b[0] < 8 - slack or b[2] > 46 - 8 + slack \
                    or b[1] < 8 - slack or b[3] > 46 - 8 + slack:
                off_frame.append((row["index"], b))
            # The icon box is centred, so the ink must be too. A couple of
            # pixels of asymmetry is inherent -- the question mark in the help
            # icon leans, and the cloud is not symmetric about its box.
            cx = (b[0] + b[2]) / 2.0
            if abs(cx - 23.0) > 3.0:
                off_centre.append((row["index"], round(cx, 1)))
        check("no icon is clipped by the frame", not off_frame, str(off_frame))
        check("every icon is centred horizontally", not off_centre, str(off_centre))

        # --- weather path parsing ----------------------------------------
        # The icons are drawn by parsing lucide path data, so the parser is
        # where a wrong answer hides. These are the cases the twelve icons
        # actually exercise, each checked against a property that is
        # independent of the code that produced it.
        print("\nweather path parsing")
        import make_weather_icons as wxmod
        import math

        # Arcs: sweep-flag=1 must go clockwise, which in the y-down coordinate
        # system means over the top. Getting this backwards mirrors every
        # curved icon horizontally and it still looks like a plausible cloud.
        for sweep, want in ((0, "below"), (1, "above")):
            pts = wxmod.parse_path(f"M0 0A1 1 0 0 {sweep} 2 0")[0]
            mid = pts[len(pts) // 2]
            check(f"sweep-flag {sweep} bulges {want}",
                  (mid[1] > 0) == (sweep == 0), f"mid y={mid[1]:.3f}")

        # A full circle built from two arcs must land every sampled point on
        # the radius. This is the property that catches a wrong centre
        # parameterisation, which is the classic arc bug.
        circ = [p for sub in wxmod.parse_path("M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20")
                for p in sub]
        err = max(abs(math.hypot(x - 12, y - 12) - 10) for x, y in circ)
        check("two half arcs trace a true circle", err < 0.01, f"max error {err}")

        # Relative and absolute forms of the same arc must agree exactly.
        absolute = wxmod.parse_path("M15.9 10.9A5.5 5.5 0 0 0 9 17")
        relative = wxmod.parse_path("M15.9 10.9a5.5 5.5 0 0 0-6.9 6.1")
        check("relative arcs match their absolute form", absolute == relative,
              f"{len(absolute)} vs {len(relative)} subpaths")

        # Arcs whose radii are smaller than the chord are scaled up per spec
        # rather than dropped. CloudSun's `A3.5 3.5` over a 7-unit chord is
        # exactly this case, and a parser that drops it loses the cloud's lobe.
        scaled = wxmod.parse_path("M0 0A1 1 0 0 0 5 0")
        check("an undersized arc radius is scaled up, not dropped",
              len(scaled[0]) > 2, f"{len(scaled[0])} point(s)")

        # H and V must not disturb the other axis -- the run-on form
        # "M2 12h20M12 2v20" in the snowflake depends on it.
        hv = wxmod.parse_path("M2 12h20M12 2v20")
        check("H and V produce one subpath each", len(hv) == 2, f"{len(hv)}")
        check("h advances x only", (hv[0][-1][0], hv[0][-1][1]) == (22.0, 12.0),
              str(hv[0][-1]))
        check("v advances y only", (hv[1][-1][0], hv[1][-1][1]) == (12.0, 22.0),
              str(hv[1][-1]))

        # stroke-width is in viewBox units and scales with the icon. A gauge
        # icon drawn 32px and 48px must both keep the same visual weight, so
        # the ink has to grow with the frame.
        # Coverage, not lit-pixel count: a thresholded count loses the
        # antialiased fringe, and it loses proportionally more at small sizes,
        # which reads as the stroke not scaling. Summed alpha is the real area.
        from _g6canvas import ink_area

        small = Image.open(_render(tmp, "wx_small.png",
                                   ["--frame-width", "32", "--frame-height", "32"]))
        large = Image.open(_render(tmp, "wx_large.png",
                                   ["--frame-width", "64", "--frame-height", "64"]))
        small_ink = ink_area(small)
        large_ink = ink_area(large)
        # The icon box is frame - 2*icon_padding, and icon_padding is a FIXED
        # pixel inset, so doubling the frame does NOT double the icon: 32 and
        # 64 give boxes of 16 and 48, a factor of 3. A stroke-only icon's area
        # is length x width and both are linear in the box, so the expected
        # ratio is 3^2 = 9. Expecting a flat 4 here fails on a correct
        # renderer, and "fixing" it would mean scaling the padding too.
        ratio = large_ink / small_ink if small_ink else 0
        box_small, box_large = 32 - 16, 64 - 16
        expect = (box_large / box_small) ** 2
        # Tolerance covers the arcs' chord approximation at 32px, where a
        # curve is only a few segments, and the 1/255 LANCZOS fringe.
        check("the icon scales with the frame rather than staying a fixed size",
              expect * 0.85 < ratio < expect * 1.15,
              f"coverage ratio {ratio:.2f} for 32->64; expected ~{expect:.2f} "
              f"because the icon box is {box_small}->{box_large} px (below means "
              "the stroke is not scaling, above means something is drawn twice)")

        # --- weather frame-count contract ---------------------------------
        print("\nweather frame-count contract")
        good = _run(WEATHER, "--block-type", "BLK_WEATHER", "--out", str(tmp / "w.png"))
        check("BLK_WEATHER accepts 12 frames", good.returncode == 0,
              good.stderr.strip()[:120])

        # --- weather input validation --------------------------------------
        print("\nweather input validation")
        # An icon_padding larger than the frame collapses the icon to nothing
        # and writes a strip of 12 blank frames -- which looks like a working
        # file and shows nothing on the watch.
        collapse = _run(WEATHER, "--frame-width", "16", "--frame-height", "16",
                        "--icon-padding", "8", "--out", str(tmp / "w2.png"))
        check("a padding that collapses the icon is refused",
              collapse.returncode != 0, f"exit={collapse.returncode}")
        tiny = _run(WEATHER, "--frame-width", "2", "--frame-height", "2",
                    "--out", str(tmp / "w3.png"))
        check("a tiny frame is refused", tiny.returncode != 0,
              f"exit={tiny.returncode}")
        no_out = _run(WEATHER, "--list")
        check("--list works without --out", no_out.returncode == 0,
              no_out.stderr.strip()[:120])
        check("--list names all twelve codes",
              all(name in no_out.stdout for name in
                  ("Other", "Sunny", "Cloudy", "Overcast", "Rainy", "Thunder",
                   "Thundershower", "High-wind", "Snowy", "Foggy", "Sandstorm", "Haze")),
              no_out.stdout[:200])

    print(f"\n{passed} checks passed, {len(failed)} failed")
    for line in failed:
        print(f"  {line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
