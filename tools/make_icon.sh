#!/bin/bash
# Render assets/icon.svg into assets/mp3sort.icns (needs macOS iconutil + rsvg-convert).
set -euo pipefail
unset CDPATH
ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[ -f "$ROOT/assets/icon.svg" ] || { echo "not the mp3sort repo: $ROOT" >&2; exit 1; }
cd "$ROOT"

command -v iconutil >/dev/null || { echo "error: iconutil not found (macOS required)" >&2; exit 1; }
command -v rsvg-convert >/dev/null || { echo "error: rsvg-convert not found; install it with: brew install librsvg" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
set_dir="$work/mp3sort.iconset"
mkdir "$set_dir"

for s in 16 32 128 256 512; do
  rsvg-convert -w $s -h $s assets/icon.svg -o "$set_dir/icon_${s}x${s}.png"
  rsvg-convert -w $((s*2)) -h $((s*2)) assets/icon.svg -o "$set_dir/icon_${s}x${s}@2x.png"
done

iconutil -c icns "$set_dir" -o assets/mp3sort.icns
echo "wrote assets/mp3sort.icns"
