import unicodedata
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.mp3 import MP3, BitrateMode

from sorter.clean import Proposal, propose


@dataclass
class Item:
    src: Path
    proposal: Proposal
    selected: bool  # por defecto: not proposal.flags
    bitrate: int | None = None  # kbps
    vbr: bool = False


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _tag(f, key: str) -> str | None:
    v = f.get(key) if f is not None else None
    return ", ".join(v) if v else None


def _read(p: Path) -> Proposal:
    try:
        f = mutagen.File(p, easy=True)
        artist, title, err = _tag(f, "artist"), _tag(f, "title"), False
    except Exception:
        artist = title = None
        err = True
    prop = propose(p.name, artist, title)
    if err:
        prop.flags.append("no se pueden leer los tags")
    return prop


def _bitrate(p: Path) -> tuple[int | None, bool]:
    try:
        i = MP3(p).info
        return i.bitrate // 1000, i.bitrate_mode == BitrateMode.VBR
    except Exception:
        return None, False


def mark_collisions(items: list[Item], dest: Path) -> None:
    groups: dict[str, list[int]] = {}
    for n, it in enumerate(items, 1):
        if it.proposal.filename:
            groups.setdefault(name_key(it.proposal.filename), []).append(n)
    existing = {name_key(p.name) for p in dest.iterdir()} if dest.is_dir() else set()
    for key, nums in groups.items():
        for n in nums:
            flags = items[n - 1].proposal.flags
            if len(nums) > 1:
                flags.append("duplicado de " + ", ".join(str(m) for m in nums if m != n))
            if key in existing:
                flags.append("ya existe en destino")
    for it in items:
        it.selected = not it.proposal.flags


def scan(source: Path, dest: Path) -> list[Item]:
    files = sorted(p for p in source.rglob("*")
                   if p.is_file() and p.suffix.lower() == ".mp3" and not p.name.startswith("."))
    items = [Item(p, _read(p), False, *_bitrate(p)) for p in files]
    mark_collisions(items, dest)
    return items
