"""The director's intent for the fast loop, like a commander's intent: the purpose, the ranked priorities, the rules the
loop must never break, what to report up, and guidance per policy domain. Every Jev request carries the part its policy
needs. A directive expires, so the loop does not act for long on intent made for an old game state."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

TICKS_PER_HOUR = 2500


class Priority(BaseModel):
    name: str
    statement: str = Field(description="One literal, checkable sentence, e.g. 'Keep more than 5 days of meals for all colonists.'")


class Directive(BaseModel):
    version: int
    base_tick: int
    expires_tick: int
    purpose: str
    priorities: list[Priority] = Field(default_factory=list)
    never: list[str] = Field(default_factory=list)
    report_when: list[str] = Field(default_factory=list)
    guidance: dict[str, str] = Field(default_factory=dict)

    def expired(self, tick: int) -> bool:
        return tick >= self.expires_tick

    def brief(self, domain: str) -> dict[str, Any]:
        """What a Jev request about `domain` carries: literal statements only, no numbers to compare."""
        out: dict[str, Any] = {"purpose": self.purpose, "priorities_in_order": [f"{p.name}: {p.statement}" for p in self.priorities]}
        if self.never:
            out["never"] = self.never
        if self.report_when:
            out["report_when"] = self.report_when
        if domain in self.guidance:
            out["guidance"] = self.guidance[domain]
        return out

    def line(self) -> str:
        day, hour = divmod(self.expires_tick // TICKS_PER_HOUR, 24)
        return f"v{self.version}: {self.purpose} (expires day {day} {hour}h)"
