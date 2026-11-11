#!/usr/bin/env bash
# Recrea sandbox/ dentro del repo y copia (solo lectura) las carpetas dadas a sandbox/complete/.
# Uso: tools/make_sandbox.sh <carpeta> [<carpeta>...]
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 <carpeta> [<carpeta>...]" >&2
  exit 1
fi
ROOT="${MP3SORT_SANDBOX_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="$(cd "$ROOT" && pwd -P)"
if [ "$ROOT" = "/" ] || [ "$ROOT" = "$(cd "$HOME" && pwd -P)" ]; then
  echo "Error: raiz insegura: $ROOT" >&2
  exit 1
fi
SANDBOX="$ROOT/sandbox"

# Resolver todos los argumentos a rutas absolutas antes de cualquier cd/rm.
SRCS=()
for f in "$@"; do
  if [ ! -d "$f" ]; then
    echo "Error: no existe la carpeta: $f" >&2
    exit 1
  fi
  abs="$(cd "$f" && pwd -P)"
  if [[ "$abs/" == "$SANDBOX/"* || "$SANDBOX/" == "$abs/"* ]]; then
    echo "Error: la carpeta esta dentro de sandbox o lo contiene: $f" >&2
    exit 1
  fi
  SRCS+=("$abs")
done

if [ -e "$SANDBOX" ]; then
  if [ ! -f "$SANDBOX/.mp3sort-sandbox" ]; then
    echo "Error: $SANDBOX existe y no tiene marcador .mp3sort-sandbox; no se borra" >&2
    exit 1
  fi
  rm -rf "$SANDBOX"
fi
mkdir -p "$SANDBOX/complete" "$SANDBOX/dest"
touch "$SANDBOX/.mp3sort-sandbox"
cd "$ROOT"
for f in "${SRCS[@]}"; do
  cp -R -- "$f" sandbox/complete/
done

echo "Sandbox listo en $SANDBOX"
echo "Ejecuta: .venv/bin/python mp3sort.py --source sandbox/complete sandbox/dest"
