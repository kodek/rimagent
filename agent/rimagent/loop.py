"""One think step: a fresh, bounded tool-use conversation with the model."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import memory, scorecard, skills
from .context import Context
from .registry import to_text

PROMPTS = Path(__file__).parent / "prompts"

DEFAULT_SYSTEM = """You are rimagent. You run this RimWorld colony by yourself through tools, and you improve your own skills, tools and reflexes between games. Nobody else will help.

Protocol for every step: read the situation, act on the most urgent thing with tools, update the notebook if something important changed, then call end_turn with a wake plan. Be terse in visible text; do the work with tool calls. Tool results are truncated at ~8k chars, so ask narrowly.

## Skills index
{skills_index}

## Always-on skills
{always_skills}

## Relevant skills for this step
{selected_skills}

## Colony notebook
{notebook}

## Journal (cross-game lessons, latest)
{journal}


## Episode scores
{scores}

## Brain load errors
{tool_errors}
"""


def load_prompt(name: str, default: str) -> str:
    p = PROMPTS / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.exists() else default


@dataclass
class StepResult:
    notes: str = ""
    calls: int = 0
    elapsed: float = 0.0
    ended_by_tool: bool = False
    transcript: list[dict[str, Any]] = field(default_factory=list)


def _fmt(template: str, **kw: str) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", v)
    return out


def build_system(ctx: Context, situation_hint: str) -> str:
    all_skills = skills.load_all()
    always = [s for s in all_skills if s.always]
    selected = skills.select(situation_hint, k=4, skills=all_skills)
    errs = []
    errs += [f"tool file {f}: {e.strip().splitlines()[-1]}" for f, e in ctx.registry.load_errors.items()]
    errs += [f"watcher {f}: {e.strip().splitlines()[-1]}" for f, e in ctx.registry.watcher_errors.items()]
    return _fmt(
        load_prompt("system", DEFAULT_SYSTEM),
        skills_index=skills.index_text(all_skills),
        always_skills="\n\n".join(f"### {s.name}\n{s.body}" for s in always) or "(none)",
        selected_skills="\n\n".join(f"### {s.name}\n{s.body}" for s in selected) or "(none)",
        notebook=memory.notebook_read() or "(empty, start one)",
        journal=memory.journal_read(12) or "(empty)",
        operator="",
        scores=scorecard.history_text(8),
        tool_errors="\n".join(errs) or "(none)",
    )


def think(ctx: Context, user_message: str, situation_hint: str = "", *, max_calls: int | None = None, tool_groups: set[str] | None = None, thinking: bool | None = None, trigger: str = "scheduled", tool_allow=None) -> StepResult:
    """Run a bounded tool-use loop. Returns when the model calls end_turn/end_episode, stops calling tools, or hits max_calls."""
    cfg = ctx.config
    max_calls = max_calls or int(cfg["play"].get("max_tool_calls", 30))
    ctx.reset_turn()
    ctx.registry.reload_brain()
    t0 = time.time()
    res = StepResult()
    system = build_system(ctx, situation_hint or user_message[:2000])
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user_message}]
    tools = ctx.registry.specs(groups=tool_groups, allow=tool_allow)
    st = ctx.stream
    ctx.emit("think_start", {"trigger": trigger, "prompt_chars": len(system) + len(user_message), "tools": len(tools), "stream": st})
    step = 0
    while True:
        if res.calls >= max_calls:
            messages.append({"role": "user", "content": f"You have used {res.calls} tool calls, the limit for this step. Call end_turn now with your notes and wake plan."})
            tools_now = [t for t in tools if t["function"]["name"] in ("end_turn", "end_episode")]
        else:
            tools_now = tools
        reply = None
        for attempt in range(2):
            try:
                reply = ctx.llm.chat(messages, tools_now, thinking=thinking if attempt == 0 else False)
                break
            except Exception as e:  # noqa: BLE001
                ctx.emit("error", {"text": f"LLM call failed (attempt {attempt + 1}): {e}"})
        if reply is None:
            res.notes = "LLM error: gave up after 2 attempts"
            break
        step += 1
        if reply.reasoning:
            ctx.emit("reasoning", {"text": reply.reasoning[:20000], "stream": st})
        if reply.content:
            ctx.emit("assistant", {"text": reply.content, "stream": st})
        res.transcript.append({"role": "assistant", "content": reply.content, "reasoning": reply.reasoning[:4000], "tool_calls": reply.tool_calls})
        messages.append(ctx.llm.assistant_message(reply))
        if not reply.tool_calls:
            # Narration without action. Nudge back into the loop a couple of times before accepting it as the notes.
            nudges = res.transcript.count({"role": "nudge"})
            if nudges < 2 and res.calls < max_calls:
                res.transcript.append({"role": "nudge"})
                messages.append({"role": "user", "content": "You wrote text but called no tool. Continue with tool calls, or call end_turn(notes, wake_in_hours, wake_on) if you are done with this step."})
                continue
            res.notes = reply.content.strip()
            break
        image_msgs: list[dict[str, Any]] = []
        for tc in reply.tool_calls:
            name, args, cid = tc["name"], tc["arguments"], tc["id"]
            ctx.emit("tool_call", {"name": name, "args": args, "id": cid, "stream": st})
            t1 = time.time()
            result, ok = ctx.registry.execute(ctx, name, args)
            res.calls += 1
            image = None
            if isinstance(result, dict) and "_image_png_b64" in result:
                image = result.pop("_image_png_b64")
            text = to_text(result)
            ctx.emit("tool_result", {"name": name, "id": cid, "ok": ok, "text": text[:3000], "elapsed": round(time.time() - t1, 2), "stream": st})
            res.transcript.append({"role": "tool", "name": name, "ok": ok, "text": text[:3000]})
            messages.append({"role": "tool", "tool_call_id": cid, "content": text})
            if image:
                image_msgs.append({"role": "user", "content": [{"type": "text", "text": f"Image from {name}:"}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}]})
            if ctx.stop_turn:
                break
        messages.extend(image_msgs)
        if ctx.interrupt_check is not None and not ctx.stop_turn:
            try:
                urgent = ctx.interrupt_check()
            except Exception as e:  # noqa: BLE001
                urgent = []
                ctx.emit("error", {"text": f"interrupt check failed: {e}"})
            if urgent:
                ctx.emit("log", {"text": "urgent events delivered mid-step: " + "; ".join(u[:60] for u in urgent)})
                messages.append({"role": "user", "content": "## URGENT, happened while you were thinking (the game is now paused)\n" + "\n".join(f"- {u}" for u in urgent) + "\nDeal with these first (dialogs: rw_ui_dialog; threats: draft/position; downed: rescue), then continue."})
        inbox = ctx.extra.get("operator_inbox")
        if inbox:
            msgs, inbox[:] = list(inbox), []
            for m in msgs:
                ctx.emit("log", {"text": f"operator message delivered mid-step: {m[:80]}"})
            messages.append({"role": "user", "content": "## Message from the human operator\nAnswer it NOW with the reply_to_operator tool (one or two sentences). "
                             "If it is a tip or instruction about how to play, LEARN it: edit the most relevant skill with skill_write so it says this from now on "
                             "(mark the line 'operator tip'), and act on it in the colony if it applies right now. Then continue.\n" + "\n".join(f"- {m}" for m in msgs)})
        if ctx.stop_turn:
            res.ended_by_tool = True
            res.notes = ctx.wake.notes
            break
        # Keep the conversation bounded: if it grows huge, drop the oldest tool results' bodies.
        total = sum(len(m.get("content") or "") if isinstance(m.get("content"), str) else 0 for m in messages)
        if total > 160_000:
            for m in messages[2:]:
                if m.get("role") == "tool" and isinstance(m.get("content"), str) and len(m["content"]) > 400:
                    m["content"] = m["content"][:400] + "…(elided)"
                total = sum(len(m.get("content") or "") if isinstance(m.get("content"), str) else 0 for m in messages)
                if total < 120_000:
                    break
    res.elapsed = time.time() - t0
    ctx.emit("think_end", {"notes": res.notes, "wake": {"in_hours": ctx.wake.in_hours, "on_kinds": ctx.wake.on_kinds}, "calls": res.calls, "elapsed": round(res.elapsed, 1), "end_episode": ctx.end_episode_reason, "stream": st})
    return res


# ---------------------------------------------------------------- steward block

STEWARD_UNAVAILABLE = "steward: unavailable"
_STEWARD_MAX_STOCK, _STEWARD_MAX_PROBLEMS, _STEWARD_MAX_PAWNS = 10, 5, 6
_STEWARD_TOOLS = "Director tools: rw_steward_stock_set (target/suspend/allow), rw_steward_posture (temporary bias with hours), rw_steward_pawn (managed=false takes a pawn manual), rw_steward_explain (why a priority), rw_steward_stock_run (run a job now)."


def _hours_ago(h: Any) -> str:
    if h is None:
        return "never"
    try:
        h = float(h)
    except (TypeError, ValueError):
        return str(h)
    if h < 1:
        return f"{int(round(h * 60))}m ago"
    return f"{h:.0f}h ago" if h >= 10 else f"{h:.1f}h ago".replace(".0h", "h")


def steward_stock_line(row: dict[str, Any]) -> str:
    """One stock job as a line: `wood 420/500 forestry ok (last run 2h ago)`; ✗ + the summary when short or stalled."""
    label = row.get("label") or row.get("kind") or "?"
    kind = row.get("kind") or "?"
    target, current = row.get("target"), row.get("current")
    failures = int(row.get("failures") or 0)
    designations = int(row.get("designations") or 0)
    summary = str(row.get("summary") or "").strip()
    below = isinstance(target, (int, float)) and isinstance(current, (int, float)) and current < target
    stalled = failures >= 3 or "stall" in summary.lower()
    bad = False
    if not row.get("enabled", True):
        state = "off"
    elif row.get("suspended"):
        state = "suspended"
    elif row.get("managed") is False:
        state = "manual"
    elif stalled:
        state, bad = f"STALLED ({failures} failed runs)", True
    elif below and designations > 0:
        state = f"ok, {designations} designated"      # under target but work is queued: the job is doing its thing
    elif below and row.get("last_run_hours_ago") is None:
        state = "pending first run"
    elif below:
        state, bad = "below target, nothing designated", True
    else:
        state = "ok"
    head = f"{label} {current if current is not None else '?'}/{target if target is not None else '?'} {kind} {state}"
    if bad and summary:
        head += f": {summary[:120]}"
    return ("✗ " if bad else "") + head + f" (last run {_hours_ago(row.get('last_run_hours_ago'))})"


def steward_text(status: Any) -> str:
    """Render steward.status as the packet's Steward block body (no heading). Pure; ~25 lines max."""
    if not isinstance(status, dict):
        return STEWARD_UNAVAILABLE
    lines: list[str] = []
    en = status.get("enabled") or {}
    if isinstance(en, dict) and not (en.get("scorer", True) or en.get("stock", True)):
        lines.append("steward OFF (scorer and stock jobs disabled): you set priorities and designations yourself.")
    elif isinstance(en, dict) and (not en.get("scorer", True) or not en.get("stock", True)):
        lines.append("steward partly off: " + ", ".join(f"{k} {'on' if v else 'OFF'}" for k, v in en.items()))
    posture = status.get("posture")
    if isinstance(posture, dict) and posture:
        bits = []
        exp = posture.get("expires_in_hours")
        if exp is not None:
            bits.append(f"expires in {float(exp):.0f}h")
        for key, fmt in (("work", "{k} {v:+.1f}"), ("weights", "{k} x{v}"), ("targets", "{k} x{v}")):
            d = posture.get(key) or {}
            if isinstance(d, dict) and d:
                bits.append(key + ": " + ", ".join(fmt.format(k=k, v=v) for k, v in list(d.items())[:6]))
        lines.append(f"posture: {posture.get('label', '?')}" + (f" ({'; '.join(bits)})" if bits else ""))
    else:
        lines.append("posture: none (steady state)")
    stock = status.get("stock") or []
    if stock:
        lines.append("stock (target met = the job idles; raise the target to get more):")
        rows = [steward_stock_line(r) for r in stock if isinstance(r, dict)]
        rows.sort(key=lambda l: not l.startswith("✗"))   # problems first
        lines += ["- " + r for r in rows[:_STEWARD_MAX_STOCK]]
        if len(rows) > _STEWARD_MAX_STOCK:
            lines.append(f"- … {len(rows) - _STEWARD_MAX_STOCK} more jobs (rw_steward_stock_list)")
    else:
        lines.append("stock: no jobs (rw_steward_stock_add kind=forestry target=500 …)")
    problems = [str(x) for x in (status.get("problems") or []) if x]
    if problems:
        lines.append("problems:")
        lines += ["- " + x[:160] for x in problems[:_STEWARD_MAX_PROBLEMS]]
        if len(problems) > _STEWARD_MAX_PROBLEMS:
            lines.append(f"- … {len(problems) - _STEWARD_MAX_PROBLEMS} more")
    pawns = [p for p in (status.get("pawns") or []) if isinstance(p, dict) and p.get("managed") is False]
    if pawns:
        def prio(p: dict[str, Any]) -> str:
            pr = p.get("priorities") or {}
            items = sorted(pr.items(), key=lambda kv: (kv[1], kv[0]))[:4] if isinstance(pr, dict) else []
            return ", ".join(f"{k} {v}" for k, v in items) or "nothing enabled"
        lines.append("unmanaged pawns (their priorities are yours to keep; rw_steward_pawn managed=true hands them back):")
        lines += [f"- {p.get('name') or p.get('id')}: {prio(p)}" for p in pawns[:_STEWARD_MAX_PAWNS]]
        if len(pawns) > _STEWARD_MAX_PAWNS:
            lines.append(f"- … {len(pawns) - _STEWARD_MAX_PAWNS} more")
    research = status.get("research")
    if isinstance(research, dict):
        research = research.get("queue")
    if isinstance(research, list) and research:
        lines.append("research queue: " + ", ".join(str(r.get("label") or r.get("def") or r) if isinstance(r, dict) else str(r) for r in research[:5]) + (" …" if len(research) > 5 else ""))
    if problems or any(l.startswith("- ✗") for l in lines):
        lines.append(_STEWARD_TOOLS)
    return "\n".join(lines)


