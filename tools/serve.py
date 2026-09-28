#!/usr/bin/env python3
"""Serve exactly one directory over HTTP, and nothing else.

The repository root must never be the served directory: it holds `.git/`,
`Fogg/`, `ble-capture/` and captured device data. So this script takes the one
directory to publish as an argument, and the boundary is the argument itself
rather than a list of rules to keep in sync.

Used by tools/tunnel.sh to publish the Fogg designer's production build. The
browser then fetches Pyodide from a CDN, so the public page needs internet
access; the local server itself has no outbound traffic.

    python3 tools/serve.py Fogg/dial-designer/dist --port 8000

Stdlib only. Not hardened for hostile traffic, only for not handing out more
than it was told to.
"""

from __future__ import annotations

import argparse
import http.server
import posixpath
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Types the browser needs for this to be a working app. Anything else is 404,
# which keeps a stray .py or .json in the served directory from being a
# download link.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    root: Path
    verbose: bool

    def translate_path(self, path: str) -> str:
        """Resolve a URL path inside self.root, or return a path that cannot exist.

        Super's version would happily walk out of the root. We normalise the
        request first, so a traversal attempt collapses onto the root instead
        of escaping it, and then we re-check containment.
        """
        raw = unquote(urlsplit(path).path)
        raw = raw.split("?", 1)[0].split("#", 1)[0]
        parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".", "..")]
        if any(p.startswith(".") for p in parts):
            return str(self.root / "__forbidden__")
        candidate = self.root.joinpath(*parts) if parts else self.root
        if candidate.is_dir():
            candidate = candidate / "index.html"
        try:
            candidate.resolve().relative_to(self.root)
        except ValueError:
            return str(self.root / "__forbidden__")
        return str(candidate)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        raw = unquote(urlsplit(self.path).path)
        # A directory request is fine, it resolves to its index.html below.
        if not raw.endswith("/"):
            target = Path(self.translate_path(self.path))
            # Reject the file before opening it, so an unknown suffix cannot
            # become a download link for a stray .py or .json in the tree.
            if not target.is_file() or posixpath.splitext(target.name)[1].lower() not in CONTENT_TYPES:
                self.send_error(404)
                return
        # A browser that navigates away mid-download, or closes a tunnel
        # connection, is routine. Without this the log fills with tracebacks
        # that look like a broken server.
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def end_headers(self) -> None:
        # The designer is a dev tool being reloaded constantly; a cached bundle
        # after an edit is pure confusion.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        return CONTENT_TYPES.get(posixpath.splitext(path)[1].lower(), "application/octet-stream")

    def log_message(self, fmt: str, *args) -> None:
        if self.verbose:
            sys.stderr.write("  %s\n" % (fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="the one directory to publish")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    handler = type(
        "BoundHandler",
        (Handler,),
        {"root": root, "verbose": not args.quiet},
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    server.daemon_threads = True

    print(f"serving {root} on http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
