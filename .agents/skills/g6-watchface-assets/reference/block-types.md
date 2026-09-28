# Block types

The block type is descriptor byte 15. **Bit 0x80 set means RGBA**; the base type
is `type & 0x7F`. A 32-bit BGRA block and a 24-bit BGR block share a base type
and differ only in that bit, so a round trip must preserve the raw byte — which
is why `comp_decomp.py` keeps `raw_type` in the descriptor. Drop it and an
unmodelled type silently comes back as `0x81`.

Frame counts are not free. The watch indexes frames by value, and a strip with
the wrong count either never changes or shows the wrong thing.

| Code | Name | Frames | Holds |
|---|---|---|---|
| 0x01 | `prev` | 1 | previous/companion image |
| 0x02 | `background` | 1 | the wallpaper, 466x466, RGB, **not animated** |
| 0x03 | `arm_hour` | 1 | hour hand sprite; `posx`/`posy` is the pivot |
| 0x04 | `arm_minute` | 1 | minute hand sprite |
| 0x05 | `arm_second` | 1 | second hand sprite |
| 0x06 | `year` | — | year, usually blank |
| 0x07 | `month` | 10 or 12 | 10 = digits, 12 = month **names** |
| 0x08 | `day` | 10 | day of month, one digit per frame |
| 0x09 | `hours` | 10 | hour tens and ones, one glyph per frame |
| 0x0A | `minutes` | 10 | minute tens and ones |
| 0x0B | `seconds` | 10 | seconds |
| 0x0C | `ampm` | 2 | AM / PM |
| 0x0D | `weekd` | 7 | the full weekday row, one day lit per frame |
| 0x0E | `steps` | 10 | one digit |
| 0x0F | `pulse` | 10 | one digit |
| 0x10 | `calor` | 10 | one digit |
| 0x11 | `dist` | 10 | one digit |
| 0x12 | `battery` | 10 | one digit |
| 0x13 | `connect` | 2 | connected / not |
| 0x16 | `bigyo` | 1 | a single separator glyph |
| 0x17 | `animpart` | 5-12 | the actual animation, `ctx=10` loops it |
| 0x18 | `battery_strip` | 6 | a battery gauge, 6 levels |
| 0x19 | `weather` | 12 | one weather icon per frame |
| 0x1A | `temp` | 10 | one digit |
| 0x1E | `progress2` | 11 | an arc or bar that fills, 11 steps |
| 0x20 | `progress1` | 11 | a second progress bar |
| 0x21 | *undocumented* | 6 | a ring that fills — a 0-200 bpm gauge on the captured dial |
| 0x25 | `label` | — | a text label |
| 0x27 | `hour_lo` | 10 | low digit of the hour |
| 0x28 | `hour_hi` | 10 | high digit of the hour |
| 0x29 | `minute_hi` | 10 | high digit of the minute |
| 0x2A | `minute_lo` | 10 | low digit of the minute |

`0x21` is not in Fogg's own table. It was found on
`trek-watchfaces/0.0_G6_captured_618808.bin` (a 100x100, 6-frame block beside
the `pulse` block, showing a heart-rate ring) and named `pulse_ring` here on the
strength of a photo of the live watch. Treat the name as inferred.

## The two frame counts that bite

**`BLK_MONTH` is 10 or 12 and they are not interchangeable.** 12 frames hold the
month *names* (`JAN`..`DEC`); 10 frames hold *digits*. Building a 12-frame
numeric strip and setting `frms:12` shows a name; building a 7-frame weekday row
and setting `frms:7` on a digit block pins it to frame 0.

**A digit strip is one glyph.** See `geometry.md` §4. A 14x20 strip spelling
`09` by hand means the watch draws that two-glyph image once per digit.

## Checking a frame count

`make_digit_strip.py --block-type BLK_WEEKD` validates the count before writing
anything, and refuses:

```
$ python3 make_digit_strip.py --preset digits --block-type BLK_WEEKD --out w.png
BLK_WEEKD holds 7 frame(s) and 'digits' is 10
```

The types that are checked: `BLK_WEEKD` 7, `BLK_MONTH` 10 or 12, `BLK_BIGYO` 1,
and 10 for every other digit layer.
