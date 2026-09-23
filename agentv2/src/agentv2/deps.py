"""What every run gets as `ctx.deps`: the bridge, the bus, settings, the method catalog and the episode."""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Literal

from .bridge import Bridge
from .bus import Bus
from .catalog import Method
from .config import Settings

Stream = Literal["play", "improve", "reflect"]


@dataclass
class Episode:
    number: int = 0
    seed: str = ""
    start_day: int = 0
    sandbox: bool = False

    @property
    def colony(self) -> str:
        return f"episode-{self.number:03d}-{re.sub(r'[^A-Za-z0-9_-]', '_', self.seed) or 'unseeded'}"


@dataclass
class Turn:
    """What the tools of one think step decided, read by the runner after the run."""
    model_speed: int | None = None
    replies: list[str] = field(default_factory=list)


@dataclass
class Deps:
    bridge: Bridge
    bus: Bus
    settings: Settings
    catalog: list[Method]
    episode: Episode
    stream: Stream = "play"
    urgent: collections.deque[str] = field(default_factory=collections.deque)
    turn: Turn = field(default_factory=Turn)

    def fork(self, stream: Stream) -> Deps:
        return Deps(bridge=self.bridge, bus=self.bus, settings=self.settings, catalog=self.catalog, episode=self.episode, stream=stream)

    def emit(self, kind: str, data: dict | None = None, *, ephemeral: bool = False) -> None:
        self.bus.emit(kind, {"stream": self.stream, **(data or {})}, ephemeral=ephemeral)
