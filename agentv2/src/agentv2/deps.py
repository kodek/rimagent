"""What every run gets as `ctx.deps`: the bridge, the bus, the method catalog, the episode and the role."""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

from .bridge import Bridge
from .bus import Bus
from .catalog import Method
from .policy import MethodPolicy
from .roles import Role


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
    """What the director's tools decided in one step, read by the runner after the run."""
    model_speed: int | None = None
    replies: list[str] = field(default_factory=list)


@dataclass
class Deps:
    bridge: Bridge
    bus: Bus
    catalog: list[Method]
    episode: Episode
    role: Role

    @property
    def policy(self) -> MethodPolicy:
        return MethodPolicy(writes=self.role.writes_game, dev=self.episode.sandbox)

    def emit(self, kind: str, data: dict | None = None, *, ephemeral: bool = False) -> None:
        self.bus.emit(kind, {"stream": self.role.stream, **(data or {})}, ephemeral=ephemeral)


@dataclass
class DirectorDeps(Deps):
    turn: Turn = field(default_factory=Turn)
    urgent: collections.deque[str] = field(default_factory=collections.deque)
