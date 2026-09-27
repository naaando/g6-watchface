# Cat Gauge analog test

This version uses the earlier blue, textured cat artwork and the eight block layout of the official G6 watchface `0.0_AM05_G6_11448.bin`. The original hour, minute, and second hand sprites were recolored while preserving their dimensions. Battery, step, and progress sprites are transparent because the artwork has no matching subdials.

- `preview-with-official-hands.png`: simulated appearance at 10:08:30; these three hand blocks are included in the BIN.
- `preview-digital-concept.png`: the same simulation with a **concept-only** digital time. The analog BIN does not include digital digits.
- `cat-gauge-analog-test.bin`: compiled analog test watchface.

The BIN compiled and decoded successfully. All eight block layouts match the official source. The decoded preview, background, and three hands match their inputs within RGB565 quantization (maximum 7 per RGB channel), and hidden complication layers remain transparent.

The previews approximate the device's hand rotation; the BIN has not yet been installed or tested on the G6.

## Validação de assets da prévia

Antes de recompilar o BIN, valide os assets do sistema de prévia:

```bash
python3 ../preview/validate-preview-assets.py
```

Isso garante que os PNGs em `preview/assets/` estão consistentes com `../assets/dial_desc.json` e que o canvas é 466×466. Após a validação, copie os assets atualizados para `assets/` e execute o compilador.
