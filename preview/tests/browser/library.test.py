#!/usr/bin/env python3
"""
Does the dial library select work, and does it stay a library?

Three things are being checked, in the order they break:

  1. `dials/manifest.json` describes every .bin in `dials/`, and every file it
     names is actually fetchable. A manifest that drifts from the folder is
     worse than no manifest: the select offers a dial that 404s on click.
  2. The select is populated from that manifest and picking an entry decodes
     the file. This is the path the tunnel exists for, so it has to work over
     http and not just via the file picker.
  3. Under `file://` the manifest is unreachable — fetch cannot read the
     filesystem — and the page must degrade to the file picker rather than
     showing a select that silently does nothing.

Drives tools/serve-preview.py, the same allowlist server the tunnel runs,
because that is the server whose routing has to be right.

Usage:
    python3 preview/tests/browser/library.test.py
"""

import functools
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PREVIEW = Path(__file__).resolve().parents[2]
REPO = PREVIEW.parent
DIALS = REPO / "dials"
MANIFEST = DIALS / "manifest.json"
SERVE = REPO / "tools" / "serve-preview.py"

fails = []


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ─── The manifest, before any browser is involved ────────────────────────────

print("-- dials/manifest.json matches dials/")
check(MANIFEST.exists(), "the manifest exists")
manifest = json.loads(MANIFEST.read_text())
entries = manifest["dials"]
on_disk = sorted(p.name for p in DIALS.glob("*.bin"))
check(
    sorted(e["file"] for e in entries) == on_disk,
    f"every .bin in dials/ is listed ({len(entries)} listed, {len(on_disk)} on disk)",
)
for entry in entries:
    check(
        (DIALS / entry["file"]).is_file() and entry["bytes"] == (DIALS / entry["file"]).stat().st_size,
        f"{entry['file']} exists and its recorded size is right",
    )
    check(
        1 <= entry["blocks"] <= 64 and entry["label"].strip(),
        f"{entry['file']} has a usable block count and label",
    )
check(
    len({e["file"] for e in entries}) == len(entries),
    "no duplicate entries, which would decode the same dial twice",
)

# Regenerating must be a no-op, or the manifest is already drifting.
regen = subprocess.run(
    [sys.executable, str(REPO / "tools" / "build-dial-manifest.py"), "--check"],
    capture_output=True, text=True,
)
check(regen.returncode == 0, f"the manifest is not stale ({regen.stdout.strip() or regen.stderr.strip()})")


