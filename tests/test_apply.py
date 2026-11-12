import hashlib
import shutil
from pathlib import Path

import pytest
from conftest import audio_path
from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.id3 import COMM, ID3, PRIV, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TPUB

from sorter.apply import FRAME, apply_item
from sorter.clean import Proposal
from sorter.scan import Item

KEEP = ("TKEY", "TBPM", "TDRC", "TPUB")


def setup(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    f = src / "Lumen - Prisma - www.example.com.mp3"
    shutil.copy(audio_path(), f)
    t = ID3(f)
    t.delall("TPE1")  # start from a complete invented tag set
    t.add(TPE1(encoding=3, text="Lumen x Other"))
    t.add(TIT2(encoding=3, text="Prisma (www.example.com)"))
    t.add(TALB(encoding=3, text="www.example.com"))
    t.add(TCON(encoding=3, text="Pop"))
    t.add(COMM(encoding=3, lang="eng", desc="", text="www.example.com"))
    t.add(TKEY(encoding=3, text="Am"))
    t.add(TBPM(encoding=3, text="128"))
    t.add(TDRC(encoding=3, text="2020"))
    t.add(TPUB(encoding=3, text="Label"))
    t.save(f, v2_version=3)
    return Item(f, Proposal("Lumen", "Prisma", []), True), dest


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_apply_moves_and_cleans(tmp_path):
    item, dest = setup(tmp_path)
    before = ID3(item.src)
    kept = {k: before[k].pprint() for k in before if k.split(":")[0] in KEEP + ("APIC",)}
    assert set(k[:4] for k in kept) >= set(KEEP)
    assert apply_item(item, dest) is None
    out = dest / "Lumen - Prisma.mp3"
    assert out.exists() and not item.src.exists()
    t = ID3(out)
    assert t["TPE1"].text == ["Lumen"] and t["TIT2"].text == ["Prisma"]
    assert not t.getall("TALB") and not t.getall("TCON") and not t.getall("COMM")
    assert {k: t[k].pprint() for k in t if k.split(":")[0] in KEEP + ("APIC",)} == kept


def test_apply_keeps_id3_version(tmp_path):
    item, dest = setup(tmp_path)
    v = ID3(item.src).version
    assert v == (2, 3, 0)
    assert apply_item(item, dest) is None
    assert ID3(dest / "Lumen - Prisma.mp3").version == v


def test_apply_never_overwrites(tmp_path):
    item, dest = setup(tmp_path)
    (dest / "Lumen - Prisma.mp3").write_bytes(b"keep")
    assert apply_item(item, dest)
    assert (dest / "Lumen - Prisma.mp3").read_bytes() == b"keep"
    assert item.src.exists()


def test_apply_never_overwrites_case_insensitive(tmp_path):
    item, dest = setup(tmp_path)
    (dest / "lumen - prisma.MP3").write_bytes(b"keep")
    assert apply_item(item, dest)
    assert item.src.exists() and len(list(dest.iterdir())) == 1


def test_apply_readonly_dest(tmp_path):
    item, dest = setup(tmp_path)
    h = sha(item.src)
    dest.chmod(0o500)
    try:
        assert apply_item(item, dest)
        assert sha(item.src) == h
        assert list(dest.iterdir()) == []
    finally:
        dest.chmod(0o700)


def test_apply_tag_failure_cleans_copy(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)
    h = sha(item.src)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ID3, "save", boom)
    assert apply_item(item, dest)
    assert list(dest.iterdir()) == [] and sha(item.src) == h


def test_apply_delete_original_fails_keeps_copy(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)

    def boom(self, *a, **k):
        raise PermissionError("no")

    monkeypatch.setattr(Path, "unlink", boom)
    msg = apply_item(item, dest)
    assert msg and "original" in msg
    assert (dest / "Lumen - Prisma.mp3").exists() and item.src.exists()


def test_apply_no_filename(tmp_path):
    item = Item(tmp_path / "x.mp3", Proposal("", "", []), False)
    assert apply_item(item, tmp_path)


