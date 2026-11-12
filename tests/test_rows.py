import pytest
from mutagen.id3 import ID3, TBPM, TDRC, TKEY, TPUB

from sorter.clean import Proposal
from sorter.rows import row_from_item
from sorter.scan import Item


def mk(tmp_path, audio, artist="Lumen", title="Prisma", flags=(), tags=None):
    p = tmp_path / "a.mp3"
    p.write_bytes(audio.read_bytes())
    if tags:
        t = ID3(p)
        for f in tags:
            t.add(f)
        t.save(p)
    return row_from_item(Item(p, Proposal(artist, title, list(flags)), not flags, 320, False))


def test_suggested_and_file_tags(tmp_path, audio):
    r = mk(tmp_path, audio, tags=[TDRC(encoding=3, text="2020"), TKEY(encoding=3, text="8A"),
                                  TBPM(encoding=3, text="128"), TPUB(encoding=3, text="Example")])
    assert r.suggested == {"artist": "Lumen", "title": "Prisma", "album": "", "genre": "", "year": "2020",
                           "key": "8A", "bpm": "128", "label": "Example", "comment": ""}
    assert (r.kbps, r.vbr, r.selected, r.edited()) == (320, False, True, False)
    assert mk(tmp_path, audio).values["year"] == ""


def test_edit_reset_edited(tmp_path, audio):
    r = mk(tmp_path, audio)
    assert r.edit("album", "  Foo ") is None and r.values["album"] == "Foo" and r.edited()
    r.edit("album", "")
    assert not r.edited()
    r.edit("title", "X")
    r.reset()
    assert r.values == r.suggested


@pytest.mark.parametrize("a,t,name", [("../x", "T", "..-x - T.mp3"), ("a/b", "c:d", "a-b - c-d.mp3")])
def test_filename_plain(tmp_path, audio, a, t, name):
    r = mk(tmp_path, audio)
    r.edit("artist", a); r.edit("title", t)
    assert r.filename() == name


def test_clearing_unchecks(tmp_path, audio):
    r = mk(tmp_path, audio)
    r.edit("artist", " ")
    assert r.filename() is None and not r.selected and r.flags([]) == ["no artist or title"]


@pytest.mark.parametrize("f,v,out,ok", [
    ("bpm", "128,5", "128.5", True), ("bpm", "1000", "", False), ("bpm", "0", "", False),
    ("bpm", "abc", "", False), ("bpm", "", "", True), ("year", "2020-05", "2020-05", True),
    ("year", "20", "", False), ("year", "1899", "", False), ("key", "anything", "anything", True)])
def test_validation(tmp_path, audio, f, v, out, ok):
    r = mk(tmp_path, audio)
    assert (r.edit(f, v) is None) == ok
    if ok:
        assert r.values[f] == out
    else:
        assert r.values[f] == r.suggested[f]


def test_edit_errors(tmp_path, audio):
    r = mk(tmp_path, audio)
    assert r.edit("nope", "x") == "unknown field"
    assert r.edit("title", 5) == "invalid value"


def test_flags(tmp_path, audio):
    r = mk(tmp_path, audio, title="Prisma Foo Remix", flags=["tag and file name differ", "remix without parentheses, check"])
    assert r.flags(["duplicate of 2"]) == ["tag and file name differ", "remix without parentheses, check", "duplicate of 2"]
    r.edit("album", "x")
    assert r.flags([]) == ["remix without parentheses, check"]
    r.edit("title", "Prisma (Foo Remix)")
    assert r.flags([]) == []
    r.edit("title", "Pri*sma")
    assert r.flags([]) == ["odd characters in artist or title"]
    r.reset()
    assert "tag and file name differ" in r.flags([])
