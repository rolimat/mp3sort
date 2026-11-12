import re
from pathlib import Path

import sorter.gui as gui
from sorter.gui_api import ApiImpl, exposed
from sorter.gui_model import Model

WEB = Path(gui.__file__).parent / "web"
JS = (WEB / "app.js").read_text() if (WEB / "app.js").exists() else ""
SINKS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function")


def test_assets_exist():
    for n in ("index.html", "app.css", "app.js"):
        assert (WEB / n).is_file(), n


def test_no_remote_urls_or_sinks():
    for n in ("index.html", "app.css", "app.js"):
        text = (WEB / n).read_text()
        assert not re.search(r"https?://", text), n
    assert not [s for s in SINKS if s in JS]


def test_csp_and_local_assets_only():
    html = (WEB / "index.html").read_text()
    assert ("default-src 'none'; script-src 'self' 'unsafe-eval'; style-src 'self'; img-src 'self' data:") in html
    assert "unsafe-inline" not in html  # pywebview's bridge needs eval/new Function, nothing else
    assert "Content-Security-Policy" in html
    assert 'src="app.js"' in html and 'href="app.css"' in html


def test_api_names_are_exposed():
    impl = ApiImpl(Model())
    names = {f.__name__ for f in exposed(impl)}
    used = set(re.findall(r"pywebview\.api\.(\w+)", JS))
    assert used and used <= names
    assert "pywebviewready" in JS


def test_launcher_source_rules():
    src = Path(gui.__file__).read_text()
    assert ".resolve().as_uri()" in src and "js_api=None" in src and "expose(" in src
    assert "json.dumps" in src and "closing" in src
    assert not re.search(r"^import webview|^from webview", src, re.M)  # only inside main()


def test_gui_imports_without_window():
    assert callable(gui.main)


def test_back_to_tracks_does_not_rescan():
    m = re.search(r'"Back to tracks"[\s\S]*?\n\s*\}\n', JS)
    assert m, "Back to tracks control missing"
    block = JS[m.start():m.start() + 400]
    assert "scan" not in block.split("addEventListener", 1)[1].split("\n")[0]
