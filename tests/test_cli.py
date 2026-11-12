import shutil
from pathlib import Path

import pytest
from conftest import audio_path
from mutagen.easyid3 import EasyID3

from sorter.apply import COPIED_NOT_DELETED
from sorter.cli import main, parse_selection, render
from sorter.clean import Proposal
from sorter.scan import Item



def put(src: Path, name: str, artist: str, title: str) -> Path:
    f = src / name
    shutil.copy(audio_path(), f)
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
        Item(Path("/x/" + long), Proposal("Lumen", "Eco", ["already exists in destination"]), False),
    ]
    out = render(items)
    lines = out.splitlines()
    assert lines[0].startswith("  ✓") and "1" in lines[0] and "a.mp3" in lines[0]
    assert "→ Lumen - Prisma.mp3" in lines[0]
    assert lines[1].startswith("⚠   ") and lines[1].endswith("[already exists in destination]")
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


def test_main_quit_and_eof(tmp_path):
    src, dest = folders(tmp_path)
    f = put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    assert main([str(dest), "--source", str(src)], input_fn=feed("q")) == 0
    assert f.exists() and not list(dest.iterdir())

    def eof(prompt=""):
        raise EOFError
    assert main([str(dest), "--source", str(src)], input_fn=eof) == 0
    assert f.exists() and not list(dest.iterdir())


def test_main_toggle_and_apply(tmp_path, capsys):
    src, dest = folders(tmp_path)
    one = put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    two = put(src, "Nube - Eco.mp3", "Nube", "Eco")
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "")) == 0
    assert one.exists() and not two.exists()
    assert [p.name for p in dest.iterdir()] == ["Nube - Eco.mp3"]
    assert "Moved: 1 · Left in source: 1" in capsys.readouterr().out


def test_main_bad_input_reprompts(tmp_path, capsys):
    src, dest = folders(tmp_path)
    put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    assert main([str(dest), "--source", str(src)], input_fn=feed("9", "q")) == 0
    assert "' is out of range (1-" in capsys.readouterr().out


def test_main_cannot_include_unnamed(tmp_path, capsys):
    src, dest = folders(tmp_path)
    (src / "zzz.mp3").write_bytes(b"garbage")
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "q")) == 0
    assert "cannot include" in capsys.readouterr().out
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "")) == 0
    assert (src / "zzz.mp3").exists() and not list(dest.iterdir())


def test_main_empty_source(tmp_path, capsys):
    src, dest = folders(tmp_path)
    assert main([str(dest), "--source", str(src)], input_fn=feed()) == 0
    assert "No mp3 files in source" in capsys.readouterr().out


def test_main_dest_equals_source(tmp_path, capsys):
    src, _ = folders(tmp_path)
    assert main([str(src), "--source", str(src)], input_fn=feed()) == 2
    assert "the destination cannot be inside the source" in capsys.readouterr().out


def test_main_dest_inside_source_and_reverse(tmp_path):
    src, _ = folders(tmp_path)
    sub = src / "sub"
    sub.mkdir()
    assert main([str(sub), "--source", str(src)], input_fn=feed()) == 2
    assert main([str(src), "--source", str(sub)], input_fn=feed()) == 2


def test_parse_selection_superscript():
    with pytest.raises(ValueError, match="is not a number"):
        parse_selection("²", 5)


def test_main_summary_copied_without_delete(tmp_path, monkeypatch, capsys):
    import sorter.cli
    src, dest = folders(tmp_path)
    (src / "Lumen - Prisma.mp3").write_bytes(b"x")
    monkeypatch.setattr(sorter.cli, "apply_item",
                        lambda it, d: COPIED_NOT_DELETED + ": x")
    assert main([str(dest), "--source", str(src)], input_fn=feed("1", "")) == 0
    out = capsys.readouterr().out
    assert "Moved: 0 · Left in source: 0 · Copied without deleting original: 1" in out


def test_render_bitrate_column():
    dup = "duplicate of "
    items = [
        Item(Path("/x/a.mp3"), Proposal("Lumen", "Prisma", [dup + "2"]), False, 320),
        Item(Path("/x/b.mp3"), Proposal("Lumen", "Prisma", [dup + "1"]), False, 245, True),
        Item(Path("/x/c.mp3"), Proposal("Nube", "Eco", []), True),
        Item(Path("/x/d.mp3"), Proposal("Nube", "Eco2", ["already exists in destination"]), False),
    ]
    lines = render(items).splitlines()
    assert "Lumen - Prisma.mp3  320 kbps      [duplicate of 2]" in lines[0]
    assert "245 kbps VBR  [duplicate of 1]" in lines[1]
    assert lines[2].endswith("? kbps") and "[" not in lines[2]
    assert lines[0].index("[") == lines[1].index("[")  # reasons aligned


def test_main_prompt_on_own_line(tmp_path, capsys):
    src, dest = folders(tmp_path)
    put(src, "Lumen - Prisma.mp3", "Lumen", "Prisma")
    prompts = []
    main([str(dest), "--source", str(src)], input_fn=lambda p="": prompts.append(p) or "q")
    assert prompts == ["> "]
    assert "Enter = apply" in capsys.readouterr().out


def test_render_long_destination_capped():
    it = Item(Path("/x/a.mp3"), Proposal("L" * 80, "Eco", ["already exists in destination"]), False, 320)
    line = render([it]).splitlines()[0]
    assert "L" * 80 not in line and "… " in line
    assert line.endswith("320 kbps      [already exists in destination]")
    assert len(line) < 160
