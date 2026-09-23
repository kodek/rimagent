"""What the operator switches while the agent runs. The loaded settings stay unchanged."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeFlags:
    danger_think_speed: int
    steward: bool
    orders_off: set[str] = field(default_factory=set)
    paused: bool = False
    sandbox: bool = False
    stop: bool = False
