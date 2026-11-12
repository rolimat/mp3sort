import json
import shutil
import threading

import pytest
from conftest import audio_path

from pathlib import Path

from sorter.gui_api import ApiImpl, js_api
from sorter.gui_model import Row
from sorter.scan import Item
from sorter.gui_model import Model, load_settings


@pytest.fixture
def env(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    for n in ("Lumen - Prisma.mp3", "Nova - Echo.mp3"):
        shutil.copy(audio_path(), src / n)
    events, done = [], threading.Event()

    def push(ev, data):
        json.dumps(data)  # must be serializable
        events.append((ev, data))
        if ev == "done":
            done.set()

    picked = {"v": None}
    api = ApiImpl(Model(src, dst), choose_folder=lambda kind: picked["v"], push=push)
    api.events, api.done, api.picked, api.src, api.dst = events, done, picked, src, dst
    return api


def test_state_json_and_scan(env):
    r = env.scan()
    assert r["ok"] and r["error"] is None
    json.dumps(r)
    st = r["state"]
    assert st["counts"]["tracks"] == 2 and not st["busy"]
    row = st["rows"][0]
    assert {"n", "selected", "chip", "flags", "values", "edited_fields", "kbps", "vbr",
            "low_kbps", "filename"} <= row.keys()
    assert row["n"] == 1


def test_bad_input_no_change(env):
    env.scan()
    before = env.state()["state"]
    for call in (lambda: env.edit(99, "artist", "x"), lambda: env.edit(-1, "artist", "x"),
                 lambda: env.edit(True, "artist", "x"), lambda: env.edit("0", "artist", "x"),
                 lambda: env.edit(0, "nope", "x"), lambda: env.edit(0, "artist", 5),
                 lambda: env.edit(0, "artist", "x" * 501), lambda: env.toggle(2),
                 lambda: env.reset(None), lambda: env.choose("other"),
                 lambda: env.set_editing("yes")):
        r = call()
        assert r["ok"] is False and r["error"]
    assert env.state()["state"] == before


def test_edit_toggle_reset(env):
    env.scan()
    assert env.edit(0, "artist", "Zed")["ok"]
    s = env.state()["state"]
    assert s["rows"][0]["edited_fields"] == ["artist"] and s["counts"]["edited"] == 1
    assert env.pending_edits() == 1
    r = env.edit(0, "bpm", "abc")
    assert r["ok"] is False and "BPM" in r["error"]
    sel = s["rows"][1]["selected"]
    assert env.toggle(1)["state"]["rows"][1]["selected"] != sel
    assert env.reset(0)["state"]["rows"][0]["edited_fields"] == []


def test_editing_blocks(env):
    env.scan()
    env.set_editing(True)
    for call in (env.move, env.scan, lambda: env.choose("source"), lambda: env.reset(0)):
        r = call()
        assert r["ok"] is False and r["error"] == "finish editing first"
    env.set_editing(False)
    assert env.scan()["ok"]


def test_choose(env, tmp_path, monkeypatch):
    monkeypatch.setattr("sorter.gui_model.SETTINGS_PATH", tmp_path / "s.json")
    env.scan()
    assert env.choose("source")["error"] == "cancelled"
    assert env.state()["state"]["counts"]["tracks"] == 2
    new = tmp_path / "other"
    new.mkdir()
    env.picked["v"] = str(new)
    r = env.choose("source")
    assert r["ok"] and r["state"]["rows"] == []
    assert r["state"]["folders"]["source"] == str(new)
    assert load_settings()[0] == new


def test_move_pushes_and_rescans(env):
    env.scan()
    env.toggle(1)  # deselect second
    r = env.move()
    assert r["ok"]
    assert env.done.wait(20)
    done = [d for e, d in env.events if e == "done"][0]
    assert done["summary"].startswith("Moved:") and done["results"]
    assert any(e == "progress" for e, _ in env.events)
    assert done["state"]["counts"]["tracks"] == 1  # rescanned: moved file gone from source
    assert not done["state"]["busy"] and env.can_close() is True
    assert len(list(env.dst.iterdir())) == 1


def test_move_error_pushes_done(env):
    # never scanned: model refuses
    env.move()
    assert env.done.wait(20)
    d = [d for e, d in env.events if e == "done"][0]
    assert d["error"]


def test_busy_blocks(env):
    env.scan()
    env._moving = True
    assert env.can_close() is False
    for call in (env.scan, lambda: env.edit(0, "artist", "x"), lambda: env.toggle(0), env.move):
        assert call()["error"] == "busy"
    assert env.state()["state"]["busy"]


NAMES = {"state", "choose", "pending_edits", "scan", "edit", "toggle", "reset", "move",
         "can_close", "set_editing"}


def test_facade_exposes_only_api(env):
    f = js_api(env)
    assert {n for n in dir(f) if not n.startswith("_")} == NAMES
    assert not hasattr(f, "__dict__") or not vars(f)
    env.scan()
    bad = (Model, Row, Item, Path, ApiImpl)
    seen = 0

    def walk(obj, depth):
        nonlocal seen
        for n in dir(obj):
            if n.startswith("_"):
                continue
            try:
                v = getattr(obj, n)
            except Exception:
                continue
            seen += 1
            assert not isinstance(v, bad), n
            if depth < 4:
                walk(v, depth + 1)
    walk(f, 1)
    assert seen


def test_facade_behaves_like_impl(env):
    f = js_api(env)
    assert f.scan()["state"]["counts"]["tracks"] == 2
    assert f.edit(0, "artist", "Zed")["ok"] and f.pending_edits() == 1
    assert f.edit(9, "artist", "x")["ok"] is False
    assert f.can_close() is True and f.set_editing(True)["ok"]
    assert f.move()["error"] == "finish editing first"
    assert f.state() == env.state()


def test_concurrent_move_starts_one(env, monkeypatch):
    env.scan()
    gate, calls = threading.Event(), []

    def slow(progress):
        calls.append(1)
        gate.wait(10)
        return []
    monkeypatch.setattr(env.model, "move", slow)
    res = []
    ts = [threading.Thread(target=lambda: res.append(env.move()["error"])) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(map(str, res)) == ["None", "busy"]
    gate.set()
    assert env.done.wait(10) and len(calls) == 1


def test_choose_save_error(env, tmp_path, monkeypatch):
    env.scan()
    new = tmp_path / "other"
    new.mkdir()
    env.picked["v"] = str(new)

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr("sorter.gui_api.save_settings", boom)
    r = env.choose("source")
    assert r["ok"] is False and r["error"].startswith("could not save settings")
    assert r["state"]["rows"] == [] and r["state"]["folders"]["source"] == str(new)


def test_done_always_pushed(env, monkeypatch):
    env.scan()

    def boom(progress):
        raise RuntimeError("kaput")
    monkeypatch.setattr(env.model, "move", boom)
    env.move()
    assert env.done.wait(10)
    d = [d for e, d in env.events if e == "done"][0]
    assert "kaput" in d["error"] and d["state"]["busy"] is False


def test_set_folder_clears(env):
    env.scan()
    env.model.set_folder("destination", env.dst)
    assert env.model.rows == [] and env.model._existing == set()
