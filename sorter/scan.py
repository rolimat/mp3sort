import os
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
    selected: bool  # default: not proposal.flags
    bitrate: int | None = None  # kbps
    vbr: bool = False


class ScanError(Exception):
    """A folder the scan needs cannot be read; the message is shown to the user as is."""


def cannot_read(folder: Path, e: OSError) -> ScanError:
    if isinstance(e, PermissionError):
        return ScanError(f"cannot read {folder}: permission denied — allow access in "
                         "System Settings > Privacy & Security")
    return ScanError(f"cannot read {folder}: {e.strerror or e}")


def mp3_files(source: Path) -> tuple[list[Path], int]:
    """Sorted mp3 files under source and the number of sub-folders that could not be read.
    Raises ScanError when source itself cannot be read (rglob would silently return nothing)."""
    try:
        os.scandir(source).close()
    except OSError as e:
        raise cannot_read(source, e) from e
    errors: list[OSError] = []
    files = [Path(d, n) for d, _, names in os.walk(source, onerror=errors.append) for n in names
             if n.lower().endswith(".mp3") and not n.startswith(".") and Path(d, n).is_file()]
    return sorted(files), len(errors)


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
        prop.flags.append("tags unreadable")
    return prop


def _bitrate(p: Path) -> tuple[int | None, bool]:
    try:
        i = MP3(p).info
        return (i.bitrate // 1000 or None), i.bitrate_mode == BitrateMode.VBR
    except Exception:
        return None, False


def mark_collisions(items: list[Item], dest: Path) -> None:
    groups: dict[str, list[int]] = {}
    for n, it in enumerate(items, 1):
        if it.proposal.filename:
            groups.setdefault(name_key(it.proposal.filename), []).append(n)
    try:
        existing = {name_key(p.name) for p in dest.iterdir()} if dest.is_dir() else set()
    except OSError as e:
        raise cannot_read(dest, e) from e
    for key, nums in groups.items():
        for n in nums:
            flags = items[n - 1].proposal.flags
            if len(nums) > 1:
                flags.append("duplicate of " + ", ".join(str(m) for m in nums if m != n))
            if key in existing:
                flags.append("already exists in destination")
    for it in items:
        it.selected = not it.proposal.flags


def scan(source: Path, dest: Path, skipped: list[int] | None = None) -> list[Item]:
    """Raises ScanError for an unreadable source/destination; appends the count of skipped
    unreadable sub-folders to `skipped` when given."""
    files, bad = mp3_files(source)
    if skipped is not None:
        skipped.append(bad)
    items = [Item(p, _read(p), False, *_bitrate(p)) for p in files]
    mark_collisions(items, dest)
    return items
