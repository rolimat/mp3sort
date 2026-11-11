import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sorter.apply import COPIED_NOT_DELETED
from sorter.gui_model import Model, load_settings, save_settings


def trunc(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class App:
    def __init__(self, root, model: Model, ask_directory=filedialog.askdirectory,
                 confirm=messagebox.askyesno, show_error=None):
        self.root, self.model = root, model
        self.ask_directory, self.confirm = ask_directory, confirm
        self.show_error = show_error or (lambda m: messagebox.showerror("mp3sort", m))
        self.worker: threading.Thread | None = None
        self._result = None
        self._progress = None
        self.src_var, self.dst_var = tk.StringVar(), tk.StringVar()
        self.status_var, self.footer_var = tk.StringVar(), tk.StringVar()
        root.title("mp3sort")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.createcommand("::tk::mac::Quit", self.on_close)  # Cmd+Q bypasses WM_DELETE_WINDOW
        self._build()
        self._sync()

    # --- layout ---
    def _build(self):
        f = ttk.Frame(self.root, padding=8)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(2, weight=1)
        ttk.Label(f, text="Source").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.src_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        self.src_btn = ttk.Button(f, text="Choose…", command=self.choose_source)
        self.src_btn.grid(row=0, column=2)
        ttk.Label(f, text="Destination").grid(row=1, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.dst_var, state="readonly").grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        self.dst_btn = ttk.Button(f, text="Choose…", command=self.choose_dest)
        self.dst_btn.grid(row=1, column=2)
        self.scan_btn = ttk.Button(f, text="Scan", command=self.scan)
        self.scan_btn.grid(row=1, column=3, padx=(6, 0))

        self.body = ttk.Frame(f)
        self.body.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=6)
        self.body.columnconfigure(0, weight=3)
        self.body.columnconfigure(1, weight=2)
        self.body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(self.body, columns=("w", "c", "n", "name", "kbps"),
                                 show="headings", selectmode="browse", height=14)
        for c, t, w, a in (("w", "⚠", 30, "center"), ("c", "✓", 30, "center"), ("n", "#", 40, "e"),
                           ("name", "New name", 380, "w"), ("kbps", "kbps", 80, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "name"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self._click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_detail())
        side = ttk.LabelFrame(self.body, text="Selected track", padding=6)
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.detail = tk.Text(side, width=36, height=14, wrap="word", state="disabled",
                              borderwidth=0, highlightthickness=0)
        self.detail.pack(fill="both", expand=True)
        self.results = ttk.Treeview(f, columns=("s", "f", "m"), show="headings", height=14)
        for c, t, w in (("s", "", 30), ("f", "File", 380), ("m", "Message", 300)):
            self.results.heading(c, text=t)
            self.results.column(c, width=w, anchor="center" if c == "s" else "w")
        self.results.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=6)
        self.results.grid_remove()

        ttk.Label(f, textvariable=self.status_var, foreground="#b45309").grid(row=3, column=0, columnspan=4, sticky="w")
        foot = ttk.Frame(f)
        foot.grid(row=4, column=0, columnspan=4, sticky="ew")
        foot.columnconfigure(0, weight=1)
        ttk.Label(foot, textvariable=self.footer_var).grid(row=0, column=0, sticky="w")
        self.move_btn = ttk.Button(foot, text="Move 0 selected", command=self.move)
        self.move_btn.grid(row=0, column=1)
        self.again_btn = ttk.Button(foot, text="Scan again", command=self.scan)
        self.again_btn.grid(row=0, column=2, padx=(6, 0))
        self.again_btn.grid_remove()

    # --- state ---
    def _sync(self):
        self.src_var.set(str(self.model.source or ""))
        self.dst_var.set(str(self.model.dest or ""))
        busy = self.model.busy or self.worker is not None
        idle = "disabled" if busy else "normal"
        for b in (self.src_btn, self.dst_btn, self.again_btn):
            b.config(state=idle)
        self.scan_btn.config(state="normal" if self.model.source and self.model.dest and not busy else "disabled")
        k = sum(it.selected for it in self.model.items)
        self.move_btn.config(text=f"Move {k} selected", state="normal" if k and not busy else "disabled")

    def _choose(self, which):
        cur = getattr(self.model, which)
        p = self.ask_directory(initialdir=str(cur) if cur else None, mustexist=True)
        if p:
            setattr(self.model, which, Path(p))
            save_settings(self.model.source, self.model.dest)
            self._sync()

    def choose_source(self):
        self._choose("source")

    def choose_dest(self):
        self._choose("dest")

    # --- table ---
    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(self.model.items):
            kb = "?" if it.bitrate is None else f"{it.bitrate}" + (" VBR" if it.vbr else "")
            self.tree.insert("", "end", iid=str(i), values=(
                "⚠" if it.proposal.flags else "", "☑" if it.selected else "☐", i + 1,
                trunc(it.proposal.filename or "(no proposed name)"), kb))
        self.footer_var.set(self.model.footer())
        self._sync()

    def _inert(self):
        return self.model.busy or self.worker is not None

    def toggle_row(self, i):
        if self._inert():
            return
        msg = self.model.toggle(i)
        self.status_var.set(msg or "")
        self.tree.set(str(i), "c", "☑" if self.model.items[i].selected else "☐")
        self.footer_var.set(self.model.footer())
        self._sync()

    def _click(self, e):
        if self._inert():
            return
        row = self.tree.identify_row(e.y)
        if row and self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#2":
            self.toggle_row(int(row))

    def _toggle_selected(self):
        if self._inert():
            return "break"
        s = self.tree.selection()
        if s:
            self.toggle_row(int(s[0]))
        return "break"

    def detail_text(self):
        return self.detail.get("1.0", "end").strip()

    def _set_detail(self, txt):
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", txt)
        self.detail.config(state="disabled")

    def _show_detail(self):
        s = self.tree.selection()
        if self._inert() or not s:
            return
        txt = "\n".join(f"{k}: {v}" for k, v in self.model.detail(int(s[0])))
        self._set_detail(txt)

    # --- background work: thread computes, main thread polls via root.after ---
    def _run(self, work, done):
        def target():
            try:
                self._result = work()
            except Exception as e:
                self._result = e
        self.worker = threading.Thread(target=target, daemon=True)
        self._sync()
        self.worker.start()
        self._poll(done)

    def _poll(self, done):
        if self._progress:
            self.status_var.set(f"Moving {self._progress[0]}/{self._progress[1]}…")
        if self.worker.is_alive():
            self.root.after(50, self._poll, done)
            return
        self.worker, r = None, self._result
        self._progress = None
        done(r)
        self._sync()

    def _show_table(self, table: bool):
        for w, on in ((self.body, table), (self.results, not table), (self.move_btn, table), (self.again_btn, not table)):
            w.grid() if on else w.grid_remove()

    def scan(self):
        if not self.model.can_scan():
            return
        self.model.busy = True
        self.status_var.set("Scanning…")
        self.tree.delete(*self.tree.get_children())
        self._set_detail("")
        self._show_table(True)

        def done(r):
            self.model.busy = False
            self.status_var.set("")
            if isinstance(r, Exception):
                self.show_error(str(r))
            elif r:
                self.show_error(r)
            self.refresh_table()
        self._run(self.model.scan, done)

    def move(self):
        k = sum(it.selected for it in self.model.items)
        if not k or self.model.busy or not self.confirm("mp3sort", f"Move {k} files to {self.model.dest}?"):
            return
        self.model.busy = True

        def prog(i, n):
            self._progress = (i, n)

        def done(r):
            self.model.busy = False
            self.status_var.set("")
            if isinstance(r, Exception):
                self.show_error(str(r))
                return
            self.results.delete(*self.results.get_children())
            for it, err in r:
                self.results.insert("", "end", values=("✓" if err is None else "!" if err.startswith(COPIED_NOT_DELETED) else "✗",
                                                       it.src.name, err or ""))
            self.footer_var.set(self.model.summary(r))
            self._show_table(False)
        self._run(lambda: self.model.move(prog), done)

    def on_close(self):
        if self.model.busy or self.worker is not None:
            self.status_var.set("Please wait until the current operation finishes")
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    s, d = load_settings()
    App(root, Model(s, d))
    root.mainloop()
