#!/usr/bin/env python3
"""
Browser harness for the dial preview.

Loads dial.html in Chromium, drops a .bin in through the file input, and
checks that the canvas actually has the right pixels. This is the only place
the renderer gets exercised for real: the Node tests cover frame selection and
geometry, but only a browser can put a dial on a screen.

Run:
    python3 tests/browser/render.test.py

Requires playwright and a local http server (getImageData is tainted under
file://, so serving over http is mandatory, not a convenience).
"""

import http.server
import socket
import socketserver
import sys
import threading
from pathlib import Path

PREVIEW = Path(__file__).resolve().parents[2]
REPO = Path(__file__).resolve().parents[4]

# Dials to check, in the order they are exercised.
DIALS = [
    ("11448", REPO / "trek-watchfaces/0.0_AM05_G6_11448.bin"),
    ("cat-gauge-v1", REPO / "trek-watchfaces/cat-gauge/cat-gauge-v1.bin"),
    ("11359", REPO / "trek-watchfaces/0.0_AM05_G6_11359.bin"),
]

failures = []
checks = 0


def check(name, condition, detail=""):
    global checks
    checks += 1
    if not condition:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")
    else:
        print(f"  ok   {name}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory, port):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    port = free_port()
    httpd = serve(PREVIEW, port)
    base = f"http://127.0.0.1:{port}/index.html"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is required: python3 -m pip install playwright && playwright install chromium")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1100})

        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.on("console", lambda m: errors.append(f"CONSOLE {m.type}: {m.text}")
                if m.type == "error" else None)

        print(f"\nserving {PREVIEW} at {base}")
        page.goto(base)
        page.wait_for_timeout(400)

        check("page loads with no script errors", not errors, "; ".join(errors))
        check("empty state is visible before a dial is chosen",
              page.is_visible("#empty-state"), "the prompt should be showing")

        for label, path in DIALS:
            print(f"\n--- {label}")
            errors.clear()
            page.goto(base)
            page.wait_for_timeout(300)
            page.set_input_files("#file-input", str(path))
            page.wait_for_timeout(900)

            check(f"{label}: loads without script errors", not errors, "; ".join(errors))

            status = page.text_content("#status")
            check(f"{label}: reports success", "blocks from" in status, f"status was {status!r}")

            info = page.evaluate(
                """() => {
                    const app = window.appForTests;
                    return {
                        name: app.dial && app.dial.name,
                        blocks: app.dial ? app.dial.blocks.length : 0,
                        errors: app.dial ? app.dial.errors.length : -1,
                        hasClock: app.description && app.description.hasClock,
                        roles: app.description
                            ? app.description.blocks.map(b => b.name + '=' + b.role)
                            : [],
                        tableRows: document.querySelectorAll('#block-table tbody tr').length
                    };
                }"""
            )

            expected = {
                "11448": 8,
                "cat-gauge-v1": 9,
                "11359": 11,
            }[label]

            check(f"{label}: decoded every block", info["blocks"] == expected,
                  f"got {info['blocks']}, expected {expected}")
            check(f"{label}: no block errors", info["errors"] == 0, f"{info['errors']} failed")
            check(f"{label}: reported as a clock", info["hasClock"] is True, "no clock detected")
            check(f"{label}: block table lists every block",
                  info["tableRows"] == expected,
                  f"table shows {info['tableRows']}, expected {expected}")

            # The real test: are there pixels, and are they the right ones?
            stats = page.evaluate(
                """() => {
                    const canvas = document.getElementById('watchface-canvas');
                    const ctx = canvas.getContext('2d');
                    const {data} = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    let opaque = 0, distinct = new Set();
                    for (let i = 0; i < data.length; i += 4) {
                        if (data[i + 3] > 0) {
                            opaque++;
                            if (distinct.size < 500) {
                                distinct.add((data[i] << 16) | (data[i+1] << 8) | data[i+2]);
                            }
                        }
                    }
                    return {opaque, colours: distinct.size, total: data.length / 4};
                }"""
            )
            check(f"{label}: canvas is not blank", stats["opaque"] > stats["total"] * 0.9,
                  f"only {stats['opaque']}/{stats['total']} pixels painted")
            check(f"{label}: canvas has real artwork", stats["colours"] > 50,
                  f"only {stats['colours']} distinct colours")

            # Hands must actually move. Render the same dial at two times and
            # confirm the pixels changed: a hand stuck at 12 o'clock is the
            # failure mode that survives every geometry check.
            first = page.evaluate(
                """() => {
                    const c = document.getElementById('watchface-canvas');
                    return c.getContext('2d').getImageData(0,0,c.width,c.height).data.join(',');
                }"""
            )
            page.evaluate("() => window.appForTests.setTime(1, 7, 5)")
            page.wait_for_timeout(250)
            second = page.evaluate(
                """() => {
                    const c = document.getElementById('watchface-canvas');
                    return c.getContext('2d').getImageData(0,0,c.width,c.height).data.join(',');
                }"""
            )
            check(f"{label}: hands move when the time changes", first != second,
                  "the canvas is identical at 10:08:30 and 01:07:05")

            page.screenshot(path=f"/tmp/dial_{label}.png")
            print(f"       screenshot: /tmp/dial_{label}.png")

        # A file that is not a dial at all must fail cleanly.
        print("\n--- error handling")
        errors.clear()
        page.goto(base)
        page.wait_for_timeout(300)
        page.evaluate(
            """() => {
                const dt = new DataTransfer();
                dt.items.add(new File([new Uint8Array([1,2,3])], 'junk.bin',
                                      {type: 'application/octet-stream'}));
                const input = document.getElementById('file-input');
                input.files = dt.files;
                input.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        )
        page.wait_for_timeout(500)
        status = page.text_content("#status")
        check("a junk file reports an error", "Could not read" in status, f"status was {status!r}")
        check("a junk file raises no script errors", not errors, "; ".join(errors))
        check("the error overlay is shown", page.is_visible("#error-overlay"),
              "the overlay should explain the failure")
        check("the download button is disabled after a failure",
              page.is_disabled("#download"), "there is nothing to download")

        browser.close()

    httpd.shutdown()

    print(f"\n{checks} checks passed, {len(failures)} failed")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
