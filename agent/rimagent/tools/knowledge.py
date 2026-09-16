"""Knowledge tools: wiki, decompiled source."""
from __future__ import annotations

from ..knowledge import source, wiki
from ..registry import tool


@tool("search_wiki", "Search the RimWorld wiki (offline copy) for game mechanics, strategy, item stats. Returns top chunks.", {"query": "keywords", "k": "results (default 5)"}, group="knowledge")
def search_wiki(ctx, query: str, k: int = 5):
    return wiki.search(query, k)


@tool("read_wiki", "Read a wiki page by title (e.g. 'Raid points', 'Temperature', 'Defense tactics').", {"title": "page title", "max_chars": "default 6000"}, group="knowledge")
def read_wiki(ctx, title: str, max_chars: int = 6000):
    return wiki.read(title, max_chars)


@tool("search_source", "Grep the decompiled RimWorld 1.6 C# source. Use to learn exactly how a mechanic works or to find engine APIs for engine_call (class names, method signatures). Fixed-string by default.", {"query": "text or regex", "regex": "treat query as regex", "limit": "max hits (default 20)"}, group="knowledge")
def search_source(ctx, query: str, regex: bool = False, limit: int = 20):
    return source.search(query, regex=regex, limit=limit)


@tool("find_source_files", "Find source files by (partial) class/file name, e.g. 'Designator_' or 'StorytellerUtility'.", {"name": "substring of the file name"}, group="knowledge")
def find_source_files(ctx, name: str, limit: int = 30):
    return source.find_files(name, limit)


@tool("read_source", "Read a range of lines from a decompiled source file (path as returned by search_source).", {"path": "relative path like RimWorld/StorytellerUtility.cs", "start": "first line", "end": "last line (max 200 lines per call)"}, group="knowledge")
def read_source(ctx, path: str, start: int = 1, end: int | None = None):
    return source.read(path, start, end)
