import csv
from pathlib import Path

import pytest
from sorter.clean import propose

FIX = Path(__file__).parent / "fixtures"
ROWS = []
for _p in (FIX / "golden.csv", FIX / "local" / "golden.csv"):  # local/ is gitignored, optional
    if _p.exists():
        with open(_p, newline="") as f:
            ROWS += list(csv.DictReader(f))


@pytest.mark.parametrize("r", ROWS, ids=[r["filename"] for r in ROWS])
def test_golden(r):
    p = propose(r["filename"], r["tag_artist"] or None, r["tag_title"] or None)
    assert p.filename == (r["expected_filename"] or None)
    assert bool(p.flags) == (r["expected_flagged"] == "1")


def test_tags_keep_original_chars():
    p = propose("17-42 - Neon Echoes (Original Mix).mp3", "17:42", "Neon Echoes (Original Mix)")
    assert (p.artist, p.title) == ("17:42", "Neon Echoes (Original Mix)")


def test_empty_norm_non_latin_is_flagged():
    assert propose("Foo - Bar.mp3", "Клубная", "Bar").flags


def test_empty_norm_equal_not_flagged():
    assert not propose("X - Bar.mp3", "X", "Bar").flags


def test_group_missing_in_filename_flag():
    p = propose("02 - Kiro Vane, Mira Dune - Quiet Harbor.mp3",
                "Kiro Vane & Mira Dune", "Quiet Harbor (Original Mix)")
    assert p.title == "Quiet Harbor (Original Mix)"
    assert p.flags == ["falta '(Original Mix)' en el nombre de fichero"]


def test_norm_special_letters():
    p = propose("01-solenox_and_ravi_(ita)-alchemy_(original_mix).mp3",
                "Solenøx, RAVI (ITA)", "Alchemy (Original Mix)")
    assert not p.flags


def test_two_different_non_latin_artists_flagged():
    assert propose("Другая - Bar.mp3", "Клубная", "Bar").flags
