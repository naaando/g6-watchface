#!/usr/bin/env python3
"""
Does a numeric block render the whole number, and do placeholders survive?

A `digits:<field>` block in a .bin is a strip of ten single-digit glyphs. The
firmware spells a multi-digit number by drawing that one glyph repeatedly, so
a renderer that draws the block once shows "3" where the watch shows "03".
That gap is invisible in a unit test of frame selection, because frame
selection was never wrong — only the composition was.

This also pins the regression where the app merged the renderer's whole
default data provider on every clock tick. That reset every complication to
null, so a battery strip fell back to frame 0, which is its *empty red* frame,
and every indicator bar drew empty. Placeholder data that reads as broken is
worse than no placeholder.

Uses 0.0_G6_captured_618808.bin because it is the dial whose on-device
appearance is known: it shows "03:07", "09/27" and "311" from single-digit
strips.

Usage:
    python3 preview/tests/browser/digits.test.py
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
BIN = REPO / "trek-watchfaces" / "0.0_G6_captured_618808.bin"

fails = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def lit(page, x, y, w, h):
    """Lit pixel count inside a screen-space rect (466-based coordinates)."""
    return page.evaluate(
        """([x, y, w, h]) => {
            const c = document.getElementById('watchface-canvas');
            const g = c.getContext('2d');
            const s = c.width / 466;
            const d = g.getImageData(
                Math.round(x * s), Math.round(y * s),
                Math.max(1, Math.round(w * s)), Math.max(1, Math.round(h * s))
            ).data;
            let n = 0;
            for (let i = 0; i < d.length; i += 4) {
                if (d[i] + d[i + 1] + d[i + 2] > 150) n++;
            }
            return n;
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
        page.wait_for_function(
            "() => window.appForTests && window.appForTests.dial", timeout=15000
        )
        page.wait_for_timeout(400)
        check(not errors, f"the dial loaded without page errors ({errors})")

        print("\n-- a single-digit strip spells a multi-digit number")
        # month is a 14x20 one-digit strip at (201,429) and the watch shows
        # "09". The second glyph therefore has to occupy x 215..229. If the
        # renderer draws the block once, that cell stays empty.
        for label, x, y, w, h in [
            ("month", 201, 429, 14, 20),
            ("month, second glyph", 215, 429, 14, 20),
            ("day", 237, 429, 14, 20),
            ("day, second glyph", 251, 429, 14, 20),
            ("hours", 31, 187, 62, 90),
            ("hours, second glyph", 93, 187, 62, 90),
            ("minutes", 181, 187, 62, 90),
            ("minutes, second glyph", 243, 187, 62, 90),
        ]:
            n = lit(page, x, y, w, h)
            check(n > 0, f"{label} is drawn ({n} lit px)")

        print("\n-- a name strip is not a number")
        # A 12-frame month block holds JAN..DEC, not digits; repeating a glyph
        # there would index a name strip as if it were a number.
        names = page.evaluate(
            """() => {
                const R = window.G6DialRenderer;
                const m = window.appForTests.dial.blocks.find(b => b.name === 'month');
                return { frames: m.frames, digit: R.isDigitStrip(R.roleOf(m), m) };
            }"""
        )
        check(
            names["frames"] == 10 and names["digit"],
            f"this dial's month block is a {names['frames']}-frame digit strip, "
            "so it is spelled as digits",
        )

        print("\n-- placeholder complications survive the clock")
        # Two clock ticks is enough: the old code merged the full default
        # provider on every tick, so one tick was already fatal.
        page.wait_for_timeout(2200)
        data = page.evaluate("() => window.appForTests.data")
        check(data["batteryPercent"] == 60, f"battery is still 60 after ticking ({data['batteryPercent']})")
        check(data["steps"] == 4820, f"steps are still 4820 after ticking ({data['steps']})")
        frame = page.evaluate(
            """() => {
                const app = window.appForTests;
                const b = app.dial.blocks.find(x => x.name === 'battery_strip');
                return window.G6DialRenderer.frameForBlock(b, app.data);
            }"""
        )
        check(frame != 0, f"the battery strip is off its empty frame 0 (frame {frame})")

        page.screenshot(path="/tmp/digits.png")
        browser.close()
finally:
    httpd.shutdown()

print()
if fails:
    print(f"{len(fails)} failed")
    sys.exit(1)
print("digits: PASS")
