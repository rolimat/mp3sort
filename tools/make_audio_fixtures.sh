#!/bin/sh
# Uso: tools/make_audio_fixtures.sh <carpeta-origen>
# Copia truncada (3 MB) de los 4 primeros .mp3 (orden alfabético, recursivo) a tests/fixtures/audio/a1..a4.mp3. Solo lee el origen.
set -eu
[ $# -eq 1 ] && [ -d "$1" ] || { echo "uso: $0 <carpeta-origen>" >&2; exit 1; }
out="$(dirname "$0")/../tests/fixtures/audio"
mkdir -p "$out"
i=0
find "$1" -type f -iname '*.mp3' ! -name '.*' | sort | head -4 | while IFS= read -r f; do
  i=$((i+1))
  head -c 3000000 "$f" > "$out/a$i.mp3"
done
