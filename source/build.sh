#!/usr/bin/env bash
# Rebuild the app from source/ and copy the result into the repository root (what GitHub Pages serves).
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm ci --omit=dev --no-audit --no-fund
out="$(mktemp -d)"
python3 build.py config.prod.js "$out/site"
cp -r "$out/site/." ..
rm -rf "$out"
echo "Built into the repository root. Commit and push to publish."
