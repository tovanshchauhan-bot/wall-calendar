#!/usr/bin/env bash
# Build a local copy wired to emulators and run the end-to-end check (test_app.py).
# Needs: Node, Python 3 with Pillow and Playwright (Chromium).
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules/firebase-tools ] || npm ci --no-audit --no-fund
work="$(mktemp -d)"
python3 build.py config.test.js "$work/site"
npx firebase emulators:start --only auth --project demo-wallcal > "$work/auth-emulator.log" 2>&1 &
python3 -m http.server 8765 --bind 127.0.0.1 --directory "$work/site" > /dev/null 2>&1 &
WEB=$!
trap 'kill $WEB 2>/dev/null || true; pkill -f "[e]mulators:start --only auth" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do grep -q "All emulators ready" "$work/auth-emulator.log" && break; sleep 1; done
python3 test_app.py "http://127.0.0.1:8765/"
