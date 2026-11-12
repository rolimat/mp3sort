#!/usr/bin/env bash
# Usage: tools/build_app.sh X.Y.Z  -> dist/mp3sort.app and dist/mp3sort-X.Y.Z.dmg
set -euo pipefail
unset CDPATH

V="${1:-}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: $0 X.Y.Z" >&2; exit 2; }
HERE="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -P "$HERE/.." && pwd -P)"
# only ever delete build/ and dist/ of this repository
[ -f "$ROOT/mp3sort.spec" ] && [ -d "$ROOT/sorter" ] || { echo "not the mp3sort repo: $ROOT" >&2; exit 1; }
cd "$ROOT"

if [ -n "${PYTHON:-}" ]; then PY="$PYTHON"
elif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"
else PY=python3; fi
"$PY" -c "import PyInstaller" 2>/dev/null \
  || { echo "PyInstaller not found for $PY: run pip install -r requirements-build.txt" >&2; exit 1; }

# the app cannot run on an older macOS than the Python it bundles
PYLIB="$("$PY" -c 'import os, sys; p = os.path.join(sys.base_prefix, "Python"); print(p if os.path.isfile(p) else os.path.realpath(sys.executable))')"
MINOS="$(vtool -arch arm64 -show-build "$PYLIB" | awk '$1 == "minos" {print $2; exit}')"
[[ "$MINOS" =~ ^[0-9]+(\.[0-9]+)*$ ]] || { echo "cannot read the minimum macOS of $PYLIB" >&2; exit 1; }

APP="$ROOT/dist/mp3sort.app"
DMG="$ROOT/dist/mp3sort-$V.dmg"

rm -rf "$ROOT/build" "$ROOT/dist"
"$PY" tools/collect_licenses.py build/licenses "$V"
MP3SORT_VERSION="$V" MP3SORT_MINOS="$MINOS" "$PY" -m PyInstaller --noconfirm mp3sort.spec
"$PY" tools/collect_licenses.py --check-bundle "$APP"
cp build/licenses/SOURCE.txt dist/SOURCE.txt  # used for the release notes

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
(cd / && "$APP/Contents/MacOS/mp3sort" --self-check)

STAGE="$ROOT/build/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp -R build/licenses "$STAGE/licenses"
for try in 1 2 3; do  # hdiutil create fails now and then on CI runners ("Resource busy")
  hdiutil create -volname mp3sort -srcfolder "$STAGE" -format UDZO -ov "$DMG" && break
  [ "$try" = 3 ] && { echo "hdiutil create failed 3 times" >&2; exit 1; }
  sleep 5
done

MNT="$(mktemp -d)"
trap 'hdiutil detach "$MNT" -quiet || true' EXIT
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null
codesign --verify --deep --strict "$MNT/mp3sort.app"
GOT="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$MNT/mp3sort.app/Contents/Info.plist")"
[ "$GOT" = "$V" ] || { echo "dmg version $GOT != $V" >&2; exit 1; }
echo "$DMG"
