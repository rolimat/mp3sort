import json
import os
from pathlib import Path

from mutagen import apev2
from mutagen.id3 import ID3

from sorter.apply import COPIED_NOT_DELETED, apply_item
from sorter.folders import check_folders
from sorter.rows import Row, row_from_item
from sorter.scan import name_key, scan

SETTINGS_PATH = Path.home() / "Library" / "Application Support" / "mp3sort" / "settings.json"


def load_settings(path: Path | None = None) -> tuple[Path | None, Path | None]:
    path = path or SETTINGS_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        s, t = d.get("source"), d.get("destination")
        return (Path(s) if isinstance(s, str) and s else None,
                Path(t) if isinstance(t, str) and t else None)
    except Exception:
        return None, None


def save_settings(source: Path | None, dest: Path | None, path: Path | None = None) -> None:
    path = path or SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"source": str(source) if source else None,
                               "destination": str(dest) if dest else None}), encoding="utf-8")
    os.replace(tmp, path)


def _old_values(tags, key: str) -> list[str]:
    return [str(t) for fr in (tags.getall(key) if tags else []) for t in fr.text]


class Model:
    def __init__(self, source: Path | None = None, dest: Path | None = None):
        self.source, self.dest = source, dest
        self.rows: list[Row] = []
        self.busy = False
        self._existing: set[str] = set()  # name_keys present in dest at scan time
        self._scanned: tuple | None = None  # (source, dest) the rows were scanned from
        self._g: dict[str, list[int]] | None = None  # cached _groups(), reset on scan/edit/reset

    def set_folder(self, kind: str, path: Path) -> None:
        if kind == "source":
            self.source = path
        else:
            self.dest = path
        self.rows, self._existing, self._scanned, self._g = [], set(), None, None  # scan required again

    def can_scan(self) -> bool:
        return bool(self.source and self.dest and not self.busy)

    def scan(self) -> str | None:
        if self.busy:
            return "busy"
        self.rows, self._existing, self._scanned, self._g = [], set(), None, None
        err = check_folders(self.source, self.dest)
        if err is None:
            self.rows = [row_from_item(it) for it in scan(self.source, self.dest)]
            self._existing = {name_key(p.name) for p in self.dest.iterdir()}
            self._scanned = (self.source, self.dest)
        return err

    def edit(self, i: int, field: str, value: str) -> str | None:
        if self.busy:
            return "busy"
        self._g = None
        return self.rows[i].edit(field, value)

    def toggle(self, i: int) -> str | None:
        if self.busy:
            return "busy"
        r = self.rows[i]
        if not r.selected and r.filename() is None:
            return "cannot include (no proposed name)"
        r.selected = not r.selected
        return None

    def reset(self, i: int) -> str | None:
        if self.busy:
            return "busy"
        self._g = None
        self.rows[i].reset()

    def _groups(self) -> dict[str, list[int]]:
        if self._g is None:
            self._g = {}
            for n, r in enumerate(self.rows, 1):
                if (fn := r.filename()):
                    self._g.setdefault(name_key(fn), []).append(n)
        return self._g

    def flags(self, i: int) -> list[str]:
        r = self.rows[i]
        extra = []
        if fn := r.filename():
            key = name_key(fn)
            others = [str(n) for n in self._groups()[key] if n != i + 1]
            if others:
                extra.append("duplicate of " + ", ".join(others))
            if key in self._existing:
                extra.append("already exists in destination")
        fl = r.flags(extra)
        return fl if r.filename() or "no artist or title" in fl else fl + ["no artist or title"]

    def low_kbps(self, i: int) -> bool:
        r = self.rows[i]
        if r.kbps is None or not (fn := r.filename()):
            return False
        group = [self.rows[n - 1].kbps or 0 for n in self._groups()[name_key(fn)]]
        return len(group) > 1 and r.kbps < max(group)

    def edited_count(self) -> int:
        return sum(r.edited() for r in self.rows)

    def counts(self) -> dict:
        warn = sum(1 for i in range(len(self.rows)) if self.flags(i))
        return {"tracks": len(self.rows), "ok": len(self.rows) - warn, "warn": warn,
                "edited": self.edited_count(), "selected": sum(r.selected for r in self.rows)}

    def strip(self, i: int) -> dict:
        r = self.rows[i]
        try:
            tags = ID3(r.item.src)
        except Exception:
            tags = None
        removed = []
        try:
            apev2.APEv2(r.item.src)
            removed.append("APE tag")
        except Exception:
            pass
        for label, key in (("Album", "TALB"), ("Genre", "TCON"), ("Comment", "COMM")):
            removed += [f"{label}: {v}" for v in _old_values(tags, key)]
        return {"filename": r.filename(), "album": r.values["album"], "label": r.values["label"],
                "comment": r.values["comment"], "from": r.item.src.name, "removed": removed}

    def move(self, progress=lambda i, n: None) -> list[tuple[Row, str | None]] | str:
        err = check_folders(self.source, self.dest)  # folders may have changed since the scan
        if err:
            return err
        if self._scanned != (self.source, self.dest):
            return "folders changed since scan, scan again"
        # true snapshot: later edits cannot change what is written
        sel = [(r, r.filename(), {f: v for f, v in r.values.items() if v != r.suggested[f]})
               for r in self.rows if r.selected]
        out = []
        self.busy = True
        try:
            for i, (r, fn, tags) in enumerate(sel, 1):
                progress(i, len(sel))
                if fn is None:
                    out.append((r, "no proposed name"))
                    continue
                try:
                    err = apply_item(r.item, self.dest, tags, fn)
                except Exception as e:
                    err = str(e) or type(e).__name__
                out.append((r, err))
        finally:
            self.busy = False
        return out

    def summary(self, results) -> str:
        moved = sum(1 for _, e in results if e is None)
        kept = sum(1 for _, e in results if e and e.startswith(COPIED_NOT_DELETED))
        left = len(self.rows) - moved - kept
        extra = f" · Copied without deleting original: {kept}" if kept else ""
        return f"Moved: {moved} · Left in source: {left}{extra}"
