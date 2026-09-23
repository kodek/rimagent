"""The brain: what the agent authors and keeps between games, exposed through Pydantic AI Harness capabilities.

brain/
  AGENTS.md                 doctrine, loaded into every run by RepoContext; the agent may edit it
  skills/<name>/SKILL.md    Agent Skills, loaded on demand (Skills + load_capability)
  watchers/<name>.py        reflexes run in the Monty sandbox without the model (see watchers/)
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

import yaml
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, CombinedCapability, DynamicCapability
from pydantic_ai_harness import CapabilityCreation, Memory, RepoContext, Skills
from pydantic_ai_harness.memory import FileStore

from .capabilities.files import NamedFileSystem
from .deps import Deps
from .knowledge import KnowledgeSearch

AUTHORED = "authored_capabilities"
"""Run metadata key: False runs without the agent-authored capabilities."""

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
before you add a near-duplicate. The frontmatter `metadata: {wake-on: "raid, hostile_group"}` lists words: when a wake's
trigger, events or alerts contain one, you are reminded to load the skill.'''

KNOWLEDGE_GUIDE = '''kb_* tools read the offline RimWorld knowledge base: `wiki/<Page>.md` (the RimWorld wiki) and `source-1.6/**/*.cs`
(the decompiled game source). kb_search finds wiki pages by topic; kb_grep searches exact text (use it for the source),
kb_find_files finds names, kb_read_file reads a file.'''


class BrainLayout:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.skills_dir = root / "skills"
        self.watchers_dir = root / "watchers"
        self.capabilities_dir = root / "capabilities"
        self.memory_dir = root / "memory"
        self.doctrine = root / "AGENTS.md"
        self.operator_log = root / "operator.md"
        self.scores = root / "scores.jsonl"

    def make_dirs(self) -> None:
        for d in (self.skills_dir, self.watchers_dir, self.capabilities_dir, self.memory_dir):
            d.mkdir(parents=True, exist_ok=True)

    def skill(self, name: str) -> Path:
        return self.skills_dir / _checked(name) / "SKILL.md"

    def watcher(self, name: str) -> Path:
        return self.watchers_dir / f"{_checked(name)}.py"

    def capability(self, name: str) -> Path:
        return self.capabilities_dir / f"{_checked(name)}.py"

    def notebook(self, colony: str) -> Path:
        return self.memory_dir / colony / "main" / "MEMORY.md"

    def journal(self) -> Path:
        return self.memory_dir / "journal" / "MEMORY.md"

    @staticmethod
    def kind_of(path: str) -> str:
        head = path.split("/", 1)[0]
        return {"skills": "skill", "watchers": "watcher", "capabilities": "capability"}.get(head, "doctrine" if path == "AGENTS.md" else "file")


def _checked(name: str) -> str:
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        raise ValueError(f"bad brain file name {name!r}")
    return name


class OperatorLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, stamp: str, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            if fh.tell() == 0:
                fh.write("# What the human operator said\n")
            fh.write(f"\n- [{stamp}] {text.strip()}\n")

    def tail(self, chars: int) -> str:
        return self.path.read_text(encoding="utf-8")[-chars:] if self.path.exists() else "(nothing)"


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    chars: int
    error: str | None = None
    wake_on: tuple[str, ...] = ()


class SkillCatalog:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def infos(self) -> list[SkillInfo]:
        out = []
        for d in sorted(p for p in self.directory.iterdir() if p.is_dir()):
            path = d / "SKILL.md"
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            try:
                Skills(self.directory, include=[d.name])
            except Exception as e:  # noqa: BLE001 - an agent-written skill must not break the others; the error is reported to it
                out.append(SkillInfo(d.name, "", len(text), f"{type(e).__name__}: {e}"))
                continue
            front = _frontmatter(text)
            out.append(SkillInfo(d.name, str(front.get("description", "")), len(text), wake_on=_wake_on(front)))
        return out

    def capability(self) -> Skills[Any] | None:
        good = [s.name for s in self.infos() if not s.error]
        return Skills(self.directory, include=good) if good else None

    def matching(self, text: str) -> list[str]:
        """The skills whose `wake-on` words are in `text`."""
        low = text.lower()
        return [s.name for s in self.infos() if not s.error and any(word in low for word in s.wake_on)]


class Brain:
    def __init__(self, layout: BrainLayout, knowledge: Path | None = None) -> None:
        layout.make_dirs()
        self.layout = layout
        self.knowledge = knowledge if knowledge and knowledge.is_dir() else None
        self.skills = SkillCatalog(layout.skills_dir)
        self.operator = OperatorLog(layout.operator_log)
        self.creation = CapabilityCreation(directory=layout.capabilities_dir, guidance=AUTHORING_GUIDE)

    def capabilities(self) -> list[AbstractCapability[Deps]]:
        """The brain capabilities every agent carries; the skill catalog and authored capabilities are re-read every run."""
        caps: list[AbstractCapability[Deps]] = [
            RepoContext(workspace_dir=self.layout.root, home_dir=self.layout.root, expose_inventory_tool=False),
            self._filesystem(),
            self._notebook(),
            self._journal(),
            self.creation,
            DynamicCapability(self._per_run),
        ]
        if self.knowledge:
            caps.append(NamedFileSystem(root_dir=self.knowledge, tools=["read_file", "list_directory", "find_files", "grep"],
                                        denied_patterns=["*.sqlite", "*.pkl", "*.log"], max_read_lines=400, prefix="kb", id="knowledge_files"))
            caps.append(KnowledgeSearch(self.knowledge))
        return caps

    def guides(self) -> str:
        return "\n\n".join([BRAIN_GUIDE, KNOWLEDGE_GUIDE] if self.knowledge else [BRAIN_GUIDE])

    def problems(self) -> dict[str, str]:
        errors = {f"skill {s.name}": s.error for s in self.skills.infos() if s.error}
        return errors | {f"capability {r.name}": r.last_error for r in self.creation.store.list_all() if r.last_error}

    def has_authored(self) -> bool:
        return any(r.status == "active" for r in self.creation.store.list_all())

    def authored(self) -> list[dict[str, Any]]:
        return [json.loads(r.model_dump_json()) for r in self.creation.store.list_all()]

    def _per_run(self, ctx: RunContext[Deps]) -> AbstractCapability[Deps] | None:
        caps: list[AbstractCapability[Any]] = []
        if skills := self.skills.capability():
            caps.append(skills)
        if (ctx.metadata or {}).get(AUTHORED, True):
            caps += [c.prefix_tools("my") for c in self.creation.store.load_active()]
        return CombinedCapability(caps) if caps else None

    def _filesystem(self) -> AbstractCapability[Deps]:
        return NamedFileSystem(
            root_dir=self.layout.root,
            denied_patterns=["memory", "memory/*", ".git*", "*/__pycache__/*"],
            protected_patterns=["scores.jsonl", "operator.md", "capabilities", "capabilities/*", ".gitignore"],
            tools=["read_file", "list_directory", "find_files", "search_files", "write_file", "edit_file", "create_directory"],
            content_hashes=False,
            prefix="brain",
            id="brain_files",
        )

    def _notebook(self) -> AbstractCapability[Deps]:
        return Memory(
            FileStore(self.layout.memory_dir),
            namespace=_colony,
            heading="Colony notebook (this game only)",
            id="notebook",
        ).prefix_tools("notebook")

    def _journal(self) -> AbstractCapability[Deps]:
        return Memory(
            FileStore(self.layout.memory_dir),
            agent_name="journal",
            heading="Journal (durable lessons across games)",
            max_lines=120,
            id="journal",
        ).prefix_tools("journal")


def _colony(ctx: RunContext[Deps]) -> str:
    return ctx.deps.episode.colony


def _frontmatter(skill_text: str) -> dict[str, Any]:
    head = skill_text.split("\n---", 1)[0].removeprefix("---")
    front = yaml.safe_load(head)
    return front if isinstance(front, dict) else {}


def _wake_on(front: dict[str, Any]) -> tuple[str, ...]:
    metadata = front.get("metadata")
    words = metadata.get("wake-on", "") if isinstance(metadata, dict) else ""
    return tuple(w.strip().lower() for w in str(words).split(",") if w.strip())
