#!/usr/bin/env python3
"""
Validate preview assets for the G6 watchface.

Verifies that:
  1. Canvas size is 466x466
  2. All asset files referenced in config.js exist in preview/assets/
  3. Every layer declares a `block` type present in dial_desc.json
  4. Each layer's geometry (size, position, rotation center, frame count)
     matches its dial_desc.json block — this is what the compiler packs
  5. Every dial_desc.json block except BLK_PREV is covered by some layer

Filenames in config.js are intentionally NOT required to match dial_desc.json:
swapping artwork (e.g. a new background) is the whole point of the preview.
The compiler reads block types and geometry, not the preview's filenames.

Usage:
    python3 validate-preview-assets.py

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
"""

import json
import os
import re
import struct
import sys

# ─── Paths (resolved relative to this script's location) ─────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = SCRIPT_DIR
ASSETS_DIR = os.path.join(PREVIEW_DIR, "assets")
CONFIG_PATH = os.path.join(PREVIEW_DIR, "config.js")
DIAL_DESC_PATH = os.path.join(PREVIEW_DIR, "..", "assets", "dial_desc.json")

EXPECTED_CANVAS_SIZE = 466


def fail(errors):
    """Print all errors and exit with code 1."""
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    sys.exit(1)


def extract_config(config_path):
    """Extract WATCHFACE_CONFIG object from config.js using regex."""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the WATCHFACE_CONFIG assignment
    match = re.search(
        r"const\s+WATCHFACE_CONFIG\s*=\s*(\{[\s\S]*?\n\})\s*;",
        content,
    )
    if not match:
        return None, "Could not find WATCHFACE_CONFIG in config.js"

    config_text = match.group(1)

    # Strip // line comments and /* */ block comments (JS-only, not JSON)
    config_text = re.sub(r"/\*[\s\S]*?\*/", "", config_text)
    config_text = re.sub(r"(?m)//[^\n]*$", "", config_text)

    # Convert JS object notation to valid JSON:
    # - Replace single quotes with double quotes
    # - Remove trailing commas
    # - Quote unquoted keys
    # Step 1: quote unquoted keys (e.g., `width:` -> `"width":`)
    config_text = re.sub(
        r"([{,]\s*)([a-zA-Z_]\w*)\s*:",
        r'\1"\2":',
        config_text,
    )
    # Step 2: replace single-quoted strings with double-quoted
    config_text = re.sub(r"'([^']*)'", r'"\1"', config_text)
    # Step 3: remove trailing commas before } or ]
    config_text = re.sub(r",\s*([}\]])", r"\1", config_text)

    try:
        config = json.loads(config_text)
    except json.JSONDecodeError as e:
        return None, f"Failed to parse WATCHFACE_CONFIG as JSON: {e}"

    return config, None


def read_png_size(path):
    """Read (width, height) from a PNG IHDR chunk using only the stdlib."""
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG file: {path}")
    # IHDR is always the first chunk: 8-byte signature, 4-byte length,
    # 4-byte type "IHDR", then width and height as big-endian uint32.
    return struct.unpack(">II", header[16:24])


def validate_animpart(layer_name, layer, errors):
    """Validate a BLK_ANIMPART layer against the format guide's constraints.

    See Fogg/docs/DIAL_FORMAT_GUIDE.md section G:
      - the block must fit within the 466x466 screen
      - recommended max ~150x150, 5-12 frames
      - ctx = 10 selects time-based looping
      - full-screen 466x466 animations should stay at 4-6 frames
    """
    width = layer.get("width", 0)
    height = layer.get("height", 0)
    frames = layer.get("frames", 0)
    posx = layer.get("posx", 0)
    posy = layer.get("posy", 0)

    if width > EXPECTED_CANVAS_SIZE or height > EXPECTED_CANVAS_SIZE:
        errors.append(
            f"Layer '{layer_name}' (BLK_ANIMPART): {width}x{height} exceeds the "
            f"{EXPECTED_CANVAS_SIZE}x{EXPECTED_CANVAS_SIZE} screen"
        )

    if posx < 0 or posy < 0 or posx + width > EXPECTED_CANVAS_SIZE \
            or posy + height > EXPECTED_CANVAS_SIZE:
        errors.append(
            f"Layer '{layer_name}' (BLK_ANIMPART): position ({posx},{posy}) with size "
            f"{width}x{height} falls outside the {EXPECTED_CANVAS_SIZE}x{EXPECTED_CANVAS_SIZE} screen"
        )

    if frames < 1:
        errors.append(f"Layer '{layer_name}' (BLK_ANIMPART): frames must be >= 1")

    # The strip asset must actually contain `frames` bands.
    frame_w = layer.get("frameWidth", 0)
    frame_h = layer.get("frameHeight", 0)
    src = layer.get("src", "")
    if frame_w and frame_h and src:
        asset_path = os.path.join(PREVIEW_DIR, src)
        if os.path.isfile(asset_path):
            iw, ih = read_png_size(asset_path)
            if iw != frame_w:
                errors.append(
                    f"Layer '{layer_name}': frameWidth is {frame_w} but the strip is {iw}px wide"
                )
            expected_h = frame_h * frames
            if ih != expected_h:
                errors.append(
                    f"Layer '{layer_name}': strip is {ih}px tall but {frames} frames x "
                    f"{frame_h}px requires {expected_h}px"
                )

    if width > 150 and frames > 6:
        errors.append(
            f"Layer '{layer_name}' (BLK_ANIMPART): {width}x{height} with {frames} frames "
            f"risks exceeding the watch's frame buffer; the guide suggests 4-6 frames "
            f"for full-screen animations"
        )


