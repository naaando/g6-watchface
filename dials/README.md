# dials/

The dial gallery. One curated `.bin` per watchface design in the repository, so
the preview can offer them in a dropdown instead of asking anyone to hunt
through six directories of duplicates.

## Why these files exist twice

The repository originally kept its dials where the tooling that produced them
lives, which is the right place for a build script and the wrong place for a
gallery. There were 22 `.bin` files, but only 9 distinct ones: six copies of
`cat-gauge-analog-test.bin` and a `decoded/source.bin` next to nearly every
original.

The originals have **not** been moved or deleted. They are still where the
build and decode scripts expect them. What is here is a flat, deduplicated
copy of one of each, kept under its original filename so the connection to its
source is obvious.

| File | Original | What it is |
|---|---|---|
| `0.0_AM05_G6_11359.bin` | `trek-watchfaces/` | Stock dial, 11 blocks: month/day/weekday complications and three subs |
| `0.0_AM05_G6_11448.bin` | `trek-watchfaces/` | Stock dial, 8 blocks: battery gauge, steps and two progress arcs |
| `0.0_G6_captured_618808.bin` | `trek-watchfaces/` | Captured off a live G6 over BLE, 16 blocks, a different dial family |
| `cat-gauge-v1.bin` | `trek-watchfaces/cat-gauge/` | First cat-gauge attempt, four 28x58 digit blocks |
| `cat-gauge-v2.bin` | `trek-watchfaces/cat-gauge-v2/` | Same, with 34x62 digits |
| `cat-gauge-analog-test.bin` | `trek-watchfaces/cat-gauge-analog-test/` | The dial `g6-cat-gauge-transfer/` ships, 434 KB |
| `cat-gauge-image-test.bin` | `trek-watchfaces/cat-gauge-image-test/` | Background-image-only test |
| `roundtrip_11359.bin` | `trek-watchfaces/` | 11359 decoded and recompiled, to prove the round trip is lossless |
| `roundtrip_11448.bin` | `trek-watchfaces/` | Same for 11448 |

`manifest.json` is generated. Do not edit it by hand and expect it to stick —
`label` and `note` survive regeneration, but every other field is overwritten:

```bash
python3 tools/build-dial-manifest.py          # rewrite
python3 tools/build-dial-manifest.py --check  # fail if stale
```

## Adding a dial

1. Copy the `.bin` into this folder.
2. Run `python3 tools/build-dial-manifest.py`.
3. Reload the preview. The select picks it up on its own.

## What is published

`tools/tunnel.sh` puts this folder on a public URL. The server that fronts it
allows `.bin` files and `manifest.json` out of this directory and nothing
else, so this README and the generator are not published even though they live
here. That restriction is why the generator sits in `tools/` instead: `dials/`
is data, `tools/` is code.
