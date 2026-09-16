"""Skill library: frontmatter roundtrip, index, BM25 selection, read/delete by name or slug."""
from __future__ import annotations

import pytest

from rimagent import paths, skills

pytestmark = pytest.mark.usefixtures("clean_brain")


def test_write_and_load_roundtrip_with_frontmatter():
    p = skills.write("Fire Safety", "How to handle fires", "Build firebreaks.\n\nKeep water nearby.", tags=["fire", "safety"], always=True)
    assert p == paths.SKILLS / "fire-safety.md"
    assert p.exists()
    raw = p.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    assert "name: Fire Safety" in raw
    assert "always: true" in raw

    all_ = skills.load_all()
    assert len(all_) == 1
    s = all_[0]
    assert s.name == "Fire Safety"
    assert s.description == "How to handle fires"
    assert s.body == "Build firebreaks.\n\nKeep water nearby."
    assert s.always is True
    assert s.tags == ["fire", "safety"]
    assert s.path == p
    assert s.chars == len(s.body)


def test_write_defaults_not_always_no_tags_and_overwrites_same_slug():
    skills.write("Cooking", "v1", "Make simple meals.")
    skills.write("cooking", "v2", "Make fine meals.")  # same slug -> overwrite
    all_ = skills.load_all()
    assert len(all_) == 1
    s = all_[0]
    assert s.always is False
    assert s.tags == []
    assert s.description == "v2"
    assert s.name == "cooking"


def test_load_all_falls_back_to_stem_and_skips_unparseable():
    (paths.SKILLS / "plain.md").write_text("no frontmatter here\n", encoding="utf-8")
    (paths.SKILLS / "bad.md").write_bytes(b"---\nname: [unclosed\n---\nbody\n")
    all_ = skills.load_all()
    names = {s.name for s in all_}
    assert "plain" in names
    assert all(s.name != "bad" for s in all_)
    plain = next(s for s in all_ if s.name == "plain")
    assert plain.body == "no frontmatter here"
    assert plain.description == ""


def test_index_text():
    assert skills.index_text() == "(no skills yet)"
    skills.write("Cooking", "Make meals", "body text", always=False)
    skills.write("Core Rules", "Always on", "rules", always=True)
    text = skills.index_text()
    lines = text.splitlines()
    assert len(lines) == 2
    assert "- Cooking: Make meals (9 chars)" in lines
    assert "- Core Rules [always]: Always on (5 chars)" in lines


def test_select_returns_relevant_skill_and_excludes_always():
    # Note: BM25Okapi (rank_bm25) gives idf == 0 to a term present in exactly half of a 2-doc corpus and a
    # negative idf to a term present in every doc, so select() needs >= 3 candidates with distinct vocabulary
    # before any hit scores > 0. Real skill libraries are bigger; tests use three.
    skills.write("Cooking", "Make meals in a stove", "Assign a cook. Build an electric stove. Haul raw food near the kitchen.", tags=["food"])
    skills.write("Defense", "Handle raids", "Build sandbags and turrets. Draft colonists when raiders arrive.", tags=["combat"])
    skills.write("Research", "Pick research", "Queue batteries then hydroponics. Assign the smartest pawn to the bench.", tags=["tech"])
    skills.write("Always Core", "Core rules about stoves and raids", "stove stove stove raid raid raid draft colonists raiders", always=True)

    hits = skills.select("raiders are attacking, draft colonists")
    assert hits, "expected at least one hit"
    assert hits[0].name == "Defense"
    assert all(not s.always for s in hits)

    hits = skills.select("where should I build the stove for cooking meals")
    assert hits[0].name == "Cooking"
    assert all(s.name != "Always Core" for s in hits)

    assert skills.select("") == []
    assert skills.select("   ") == []
    # nothing shares a token -> nothing returned
    assert skills.select("zzqqxx") == []


def test_select_respects_k_and_orders_by_score():
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    for i, w in enumerate(words):
        # every skill mentions "shared"; skill i mentions it (i+1) times -> higher score
        skills.write(f"Skill {w}", f"about {w}", " ".join(["shared"] * (i + 1)) + f" {w}")
    hits = skills.select("shared foxtrot", k=3)
    assert len(hits) == 3
    assert hits[0].name == "Skill foxtrot"
    assert all(s.name != "Skill alpha" for s in hits)
    assert len(skills.select("shared foxtrot", k=10)) == 6


def test_read_by_name_and_slug():
    skills.write("Fire Safety", "d", "body")
    by_name = skills.read("Fire Safety")
    by_slug = skills.read("fire-safety")
    by_slugged_name = skills.read("fire safety")
    assert by_name == by_slug == by_slugged_name
    assert "body" in by_name
    with pytest.raises(FileNotFoundError) as ei:
        skills.read("nonexistent")
    assert "Fire Safety" in str(ei.value)


def test_delete_by_name_and_slug():
    skills.write("Fire Safety", "d", "body")
    skills.write("Cooking", "d", "body")
    assert skills.delete("fire-safety") is True
    assert not (paths.SKILLS / "fire-safety.md").exists()
    assert skills.delete("Cooking") is True
    assert skills.delete("Cooking") is False
    assert skills.load_all() == []
