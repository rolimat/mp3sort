import functools
import importlib.util
import tempfile
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TIT2, TPE1

REAL_AUDIO = Path(__file__).parent / "fixtures" / "audio" / "a1.mp3"
_tmp = tempfile.TemporaryDirectory(prefix="mp3sort-audio-")  # removed at interpreter exit


@functools.lru_cache(maxsize=None)
def audio_path() -> Path:
    """Real local fixture if present (gitignored), else a synthetic CBR mp3 with a small ID3 tag."""
    if REAL_AUDIO.exists():
        return REAL_AUDIO
    p = Path(_tmp.name) / "a1.mp3"
    p.write_bytes((b"\xff\xfb\x90\x00" + b"\x00" * 413) * 600)
    t = ID3()
    t.add(TPE1(encoding=3, text="Lumen"))
    t.add(TIT2(encoding=3, text="Prisma"))
    t.save(p)
    return p


@pytest.fixture(scope="session")
def audio() -> Path:
    return audio_path()


@pytest.fixture(autouse=True)
def _never_read_real_source(monkeypatch):
    # Keep tests from reading the real source folder.
    # No saved settings: the CLI has no default source unless a test saves one.
    if importlib.util.find_spec("sorter.gui_model") is not None:
        import sorter.gui_model
        monkeypatch.setattr(sorter.gui_model, "SETTINGS_PATH",
                            Path("/nonexistent-mp3sort-settings/settings.json"))
