"""Brain passes: the improver runs every few in-game days beside the director, the reflector when a game ends. Both
read the game, edit the brain, and end with a brain commit."""
from __future__ import annotations

import collections
import time
import traceback
from dataclasses import dataclass, field

from pydantic_ai import Agent

from .brain import Brain
from .bus import Bus
from .deps import Deps
from .director import DirectorSession
from .events import BrainChange, Error, ThinkEnd, ThinkStart, ToolCall, ToolResult
from .history import BrainGit, GitError, Scores
from .roles import DIRECTOR
from .running import run_agent
from .tools.turn import Finished


@dataclass
class BrainPasses:
    improver: Agent[Deps, Finished]
    reflector: Agent[Deps, Finished]
    brain: Brain
    git: BrainGit
    scores: Scores
    bus: Bus
    director: DirectorSession
    max_requests: int
    usage_seq: int = field(default=0, init=False)

    async def improve(self, deps: Deps, day: int) -> str:
        episode = deps.episode
        notes = await self.director.notes(episode.colony)
        prompt = (f"# Improvement pass, day {day} of episode {episode.number}\n\n## Your tool use since the last pass (calls, failures)\n"
                  f"{self.usage_stats()}\n\n## Recent step notes\n" + _bullets(notes[-30:])
                  + "\n\n## Earlier passes\n" + _bullets(episode.pass_notes[-5:]) + f"\n\n## Scores\n{self.scores.text(8)}")
        result = await self._run(self.improver, prompt, deps, f"episode {episode.number} day {day}: improvement pass")
        episode.pass_notes.append(f"[improvement pass day {day}] {result}")
        return result

    async def reflect(self, deps: Deps, reason: str, days: int, total: float) -> str:
        episode = deps.episode
        notes = await self.director.notes(episode.colony)
        timeline = "\n".join(f"[{e.get('day', '?')}d {e.get('hour', '?')}h] {e.get('kind')}: {e.get('text', '')}" for e in episode.timeline)[-14_000:]
        prompt = (f"# Episode {episode.number} reflection (seed {episode.seed})\n\nThis game is over ({reason}) after {days} days. Score {total}.\n\n"
                  f"## Timeline\n{timeline}\n\n## Your step notes\n" + _bullets(notes[-40:])
                  + "\n\n## Improvement passes\n" + _bullets(episode.pass_notes)
                  + f"\n\n## What the operator said\n{self.brain.operator.tail(3000)}\n\n## Scores\n{self.scores.text(12)}")
        return await self._run(self.reflector, prompt, deps, f"episode {episode.number} ({episode.seed}): {reason}; score {total}")

    def usage_stats(self) -> str:
        """The director's tool calls and failures since the last pass, from the bus. StepPersistence cannot supply the
        failures: core skips `on_tool_execute_error` for `ToolFailed` (pydantic-ai 2.47, tool_manager.py)."""
        counts, errors = collections.Counter[str](), collections.Counter[str]()
        for e in self.bus.since(self.usage_seq, limit=5000, kinds={ToolCall.KIND, ToolResult.KIND}):
            if e["data"].get("stream") != DIRECTOR.stream:
                continue
            if e["kind"] == ToolCall.KIND:
                counts[e["data"]["name"]] += 1
            elif not e["data"].get("ok"):
                errors[e["data"]["name"]] += 1
        self.usage_seq = self.bus.last_seq
        return "\n".join(f"- {n}: {c}" + (f", {errors[n]} failed" if errors[n] else "") for n, c in counts.most_common(25)) or "(no tool calls)"

    async def commit(self, message: str) -> str | None:
        try:
            sha = await self.git.commit(message)
        except GitError as e:
            self.bus.emit(Error(text=f"brain commit: {e}"))
            return None
        if sha:
            self.bus.emit(BrainChange(kind="git", action="commit", sha=sha))
        return sha

    async def brain_sha(self) -> str:
        try:
            return await self.git.head()
        except GitError as e:
            self.bus.emit(Error(text=f"brain head: {e}"))
            return ""

    async def _run(self, agent: Agent[Deps, Finished], prompt: str, deps: Deps, commit: str) -> str:
        deps.emit(ThinkStart(trigger=commit, step=0, urgent=False, prompt_chars=len(prompt)))
        started, calls = time.monotonic(), 0
        try:
            result = await run_agent(agent, prompt, deps, self.brain, max_requests=self.max_requests, conversation_id=deps.episode.colony)
            notes, calls = result.output.notes, result.usage.tool_calls
        except Exception as e:  # noqa: BLE001 - a failed pass is reported; the game and the episode go on
            notes = f"(pass failed: {type(e).__name__}: {e})"
            self.bus.emit(Error(text=f"{deps.role.name}: {notes}\n{traceback.format_exc(limit=6)}"))
        deps.emit(ThinkEnd(notes=notes, calls=calls, elapsed=round(time.monotonic() - started, 1)))
        await self.commit(commit)
        return notes


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {n}" for n in lines if n) or "(none)"
