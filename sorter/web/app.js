"use strict";
// All DOM is built with createElement + textContent; nothing from the API is ever parsed as HTML.
const EDIT = ["artist", "title", "genre", "year", "key", "bpm"];
const HEAD = [["", ""], ["", ""], ["#", ""], ["Artist", ""], ["Title", ""], ["Genre", ""], ["Year", ""], ["Key", ""], ["BPM", "num"], ["kbps", "num"]];
const $ = (id) => document.getElementById(id);

let S = null;          // last state from the API
let cur = -1;          // row shown in the strip
let ed = null;         // open editor: {i, field, input, err, orig, pending, cell}
let moving = null;     // {i, n, name} while a move runs
let results = null;    // {results, summary, error} after a move
let note = "";
let clickRow = null;   // row under the mouse when an open editor loses focus: select it after the commit
let removed = { i: null, text: "" };  // "Removed" text for the strip row (read-only call)

function h(tag, cls, ...kids) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids) e.append(k);
  return e;
}
const txt = (cls, s, tag = "span") => h(tag, cls, String(s));

// API calls are serialised: pywebview runs each call on its own thread, order matters for set_editing.
let queue = Promise.resolve();
const q = (fn) => (queue = queue.then(fn, fn));
const A = {
  state: () => q(() => pywebview.api.state()),
  choose: (k) => q(() => pywebview.api.choose(k)),
  pending_edits: () => q(() => pywebview.api.pending_edits()),
  scan: () => q(() => pywebview.api.scan()),
  edit: (i, f, v) => q(() => pywebview.api.edit(i, f, v)),
  toggle: (i) => q(() => pywebview.api.toggle(i)),
  reset: (i) => q(() => pywebview.api.reset(i)),
  move: () => q(() => pywebview.api.move()),
  strip: (i) => q(() => pywebview.api.strip(i)),
  set_editing: (on) => q(() => pywebview.api.set_editing(on)),
};

const busy = () => !!(S && S.busy) || !!moving;
const locked = () => busy() || !!ed;   // controls disabled while moving or editing

function apply(r) {
  if (r && r.state) {
    S = r.state;
    removed = { i: null, text: "" };
    if (cur >= S.rows.length) cur = -1;
  }
  note = r && r.error && r.error !== "cancelled" ? r.error : "";
  return !!(r && r.ok);
}

// ---- dialog --------------------------------------------------------------
function confirmDlg(title, body, okLabel) {
  return new Promise((resolve) => {
    const m = $("modal");
    const done = (v) => { m.hidden = true; m.replaceChildren(); document.removeEventListener("keydown", key, true); resolve(v); };
    const ok = h("button", "p", okLabel), no = h("button", "", "Cancel");
    ok.addEventListener("click", () => done(true));
    no.addEventListener("click", () => done(false));
    const key = (e) => {   // modal: Esc cancels, Tab cycles inside, Enter only presses the focused button
      if (e.key === "Escape") { e.preventDefault(); done(false); }
      else if (e.key === "Tab") { e.preventDefault(); (document.activeElement === ok ? no : ok).focus(); }
      else if (e.key === "Enter" && document.activeElement !== ok && document.activeElement !== no) { e.preventDefault(); e.stopPropagation(); }
    };
    document.addEventListener("keydown", key, true);
    m.replaceChildren(h("div", "dlg", txt("", title, "h3"), txt("", body, "p"), h("div", "btns", no, ok)));
    m.hidden = false;
    ok.focus();
  });
}

// ---- top bar -------------------------------------------------------------
async function discardOk() {
  const n = await A.pending_edits();
  return !n || confirmDlg(`Discard ${n} edited track${n > 1 ? "s" : ""}?`, "Your tag edits are lost when the folders are scanned again.", "Discard");
}

async function chooseFolder(kind) {
  if (locked() || !(await discardOk())) return;
  const r = await A.choose(kind);
  if (r.ok) { results = null; cur = -1; }
  apply(r);
  render();
}

async function scan() {
  if (locked() || !(await discardOk())) return;
  results = null;
  apply(await A.scan());
  cur = -1;
  render();
}

function renderBar() {
  const f = S.folders, items = [];
  for (const [kind, label] of [["source", "Source"], ["destination", "Destination"]]) {
    const b = h("button", "", "Choose…");
    b.disabled = locked();
    b.addEventListener("click", () => chooseFolder(kind));
    const p = h("div", "path", h("b", "", f[kind] || "(not set)"));
    p.title = f[kind] || "";
    items.push(txt("lbl", label), p, b);
  }
  const s = h("button", "p", "Scan");
  s.disabled = locked() || !f.source || !f.destination;
  s.addEventListener("click", scan);
  $("bar").replaceChildren(...items, s);
}

// ---- table ---------------------------------------------------------------
function cell(r, i, f) {
  const empty = !r.values[f];
  const td = h("td", "ed" + (r.edited_fields.includes(f) ? " edited" : "") + (empty ? " g" : "") + (f === "bpm" ? " num" : ""), empty ? "—" : r.values[f]);
  td.tabIndex = 0;
  td.dataset.i = i;
  td.dataset.f = f;
  td.addEventListener("dblclick", () => openCell(i, f));
  td.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === td) { e.preventDefault(); openCell(i, f); } });
  return td;
}

