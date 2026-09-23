from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from pydantic_ai import models  # noqa: E402

from agentv2 import config  # noqa: E402
from agentv2.bridge import Bridge  # noqa: E402
from agentv2.bus import Bus  # noqa: E402
from agentv2.fakegame import FakeGame  # noqa: E402

models.ALLOW_MODEL_REQUESTS = False
SEED_BRAIN = Path(__file__).resolve().parents[1] / "brain"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    shutil.copytree(SEED_BRAIN, tmp_path / "brain", ignore=shutil.ignore_patterns(".memory-store.sqlite3*", "__pycache__"))
    (tmp_path / "config.yaml").write_text("play:\n  max_days: 2\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def settings(root: Path) -> config.Settings:
    return config.load(root)


@pytest.fixture
def game() -> FakeGame:
    return FakeGame()


@pytest.fixture
async def bridge(game: FakeGame):
    b = Bridge("http://fakegame", transport=game.transport())
    yield b
    await b.aclose()


@pytest.fixture
def bus() -> Bus:
    return Bus()
