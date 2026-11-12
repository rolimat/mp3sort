"""JSON-only API for the web UI. Everything from the page is untrusted: validate before use."""
import threading
from pathlib import Path

from sorter.apply import FIELDS
from sorter.gui_model import Model, save_settings

MAX_VALUE = 500


class Api:
    def __init__(self, model: Model, choose_folder=lambda kind: None, push=lambda event, data: None):
        self.model, self._choose, self._push = model, choose_folder, push
        self._editing = False
        self._moving = False  # set before the thread starts, so there is no gap with model.busy

    # -- state ---------------------------------------------------------------
    def _busy(self) -> bool:
        return self._moving or self.model.busy

    def _row(self, i: int) -> dict:
        m, r = self.model, self.model.rows[i]
        flags = m.flags(i)
        edited = [f for f in FIELDS if r.values[f] != r.suggested[f]]
        return {"n": i + 1, "selected": r.selected, "chip": "warn" if flags else "edit" if edited else "",
                "flags": flags, "values": dict(r.values), "edited_fields": edited, "kbps": r.kbps,
                "vbr": r.vbr, "low_kbps": m.low_kbps(i), "filename": r.filename()}

    def _state(self) -> dict:
        m = self.model
        return {"folders": {"source": str(m.source) if m.source else None,
                            "destination": str(m.dest) if m.dest else None},
                "busy": self._busy(), "counts": m.counts(),
                "rows": [self._row(i) for i in range(len(m.rows))]}

    def _res(self, error: str | None = None) -> dict:
        return {"ok": error is None, "error": error, "state": self._state()}

    def _guard(self, *, editing: bool = False) -> str | None:
        if self._busy():
            return "busy"
        return "finish editing first" if editing and self._editing else None

    def _index(self, i) -> str | None:
        ok = isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(self.model.rows)
        return None if ok else "invalid row"

    # -- calls ---------------------------------------------------------------
    def state(self) -> dict:
        return self._res()

    def can_close(self) -> bool:
        return not self._busy()

    def pending_edits(self) -> int:
        return self.model.edited_count()

    def set_editing(self, on) -> dict:
        if not isinstance(on, bool):
            return self._res("invalid value")
        self._editing = on
        return self._res()

    def choose(self, kind) -> dict:
        if kind not in ("source", "destination"):
            return self._res("invalid folder kind")
        if err := self._guard(editing=True):
            return self._res(err)
        folder = self._choose(kind)
        if not folder or not isinstance(folder, str):
            return self._res("cancelled")
        m = self.model
        if kind == "source":
            m.source = Path(folder)
        else:
            m.dest = Path(folder)
        save_settings(m.source, m.dest)
        m.rows, m._scanned, m._g = [], None, None  # scan required again
        return self._res()

    def scan(self) -> dict:
        return self._res(self._guard(editing=True) or self.model.scan())

    def edit(self, i, field, value) -> dict:
        if err := self._guard() or self._index(i):
            return self._res(err)
        if field not in FIELDS or not isinstance(value, str):
            return self._res("invalid field or value")
        if len(value) > MAX_VALUE:
            return self._res(f"value too long (max {MAX_VALUE} characters)")
        return self._res(self.model.edit(i, field, value))

    def toggle(self, i) -> dict:
        if err := self._guard() or self._index(i):
            return self._res(err)
        return self._res(self.model.toggle(i))

    def reset(self, i) -> dict:
        if err := self._guard(editing=True) or self._index(i):
            return self._res(err)
        return self._res(self.model.reset(i))

    def move(self) -> dict:
        if err := self._guard(editing=True):
            return self._res(err)
        self._moving = True
        names = [r.filename() or "" for r in self.model.rows if r.selected]
        threading.Thread(target=self._run_move, args=(names,), daemon=True).start()
        return self._res()

    def _run_move(self, names: list[str]) -> None:
        data: dict = {"results": [], "summary": "", "error": None}
        try:
            out = self.model.move(lambda i, n: self._push("progress", {"i": i, "n": n, "name": names[i - 1]}))
            if isinstance(out, str):
                data["error"] = out
            else:
                pos = {id(r): n for n, r in enumerate(self.model.rows, 1)}
                data["results"] = [{"n": pos[id(r)], "filename": r.filename(), "error": e} for r, e in out]
                data["summary"] = self.model.summary(out)
                if out:  # destination listing is stale now
                    data["error"] = self.model.scan()
        except Exception as e:
            data["error"] = str(e) or type(e).__name__
        finally:
            self._moving = False
        data["state"] = self._state()
        self._push("done", data)
