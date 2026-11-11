import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.report import build_report


def test_build_report_totals_and_flagged_first():
    cases = [
        {"dir": "d", "filename": "Artist - Title.mp3", "artist": "Artist", "title": "Title"},
        {"dir": "d", "filename": "weird.mp3", "artist": None, "title": None},
    ]
    out = build_report(cases)
    lines = out.splitlines()
    assert lines[0].startswith("1 ok · 1 ⚠")
    rows = [l for l in lines if l.startswith("| ") and l[2].isdigit()]
    assert "⚠" in rows[0] or "weird" in rows[0]
    assert "weird.mp3" in rows[0]
