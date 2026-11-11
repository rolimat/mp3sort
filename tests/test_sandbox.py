import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "make_sandbox.sh"


def run(root, *args):
    env = {**os.environ, "MP3SORT_SANDBOX_ROOT": str(root)}
    return subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_copies_folders_and_leaves_originals(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    a = tmp_path / "Carpeta Uno"
    b = tmp_path / "otra carpeta"
    for d, name in ((a, "x.mp3"), (b, "y.mp3")):
        d.mkdir()
        (d / name).write_bytes(b"data")
    r = run(root, str(a), str(b))
    assert r.returncode == 0, r.stderr
    assert (root / "sandbox/complete/Carpeta Uno/x.mp3").read_bytes() == b"data"
    assert (root / "sandbox/complete/otra carpeta/y.mp3").exists()
    assert (root / "sandbox/dest").is_dir()
    assert (a / "x.mp3").exists() and (b / "y.mp3").exists()
    assert "mp3sort.py --source sandbox/complete sandbox/dest" in r.stdout


def test_missing_folder_keeps_existing_sandbox(tmp_path):
    root = tmp_path / "repo"
    (root / "sandbox").mkdir(parents=True)
    keep = root / "sandbox" / "keep.txt"
    keep.write_text("x")
    good = tmp_path / "ok"
    good.mkdir()
    r = run(root, str(good), str(tmp_path / "nope"))
    assert r.returncode == 1
    assert keep.exists()
    r = run(root)
    assert r.returncode == 1 and keep.exists()


def _mk(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.mp3").write_bytes(b"1")
    return root, d


def test_sandbox_without_marker_is_kept(tmp_path):
    root, d = _mk(tmp_path)
    (root / "sandbox").mkdir()
    keep = root / "sandbox" / "keep.txt"
    keep.write_text("x")
    r = run(root, str(d))
    assert r.returncode == 1 and keep.exists()


def test_sandbox_with_marker_is_rebuilt(tmp_path):
    root, d = _mk(tmp_path)
    assert run(root, str(d)).returncode == 0
    assert (root / "sandbox/.mp3sort-sandbox").exists()
    (root / "sandbox/old.txt").write_text("x")
    assert run(root, str(d)).returncode == 0
    assert not (root / "sandbox/old.txt").exists()
    assert (root / "sandbox/complete/src/a.mp3").exists()


def test_root_home_or_slash_refused(tmp_path):
    _, d = _mk(tmp_path)
    for bad in (os.path.expanduser("~"), "/"):
        r = run(bad, str(d))
        assert r.returncode == 1


def test_relative_arg_from_other_cwd(tmp_path):
    root, d = _mk(tmp_path)
    env = {**os.environ, "MP3SORT_SANDBOX_ROOT": str(root)}
    r = subprocess.run([str(SCRIPT), "src"], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (root / "sandbox/complete/src/a.mp3").exists()


def test_arg_inside_or_containing_sandbox_refused(tmp_path):
    root, d = _mk(tmp_path)
    assert run(root, str(d)).returncode == 0
    marker = root / "sandbox/.mp3sort-sandbox"
    for arg in (root / "sandbox/complete", root):
        r = run(root, str(arg))
        assert r.returncode == 1 and marker.exists()
