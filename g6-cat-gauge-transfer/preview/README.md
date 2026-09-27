# G6 Watchface Preview

Two HTML5 Canvas previews for G6 / Trek 1 watchfaces, sharing one decoder.

| Page | Use it for |
|---|---|
| `index.html` | **Looking at a dial.** Drop in any `.bin` and it decodes in the browser. |
| `authoring.html` | **Changing art before compiling.** Swaps background PNGs against a fixed geometry. |

Start with `index.html`. It needs nothing but a `.bin` file.

```
open index.html
```

---

## index.html — open a dial

Choose a `.bin` with the **Open .bin…** button, or drop one on the page. The
whole window is a drop target, so you do not have to aim.

The dial is decoded client-side by `bin-decoder.js`, a port of
`Fogg/comp_decomp.py`. Nothing is converted first, so this works on a dial
pulled straight off the device or out of an APK, and it works on dials this
repo has never seen.

Under **Blocks in this dial** is a table of everything the file contained,
which is the fastest way to confirm a decode did not silently drop something.

### What the preview does and does not do

Everything drawn is the dial's own artwork, from its own blocks. The preview
supplies values the firmware would normally read from sensors — battery,
steps, pulse, temperature — through sliders. The clock uses the browser's
`Date`, since there is no RTC here.

| Preview behaviour | Why |
|---|---|
| Complication values come from sliders | The device reads them from sensors. |
| Animation plays at 130 ms/frame | `BLK_ANIMPART`'s `ctx` selects looping, but not a speed. The firmware picks its own. |
| Hands rotate from the descriptor's `ctx`/`cty` | See the pivot note below — these fields are misnamed. |
| Animation is played even if `ctx` is not 10 | The preview cannot tell what triggers it, so it loops. |
| No preview thumbnail on screen | `BLK_PREVI` is the 280×280 image shown in the watch's face picker, not on the dial. |

If a block fails to decode the rest of the dial still renders and the status
line says which block. A file that is not a dial at all gets an error overlay
rather than a black screen.

---

## authoring.html — change art before compiling

This is the original page. It is for iterating on artwork: swap the PNGs in
`assets/`, reload, and see the result, without rebuilding a BIN.

Two dials are available via a query parameter:

```
open "file://$PWD/authoring.html?dial=11448"
```

> **macOS `open` caveat:** `open authoring.html?dial=11448` fails with "No such
> file or directory" — `open` treats the `?` as part of the filename. Pass a
> full `file://` URL as above. Double-clicking in Finder cannot pass a query
> string at all.

| id | Dial |
|---|---|
| `cat-gauge-analog-test` | Default. The current build, with swappable art. |
| `11448` | `0.0_AM05_G6_11448.bin`, a stock Trek 1 dial. |

Only dials with **identical geometry** belong in the selector — same block
types, sizes, positions and `ctx`/`cty`. Those differ only in artwork, so
switching is just pointing `src` at different PNGs. Verified block by block:
`0.0_AM05_G6_11448` and `cat_gauge_analog_test` match on all 8 blocks,
including the arms.

A dial with *different* geometry needs its own `config.js` and its own
`dial_desc.json`, since the descriptor is what the compiler packs and what
`validate-preview-assets.py` checks against. An unrecognised `?dial=` shows an
error rather than silently falling back.

To add a dial, copy its decoded assets under `assets/dials/<id>/` and add an
entry to `DIAL_ASSET_SETS` in `config.js`. The validator checks that every file
the selector can point at exists.

---

## Format notes worth knowing

These cost real debugging time. Each is verified against decoded pixels or
against `Fogg/comp_decomp.py`, not read off the spec.

### Arm pivots: `ctx` is measured from the bottom

The `ctx` / `cty` fields are named misleadingly.

- `cty` is the **horizontal** offset from the sprite's left edge, and equals
  `width / 2` for all three hands in every dial measured.
- `ctx` is the distance from the **bottom** edge, so `pivotY = height - ctx`.

For `0.0_AM05_G6_11448`:

| block | w × h | `ctx` | `cty` | real pivot (x, y) |
|---|---|---|---|---|
| `arm_hour` | 18 × 132 | 2 | 9 | (9, 130) |
| `arm_minute` | 16 × 182 | 2 | 8 | (8, 180) |
| `arm_second` | 28 × 256 | 44 | 14 | (14, 212) |

Implemented as `handPivot(block)` in `bin-decoder.js`. Reading the fields the
obvious way renders every hand 180° off while still converging on the dial
centre, so the error is easy to miss by eye.

