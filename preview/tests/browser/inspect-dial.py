#!/usr/bin/env python3
"""Load an arbitrary dial .bin into preview/index.html and report what the
renderer actually drew, so a screenshot can be compared against the device.
"""
import http.server
import socket
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
PREVIEW = Path(__file__).resolve().parents[2]
REL = sys.argv[1] if len(sys.argv) > 1 else "trek-watchfaces/0.0_G6_captured_618808.bin"


def serve(directory):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


httpd, port = serve(PREVIEW)
errors = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1100})
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.goto(f"http://127.0.0.1:{port}/index.html")
        page.set_input_files("#file-input", str(REPO / REL))
        page.wait_for_function("() => window.appForTests && window.appForTests.dial", timeout=15000)
        page.wait_for_timeout(400)

        report = page.evaluate(
            """() => {
              const app = window.appForTests;
              const R = window.G6DialRenderer;
              const data = app.data || {};
              const rows = app.dial.blocks.map(b => ({
                name: b.name,
                size: b.width + 'x' + b.height,
                pos: b.posx + ',' + b.posy,
                frames: b.frames,
                role: R.roleOf(b),
                frame: R.frameForBlock(b, data),
              }));
              return { data: data, blocks: rows, errors: app.dial.errors, appError: app.error };
            }"""
        )
        print("app error:", report["appError"])
        print("data:", report["data"])
        print("decode errors:", report["errors"])
        print(f"{'block':16}{'size':10}{'pos':10}{'fr':>3}  {'role':22}{'frame':>5}")
        for r in report["blocks"]:
            print(f"{r['name']:16}{r['size']:10}{r['pos']:10}{r['frames']:>3}  {r['role']:22}{r['frame']:>5}")
        page.screenshot(path="/tmp/app-dial.png", full_page=True)
        page.locator("#watchface-canvas").screenshot(path="/tmp/app-canvas.png")
        print("page errors:", errors or "none")
        browser.close()
finally:
    httpd.shutdown()
