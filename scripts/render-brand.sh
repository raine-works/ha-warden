#!/usr/bin/env bash
# Renders custom_components/warden/brand/icon.png (256px) and icon@2x.png (512px) from
# assets/logo.svg with headless Chrome on a transparent background. CHROME overrides its path.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
chrome="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
for pair in "icon.png 256" "icon@2x.png 512"; do
  set -- $pair
  printf '<!doctype html><style>html,body{margin:0;background:transparent}svg{display:block;width:%spx;height:%spx}</style>%s' \
    "$2" "$2" "$(cat "$root/assets/logo.svg")" > "$work/page.html"
  "$chrome" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
    --window-size="$2,$2" --user-data-dir="$work/chrome" \
    --screenshot="$root/custom_components/warden/brand/$1" "file://$work/page.html" >/dev/null 2>&1
  echo "$1 (${2}px)"
done