function row(r, i) {
  const cb = h("span", "cb" + (r.selected ? " on" : "") + (r.filename ? "" : " no"));
  cb.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (locked() || !r.filename) return;
    apply(await A.toggle(i));
    render();
  });
  const chip = h("td", "");
  if (r.flags.length) { const c = txt("chip cw", "⚠"); c.title = r.flags.join("; "); chip.append(c); }
  if (r.edited_fields.length) chip.append(txt("chip ce", "✎"));
  const kb = h("td", "num" + (r.low_kbps ? " r" : ""), r.kbps == null ? "—" : String(r.kbps));
  if (r.vbr) kb.append(" ", txt("g", "VBR"));
  const tr = h("tr", (i === cur ? "sel " : "") + (r.low_kbps ? "dim" : ""), h("td", "", cb), chip, txt("g", r.n, "td"),
    ...EDIT.map((f) => cell(r, i, f)), kb);
  tr.dataset.i = i;
  tr.addEventListener("mousedown", () => { clickRow = i; });
  tr.addEventListener("click", () => {
    if (locked() || cur === i) return;
    cur = i;
    markSel();
    renderStrip(); renderFoot();
  });
  return tr;
}

function markSel() {
  for (const t of $("main").querySelectorAll("tbody tr")) t.classList.toggle("sel", +t.dataset.i === cur);
}

function renderMain() {
  const m = $("main");
  if (results) return renderResults(m);
  if (!S.rows.length) return m.replaceChildren(txt("empty", "Choose a source and a destination folder, then press Scan."));
  const head = h("tr", "", ...HEAD.map(([t, c]) => txt(c, t, "th")));
  m.replaceChildren(h("table", "", h("thead", "", head), h("tbody", "", ...S.rows.map(row))));
}

function renderResults(m) {
  const rows = results.results.map((x) => {
    const ok = x.error === null, kept = !ok && x.error.startsWith("copied and verified");
    return h("tr", "", txt(ok ? "ok" : kept ? "w" : "r", ok ? "✓" : kept ? "!" : "✗", "td"), txt("", x.filename || "(no name)", "td"),
      txt(ok ? "g" : kept ? "w" : "r", ok ? "moved" : x.error, "td"));
  });
  const head = h("tr", "", txt("", "", "th"), txt("", "File", "th"), txt("", "Result", "th"));
  m.replaceChildren(h("table", "", h("thead", "", head), h("tbody", "", ...rows)));
}

// ---- strip + footer ------------------------------------------------------
function renderStrip() {
  const s = $("strip");
  const r = !results && cur >= 0 ? S.rows[cur] : null;
  if (!r) return s.replaceChildren(txt("g wide", results ? "" : "Select a row to see the file name and more tags."));
  const field = (label, f) => {
    const inp = h("input");
    inp.value = r.values[f];
    inp.placeholder = "(empty)";
    inp.disabled = busy();
    const err = h("div", "err");
    inp.dataset.f = f;
    inp.addEventListener("focus", () => { if (!ed) begin(cur, f, inp, err); });
    inp.addEventListener("keydown", editorKeys);
    inp.addEventListener("blur", onBlur);
    return [txt("lbl", label), h("div", "", inp, err)];
  };
  s.replaceChildren(txt("lbl", "File"), txt("v", r.filename || "—"), ...field("Album", "album"), ...field("Label", "label"),
    txt("lbl", "From"), txt("v g", r.from), ...field("Comment", "comment"),
    txt("lbl", "Removed"), txt("v g wide", removed.i === cur ? removed.text : "\u2026"));
  if (removed.i !== cur) {
    const i = cur;
    removed = { i, text: "" };
    A.strip(i).then((x) => {
      if (!x.ok || cur !== i || !S) return;
      const t = x.strip.removed;
      removed = { i, text: t.length ? t.join(" \u00B7 ") : "nothing" };
      if (!ed) renderStrip();
    });
  }
}

function renderFoot() {
  const f = $("foot");
  if (moving) {
    const bar = h("i");
    bar.style.width = (moving.n ? ((moving.i - 1) / moving.n) * 100 : 0) + "%";
    return f.replaceChildren(h("div", "", txt("g", `Moving ${moving.i} / ${moving.n} · ${moving.name}`, "div"), h("div", "prog", bar),
      txt("g", "The window can't be closed until it finishes.", "div")));
  }
  if (results) {
    const b = h("button", "p", "Scan again");
    b.addEventListener("click", scan);
    return f.replaceChildren(txt(results.error ? "r" : "g", [results.summary, results.error].filter(Boolean).join(" · ")), b);
  }
  const c = S.counts;
  const info = `${c.tracks} tracks · ${c.ok} ok · ${c.warn} ⚠ · ${c.edited} edited · ${c.selected} selected`;
  const reset = h("button", "", "↺ Reset row");
  reset.disabled = locked() || cur < 0 || !S.rows[cur] || !S.rows[cur].edited_fields.length;
  reset.addEventListener("click", async () => { apply(await A.reset(cur)); render(); });
  const mv = h("button", "p", `Move ${c.selected} track${c.selected === 1 ? "" : "s"}`);
  mv.disabled = locked() || c.selected === 0;
  mv.addEventListener("click", move);
  f.replaceChildren(h("div", "", txt("g", info), note ? txt("r", "  " + note) : ""), h("div", "btns", reset, mv));
}

