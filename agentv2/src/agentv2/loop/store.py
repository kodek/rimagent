"""The decision log and the policy stages, in runs/loop.sqlite, outside the brain the agent edits.

Every decision keeps the exact state and questions Jev got, so a changed policy can be replayed on it without the game.
A label ("truth") says what the right answer was; a share of the decisions is held out: the agent never sees their
labels, and only the promotion gate scores on them. A stage belongs to one policy version (its content hash)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Stage = Literal["off", "shadow", "canary", "active"]
STAGES: tuple[Stage, ...] = ("off", "shadow", "canary", "active")
SOURCES = {"improver": 1, "reflector": 1, "director": 2, "operator": 3}

_SCHEMA = """
create table if not exists decisions(
  id integer primary key, t real, tick integer, colony text, policy text, digest text, stage text, entity text, summary text,
  options text, state text, questions text, answers text, label text, confidence real, outcome text, reason text, action text, result text, ms real,
  truth text, truth_source text, truth_note text);
create index if not exists decisions_policy on decisions(policy, id);
create table if not exists stages(policy text, digest text, stage text, t real, note text, evidence text, primary key(policy, digest));
create table if not exists stage_log(t real, policy text, digest text, stage text, note text, evidence text);
"""


class Decision(BaseModel):
    id: int
    t: float
    tick: int
    colony: str
    policy: str
    digest: str
    stage: str
    entity: str
    summary: str
    options: list[str]
    state: Any
    questions: dict[str, Any]
    answers: dict[str, Any]
    label: str | None
    confidence: float | None
    outcome: str
    reason: str
    action: Any = None
    result: Any = None
    ms: float | None = None
    truth: str | None = None
    truth_source: str | None = None
    truth_note: str | None = None

    @property
    def verdict(self) -> str:
        """What it decided, in label terms: the option it acted with (or would have, in shadow), `escalate` or `none`."""
        if self.outcome in ("acted", "failed", "shadow"):
            return self.label or "none"
        return "escalate" if "escalat" in self.outcome else "none"


class LoopStore:
    def __init__(self, path: Path, heldout_share: float = 0.3) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.heldout_share = heldout_share

    def heldout(self, decision_id: int) -> bool:
        return (decision_id * 2654435761) % 1000 < self.heldout_share * 1000

    def record(self, **row: Any) -> int:
        row = {k: json.dumps(v) if k in ("options", "state", "questions", "answers", "action", "result") else v for k, v in row.items()}
        cur = self.db.execute(f"insert into decisions({', '.join(row)}, t) values({', '.join('?' * len(row))}, ?)", [*row.values(), time.time()])
        self.db.commit()
        assert cur.lastrowid is not None, "sqlite gave no row id"
        return cur.lastrowid

    def finish(self, decision_id: int, outcome: str, reason: str | None = None, action: Any = None, result: Any = None) -> None:
        self.db.execute("update decisions set outcome=?, reason=coalesce(?, reason), action=coalesce(?, action), result=coalesce(?, result) "
                        "where id=?", (outcome, reason, json.dumps(action) if action is not None else None,
                                      json.dumps(result, default=str) if result is not None else None, decision_id))
        self.db.commit()

    def get(self, decision_id: int) -> Decision | None:
        row = self.db.execute("select * from decisions where id=?", (decision_id,)).fetchone()
        return _decision(row) if row else None

    def set_truth(self, decision_id: int, truth: str, source: str, note: str = "") -> bool:
        """Label a decision; a stronger source (operator > director > brain pass) is not overwritten by a weaker one."""
        current = self.get(decision_id)
        if current is None:
            raise LookupError(f"no decision {decision_id}")
        if current.truth_source and SOURCES.get(current.truth_source, 0) > SOURCES.get(source, 0):
            return False
        self.db.execute("update decisions set truth=?, truth_source=?, truth_note=? where id=?", (truth, source, note, decision_id))
        self.db.commit()
        return True

    def latest(self, entity: str, *, since_t: float, unlabeled: bool = True, policy: str | None = None) -> Decision | None:
        sql = "select * from decisions where entity=? and t>=? and outcome!='acted'" + (" and truth is null" if unlabeled else "")
        args: list[Any] = [entity, since_t]
        if policy:
            sql, args = sql + " and policy=?", [*args, policy]
        row = self.db.execute(sql + " order by id desc limit 1", args).fetchone()
        return _decision(row) if row else None

    def recent(self, policy: str | None = None, limit: int = 20, where: str = "", digest: str | None = None) -> list[Decision]:
        sql, args = "select * from decisions where 1=1" + (f" and {where}" if where else ""), []
        if policy:
            sql, args = sql + " and policy=?", [policy]
        if digest:
            sql, args = sql + " and digest=?", [*args, digest]
        rows = self.db.execute(sql + " order by id desc limit ?", [*args, limit]).fetchall()
        return [_decision(r) for r in rows]

    def labelled(self, policy: str, *, heldout: bool) -> list[Decision]:
        rows = self.db.execute("select * from decisions where policy=? and truth is not null order by id", (policy,)).fetchall()
        return [d for r in rows if self.heldout((d := _decision(r)).id) == heldout]

    def counts(self, policy: str, digest: str | None = None) -> dict[str, int]:
        sql, args = "select outcome, count(*) n from decisions where policy=?", [policy]
        if digest:
            sql, args = sql + " and digest=?", [*args, digest]
        return {r["outcome"]: r["n"] for r in self.db.execute(sql + " group by outcome", args)}

    def stage(self, policy: str, digest: str) -> Stage:
        row = self.db.execute("select stage from stages where policy=? and digest=?", (policy, digest)).fetchone()
        return row["stage"] if row else "shadow"

    def set_stage(self, policy: str, digest: str, stage: Stage, note: str, evidence: dict[str, Any] | None = None) -> None:
        now, blob = time.time(), json.dumps(evidence or {})
        self.db.execute("insert or replace into stages values(?, ?, ?, ?, ?, ?)", (policy, digest, stage, now, note, blob))
        self.db.execute("insert into stage_log values(?, ?, ?, ?, ?, ?)", (now, policy, digest, stage, note, blob))
        self.db.commit()

    def stage_history(self, policy: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.execute("select * from stage_log where policy=? order by t desc limit ?", (policy, limit)).fetchall()
        return [dict(r) | {"evidence": json.loads(r["evidence"] or "{}")} for r in rows]

    def close(self) -> None:
        self.db.close()


def _decision(row: sqlite3.Row) -> Decision:
    data = dict(row)
    for k in ("options", "state", "questions", "answers", "action", "result"):
        data[k] = json.loads(data[k]) if data[k] is not None else {"questions": {}, "answers": {}, "options": []}.get(k)
    return Decision.model_validate(data)
