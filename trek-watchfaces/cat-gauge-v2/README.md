# Cat Gauge v2

Revised G6 / Trek 1 watchface based on the two visual references supplied by the user. The original cat in the left half of the gauge, blue nitrous-style arc, red limiter arc, and dark right half are preserved as the main composition. The time is represented by live four-digit sprites plus analog hour, minute, and second hands.

- `preview-large.png`: 466 × 466 review preview at 10:08:30.
- `cat-gauge-v2.bin`: compiled watchface.
- `assets/`: generated background, hand sprites, digit strip, and block metadata.
- `decoded/`: images extracted from the compiled BIN for validation.
- `../build_cat_gauge_v2.py`: reproducible asset builder.

The build and reverse decode passed: nine blocks were recovered, all alpha values matched, and every RGB channel differed by no more than 7 units because of RGB565 quantization. The watchface has **not** been uploaded to the watch. The digital sprite blocks still require an on-watch compatibility test.
