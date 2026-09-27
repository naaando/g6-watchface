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
| Background | `assets/background.png` | 466×466 background image |
| Battery | `assets/battery_strip.png` | 6-frame battery indicator (0-5) |
| Steps | `assets/steps.png` | 10-frame step counter (0-9) |
| Progress | `assets/progress2.png` | 11-frame progress ring (0-10) |
| Hour hand | `assets/arm_hour.png` | Rotating hour hand |
| Minute hand | `assets/arm_minute.png` | Rotating minute hand |
| Second hand | `assets/arm_second.png` | Rotating second hand |

All positions, dimensions, and rotation centers come from `dial_desc.json` in the BIN descriptor.

### Simulated / Conceptual

| Feature | Status | Notes |
|---------|--------|-------|
| Digital time overlay | **CONCEPT ONLY** | Drawn programmatically on canvas. Not part of the actual BIN. Clearly labeled "DIGITAL CONCEPT — SIMULATED". |
| Real-time clock | **SIMULATED** | Uses browser's `Date` object. On the actual device, time comes from the watch's RTC. |
| Battery/Steps/Progress values | **SIMULATED** | Controlled via sliders. On the device, these come from actual sensors. |

## Controls

- **Hour / Minute / Second sliders** — Set hand positions manually
- **Battery slider** — Select battery level (0-5)
- **Steps slider** — Select step count (0-9)
- **Progress slider** — Select progress value (0-10)
- **Real-time Clock** — Animate hands using system time
- **Digital Concept** — Toggle the simulated digital time overlay
- **Reference** — Show the official reference image (`../preview-with-official-hands.png`) next to the canvas for comparison
- **Download PNG** — Export the current canvas as `g6-watchface-preview.png`

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
├── README.md           # This file
└── assets/             # Layer images
    ├── background.png
    ├── battery_strip.png
    ├── steps.png
    ├── progress2.png
    ├── arm_hour.png
    ├── arm_minute.png
    └── arm_second.png
```

## Reference Image

The reference image (`../preview-with-official-hands.png`) shows the watchface with official hands for visual comparison. Toggle "Reference" to display it side-by-side with the canvas preview.
