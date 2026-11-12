"""pywebview launcher. `webview` is imported only inside main() so importing this module is side-effect free."""
import json
import logging
import sys
from pathlib import Path

from sorter.gui_api import ApiImpl, exposed
from sorter.gui_model import Model, load_settings

WEB = Path(__file__).parent / "web"


# what pywebview 6.2.1's util.load_js_files() reads from its js dir (polyfill only on mshtml)
WEBVIEW_JS = ("api.js", "customize.js", "finish.js", "state.js", "lib/dom_json.js", "lib/polyfill.js")


def _webview_js() -> Path:
    from webview.util import get_js_dir
    return Path(get_js_dir())  # the same lookup pywebview uses when it injects the files


def self_check() -> int:
    """Verify the bundle's assets and imports without opening a window."""
    try:
        for name in ("index.html", "app.css", "app.js"):
            if not (WEB / name).is_file():
                raise FileNotFoundError(f"missing web asset: {WEB / name}")
        js = _webview_js()
        missing = [f for f in WEBVIEW_JS if not (js / f).is_file()]
        if missing:
            raise FileNotFoundError(f"missing pywebview js files in {js}: {', '.join(missing)}")

        if sys.platform == "darwin":
            import webview.platforms.cocoa  # noqa: F401
    except Exception as e:
        print(f"self-check failed: {e!r}")
        return 1
    print("self-check ok")
    return 0


def main() -> None:
    import webview

    impl = ApiImpl(Model(*load_settings()))
    # file:// URL on purpose: a plain path would make pywebview start a localhost HTTP server
    url = (WEB / "index.html").resolve().as_uri()
    window = webview.create_window("mp3sort", url=url, js_api=None, width=1250, height=760)

    def choose_folder(kind):
        picked = window.create_file_dialog(webview.FileDialog.FOLDER)
        return picked[0] if picked else None

    def push(event, data):  # data only via json.dumps, never formatted into JS
        try:
            window.evaluate_js("window.onPush(" + json.dumps(event) + "," + json.dumps(data) + ")")
        except Exception:  # never let a page error abort a move
            logging.getLogger(__name__).exception("push %s failed", event)

    impl._choose, impl._push = choose_folder, push
    window.expose(*exposed(impl))
    window.events.closing += lambda: impl.can_close()  # False cancels (also Cmd+Q on macOS)
    webview.start()
