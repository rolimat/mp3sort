import errno
import os
import sys
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
        hint = ""
        if sys.platform == "darwin" and e.errno == errno.EPERM:  # macOS privacy (TCC) denial
            hint = " — allow access in System Settings > Privacy & Security"
        return ScanError(f"cannot read {folder}: permission denied{hint}")
    return ScanError(f"cannot read {folder}: {e.strerror or e}")


def _entries(d) -> list:
    """Directory entries; needs list AND search permission (a 0644 folder lists names but cannot be read)."""
    if not os.access(d, os.R_OK | os.X_OK):
        raise PermissionError(errno.EACCES, "Permission denied", str(d))
    with os.scandir(d) as it:
        return list(it)


def mp3_files(source: Path) -> tuple[list[Path], int]:
    """Sorted mp3 files under source and the number of sub-folders that could not be read.
    Hidden files and folders (.Trashes, .Spotlight-V100, ...) are ignored.
    Raises ScanError when source itself cannot be read (rglob would silently return nothing)."""
    try:
        todo = [_entries(source)]
    except OSError as e:
        raise cannot_read(source, e) from e
    files, skipped = [], 0
    while todo:
        for e in todo.pop():
            if e.name.startswith("."):
                continue
            if e.is_dir(follow_symlinks=False):
                try:
                    todo.append(_entries(e.path))
                except OSError:
                    skipped += 1
            elif e.name.lower().endswith(".mp3") and e.is_file():
                files.append(Path(e.path))
    return sorted(files), skipped


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
