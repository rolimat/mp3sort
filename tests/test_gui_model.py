import shutil
from pathlib import Path

import pytest
from conftest import audio_path
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3, TALB, TDRC, TKEY

import sorter.gui_model as gm
from sorter.apply import COPIED_NOT_DELETED
from sorter.clean import Proposal
from sorter.gui_model import Model, load_settings, save_settings
from sorter.rows import row_from_item
from sorter.scan import Item, name_key


def item(tmp_path, name="a.mp3", flags=(), fn="A - B.mp3", sel=True):
    return Item(tmp_path / name, Proposal("A", "B", list(flags)) if fn else Proposal("", "", list(flags)), sel)


def test_settings(tmp_path):
    p = tmp_path / "x" / "settings.json"
    assert load_settings(p) == (None, None)
    p.parent.mkdir()
    p.write_text("{nope")
    assert load_settings(p) == (None, None)
    s, d = tmp_path / "gone1", tmp_path / "gone2"
    save_settings(s, d, p)
    assert load_settings(p) == (s, d)
    q = tmp_path / "new" / "deep" / "s.json"
    save_settings(None, None, q)
    assert load_settings(q) == (None, None)


def test_scan_error(tmp_path):
    m = Model(tmp_path / "gone", tmp_path)
    assert m.scan().startswith("Error: the source folder does not exist")


def rows(m, *its):
    m.rows = [row_from_item(i) for i in its]
    m._scanned = (m.source, m.dest)  # as if scanned


def test_toggle_counts(tmp_path):
    m = Model()
    rows(m, item(tmp_path), item(tmp_path, flags=["x"], sel=False), item(tmp_path, fn=None, sel=False))
    assert m.toggle(2) == "cannot include (no proposed name)"
    assert m.toggle(1) is None and m.rows[1].selected
    assert m.flags(2) == ["no artist or title"]
    assert m.counts() == {"tracks": 3, "ok": 0, "warn": 3,  # rows 1 and 2 share a name
                           "edited": 0, "selected": 2}
    assert m.toggle(0) is None and not m.rows[0].selected


def test_edit_flags_duplicates_and_reset(tmp_path):
    m = Model()
    rows(m, item(tmp_path, "a.mp3"), item(tmp_path, "b.mp3"), item(tmp_path, "c.mp3"))
    m.rows[1].kbps, m.rows[0].kbps = 128, 320
    m._existing = {name_key("A - B.mp3")}
    assert m.flags(0) == ["duplicate of 2, 3", "already exists in destination"]
    assert [m.low_kbps(i) for i in range(3)] == [False, True, False]  # unknown kbps never red
    assert m.edit(2, "title", "Other") is None and m.edit(1, "title", "Other 2") is None
    assert m.flags(0) == ["already exists in destination"]
    assert m.flags(2) == []
    assert not m.low_kbps(1) and m.edited_count() == 2
    assert m.edit(1, "bpm", "abc") is not None
    m.reset(2)
    assert m.edited_count() == 1 and m.flags(2)[0] == "duplicate of 1"
    m.edit(0, "artist", "")
    assert m.flags(0) == ["no artist or title"]


def test_strip(tmp_path):
    f = tmp_path / "Lumen - Prisma.mp3"
    shutil.copy(audio_path(), f)
    t = ID3(f)
    t.add(TALB(encoding=3, text="Record"))
    t.save(f)
    a = APEv2()
    a["Comment"] = "www.example.com"
    a.save(f)
    m = Model()
    rows(m, Item(f, Proposal("Lumen", "Prisma", []), True))
    st = m.strip(0)
    assert st["from"] == f.name and st["filename"] == "Lumen - Prisma.mp3"
    assert st["removed"][:2] == ["APE tag", "Album: Record"]


