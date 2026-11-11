import json
import os
from pathlib import Path

from mutagen import apev2
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from sorter.apply import COPIED_NOT_DELETED, apply_item
from sorter.cli import DEFAULT_SOURCE
from sorter.folders import check_folders
from sorter.scan import Item, scan

SETTINGS_PATH = Path.home() / "Library" / "Application Support" / "mp3sort" / "settings.json"


def load_settings(path: Path = SETTINGS_PATH) -> tuple[Path | None, Path | None]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        s, t = d.get("source"), d.get("destination")
        return (Path(s) if isinstance(s, str) and s else None,
                Path(t) if isinstance(t, str) and t else None)
    except Exception:
        return DEFAULT_SOURCE, None


def save_settings(source: Path | None, dest: Path | None, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"source": str(source) if source else None,
                               "destination": str(dest) if dest else None}), encoding="utf-8")
    os.replace(tmp, path)


def _old(tags, key: str) -> str:
    v = [str(t) for fr in (tags.getall(key) if tags else []) for t in fr.text]
    return f"{', '.join(v)} → (empty)" if v else "(empty)"


class Model:
    def __init__(self, source: Path | None = None, dest: Path | None = None):
        self.source, self.dest = source, dest
        self.items: list[Item] = []
        self.busy = False

    def can_scan(self) -> bool:
        return bool(self.source and self.dest and not self.busy)

    def scan(self) -> str | None:
        err = check_folders(self.source, self.dest)
        if err is None:
            self.items = scan(self.source, self.dest)
        return err

    def toggle(self, i: int) -> str | None:
        it = self.items[i]
        if not it.selected and it.proposal.filename is None:
            return "cannot include (no proposed name)"
        it.selected = not it.selected
        return None

    def footer(self) -> str:
        warn = sum(1 for it in self.items if it.proposal.flags)
        sel = sum(1 for it in self.items if it.selected)
        return f"{len(self.items) - warn} ok · {warn} ⚠ · {sel} selected"

    def detail(self, i: int) -> list[tuple[str, str]]:
        it = self.items[i]
        p = it.proposal
        try:
            tags = ID3(it.src)
        except Exception:
            tags = None
        try:
            apev2.APEv2(it.src)
            ape = "present → removed"
        except Exception:
            ape = "none"
        try:
            secs = int(MP3(it.src).info.length)
            dur = f"{secs // 60}:{secs % 60:02d}"
        except Exception:
            dur = "?"
        rate = "? kbps" if it.bitrate is None else f"{it.bitrate} kbps" + (" VBR" if it.vbr else "")
        return [("Original file", it.src.name), ("Folder", str(it.src.parent)),
                ("Artist", p.artist or ""), ("Title", p.title or ""),
                ("Album", _old(tags, "TALB")), ("Genre", _old(tags, "TCON")),
                ("Comment", _old(tags, "COMM")), ("APE tag", ape),
                ("Quality", f"{rate} · {dur}"),
                ("Warning", "⚠ " + "; ".join(p.flags) if p.flags else "—")]

    def move(self, progress=lambda i, n: None) -> list[tuple[Item, str | None]]:
        sel = [it for it in self.items if it.selected]
        out = []
        self.busy = True
        try:
            for i, it in enumerate(sel, 1):
                progress(i, len(sel))
                try:
                    err = apply_item(it, self.dest)
                except Exception as e:
                    err = str(e) or type(e).__name__
                out.append((it, err))
        finally:
            self.busy = False
        return out

    def summary(self, results) -> str:
        moved = sum(1 for _, e in results if e is None)
        kept = sum(1 for _, e in results if e and e.startswith(COPIED_NOT_DELETED))
        left = len(self.items) - moved - kept
        extra = f" · Copied without deleting original: {kept}" if kept else ""
        return f"Moved: {moved} · Left in source: {left}{extra}"
