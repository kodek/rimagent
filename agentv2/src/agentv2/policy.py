"""Which RimBridge methods a caller may use: the director, a brain pass, or a watcher."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import HIDDEN, is_read_only


@dataclass(frozen=True)
class MethodPolicy:
    writes: bool
    dev: bool = False
    read_only_hint: str = "this pass may only read it"

    def refusal(self, method: str) -> str | None:
        if method in HIDDEN:
            return f"{method} is reserved for the runner"
        if method.startswith("dev.") and not self.dev:
            return "dev.* methods exist only in sandbox episodes"
        if not self.writes and not is_read_only(method):
            return f"{method} changes the game; {self.read_only_hint}"
        return None


WATCHER_POLICY = MethodPolicy(writes=False, read_only_hint="return an action instead")
