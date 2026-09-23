"""What the operator switches while the agent runs. The loaded settings stay unchanged."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeFlags:
    danger_think_speed: int
    steward: bool
    paused: bool = False
    sandbox: bool = False
    stop: bool = False
