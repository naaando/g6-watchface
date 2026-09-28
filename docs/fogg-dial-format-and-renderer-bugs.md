# HK89 dial format notes, and what the Fogg designer gets wrong

Written while comparing `Fogg/dial-designer` against photos of a live G6 and
against `Fogg/comp_decomp.py`. The repository's own `preview/` did this work
until 2026-09-28; it was removed in favour of testing inside the designer, so
this file is where the findings live now.

Everything here was measured, not inferred, unless it says "assumed".

---

## 1. Block descriptor

20 bytes per block, from offset 4:

| Offset | Field | Notes |
|---|---|---|
| 0-3 | `image_offset` uint32le | |
| 4 | `pic_idx` | index into the picture-length table |
| 5 | *unused* | |
| 6-7 | `width` uint16le | |
| 8-9 | `height` uint16le | **one frame**, not the whole strip |
| 10-11 | `posx` uint16le | for hands this is the **pivot**, see §3 |
| 12-13 | `posy` uint16le | idem |
| 14 | `parts` | frame count |
| 15 | `block_type` | bit `0x80` set means RGBA |
| 16 | *align* int8 | |
| 17 | `compression` | 4 or 6 = RLE, else raw with 4-byte row alignment |
| 18 | `cent_x` int8 | see §2 |
| 19 | `cent_y` int8 | see §2 |

Header: `0-1` uint16le pltable size, `2` block count, `3` format (0x02). The
picture-length table sits at `4 + num_blocks*20` and holds one uint32le per
frame — that is the only thing delimiting frames, there is no end marker.

### Pixel formats

- **RGB565** — 2 bytes per pixel, **big-endian**.
- **RGBA5658** — 3 bytes per pixel, **not 4**: one alpha byte, then RGB565
  big-endian. The name is misleading.

Widen RGB565 with `r=((v>>11)&0x1F)<<3, g=((v>>5)&0x3F)<<2, b=(v&0x1F)<<3`.

### RLE

Each frame starts with a uint16le offset to the RLE commands. Then:

- `count == 0` → one literal pixel follows
- `count & 0x80` → the next pixel is repeated `count & 0x7F` times
  (**one** payload for the whole run — consuming one per repeat produces
  garbage that looks like a decoder bug)
- otherwise → `count` literal pixels follow

### Block types

`0x01` prev · `0x02` background · `0x03` hour hand · `0x04` minute hand ·
`0x05` second hand · `0x06` year · `0x07` month · `0x08` day · `0x09` hours ·
`0x0A` minutes · `0x0B` seconds · `0x0C` am/pm · `0x0D` weekday · `0x0E` steps
· `0x0F` pulse · `0x10` calories · `0x11` distance · `0x12` battery ·
`0x13` connection · `0x16` bigyo · `0x17` animation part · `0x18` battery
strip · `0x19` weather · `0x1A` temperature · `0x1E` progress ring 2 ·
`0x20` progress ring 1 · `0x25` label · `0x27` hour low digit · `0x28` hour
high digit · `0x29` minute high digit · `0x2A` minute low digit.

**`0x21` is undocumented.** Fogg names it `BLK_UNKNOWN2` and maps it to `0x20`
in `TYPE_MAP`. On `0.0_G6_captured_618808.bin` it is a 6-frame 100×100 ring
that belongs to the pulse block, so it is a 0-200 bpm gauge.

---

## 2. Hand pivots (`cent_x` / `cent_y`)

`Fogg/docs/DIAL_FORMAT_GUIDE.md` section E had this wrong. The correct
convention, verified against extracted sprite pixels in four dials with no
exceptions:

- `cent_x` is the **horizontal** offset from the sprite's left edge, and equals
  `width/2` for every hand in every dial.
- `cent_y` is measured **up from the bottom edge**, so
  `pivotY = height - cent_y`.

```
pivot = { x: cent_x, y: height - cent_y }
```

Reading `cent_y` as a distance from the top turns every hand 180° around. It is
easy to miss because the bases still converge on the centre.

---

## 3. `posx`/`posy` on a hand is the pivot, not the sprite's top-left

Every hand in every dial has `posx = posy = 233`. A 256 px hand at `posy = 233`
is normal, not off-screen. Any naive bounding-box check rejects every hand in
every dial.

---

## 4. Frame strips are vertical

A block of `w × h` with `frms` frames is stored `w × (h * frms)`, frames
stacked top to bottom. This applies to animation strips *and* to indicator
strips.

Proved on `battery_strip.png` (110×660, 6 frames): counting lit pixels in the
horizontal slice `sx = k*110, sy = 0` gives `[925, 0, 0, 0, 0, 0]`; the vertical
slice `sx = 0, sy = k*110` gives `[925, 1056, 1076, 1078, 1054, 915]`.

The old `preview.js` sliced horizontally, so every indicator was frozen on
frame 0. Frame 0 of a battery gauge happens to look plausible, which is why it
survived so long.

