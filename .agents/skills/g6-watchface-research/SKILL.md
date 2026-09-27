---
name: g6-watchface-research
description: Use when investigating or creating watchfaces for G6/Trek 1 devices controlled by AuraFit, especially when ADB Wi-Fi, JieLi RCSP, SMA/SMABLE, Fogg, BIN extraction, or BLE transfer are involved.
---

# G6/Trek 1 watchface research

## Overview

Treat the watchface as a device-specific binary asset and preserve an original BIN as the template. Separate visual design, binary compilation, and BLE transfer so a failed experiment does not become a firmware incident.

## Known routing

- Pairing-mode scans can identify the G6 through JieLi RCSP/JL701N, but the official WatchManager may not expose every watchface operation.
- AuraFit uses the SMA/SMABLE path (`com.szabh.smable3`, `WatchFaceBuilder`) for this G6 family. Fogg's AM05/STF path is the relevant implementation to inspect.
- Use an original AM05 BIN from AuraFit as the layout template; do not invent a container format.

## Workflow

1. Record device state and keep AuraFit disconnected while another BLE sender is active.
2. Extract at least one original BIN and decode it before editing artwork.
3. Preserve block dimensions, order, metadata, and transparency. Validate by recompiling and decoding.
4. Fix RGB565 conversion explicitly by casting NumPy channel values to Python `int` before shifting.
5. Build the sender APK with the BIN under `app/src/main/assets/dials/`; verify the APK contents with `unzip -l`.
6. Transfer only the tested BIN. Never use OTA, firmware update, restore, or resource update actions during a watchface experiment.

## Validation gates

- Preview matches the intended design.
- All template blocks round-trip after compile/decode.
- RGB565 differences are quantization-level and alpha is exact.
- APK contains the expected BIN and its SHA-256 is recorded.
- A real G6 transfer is reported separately; a successful build is not evidence of device compatibility.

## References

- Project evidence and device-specific facts: `g6-cat-gauge-transfer/KNOWLEDGE.md`.
- Safe transfer procedure: `g6-cat-gauge-transfer/TRANSFER_STEPS.md`.
