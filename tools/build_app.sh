#!/usr/bin/env bash
# Usage: tools/build_app.sh X.Y.Z  -> dist/mp3sort.app and dist/mp3sort-X.Y.Z.dmg
set -euo pipefail

V="${1:-}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: $0 X.Y.Z" >&2; exit 2; }
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
PY="${PYTHON:-python3}"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"
APP="$ROOT/dist/mp3sort.app"
DMG="$ROOT/dist/mp3sort-$V.dmg"

rm -rf build dist
"$PY" tools/collect_licenses.py build/licenses
MP3SORT_VERSION="$V" "$PY" -m PyInstaller --noconfirm mp3sort.spec

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
(cd / && "$APP/Contents/MacOS/mp3sort" --self-check)

STAGE="$ROOT/build/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp -R build/licenses "$STAGE/licenses"
hdiutil create -volname mp3sort -srcfolder "$STAGE" -format UDZO -ov "$DMG"

MNT="$(mktemp -d)"
trap 'hdiutil detach "$MNT" -quiet || true' EXIT
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null
codesign --verify --deep --strict "$MNT/mp3sort.app"
GOT="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$MNT/mp3sort.app/Contents/Info.plist")"
[ "$GOT" = "$V" ] || { echo "dmg version $GOT != $V" >&2; exit 1; }
echo "$DMG"
