"""Seed strategy skills from the offline wiki.

`distill_skills(llm, log)` reads a handful of wiki pages per skill, asks the LLM to distil them into a skill
body in the same format as the hand-written skills in brain/skills, and writes it, only if no skill of that
name exists yet, so re-running never clobbers what the agent has since improved.

    cd agent && uv run python -c "from rimagent.knowledge import seed; from rimagent.llm import LLM; seed.distill_skills(LLM())"
"""
from __future__ import annotations

import re
from typing import Callable

from .. import skills
from . import wiki

# (skill name, wiki page titles, focus), the focus tells the LLM what an agent needs from those pages.
SEED_SKILLS: list[tuple[str, list[str], str]] = [
    (
        "early-game-food",
        ["Rice plant", "Potato plant", "Corn plant", "Nutrition", "Food", "Meals", "Simple meal", "Growing zone", "Campfire", "Food Poison Chance"],
        "Rice vs potatoes vs corn with growth days, yield and nutrition; nutrition per colonist per day (1.6) and how many growing cells that needs; "
        "hunting safely (revenge animals, hunt at range); butchering and cooking simple meals at a campfire; raw-food and no-table mood penalties.",
    ),
    (
        "base-building",
        ["Wall", "Door", "Roof", "Rooms", "Wood", "Stone blocks", "Beauty", "Comfort"],
        "Room sizes and bedroom space thoughts, doors, how roofs form and collapse, stone vs wood (flammability, HP, beauty, cost), floors, "
        "home area, a sensible first layout for 3 colonists.",
    ),
    (
        "defense-basics",
        ["Raid points", "Raider", "Defense tactics", "Defense structures", "Cover", "Turret"],
        "How raid points scale with wealth and colonists; raid types; chokepoints and killboxes; cover values; turret cost/range; "
        "drafting discipline for the first raids with 3 colonists.",
    ),
    (
        "mood-and-mental-breaks",
        ["Mood", "Mental break", "Mental Break Threshold", "Recreation", "Beauty", "Comfort"],
        "Break thresholds (minor/major/extreme) and trait shifts; common early debuffs and buffs with values; kinds of breaks and how to respond; "
        "recreation, bedrooms vs barracks; what to build first for mood.",
    ),
    (
        "temperature-and-seasons",
        ["Temperature", "Comfortable Temperature", "Passive cooler", "Heater", "Cooler", "Campfire", "Parka", "Clothing"],
        "Comfortable range and hypothermia/heatstroke thresholds; growing season limits; cold snap and heat wave; passive cooler, heater, cooler numbers; "
        "insulation and clothing.",
    ),
    (
        "medicine-and-health",
        ["Medicine", "Herbal medicine", "Doctoring", "Infection", "Disease", "Flu", "Plague", "Malaria"],
        "Tend quality factors; medicine potencies; infections and the immunity race; medical policies (herbal vs industrial); doctors and self-tend; "
        "what to do when a colonist is downed.",
    ),
    (
        "research-order",
        ["Research", "Research bench", "Research Speed"],
        "What Crashlanded starts with; research bench and speed factors; a recommended early order with costs and reasons for a 3-colonist colony.",
    ),
    (
        "animals-and-hunting",
        ["Animals", "Animal husbandry", "Manhunter pulse", "Deer", "Elk", "Muffalo", "Alpaca", "Boar", "Cougar", "Hare", "Turkey"],
        "Revenge chance and meat yield per common animal; safe hunting method; predators and how to respond; taming and what is worth taming early; "
        "pens and training; manhunter response.",
    ),
    (
        "work-priorities",
        ["Work", "Skills"],
        "Which skills matter early; work types in order and their defNames; how 1-4/0 priorities resolve; passions; a default matrix for 3 Crashlanded colonists "
        "using rw_ui_set_work.",
    ),
    (
        "storyteller-and-threats",
        ["Cassandra Classic", "Raid points", "Wealth", "Wealth management", "Manhunter pulse"],
        "Cassandra pacing and the threat cycle; how wealth and colonist count drive threat points; what raises wealth fastest; incident kinds of the first year "
        "and a one-line response to each.",
    ),
]