def raw_get(path, port):
    """Status code for a request path sent verbatim, with no normalisation.

    urllib and curl both collapse `..` before the bytes leave the client, so a
    traversal test built on either of them silently tests the wrong URL. This
    puts the bytes on the wire by hand.
    """
    request = (
        f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(request)
        head = b""
        while b"\r\n" not in head:
            chunk = sock.recv(1024)
            if not chunk:
                break
            head += chunk
    first = head.split(b"\r\n", 1)[0].decode(errors="replace")
    match = re.search(r"\b(\d{3})\b", first)
    return int(match.group(1)) if match else 0


# ─── The allowlist server ───────────────────────────────────────────────────

port = free_port()
server = subprocess.Popen(
    [sys.executable, str(SERVE), "--port", str(port)],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
base = f"http://127.0.0.1:{port}"
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/", timeout=1).read()
            break
        except Exception:
            time.sleep(0.2)
    else:
        check(False, "the allowlist server came up")
        raise SystemExit(1)

    print("\n-- the allowlist server exposes nothing else")
    # The tunnel is a public URL, so a wrong 404 here is a real disclosure.
    for path, should_be_200 in [
        ("/index.html", True),
        ("/bin-decoder.js", True),
        ("/dials/manifest.json", True),
        ("/dials/0.0_G6_captured_618808.bin", True),
        ("/.git/config", False),
        ("/.git/HEAD", False),
        ("/../.git/config", False),
        ("/../Fogg/comp_decomp.py", False),
        ("/../ble-capture/log.txt", False),
        ("/../g6-cat-gauge-transfer/README.md", False),
        ("/preview/index.html", False),
        # dials/ is published, so it may only give up dial data and its
        # manifest -- not the generator, and not its own README.
        ("/dials/build-dial-manifest.py", False),
        ("/dials/README.md", False),
    ]:
        try:
            status = urllib.request.urlopen(base + path, timeout=5).status
        except urllib.error.HTTPError as err:
            status = err.code
        check(
            (status == 200) == should_be_200,
            f"GET {path} -> {status}" + ("" if should_be_200 else " (must not be served)"),
        )

    print("\n-- traversal, sent unnormalised so it is really tested")
    for path in [
        "/../../etc/passwd",
        "/../.git/config",
        "/dials/../.git/config",
        "/dials/../../tools/serve-preview.py",
        "/%2e%2e/.git/config",
        "/dials/%2e%2e%2f%2e%2e%2f.git%2fconfig",
    ]:
        status = raw_get(path, port)
        check(status in (400, 403, 404), f"GET {path} -> {status} (must not be served)")

    # ─── The page ────────────────────────────────────────────────────────────

    print("\n-- the select is populated and decodes what it offers")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/index.html")
        page.wait_for_function(
            "() => { const s = document.getElementById('dial-select');"
            " return s && !s.disabled && s.options.length > 1; }",
            timeout=15000,
        )
        check(not errors, f"the page loaded without script errors ({errors})")

        options = page.eval_on_selector_all(
            "#dial-select option:not([value=''])", "els => els.map(e => e.value)"
        )
        check(
            sorted(options) == on_disk,
            f"the select offers every dial in the folder ({len(options)} options)",
        )
        labels = page.eval_on_selector_all(
            "#dial-select option:not([value=''])", "els => els.map(e => e.textContent)"
        )
        check(
            all("blocks" in label for label in labels),
            "every option says how many blocks the dial has, so they are told apart",
        )
        check(
            "Library" in page.text_content("#library-note") or "library" in page.text_content("#library-note"),
            "the page says how many dials it found",
        )

        # Actually pick one and confirm it decodes. The captured dial is the
        # one with the most blocks, so it is also the one most likely to trip
        # a decoder edge case.
        target = "0.0_G6_captured_618808.bin"
        page.select_option("#dial-select", target)
        page.wait_for_function(
            f"() => window.appForTests.dial && window.appForTests.dial.name === {target!r}",
            timeout=15000,
        )
        loaded = page.evaluate(
            "() => ({ blocks: window.appForTests.dial.blocks.length,"
            " errors: window.appForTests.dial.errors.length,"
            " lit: (() => { const c = document.getElementById('watchface-canvas');"
            "   const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
            "   let n = 0; for (let i = 0; i < d.length; i += 4)"
            "     if (d[i] + d[i+1] + d[i+2] > 150) n++; return n; })() })"
        )
        check(loaded["blocks"] == 16, f"the picked dial has 16 blocks (got {loaded['blocks']})")
        check(loaded["errors"] == 0, f"it decoded with no block errors ({loaded['errors']})")
        check(loaded["lit"] > 20000, f"it actually painted something ({loaded['lit']} lit px)")
        check(
            target in page.text_content("#status"),
            "the status line names the dial that was picked",
        )

        # And the picker still works, so the select is an addition rather than
        # a replacement.
        other = REPO / "trek-watchfaces" / "0.0_AM05_G6_11448.bin"
        page.set_input_files("#file-input", str(other))
        page.wait_for_function(
            "() => window.appForTests.dial && window.appForTests.dial.name"
            " === '0.0_AM05_G6_11448.bin'",
            timeout=15000,
        )
        check(True, "the file picker still loads a dial the library does not have")

        print("\n-- under file:// the library degrades instead of breaking")
        page2 = browser.new_page()
        page2.on("pageerror", lambda e: errors.append(str(e)))
        page2.goto((PREVIEW / "index.html").resolve().as_uri())
        page2.wait_for_timeout(1200)
        state = page2.evaluate(
            "() => { const s = document.getElementById('dial-select');"
            " return { disabled: s.disabled, text: s.textContent,"
            "   fileInput: !!document.getElementById('file-input') }; }"
        )
        check(state["disabled"], "the select is disabled when the manifest cannot be read")
        check(
            "unavailable" in state["text"].lower(),
            f"and says so, rather than sitting there looking usable ({state['text']!r})",
        )
        check(state["fileInput"], "the file picker is still there")
        check("tools/serve-preview.py" in page2.text_content("#library-note"),
              "and the note explains how to get the library back")

        page.screenshot(path="/tmp/library.png")
        browser.close()
finally:
    server.terminate()
    server.wait(timeout=5)

print()
if fails:
    print(f"{len(fails)} failed")
    sys.exit(1)
print("library: PASS")
