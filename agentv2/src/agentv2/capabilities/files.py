"""A Harness FileSystem whose tools carry a name prefix (brain_*, kb_*)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai_harness import FileSystem
from pydantic_ai_harness.filesystem import FileSystemToolset


@dataclass
class NamedFileSystem(FileSystem[Any]):
    """`prefix_tools` hides the prefixed tool name from the tool, so FileSystem events fail (pydantic-ai 2.47).
    Registering the tools under their prefixed names avoids the wrapper. Use `tools=`, not `read_only=`."""

    prefix: str = ""

    def get_toolset(self) -> FileSystemToolset[Any]:
        toolset = super().get_toolset()
        assert isinstance(toolset, FileSystemToolset), "read_only filters by unprefixed names; pass a read-only tools= list instead"
        for name in list(toolset.tools):
            tool = toolset.tools.pop(name)
            tool.name = f"{self.prefix}_{name}"
            toolset.tools[tool.name] = tool
        return toolset
