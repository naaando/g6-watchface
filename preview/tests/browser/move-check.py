#!/usr/bin/env python3
"""Post-move check: both pages load clean from preview/ at the repo root."""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PREVIEW = Path(__file__).resolve().parents[2]
REPO = Path(__file__).resolve().parents[3]
PORT = 8731

fails = []


def check(cond, label):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        fails.append(label)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # index.html — the .bin page
    errs = []
    page = browser.new_page(viewport={"width": 900, "height": 1200})
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"http://127.0.0.1:{PORT}/index.html")
    page.wait_for_timeout(600)
    check(not errs, f"index.html no page errors ({errs})")
    check(page.locator("#file-input").count() == 1, "index.html has the file input")
    page.set_input_files(
        "#file-input", str(REPO / "trek-watchfaces" / "0.0_AM05_G6_11448.bin")
    )
    page.wait_for_timeout(800)
    status = page.text_content("#status")
    check("8 blocks" in status, f"index.html loaded 11448 after the move ({status!r})")
    page.screenshot(path="/tmp/move_index.png")

    # authoring.html — the art page, whose reference image path had to change
    errs2 = []
    page2 = browser.new_page(viewport={"width": 1100, "height": 1400})
    page2.on("pageerror", lambda e: errs2.append(str(e)))
    failed = []
    page2.on("requestfailed", lambda r: failed.append(r.url))
    page2.goto(f"http://127.0.0.1:{PORT}/authoring.html")
    page2.wait_for_timeout(600)
    check(not errs2, f"authoring.html no page errors ({errs2})")
    check(
        page2.locator("#status").inner_text().strip() != "",
        "authoring.html reached a status",
    )
    bad = [u for u in failed if "favicon" not in u]
    check(not bad, f"no failed asset requests ({bad})")
    page2.screenshot(path="/tmp/move_authoring.png")
    print("  status:", page2.locator("#status").inner_text().strip())
    browser.close()

print()
if fails:
    print(f"{len(fails)} failed")
    sys.exit(1)
print("move check: PASS")
