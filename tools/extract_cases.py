"""Extrae (dir, filename, artist, title) de los .mp3 de las carpetas dadas. Solo lectura."""
import json
import sys
from pathlib import Path

import mutagen

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "local" / "cases.json"


def tag(f, key):
    v = f.get(key) if f is not None else None
    return ", ".join(v) if v else None


def main(folders):
    cases = []
    for folder in folders:
        for p in sorted(Path(folder).rglob("*.mp3")):
            try:
                f = mutagen.File(p, easy=True)
            except Exception:
                f = None
            cases.append({"dir": p.parent.name, "filename": p.name,
                          "artist": tag(f, "artist"), "title": tag(f, "title")})
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(cases)} casos -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
