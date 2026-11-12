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


def test_collected_licenses_are_text_and_pyobjc_core_uses_metadata(tmp_path):
    import sys
    from tools.collect_licenses import collect_licenses

    collect_licenses(tmp_path)
    for f in (tmp_path / "third-party").rglob("*"):
        if f.is_file():
            f.read_text(encoding="utf-8")  # a binary or non-UTF-8 file would raise
    if sys.platform == "darwin":
        assert (tmp_path / "third-party" / "pyobjc-core" / "LICENSE-METADATA.txt").exists()


def test_license_regex_rejects_binaries_and_keeps_nested_paths():
    from tools.collect_licenses import LICENSE_RE

    assert LICENSE_RE.search("PyObjCTest/copying.cpython-314-darwin.so") is None
    assert LICENSE_RE.search("x.dist-info/licenses/vendor/LICENSE.txt")
    assert LICENSE_RE.search("x.dist-info/COPYING")


def test_version_from_tag():
    import subprocess
    import pytest
    from tools.release_version import version_from_tag

    assert version_from_tag("v1.0.0") == "1.0.0"
    assert version_from_tag("v12.3.45") == "12.3.45"
    for bad in ("v1.0", "1.0.0", "v1.0.0-rc1", ""):
        with pytest.raises(ValueError):
            version_from_tag(bad)
    script = Path(__file__).resolve().parent.parent / "tools" / "release_version.py"
    r = subprocess.run([sys.executable, str(script), "v1.0"], capture_output=True, text=True)
    assert r.returncode == 2 and "invalid tag: v1.0" in r.stderr
    r = subprocess.run([sys.executable, str(script), "v1.2.3"], capture_output=True, text=True)
    assert r.stdout.strip() == "1.2.3"


def test_release_workflow():
    import re

    wf = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"
    assert wf.exists()
    t = wf.read_text(encoding="utf-8")
    for needle in ('tags: ["v*.*.*"]', "pull_request:", "macos-latest", 'python-version: "3.14"',
                   "pytest -q", "tools/build_app.sh", "gh release create"):
        assert needle in t, needle
    assert "--clobber" not in t and "--draft" not in t
    assert set(re.findall(r"secrets\.\w+", t)) == {"secrets.GITHUB_TOKEN"}
    assert t.count("contents: write") == 1
    assert re.search(r"^permissions:\n  contents: read$", t, re.M)
    # event data must not be interpolated into scripts
    assert "${{ github.ref_name }}" not in t
