import shutil
from pathlib import Path

import pytest
from conftest import audio_path
from mutagen.apev2 import APEv2
from mutagen.id3 import COMM, ID3, TALB

import sorter.gui_model as gm
from sorter.apply import COPIED_NOT_DELETED
from sorter.clean import Proposal
from sorter.gui_model import Model, load_settings, save_settings
from sorter.scan import Item



def item(tmp_path, name="a.mp3", flags=(), fn="A - B.mp3", sel=True):
    return Item(tmp_path / name, Proposal("A", "B", list(flags)) if fn else Proposal(None, None, list(flags)), sel)


def test_settings(tmp_path):
    p = tmp_path / "x" / "settings.json"
    assert load_settings(p) == (gm.DEFAULT_SOURCE, None)
    p.parent.mkdir()
    p.write_text("{nope")
    assert load_settings(p) == (gm.DEFAULT_SOURCE, None)
    s, d = tmp_path / "gone1", tmp_path / "gone2"
    save_settings(s, d, p)
    assert load_settings(p) == (s, d)
    q = tmp_path / "new" / "deep" / "s.json"
    save_settings(None, None, q)
    assert load_settings(q) == (None, None)


def test_can_scan_and_scan_error(tmp_path):
    m = Model()
    assert not m.can_scan()
    m.source, m.dest = tmp_path / "gone", tmp_path
    assert m.can_scan()
    m.busy = True
    assert not m.can_scan()
    m.busy = False
    assert m.scan().startswith("Error: the source folder does not exist")


def test_toggle_footer(tmp_path):
    m = Model()
    m.items = [item(tmp_path), item(tmp_path, flags=["x"], sel=False), item(tmp_path, fn=None, sel=False)]
    assert m.toggle(2) == "cannot include (no proposed name)"
    assert m.toggle(1) is None and m.items[1].selected
    assert m.footer() == "2 ok · 1 ⚠ · 2 selected"
    assert m.toggle(0) is None and not m.items[0].selected


def test_detail(tmp_path):
    f = tmp_path / "Lumen - Prisma.mp3"
    shutil.copy(audio_path(), f)
    t = ID3(f)
    t.add(TALB(encoding=3, text="Record"))
    t.add(COMM(encoding=3, lang="eng", desc="", text="promo text"))
    t.save(f)
    a = APEv2()
    a["Comment"] = "www.example.com"
    a.save(f)
    before = f.read_bytes()
    m = Model()
    m.items = [Item(f, Proposal("Lumen", "Prisma", ["w"]), False, 320, True)]
    d = dict(m.detail(0))
    assert list(d) == ["Original file", "Folder", "Artist", "Title", "Album", "Genre",
                       "Comment", "APE tag", "Quality", "Warning"]
    assert d["Album"] == "Record → (empty)" and d["Comment"] == "promo text → (empty)"
    assert d["Genre"] == "(empty)" and d["APE tag"] == "present → removed"
    assert d["Quality"].startswith("320 kbps VBR · ") and d["Warning"] == "⚠ w"
    assert f.read_bytes() == before


def test_detail_unreadable(tmp_path):
    f = tmp_path / "x.mp3"
    f.write_bytes(b"junk")
    m = Model()
    m.items = [Item(f, Proposal("A", "B", []), True)]
    d = dict(m.detail(0))
    assert d["APE tag"] == "none" and d["Quality"] == "? kbps · ?" and d["Warning"] == "—"


def test_move_and_summary(tmp_path, monkeypatch):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    its = [item(tmp_path, n + ".mp3") for n in "abc"] + [item(tmp_path, "d", sel=False)]
    m.items = its

    def fake(it, dest):
        assert m.busy
        if it.src.name == "a.mp3":
            raise RuntimeError("boom")
        return COPIED_NOT_DELETED + ": x" if it.src.name == "b.mp3" else None

    monkeypatch.setattr(gm, "apply_item", fake)
    calls = []
    res = m.move(lambda i, n: calls.append((i, n)))
    assert not m.busy and calls == [(1, 3), (2, 3), (3, 3)]
    assert [e for _, e in res][0] == "boom" and res[2][1] is None
    assert m.summary(res) == "Moved: 1 · Left in source: 2 · Copied without deleting original: 1"
    assert m.summary([(its[0], None)]).startswith("Moved: 1 · Left in source: 3")
    assert "Copied" not in m.summary([(its[0], None)])


def test_settings_default_path_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "SETTINGS_PATH", tmp_path / "t" / "s.json")
    a, b = tmp_path / "a", tmp_path / "b"
    save_settings(a, b)
    assert load_settings() == (a, b)
    assert (tmp_path / "t" / "s.json").exists()


def test_scan_error_clears_items(tmp_path):
    m = Model(tmp_path / "gone", tmp_path)
    m.items = [item(tmp_path)]
    assert m.scan() is not None and m.items == []


@pytest.mark.parametrize("sub", [False, True])
def test_move_rechecks_folders(tmp_path, sub):
    s, d = tmp_path / "src", tmp_path / "dst"
    s.mkdir(); d.mkdir()
    f = s / "a.mp3"
    f.write_bytes(b"x")
    m = Model(s, d)
    m.items = [Item(f, Proposal("A", "B", []), True)]
    m.dest = s / "inner" if sub else s
    m.dest.mkdir(exist_ok=True)
    assert m.move() == "Error: the destination cannot be inside the source (or vice versa)"
    assert f.read_bytes() == b"x" and not list((s / "inner").glob("*") if sub else [])
