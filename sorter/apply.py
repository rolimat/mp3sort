import os
import shutil
from pathlib import Path

from mutagen import apev2
from mutagen.id3 import COMM, ID3, ID3NoHeaderError, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TPUB
from mutagen.mp3 import MP3

from sorter.scan import Item, name_key


FIELDS = ("artist", "title", "album", "genre", "year", "key", "bpm", "label", "comment")
FRAME = {"artist": "TPE1", "title": "TIT2", "album": "TALB", "genre": "TCON", "year": "TDRC",
         "key": "TKEY", "bpm": "TBPM", "label": "TPUB", "comment": "COMM"}
_CLS = {"TPE1": TPE1, "TIT2": TIT2, "TALB": TALB, "TCON": TCON, "TDRC": TDRC,
        "TKEY": TKEY, "TBPM": TBPM, "TPUB": TPUB}

COPIED_NOT_DELETED = "copied and verified, but the original could not be deleted (both remain)"


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            import fcntl
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)  # macOS: os.fsync does not reach the platter
        except (ImportError, AttributeError, OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def _sync(target: Path) -> None:
    """Flush the copy and its directory entry to disk before the original is deleted."""
    _fsync(target)
    _fsync(target.parent)


def _wanted(item: Item, tags: dict[str, str]) -> dict[str, str]:
    """field -> value to write ("" = remove). Fields not in the result are left untouched."""
    want = {"artist": item.proposal.artist, "title": item.proposal.title,
            "album": "", "genre": "", "comment": ""}
    want.update(tags)
    return want


def apply_item(item: Item, dest: Path, tags: dict[str, str] | None = None,
               filename: str | None = None) -> str | None:
    """Move item.src into dest with cleaned tags. Returns None on success, else an error message.

    tags: optional exact values per field (see FIELDS); "" removes the frame, absent keys keep the
    default behaviour. filename overrides the proposed file name."""
    if not all(isinstance(v, str) for v in (tags or {}).values()):
        return "invalid tag value"
    bad = [k for k in tags or () if k not in FIELDS]
    if bad:
        return f"unknown tag field: {', '.join(bad)}"
    want = _wanted(item, tags or {})
    name = filename or item.proposal.filename
    if name is None:
        return "no proposed name"
    if Path(name).name != name or name in (".", "..") or "\0" in name:
        return "invalid file name"
    target = dest / name
    try:
        if any(name_key(p.name) == name_key(name) for p in dest.iterdir()):
            return "already exists in destination, not overwritten"
    except OSError as e:
        return f"cannot read destination: {e}"
    try:
        with open(item.src, "rb") as r, open(target, "xb") as w:  # "x": never overwrites
            try:
                shutil.copyfileobj(r, w)
            except BaseException:
                w.close()
                target.unlink(missing_ok=True)  # only after open "xb" succeeded: the copy is ours
                raise
    except FileExistsError:
        return "already exists in destination, not overwritten"
    except OSError as e:
        return f"copy failed: {e}"
    try:
        try:
            id3 = ID3(target)
            v2 = id3.version[1] if id3.version[1] in (3, 4) else 4  # v2.2 cannot be written
        except ID3NoHeaderError:
            id3, v2 = ID3(), 4
        for field, value in want.items():
            frame = FRAME[field]
            id3.delall(frame)
            if value == "":
                continue
            id3.add(COMM(encoding=3, lang="eng", desc="", text=value) if frame == "COMM"
                    else _CLS[frame](encoding=3, text=value))
        id3.save(target, v1=1, v2_version=v2)
        size0 = target.stat().st_size
        apev2.delete(target)  # APEv2 carries junk (sites, comments); PRIV/Traktor (ID3) is kept
        chk = ID3(target)
        for field, value in want.items():
            got = [[str(x) for x in f.text] for f in chk.getall(FRAME[field])]
            if got != ([[value]] if value else []):
                raise ValueError("written tags do not match")
        try:
            apev2.APEv2(target)
            raise ValueError("an APEv2 tag remains")
        except apev2.APENoHeaderError:
            pass
        info = MP3(target).info
        # without a Xing header mutagen estimates duration from total size: the removed APE shortens it
        extra = (size0 - target.stat().st_size) * 8 / info.bitrate if info.bitrate else 0
        if abs(info.length - MP3(item.src).info.length) > 0.1 + extra:
            raise ValueError("duration changed")
    except Exception as e:
        target.unlink(missing_ok=True)
        return f"error writing tags, original untouched: {e}"
    except BaseException:  # Ctrl-C: do not leave an unverified copy
        target.unlink(missing_ok=True)
        raise
    try:
        shutil.copystat(item.src, target)  # after tagging: keeps the source mtime/mode, even 0444
        _sync(target)
    except Exception as e:
        target.unlink(missing_ok=True)
        return f"could not finish the copy on disk, original untouched: {e}"
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    try:
        item.src.unlink()
    except OSError as e:
        return f"{COPIED_NOT_DELETED}: {e}"
    return None
