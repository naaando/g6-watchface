# Geometry

The three conventions that decide whether a block works. All three are
counter-intuitive, all three are verified against every dial in `dials/`, and
all three fail in a way that still looks plausible.

## 1. Frame strips are vertical

A block with `frms` frames is **one** image of `width x (height * frms)`, frames
stacked top to bottom. Not side by side.

Measured on `0.0_AM05_G6_11448.bin`'s `battery_strip` (110x660, 6 frames), by
counting lit pixels per crop:

| Slicing | Lit pixels per frame |
|---|---|
| horizontal, `sx = k*110, sy = 0` | `925, 0, 0, 0, 0, 0` |
| vertical, `sx = 0, sy = k*110` | `925, 1056, 1076, 1078, 1054, 915` |

The horizontal reading gives frame 0 a plausible gauge and five blank frames.
That is the whole failure: it renders fine and never updates.

## 2. A hand's pivot is measured from the bottom

For a block with a pivot, the descriptor's two centring bytes are named
confusingly. They are:

```
pivot = {x: cent_x, y: height - cent_y}
```

- `cent_x` (`cty` in `dial_desc.json`) is the **horizontal** offset from the
  sprite's left edge. It equals `width/2` for every hand in every dial, with no
  exceptions — verified across 12 hands in 4 dials.
- `cent_y` (`ctx`) is the distance from the sprite's **bottom** edge up to the
  pivot. It is not an offset from the top.

Measured:

| Dial | Block | Size | `ctx` | `cty` | Pivot |
|---|---|---|---|---|---|
| 11448 | `arm_hour` | 18x132 | 2 | 9 | (9, 130) |
| 11448 | `arm_minute` | 16x182 | 2 | 8 | (8, 180) |
| 11448 | `arm_second` | 28x256 | 44 | 14 | (14, 212) |
| 11359 | `arm_hour` | 38x150 | 18 | 19 | (19, 132) |
| 11359 | `arm_minute` | 28x184 | 13 | 14 | (14, 171) |
| 11359 | `arm_second` | 18x231 | 20 | 9 | (9, 211) |

Reading `ctx` as a top offset puts every hand 180 degrees out. That is easy to
miss by eye, because the *base* of a 180-degree-rotated hand still sits on the
centre of the face.

Sprite width must be even. On an odd-width sprite `width/2` is a half pixel and
the hand rotates about half a pixel off-centre forever. The second-hand preset
is 5px wide, and 5 + 2*10 padding = 25, so this is not hypothetical.

`Fogg/docs/DIAL_FORMAT_GUIDE.md` section E states this convention **wrong**.
That file is a third-party clone and must not be pushed to; the correction lives
in `docs/fogg-dial-format-and-renderer-bugs.md`.

## 3. On a hand block, posx/posy is the pivot

For every other block, `posx`/`posy` is the sprite's top-left on screen. For a
hand, it is **where the pivot goes**, which is `(233, 233)` in every dial that
has hands.

So a 256px hand at `posy=233` is correct, not a block hanging off the bottom of
the screen. Any bounds check written as `posx + width <= 466` rejects every hand
in every dial.

## 4. A digit block spells a number

A block with one glyph per frame holds **one** glyph. The watch draws the same
sprite **once per digit of the value**, side by side, zero-padded, advancing by
the sprite width each time.

Evidence: `0.0_G6_captured_618808.bin` has a 14x20 one-digit `month` strip and a
62x90 one-digit `hours` strip, and the watch shows `09` and `03`.

Field widths are **not** in the `.bin`. They are a property of the dial's
authoring, and this is the table to change when a dial disagrees:

| Field | Glyphs |
|---|---|
| `hours`, `minutes`, `seconds`, `month`, `day`, `pulse`, `dist`, `temp` | 2 |
| `steps`, `calor`, `battery` | 3 |

Because the value is zero-padded, a three-glyph steps field with a value of
`5000` renders `000`. Pick a placeholder that exercises the field.

## 5. Background is not animated

`BLK_BACKGROUND` is `frms:1`, `colsp:RGB`, exactly 466x466. The firmware does
not animate the wallpaper — no amount of frames will help.

Animation is a separate block, `BLK_ANIMPART` (0x17), with `ctx=10` selecting
time-based looping. A 466x466 x 10-frame animation is over 4MB of raw frame
buffer and **will crash the watch**. Keep it near 150x150 with 5-12 frames.

## 6. Blank complication blocks are often deliberate

Several builds write fully transparent RGBA to their indicator blocks on
purpose (`trek-watchfaces/build_cat_gauge_analog_test.py:65-66`). "This
complication decodes to nothing" is not by itself a decode failure.