Frame-to-meaning is not uniform:

| Block | Frames | Frame *n* is |
|---|---|---|
| battery strip | 6 | a band: 0-5 / 6-20 / 21-40 / 41-60 / 61-80 / 81-100 % |
| progress ring | 11 | the arc at `round(pct/100 * 10)` |
| digit strip | 10 | the digit *n* |
| month | 12 | the **name** JAN..DEC |
| weekday | 7 | the whole SUN..SAT row with one day lit, Sunday first |
| `0x21` ring | 6 | the arc at `round(bpm/200 * 5)` |

---

## 5. A digit block is one glyph, drawn N times

The firmware repeats the same sprite side by side to spell a zero-padded
number, and `posx` is the left edge of the whole number.

Evidence: `0.0_G6_captured_618808.bin` has a 14×20 one-digit `month` strip and
a 62×90 one-digit `hours` strip, yet the device shows `09/27` and `03:07`.

The field widths are **not in the `.bin`**. Measured off a photo of the live
watch:

| Field | Glyphs | | Field | Glyphs |
|---|---|---|---|---|
| hours, minutes, seconds | 2 | | steps | 3 |
| month, day | 2 | | pulse | 2 |
| calories | 3 | | | |

`steps` and `pulse` are the same 12×18 sprite at different positions, 3 and 2
glyphs wide respectively.

Corollary that looks like a bug and is not: a slider with `step="100"` for
steps can only ever reach values ending in 0, so a 10-frame block stays on
frame 0 forever and reads as permanently blank.

---

## 6. Background is not animated

`BLK_BACKGROUND` is `frms: 1`, `colsp: RGB`, exactly 466×466. The firmware does
not animate the wallpaper. Animation is a separate `BLK_ANIMPART` (`0x17`),
`ctx = 10` meaning time-based looping.

A 466×466 animation with 10 frames needs over 4 MB of raw frame buffer and
will crash the watch. Keep it near 150×150 and 5-12 frames.

---

## 7. Blank complication blocks are often deliberate

The cat-gauge builds write all-zero RGBA for blocks 2..5 on purpose
(`trek-watchfaces/build_cat_gauge_analog_test.py`). A complication that decodes
to nothing is not necessarily a decode failure — check the build script before
hunting a bug.

---

## 8. Renderer bugs in `Fogg/dial-designer`

All of these are in `src/components/CanvasWatchface.tsx` unless noted, and all
were confirmed on screen by loading `0.0_G6_captured_618808.bin` into the
running designer.

| Symptom | Cause |
|---|---|
| Month is always May | `BLK_MONTH` is treated as a strip: `frameIdx = 4`. A 10-frame month block is a **digit** strip, and the two need different code. |
| Month is May **and** weekday is wrong | `:352` `new Date(mockState.year, 4, day).getDay()` — month hardcoded to 4, and a fake year. |
| Steps shows `20` for 6420 | `:198` `steps % 100`. The device shows 3 glyphs. |
| Steps number is 2 digits | Same line. Any multi-glyph field loses its leading digits. |
| Calorie, pulse and weather are frozen literals | `:203-212` hardcoded strings, and `weatherVal` defaults to 1. |
| The pulse ring follows the **battery** slider | `:334` `if (type === 'BLK_BATTS' \|\| type === 'BLK_UNK_A1')`. `BLK_UNK_A1` is `0x21`, a 0-200 bpm gauge, not a battery. |
| `BLK_ANIMPART` is compiled as a horizontal strip | It is vertical like everything else (§4). |

The designer is also, by design, a **viewer**: it cannot compile a `.bin` back
out, and the removed `preview/` could not either. Neither can be trusted for
`0x21` or for multi-glyph numbers until these are fixed.

---

## 9. The bundled `comp_decomp.py` was stale and silently corrupted dials

`dial-designer/public/comp_decomp.py` is a copy of `comp_decomp.py`, and it had
drifted: it lacked the `raw_type` preservation fix, so a decompile → compile
round trip rewrote any block type the tool does not model.

`TYPE_MAP` has no `0x21`/`0xA1` entry, so `TYPE_MAP.get(type_str, 0x01)` fell
through to `0x01` and the RGBA bit made it `0x81`. Measured on
`0.0_G6_captured_618808.bin`:

| `comp_decomp.py` | output | block 4 |
|---|---|---|
| `public/` (what the designer ran) | 609748 bytes | `0xA1` → `0x81` |
| repository root | 618808 bytes | preserved |

So opening that dial in the designer and pressing *Compile & Download .bin*
deleted the heart-rate ring with no warning. `public/` now has the same file as
the root, and a round trip through the running app is byte-identical.

**Both need to go upstream to `MiguelDLM/Fogg`.** As of 2026-09-28 they exist
only as uncommitted local changes in that clone.