def test_move_writes_only_edited_tags(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    f = s / "x.mp3"
    shutil.copy(audio_path(), f)
    t = ID3(f)
    t.add(TDRC(encoding=3, text="2019-05-06 10:00:00"))
    t.add(TKEY(encoding=3, text="Am"))
    t.add(TALB(encoding=3, text="Record"))
    t.save(f)
    m = Model(s, d)
    rows(m, Item(f, Proposal("Lumen", "Prisma", []), True))
    m.edit(0, "bpm", "128,5")
    res = m.move()
    assert res[0][1] is None and not f.exists()
    out = ID3(d / "Lumen - Prisma.mp3")
    assert str(out["TDRC"].text[0]) == "2019" and str(out["TKEY"]) == "Am"
    assert str(out["TBPM"]) == "128.5" and "TALB" not in out


def test_move_and_summary(tmp_path, monkeypatch):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    its = [item(tmp_path, n + ".mp3") for n in "abc"] + [item(tmp_path, "d", sel=False)]
    rows(m, *its)
    m.edit(2, "title", "Edited")
    seen = {}

    def fake(it, dest, tags=None, filename=None):
        assert m.busy
        seen[it.src.name] = (tags, filename)
        if it.src.name == "a.mp3":
            raise RuntimeError("boom")
        return COPIED_NOT_DELETED + ": x" if it.src.name == "b.mp3" else None

    monkeypatch.setattr(gm, "apply_item", fake)
    calls = []
    res = m.move(lambda i, n: calls.append((i, n)))
    assert not m.busy and calls == [(1, 3), (2, 3), (3, 3)]
    assert [e for _, e in res][0] == "boom" and res[2][1] is None
    assert seen["a.mp3"] == ({}, "A - B.mp3") and seen["c.mp3"] == ({"title": "Edited"}, "A - Edited.mp3")
    assert m.summary(res) == "Moved: 1 · Left in source: 2 · Copied without deleting original: 1"
    assert "Copied" not in m.summary([(m.rows[0], None)])


def test_move_skips_row_without_name(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    rows(m, item(tmp_path))
    m.rows[0].values["artist"] = ""
    assert [e for _, e in m.move()] == ["no proposed name"]


def test_settings_default_path_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "SETTINGS_PATH", tmp_path / "t" / "s.json")
    a, b = tmp_path / "a", tmp_path / "b"
    save_settings(a, b)
    assert load_settings() == (a, b)
    assert (tmp_path / "t" / "s.json").exists()


def test_scan_error_clears_rows(tmp_path):
    m = Model(tmp_path / "gone", tmp_path)
    rows(m, item(tmp_path))
    assert m.scan() is not None and m.rows == []


def test_scan_records_existing(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    shutil.copy(audio_path(), s / "Lumen - Prisma.mp3")
    m = Model(s, d)
    m.scan()
    (d / m.rows[0].filename()).write_bytes(b"x")
    assert m.scan() is None and "already exists in destination" in m.flags(0)


@pytest.mark.parametrize("sub", [False, True])
def test_move_rechecks_folders(tmp_path, sub):
    s, d = tmp_path / "src", tmp_path / "dst"
    s.mkdir(); d.mkdir()
    f = s / "a.mp3"
    f.write_bytes(b"x")
    m = Model(s, d)
    rows(m, Item(f, Proposal("A", "B", []), True))
    m.dest = s / "inner" if sub else s
    m.dest.mkdir(exist_ok=True)
    assert m.move() == "Error: the destination cannot be inside the source (or vice versa)"
    assert f.read_bytes() == b"x" and not list((s / "inner").glob("*") if sub else [])


def test_counts_fast_on_many_rows(tmp_path):
    import time
    m = Model()
    rows(m, *[Item(tmp_path / f"{n}.mp3", Proposal(f"A{n}", "T", []), True) for n in range(2000)])
    m.rows[1].values["artist"] = m.rows[0].values["artist"]
    t = time.perf_counter()
    c = m.counts()
    assert time.perf_counter() - t < 0.5
    assert c["tracks"] == 2000 and c["warn"] == 2 and m.flags(0) == ["duplicate of 2"]


def test_busy_blocks_mutators(tmp_path):
    m = Model(tmp_path, tmp_path / "d")
    rows(m, item(tmp_path))
    m.busy = True
    assert m.edit(0, "title", "X") == "busy" and m.toggle(0) == "busy"
    assert m.reset(0) == "busy" and m.scan() == "busy"
    assert m.rows[0].values["title"] == "B" and m.rows[0].selected


def test_move_snapshot_ignores_edits_during_move(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    rows(m, item(tmp_path, "a.mp3"), item(tmp_path, "b.mp3"))
    m.rows[1].values["title"] = "Edited"
    seen = []
    import sorter.gui_model as g
    orig, g.apply_item = g.apply_item, lambda it, dest, tags=None, filename=None: seen.append((tags, filename))
    try:
        def progress(i, n):
            m.rows[1].values["title"] = "Changed"  # bypasses the busy guard on purpose
            m.rows[1].selected = False
        m.move(progress)
    finally:
        g.apply_item = orig
    assert seen[1] == ({"title": "Edited"}, "A - Edited.mp3")


def test_move_refused_when_folders_changed_since_scan(tmp_path):
    a, b, c = (tmp_path / n for n in "abc")
    for p in (a, b, c):
        p.mkdir()
    (a / "x.mp3").write_bytes(b"x")
    m = Model(a, b)
    m.scan()
    m.dest = c
    assert m.move() == "folders changed since scan, scan again"
    assert (a / "x.mp3").exists()


def test_edit_collisions(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    (d / "Z - Q.mp3").write_bytes(b"old")
    m = Model(s, d)
    m._existing = {name_key("Z - Q.mp3")}
    rows(m, item(tmp_path, "a.mp3"), item(tmp_path, "b.mp3"), item(tmp_path, "c.mp3"))
    m.edit(0, "artist", "N"); m.edit(1, "artist", "N")
    assert m.flags(0) == ["duplicate of 2"] and m.flags(1) == ["duplicate of 1"]
    m.edit(2, "artist", "Z"); m.edit(2, "title", "Q")
    assert m.flags(2) == ["already exists in destination"]


def test_move_same_final_name_second_refused(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    for n in "ab":
        shutil.copy(audio_path(), s / f"{n}.mp3")
    m = Model(s, d)
    rows(m, Item(s / "a.mp3", Proposal("A", "B", []), True), Item(s / "b.mp3", Proposal("C", "D", []), True))
    m.edit(1, "artist", "A"); m.edit(1, "title", "B")
    res = m.move()
    assert res[0][1] is None and res[1][1] == "already exists in destination, not overwritten"
    assert (s / "b.mp3").exists() and not (s / "a.mp3").exists()
    assert [p.name for p in d.iterdir()] == ["A - B.mp3"]


def test_after_move_keeps_unmoved_rows_and_edits(tmp_path, monkeypatch):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    its = [Item(tmp_path / f"{n}.mp3", Proposal("A", n.upper(), []), sel) for n, sel in
           (("a", True), ("b", True), ("c", False), ("d", True))]
    rows(m, *its)
    m.edit(2, "title", "Edited")  # unselected, edited
    m.edit(1, "album", "Kept")    # will fail
    def fake(it, dest, tags=None, filename=None):
        if it.src.name == "b.mp3":
            return "boom"
        (dest / filename).write_bytes(b"")
        return COPIED_NOT_DELETED + ": x" if it.src.name == "d.mp3" else None

    monkeypatch.setattr(gm, "apply_item", fake)
    res = m.move()
    m.after_move(res)
    assert [r.item.src.name for r in m.rows] == ["b.mp3", "c.mp3"]
    assert m.rows[0].values["album"] == "Kept" and m.rows[1].values["title"] == "Edited"
    assert m.edited_count() == 2 and not m.rows[1].selected
    m.edit(1, "title", "A")  # "A - A.mp3" was just moved
    assert "already exists in destination" in m.flags(1)


def _year_file(tmp_path, name, year):
    f = tmp_path / "s" / name
    f.parent.mkdir(exist_ok=True)
    shutil.copy(audio_path(), f)
    t = ID3(f)
    t.add(TDRC(encoding=3, text=year))
    t.save(f)
    return f


def test_move_writes_shortened_year_without_marking_edited(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    f = _year_file(tmp_path, "a.mp3", "2025-03-28")
    m = Model(tmp_path / "s", d)
    rows(m, Item(f, Proposal("Lumen", "Prisma", []), True))
    assert m.edited_count() == 0
    assert m.move()[0][1] is None
    assert str(ID3(d / "Lumen - Prisma.mp3")["TDRC"].text[0]) == "2025"


def test_move_year_typed_full_date_and_plain_year(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    a = _year_file(tmp_path, "a.mp3", "2025-03-28")
    b = _year_file(tmp_path, "b.mp3", "2024")
    m = Model(tmp_path / "s", d)
    rows(m, Item(a, Proposal("Lumen", "Prisma", []), True), Item(b, Proposal("Lumen", "Aura", []), True))
    m.edit(0, "year", "2025-03-28")
    assert m.move()[0][1] is None
    assert str(ID3(d / "Lumen - Prisma.mp3")["TDRC"].text[0]) == "2025-03-28"
    assert str(ID3(d / "Lumen - Aura.mp3")["TDRC"].text[0]) == "2024"


def test_after_move_survives_unreadable_destination(tmp_path, monkeypatch):
    s, d = tmp_path / "s", tmp_path / "d"
    s.mkdir(); d.mkdir()
    m = Model(s, d)
    rows(m, Item(tmp_path / "a.mp3", Proposal("A", "B", []), True))
    m._g, m._existing = {"x": [1]}, {"old"}
    real = Path.iterdir

    def boom(self):
        if self == d:
            raise OSError("denied")
        return real(self)

    monkeypatch.setattr(Path, "iterdir", boom)
    err = m.after_move([(m.rows[0], None)])
    assert "denied" in err and m._existing == {"old"} and m._g is None and m.rows == []
