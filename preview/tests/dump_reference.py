#!/usr/bin/env python3
"""
Dump per-block checksums from a dial .bin using the Python reference decoder.

This is the independent oracle for the JavaScript decoder in bin-decoder.js.
The two implementations were written from the same format documentation, so
agreement between them is real evidence the JS port is correct; agreement
between the JS decoder and its own golden file is only regression safety.

Usage:
    python3 tests/dump_reference.py <dial.bin> [out.json]

Writes a JSON object keyed by block short name, each with the per-frame size,
the frame count, a sha256 of the decoded RGBA bytes, and the sum of those
bytes. Compare against what bin-decoder.js produces for the same file:

    node tests/compare-with-reference.js <dial.bin> <out.json>

Requires PIL and numpy, the same dependencies as Fogg/comp_decomp.py.
"""

import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np

# preview/tests/ -> preview/ -> repo root
REPO = Path(__file__).resolve().parents[2]
COMP_DECOMP = REPO / "Fogg" / "comp_decomp.py"


def load_reference():
    if not COMP_DECOMP.exists():
        sys.exit(f"reference decoder not found at {COMP_DECOMP}")
    spec = importlib.util.spec_from_file_location("comp_decomp", COMP_DECOMP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    ref = load_reference()
    data = Path(sys.argv[1]).read_bytes()

    num_blocks = data[2]
    pltable_offset = 4 + num_blocks * 20

    result = {}
    for i in range(num_blocks):
        o = 4 + i * 20
        image_offset = struct.unpack_from("<I", data, o)[0]
        pic_idx = data[o + 4]
        width = struct.unpack_from("<H", data, o + 6)[0]
        height = struct.unpack_from("<H", data, o + 8)[0]
        frames = data[o + 14]
        block_type = data[o + 15]
        compression = data[o + 17]

        base_type = block_type & 0x7F
        name = ref.BLOCK_TYPE_NAMES.get(base_type, ("unknown_%02X" % base_type, "?"))[0]

        frame_sizes = [
            struct.unpack_from("<I", data, pltable_offset + (pic_idx + k) * 4)[0]
            for k in range(frames)
        ]
        block_data = data[image_offset:image_offset + sum(frame_sizes)]

        if compression in (4, 6):
            if block_type & 0x80:
                arr = ref.decompress_rle_rgba(block_data, width, height, frames, frame_sizes)
            else:
                arr = ref.decompress_rle_rgb(block_data, width, height, frames, frame_sizes)
        else:
            if block_type & 0x80:
                arr = ref.decode_raw_rgba(block_data, width, height * frames)
            else:
                arr = ref.decode_raw_rgb(block_data, width, height * frames)

        # The Python tool emits RGB for blocks without an alpha bit; the JS
        # decoder always emits RGBA with alpha 255. Normalise before hashing.
        if not (block_type & 0x80):
            rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            rgba[..., :3] = arr
            rgba[..., 3] = 255
            arr = rgba

        result[name] = {
            "w": width,
            "h": height,
            "parts": frames,
            "sha": hashlib.sha256(arr.tobytes()).hexdigest(),
            "sum": int(arr.astype(np.int64).sum()),
        }

    if out_path:
        Path(out_path).write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote {out_path} ({len(result)} blocks)")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
