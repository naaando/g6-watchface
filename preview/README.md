# G6 Watchface Preview

Two HTML5 Canvas previews for G6 / Trek 1 watchfaces, sharing one decoder.

This directory sits at the repository root and works on any dial — it is not tied
to the cat-gauge package. See the [repo README](../README.md) for the rest.

| Page | Use it for |
|---|---|
| `index.html` | **Looking at a dial.** Drop in any `.bin` and it decodes in the browser. |
| `authoring.html` | **Changing art before compiling.** Swaps background PNGs against a fixed geometry. |

Start with `index.html`. It needs nothing but a `.bin` file.

```
open index.html
```

Or serve the whole thing, which adds a dropdown of every dial in `dials/`:

```
tools/tunnel.sh
```

That starts a local server and publishes it on a public `trycloudflare.com`
URL. See [Publishing it](#publishing-it) below.

---

## index.html — open a dial

Pick a dial from the dropdown, or use the **Open .bin…** button, or drop a
file on the page. The whole window is a drop target, so you do not have to aim.

The dropdown is filled from [`dials/`](../dials) by a generated manifest, so it
only appears when the page is served over http. Opened as a `file://` URL,
`fetch` cannot read the filesystem, so the select is disabled and the button
and drop target carry on working. That is the primary way to use this and it is
not a downgrade.

The dial is decoded client-side by `bin-decoder.js`, a port of
`Fogg/comp_decomp.py`. Nothing is converted first, so this works on a dial
pulled straight off the device or out of an APK, and it works on dials this
repo has never seen.

### Publishing it

```bash
tools/tunnel.sh          # local :8000 plus a public https URL
tools/tunnel.sh 9000     # a different local port
tools/tunnel.sh 8000 --no-cloudflared   # local server only, no tunnel
```

`cloudflared tunnel --url` needs no account, no domain and no config file. The
hostname is random and changes every run, so do not bookmark it.

**The tunnel is public, so the server is an allowlist, not a file server.**
`tools/serve-preview.py` exposes exactly three things:

| URL | Comes from |
|---|---|
| `/…` | `preview/` |
| `/dials/<name>.bin`, `/dials/manifest.json` | `dials/` |
| `/g6-cat-gauge-transfer/preview-with-official-hands.png` | `authoring.html`'s reference image |

Everything else is a 404, including the repository's `.git/`, `Fogg/`,
`ble-capture/` and `Android-JL_Health/`. The `dials/` mount is narrowed further
to dial data only, so the manifest generator and `dials/README.md` are not
published either — which is why the generator lives in `tools/`.

`library.test.py` asserts all of that, including traversal attempts sent over a
raw socket, because `curl` and `urllib` both collapse `..` before the request
leaves the client and would silently test the wrong URL.

### Adding a dial to the dropdown

```bash
cp somewhere/new.bin dials/
python3 tools/build-dial-manifest.py
```

That is the whole workflow. The manifest generator reads the block count out of
the header, so describing a dial costs nothing even at 600 KB. Hand-written
`label` and `note` fields survive regeneration; everything else is overwritten.

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
necessarily a bug; compare against the build script before chasing it. The
stock `0.0_AM05_G6_11448` *does* carry real indicator artwork, so use it when
you want to prove the complication path works.

### A 10-frame block shows ONE digit, so the slider must reach one

Most `digits:` blocks have 10 frames and render a single digit — the frame index
is the value modulo 10. That makes the control's step size load-bearing: a
`steps` slider with `step="100"` can only ever land on values ending in 0, so
the block is pinned to frame 0 and looks permanently blank even though the
decode is perfect. `step="1"` is the fix. This shipped once.

Which field drives which block is also easy to get wrong, because the roles are
independent: `progress2` is an arc driven by the **battery** percentage, not by
calories. Moving the calorie slider does nothing to it.

### One glyph, drawn N times: how a `.bin` spells "03"

A single-digit block does not mean a single-digit display. The firmware repeats
the glyph to spell a zero-padded number, and the block's `posx` is the left
edge of the whole number, not of one digit.

`0.0_G6_captured_618808.bin` is the proof. Its `month` block is a 14x20 strip of
ten digits, and its `hours` block is 62x90 — yet the watch shows "09/27" and
"03:07". Drawing each block once, the obvious reading, gives "9", "7" and "5".

So the preview composes the number itself: `numberForRole` returns the whole
value, `padNumber` spells it at a fixed width, and `drawNumber` draws one
sprite per character, advancing a sprite width each time.

**How many glyphs is not in the file.** Nothing in the `.bin` states the width,
so it is a table — `DIGIT_COUNTS` in `dial-renderer.js` — read off a photo of
the live watch. `steps` is three digits there, `pulse` is two, and both blocks
are the same 12x18 sprite. If a dial disagrees with the table, that table is the
one place to change it. `isDigitStrip` keeps the exceptions honest: a 12-frame
`month` block holds the month **names** JAN..DEC, and `year` has no four-digit
glyph set, so neither is repeated.

### Type `0x21` is undocumented

`0.21` is not in Fogg's `BLOCK_TYPE_NAMES`. It appears on the captured dial as a
six-frame 100x100 ring sitting beside the `pulse` block and showing a segmented
heart-rate ring, so the decoder names it `pulse_ring` and the renderer drives it
from the pulse. Treat that as an inference from one dial, not a spec.

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
node tests/dial-renderer.test.js   # 27 checks: frame selection, hand angles, digit spelling
python3 tests/browser/render.test.py     # 34 checks: index.html in real Chromium
python3 tests/browser/authoring.test.py  # 7 checks: authoring.html boots, assets resolve
python3 tests/browser/indicators.test.py # 10 checks: complications draw and follow their slider
python3 tests/browser/digits.test.py     # 14 checks: multi-digit spelling, placeholders survive the clock
python3 tests/browser/library.test.py    # 54 checks: the dial dropdown, and what the tunnel does NOT expose
node tests/compare-with-reference.js --all     # parity with Fogg/comp_decomp.py
python3 tools/build-dial-manifest.py --check    # the dials/ manifest is not stale
```

The Python parity check needs Pillow and numpy; the rest do not. The browser
tests need Playwright, and start their own http server because `getImageData`
is tainted under `file://`.

Two of them serve something other than `preview/`, because that is what makes
a real path resolve:

- `render.test.py` and `authoring.test.py` serve the **repo root**, so
  `../dials/manifest.json` and `authoring.html`'s `../` reference image work
  the way they do in production. Serving `preview/` alone makes the manifest
  404, and a 404 is a console error, so the "loads without script errors" check
  would fail on a page that is behaving correctly.
- `library.test.py` drives `tools/serve-preview.py` itself, the allowlist
  server the tunnel runs, because its routing is the thing being tested.

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
- **Refreshing the clock must not touch anything else.** The app merged the
  renderer's whole default data provider on every tick, which reset every
  complication to `null`. The battery strip's frame 0 is its *empty red* frame,
  so the dial rendered a critical battery and empty gauges on a healthy watch —
  and no decode was at fault. `clockData()` exists so a tick can only move the
  clock; `digits.test.py` fails if the sensor fields come back.

---

## File structure

```
preview/                   # repository root
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
│   └── browser/
│       ├── render.test.py       # index.html in Chromium
│       ├── authoring.test.py    # authoring.html in Chromium
│       ├── indicators.test.py   # complications draw and follow their slider
│       ├── digits.test.py       # multi-digit spelling, placeholders vs the clock
│       ├── library.test.py      # the dial dropdown, and the allowlist server
│       └── inspect-dial.py      # not a test: dumps what a given .bin renders
├── *-smoke.html          # authoring.html smoke tests
└── assets/               # authoring.html's layer images
```
