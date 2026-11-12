from sorter.folders import check_folders


def test_check_folders(tmp_path):
    s, d = tmp_path / "s", tmp_path / "d"
    assert check_folders(s, d) == f"Error: the destination folder does not exist: {d}"
    d.mkdir()
    assert check_folders(s, d) == f"Error: the source folder does not exist: {s}"
    s.mkdir()
    assert check_folders(s, d) is None
    msg = "Error: the destination cannot be inside the source (or vice versa)"
    assert check_folders(s, s) == msg
    (s / "in").mkdir()
    assert check_folders(s, s / "in") == msg
    assert check_folders(s / "in", s) == msg
