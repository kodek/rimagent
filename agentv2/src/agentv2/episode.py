"""The episode: identity, tallies, timeline and pass notes, saved to runs/episode.json so a restart keeps them."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

TIMELINE_KINDS = {"day", "colonist_died", "colonist_downed", "incident", "hostile_group", "hostile_group_gone", "letter", "mental_break",
                  "research_finished", "building_lost", "colonist_joined", "colonist_left", "quest"}


class Episode(BaseModel):
    number: int = Field(default=0, validation_alias=AliasChoices("number", "episode"))
    seed: str = ""
    start_day: int = 0
    sandbox: bool = False
    deaths: int = 0
    raids: int = 0
    last_improve_day: int = 0
    ended: bool = False
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    pass_notes: list[str] = Field(default_factory=list)

    @property
    def colony(self) -> str:
        return f"episode-{self.number:03d}-{re.sub(r'[^A-Za-z0-9_-]', '_', self.seed) or 'unseeded'}"

    def tally(self, events: list[dict[str, Any]]) -> None:
        for e in events:
            self.deaths += e.get("kind") == "colonist_died"
            self.raids += e.get("kind") == "hostile_group"
        self.timeline += [e for e in events if e.get("kind") in TIMELINE_KINDS]


class EpisodeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Episode | None:
        return Episode.model_validate_json(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    def save(self, episode: Episode) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(episode.model_dump_json(), encoding="utf-8")
