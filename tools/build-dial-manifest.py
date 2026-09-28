#!/usr/bin/env python3
"""
Regenerate dials/manifest.json from whatever .bin files are in dials/.

The manifest is the catalogue of dials/: what each one is called, how big it
is, how many blocks it has, and where it came from. It is what makes the folder
browsable rather than just a pile of binaries.

It lives in tools/ rather than next to the dials so that dials/ holds nothing
but dial data.

Standard library only.

The block count is read straight from the header rather than by decoding:
byte 2 is `num_blocks` and bytes 0-1 are the paletted-table size, which is
enough to describe a dial without decoding 600 KB of pixels.

Hand-written `label` and `note` fields are preserved across regeneration, so
the script can be re-run freely without losing prose.

Usage:
    python3 tools/build-dial-manifest.py [--check]

    --check  exit 1 if the manifest on disk is stale, without writing it.
             For CI, or for noticing a .bin someone dropped in and forgot.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

DIALS = Path(__file__).resolve().parent.parent / "dials"
MANIFEST = DIALS / "manifest.json"


def describe(path):
    """Read just enough of the header to describe the dial in a dropdown."""
    raw = path.read_bytes()
    if len(raw) < 4:
        raise ValueError(f"{path.name}: too small to be a dial")
    return {
        "file": path.name,
        "label": None,  # filled in from the old manifest, or derived
        "bytes": len(raw),
        # sha256 prefix, so two dials that are byte-identical are visibly so
        "sha": hashlib.sha256(raw).hexdigest()[:12],
        "blocks": raw[2],
    }


def derive_label(filename):
    """`cat-gauge-v1.bin` -> `cat gauge v1`, for when there is no override."""
    stem = re.sub(r"\.bin$", "", filename, flags=re.IGNORECASE)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"^0\.0\s+", "", stem)  # the stock dials lead with "0.0 "
    return re.sub(r"\s+", " ", stem).strip()


def main():
    check_only = "--check" in sys.argv[1:]

    bins = sorted(p for p in DIALS.glob("*.bin") if p.is_file())
    if not bins:
        print(f"no .bin files in {DIALS}", file=sys.stderr)
        return 1

    # Keep hand-written prose: a manifest is edited by humans, and the .bin
    # files carry no room for a description of what a dial actually is.
    previous = {}
    if MANIFEST.exists():
        try:
            previous = {
                entry["file"]: entry for entry in json.loads(MANIFEST.read_text())["dials"]
            }
        except (KeyError, TypeError, json.JSONDecodeError) as err:
            print(f"warning: ignoring unreadable manifest ({err})", file=sys.stderr)

    entries = []
    for path in bins:
        entry = describe(path)
        old = previous.get(entry["file"], {})
        entry["label"] = old.get("label") or derive_label(entry["file"])
        if old.get("note"):
            entry["note"] = old["note"]
        entries.append(entry)

    document = {"dials": entries}
    text = json.dumps(document, indent=2) + "\n"

    if check_only:
        current = MANIFEST.read_text() if MANIFEST.exists() else ""
        if current != text:
            print("manifest is stale; run: python3 dials/build-manifest.py", file=sys.stderr)
            return 1
        print(f"manifest up to date ({len(entries)} dials)")
        return 0

    MANIFEST.write_text(text)
    for entry in entries:
        note = f"  {entry['note']}" if entry.get("note") else ""
        print(f"  {entry['file']:<30} {entry['blocks']:>2} blocks{note}")
    print(f"\nwrote {MANIFEST} ({len(entries)} dials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
