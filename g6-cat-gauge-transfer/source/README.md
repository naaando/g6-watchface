# Cat Gauge analog test

This version uses the earlier blue, textured cat artwork and the eight block layout of the official G6 watchface `0.0_AM05_G6_11448.bin`. The original hour, minute, and second hand sprites were recolored while preserving their dimensions. Battery, step, and progress sprites are transparent because the artwork has no matching subdials.

- `preview-with-official-hands.png`: simulated appearance at 10:08:30; these three hand blocks are included in the BIN.
- `preview-digital-concept.png`: the same simulation with a **concept-only** digital time. The analog BIN does not include digital digits.
- `cat-gauge-analog-test.bin`: compiled analog test watchface.

The BIN compiled and decoded successfully. All eight block layouts match the official source. The decoded preview, background, and three hands match their inputs within RGB565 quantization (maximum 7 per RGB channel), and hidden complication layers remain transparent.

The previews approximate the device's hand rotation; the BIN has not yet been installed or tested on the G6.

## Onde conferir o resultado

O sistema de prévia foi removido em 2026-09-28; a verificação acontece agora no
editor do Fogg (`Fogg/dial-designer/`, na raiz do repositório), que abre qualquer
`.bin` e recompila para `.bin`. As notas de formato e a lista de defeitos do
renderizador estão em
[`docs/fogg-dial-format-and-renderer-bugs.md`](../../docs/fogg-dial-format-and-renderer-bugs.md).

Antes de recompilar, confira que `../assets/dial_desc.json` e os PNGs em
`../assets/` concordam em número, nome e dimensões:

```bash
python3 -c "import json;d=json.load(open('../assets/dial_desc.json'));print(len(d['blocks']),'blocos');[print('  ',b['type'],b['fname'],f\"{b['width']}x{b['height']}\") for b in d['blocks']]"
```

Cada bloco, menos `BLK_PREV`, deve ter o PNG correspondente em `../assets/`.
