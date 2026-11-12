"""pywebview launcher. `webview` is imported only inside main() so importing this module is side-effect free."""
import json
import logging
from pathlib import Path

from sorter.gui_api import ApiImpl, exposed
from sorter.gui_model import Model, load_settings


def main() -> None:
    import webview

    impl = ApiImpl(Model(*load_settings()))
    # file:// URL on purpose: a plain path would make pywebview start a localhost HTTP server
    url = (Path(__file__).parent / "web" / "index.html").resolve().as_uri()
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
