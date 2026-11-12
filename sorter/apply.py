import errno
import os
import shutil
import stat
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


# F_FULLFSYNC is not supported on every file system (SMB, some FUSE): only then plain fsync
_NO_FULLFSYNC = {errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP), errno.ENOTTY, errno.EINVAL}


def _fsync(path: Path) -> None:
    if os.name == "nt":  # Windows: fsync needs a handle opened for writing; directories cannot be opened
        with open(path, "r+b") as f:
            os.fsync(f.fileno())
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            import fcntl
            full = fcntl.F_FULLFSYNC  # macOS: os.fsync does not reach the platter
        except (ImportError, AttributeError):
            os.fsync(fd)
            return
        try:
            fcntl.fcntl(fd, full)
        except OSError as e:
            if e.errno not in _NO_FULLFSYNC:
                raise
            os.fsync(fd)
    finally:
        os.close(fd)


def _sync(target: Path) -> None:
    """Flush the copy (and on POSIX its directory entry) to disk before the original is deleted."""
    _fsync(target)
    if os.name != "nt":
        _fsync(target.parent)


def _remove_copy(target: Path, msg: str) -> str:
    """Delete our own copy; never raises. Returns msg, extended when the copy could not be removed."""
    try:
        target.unlink(missing_ok=True)
        return msg
    except OSError:
        pass
    try:
        os.chmod(target, stat.S_IMODE(os.stat(target).st_mode) | stat.S_IWUSR)
        target.unlink(missing_ok=True)
        return msg
    except OSError:
        return f"{msg} (copy left at {target}, original untouched)"


def _copy_metadata(src: Path, target: Path, mode: bool) -> None:
    """Best effort (FAT/exFAT refuse some of it): times, or the permission bits. No BSD flags."""
    try:
        st = src.stat()
        if mode:
            os.chmod(target, stat.S_IMODE(st.st_mode))
        else:
            os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    except OSError:
        pass


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
        r = open(item.src, "rb")
    except OSError as e:
        return f"copy failed, original untouched: {e}"
    with r:
        try:
            w = open(target, "xb")  # "x": never overwrites
        except FileExistsError:
            return "already exists in destination, not overwritten"
        except OSError as e:
            return f"copy failed, original untouched: {e}"
        try:  # from here the file is ours: any failure, including the final close, removes it
            with w:
                shutil.copyfileobj(r, w)
        except Exception as e:
            return _remove_copy(target, f"copy failed, original untouched: {e}")
        except BaseException:
            _remove_copy(target, "")
            raise
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
        return _remove_copy(target, f"error writing tags, original untouched: {e}")
    except BaseException:  # Ctrl-C: do not leave an unverified copy
        _remove_copy(target, "")
        raise
    _copy_metadata(item.src, target, mode=False)  # after tagging, which would reset the mtime
    try:
        _sync(target)
    except Exception as e:
        return _remove_copy(target, f"could not finish the copy on disk, original untouched: {e}")
    except BaseException:
        _remove_copy(target, "")
        raise
    _copy_metadata(item.src, target, mode=True)  # after the sync: Windows needs a writable handle
    try:
        item.src.unlink()
    except OSError as e:
        return f"{COPIED_NOT_DELETED}: {e}"
    return None
