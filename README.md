# g6-watchface

Tools for building, previewing and transferring watchfaces for the **JieLi
G6 / Trek 1** watch.

The thing to open first:

```
open preview/index.html
```

Pick any `.bin` and it decodes in the browser — no conversion step, no server.

To browse every dial in the repo from a dropdown, on your machine or on a
public URL:

```
tools/tunnel.sh
```

## What is here

| Path | What it is |
|---|---|
| `preview/` | The watchface preview. `index.html` opens a `.bin`; `authoring.html` swaps art before compiling. See [preview/README.md](preview/README.md). |
| `dials/` | Every unique dial in the repo, copied under one name each so the preview can offer them as a dropdown. [dials/README.md](dials/README.md) says where each came from. |
| `tools/` | The allowlist static server and the Cloudflare tunnel wrapper, plus the `dials/` manifest generator. |
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

## Sharing the preview

`tools/tunnel.sh` serves the preview on a local port and puts a public
`https://*.trycloudflare.com` URL in front of it — no account, no domain, no
config. The hostname is random and changes every run.

The server is an allowlist rather than a file server, so publishing it exposes
`preview/`, `dials/*.bin` and one reference image, and nothing else in the
repository. That boundary is enforced by
`preview/tests/browser/library.test.py`, which is worth re-reading before
widening what the server hands out.

## Tests

```bash
node preview/tests/compare-with-reference.js --all  # decoder vs. the Python original
node preview/tests/bin-decoder.test.js              # 82 structural checks
node preview/tests/dial-renderer.test.js            # frame selection, hand angles, digit spelling
python3 preview/tests/browser/render.test.py        # 34 checks in real Chromium
python3 preview/tests/browser/authoring.test.py     # authoring.html boots and its assets resolve
python3 preview/tests/browser/indicators.test.py    # complications draw and follow their slider
python3 preview/tests/browser/digits.test.py        # multi-digit numbers, and the clock leaving them alone
python3 preview/tests/browser/library.test.py       # the dial dropdown, and what the tunnel does NOT expose
python3 preview/validate-preview-assets.py          # authoring.html assets vs dial_desc.json
python3 tools/build-dial-manifest.py --check        # the dials/ manifest is not stale
```
