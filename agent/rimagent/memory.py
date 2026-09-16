"""Notebook (current colony, rewritable) and journal (cross-game, append-only)."""
from __future__ import annotations

import datetime as _dt

from .paths import JOURNAL, NOTEBOOK

NOTEBOOK_BUDGET = 6000  # chars


def notebook_read() -> str:
    return NOTEBOOK.read_text(encoding="utf-8") if NOTEBOOK.exists() else ""


def notebook_write(text: str) -> None:
    NOTEBOOK.write_text(text.strip() + "\n", encoding="utf-8")


def notebook_append(text: str) -> None:
    cur = notebook_read()
    notebook_write(cur + "\n" + text.strip())


def notebook_reset(header: str) -> None:
    notebook_write(header)


def journal_read(last_n: int = 40) -> str:
    if not JOURNAL.exists():
        return ""
    entries = JOURNAL.read_text(encoding="utf-8").split("\n## ")
    tail = entries[-last_n:]
    return ("## " if len(entries) > 1 else "") + "\n## ".join(e for e in tail).strip()


def journal_append(title: str, text: str, episode: int | None = None) -> None:
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    ep = f" (episode {episode})" if episode is not None else ""
    with JOURNAL.open("a", encoding="utf-8") as fh:
        if fh.tell() == 0:
            fh.write("# Journal — lessons that survive between games\n\n")
        fh.write(f"\n## {stamp}{ep}: {title}\n{text.strip()}\n")
