---
name: g6-watchface-assets
description: Generate the PNG assets an HK89 / G6 / Trek 1 watchface needs, in the exact geometry the dial compiler packs - glyph strips and hand sprites. Use when creating or changing artwork for a dial block, when a block renders the wrong frame, blank, sideways, off-centre, or rotating about the wrong point, or when assembling the assets for a new .bin.
---

# G6 watchface assets

Every image in a `.bin` is a **vertical strip**: the frames of one block
stacked top to bottom in a single image of `width x (height * frames)`. Not
side by side. This is the mistake that survives review, because frame 0 of most
blocks is a valid-looking image — a battery gauge that reads "empty" instead of
"full", a weekday row where only "SUN" is lit. It is not discovered until
someone owns the watch and notices the number never changes.

These scripts are Python ports of the generators inside Fogg's designer
(`Fogg/dial-designer/src/components/`), kept behaviour-compatible so a strip
built here drops into the same block a strip built in the designer would have.
The designer is the reference; where the two deliberately differ, the script
says why.

## Which script

| Need | Script |
|---|---|
| Digits, weekday rows, month names, any single glyph | `scripts/make_digit_strip.py` |
| A hand sprite, with the pivot and `ctx`/`cty` computed for you | `scripts/make_hand_sprite.py` |

Run `python3 <script> --help` for the full flags. Both take `--json` and report
what they built, including per-frame alpha bounding boxes — use it to check the
result rather than trusting that a file appeared.

Not yet ported from the designer: the battery/progress gauge
(`BatteryGenerator.tsx`), the weather icons (`WeatherGenerator.tsx`), and the
two slicers (`AnimationSlicer.tsx`, `SpriteSlicerModal.tsx`). Until then, build
those in the designer and copy the PNG out.

## The two rules that matter most

**A glyph block holds one glyph, and the watch draws it once per digit.** A
14x20 one-digit strip is how the watch spells `09`. Make a strip that already
contains several characters and the watch draws it repeatedly. `posx` is the
left edge of the whole number, not of one glyph, and the value is zero-padded —
so `--frame-width` is a per-glyph advance.

**A hand's pivot is measured from the wrong-looking edge.** `cty` is the
horizontal offset from the sprite's left and is always `width/2`. `ctx` is the
distance from the sprite's **bottom** up to the pivot, so `pivot.y = height -
ctx`. And on a hand block `posx`/`posy` is where the **pivot** goes on screen,
not the top-left of the sprite. `make_hand_sprite.py` prints all of it; there is
no reason to compute it by hand.

## Start here

1. `make_digit_strip.py` for the time, passing `--block-type` so the frame count
   is checked rather than assumed.
2. `make_hand_sprite.py` for hour/minute/second.
3. Assemble with one of the `trek-watchfaces/build_*.py` scripts, which pack the
   PNGs into a `.bin` against a `dial_desc.json`.

## Then verify

```bash
python3 scripts/test_assets.py
```

51 checks encoding the failures that are invisible on screen: a sideways strip,
a glyph flush against the cell edge, a frozen frame, a tofu box where a digit
should be, a hand rotating about half a pixel off-centre. Run it after touching
anything here, and if you add a check, confirm it fails when you break the thing
it guards.

To see a dial whole, use the Fogg designer (`Fogg/dial-designer/`, `npm run dev`)
— it is also the only way to get a `.bin` back out. Its preview has known gaps
(`docs/fogg-dial-format-and-renderer-bugs.md`): the month, weekday, step count
and heart-rate ring are all rendered from the wrong source there, so **do not
trust what it shows for a complication**. Confirm in the compiled `.bin`.

## Reference

- `reference/block-types.md` — block types, frame counts, what each is for.
  Read before deciding a frame count.
- `reference/geometry.md` — the pivot convention, vertical strips, and the digit
  block that spells a number.
