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


def test_license_file_is_gpl3():
    text = (Path(__file__).resolve().parent.parent / "LICENSE").read_text()
    assert text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE")
    assert "Version 3, 29 June 2007" in text


def test_collect_licenses_includes_project_and_mutagen(tmp_path):
    from tools.collect_licenses import collect_licenses

    collect_licenses(tmp_path)
    text = (tmp_path / "LICENSE").read_text()
    assert "GNU GENERAL PUBLIC LICENSE" in text and "Version 3" in text
    assert any((tmp_path / "third-party" / "mutagen").iterdir())
    assert (tmp_path / "third-party" / "python" / "LICENSE.txt").exists()
    assert "github.com/rolimat/mp3sort" in (tmp_path / "SOURCE.txt").read_text()
