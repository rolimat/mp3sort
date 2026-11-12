import hashlib
import shutil
from pathlib import Path

import pytest
from conftest import audio_path
from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.id3 import COMM, ID3, PRIV, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TPUB

from sorter.apply import apply_item
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
            assert v2_version in (3, 4)  # mutagen solo escribe v2.3/v2.4
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
    monkeypatch.setattr(ID3, "save", lambda *a, **k: None)  # tags no se escriben
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
