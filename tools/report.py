"""Genera report/report.md aplicando propose() a tests/fixtures/local/cases.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sorter.clean import propose  # noqa: E402


def cell(s):
    return (s or "").replace("|", "\\|")


def build_report(cases: list[dict]) -> str:
    rows = []
    for c in cases:
        p = propose(c["filename"], c.get("artist"), c.get("title"))
        rows.append((bool(p.flags), c, p))
    rows.sort(key=lambda r: not r[0])  # estable: ⚠ primero
    bad = sum(r[0] for r in rows)
    out = [f"{len(rows) - bad} ok · {bad} ⚠", "",
           "| # | fichero original | tag artista | tag título | propuesto | ⚠ motivo |",
           "|---|---|---|---|---|---|"]
    for i, (flag, c, p) in enumerate(rows, 1):
        motivo = ("⚠ " + "; ".join(p.flags)) if flag else ""
        out.append("| " + " | ".join(cell(x) for x in (
            str(i), c["filename"], c.get("artist"), c.get("title"), p.filename, motivo)) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    cases = json.loads((ROOT / "tests" / "fixtures" / "local" / "cases.json").read_text(encoding="utf-8"))
    dest = ROOT / "report" / "report.md"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(build_report(cases), encoding="utf-8")
    print(dest)
