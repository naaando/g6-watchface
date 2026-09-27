# g6-watchface

Tools for building, previewing and transferring watchfaces for the **JieLi
G6 / Trek 1** watch.

The thing to open first:

```
open preview/index.html
```

Pick any `.bin` and it decodes in the browser — no conversion step, no server.

## What is here

| Path | What it is |
|---|---|
| `preview/` | The watchface preview. `index.html` opens a `.bin`; `authoring.html` swaps art before compiling. See [preview/README.md](preview/README.md). |
| `trek-watchfaces/` | Dials and the build scripts that compile them, plus the decoded reference dials. |
| `g6-cat-gauge-transfer/` | The cat-gauge dial packaged for transfer: compiled `.bin`, assets, source, and the JieLi sender APK project. |
| `ble-capture/` | Bluetooth HCI capture and parsing, for working out what the AuraFit app actually sends. |
| `Android-JL_Health/` | The stock JieLi health APK, kept for reference when reverse-engineering the protocol. |
| `Fogg/` | A third-party HK89 dial decompiler/compiler (`comp_decomp.py`). Not part of this project. |
| `docs/` | Implementation plans. |

## The two ways to look at a dial

- **Already have a `.bin`?** `preview/index.html`. It is a pure-JS port of
  `Fogg/comp_decomp.py`, verified byte-identical against it across every dial in
  `trek-watchfaces/`.
- **About to change the artwork?** `preview/authoring.html`. It keeps
  `dial_desc.json`'s geometry fixed and lets you swap background PNGs, so what
  you see is what the compiler will pack.

## Tests

```bash
node preview/tests/compare-with-reference.js --all  # decoder vs. the Python original
node preview/tests/bin-decoder.test.js              # 82 structural checks
node preview/tests/dial-renderer.test.js            # frame selection, hand angles
python3 preview/tests/browser/render.test.py        # 33 checks in real Chromium
python3 preview/tests/browser/authoring.test.py     # authoring.html boots and its assets resolve
python3 preview/validate-preview-assets.py          # authoring.html assets vs dial_desc.json
```
