import shutil
from pathlib import Path

from mutagen import apev2
from mutagen.id3 import ID3, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp3 import MP3

from sorter.scan import Item, name_key


COPIED_NOT_DELETED = "copied and verified, but the original could not be deleted (both remain)"


def apply_item(item: Item, dest: Path) -> str | None:
    """Move item.src into dest with cleaned tags. Returns None on success, else an error message."""
    name = item.proposal.filename
    if name is None:
        return "no proposed name"
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
        shutil.copystat(item.src, target)
        try:
            tags = ID3(target)
            v2 = tags.version[1] if tags.version[1] in (3, 4) else 4  # v2.2 cannot be written
        except ID3NoHeaderError:
            tags, v2 = ID3(), 4
        tags.setall("TPE1", [TPE1(encoding=3, text=item.proposal.artist)])
        tags.setall("TIT2", [TIT2(encoding=3, text=item.proposal.title)])
        for k in ("TALB", "TCON", "COMM"):
            tags.delall(k)
        tags.save(target, v1=1, v2_version=v2)
        size0 = target.stat().st_size
        apev2.delete(target)  # APEv2 carries junk (sites, comments); PRIV/Traktor (ID3) is kept
        chk = ID3(target)
        if chk["TPE1"].text != [item.proposal.artist] or chk["TIT2"].text != [item.proposal.title]:
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
        item.src.unlink()
    except OSError as e:
        return f"{COPIED_NOT_DELETED}: {e}"
    return None