def steward_block(ctx: Context) -> str:
    """The packet's Steward section: rendered from steward.status, or `steward: unavailable` when the RPC is missing/failing."""
    try:
        status = ctx.bridge.call("steward.status")
    except Exception:  # noqa: BLE001  (BridgeError for unknown method / ok:false, or the bridge being down)
        status = None
    body = steward_text(status) if isinstance(status, dict) else STEWARD_UNAVAILABLE
    return "## Steward (sets work priorities and keeps stock targets; you direct it)\n" + body


def situation_packet(ctx: Context, trigger: str, events: list[dict[str, Any]], alerts: list[dict[str, Any]], extra: str = "") -> tuple[str, str]:
    """Build the user message for a play step: change first, then objects, then raw state. Returns (message, hint)."""
    from . import tracker, worlddiff
    parts: list[str] = [f"## Wake trigger\n{trigger}"]
    hint = trigger
    if ctx.extra.get("sandbox"):
        parts.append("## SANDBOX EPISODE (not scored)\nGod mode is on: blueprints complete instantly and cost nothing; all research is unlocked. Use this game to EXPERIMENT and LEARN: build layouts you were unsure about, wire power grids and check state.power / map.power, test defenses with rw_dev_incident, try mechanics you have not used. After each experiment write what you learned into the relevant skill (with numbers) and, if it is a repeatable check, into a tool or watcher. Do not optimise the colony; optimise your skills.")
        hint += " experiment sandbox"
    summary: dict[str, Any] = {}
    base: dict[str, Any] = {}
    try:
        summary = ctx.bridge.call("state.summary")
    except Exception as e:  # noqa: BLE001
        parts.append(f"## Colony summary unavailable: {e}")
    try:
        base = ctx.bridge.call("state.base")
    except Exception as e:  # noqa: BLE001
        parts.append(f"## Base graph unavailable: {e}")
    if extra:
        parts.append(extra)
    try:
        dialogs = ctx.bridge.call("state.dialogs")
        if dialogs:
            parts.append("## OPEN DIALOGS, the game is paused until you answer with rw_ui_dialog(choice=...)\n" + json.dumps(dialogs, ensure_ascii=False)[:6000])
            hint += " dialog choice " + " ".join(str(d.get("text", ""))[:100] for d in dialogs)
    except Exception:  # noqa: BLE001
        pass
    if summary:
        try:
            parts.append("## Tracked values (trend, oldest→newest)\n" + tracker.sample(ctx.bridge, summary))
        except Exception as e:  # noqa: BLE001
            parts.append(f"## Tracked values unavailable: {e}")
    if summary and base:
        try:
            parts.append("## What changed since your last step\n" + worlddiff.diff_text(summary, base))
        except Exception as e:  # noqa: BLE001
            parts.append(f"## Diff unavailable: {e}")
    parts.append(steward_block(ctx))
    hint += " steward"
    if events:
        lines = [f"- [{e.get('day', '?')}d {e.get('hour', '?')}h] {e.get('kind')}: {e.get('text', '')}" for e in events[-80:]]
        parts.append(f"## New events ({len(events)})\n" + "\n".join(lines))
        hint += " " + " ".join(e.get("kind", "") for e in events[-30:])
    if alerts:
        parts.append("## Watcher alerts\n" + "\n".join(f"- {a.get('watcher')}: {a.get('text')}" for a in alerts))
    if summary.get("alerts"):
        parts.append("## Game alerts\n" + "\n".join(f"- [{a.get('priority')}] {a.get('label')}: {str(a.get('explanation', ''))[:160]}" for a in summary["alerts"][:12]))
        hint += " " + " ".join(str(a.get("label", "")) for a in summary["alerts"])
    try:
        letters = ctx.bridge.call("state.letters")
        if letters:
            parts.append("## Letters waiting (respond with rw_ui_letter or they pile up)\n" + json.dumps(letters, ensure_ascii=False)[:5000])
            hint += " " + " ".join(l.get("label", "") for l in letters)
    except Exception:  # noqa: BLE001
        pass
    if base:
        parts.append("## The base as objects (state.base)\n" + worlddiff.base_text(base))
    if summary:
        cols = summary.get("colonist_list") or []
        col_lines = [f"- {c.get('name')} ({c.get('id')}) at {c.get('pos')}: mood {c.get('mood')}, health {c.get('health')}, {c.get('job')}; {c.get('top_skills')}; weapon {c.get('weapon')}" + (" DOWNED" if c.get("downed") else "") + (f" MENTAL: {c.get('mental_state')}" if c.get("mental_state") else "") for c in cols]
        parts.append("## Colonists\n" + "\n".join(col_lines))
        slim = {k: v for k, v in summary.items() if k not in ("colonist_list", "alerts", "zones", "hostiles")}
        if summary.get("hostiles"):
            slim["hostiles"] = summary["hostiles"][:20]
        if summary.get("zones"):
            slim["zones"] = summary["zones"][:12]
        parts.append("## Colony numbers (state.summary)\n" + json.dumps(slim, ensure_ascii=False))
    parts.append("Act now. End with end_turn (notes + wake plan).")
    try:
        tracked = next((p for p in parts if p.startswith("## Tracked values")), "")
        changes = next((p for p in parts if p.startswith("## What changed")), "")
        ctx.emit("situation", {"trigger": trigger, "tracked": tracked.split("\n", 1)[-1] if tracked else "", "changes": changes.split("\n", 1)[-1] if changes else "", "day": summary.get("day"), "hour": summary.get("hour"), "chars": sum(len(p) for p in parts)})
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts), hint
