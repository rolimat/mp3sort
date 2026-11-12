import json
import shutil
import threading

import pytest
from conftest import audio_path

from pathlib import Path

from sorter.gui_api import ApiImpl, exposed
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
         "can_close", "set_editing", "strip"}


def _nested(obj, attr_str):  # copy of pywebview.util get_nested_attribute
    for attr in attr_str.split("."):
        obj = getattr(obj, attr, None)
        if obj is None:
            return None
    return obj


def test_exposed_exact_names_and_dispatch(env):
    fs = exposed(env)
    assert {f.__name__ for f in fs} == NAMES and len(fs) == len(NAMES)
    funcs = {f.__name__: f for f in fs}

    def resolve(name):  # pywebview util.py: _functions.get(name) or nested(js_api=None, name)
        return funcs.get(name) or _nested(None, name)
    for n in NAMES:
        assert resolve(n) is funcs[n]
    for n in ("state.__globals__", "state.__globals__.update", "state.__builtins__",
              "state.__closure__", "__class__.__base__.__subclasses__",
              "__class__.__init_subclass__", "state.__code__", "model", "_impl"):
        r = resolve(n)
        assert r is None or not hasattr(r, "__globals__"), n


def test_exposed_behaves_like_impl(env):
    f = {g.__name__: g for g in exposed(env)}
    f = type('F', (), f)
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


def test_row_has_from_and_strip(env):
    env.scan()
    row = env.state()["state"]["rows"][0]
    assert row["from"].endswith(".mp3")
    r = env.strip(0)
    assert r["ok"] and isinstance(r["strip"]["removed"], list) and r["strip"]["from"] == row["from"]
    assert env.strip(99)["ok"] is False and env.strip(True)["ok"] is False and env.strip("0")["ok"] is False


def test_raising_push_does_not_break_move(env):
    calls = []

    def bad(ev, data):
        calls.append(ev)
        raise RuntimeError("js exception")
    env._push = bad
    env.scan()
    for i, r in enumerate(env.state()["state"]["rows"]):
        if not r["selected"]:
            env.toggle(i)
    assert env.move()["ok"]
    for _ in range(200):
        if "done" in calls and not env.model.busy and not env._moving:
            break
        threading.Event().wait(0.05)
    assert "progress" in calls and "done" in calls
    assert env.can_close() is True and len(list(env.dst.iterdir())) >= 1


def test_launcher_main_wiring(monkeypatch, tmp_path):
    import sys
    import types

    import sorter.gui as gui
    cap = {}

    class Closing(list):
        def __iadd__(self, f):
            self.append(f)
            return self

    win = types.SimpleNamespace(events=types.SimpleNamespace(closing=Closing()),
                                expose=lambda *fs: cap.setdefault("names", {f.__name__ for f in fs}))
    wv = types.ModuleType("webview")
    wv.FileDialog = types.SimpleNamespace(FOLDER=1)

    def create_window(title, **kw):
        cap["kw"] = kw
        return win
    wv.create_window, wv.start = create_window, lambda: cap.setdefault("started", True)
    monkeypatch.setitem(sys.modules, "webview", wv)
    gui.main()
    assert cap["kw"]["url"].startswith("file://") and cap["kw"]["js_api"] is None
    assert len(cap["names"]) == 11 and cap["started"]
    (closing,) = win.events.closing
    assert closing() is True


@pytest.fixture
def locked_dir():
    import os
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    done = []
    yield lambda p, mode=0: (p.chmod(mode), done.append(p))
    for p in done:
        p.chmod(0o755)


@pytest.mark.parametrize("which", ["src", "dst"])
def test_scan_unreadable_folder_reports_error(env, locked_dir, which):
    folder = getattr(env, which)
    locked_dir(folder)
    r = env.scan()
    assert not r["ok"] and r["state"]["rows"] == []
    assert f"cannot read {folder}: permission denied" in r["error"]
    assert "Privacy & Security" not in r["error"]  # EACCES: plain permission problem


def test_scan_macos_privacy_denial_gets_hint(env, monkeypatch):
    import errno
    import sorter.scan as sc

    def denied(p):
        raise PermissionError(errno.EPERM, "Operation not permitted", str(p))

    monkeypatch.setattr(sc.os, "scandir", denied)
    monkeypatch.setattr(sc.sys, "platform", "darwin")
    r = env.scan()
    assert not r["ok"] and f"cannot read {env.src}: permission denied" in r["error"]
    assert "System Settings > Privacy & Security" in r["error"]


def test_scan_source_listable_but_not_searchable(env, locked_dir):
    locked_dir(env.src, 0o644)
    r = env.scan()
    assert not r["ok"] and f"cannot read {env.src}: permission denied" in r["error"]


def test_scan_subfolder_listable_but_not_searchable_is_skipped(env, locked_dir):
    sub = env.src / "sub"
    sub.mkdir()
    shutil.copy(audio_path(), sub / "Ana - Bruma.mp3")
    locked_dir(sub, 0o644)
    r = env.scan()
    assert r["state"]["counts"]["tracks"] == 2 and "1 sub-folder could not be read" in r["error"]


def test_scan_skips_hidden_system_folders(env, locked_dir):
    trash = env.src / ".Trashes"
    (trash / "501").mkdir(parents=True)
    shutil.copy(audio_path(), trash / "501" / "x.mp3")
    shutil.copy(audio_path(), env.src / ".hidden.mp3")
    locked_dir(trash, 0o300)
    r = env.scan()
    assert r["ok"] and r["error"] is None and r["state"]["counts"]["tracks"] == 2


def test_scan_unreadable_subfolder_is_counted(env, locked_dir):
    sub = env.src / "sub"
    sub.mkdir()
    shutil.copy(audio_path(), sub / "Ana - Bruma.mp3")
    locked_dir(sub)
    r = env.scan()
    assert r["state"]["counts"]["tracks"] == 2
    assert not r["ok"] and "1 sub-folder could not be read" in r["error"]
