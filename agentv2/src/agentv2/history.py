"""Brain history: episode scores, and the brain directory in git (one commit per pass and per episode)."""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

from .brain import BrainLayout
from .deps import Deps
from .events import BrainChange


def score(days: int, colonists: int, deaths: int, wealth: float, mood: float, research: int, raids: int) -> float:
    return round(days * 10 + colonists * 60 + max(0.0, wealth - 14_000) / 400 + mood * 0.5 + research * 8 + raids * 40 - deaths * 120, 1)


class Scores:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, row: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.time(), **row}) + "\n")

    def history(self, last: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()][-last:]

    def text(self, last: int = 12) -> str:
        rows = self.history(last)
        if not rows:
            return "(no episodes scored yet)"
        head = "episode | seed | days | colonists | deaths | wealth | score | assisted | brain | ended"
        return "\n".join([head] + [
            f"{r.get('episode')} | {r.get('seed')} | {r.get('days')} | {r.get('colonists')} | {r.get('deaths')} | {r.get('wealth')} | "
            f"{r.get('score')} | {'yes' if r.get('assisted') else 'no'} | {str(r.get('brain_sha', ''))[:7]} | {r.get('ended')}" for r in rows])


class GitError(Exception):
    pass


class BrainGit:
    def __init__(self, brain: Path) -> None:
        self.brain = brain

    async def _git(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec("git", "-C", str(self.brain), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise GitError((err or out).decode().strip() or f"git {args[0]} failed")
        return out.decode().strip()

    async def commit(self, message: str) -> str | None:
        await self._git("add", "-A", ".")
        if not await self._git("status", "--porcelain", "--", "."):
            return None
        await self._git("commit", "-q", "-m", message, "--", ".")
        return await self.head()

    async def head(self) -> str:
        return await self._git("rev-parse", "HEAD")

    async def log(self, n: int = 15) -> str:
        return await self._git("log", f"-{n}", "--date=short", "--pretty=%h %ad %s", "--", ".")

    async def diff(self, sha: str) -> str:
        return (await self._git("show", "--stat", "--patch", "--no-color", sha, "--", "."))[:20_000]

    async def revert_to(self, sha: str) -> str | None:
        await self._git("checkout", sha, "--", ".")
        return await self.commit(f"brain: revert to {sha[:7]}")


@dataclass
class BrainTools(AbstractCapability[Deps]):
    """Scores, brain history, and deleting skills and watchers (the brain FileSystem has no delete)."""

    scores: Scores
    git: BrainGit
    layout: BrainLayout

    def get_toolset(self) -> AgentToolset[Deps]:
        toolset = FunctionToolset[Deps](id="brain_history")
        git, scores, layout = self.git, self.scores, self.layout

        @toolset.tool_plain
        def score_history(last: int = 12) -> str:
            """Past episodes: score, seed, days, deaths, whether assisted, and the brain commit each ran on."""
            return scores.text(last)

        @toolset.tool_plain
        async def brain_log(n: int = 15) -> str:
            """The git log of the brain directory, one commit per improvement pass and per episode."""
            return await _git_call(git.log(n))

        @toolset.tool_plain
        async def brain_diff(sha: str) -> str:
            """What changed in the brain in one commit."""
            return await _git_call(git.diff(sha))

        @toolset.tool
        async def brain_revert(ctx: RunContext[Deps], sha: str) -> str:
            """Restore the whole brain to an earlier commit (when a change made play worse). History is kept."""
            new = await _git_call(git.revert_to(sha))
            ctx.deps.emit(BrainChange(kind="git", action="revert", sha=sha))
            return f"brain restored to {sha[:7]}" + (f" (commit {new[:7]})" if new else " (it already matched)")

        @toolset.tool
        def delete_skill(ctx: RunContext[Deps], name: str) -> str:
            """Delete a skill (its folder under skills/). Git keeps the old version."""
            return _delete(ctx, layout.skill, "skill", name)

        @toolset.tool
        def delete_watcher(ctx: RunContext[Deps], name: str) -> str:
            """Delete a watcher (watchers/<name>.py). Git keeps the old version."""
            return _delete(ctx, layout.watcher, "watcher", name)

        return toolset


async def _git_call(coro: Any) -> Any:
    try:
        return await coro
    except GitError as e:
        raise ToolFailed(str(e)) from e


def _delete(ctx: RunContext[Deps], locate: Callable[[str], Path], kind: str, name: str) -> str:
    try:
        path = locate(name)
    except ValueError:
        path = None
    if path is None or not path.is_file():
        raise ToolFailed(f"no {kind} named {name!r}")
    path.unlink()
    if kind == "skill" and not any(path.parent.iterdir()):
        path.parent.rmdir()
    ctx.deps.emit(BrainChange(kind=kind, name=name, action="delete"))
    return f"deleted {kind} {name}"