function render() {
  renderBar(); renderMain(); renderStrip(); renderFoot();
}

// ---- editing -------------------------------------------------------------
function begin(i, field, input, err) {
  ed = { i, field, input, err, orig: input.value, pending: false, cell: !!input.closest("td") };
  A.set_editing(true);
  renderBar(); renderFoot();
}

function end() {
  ed = null;
  A.set_editing(false);
}

function openCell(i, f) {
  if (locked()) return;
  cur = i;
  const td = $("main").querySelector(`td[data-i="${i}"][data-f="${f}"]`);
  const inp = h("input");
  inp.value = S.rows[i].values[f];
  const err = h("div", "err");
  td.replaceChildren(inp, err);
  markSel();
  renderStrip();
  inp.addEventListener("keydown", editorKeys);
  inp.addEventListener("blur", onBlur);
  begin(i, f, inp, err);
  inp.focus();
  inp.select();
}

function editorKeys(e) {
  if (!ed || e.target !== ed.input) return;
  if (ed.pending) { e.preventDefault(); return; }   // the screen must match what the server applied
  if (e.key === "Enter") { e.preventDefault(); commit(0); }
  else if (e.key === "Escape") { e.preventDefault(); cancel(); }
  else if (e.key === "Tab" && ed.cell) { e.preventDefault(); commit(e.shiftKey ? -1 : 1); }
}

function onBlur(e) {
  if (!ed) return;
  const to = e.relatedTarget && e.relatedTarget.closest("#strip") ? e.relatedTarget.dataset.f : null;
  if (to) ed.refocus = to;
  if (ed.pending) return;
  if (ed.input.value !== ed.orig || ed.err.textContent) return commit(0);
  closeUnchanged();
}

function afterClose(refocus) {
  if (clickRow !== null) { cur = clickRow; clickRow = null; }
  render();
  if (refocus) { const el = $("strip").querySelector(`input[data-f="${refocus}"]`); if (el) el.focus(); }
}

function closeUnchanged() {
  const wasCell = ed.cell;
  const refocus = ed.refocus;
  end();
  if (wasCell || clickRow !== null) afterClose(refocus); else { renderBar(); renderFoot(); }   // keep the table intact so a click on another row still lands
}

function cancel() {
  end();
  render();
}

async function commit(dir) {
  const e = ed;
  if (!e || e.pending) return;
  const next = dir ? nextCell(e.i, e.field, dir) : null;
  if (e.input.value === e.orig) { closeUnchanged(); if (next) openCell(...next); return; }
  e.pending = true;
  let r;
  try { r = await A.edit(e.i, e.field, e.input.value); } finally { e.pending = false; }
  if (ed !== e) return;
  if (r.ok) {
    apply(r);
    const refocus = e.refocus;
    end();
    afterClose(refocus);
    if (next) openCell(...next);
  } else {
    clickRow = null;
    e.err.textContent = r.error;   // stays open: the invalid value must be fixed or cancelled
    e.input.focus();
  }
}

function nextCell(i, f, dir) {
  const k = i * EDIT.length + EDIT.indexOf(f) + dir;
  const ni = Math.floor(k / EDIT.length);
  return k < 0 || ni >= S.rows.length ? null : [ni, EDIT[k - ni * EDIT.length]];
}

// ---- move ----------------------------------------------------------------
async function move() {
  if (locked()) return;
  const sel = S.rows.filter((r) => r.selected);
  const edited = sel.filter((r) => r.edited_fields.length).length;
  const body = `To ${S.folders.destination}.` + (edited ? ` ${edited} with edited tags, written as shown.` : "");
  if (!(await confirmDlg(`Move ${sel.length} track${sel.length === 1 ? "" : "s"}?`, body, "Move"))) return;
  moving = { i: 1, n: sel.length, name: "" };   // before the call: "done" may arrive before it resolves
  render();
  const r = await A.move();
  if (!r.ok) { moving = null; apply(r); render(); }
}

window.onPush = function (event, data) {
  if (event === "progress") {
    moving = { i: data.i, n: data.n, name: data.name || "" };
    renderFoot();
  } else if (event === "done") {
    moving = null;
    results = { results: data.results, summary: data.summary, error: data.error };
    (data.state ? Promise.resolve({ ok: true, state: data.state }) : A.state()).then((r) => { apply(r); note = ""; cur = -1; render(); });
  }
};

document.addEventListener("mousedown", () => { clickRow = null; }, true);

window.addEventListener("pywebviewready", async () => {
  apply(await A.state());
  render();
});
