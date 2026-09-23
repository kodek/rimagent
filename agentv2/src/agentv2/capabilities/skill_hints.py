"""Remind the director of the skills that match its wake and that it has not loaded. Harness SystemReminders puts the
reminder at the tail of a request and never into the history."""
from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai_harness import SystemReminders

from ..deps import DirectorDeps

EVERY = 4


def skill_hint(ctx: RunContext[DirectorDeps]) -> str | None:
    if ctx.run_step > 1 and ctx.run_step % EVERY:
        return None
    missing = [name for name in ctx.deps.relevant_skills if name not in ctx.loaded_capability_ids]
    if not missing:
        return None
    return (f"<system-reminder>\nSkills that match this wake and that you have not loaded: {', '.join(missing)}. "
            "Load each with load_capability before you act on its problem.\n</system-reminder>")


def skill_hints() -> SystemReminders[DirectorDeps]:
    return SystemReminders(dynamic_reminders=[skill_hint])