_FORMAT_RULES = """Write the skill BODY in markdown (no frontmatter, no title line needed) as operating instructions for an agent that plays
RimWorld 1.6 through tool calls: triggers ("when ..."), numbered steps, concrete numbers (days, nutrition, temperatures, costs,
percentages, thresholds), pitfalls. 300-700 words. Only use facts from the wiki pages given below; if the pages do not say, say nothing.
Name bridge tools where they apply: rw_ui_zone (zones), rw_ui_build (blueprints: def/at/rect/line/stuff), rw_ui_designate
(mine|cut|harvestwood|hunt|haul|tame|unforbid on cells/rect/things), rw_ui_add_bill, rw_ui_set_work (1 highest .. 4 lowest, 0 off),
rw_ui_set_research, rw_ui_draft/rw_ui_goto/rw_ui_attack, rw_ui_set_policies, rw_state_pawn, rw_state_threats, rw_map_find, rw_defs_get.
Coordinates are [x, z]; rects are [minX, minZ, w, h]. No emojis. End with one line: `Sources: <page>; <page>; ...`.
Return ONLY the body text."""


def _tags_for(name: str) -> list[str]:
    return [t for t in re.split(r"[-_ ]+", name) if t and t not in ("and", "basics")]


def _description_for(name: str, focus: str) -> str:
    first = focus.split(";")[0].strip().rstrip(".")
    return f"{name.replace('-', ' ').capitalize()}: {first}"


def _pages_text(titles: list[str], per_page: int = 9000, log: Callable[[str], None] = print) -> str:
    parts = []
    for t in titles:
        text = wiki.read(t, per_page)
        if text.startswith("no page named"):
            log(f"  wiki: {text}")
            continue
        parts.append(f"=== {t} ===\n{text}")
    return "\n\n".join(parts)


def distill_one(llm, name: str, titles: list[str], focus: str, log: Callable[[str], None] = print, max_tokens: int = 2500) -> str | None:
    """Return the generated body (not written) or None if the wiki had nothing."""
    pages = _pages_text(titles, log=log)
    if not pages.strip():
        log(f"  {name}: no wiki pages found, skipped")
        return None
    messages = [
        {"role": "system", "content": "You distil RimWorld wiki pages into short, concrete playbooks for an autonomous agent."},
        {"role": "user", "content": f"Skill name: {name}\nFocus: {focus}\n\n{_FORMAT_RULES}\n\nWIKI PAGES:\n\n{pages}"},
    ]
    reply = llm.chat(messages, thinking=False, max_tokens=max_tokens)
    body = (reply.content or "").strip()
    # strip an accidental fenced block or frontmatter
    body = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", body).strip()
    if body.startswith("---"):
        body = body.split("---", 2)[-1].strip()
    return body or None


def distill_skills(llm, log: Callable[[str], None] = print, only: list[str] | None = None, force: bool = False) -> list[str]:
    """Write every seed skill that does not exist yet. Returns the names written."""
    existing = {s.name for s in skills.load_all()}
    written: list[str] = []
    for name, titles, focus in SEED_SKILLS:
        if only and name not in only:
            continue
        if name in existing and not force:
            log(f"skip {name}: already exists")
            continue
        log(f"distilling {name} from {len(titles)} pages")
        body = distill_one(llm, name, titles, focus, log=log)
        if not body:
            continue
        path = skills.write(name, _description_for(name, focus), body, tags=_tags_for(name), always=False)
        log(f"  wrote {path.name} ({len(body)} chars)")
        written.append(name)
    return written


if __name__ == "__main__":  # pragma: no cover
    from ..llm import LLM

    distill_skills(LLM())