def validate(config, dial_desc):
    """Run all validation checks. Returns list of error strings."""
    errors = []

    # ── Check 1: Canvas size ──────────────────────────────────────────────────
    width = config.get("width")
    height = config.get("height")
    if width != EXPECTED_CANVAS_SIZE or height != EXPECTED_CANVAS_SIZE:
        errors.append(
            f"Canvas size is {width}x{height}, expected {EXPECTED_CANVAS_SIZE}x{EXPECTED_CANVAS_SIZE}"
        )

    # ── Check 2: All referenced asset files exist ─────────────────────────────
    layers = config.get("layers", {})
    if not layers:
        errors.append("No layers found in WATCHFACE_CONFIG")
        return errors

    for layer_name, layer in layers.items():
        src = layer.get("src", "")
        if not src:
            errors.append(f"Layer '{layer_name}' has no 'src' field")
            continue

        asset_path = os.path.join(PREVIEW_DIR, src)
        if not os.path.isfile(asset_path):
            errors.append(
                f"Layer '{layer_name}': asset file not found: {src}"
            )

    # ── Check 3-5: Match layers to dial_desc blocks by type, not by filename ──
    dial_blocks = dial_desc.get("blocks", [])
    dial_by_type = {block["type"]: block for block in dial_blocks}

    for layer_name, layer in layers.items():
        block_type = layer.get("block")
        if not block_type:
            errors.append(f"Layer '{layer_name}' has no 'block' field")
            continue

        block = dial_by_type.get(block_type)

        # Optional blocks (e.g. BLK_ANIMPART) are legal firmware block types
        # that this dial simply doesn't use. They are absent from dial_desc.json,
        # so validate them against the format guide's constraints instead.
        if block is None:
            if not layer.get("optional"):
                errors.append(
                    f"Layer '{layer_name}': block type '{block_type}' not found in "
                    f"dial_desc.json (mark it 'optional: true' if it is a known "
                    f"block type the current dial does not use)"
                )
            validate_animpart(layer_name, layer, errors)
            continue

        # Geometry the compiler packs must match the descriptor exactly.
        expected = {
            "width": block["width"],
            "height": block["height"],
            "posx": block["posx"],
            "posy": block["posy"],
            "ctx": block["ctx"],
            "cty": block["cty"],
            "frames": block["frms"],
        }
        for key, want in expected.items():
            got = layer.get(key)
            if got != want:
                errors.append(
                    f"Layer '{layer_name}' ({block_type}): {key} is {got!r}, "
                    f"expected {want!r} from dial_desc.json"
                )

    # Every composable block must have a layer.
    covered_types = {layer.get("block") for layer in layers.values()}
    for block in dial_blocks:
        block_type = block.get("type", "")
        # BLK_PREV is the preview screenshot, not a composable layer
        if block_type == "BLK_PREV":
            continue
        if block_type not in covered_types:
            errors.append(
                f"dial_desc.json block '{block['fname']}' (type {block_type}) "
                f"has no corresponding layer in config.js"
            )

    return errors


def main():
    # ── Load config.js ────────────────────────────────────────────────────────
    if not os.path.isfile(CONFIG_PATH):
        fail([f"config.js not found at {CONFIG_PATH}"])

    config, err = extract_config(CONFIG_PATH)
    if err:
        fail([err])

    # ── Load dial_desc.json ───────────────────────────────────────────────────
    if not os.path.isfile(DIAL_DESC_PATH):
        fail([f"dial_desc.json not found at {DIAL_DESC_PATH}"])

    with open(DIAL_DESC_PATH, "r", encoding="utf-8") as f:
        dial_desc = json.load(f)

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = validate(config, dial_desc)

    if errors:
        fail(errors)

    print("preview assets: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