def test_apply_id3v22_source(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)

    class V22(ID3):  # simula v2.2: mutagen no escribe v2.2
        version = property(lambda self: (2, 2, 0), lambda self, v: None)

        def save(self, f, v1=1, v2_version=4, **k):
            assert v2_version in (3, 4)  # mutagen only writes v2.3/v2.4
            super().save(f, v1=v1, v2_version=v2_version, **k)

    monkeypatch.setattr("sorter.apply.ID3", V22)
    assert apply_item(item, dest) is None
    assert ID3(dest / "Lumen - Prisma.mp3").version[1] in (3, 4)
    assert not item.src.exists()


def test_apply_interrupt_cleans_copy(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)
    h = sha(item.src)

    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(ID3, "save", boom)
    with pytest.raises(KeyboardInterrupt):
        apply_item(item, dest)
    assert list(dest.iterdir()) == [] and sha(item.src) == h


def test_apply_verification_mismatch(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)
    h = sha(item.src)
    monkeypatch.setattr(ID3, "save", lambda *a, **k: None)  # tags are not written
    assert apply_item(item, dest)
    assert list(dest.iterdir()) == [] and sha(item.src) == h


def test_apply_no_id3_header(tmp_path):
    item, dest = setup(tmp_path)
    ID3(item.src).delete(item.src)
    assert apply_item(item, dest) is None
    t = ID3(dest / "Lumen - Prisma.mp3")
    assert t["TPE1"].text == ["Lumen"] and t.version[1] == 4


def add_ape(f):
    a = APEv2()
    a["COMMENT"], a["ARTIST"], a["WWW"] = "www.example.com", "Lumen x Other", "www.example.com"
    a.save(f)


def test_apply_deletes_apev2_keeps_priv(tmp_path):
    item, dest = setup(tmp_path)
    t = ID3(item.src)
    t.add(PRIV(owner="TRAKTOR4", data=b"\x01\x02invented"))
    t.save(item.src, v2_version=3)
    add_ape(item.src)
    priv = sorted(p.data for p in ID3(item.src).getall("PRIV:TRAKTOR4"))
    assert apply_item(item, dest) is None
    out = dest / "Lumen - Prisma.mp3"
    with pytest.raises(APENoHeaderError):
        APEv2(out)
    t = ID3(out)
    assert sorted(p.data for p in t.getall("PRIV:TRAKTOR4")) == priv
    assert b"\x01\x02invented" in priv
    assert t["TPE1"].text == ["Lumen"] and t["TKEY"].text == ["Am"]


def test_apply_apev2_failure_keeps_original_ape(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)
    add_ape(item.src)
    h = sha(item.src)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ID3, "save", boom)
    assert apply_item(item, dest)
    assert list(dest.iterdir()) == [] and sha(item.src) == h
    assert APEv2(item.src)["WWW"] == "www.example.com"


def test_apply_verification_fails_if_ape_remains(tmp_path, monkeypatch):
    item, dest = setup(tmp_path)
    add_ape(item.src)
    h = sha(item.src)
    monkeypatch.setattr("sorter.apply.apev2.delete", lambda *a, **k: None)
    assert apply_item(item, dest)
    assert list(dest.iterdir()) == [] and sha(item.src) == h


