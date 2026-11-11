import shutil
import unicodedata
from pathlib import Path

import mutagen
import pytest
from mutagen.easyid3 import EasyID3

from sorter.scan import name_key, scan

AUDIO = Path(__file__).parent / "fixtures" / "audio" / "a1.mp3"
needs_audio = pytest.mark.skipif(not AUDIO.exists(), reason="falta tests/fixtures/audio/a1.mp3")


def put(path: Path, name: str, artist=None, title=None) -> Path:
    """Copia la fixture a path/name y escribe tags inventados en la copia."""
    path.mkdir(parents=True, exist_ok=True)
    dst = path / name
    shutil.copy(AUDIO, dst)
    if artist:
        f = mutagen.File(dst, easy=True)
        if f.tags is None:
            f.add_tags()
        f["artist"], f["title"] = artist, title
        f.save()
    return dst


def fake(path: Path, name: str, data=b"garbage") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_bytes(data)
    return path / name


@needs_audio
def test_scan_finds_mp3_recursively(tmp_path):
    src = tmp_path / "src"
    put(src, "Lumen - Prisma - www.example.com.mp3", "Lumen", "Prisma")
    put(src / "a", "Lumen - Eco (Original Mix).mp3", "Lumen", "Eco (Original Mix)")
    put(src / "a" / "b", "Nova - Ruta 122.mp3")
    put(src / "c", "01-nova--cima-abc.mp3")
    fake(src, "x.flac")
    fake(src, "y.mp3.asd")
    fake(src, ".DS_Store")
    items = scan(src, tmp_path / "dest")
    assert len(items) == 4
    assert [i.src for i in items] == sorted(i.src for i in items)


@needs_audio
def test_ok_items_selected(tmp_path):
    src = tmp_path / "src"
    put(src, "Lumen - Prisma - www.example.com.mp3", "Lumen", "Prisma")
    (item,) = scan(src, tmp_path / "dest")
    assert item.selected is True
    assert item.proposal.filename == "Lumen - Prisma.mp3"


def test_scan_uppercase_ext_and_hidden(tmp_path):
    src = tmp_path / "src"
    fake(src, "Ana - Bruma.MP3")
    fake(src, "._Ana - Bruma.mp3")
    items = scan(src, tmp_path / "dest")
    assert [i.src.name for i in items] == ["Ana - Bruma.MP3"]


def test_scan_corrupt_mp3(tmp_path):
    src = tmp_path / "src"
    fake(src, "Foo - Bar.mp3")
    (item,) = scan(src, tmp_path / "dest")
    assert item.proposal.artist == "Foo"
    assert item.proposal.flags and item.selected is False


@needs_audio
def test_duplicates_flagged(tmp_path):
    src = tmp_path / "src"
    put(src / "x", "Lumen - Prisma.mp3", "Lumen", "Prisma")
    put(src / "y", "Lumen - Prisma.mp3", "Lumen", "Prisma")
    items = scan(src, tmp_path / "dest")
    assert len(items) == 2
    for n, i in enumerate(items):
        assert any(f == f"duplicado de {2 - n}" for f in i.proposal.flags)
        assert i.selected is False


def test_duplicate_unicode_case(tmp_path):
    src = tmp_path / "src"
    fake(src / "x", unicodedata.normalize("NFC", "SÖLÄR - X.mp3"))
    fake(src / "y", unicodedata.normalize("NFD", "sölär - x.mp3"))
    items = scan(src, tmp_path / "dest")
    assert len(items) == 2
    assert all(any(f.startswith("duplicado de ") for f in i.proposal.flags) for i in items)
    assert name_key("SÖLÄR") == name_key(unicodedata.normalize("NFD", "sölär"))


@needs_audio
def test_conflict_with_dest(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    dest.mkdir()
    (dest / "lumen - prisma.mp3").write_bytes(b"x")
    (item,) = scan(src, dest)
    assert "ya existe en destino" in item.proposal.flags
    assert item.selected is False


@needs_audio
def test_scan_bitrate(tmp_path):
    src = tmp_path / "src"
    put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    fake(src, "Nova - Ruta.mp3")
    good, bad = scan(src, tmp_path)
    assert isinstance(good.bitrate, int) and good.bitrate > 0
    assert isinstance(good.vbr, bool)
    assert bad.bitrate is None and bad.vbr is False


def test_scan_bitrate_zero_is_none(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sorter.scan
    src = tmp_path / "src"
    fake(src, "Nova - Ruta.mp3")
    monkeypatch.setattr(sorter.scan, "MP3", lambda p: SimpleNamespace(
        info=SimpleNamespace(bitrate=0, bitrate_mode=None)))
    assert scan(src, tmp_path)[0].bitrate is None
