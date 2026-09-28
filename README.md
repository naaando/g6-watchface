# g6-watchface

Tools for building, previewing and transferring watchfaces for the **JieLi
G6 / Trek 1** watch.

The thing to open first:

```
cd Fogg/dial-designer && npm install && npm run dev
```

Then **Decompile Existing Dial** and pick a `.bin` from `dials/`. It decodes in
the browser — no conversion step, no local server.

## What is here

| Path | What it is |
|---|---|
| `Fogg/dial-designer/` | The dial editor. Third-party (see below), and the tool dials are now tested in. |
| `dials/` | Every dial in the repository, one deduplicated copy of each, so the designer's file dialog has something to browse. [dials/README.md](dials/README.md) says where each came from. |
| `tools/` | The static server and the Cloudflare tunnel wrapper for sharing the designer, plus the `dials/` manifest generator. |
| `trek-watchfaces/` | Dials and the build scripts that compile them, plus the decoded reference dials. |
| `g6-cat-gauge-transfer/` | The cat-gauge dial packaged for transfer: compiled `.bin`, assets, source, and the JieLi sender APK project. |
| `ble-capture/` | Bluetooth HCI capture and parsing, for working out what the AuraFit app actually sends. |
| `Android-JL_Health/` | The stock JieLi health APK, kept for reference when reverse-engineering the protocol. |
| `Fogg/` | A third-party HK89 dial decompiler/compiler (`comp_decomp.py`) and the designer. Not part of this project. |
| `docs/` | Design notes, including the dial format and what the designer gets wrong. |

## Working on a dial

- **Editing or building one?** `Fogg/dial-designer`. It decompiles a `.bin` into
  layers you can select and move, and compiles back to a `.bin`.
- **Compiling from a script?** `trek-watchfaces/build_*.py`, via
  `Fogg/comp_decomp.py`.
- **Going over Bluetooth?** `ble-capture/` and `g6-cat-gauge-transfer/sender/`.

### The editor is a viewer, and it has known gaps

It renders complications from mock values, not from real sensor data, and a few
of those are wrong in ways that matter — the month is pinned to May, the steps
counter drops its leading digit, and the pulse ring follows the battery slider.
[docs/fogg-dial-format-and-renderer-bugs.md](docs/fogg-dial-format-and-renderer-bugs.md)
has the list with the file and line for each, plus the binary format notes that
were established along the way.

Do not trust the editor's output for `0x21` (the pulse ring) or for any
multi-glyph number until those are fixed.

## Sharing the designer

```
tools/tunnel.sh
```

Builds the designer and puts a public `https://*.trycloudflare.com` URL in
front of it — no account, no domain, no config. The hostname is random and
changes every run.

`tools/serve.py` is handed exactly one directory, the designer's `dist/`, so
publishing it does not expose the repository's `.git`, `Fogg/` source or
`ble-capture/`. A dev server is deliberately not used: it would also serve
`node_modules/` and the source tree.

The page fetches Pyodide from a CDN at runtime, so a viewer needs internet
access and the first load pulls a few MB.

## Tests

```bash
python3 -m pytest trek-watchfaces/tests/             # per-dial build assertions
python3 tools/build-dial-manifest.py --check        # the dials/ manifest is not stale
```

A dial is checked by rebuilding it, decompiling it with
`Fogg/comp_decomp.py` and asserting the block table and the pixels — see
`trek-watchfaces/tests/test_silver_cat.py` for the pattern.

The removed `preview/` carried a pure-JS port of `comp_decomp.py`, verified
byte-identical against it across every dial, plus 82 decoder, 27 renderer and
108 browser checks. It was removed on 2026-09-28 in favour of testing inside
the designer; it is still in the git history if the format work is ever needed
again.

## Upstream

`Fogg/` is a nested clone of `github.com/MiguelDLM/Fogg`, not a submodule, and
this repository never pushes to it. Two local, uncommitted changes there are
fixes worth sending upstream:

- `docs/DIAL_FORMAT_GUIDE.md` section E had the hand pivot convention backwards.
- `dial-designer/public/comp_decomp.py` was a stale copy that rewrote unknown
  block types on a round trip — `0xA1` became `0x81`, silently deleting the
  pulse ring. The repository-root copy already had the fix; `public/` now
  matches it.

So `git status` showing `M Fogg` is expected.