def test_apply_big_ape_on_cbr_without_xing(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    f = src / "x.mp3"
    f.write_bytes((b"\xff\xfb\x90\x00" + b"\x00" * 413) * 600)  # CBR 128k without Xing
    t = ID3()
    t.add(TPE1(encoding=3, text="Old"))
    t.save(f, v1=0)
    a = APEv2()
    a["WWW"], a["BIG"] = "www.example.com", "x" * 5000
    a.save(f)
    item = Item(f, Proposal("Lumen", "Prisma", []), True)
    assert apply_item(item, dest) is None
    out = dest / "Lumen - Prisma.mp3"
    assert out.exists() and not f.exists() and b"APETAGEX" not in out.read_bytes()


ALL = {"artist": "A Name", "title": "T Name", "album": "Alb", "genre": "Ambient", "year": "2021-05",
       "key": "8A", "bpm": "126.5", "label": "Lbl", "comment": "hello"}


def test_apply_tags_override_all_fields(tmp_path):
    item, dest = setup(tmp_path)
    assert apply_item(item, dest, tags=ALL, filename="Custom Name.mp3") is None
    out = dest / "Custom Name.mp3"
    assert out.exists() and not item.src.exists()
    t = ID3(out)
    for field, frame in FRAME.items():
        got = t.getall(frame)[0].text
        assert [str(x) for x in got] == [ALL[field]], field
    assert t.getall("COMM")[0].lang == "eng" and t.getall("COMM")[0].desc == ""
    assert not t.getall("COMM:x")


def test_apply_tags_empty_removes_frame(tmp_path):
    item, dest = setup(tmp_path)
    assert apply_item(item, dest, tags={"bpm": "", "key": "", "artist": "Solo"}) is None
    t = ID3(dest / "Lumen - Prisma.mp3")
    assert not t.getall("TBPM") and not t.getall("TKEY")
    assert t["TPE1"].text == ["Solo"]


def test_apply_tags_untouched_fields_keep_source(tmp_path):
    item, dest = setup(tmp_path)
    assert apply_item(item, dest, tags={"album": "New Album"}) is None
    t = ID3(dest / "Lumen - Prisma.mp3")
    assert t["TALB"].text == ["New Album"] and not t.getall("TCON") and not t.getall("COMM")
    assert t["TKEY"].text == ["Am"] and t["TBPM"].text == ["128"] and t["TPUB"].text == ["Label"]
    assert str(t["TDRC"].text[0]) == "2020"
    assert t["TPE1"].text == ["Lumen"] and t["TIT2"].text == ["Prisma"]


def test_apply_filename_override_never_overwrites(tmp_path):
    item, dest = setup(tmp_path)
    (dest / "Other.MP3").write_bytes(b"keep")
    assert apply_item(item, dest, filename="other.mp3")
    assert (dest / "Other.MP3").read_bytes() == b"keep" and item.src.exists()


def test_apply_unknown_tag_key(tmp_path):
    item, dest = setup(tmp_path)
    before = sha(item.src)
    assert "bogus" in apply_item(item, dest, tags={"bogus": "x"})
    assert sha(item.src) == before and not list(dest.iterdir())


@pytest.mark.parametrize("bad", ["../x.mp3", "ABS", "a/b.mp3", "..", ".", "a\0b.mp3"])
def test_apply_rejects_unsafe_filename(tmp_path, bad):
    bad = str(tmp_path / "abs-x.mp3") if bad == "ABS" else bad
    item, dest = setup(tmp_path)
    before = sha(item.src)
    assert apply_item(item, dest, filename=bad) == "invalid file name"
    assert sha(item.src) == before and not list(dest.iterdir())
    assert not (tmp_path / "x.mp3").exists()


def test_apply_rejects_non_str_tag_value(tmp_path):
    item, dest = setup(tmp_path)
    assert apply_item(item, dest, tags={"bpm": 128}) == "invalid tag value"
    assert item.src.exists() and not list(dest.iterdir())


@pytest.mark.parametrize("year", ["2021", "2021-05", "2021-05-03"])
def test_apply_year_forms_v23(tmp_path, year):
    item, dest = setup(tmp_path)
    assert apply_item(item, dest, tags={"year": year}) is None
    assert str(ID3(dest / "Lumen - Prisma.mp3")["TDRC"].text[0]) == year


def test_apply_syncs_copy_before_deleting_original(tmp_path, monkeypatch):
    import sorter.apply as ap

    item, dest = setup(tmp_path)
    seen = []
    real = ap._sync
    monkeypatch.setattr(ap, "_sync", lambda p: (seen.append((p, item.src.exists())), real(p)))
    assert apply_item(item, dest) is None
    assert seen == [(dest / "Lumen - Prisma.mp3", True)]


def test_apply_sync_failure_keeps_original(tmp_path, monkeypatch):
    import sorter.apply as ap

    item, dest = setup(tmp_path)
    before = sha(item.src)

    def boom(p):
        raise OSError("disk gone")

    monkeypatch.setattr(ap, "_sync", boom)
    err = apply_item(item, dest)
    assert err and "original untouched" in err and "disk gone" in err
    assert sha(item.src) == before and not list(dest.iterdir())


def test_apply_readonly_source_keeps_mode_and_mtime(tmp_path):
    import os

    item, dest = setup(tmp_path)
    os.utime(item.src, (1_000_000_000, 1_000_000_000))
    item.src.chmod(0o444)
    st = item.src.stat()
    assert apply_item(item, dest) is None
    out = (dest / "Lumen - Prisma.mp3").stat()
    assert out.st_mtime == st.st_mtime and (out.st_mode & 0o777) == 0o444


def test_sync_on_windows_uses_writable_handle_and_skips_dir(tmp_path, monkeypatch):
    import sorter.apply as ap

    f = tmp_path / "x.mp3"
    f.write_bytes(b"data")
    synced = []
    monkeypatch.setattr(ap.os, "fsync", lambda fd: synced.append(fd))

    def no_os_open(*a, **k):
        raise AssertionError("POSIX path used")

    monkeypatch.setattr(ap.os, "open", no_os_open)
    monkeypatch.setattr(ap.os, "name", "nt")
    ap._sync(f)
    assert len(synced) == 1  # the file only, through a handle opened r+b


def test_fullfsync_fallback_only_for_unsupported(tmp_path, monkeypatch):
    import errno
    import fcntl
    import sorter.apply as ap

    f = tmp_path / "x"
    f.write_bytes(b"data")
    monkeypatch.setattr(fcntl, "F_FULLFSYNC", 51, raising=False)
    synced = []
    monkeypatch.setattr(ap.os, "fsync", lambda fd: synced.append(fd))
    for code in (errno.ENOTSUP, errno.ENOTTY, errno.EINVAL):
        def unsupported(fd, op, code=code):
            raise OSError(code, "nope")
        monkeypatch.setattr(fcntl, "fcntl", unsupported)
        ap._fsync(f)
    assert len(synced) == 3

    def io_error(fd, op):
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(fcntl, "fcntl", io_error)
    with pytest.raises(OSError):
        ap._fsync(f)


def test_fullfsync_error_keeps_original(tmp_path, monkeypatch):
    import errno
    import fcntl

    item, dest = setup(tmp_path)
    monkeypatch.setattr(fcntl, "F_FULLFSYNC", 51, raising=False)

    def io_error(fd, op):
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(fcntl, "fcntl", io_error)
    err = apply_item(item, dest)
    assert err and "original untouched" in err and item.src.exists() and not list(dest.iterdir())


def test_close_error_removes_partial_copy(tmp_path, monkeypatch):
    import builtins
    import errno
    import sorter.apply as ap

    item, dest = setup(tmp_path)
    before = sha(item.src)

    class Full:
        def __init__(self, f):
            self.f = f

        def write(self, b):
            return self.f.write(b[: len(b) // 2])  # the disk takes only part of it

        def close(self):
            self.f.close()
            raise OSError(errno.ENOSPC, "No space left on device")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def fake_open(p, mode="r", *a, **k):
        f = builtins.open(p, mode, *a, **k)
        return Full(f) if mode == "xb" else f

    monkeypatch.setattr(ap, "open", fake_open, raising=False)
    err = apply_item(item, dest)
    assert err.startswith("copy failed") and "original untouched" in err and "No space left" in err
    assert not list(dest.iterdir()) and sha(item.src) == before


def test_cleanup_failure_is_reported_not_raised(tmp_path, monkeypatch):
    import sorter.apply as ap

    item, dest = setup(tmp_path)
    real_unlink = Path.unlink

    def locked(self, missing_ok=False):
        if self.parent == dest:
            raise PermissionError(1, "Operation not permitted", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    def boom(p):
        p.chmod(0o444)  # a read-only copy (e.g. Windows read-only attribute)
        raise OSError("disk gone")

    monkeypatch.setattr(ap, "_sync", boom)
    monkeypatch.setattr(Path, "unlink", locked)
    err = apply_item(item, dest)
    left = dest / "Lumen - Prisma.mp3"
    assert f"copy left at {left}, original untouched" in err and "disk gone" in err
    assert item.src.exists() and left.exists()
    assert left.stat().st_mode & 0o200  # write protection cleared for the retry


def test_metadata_is_best_effort(tmp_path, monkeypatch):
    import os
    import sorter.apply as ap

    item, dest = setup(tmp_path)
    os.utime(item.src, (1_000_000_000, 1_000_000_000))

    def no_chmod(*a, **k):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(ap.os, "chmod", no_chmod)
    assert apply_item(item, dest) is None
    assert (dest / "Lumen - Prisma.mp3").stat().st_mtime == 1_000_000_000


def test_no_bsd_flags_copied():
    src = (Path(__file__).resolve().parent.parent / "sorter" / "apply.py").read_text()
    assert "copystat" not in src and "chflags" not in src
