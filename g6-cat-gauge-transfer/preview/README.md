# G6 Watchface Preview

Interactive HTML5 Canvas preview for the G6/Trek 1 "cat_gauge_analog_test" watchface.

## Opening the Page

Open `index.html` directly in any modern browser. No server required — works with `file://` protocol.

```
open index.html
# or
firefox index.html
# or
google-chrome index.html
```

## What's Real vs Simulated

### Real Data (from BIN / dial_desc.json)

| Layer | Source | Description |
|-------|--------|-------------|
| Background | `assets/cat-background.png` | 466×466 background image (art swapped freely; the filename need not match the BIN) |
| Battery | `assets/battery_strip.png` | 6-frame battery indicator (0-5) |
| Steps | `assets/steps.png` | 10-frame step counter (0-9) |
| Progress | `assets/progress2.png` | 11-frame progress ring (0-10) |
| Hour hand | `assets/arm_hour.png` | Rotating hour hand |
| Minute hand | `assets/arm_minute.png` | Rotating minute hand |
| Second hand | `assets/arm_second.png` | Rotating second hand |

All positions, dimensions, and rotation centers come from `dial_desc.json` in the BIN descriptor.

#### Arm rotation pivots (`ctx` / `cty`)

The `ctx` / `cty` fields in `dial_desc.json` are named misleadingly. Verified
against the extracted sprites of this dial:

| block | width | height | `ctx` | `cty` | real pivot (x, y) |
|---|---|---|---|---|---|
| `BLK_ARM_HOUR` | 18 | 132 | 2 | 9 | (9, 130) |
| `BLK_ARM_MINUTE` | 16 | 182 | 2 | 8 | (8, 180) |
| `BLK_ARM_SECOND` | 28 | 256 | 44 | 14 | (14, 212) |

- `cty` is the **horizontal** offset from the left edge, and equals `width / 2`
  for all three hands.
- `ctx` is the distance from the **bottom** edge to the pivot, so
  `pivotY = height - ctx`. It is *not* a distance from the top.

`getHandPivot(block)` in `preview.js` implements this. Getting it wrong renders
every hand 180° off while still converging on the dial centre, so the error is
easy to miss by eye — the in-browser check is to render at 10:08:30 and compare
each hand's tip angle (expected 304° / 51° / 180°) via `getImageData`.

Note: `Fogg/docs/DIAL_FORMAT_GUIDE.md` section E described these fields
incorrectly; it has been corrected in the local Fogg checkout.

### Optional Blocks (not in this dial's descriptor)

| Layer | Source | Description |
|-------|--------|-------------|
| Animation | `assets/animpart.png` | `BLK_ANIMPART` (0x17) looping animation, 6 frames at 100ms (10fps) |

`BLK_ANIMPART` is a real firmware block type that this particular dial does not
use, so it is absent from `dial_desc.json`. Layers like this are marked
`optional: true` in `config.js`; the validator checks them against the format
guide's constraints instead of the descriptor, and the preview degrades
gracefully if the asset is missing.

Constraints from `Fogg/docs/DIAL_FORMAT_GUIDE.md` (section G):

- The block must fit inside the 466×466 screen
- Recommended maximum: ~150×150 px, 5–12 frames
- `ctx = 10` selects time-based looping
- Full-screen 466×466 animations exist (dial templates 3274, 7235, 10044) but
  stay at **4–6 frames** — 10 full-screen frames exceed 4 MB of raw frame
  buffer and will crash the watch

Animation assets are **vertical strips**: one frame per `frameHeight` row band.
Indicator blocks (battery, steps, progress) are **horizontal strips**. Build a
strip from a GIF or video with:

```bash
python3 make-anim-strip.py source.gif assets/animpart.png --frames 6 --size 150
```

### Simulated / Conceptual

| Feature | Status | Notes |
|---------|--------|-------|
| Digital time overlay | **CONCEPT ONLY** | Drawn programmatically on canvas. Not part of the actual BIN. Clearly labeled "DIGITAL CONCEPT — SIMULATED". |
| Real-time clock | **SIMULATED** | Uses browser's `Date` object, on by default. On the actual device, time comes from the watch's RTC. |
| Battery/Steps/Progress values | **SIMULATED** | Controlled via sliders. On the device, these come from actual sensors. |

## Controls

The preview opens in a clean state: just the watchface running on the system
clock. Everything else is behind the **Detalhes** disclosure.

Always visible:

- **Real-time Clock** — Animate hands using system time. On by default.
- **Detalhes** — Expands the inspection controls below.
- **Download PNG** — Export the current canvas as `g6-watchface-preview.png`

Inside **Detalhes**:

- **Hour / Minute / Second sliders** — Set hand positions manually. Touching any
  of them stops the real-time clock and unchecks it, since you are asking for a
  fixed time.
- **Battery slider** — Select battery level (0-5)
- **Steps slider** — Select step count (0-9)
- **Progress slider** — Select progress value (0-10)
- **Digital Concept** — Toggle the simulated digital time overlay
- **Animation** — Pause/resume the `BLK_ANIMPART` loop (shown only when an animation layer is present)
- **Reference** — Show the official reference image (`../preview-with-official-hands.png`) next to the canvas for comparison

## Generating New Images for the Compiler

To regenerate the layer images from the BIN:

1. Extract the BIN file from the device or APK
2. Parse `dial_desc.json` to get block definitions
3. Extract each block's frames as individual PNGs
4. Place them in `assets/` with the filenames referenced in `config.js`

The `dial_desc.json` in `g6-cat-gauge-transfer/assets/` contains the full block layout with positions, dimensions, and frame counts.

## File Structure

```
preview/
├── index.html          # Main preview page
├── preview.js          # Canvas compositor + state management
├── config.js           # Layer configuration (from dial_desc.json)
├── preview.css         # Styles
├── export-smoke.html   # Export smoke test
├── compositor-smoke.html  # Compositor smoke test
├── state-smoke.html    # State management smoke test
├── validate-preview-assets.py  # Asset/geometry validator (stdlib only)
├── make-anim-strip.py  # Build a BLK_ANIMPART vertical strip from GIF/video
├── README.md           # This file
└── assets/             # Layer images
    ├── cat-background.png  # Active background (art is swappable)
    ├── background.png      # Original background from the BIN
    ├── animpart.png        # BLK_ANIMPART vertical strip (6 frames)
    ├── battery_strip.png
    ├── steps.png
    ├── progress2.png
    ├── arm_hour.png
    ├── arm_minute.png
    └── arm_second.png
```

## Reference Image

The reference image (`../preview-with-official-hands.png`) shows the watchface with official hands for visual comparison. Toggle "Reference" to display it side-by-side with the canvas preview.
