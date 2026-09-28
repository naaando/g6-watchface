# Silver Cat — G6 / Trek 1

The background comes from the user's 1264 × 1264 silver-cat PNG in `source/user-cat.png`, resized to the G6's 466 × 466 canvas. The live `HH:MM` digits sit in the black area above the cat. The colon is part of the background; the watch draws the four digits from two ten-frame RGBA strips.

`silver-cat.bin` retains the 16 block types and order of `0.0_G6_captured_618808.bin`, a dial captured while AuraFit sent it to the G6. The other dynamic blocks are transparent. `preview-large.png` shows 10:08 for visual review; those digits are not fixed in the BIN's background.

Build from the repository root with a Python environment containing Pillow and NumPy:

```sh
python3 trek-watchfaces/build_silver_cat.py
```

The build compiles and decodes locally. Its appearance and live digits still require a real transfer to the G6. The sender app's Dials page can select a downloaded `.bin` through its file picker; disconnect AuraFit before that app connects to the watch.
