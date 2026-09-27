#!/usr/bin/env python3
"""
Validate preview assets for the G6 watchface.

Verifies that:
  1. All asset files referenced in config.js exist in preview/assets/
  2. Canvas size is 466x466
  3. Block names (filenames) in config.js match dial_desc.json

Usage:
    python3 validate-preview-assets.py

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
"""

import json
import os
import re
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

    # ── Check 3: Block names match dial_desc.json ─────────────────────────────
    dial_blocks = dial_desc.get("blocks", [])
    dial_fnames = {block["fname"] for block in dial_blocks}

    for layer_name, layer in layers.items():
        src = layer.get("src", "")
        if not src:
            continue
        fname = os.path.basename(src)
        if fname not in dial_fnames:
            errors.append(
                f"Layer '{layer_name}': filename '{fname}' not found in dial_desc.json"
            )

    # ── Check 4: Every dial_desc block (except BLK_PREV) has a config layer ──
    config_fnames = {
        os.path.basename(layer.get("src", ""))
        for layer in layers.values()
        if layer.get("src")
    }
    for block in dial_blocks:
        fname = block["fname"]
        block_type = block.get("type", "")
        # BLK_PREV is the preview screenshot, not a composable layer
        if block_type == "BLK_PREV":
            continue
        if fname not in config_fnames:
            errors.append(
                f"dial_desc.json block '{fname}' (type {block_type}) has no corresponding layer in config.js"
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
