#!/usr/bin/env python3
"""
Serve the preview and the dial gallery, and nothing else.

This exists instead of `python3 -m http.server` at the repo root because the
preview is about to be published through a Cloudflare quick tunnel, which puts
it on the public internet. The repo root also holds `.git/`, `Fogg/` (a third
party clone), `ble-capture/` and `Android-JL_Health/`, none of which should be
reachable from a URL anyone can guess.

So this is an allowlist server, not a file server:

    /                              -> preview/
    /dials/<name>.bin              -> dials/
    /g6-cat-gauge-transfer/preview-with-official-hands.png

Everything else is a 404. Path traversal and dotfiles are rejected before the
lookup, so `..` cannot climb out of an allowed directory.

Standard library only.

Usage:
    python3 tools/serve-preview.py [--port 8000] [--host 127.0.0.1]
"""

import argparse
import functools
import http.server
import posixpath
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PREVIEW = REPO / "preview"
DIALS = REPO / "dials"

# url prefix -> (directory, allowed suffixes) pairs, most specific first: the
# root mount is the fallback, so it has to be tried last or it would swallow
# every other mount. The dials mount is restricted to dial data on purpose —
# it is the one folder served to a public URL that is not preview code, and it
# should never grow a build script.
MOUNTS = [
    ("/dials/", DIALS, (".bin",)),
    ("/", PREVIEW, None),  # None means "anything inside preview/"
]

# Individual files, because authoring.html reaches up out of preview/ for its
# reference image and a test asserts that image still decodes.
FILES = {
    "/g6-cat-gauge-transfer/preview-with-official-hands.png":
        REPO / "g6-cat-gauge-transfer" / "preview-with-official-hands.png",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # SimpleHTTPRequestHandler would happily walk out of the root; resolve
        # the URL against the allowlist by hand instead.
        clean = posixpath.normpath(path.split("?", 1)[0].split("#", 1)[0])
        if ".." in clean.split("/") or clean.startswith("/."):
            return str(REPO / "__denied__")

        if clean in FILES:
            return str(FILES[clean])

        for prefix, directory, suffixes in MOUNTS:
            if prefix != "/" and not clean.startswith(prefix):
                continue
            if prefix == "/":
                relative = clean.lstrip("/") or "index.html"
            else:
                relative = clean[len(prefix):]
            if ".." in relative.split("/") or relative.startswith("."):
                return str(REPO / "__denied__")
            name = posixpath.basename(relative)
            # A suffix list of None means the mount allows anything; otherwise
            # manifest.json is always allowed so the gallery can be read.
            if suffixes is not None and name != "manifest.json" and not name.endswith(suffixes):
                return str(REPO / "__denied__")
            candidate = (directory / relative).resolve()
            # Belt and braces: the resolved path must still be inside the
            # allowed directory, or a symlink could have walked away from it.
            if candidate.is_file() and str(candidate).startswith(str(directory.resolve()) + "/"):
                return str(candidate)
            if candidate.is_dir():
                index = candidate / "index.html"
                if index.is_file():
                    return str(index)
            return str(REPO / "__notfound__")

        return str(REPO / "__notfound__")

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            message = "not exposed by the allowlist server"
        super().send_error(code, message, explain)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if not PREVIEW.is_dir():
        print(f"missing {PREVIEW}", file=sys.stderr)
        return 1

    handler = functools.partial(Handler, directory=str(REPO))
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"serving {PREVIEW.name}/ and dials/ on http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