`Fogg/docs/DIAL_FORMAT_GUIDE.md` section E described these incorrectly; it has
been corrected in the local Fogg checkout.

### Arm position is the pivot, not the sprite's corner

For arm blocks, `posx`/`posy` is where the pivot lands on screen — 233, 233 in
every dial measured — not the top-left of the sprite. So a 256px hand at
`posy=233` is normal, not an off-screen block. A naive bounding-box bounds
check will reject every hand in every dial.

### Frame strips are vertical

Frames stack top to bottom: a strip is `width` × (`height` × `frames`).
Animation strips and indicator strips alike. Reading them horizontally renders
frame 0 forever and is easy to miss when frame 0 looks plausible.

This was a real bug in the old `preview.js`, where `drawSpriteFrame` sliced
horizontally. `drawAnimFrame` in the same file had it right.

### `RGBA5658` is 3 bytes per pixel, not 4

One alpha byte, then RGB565 big-endian. The name is misleading.

### Blank indicator strips can be intentional

The `cat-gauge` builds write all-zero RGBA for `battery_strip`, `steps` and
`progress2` on purpose — see `trek-watchfaces/build_cat_gauge_analog_test.py`.
The artwork does not suit them. So "this indicator decodes to nothing" is not
necessarily a bug; compare against the build script before chasing it.

---

## Reusable modules

The three modules have no DOM dependency of their own beyond a canvas you hand
them, so they can be imported by another page, a test, or a build script.

| Module | Depends on | Does |
|---|---|---|
| `bin-decoder.js` | nothing | `.bin` → blocks with pixel data. Runs in Node. |
| `dial-renderer.js` | a canvas | blocks + data → pixels. |
| `dial-app.js` | a canvas, the two above | loading, clock, animation, state, PNG export. |

```js
const app = new G6DialApp({
  canvas: document.querySelector('canvas'),
  decoder: G6BinDecoder,
  renderer: G6DialRenderer
});

app.subscribe((app) => console.log(app.description.blocks.length, 'blocks'));
await app.loadBinFile(fileFromAnInput);
app.setData({ batteryPercent: 85 });
app.startClock();
const png = app.exportPng();
```

`bin-decoder.js` is a port of `Fogg/comp_decomp.py`, and is verified
byte-identical to it: every block of all 8 dials in the repo decodes to the
same SHA-256 in both. Run `node tests/compare-with-reference.js --all` to
re-check.

---

## Tests

```bash
node tests/bin-decoder.test.js     # 82 checks: header, RLE, geometry, errors
node tests/dial-renderer.test.js   # 21 checks: frame selection, hand angles
python3 tests/browser/render.test.py  # 33 checks: real Chromium, real pixels
node tests/compare-with-reference.js --all  # parity with Fogg/comp_decomp.py
```

The Python parity check needs Pillow and numpy; the rest do not. The browser
test needs Playwright, and starts its own http server because `getImageData`
is tainted under `file://`.

`tests/golden.json` holds per-block checksums so a change in the decoder shows
up as a test failure rather than a silently different preview. Regenerate with
`--update` when a dial legitimately changes.

### Two lessons from writing them

- **`node --check` cannot validate inline `<script>` in HTML.** A stray `});`
  left the page black with the status stuck on "Loading…" while the syntax
  check passed the whole time. Only a real browser catches that.
- **A test that never fails is not a test.** The first draft of the renderer
  tests asserted that indicator strips contain artwork, which is wrong for the
  `cat-gauge` builds. It looked like a decoder bug and was a bad assumption.

---

## File structure

```
preview/
├── index.html            # Open a .bin
├── authoring.html        # Swappable art against fixed geometry
├── bin-decoder.js        # .bin → blocks
├── dial-renderer.js      # blocks → pixels
├── dial-app.js           # loading, clock, animation, export
├── config.js             # authoring.html's layer config (from dial_desc.json)
├── preview.js            # authoring.html's compositor
├── preview.css           # authoring.html's styles
├── validate-preview-assets.py  # authoring.html's asset/geometry validator
├── make-anim-strip.py    # BLK_ANIMPART vertical strip from GIF/video
├── tests/
│   ├── bin-decoder.test.js
│   ├── dial-renderer.test.js
│   ├── compare-with-reference.js
│   ├── dump_reference.py      # the Python oracle
│   ├── fixtures.js
│   ├── golden.json
│   └── browser/render.test.py
├── *-smoke.html          # authoring.html smoke tests
└── assets/               # authoring.html's layer images
```
