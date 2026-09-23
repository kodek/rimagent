"""The offline knowledge base in ../knowledge: the RimWorld wiki as Markdown (`agentv2 seed`), a ranked search over it,
and the decompiled game source, which the operator makes with ilspycmd."""
from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import mwparserfromhell
from pydantic_ai import ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset

WIKI_API = "https://rimworldwiki.com/api.php"
USER_AGENT = "agentv2/0.1 (RimWorld agent; offline knowledge seed)"
INDEX = "wiki-index.sqlite"
BATCH = 40
CHUNK = 1200
SOURCE_HINT = ("The decompiled game source is not there. To add it: dotnet tool install -g ilspycmd; "
               "ilspycmd -p -o {dest} <the game's Managed folder>/Assembly-CSharp.dll")

Log = Callable[[str], None]


def page_file(wiki: Path, title: str) -> Path:
    name = re.sub(r"[^A-Za-z0-9._ ()'-]+", "_", title).strip()[:120]
    return wiki / f"{name}.md"


def wikitext_to_markdown(title: str, wikitext: str) -> str:
    """Infobox and stats parameters as `key: value` lines (they hold most numbers), then the plain text."""
    code = mwparserfromhell.parse(wikitext)
    stats = [f"{p.name.strip()}: {value}" for t in code.filter_templates(recursive=False)
             if str(t.name).strip().lower().startswith(("infobox", "stats")) for p in t.params
             if (value := p.value.strip_code().strip()) and len(value) < 200]
    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"\{\{#.*?\}\}|</?[A-Za-z][^>]*>", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return f"# {title}\n\n" + "\n".join(stats) + ("\n\n" if stats else "") + text + "\n"


async def scrape_wiki(client: httpx.AsyncClient, wiki: Path, *, refresh: bool = False, limit: int | None = None, log: Log = print) -> int:
    """Write each wiki article to `wiki/<title>.md`; skip the ones already there unless `refresh`."""
    wiki.mkdir(parents=True, exist_ok=True)
    titles = await _all_titles(client, limit)
    todo = [t for t in titles if refresh or not page_file(wiki, t).exists()]
    log(f"wiki: {len(titles)} articles, {len(todo)} to fetch")
    written = 0
    for start in range(0, len(todo), BATCH):
        for title, wikitext in (await _wikitext(client, todo[start:start + BATCH])).items():
            page_file(wiki, title).write_text(wikitext_to_markdown(title, wikitext), encoding="utf-8")
            written += 1
        log(f"wiki: {min(start + BATCH, len(todo))}/{len(todo)}")
        await asyncio.sleep(0.3)
    return written


async def _api(client: httpx.AsyncClient, params: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
    while True:
        try:
            response = await client.get(WIKI_API, params={**params, "format": "json", "formatversion": 2})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            attempts -= 1
            if not attempts:
                raise
            await asyncio.sleep(3)


async def _all_titles(client: httpx.AsyncClient, limit: int | None) -> list[str]:
    titles: list[str] = []
    more: dict[str, Any] = {}
    while True:
        data = await _api(client, {"action": "query", "list": "allpages", "aplimit": 500, "apnamespace": 0, "apfilterredir": "nonredirects", **more})
        titles += [p["title"] for p in data["query"]["allpages"]]
        if "continue" not in data or (limit and len(titles) >= limit):
            return titles[:limit]
        more = data["continue"]


async def _wikitext(client: httpx.AsyncClient, titles: list[str]) -> dict[str, str]:
    data = await _api(client, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": "|".join(titles)})
    return {p["title"]: p["revisions"][0]["slots"]["main"]["content"] for p in data["query"]["pages"] if p.get("revisions")}


def build_index(knowledge: Path, log: Log = print) -> int:
    """A SQLite FTS5 index over paragraph chunks of every wiki page, ranked by BM25."""
    wiki, path = knowledge / "wiki", knowledge / INDEX
    path.unlink(missing_ok=True)
    rows = [(title, f"wiki/{f.name}", chunk) for f in sorted(wiki.glob("*.md")) for title, chunk in _chunks(f)]
    with sqlite3.connect(path) as db:
        db.execute("CREATE VIRTUAL TABLE chunks USING fts5(title, path UNINDEXED, text, tokenize='porter unicode61')")
        db.executemany("INSERT INTO chunks VALUES (?, ?, ?)", rows)
    db.close()
    log(f"wiki index: {len(rows)} chunks from {len(list(wiki.glob('*.md')))} pages")
    return len(rows)


def _chunks(page: Path) -> list[tuple[str, str]]:
    text = page.read_text(encoding="utf-8")
    title = text.split("\n", 1)[0].lstrip("# ").strip()
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) > CHUNK:
            chunks.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    return [(title, c) for c in [*chunks, current.strip()] if c]


def search(index: Path, query: str, limit: int = 5, per_page: int = 2) -> list[dict[str, str]]:
    words = re.findall(r"\w+", query.lower())
    if not words:
        return []
    match = " OR ".join(f'"{w}"' for w in words)
    with sqlite3.connect(f"file:{index}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT title, path, text FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks, 10.0, 0.0, 1.0) LIMIT ?",
                          (match, limit * 10)).fetchall()
    db.close()
    hits: list[dict[str, str]] = []
    for title, path, text in rows:
        if sum(h["title"] == title for h in hits) < per_page:
            hits.append({"title": title, "path": path, "excerpt": text[:700]})
        if len(hits) >= limit:
            break
    return hits


@dataclass
class KnowledgeSearch(AbstractCapability[Any]):
    """kb_search: ranked search over the wiki; kb_read_file reads a whole page."""

    knowledge: Path

    def get_toolset(self) -> AgentToolset[Any]:
        toolset = FunctionToolset[Any](id="knowledge_search")
        index = self.knowledge / INDEX

        @toolset.tool_plain
        def kb_search(query: str, limit: int = 5) -> list[dict[str, str]]:
            """Search the RimWorld wiki by topic (ranked, words need not be exact). Read a whole page with kb_read_file(path).

            Args:
                query: Words, e.g. "raid points wealth" or "rice growing days".
                limit: How many excerpts.
            """
            if not index.exists():
                raise ToolFailed("the wiki index is missing: the operator makes it with `agentv2 seed`; use kb_grep meanwhile")
            return search(index, query, limit)

        return toolset


async def seed(knowledge: Path, *, refresh: bool = False, limit: int | None = None, index_only: bool = False, log: Log = print) -> None:
    if not index_only:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
            await scrape_wiki(client, knowledge / "wiki", refresh=refresh, limit=limit, log=log)
    build_index(knowledge, log)
    if not (knowledge / "source-1.6").is_dir():
        log(SOURCE_HINT.format(dest=knowledge / "source-1.6"))
