import argparse
from pathlib import Path

from sorter.apply import COPIED_NOT_DELETED, apply_item
from sorter.scan import Item, scan

DEFAULT_SOURCE = Path.home() / "Soulseek Downloads" / "complete"
HELP = "Numbers to EXCLUDE/INCLUDE (e.g. 3,5), Enter = apply, q = quit"


def _short(name: str, n: int = 50) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def render(items: list[Item]) -> str:
    lines = []
    names = [_short(it.proposal.filename or "(no name)") for it in items]
    w = max(map(len, names), default=0)
    for n, (it, name) in enumerate(zip(items, names), 1):
        p = it.proposal
        mark = ("⚠" if p.flags else " ") + " " + ("✓" if it.selected else " ")
        rate = "? kbps" if it.bitrate is None else f"{it.bitrate} kbps" + (" VBR" if it.vbr else "")
        line = f"{mark} {n:>3}  {_short(it.src.name):<50} → {name:<{w}}  {rate:<12}"
        if p.flags:
            line += f"  [{'; '.join(p.flags)}]"
        lines.append(line.rstrip())
    warn = sum(1 for it in items if it.proposal.flags)
    lines.append(f"{len(items) - warn} ok · {warn} ⚠")
    return "\n".join(lines)


def parse_selection(text: str, n: int) -> list[int]:
    out = []
    for tok in text.replace(",", " ").split():
        if not tok.isdecimal():
            raise ValueError(f"'{tok}' is not a number")
        k = int(tok)
        if not 1 <= k <= n:
            raise ValueError(f"{k} is out of range (1-{n})")
        out.append(k - 1)
    return out


def main(argv: list[str] | None = None, input_fn=input) -> int:
    ap = argparse.ArgumentParser(prog="mp3sort")
    ap.add_argument("dest", type=Path, help="destination folder")
    ap.add_argument("--source", type=Path, default=None, help="source folder")
    args = ap.parse_args(argv)
    source = args.source or DEFAULT_SOURCE  # lookup en llamada, no en import
    dest = args.dest
    for label, d in (("destination", dest), ("source", source)):
        if not d.is_dir():
            print(f"Error: the {label} folder does not exist: {d}")
            return 2
    s, d = source.resolve(), dest.resolve()
    if s == d or s in d.parents or d in s.parents:
        print("Error: the destination cannot be inside the source (or vice versa)")
        return 2
    items = scan(source, dest)
    if not items:
        print("No mp3 files in source")
        return 0
    while True:
        print(render(items))
        print(HELP)
        try:
            text = input_fn("> ").strip()
        except EOFError:
            text = "q"
        if text.lower() == "q":
            return 0
        if text:
            try:
                idx = parse_selection(text, len(items))
            except ValueError as e:
                print(e)
                continue
            for i in idx:
                it = items[i]
                if not it.selected and it.proposal.filename is None:
                    print(f"{i + 1}: cannot include (no proposed name)")
                else:
                    it.selected = not it.selected
            continue
        moved = left = kept = 0
        for it in items:
            if not it.selected:
                left += 1
                continue
            err = apply_item(it, dest)
            if err is None:
                moved += 1
                print(f"✓ {it.src.name}")
            elif err.startswith(COPIED_NOT_DELETED):
                kept += 1
                print(f"! {it.src.name}: {err}")
            else:
                left += 1
                print(f"✗ {it.src.name}: {err}")
        extra = f" · Copied without deleting original: {kept}" if kept else ""
        print(f"Moved: {moved} · Left in source: {left}{extra}")
        return 0
