"""The watcher files in brain/watchers, re-read when they change; memo and error stay with an unchanged file."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Watcher:
    name: str
    source: str
    digest: str
    memo: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class WatcherRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.loaded: dict[str, Watcher] = {}

    def scan(self) -> list[Watcher]:
        files = {p.stem: p for p in sorted(self.directory.glob("*.py"))}
        for name in set(self.loaded) - set(files):
            del self.loaded[name]
        for name, path in files.items():
            source = path.read_text(encoding="utf-8")
            digest = hashlib.blake2b(source.encode(), digest_size=12).hexdigest()
            current = self.loaded.get(name)
            if current is None or current.digest != digest:
                self.loaded[name] = Watcher(name, source, digest)
        return list(self.loaded.values())
