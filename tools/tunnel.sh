#!/usr/bin/env bash
#
# Publish the G6 dial preview on a public https URL via a Cloudflare quick
# tunnel. No Cloudflare account, no domain, no config file: cloudflared hands
# back a random trycloudflare.com hostname that lives as long as the process.
#
# What gets published is deliberately narrow. tools/serve-preview.py is an
# allowlist server: it exposes preview/ and dials/ and 404s everything else,
# so the repo's .git, Fogg/ and ble-capture/ are not reachable even though the
# tunnel is public and the URL is guessable.
#
# Usage:
#   tools/tunnel.sh              # serve on 8000, print the public URL
#   tools/tunnel.sh 9000         # a different local port
#   tools/tunnel.sh 8000 --no-cloudflared    # just the local server
#
# The quick tunnel URL changes every run, so do not bookmark it.

set -euo pipefail

PORT="${1:-8000}"
shift || true

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

LOG="${TMPDIR:-/tmp}/g6-preview-tunnel.log"
: > "$LOG"

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

# Started as a child of this script, not as a detached subshell, so the trap
# above can actually reap it.
python3 tools/serve-preview.py --port "$PORT" >"$LOG" 2>&1 &
pids+=($!)

# Give the local server a moment so the tunnel does not announce a URL that
# 502s on the first request.
sleep 1
if ! kill -0 "${pids[0]}" 2>/dev/null; then
  echo "the local server failed to start:" >&2
  cat "$LOG" >&2
  exit 1
fi

echo "local:  http://127.0.0.1:$PORT/"

if [ "${1:-}" = "--no-cloudflared" ]; then
  echo
  echo "serving locally only. log: $LOG"
  wait "${pids[0]}"
  exit 0
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo
  echo "cloudflared is not installed. Install it with: brew install cloudflared" >&2
  echo "The local server is still running on http://127.0.0.1:$PORT/" >&2
  exit 1
fi

# --no-autoupdate because cloudflared reaching out to its own release channel
# mid-tunnel is a surprising way to lose a preview.
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >>"$LOG" 2>&1 &
pids+=($!)

URL=""
for _ in $(seq 1 60); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  if [ -n "$URL" ]; then
    break
  fi
  if ! kill -0 "${pids[1]}" 2>/dev/null; then
    echo "cloudflared exited:" >&2
    cat "$LOG" >&2
    exit 1
  fi
  sleep 1
done

if [ -z "$URL" ]; then
  echo "no tunnel URL after 60s. log: $LOG" >&2
  exit 1
fi

cat <<EOF

  public: $URL
  local:  http://127.0.0.1:$PORT/

  The public URL serves preview/ and dials/ only, and nothing else in the
  repository. It changes every run. Ctrl-C stops both processes.

EOF

tail -f "$LOG"
