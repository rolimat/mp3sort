import shutil
import time
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")  # absent on minimal CI images

import sorter.gui_model as gm  # noqa: E402
from sorter.gui import App, trunc  # noqa: E402
from sorter.gui_model import Model  # noqa: E402

AUDIO = Path(__file__).parent / "fixtures" / "audio" / "a1.mp3"
needs_audio = pytest.mark.skipif(not AUDIO.exists(), reason="missing a1.mp3")


@pytest.fixture(autouse=True)
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "SETTINGS_PATH", tmp_path / "cfg" / "settings.json")


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    yield r
    r.destroy()


def wait(root, app):
    end = time.time() + 20
    while app.worker is not None and time.time() < end:
        root.update()
        time.sleep(0.01)
    root.update()
    assert app.worker is None


def folders(tmp_path):
    s, d = tmp_path / "src", tmp_path / "dst"
    s.mkdir(); d.mkdir()
    return s, d


def test_trunc():
    assert trunc("x" * 61) == "x" * 59 + "…" and trunc("abc") == "abc"


def test_choose_saves_and_scan_enabled(root, tmp_path):
    s, d = folders(tmp_path)
    picks = iter([str(s), str(d)])
    app = App(root, Model(), ask_directory=lambda **k: next(picks), confirm=lambda *a, **k: True)
    assert str(app.scan_btn["state"]) == "disabled"
    app.choose_source()
    assert str(app.scan_btn["state"]) == "disabled"
    app.choose_dest()
    assert str(app.scan_btn["state"]) == "normal"
    assert gm.load_settings() == (s, d)


def test_cancelled_dialog_keeps_value(root, tmp_path):
    app = App(root, Model(tmp_path, None), ask_directory=lambda **k: "", confirm=lambda *a, **k: True)
    app.choose_source()
    assert app.model.source == tmp_path


def test_scan_error_shown_without_dialog(root, tmp_path):
    s, d = folders(tmp_path)
    errs = []
    app = App(root, Model(s, tmp_path / "gone"), ask_directory=None, confirm=None, show_error=errs.append)
    app.scan(); wait(root, app)
    assert errs and "does not exist" in errs[0] and not app.tree.get_children()


@needs_audio
def test_scan_select_move(root, tmp_path):
    s, d = folders(tmp_path)
    shutil.copy(AUDIO, s / "Lumen - Prisma - www.example.com.mp3")
    shutil.copy(AUDIO, s / "junk.mp3")
    answers = [False, True]
    errs = []
    app = App(root, Model(s, d), ask_directory=None, confirm=lambda *a, **k: answers.pop(0), show_error=errs.append)
    app.scan(); wait(root, app)
    rows = app.tree.get_children()
    assert len(rows) == len(app.model.items) == 2
    v = app.tree.item(rows[0], "values")
    assert v[1] in ("☑", "☐") and v[2] == "1"
    assert v[0] == "⚠" and v[3] == app.model.items[0].proposal.filename and v[4] != ""
    assert str(app.move_btn["state"]) == "disabled" and app.move_btn["text"] == "Move 0 selected"
    app.tree.selection_set(rows[0]); root.update()
    assert "Original file" in app.detail_text()
    assert app.model.footer() in app.footer_var.get()
    app.toggle_row(1)
    k = sum(it.selected for it in app.model.items)
    assert f"Move {k} selected" == app.move_btn["text"]
    app.move(); wait(root, app)          # confirm False
    assert not list(d.iterdir()) and len(list(s.iterdir())) == 2
    app.move(); wait(root, app)          # confirm True
    assert len(list(d.iterdir())) == k
    assert k == 1 and app.body.winfo_manager() == '' and app.results.winfo_manager() == 'grid'
    assert app.results.get_children() and "Moved:" in app.footer_var.get()
    app.scan(); wait(root, app)          # Scan again returns to table
    assert app.body.winfo_manager() == 'grid' and len(app.tree.get_children()) == 1


def test_toggle_refusal(root, tmp_path):
    from sorter.clean import Proposal
    from sorter.scan import Item
    s, d = folders(tmp_path)
    m = Model(s, d)
    m.items = [Item(s / "a.mp3", Proposal(None, None, ["x"]), False)]
    app = App(root, m, ask_directory=None, confirm=None)
    app.refresh_table()
    app.toggle_row(0)
    assert app.status_var.get() == "cannot include (no proposed name)" and not m.items[0].selected


def test_inert_while_busy(root, tmp_path):
    from sorter.clean import Proposal
    from sorter.scan import Item
    s, d = folders(tmp_path)
    m = Model(s, d)
    m.items = [Item(s / "a.mp3", Proposal("A", "B", []), True)]
    app = App(root, m, ask_directory=None, confirm=None)
    app.refresh_table()
    m.busy = True
    try:
        m.items = []  # stale row 0 would raise IndexError if handled
        app.toggle_row(0)
        app.tree.selection_set("0")
        app._show_detail()
        assert app._toggle_selected() == "break"
        assert app.detail_text() == ""
    finally:
        m.busy = False


def test_close_and_quit(root, tmp_path):
    app = App(root, Model(), ask_directory=None, confirm=None)
    assert root.tk.call("info", "commands", "::tk::mac::Quit")
    app.model.busy = True
    try:
        app.on_close()
        assert root.winfo_exists()
    finally:
        app.model.busy = False
    called = []
    root.destroy = (lambda: called.append(1))
    app.on_close()
    del root.destroy  # restore the class method for the fixture teardown
    assert called
