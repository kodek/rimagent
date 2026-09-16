"""Search the decompiled game source (exact 1.6 build + legacy repo) with ripgrep."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..paths import SOURCE_16, SOURCE_LEGACY


def search(query: str, regex: bool = False, limit: int = 20, legacy: bool = False) -> list[dict]:
    root = SOURCE_LEGACY if legacy else SOURCE_16
    if not root.exists():
        return [{"error": f"{root} missing; run `rimagent seed`"}]
    args = ["rg", "--no-heading", "--line-number", "--color", "never", "-m", "3", "--max-columns", "220", "-g", "*.cs"]
    if not regex:
        args.append("-F")
    args += [query, str(root)]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        return [{"error": "search timed out; narrow the query"}]
    hits = []
    for line in out.splitlines():
        m = re.match(r"^(.*?):(\d+):(.*)$", line)
        if not m:
            continue
        path, ln, text = m.groups()
        hits.append({"file": str(Path(path).relative_to(root)), "line": int(ln), "text": text.strip()[:220]})
        if len(hits) >= limit:
            break
    return hits


def find_files(name_query: str, limit: int = 30, legacy: bool = False) -> list[str]:
    root = SOURCE_LEGACY if legacy else SOURCE_16
    q = name_query.lower()
    out = []
    for p in root.rglob("*.cs"):
        if q in p.name.lower():
            out.append(str(p.relative_to(root)))
            if len(out) >= limit:
                break
    return out


def read(path: str, start: int = 1, end: int | None = None, legacy: bool = False, max_lines: int = 200) -> str:
    root = SOURCE_LEGACY if legacy else SOURCE_16
    f = (root / path).resolve()
    if not str(f).startswith(str(root.resolve())) or not f.exists():
        cands = find_files(Path(path).name, 5, legacy)
        return f"no file {path!r}. Candidates: {cands}"
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start)
    end = min(len(lines), end or start + max_lines - 1, start + max_lines - 1)
    body = "\n".join(f"{i:5d}  {lines[i - 1]}" for i in range(start, end + 1))
    return f"{path} lines {start}-{end} of {len(lines)}\n{body}"
