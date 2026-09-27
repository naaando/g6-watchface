# Cat Gauge image test

This is a display-only test watchface built from the user's second reference image. The gauge was cropped and resized to 466 × 466 pixels; its artwork and visible numbers were not redrawn. `preview-large.png` shows exactly what this static version is meant to display.

The BIN uses the eight block types, frame counts, dimensions, positions, color formats, and compression settings from the official G6 watchface `0.0_AM05_G6_11448.bin`. Its battery, steps, progress, and three hand layers are fully transparent so the supplied image is unobstructed.

This test does **not** display the live time: the needle and `1 88 Km/h` are pixels in the image. It has not been installed on the watch. The purpose is to validate that a custom background can be packaged and displayed before adding working clock components.

Build and validate from the project root:

```sh
python trek-watchfaces/build_cat_gauge_image_test.py
python Fogg/comp_decomp.py -c trek-watchfaces/cat-gauge-image-test/assets trek-watchfaces/cat-gauge-image-test/cat-gauge-image-test.bin
python Fogg/comp_decomp.py trek-watchfaces/cat-gauge-image-test/cat-gauge-image-test.bin trek-watchfaces/cat-gauge-image-test/decoded
```

The compiled BIN was decoded successfully. All eight block layouts match the official source; the decoded background differs by at most 7 units per RGB channel due to RGB565 conversion; all dynamic blocks remain transparent.
