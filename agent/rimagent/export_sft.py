"""Turn captured LLM calls (sft/raw/capture-*.jsonl, written by llm.LLM._capture) into an SFT dataset.

Filters to honest (non-assisted) episodes at or above --min-score (per brain/scores.jsonl) and, by default,
the "play" stream only (excludes reflect/watchdog/parallel-manager calls). Each kept call becomes one
OpenAI-style {"messages": [...], "tools": [...]} training example ending in the model's assistant turn
(tool_calls preserved; reasoning_content re-attached as a <think> block for Qwen3-style thinking SFT).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .paths import SFT_RAW, SCORES

_TOOLS_DIR = SFT_RAW / "tools"


def _good_episodes(min_score: float, include_assisted: bool) -> set[tuple[Any, Any]]:
    if not SCORES.exists():
        return set()
    rows = [json.loads(l) for l in SCORES.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {(r.get("episode"), r.get("seed")) for r in rows if (include_assisted or not r.get("assisted")) and r.get("score", float("-inf")) >= min_score}


def _load_tools(ref: str | None) -> list[dict[str, Any]] | None:
    if not ref:
        return None
    p = _TOOLS_DIR / f"{ref}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _assistant_turn(reply: dict[str, Any]) -> dict[str, Any]:
    content = reply.get("content") or ""
    if reply.get("reasoning"):
        content = f"<think>\n{reply['reasoning']}\n</think>\n{content}"
    m: dict[str, Any] = {"role": "assistant", "content": content}
    if reply.get("tool_calls"):
        m["tool_calls"] = [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}} for tc in reply["tool_calls"]]
    return m


def export(out_path: Path, min_score: float = 0.0, include_assisted: bool = False, streams: set[str] | None = None) -> tuple[int, int]:
    streams = streams if streams is not None else {"play"}
    good = _good_episodes(min_score, include_assisted)
    kept = seen = 0
    with out_path.open("w", encoding="utf-8") as out:
        for f in sorted(SFT_RAW.glob("capture-*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                seen += 1
                rec = json.loads(line)
                meta = rec.get("meta") or {}
                key = (meta.get("episode"), meta.get("seed"))
                if key not in good or (streams and meta.get("stream") not in streams):
                    continue
                example = {"messages": rec["messages"] + [_assistant_turn(rec["reply"])]}
                tools = _load_tools(rec.get("tools_ref"))
                if tools:
                    example["tools"] = tools
                out.write(json.dumps(example) + "\n")
                kept += 1
    return kept, seen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="sft/dataset.jsonl")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--include-assisted", action="store_true")
    ap.add_argument("--streams", default="play", help="comma-separated stream names, or 'all'")
    args = ap.parse_args(argv)
    streams = None if args.streams == "all" else set(args.streams.split(","))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept, seen = export(out_path, args.min_score, args.include_assisted, streams)
    print(f"wrote {kept}/{seen} captured calls to {out_path}")


if __name__ == "__main__":
    main()
