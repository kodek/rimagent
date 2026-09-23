"""The episode: identity, tallies, timeline and pass notes, saved to runs/episode.json so a restart keeps them."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from .bridge import GameStatus
from .world import Tracked, View, default_tracked

TIMELINE_KINDS = {"day", "colonist_died", "colonist_downed", "incident", "hostile_group", "hostile_group_gone", "letter", "mental_break",
                  "research_finished", "building_lost", "colonist_joined", "colonist_left", "quest"}


class Checkpoint(BaseModel):
    """The episode when the game was last saved: loading that save rewinds the episode to it."""

    tick: int
    day: int
    hour: int
    deaths: int
    raids: int
    timeline: int


class Episode(BaseModel):
    number: int = Field(default=0, validation_alias=AliasChoices("number", "episode"))
    seed: str = ""
    start_day: int = 0
    sandbox: bool = False
    deaths: int = 0
    raids: int = 0
    last_improve_day: int = 0
    ended: bool = False
    assisted: bool = False
    checkpoint: Checkpoint | None = None
    view: View | None = None
    tracked: dict[str, Tracked] = Field(default_factory=default_tracked)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    pass_notes: list[str] = Field(default_factory=list)

    @property
    def colony(self) -> str:
        return f"episode-{self.number:03d}-{re.sub(r'[^A-Za-z0-9_-]', '_', self.seed) or 'unseeded'}"

    @property
    def unfinished(self) -> bool:
        return bool(self.seed) and not self.ended

    def tally(self, events: list[dict[str, Any]]) -> None:
        for e in events:
            self.deaths += e.get("kind") == "colonist_died"
            self.raids += e.get("kind") == "hostile_group"
        self.timeline += [e for e in events if e.get("kind") in TIMELINE_KINDS]

    def saved(self, st: GameStatus) -> None:
        self.checkpoint = Checkpoint(tick=st.tick, day=st.day, hour=st.hour, deaths=self.deaths, raids=self.raids, timeline=len(self.timeline))

    def rewind(self, st: GameStatus) -> Checkpoint:
        """The save of `checkpoint` was loaded: forget what happened after it."""
        cp = self.checkpoint
        assert cp is not None, "rewind needs a checkpoint"
        self.deaths, self.raids, self.view = cp.deaths, cp.raids, None
        del self.timeline[cp.timeline:]
        self.timeline.append({"kind": "reloaded", "text": f"the game crashed; loaded the save of day {cp.day} {cp.hour}h", "day": st.day, "hour": st.hour})
        return cp


class EpisodeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Episode | None:
        return Episode.model_validate_json(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    def save(self, episode: Episode) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(episode.model_dump_json(), encoding="utf-8")
