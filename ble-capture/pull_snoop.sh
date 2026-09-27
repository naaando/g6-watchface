#!/usr/bin/env bash
# Pull the Bluetooth HCI snoop log off the Galaxy A54 over adb and stage it
# locally for parse_btsnoop.py. Passive: nothing is transmitted to the watch.
set -euo pipefail

OUT_DIR="${1:-./capture-$(date +%Y%m%d-%H%M%S)}"
ADB="${ADB:-adb}"
mkdir -p "$OUT_DIR"

if ! "$ADB" get-state >/dev/null 2>&1; then
  echo "no adb device. Enable Wireless debugging on the A54 and run:" >&2
  echo "  adb pair <ip>:<pair-port>   # then enter the 6-digit code" >&2
  echo "  adb connect <ip>:<port>" >&2
  exit 1
fi

echo "[device] $("$ADB" shell getprop ro.product.model | tr -d '\r') / Android $("$ADB" shell getprop ro.build.version.release | tr -d '\r')"

echo "[1/4] snoop log mode: $("$ADB" shell settings get global bluetooth_btsnoop_log_mode | tr -d '\r')"
echo "      (2 = verbose, on Developer options > Enable Bluetooth HCI snoop log)"

echo "[2/4] verifying the snoop logger actually started..."
# AOSP samples the snoop log mode once, when Bluetooth comes up. A `settings put`
# afterwards does nothing, so check the value the stack actually captured.
SET=$("$ADB" shell dumpsys bluetooth_manager 2>/dev/null | tr -d '\r' \
      | sed -n 's/^ *sSnoopLogSettingAtEnable *= *//p' | head -1)
case "$SET" in
  FULL|VERBOSE|CORRECTED|RAW) echo "      sSnoopLogSettingAtEnable = $SET (logging)" ;;
  *) echo "      WARNING: sSnoopLogSettingAtEnable = '${SET:-EMPTY}' - not logging." >&2
     echo "      Toggle Developer options > Enable Bluetooth HCI snoop log, or:" >&2
     echo "        adb shell settings put global bluetooth_btsnoop_log_mode 2" >&2
     echo "        adb shell svc bluetooth disable && adb shell svc bluetooth enable" >&2
     exit 2 ;;
esac

echo "[3/4] collecting bugreport (30-90s)..."
ZIP="$OUT_DIR/bugreport.zip"
# Host-side `adb bugreport <local.zip>` is the reliable form: on Android 16 the
# device-side `bugreport /sdcard/...` variant only prints a deprecation warning.
# No root, so this is the only way to read the log: the shell uid cannot open
# /data/log/bt/btsnoop_hci.log directly.
yes | "$ADB" bugreport "$ZIP" | tail -2

echo "[4/4] extracting btsnoop_hci.log..."
python3 - "$ZIP" "$OUT_DIR" <<'PY'
import sys, zipfile
zip_path, out_dir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path) as zf:
    names = [n for n in zf.namelist() if n.endswith("btsnoop_hci.log")]
    if not names:
        cands = [n for n in zf.namelist() if "bluetooth" in n.lower() or "btsnoop" in n.lower()]
        sys.exit(f"no btsnoop_hci.log in bugreport. candidates: {cands[:10]}")
    # Samsung ships the log at FS/data/log/bt/btsnoop_hci.log, AOSP at
    # FS/data/misc/bluetooth/logs/. Take the largest in case both are present.
    best = max(names, key=lambda n: zf.getinfo(n).file_size)
    data = zf.read(best)
    with open(f"{out_dir}/btsnoop_hci.log", "wb") as fh:
        fh.write(data)
    print(f"    {best} -> {out_dir}/btsnoop_hci.log ({len(data)} bytes)")
PY

echo
echo "Now run:"
echo "  python3 parse_btsnoop.py $OUT_DIR/btsnoop_hci.log -o $OUT_DIR/captured"
