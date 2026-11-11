#!/bin/sh
# Usage: tools/make_audio_fixtures.sh <source-folder>
# Truncated copy (3 MB) of the first 4 .mp3 files (alphabetical, recursive) into tests/fixtures/audio/a1..a4.mp3. Only reads the source.
set -eu
[ $# -eq 1 ] && [ -d "$1" ] || { echo "Usage: $0 <source-folder>" >&2; exit 1; }
out="$(dirname "$0")/../tests/fixtures/audio"
mkdir -p "$out"
i=0
find "$1" -type f -iname '*.mp3' ! -name '.*' | sort | head -4 | while IFS= read -r f; do
  i=$((i+1))
  head -c 3000000 "$f" > "$out/a$i.mp3"
done
