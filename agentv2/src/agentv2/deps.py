"""What every run gets as `ctx.deps`: the bridge, the bus, the method catalog, the episode and the role."""
from __future__ import annotations

from dataclasses import dataclass, field

from .bridge import Bridge
from .bus import Bus
from .catalog import Method
from .episode import Episode
from .events import Event
from .policy import MethodPolicy
from .roles import Role


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

    def emit(self, event: Event) -> None:
        self.bus.emit(event, stream=self.role.stream)


@dataclass
class DirectorDeps(Deps):
    turn: Turn = field(default_factory=Turn)
    relevant_skills: list[str] = field(default_factory=list)
