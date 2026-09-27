# Cat Gauge for G6 / Trek 1

An original cat illustration inspired by the blue tachometer style of *Need for Speed Underground 2*. The 466 × 466 dial combines moving hour, minute, and second hands with a live four-digit digital time display. `assets/prev.png` shows the intended appearance at 10:08.

- `cat-gauge-v1.bin`: compiled watchface for review and a later on-watch test.
- `assets/`: source images and `dial_desc.json`.
- `decoded/`: images and metadata extracted back from the compiled BIN for validation.
- `../build_cat_gauge.py`: source code that draws the face.

Build from the project root:

```sh
python trek-watchfaces/build_cat_gauge.py
python Fogg/comp_decomp.py -c trek-watchfaces/cat-gauge/assets trek-watchfaces/cat-gauge/cat-gauge-v1.bin
python Fogg/comp_decomp.py trek-watchfaces/cat-gauge/cat-gauge-v1.bin trek-watchfaces/cat-gauge/decoded
```

The Fogg compiler's `rgb888_to_rgb565` function was patched locally to cast NumPy color channels to Python integers before 16-bit shifts. Without this, red and green bits overflow and the preview turns blue.

The BIN compiles and decompiles into nine expected blocks. Decoded RGB pixels differ from source by at most 7 per channel, as expected from RGB565 quantization; RGBA alpha channels are identical. The new digital-time block types have not been verified on this specific watch, and the BIN has **not** been transferred to it.
