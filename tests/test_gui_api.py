import json
import shutil
import threading

import pytest
from conftest import audio_path

from sorter.gui_api import Api
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
    api = Api(Model(src, dst), choose_folder=lambda kind: picked["v"], push=push)
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
