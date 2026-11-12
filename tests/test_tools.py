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


def test_collected_licenses_are_text_and_pyobjc_core_has_real_text(tmp_path):
    import sys
    from tools.collect_licenses import collect_licenses

    collect_licenses(tmp_path)
    for f in (tmp_path / "third-party").rglob("*"):
        if f.is_file():
            f.read_text(encoding="utf-8")  # a binary or non-UTF-8 file would raise
    assert not list(tmp_path.rglob("LICENSE-METADATA.txt"))
    if sys.platform == "darwin":
        texts = [f.read_text() for f in (tmp_path / "third-party" / "pyobjc-core").rglob("*") if f.is_file()]
        assert any("Permission is hereby granted" in t for t in texts)


class FakeDist:
    def __init__(self, root, name, files):
        self.metadata, self.version, self._root = {"Name": name}, "1.0", root
        self.files = files
        for f in files:
            p = root / f
            if ".." not in f and not f.startswith("/"):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f"text of {f}")

    def locate_file(self, f):
        return self._root / f


def test_bundled_is_runtime_only():
    from tools.collect_licenses import _bundled

    names = set(_bundled())
    assert {"mutagen", "pywebview", "bottle", "proxy_tools", "typing_extensions"} <= names
    assert not names & {"setuptools", "packaging", "altgraph", "macholib", "pyinstaller-hooks-contrib",
                        "pytest", "pluggy", "iniconfig"}


def test_native_and_override_texts_are_copied(tmp_path):
    from tools.collect_licenses import collect_licenses

    collect_licenses(tmp_path)
    tp = tmp_path / "third-party"
    assert "Apache License" in (tp / "openssl" / "LICENSE.txt").read_text()
    assert "Redistribution and use" in (tp / "mpdecimal" / "COPYRIGHT.txt").read_text()
    assert "Zstandard" in (tp / "zstd" / "LICENSE").read_text()
    assert "Permission to use, copy, modify" in (tp / "xz" / "COPYING.0BSD").read_text()
    assert "Redistribution and use" in (tp / "proxy_tools" / "LICENSE.txt").read_text()


def test_dist_without_license_or_override_fails(tmp_path, monkeypatch):
    import pytest
    import tools.collect_licenses as cl

    d = FakeDist(tmp_path / "sp", "nolic", ["nolic/__init__.py"])
    d.metadata["License"] = "MIT"  # declared licence metadata is not a licence text
    monkeypatch.setattr(cl, "_bundled", lambda: {"nolic": d})
    with pytest.raises(SystemExit, match="nolic"):
        cl.collect_licenses(tmp_path / "out")


def test_license_paths_keep_structure_reject_escape_and_collisions(tmp_path, monkeypatch, capsys):
    import pytest
    import tools.collect_licenses as cl

    assert str(cl._dest("x-1.dist-info/licenses/vendor/LICENSE")) == "licenses/vendor/LICENSE"
    assert str(cl._dest("pkg/sub/COPYING")) == "pkg/sub/COPYING"
    assert cl._dest("../../share/LICENSE") is None and cl._dest("/abs/LICENSE") is None
    d = FakeDist(tmp_path / "sp", "esc", ["esc-1.dist-info/LICENSE", "../../share/LICENSE"])
    monkeypatch.setattr(cl, "_bundled", lambda: {"esc": d})
    cl.collect_licenses(tmp_path / "out")
    assert (tmp_path / "out/third-party/esc/LICENSE").exists()
    assert "unsafe license path ../../share/LICENSE" in capsys.readouterr().err
    d = FakeDist(tmp_path / "sp2", "dup", ["dup-1.dist-info/LICENSE", "LICENSE"])
    monkeypatch.setattr(cl, "_bundled", lambda: {"dup": d})
    with pytest.raises(SystemExit, match="map to"):
        cl.collect_licenses(tmp_path / "out2")


def test_python_license_found_in_base_prefix(tmp_path, monkeypatch):
    import pytest
    import tools.collect_licenses as cl

    empty, base = tmp_path / "stdlib", tmp_path / "base"
    empty.mkdir(); base.mkdir()
    monkeypatch.setattr(cl.sysconfig, "get_paths", lambda: {"stdlib": str(empty)})
    monkeypatch.setattr(cl.sys, "base_prefix", str(base))
    with pytest.raises(SystemExit, match="Python license not found"):
        cl._python_license()
    (base / "LICENSE.txt").write_text("PSF")
    assert cl._python_license() == base / "LICENSE.txt"


def test_source_offer_lists_tag_and_versions(tmp_path):
    from importlib import metadata
    from tools.collect_licenses import collect_licenses

    collect_licenses(tmp_path, "1.2.3")
    t = (tmp_path / "SOURCE.txt").read_text()
    assert "https://github.com/rolimat/mp3sort/tree/v1.2.3" in t
    v = metadata.version("mutagen")
    assert f"mutagen {v}: https://pypi.org/project/mutagen/{v}/#files" in t
    assert "The complete corresponding source code is available at the URLs above." in t
    collect_licenses(tmp_path / "dev")
    assert "/tree/main" in (tmp_path / "dev" / "SOURCE.txt").read_text()


def test_check_bundle_fails_on_unknown_native(tmp_path):
    from tools.collect_licenses import unknown_native

    c = tmp_path / "x.app" / "Contents"
    fw = c / "Frameworks"
    (c / "Resources/licenses/third-party/openssl").mkdir(parents=True)
    (c / "Resources/licenses/third-party/python").mkdir()
    (fw / "python3__dot__14/lib-dynload").mkdir(parents=True)
    (fw / "python3__dot__14/lib-dynload/_ssl.cpython-314-darwin.so").write_bytes(b"\xcf\xfa\xed\xfe")
    (fw / "libssl.3.dylib").write_bytes(b"\xcf\xfa\xed\xfe")
    (fw / "Python.framework").mkdir()
    (c / "Resources/libssl.3.dylib").symlink_to(fw / "libssl.3.dylib")
    (fw / "data.bin").write_bytes(b"nope")
    assert unknown_native(tmp_path / "x.app") == []
    (fw / "libfoo.1.dylib").write_bytes(b"\xcf\xfa\xed\xfe")
    (fw / "helper").write_bytes(b"\xca\xfe\xba\xbe")
    (fw / "mystery").mkdir()
    (fw / "mystery/_x.cpython-314-darwin.so").write_bytes(b"\xcf\xfa\xed\xfe")
    assert sorted(unknown_native(tmp_path / "x.app")) == ["Frameworks/helper", "Frameworks/libfoo.1.dylib",
                                                          "Frameworks/mystery/_x.cpython-314-darwin.so"]


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
