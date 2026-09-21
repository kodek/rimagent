"""Search the decompiled game source (exact 1.6 build + legacy repo).

Ripgrep when it is on PATH, and a plain scan when it is not. README lists rg as
a requirement, but on Windows it is rarely already installed and the failure was
a FileNotFoundError out of subprocess, which does not read as "ripgrep is
missing" to anyone, model or human.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..paths import SOURCE_16, SOURCE_LEGACY

MAX_COL = 220


def search(query: str, regex: bool = False, limit: int = 20, legacy: bool = False) -> list[dict]:
    root = SOURCE_LEGACY if legacy else SOURCE_16
    if not root.exists():
        return [{"error": f"{root} missing; run `rimagent seed`"}]
    rg = shutil.which("rg")
    if rg is None:
        return _scan(root, query, regex, limit)
    args = [rg, "--no-heading", "--line-number", "--color", "never", "-m", "3", "--max-columns", str(MAX_COL), "-g", "*.cs"]
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
        hits.append({"file": str(Path(path).relative_to(root)), "line": int(ln), "text": text.strip()[:MAX_COL]})
        if len(hits) >= limit:
            break
    return hits


def _scan(root: Path, query: str, regex: bool, limit: int, per_file: int = 3) -> list[dict]:
    """Same answer as the ripgrep path, without ripgrep. Slower, and it stops at `limit`."""
    try:
        pat = re.compile(query if regex else re.escape(query))
    except re.error as e:
        return [{"error": f"bad regex: {e}"}]
    hits: list[dict] = []
    for p in sorted(root.rglob("*.cs")):
        found = 0
        try:
            with p.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if not pat.search(line):
                        continue
                    hits.append({"file": str(p.relative_to(root)), "line": i, "text": line.strip()[:MAX_COL]})
                    found += 1
                    if len(hits) >= limit:
                        return hits
                    if found >= per_file:
                        break
        except OSError:
            continue
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
