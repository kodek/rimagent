"""Test bootstrap: point RIMAGENT_ROOT at a throwaway directory BEFORE any rimagent module is imported.

rimagent.paths resolves ROOT from the env var at import time and creates brain/ subdirs under it, so the
env var must be set before the first `import rimagent.*` anywhere in the test session. conftest.py is
imported by pytest before any test module is collected, so doing it at module top level is sufficient;
pytest_configure repeats it defensively.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="rimagent-tests-"))
for _sub in ("brain/skills", "brain/tools", "brain/watchers", "brain/memory", "knowledge/wiki", "runs"):
    (_TMP_ROOT / _sub).mkdir(parents=True, exist_ok=True)
os.environ["RIMAGENT_ROOT"] = str(_TMP_ROOT)

assert not any(m == "rimagent" or m.startswith("rimagent.") for m in sys.modules), "rimagent imported before conftest set RIMAGENT_ROOT"


def pytest_configure(config):  # noqa: ARG001
    os.environ["RIMAGENT_ROOT"] = str(_TMP_ROOT)


@pytest.fixture(scope="session", autouse=True)
def _isolated_root():
    """Sanity guard: every rimagent path must live under the temp root, never the real repo."""
    from rimagent import paths

    assert paths.ROOT == _TMP_ROOT, f"paths.ROOT={paths.ROOT} is not the temp root {_TMP_ROOT}"
    assert str(paths.BRAIN).startswith(str(_TMP_ROOT))
    yield


@pytest.fixture
def tmp_root() -> Path:
    return _TMP_ROOT


@pytest.fixture
def clean_brain():
    """Empty brain/skills, tools, watchers, memory and scores before (and after) a test."""
    from rimagent import paths

    def _wipe():
        for d in (paths.SKILLS, paths.TOOLS, paths.WATCHERS, paths.MEMORY):
            for f in d.glob("*"):
                if f.is_file():
                    f.unlink()
        if paths.SCORES.exists():
            paths.SCORES.unlink()

    _wipe()
    yield
    _wipe()
