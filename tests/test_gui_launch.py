import sorter.gui as gui


def test_self_check_ok(capsys):
    assert gui.self_check() == 0
    assert "self-check ok" in capsys.readouterr().out


def test_self_check_missing_asset(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gui, "WEB", tmp_path)
    assert gui.self_check() == 1
    assert "index.html" in capsys.readouterr().out


def test_self_check_missing_pywebview_js(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gui, "_webview_js", lambda: tmp_path)
    assert gui.self_check() == 1
    assert "pywebview js" in capsys.readouterr().out
