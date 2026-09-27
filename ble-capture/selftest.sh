#!/usr/bin/env bash
# Self-test: round-trip real dial BINs through the synthetic btsnoop generator
# and confirm the parser recovers each file byte for byte.
#
# Transport/link pairs exercised (only the real-world valid combinations plus
# the "handle unidentified" sniff fallback):
#   le    + att     BLE GATT write, identified by LE Connection Complete
#   bredr + rfcomm  classic SPP, identified by BR/EDR Connection Complete
#   ?     + att     no connection event: parser must sniff ATT
#   ?     + rfcomm  no connection event: parser must sniff RFCOMM
set -uo pipefail

cd "$(dirname "$0")"
T="${TMPDIR:-/tmp}/g6-selftest"
rm -rf "$T"
mkdir -p "$T"

BINS=(../trek-watchfaces/0.0_AM05_G6_11359.bin
      ../trek-watchfaces/0.0_AM05_G6_11448.bin
      ../trek-watchfaces/0.0_G6_captured_618808.bin)
# link:transport:extra-generator-flag
CASES=("le:att:" "bredr:rfcomm:" "le:att:--no-complete" "le:rfcomm:--no-complete"
       "le:att:--sma" "bredr:rfcomm:--sma")
fail=0

for bin in "${BINS[@]}"; do
  want=$(shasum -a 256 "$bin" | cut -d' ' -f1)
  name=$(basename "$bin" .bin)
  for case in "${CASES[@]}"; do
    IFS=':' read -r link tr extra <<<"$case"
    tag="$name-$link-$tr${extra:+${extra#--}}"
    gen=(python3 make_fake_snoop.py "$bin" "$T/$tag.log" --link "$link" --transport "$tr")
    [ -n "$extra" ] && gen+=("$extra")
    "${gen[@]}" >/dev/null || { echo "FAIL  $tag (generator)"; fail=1; continue; }

    # the sniff cases must be solved without help; identified cases are forced
    # so a wrong --link in the generator is caught instead of sniffed away
    pargs=(python3 parse_btsnoop.py "$T/$tag.log" -o "$T/out-$tag")
    if [ "$extra" != "--no-complete" ]; then pargs+=(--transport "$tr"); fi
    out=$("${pargs[@]}" 2>&1)
    got=$(shasum -a 256 "$T/out-$tag/"*.bin 2>/dev/null | cut -d' ' -f1 | head -1)
    if [ "$got" = "$want" ]; then
      echo "PASS  $tag  sha256 $got"
    else
      echo "FAIL  $tag  (got '${got:-none}')"
      echo "$out" | sed 's/^/      /'
      fail=1
    fi
  done
done

if [ "$fail" -eq 0 ]; then
  echo "all self-tests passed"
fi
exit $fail
