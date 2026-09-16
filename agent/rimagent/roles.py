"""Parallel mode: four specialist streams per calm step, each owning a slice of the write tools."""
from __future__ import annotations

import re
from typing import Callable

from .registry import Tool

# Tools every role may use (reads, knowledge, turn control).
_SHARED = re.compile(r"^(rw_state_|rw_map_|rw_defs_|rw_engine_get$|rw_engine_members$|rw_engine_types$|rw_engine_call$|rw_anchor_list$|rw_game_status$|rw_game_log_tail$|rw_bridge_methods$|search_|read_|find_source_files$|watch_|notebook_read$|skill_read$|skill_list$|journal_read$|score_history$|tool_list$|watcher_list$|run_python$|look$|rpc$|end_turn$|reply_to_operator$)")

ROLES: dict[str, dict] = {
    "econ": {
        "title": "Economy",
        "brief": "You run the economy: work priorities and schedules, growing zones and crops, stockpiles and storage filters, bills (cooking, butchering, crafting), hunting/tree-cutting/mining designations, hauling. Keep food days above 6, wood and steel stocked, nobody idle. Do not build structures, draft pawns, answer letters or edit skills; other streams do that.",
        "allow": re.compile(r"^(rw_ui_set_work|rw_ui_set_work_many|rw_ui_set_schedule|rw_ui_zone|rw_ui_storage|rw_ui_add_bill|rw_ui_bill|rw_ui_designate|rw_ui_area|notebook_append)$"),
    },
    "build": {
        "title": "Builder",
        "brief": "You are the architect: rooms, walls, doors, roofs, furniture placement, base extensions, power grids (generators, batteries, conduits with rw_ui_wire), deconstruction. Use rw_map_detail and anchors; name every site with rw_anchor_set; verify with dry runs. Do not change work priorities, draft pawns, answer letters or edit skills.",
        "allow": re.compile(r"^(rw_ui_build|rw_ui_build_many|rw_ui_wire|rw_anchor_set|rw_anchor_delete|rw_ui_designate|rw_ui_zone|rw_ui_area|notebook_append)$"),
    },
    "guard": {
        "title": "Guardian",
        "brief": "You keep people alive: threats and defense (draft, position, attack, retreat), fires, medical care and rescue, mood and mental-break prevention, hostility/medical policies, animals and prisoners, game speed during danger (rw_game_speed). Do not build, set work priorities, answer letters or edit skills.",
        "allow": re.compile(r"^(rw_ui_draft|rw_ui_goto|rw_ui_attack|rw_ui_job|rw_ui_cancel_job|rw_ui_set_policies|rw_ui_order|rw_ui_orders_at|rw_ui_press|rw_ui_gizmos|rw_ui_animal|rw_ui_prisoner|rw_game_speed|rw_game_pause|notebook_append)$"),
    },
    "steward": {
        "title": "Steward",
        "brief": "You are the steward: letters, quests and dialogs (answer every open one), research choice, trade, recruiting and prisoners, the operator's messages (reply first), and the colony's memory: keep the notebook current, edit skills, write tools and watchers, journal durable lessons, and decide the wake plan for the whole colony. You may end the episode if it is truly lost. Do not build, draft, or set work priorities.",
        "allow": re.compile(r"^(rw_ui_letter|rw_ui_dialog|rw_ui_set_research|rw_ui_prisoner|rw_game_save|rw_game_speed|notebook_|journal_|skill_|tool_|watcher_|brain_|end_episode$)"),
    },
}


def allow_for(role: str) -> Callable[[Tool], bool]:
    own = ROLES[role]["allow"]

    def ok(t: Tool) -> bool:
        if t.source == "brain":
            return True  # the agent's own tools are shared
        return bool(_SHARED.match(t.name) or own.match(t.name))

    return ok


def brief_for(role: str) -> str:
    r = ROLES[role]
    others = ", ".join(v["title"] for k, v in ROLES.items() if k != role)
    return f"## Your role this step: {r['title']} (parallel mode)\n{r['brief']}\nThree other streams ({others}) are acting on the same colony right now; stay in your lane, read state before precise actions, and keep your notes short. End with end_turn."
