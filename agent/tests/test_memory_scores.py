"""Notebook/journal memory and the episode scorecard."""
from __future__ import annotations

import json

import pytest

from rimagent import memory, paths, scorecard

pytestmark = pytest.mark.usefixtures("clean_brain")


# ---------------------------------------------------------------- notebook

def test_notebook_read_empty_when_missing():
    assert not paths.NOTEBOOK.exists()
    assert memory.notebook_read() == ""


def test_notebook_write_append_read():
    memory.notebook_write("  # Colony\nline one  \n\n")
    assert paths.NOTEBOOK.read_text(encoding="utf-8") == "# Colony\nline one\n"
    assert memory.notebook_read() == "# Colony\nline one\n"

    memory.notebook_append("  line two ")
    assert memory.notebook_read() == "# Colony\nline one\n\nline two\n"

    memory.notebook_reset("# Fresh")
    assert memory.notebook_read() == "# Fresh\n"


# ---------------------------------------------------------------- journal

def test_journal_read_empty_when_missing():
    assert memory.journal_read() == ""


def test_journal_append_writes_header_once_and_entries():
    memory.journal_append("First lesson", "Don't build with wood.\n", episode=1)
    memory.journal_append("Second lesson", "Stockpile food.")
    memory.journal_append("Third lesson", "Research batteries.", episode=3)

    raw = paths.JOURNAL.read_text(encoding="utf-8")
    assert raw.count("# Journal — lessons that survive between games") == 1
    assert raw.startswith("# Journal — lessons that survive between games\n")
    assert raw.count("\n## ") == 3
    assert "(episode 1): First lesson\nDon't build with wood.\n" in raw
    assert ": Second lesson\nStockpile food.\n" in raw
    assert "(episode 3): Third lesson" in raw
    assert "(episode )" not in raw


def test_journal_read_tail():
    for i in range(5):
        memory.journal_append(f"Lesson {i}", f"text {i}")

    full = memory.journal_read()
    assert full.startswith("## ")
    for i in range(5):
        assert f"Lesson {i}" in full
    # header is dropped (it lives before the first "\n## ")
    assert "# Journal" not in full.split("\n## ")[0] or full.startswith("## ")

    last2 = memory.journal_read(last_n=2)
    assert last2.startswith("## ")
    assert "Lesson 3" in last2 and "Lesson 4" in last2
    assert "Lesson 2" not in last2
    assert last2.count("## ") == 2
    assert last2.endswith("text 4")


# ---------------------------------------------------------------- scorecard

def test_record_and_history():
    assert scorecard.history() == []
    assert scorecard.history_text() == "(no episodes scored yet)"

    scorecard.record({"episode": 1, "seed": "s1", "days": 10, "colonists": 3, "deaths": 0, "wealth": 15000, "score": 500.0, "assisted": False, "brain_sha": "abcdef0123456", "ended": "max_days"})
    scorecard.record({"episode": 2, "seed": "s2", "days": 5, "colonists": 2, "deaths": 1, "wealth": 9000, "score": 100.0, "assisted": True, "brain_sha": "1234567890", "ended": "wipe"})

    rows = scorecard.history()
    assert [r["episode"] for r in rows] == [1, 2]
    assert all("t" in r and isinstance(r["t"], float) for r in rows)
    assert scorecard.history(last=1)[0]["episode"] == 2

    lines = paths.SCORES.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["seed"] == "s1"

    text = scorecard.history_text()
    tl = text.splitlines()
    assert tl[0].startswith("episode | seed | days")
    assert tl[1] == "1 | s1 | 10 | 3 | 0 | 15000 | 500.0 | no | abcdef0 | max_days"
    assert tl[2] == "2 | s2 | 5 | 2 | 1 | 9000 | 100.0 | yes | 1234567 | wipe"
    assert len(scorecard.history_text(last=1).splitlines()) == 2


def test_history_skips_blank_lines():
    scorecard.record({"episode": 1})
    with paths.SCORES.open("a", encoding="utf-8") as fh:
        fh.write("\n\n")
    scorecard.record({"episode": 2})
    assert [r["episode"] for r in scorecard.history()] == [1, 2]


def test_score_from_monotonic_sanity():
    base = dict(days=20, colonists=4, deaths=0, wealth=20000, mood_avg=60, research_done=3, raids_survived=2)
    s0 = scorecard.score_from(**base)
    assert isinstance(s0, float)

    assert scorecard.score_from(**{**base, "deaths": 1}) < s0
    assert scorecard.score_from(**{**base, "deaths": 2}) < scorecard.score_from(**{**base, "deaths": 1})
    assert scorecard.score_from(**{**base, "days": 30}) > s0
    assert scorecard.score_from(**{**base, "colonists": 5}) > s0
    assert scorecard.score_from(**{**base, "wealth": 30000}) > s0
    assert scorecard.score_from(**{**base, "mood_avg": 80}) > s0
    assert scorecard.score_from(**{**base, "research_done": 5}) > s0
    assert scorecard.score_from(**{**base, "raids_survived": 3}) > s0
    # wealth below the 14000 floor contributes nothing (not negative)
    assert scorecard.score_from(**{**base, "wealth": 1000}) == scorecard.score_from(**{**base, "wealth": 14000})
    # explicit formula check
    assert scorecard.score_from(days=1, colonists=1, deaths=1, wealth=14400, mood_avg=2, research_done=1, raids_survived=1) == round(10 + 60 + 1 + 1 + 8 + 40 - 120, 1)
