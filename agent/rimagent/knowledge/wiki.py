"""RimWorld wiki → local markdown + BM25 index.

Scrapes every article through the MediaWiki API (wikitext), strips markup with mwparserfromhell, and stores
one file per page in knowledge/wiki. Search is BM25 over title + body chunks.
"""
from __future__ import annotations

import json
import pickle
import re
import time
from pathlib import Path

import httpx
import mwparserfromhell
from rank_bm25 import BM25Okapi

from ..paths import KNOWLEDGE, WIKI

API = "https://rimworldwiki.com/api.php"
INDEX_FILE = KNOWLEDGE / "wiki_bm25.pkl"
UA = {"User-Agent": "rimagent/0.1 (personal RimWorld agent; contact: local)"}


def _safe_name(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ ()'-]+", "_", title).strip()[:120]


def list_all_pages(client: httpx.Client) -> list[str]:
    titles: list[str] = []
    cont: dict = {}
    while True:
        r = client.get(API, params={"action": "query", "list": "allpages", "aplimit": 500, "apfilterredir": "nonredirects", "apnamespace": 0, "format": "json", **cont})
        r.raise_for_status()
        data = r.json()
        titles += [p["title"] for p in data["query"]["allpages"]]
        if "continue" not in data:
            break
        cont = data["continue"]
    return titles


def fetch_wikitext(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    r = client.get(API, params={"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": "|".join(titles), "format": "json", "formatversion": 2})
    r.raise_for_status()
    for page in r.json()["query"]["pages"]:
        if "revisions" in page:
            out[page["title"]] = page["revisions"][0]["slots"]["main"]["content"]
    return out


def wikitext_to_text(wt: str) -> str:
    code = mwparserfromhell.parse(wt)
    # Keep infobox-like template params as "key: value" lines; they hold most stats.
    lines: list[str] = []
    for tpl in code.filter_templates(recursive=False):
        name = str(tpl.name).strip().lower()
        if name.startswith("infobox") or name in ("main", "stats"):
            for param in tpl.params:
                v = param.value.strip_code().strip()
                if v and len(v) < 200:
                    lines.append(f"{param.name.strip()}: {v}")
    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return ("\n".join(lines) + "\n\n" + text).strip()


def scrape(limit: int | None = None, force: bool = False, log=print) -> int:
    with httpx.Client(headers=UA, timeout=60) as client:
        titles = list_all_pages(client)
        if limit:
            titles = titles[:limit]
        log(f"wiki: {len(titles)} articles")
        todo = [t for t in titles if force or not (WIKI / f"{_safe_name(t)}.md").exists()]
        log(f"wiki: fetching {len(todo)} new/updated pages")
        n = 0
        for i in range(0, len(todo), 40):
            batch = todo[i:i + 40]
            for attempt in range(3):
                try:
                    pages = fetch_wikitext(client, batch)
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"wiki: retry {attempt} ({e})")
                    time.sleep(3)
            else:
                continue
            for title, wt in pages.items():
                text = wikitext_to_text(wt)
                (WIKI / f"{_safe_name(title)}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
                n += 1
            if i % 400 == 0:
                log(f"wiki: {i + len(batch)}/{len(todo)}")
            time.sleep(0.3)
    build_index(log=log)
    return n


_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def build_index(log=print) -> None:
    docs: list[dict] = []
    for f in sorted(WIKI.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        title = text.split("\n", 1)[0].lstrip("# ").strip()
        # chunk by ~1200 chars on paragraph boundaries so hits point at the relevant part
        paras = text.split("\n\n")
        buf = ""
        for para in paras:
            if len(buf) + len(para) > 1200 and buf:
                docs.append({"title": title, "file": f.name, "text": buf.strip()})
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            docs.append({"title": title, "file": f.name, "text": buf.strip()})
    corpus = [_tok(d["title"] + " " + d["title"] + " " + d["text"]) for d in docs]
    bm25 = BM25Okapi(corpus) if corpus else None
    with INDEX_FILE.open("wb") as fh:
        pickle.dump({"docs": docs, "bm25": bm25}, fh)
    log(f"wiki: indexed {len(docs)} chunks from {len(list(WIKI.glob('*.md')))} pages")


_cache: dict | None = None


def _index() -> dict | None:
    global _cache
    if _cache is None and INDEX_FILE.exists():
        with INDEX_FILE.open("rb") as fh:
            _cache = pickle.load(fh)
    return _cache


def search(query: str, k: int = 5) -> list[dict]:
    idx = _index()
    if not idx or idx["bm25"] is None:
        return [{"error": "wiki index not built; run `rimagent seed`"}]
    scores = idx["bm25"].get_scores(_tok(query))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out = []
    seen_titles: dict[str, int] = {}
    for i in order:
        if scores[i] <= 0:
            break
        d = idx["docs"][i]
        if seen_titles.get(d["title"], 0) >= 2:
            continue
        seen_titles[d["title"]] = seen_titles.get(d["title"], 0) + 1
        out.append({"title": d["title"], "score": round(float(scores[i]), 2), "excerpt": d["text"][:900]})
        if len(out) >= k:
            break
    return out


def read(title: str, max_chars: int = 6000) -> str:
    f = WIKI / f"{_safe_name(title)}.md"
    if not f.exists():
        # fuzzy: case-insensitive prefix
        cands = [p for p in WIKI.glob("*.md") if p.stem.lower().startswith(title.lower())]
        if not cands:
            hits = search(title, 3)
            return "no page named %r. Closest: %s" % (title, ", ".join(h.get("title", "?") for h in hits))
        f = cands[0]
    text = f.read_text(encoding="utf-8")
    return text[:max_chars] + ("\n…(truncated; ask for a section)" if len(text) > max_chars else "")
