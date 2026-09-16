"""Wiki knowledge: wikitext stripping, BM25 index/search over pages in WIKI, fuzzy read."""
from __future__ import annotations

import pytest

from rimagent import paths
from rimagent.knowledge import wiki


def test_wikitext_to_text_strips_markup_and_keeps_infobox_params():
    wt = (
        "{{Infobox main|name=Steel|marketvalue=1.9|description=A [[metal]] for [[building|buildings]].|empty=}}\n"
        "{{Stub}}\n"
        "'''Steel''' is a [[Resources|resource]] used for [[construction]] and ''crafting''.\n\n"
        "== Acquisition ==\n"
        "Mine [[compacted steel]] or smelt {{Icon|slag}} chunks.\n"
    )
    text = wiki.wikitext_to_text(wt)

    # infobox params come first as key: value, with inner markup stripped
    head, body = text.split("\n\n", 1)
    assert head.splitlines() == ["name: Steel", "marketvalue: 1.9", "description: A metal for buildings."]
    # templates and link brackets are gone from the body, link text is kept
    assert "{{" not in text and "}}" not in text
    assert "[[" not in text and "]]" not in text
    assert "'''" not in text and "''" not in text
    assert "Steel is a resource used for construction and crafting." in body
    assert "Acquisition" in body
    assert "Mine compacted steel or smelt" in body
    assert "\n\n\n" not in text


def test_wikitext_to_text_ignores_non_infobox_templates_and_long_values():
    wt = "{{Navbox|foo=bar}}{{Infobox thing|long=" + "x" * 250 + "|short=ok}}\nBody."
    text = wiki.wikitext_to_text(wt)
    assert "foo: bar" not in text
    assert "long:" not in text
    assert text.startswith("short: ok\n\nBody.")


@pytest.fixture
def fake_wiki(monkeypatch):
    for f in paths.WIKI.glob("*.md"):
        f.unlink()
    if wiki.INDEX_FILE.exists():
        wiki.INDEX_FILE.unlink()
    pages = {
        "Steel": "Steel is a common metal resource. It is used for construction of walls and weapons.\n\nSmelt steel slag chunks at an electric smelter.",
        "Rice": "Rice plant is a fast growing crop. Plant rice in a growing zone on rich soil.\n\nRice grows quickly but yields little nutrition per harvest.",
        "Turret": "The mini-turret is a defensive building that shoots at hostile raiders automatically.\n\nTurrets need steel and components; they explode when destroyed.",
    }
    for title, body in pages.items():
        (paths.WIKI / f"{wiki._safe_name(title)}.md").write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    logs = []
    wiki.build_index(log=logs.append)
    assert wiki.INDEX_FILE.exists()
    assert logs and "3 pages" in logs[-1]
    # build_index does not invalidate the in-process cache; make sure search sees the fresh index
    monkeypatch.setattr(wiki, "_cache", None)
    yield pages
    monkeypatch.setattr(wiki, "_cache", None)
    for f in paths.WIKI.glob("*.md"):
        f.unlink()
    if wiki.INDEX_FILE.exists():
        wiki.INDEX_FILE.unlink()


def test_index_file_lives_under_temp_knowledge_dir():
    assert str(wiki.INDEX_FILE).startswith(str(paths.ROOT))
    assert str(paths.WIKI).startswith(str(paths.ROOT))


def test_build_index_and_search(fake_wiki):
    hits = wiki.search("growing crop rice", k=5)
    assert hits and "error" not in hits[0]
    assert hits[0]["title"] == "Rice"
    assert hits[0]["score"] > 0
    assert "rice" in hits[0]["excerpt"].lower()

    hits = wiki.search("hostile raiders defensive", k=5)
    assert hits[0]["title"] == "Turret"

    # per-title cap of 2 chunks and k cap
    hits = wiki.search("steel", k=1)
    assert len(hits) == 1 and hits[0]["title"] == "Steel"

    # a query sharing no tokens yields nothing rather than junk
    assert wiki.search("zzqqxx") == []


def test_search_without_index_reports_error(monkeypatch):
    monkeypatch.setattr(wiki, "_cache", None)
    if wiki.INDEX_FILE.exists():
        wiki.INDEX_FILE.unlink()
    out = wiki.search("steel")
    assert out == [{"error": "wiki index not built; run `rimagent seed`"}]


def test_read_exact_and_fuzzy_prefix(fake_wiki):
    exact = wiki.read("Steel")
    assert exact.startswith("# Steel\n")
    assert "electric smelter" in exact

    fuzzy = wiki.read("tur")           # case-insensitive prefix match
    assert fuzzy.startswith("# Turret\n")
    assert wiki.read("RIC").startswith("# Rice\n")

    missing = wiki.read("Component")
    assert missing.startswith("no page named 'Component'")

    truncated = wiki.read("Steel", max_chars=20)
    assert truncated.startswith("# Steel")
    assert truncated.endswith("…(truncated; ask for a section)")


def test_read_search_fallback_lists_closest(fake_wiki):
    # no page starts with this, but the search hits by content
    out = wiki.read("smelter")
    assert out.startswith("no page named 'smelter'")
    assert "Steel" in out


def test_safe_name():
    assert wiki._safe_name("Rice (plant)") == "Rice (plant)"
    assert wiki._safe_name("A/B: C?") == "A_B_ C_"
    assert len(wiki._safe_name("x" * 300)) == 120


def test_tok():
    assert wiki._tok("Hello, World! 42-ab") == ["hello", "world", "42", "ab"]
