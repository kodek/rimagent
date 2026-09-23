"""What the dashboard reads about the brain: skills, watchers, capabilities, memory files, git history and scores."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..brain import Brain
from ..episode import Episode
from ..history import BrainGit, Scores
from ..watchers import Watchers


@dataclass
class BrainView:
    brain: Brain
    watchers: Watchers
    git: BrainGit
    scores: Scores
    episode: Callable[[], Episode]

    def tree(self) -> dict[str, Any]:
        episode, layout = self.episode(), self.brain.layout
        return {
            "skills": [{"name": s.name, "description": s.description, "chars": s.chars, "error": s.error} for s in self.brain.skills.infos()],
            "watchers": self.watchers.listing(),
            "capabilities": self.brain.authored(),
            "colony": episode.colony if episode.seed else None,
            "memory": {"doctrine": _chars(layout.doctrine), "notebook": _chars(layout.notebook(episode.colony)),
                       "journal": _chars(layout.journal()), "operator": _chars(layout.operator_log)},
        }

    def file(self, kind: str, name: str | None) -> Path:
        """Raises ValueError for an unknown kind or a bad name."""
        layout = self.brain.layout
        fixed = {"doctrine": layout.doctrine, "notebook": layout.notebook(self.episode().colony), "journal": layout.journal(),
                 "operator": layout.operator_log}
        if kind in fixed:
            return fixed[kind]
        named = {"skill": layout.skill, "watcher": layout.watcher, "capability": layout.capability}
        if kind not in named:
            raise ValueError(f"unknown kind {kind!r}")
        return named[kind](name or "")

    async def log(self, n: int) -> str:
        return await self.git.log(n)

    async def diff(self, sha: str) -> str:
        return await self.git.diff(sha)

    def score_rows(self, last: int) -> list[dict[str, Any]]:
        return self.scores.history(last)


def _chars(path: Path) -> int | None:
    return len(path.read_text(encoding="utf-8")) if path.is_file() else None
