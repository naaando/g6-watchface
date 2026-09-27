#!/usr/bin/env python3
"""
Do the complication blocks actually render, and do they follow their slider?

Three separate failure modes are covered, all of which look identical on
screen ("the indicator is empty"):

  1. The block decodes to nothing at all. Real for the cat-gauge builds, which
     deliberately pack transparent strips — see build_cat_gauge_analog_test.py.
     For 11448 the indicators carry real artwork, so empty pixels here is a bug.
  2. The block draws, but sits on frame 0 forever because the slider is
     quantised below the block's resolution. A 10-frame block shows ONE digit,
     so a step=100 steps slider pins that digit at 0 and the block looks dead.
     This actually shipped once; the whole point is to catch it coming back.
  3. The right slider is wired to the wrong field, so moving it does nothing.

Usage:
    python3 preview/tests/browser/indicators.test.py
"""

import functools
import http.server
import socket
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

PREVIEW = Path(__file__).resolve().parents[2]
REPO = PREVIEW.parent
# 11448 is the stock dial: unlike the cat-gauge builds it has real indicator
# artwork, so it can actually prove the complication path works.
BIN = REPO / "trek-watchfaces" / "0.0_AM05_G6_11448.bin"

# Screen-space rects, from the block table. The canvas is 280px for a 466px
# screen, so these are scaled in JS.
RECTS = {
    "battery_strip": (178, 78, 110, 110),
    "steps": (234, 304, 12, 18),
    "progress2": (178, 271, 110, 110),
}

fails = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def set_value(page, selector, value):
    page.eval_on_selector(
        selector,
        """(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }""",
        value,
    )
    page.wait_for_timeout(220)


def region_digest(page, x, y, w, h):
    """Count lit pixels and hash the block's rect on the canvas."""
    return page.evaluate(
        """([x, y, w, h]) => {
            const c = document.getElementById('watchface-canvas');
            const g = c.getContext('2d');
            const s = c.width / 466;
            const d = g.getImageData(
                Math.round(x * s), Math.round(y * s),
                Math.max(1, Math.round(w * s)), Math.max(1, Math.round(h * s))
            ).data;
            let lit = 0, hash = 2166136261;
            for (let i = 0; i < d.length; i += 4) {
                // the artwork under these blocks is dark; count the lit marks
                if (d[i] + d[i + 1] + d[i + 2] > 150) lit++;
                hash ^= d[i] + d[i + 1] * 3 + d[i + 2] * 7 + i;
                hash = Math.imul(hash, 16777619);
            }
            return { lit, hash: hash >>> 0 };
        }""",
        [x, y, w, h],
    )


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
httpd = http.server.HTTPServer(
    ("127.0.0.1", port), functools.partial(Quiet, directory=str(PREVIEW))
)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/index.html")
        page.set_input_files("#file-input", str(BIN))
        page.wait_for_timeout(700)
        check(not errors, f"11448 loaded without page errors ({errors})")

        # Freeze the clock so only the slider under test moves.
        page.eval_on_selector(
            "#real-time",
            "el => { el.checked = false; el.dispatchEvent(new Event('change', {bubbles: true})); }",
        )
        page.wait_for_timeout(200)

        print("\n-- failure mode 1: the block decoded to nothing")
        for name, rect in RECTS.items():
            d = region_digest(page, *rect)
            check(d["lit"] > 0, f"{name} draws something ({d['lit']} lit px)")

        print("\n-- failure modes 2 and 3: the block is frozen on frame 0")
        # Each entry pairs the block with the field that actually drives it.
        # `steps` is a 10-frame digit block, so the two values must differ in
        # their last digit; progress2 is a battery arc, not a calorie arc.
        for block, slider, low, high, restore in [
            ("battery_strip", "#battery", 0, 100, 60),
            ("steps", "#steps", 1230, 5679, 4820),
            ("progress2", "#battery", 0, 100, 60),
        ]:
            set_value(page, slider, low)
            at_low = region_digest(page, *RECTS[block])
            set_value(page, slider, high)
            at_high = region_digest(page, *RECTS[block])
            check(
                at_low["hash"] != at_high["hash"],
                f"{block} repaints when {slider} moves",
            )
            check(
                at_low["lit"] != at_high["lit"],
                f"{block} changes by more than a stray pixel "
                f"({at_low['lit']} -> {at_high['lit']} lit)",
            )
            set_value(page, slider, restore)

        # The regression that motivated this file: a coarse step pins the digit.
        step_attr = page.get_attribute("#steps", "step")
        check(
            step_attr == "1",
            f"the steps slider resolves to single steps (step={step_attr!r}), "
            "or a one-digit block can never leave frame 0",
        )

        page.screenshot(path="/tmp/indicators.png")
        browser.close()
finally:
    httpd.shutdown()

print()
if fails:
    print(f"{len(fails)} failed")
    sys.exit(1)
print("complications: PASS")
