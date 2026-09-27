#!/usr/bin/env python3
"""
Smoke test for authoring.html.

render.test.py covers index.html (the .bin page). This covers the other page:
that it boots, declares its global, and loads every layer asset from the repo
root's preview/ directory. Run it after moving the preview or renaming assets —
a path that only index.html uses would otherwise go unnoticed.

Usage:
    python3 preview/tests/browser/authoring.test.py
"""

import functools
import http.server
import socket
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

PREVIEW = Path(__file__).resolve().parents[2]
# Serve the repo root, not preview/. authoring.html reaches up with "../" for
# the reference image, exactly as it does under file://. Serving preview/ as
# the root would make that climb escape the server and 404, which is an
# artefact of the test rather than a real breakage.
REPO = PREVIEW.parent

fails = []


def check(cond, label):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        fails.append(label)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(directory):
    """Start a throwaway server so relative asset paths resolve like in a browser."""
    handler = functools.partial(QuietHandler, directory=str(directory))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd = http.server.HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


httpd, port = serve(REPO)
BASE = f"http://127.0.0.1:{port}/preview/authoring.html"

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 1400})

        errors = []
        failed_requests = []
        console_errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed_requests.append(r.url))
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )

        page.goto(BASE)
        page.wait_for_timeout(800)

        check(not errors, f"no page errors ({errors})")
        check(
            not console_errors, f"no console errors ({console_errors})"
        )
        bad = [u for u in failed_requests if "favicon" not in u]
        check(not bad, f"every asset resolved ({bad})")

        status = (page.text_content("#status") or "").strip()
        check(status == "Ready", f"status is Ready (was {status!r})")

        # The layers are loaded asynchronously; assert they actually decoded,
        # since a wrong src path can leave the page "Ready" but blank.
        opaque = page.evaluate(
            """() => {
                const c = document.getElementById('watchface-canvas');
                const g = c.getContext('2d');
                const d = g.getImageData(0, 0, c.width, c.height).data;
                let n = 0;
                for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
                return n;
            }"""
        )
        total = 466 * 466
        check(
            opaque > total * 0.5,
            f"the canvas actually painted ({opaque}/{total} opaque)",
        )

        check(
            page.evaluate("typeof window.WATCHFACE_CONFIG") == "object",
            "WATCHFACE_CONFIG is exposed for the smoke tests",
        )

        # The reference image lives outside preview/ and is reached with "../".
        # That is the one path a move would break, so assert it decodes.
        img_ok = page.evaluate(
            """async () => {
                const img = document.getElementById('reference-image');
                await img.decode();
                return img.naturalWidth > 0 && img.naturalHeight > 0;
            }"""
        )
        check(bool(img_ok), "the ../ reference image decodes")

        page.screenshot(path="/tmp/authoring-page.png")
        browser.close()
finally:
    httpd.shutdown()

print()
if fails:
    print(f"{len(fails)} failed")
    sys.exit(1)
print("authoring.html: PASS")
