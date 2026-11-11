import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _never_read_real_source(monkeypatch):
    # Evita que un test lea el origen real; solo actúa cuando sorter.cli exista.
    if importlib.util.find_spec("sorter.cli") is not None:
        import sorter.cli
        monkeypatch.setattr(sorter.cli, "DEFAULT_SOURCE", Path("/nonexistent-mp3sort-source"))
