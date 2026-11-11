#!/usr/bin/env bash
# Recrea sandbox/ dentro del repo y copia (solo lectura) las carpetas dadas a sandbox/complete/.
# Uso: tools/make_sandbox.sh <carpeta> [<carpeta>...]
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 <carpeta> [<carpeta>...]" >&2
  exit 1
fi
for f in "$@"; do
  if [ ! -d "$f" ]; then
    echo "Error: no existe la carpeta: $f" >&2
    exit 1
  fi
done

ROOT="${MP3SORT_SANDBOX_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="$(cd "$ROOT" && pwd -P)"
SANDBOX="$ROOT/sandbox"
case "$SANDBOX" in
  "$ROOT"/sandbox) ;;
  *) echo "Error: ruta de sandbox insegura: $SANDBOX" >&2; exit 1 ;;
esac
[ "${SANDBOX##*/}" = "sandbox" ] && [ "$SANDBOX" != "/sandbox" ] || { echo "Error: ruta de sandbox insegura" >&2; exit 1; }

cd "$ROOT"
rm -rf sandbox
mkdir -p sandbox/complete sandbox/dest
for f in "$@"; do
  cp -R "$f" sandbox/complete/
done

echo "Sandbox listo en $SANDBOX"
echo "Ejecuta: .venv/bin/python mp3sort.py --source sandbox/complete sandbox/dest"
