"""The brain: what the agent authors and keeps between games, exposed through Pydantic AI Harness capabilities.

brain/
  AGENTS.md                 doctrine, loaded into every run by RepoContext; the agent may edit it
  skills/<name>/SKILL.md    Agent Skills, loaded on demand (Skills + load_capability)
  watchers/<name>.py        reflexes run in the Monty sandbox without the model (see watchers.py)
  capabilities/             agent-authored capabilities (CapabilityCreation), active from the next step
  memory/                   Memory FileStore: a notebook per colony, and the cross-game journal
  operator.md               what the human operator said (read-only for the agent)
  scores.jsonl              one row per episode
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai_harness import CapabilityCreation, Memory, RepoContext, Skills
from pydantic_ai_harness.capability_creation import CapabilityStore
from pydantic_ai_harness.memory import FileStore

from .capabilities.files import NamedFileSystem
from .deps import Deps

AUTHORING_GUIDE = '''You can give yourself new tools and hooks with `author_capability(name, code)`. The code defines exactly one
subclass of `pydantic_ai.capabilities.AbstractCapability` that constructs with no arguments. It is validated now and becomes
active at your next think step. Its tools appear with the prefix `my_`. `ctx.deps.bridge.call(method, params)` calls RimBridge
(dotted method names, as in the rw_* descriptions). Example:

```python
from dataclasses import dataclass
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

tools = FunctionToolset()

@tools.tool
async def colony_brief(ctx: RunContext) -> dict:
    """The numbers I read at the start of every step, in one call."""
    s = await ctx.deps.bridge.call("state.summary")
    return {k: s.get(k) for k in ("day", "food_days", "mood_avg", "wealth")}

@dataclass
class ColonyBrief(AbstractCapability):
    def get_toolset(self):
        return tools
```

Put knowledge in a skill, reflexes that must run without you in a watcher, and a reusable multi-call procedure in a capability.'''

BRAIN_GUIDE = '''brain_* tools edit your brain directory: `AGENTS.md` (your doctrine, loaded at the start of every step),
`skills/<name>/SKILL.md` (one folder per skill: YAML frontmatter with `name` equal to the folder name and a one-line
`description` of when to load it, then the Markdown body; create the folder first) and `watchers/<name>.py`. A new or edited
skill is in the catalog from your next step. Keep skills concrete: triggers, steps, numbers, pitfalls; edit an existing skill
before you add a near-duplicate.'''

KNOWLEDGE_GUIDE = '''kb_* tools read the offline RimWorld knowledge base: `wiki/<Page>.md` (the RimWorld wiki) and `source-1.6/**/*.cs`
(the decompiled game source). Use kb_grep to search, kb_find_files for names, kb_read_file to read.'''


@dataclass(frozen=True)
class RunCapabilities:
    skills: list[AbstractCapability[Any]]
    authored: list[AbstractCapability[Any]]
    errors: dict[str, str]


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    chars: int
    error: str | None = None


class Brain:
    def __init__(self, root: Path, knowledge: Path | None = None) -> None:
        self.root = root
        self.knowledge = knowledge
        self.skills_dir = root / "skills"
        self.watchers_dir = root / "watchers"
        self.capabilities_dir = root / "capabilities"
        self.memory_dir = root / "memory"
        self.doctrine = root / "AGENTS.md"
        self.operator_log = root / "operator.md"
        self.scores = root / "scores.jsonl"
        for d in (self.skills_dir, self.watchers_dir, self.capabilities_dir, self.memory_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.creation = CapabilityCreation(directory=self.capabilities_dir, guidance=AUTHORING_GUIDE)

    @property
    def store(self) -> CapabilityStore:
        return self.creation.store

    def capabilities(self, *, write: bool = True) -> list[AbstractCapability[Deps]]:
        """The brain capabilities every agent carries. The knowledge base is included when it exists."""
        caps: list[AbstractCapability[Deps]] = [
            RepoContext(workspace_dir=self.root, home_dir=self.root, expose_inventory_tool=False),
            self.filesystem(write=write),
            self.notebook(),
            self.journal(),
        ]
        if write:
            caps.append(self.creation)
        if self.knowledge and self.knowledge.is_dir():
            caps.append(NamedFileSystem(root_dir=self.knowledge, tools=["read_file", "list_directory", "find_files", "grep"],
                                        max_read_lines=400, prefix="kb", id="knowledge_files"))
        return caps

    def filesystem(self, *, write: bool = True) -> AbstractCapability[Deps]:
        tools = ["read_file", "list_directory", "find_files", "search_files"]
        if write:
            tools += ["write_file", "edit_file", "create_directory"]
        return NamedFileSystem(
            root_dir=self.root,
            denied_patterns=["memory", "memory/*", ".git*", "*/__pycache__/*"],
            protected_patterns=["scores.jsonl", "operator.md", "capabilities", "capabilities/*", ".gitignore"],
            tools=tools,
            content_hashes=False,
            prefix="brain",
            id="brain_files",
        )

    def notebook(self) -> AbstractCapability[Deps]:
        return Memory(
            FileStore(self.memory_dir),
            namespace=_colony,
            heading="Colony notebook (this game only)",
            id="notebook",
        ).prefix_tools("notebook")

    def journal(self) -> AbstractCapability[Deps]:
        return Memory(
            FileStore(self.memory_dir),
            agent_name="journal",
            heading="Journal (durable lessons across games)",
            max_lines=120,
            id="journal",
        ).prefix_tools("journal")

    def guides(self) -> str:
        parts = [BRAIN_GUIDE]
        if self.knowledge and self.knowledge.is_dir():
            parts.append(KNOWLEDGE_GUIDE)
        return "\n\n".join(parts)

    def run_capabilities(self) -> RunCapabilities:
        """Per-run capabilities, re-read every step: the skill catalog and the agent's own capabilities, with their errors."""
        infos = self.skills()
        good = [s.name for s in infos if not s.error]
        errors = {f"skill {s.name}": s.error for s in infos if s.error}
        errors |= {f"capability {r.name}": r.last_error for r in self.store.list_all() if r.last_error}
        return RunCapabilities(
            skills=[Skills(self.skills_dir, include=good)] if good else [],
            authored=[c.prefix_tools("my") for c in self.store.load_active()],
            errors=errors,
        )

    def skills(self) -> list[SkillInfo]:
        out = []
        for d in sorted(p for p in self.skills_dir.iterdir() if p.is_dir()):
            path = d / "SKILL.md"
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            try:
                Skills(self.skills_dir, include=[d.name])
            except Exception as e:  # noqa: BLE001 - an agent-written skill must not break the others; the error is reported to it
                out.append(SkillInfo(d.name, "", len(text), f"{type(e).__name__}: {e}"))
                continue
            out.append(SkillInfo(d.name, _description(text), len(text)))
        return out

    def record_operator(self, stamp: str, text: str) -> None:
        with self.operator_log.open("a", encoding="utf-8") as fh:
            if fh.tell() == 0:
                fh.write("# What the human operator said\n")
            fh.write(f"\n- [{stamp}] {text.strip()}\n")

    def memory_file(self, which: str, colony: str) -> Path:
        return self.memory_dir / "journal" / "MEMORY.md" if which == "journal" else self.memory_dir / colony / "main" / "MEMORY.md"

    def authored(self) -> list[dict[str, Any]]:
        return [json.loads(r.model_dump_json()) for r in self.store.list_all()]


def _colony(ctx: RunContext[Deps]) -> str:
    return ctx.deps.episode.colony


def _description(skill_text: str) -> str:
    for line in skill_text.splitlines()[1:]:
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
        if line.strip() == "---":
            break
    return ""
