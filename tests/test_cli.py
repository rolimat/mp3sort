import shutil
from pathlib import Path

import pytest
from mutagen.easyid3 import EasyID3

from sorter.cli import main, parse_selection, render
from sorter.clean import Proposal
from sorter.scan import Item

AUDIO = Path(__file__).parent / "fixtures" / "audio" / "a1.mp3"
needs_audio = pytest.mark.skipif(not AUDIO.exists(), reason="falta tests/fixtures/audio/a1.mp3")


def put(src: Path, name: str, artist: str, title: str) -> Path:
    f = src / name
    shutil.copy(AUDIO, f)
    t = EasyID3(f)
    t["artist"], t["title"] = artist, title
    t.save()
    return f


def folders(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    return src, dest


def feed(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_render():
    long = "L" * 60 + ".mp3"
    items = [
        Item(Path("/x/a.mp3"), Proposal("Lumen", "Prisma", []), True),
        Item(Path("/x/" + long), Proposal("Lumen", "Eco", ["ya existe en destino"]), False),
    ]
    out = render(items)
    lines = out.splitlines()
    assert lines[0].startswith("✓") and "1" in lines[0] and "a.mp3" in lines[0]
    assert "→ Lumen - Prisma.mp3" in lines[0]
    assert lines[1].startswith(" ") and "⚠ [ya existe en destino]" in lines[1]
    assert "L" * 49 + "…" in lines[1] and "L" * 50 not in lines[1]
    assert lines[-1] == "1 ok · 1 ⚠"


def test_parse_selection():
    assert parse_selection("3,5", 5) == [2, 4]
    assert parse_selection("3 5", 5) == [2, 4]
    assert parse_selection("3, 5", 5) == [2, 4]
    for bad in ("9", "0", "abc"):
        with pytest.raises(ValueError):
            parse_selection(bad, 5)


def test_main_dest_missing():
    def boom(*a):
        raise AssertionError("no debe pedir input")
    assert main(["/nonexistent"], input_fn=boom) == 2


def test_main_default_source_blocked(tmp_path):
    assert main([str(tmp_path)], input_fn=feed()) == 2


@needs_audio
def test_main_quit_and_eof(tmp_path):
    src, dest = folders(tmp_path)
    f = put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    assert main([str(dest), "--source", str(src)], input_fn=feed("q")) == 0
    assert f.exists() and not list(dest.iterdir())

    def eof(prompt=""):
        raise EOFError
    assert main([str(dest), "--source", str(src)], input_fn=eof) == 0
    assert f.exists() and not list(dest.iterdir())


@needs_audio
def test_main_toggle_and_apply(tmp_path, capsys):
    src, dest = folders(tmp_path)
    one = put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    two = put(src, "Nube - Eco.mp3", "Nube", "Eco")
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "")) == 0
    assert one.exists() and not two.exists()
    assert [p.name for p in dest.iterdir()] == ["Nube - Eco.mp3"]
    assert "Movidos: 1 · Quedan en origen: 1" in capsys.readouterr().out


@needs_audio
def test_main_bad_input_reprompts(tmp_path, capsys):
    src, dest = folders(tmp_path)
    put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    assert main([str(dest), "--source", str(src)], input_fn=feed("9", "q")) == 0
    assert "fuera de rango" in capsys.readouterr().out


def test_main_cannot_include_unnamed(tmp_path, capsys):
    src, dest = folders(tmp_path)
    (src / "zzz.mp3").write_bytes(b"garbage")
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "q")) == 0
    assert "no se puede incluir" in capsys.readouterr().out
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "")) == 0
    assert (src / "zzz.mp3").exists() and not list(dest.iterdir())


def test_main_empty_source(tmp_path, capsys):
    src, dest = folders(tmp_path)
    assert main([str(dest), "--source", str(src)], input_fn=feed()) == 0
    assert "No hay mp3 en el origen" in capsys.readouterr().out
