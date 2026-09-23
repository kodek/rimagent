"""An in-process stand-in for RimBridge (httpx transport), for tests and for smoke runs without RimWorld.

    game = FakeGame()
    bridge = Bridge("http://fake", transport=game.transport())
"""
from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import httpx
from PIL import Image

TICKS_PER_HOUR = 2500


@dataclass
class FakeGame:
    state: str = "playing"
    tick: int = 60_000
    speed: int = 3
    paused: bool = False
    seed: str = "rimagent-1"
    colonists: list[dict[str, Any]] = field(default_factory=lambda: [
        {"name": "Bob", "id": "Human1", "pos": [120, 118], "mood": 62, "health": 100, "job": "Cutting a tree", "top_skills": "Shooting 6!, Mining 4", "weapon": "Revolver"},
        {"name": "Ann", "id": "Human2", "pos": [122, 121], "mood": 55, "health": 90, "job": "Hauling", "top_skills": "Cooking 7!!, Growing 5"},
        {"name": "Cid", "id": "Human3", "pos": [118, 125], "mood": 71, "health": 100, "job": "Idle", "top_skills": "Construction 8!", "weapon": "Knife"},
    ])
    rooms: list[dict[str, Any]] = field(default_factory=lambda: [
        {"id": 1, "ref": "Room:1", "role": "Bedroom", "size": "6x5 (20 cells)", "free_floor": 12, "doors": [{"leads_to": "outside"}],
         "contents": {"Bed": 3}, "temp": 18, "problems": []},
    ])
    hostiles: list[dict[str, Any]] = field(default_factory=list)
    stocks: dict[str, int] = field(default_factory=lambda: {"WoodLog": 240, "Steel": 180})
    things: list[dict[str, Any]] = field(default_factory=list)
    bills: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    letters: list[dict[str, Any]] = field(default_factory=list)
    dialogs: list[dict[str, Any]] = field(default_factory=list)
    posture: dict[str, Any] | None = None
    ledger: list[dict[str, Any]] = field(default_factory=list)
    saves: dict[str, dict[str, Any]] = field(default_factory=dict)
    alive: bool = True
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    methods: list[dict[str, str]] = field(default_factory=lambda: json.loads(resources.files("agentv2").joinpath("fake_methods.json").read_text()))

    @property
    def day(self) -> int:
        return self.tick // (TICKS_PER_HOUR * 24)

    @property
    def hour(self) -> int:
        return self.tick // TICKS_PER_HOUR % 24

    def add_event(self, kind: str, text: str, **data: Any) -> None:
        self.ledger.append({"seq": len(self.ledger) + 1, "kind": kind, "text": text, "tick": self.tick, "day": self.day, "hour": self.hour, **data})

    def add_letter(self, label: str, text: str = "", choices: list[str] | None = None, def_: str = "NewQuest", quest: int | None = None) -> int:
        """A letter arrives, as LetterStack.ReceiveLetter does: on the stack and in the ledger. Only a choice letter has text."""
        letter_id = 100 + sum(e["kind"] == "letter" for e in self.ledger)
        letter: dict[str, Any] = {"id": letter_id, "label": label, "def": def_, "tick": self.tick}
        if choices:
            letter |= {"text": text, "choices": list(choices)} | ({"quest": quest} if quest is not None else {})
        self.letters.append(letter)
        data = {"label": label, "def": def_, "text": text if choices else "", "id": letter_id} | ({"quest": quest} if quest is not None and choices else {})
        self.add_event("letter", label, data=data)
        return letter_id

    def open_dialog(self, text: str, choices: list[str], type_: str = "Dialog_NodeTree", title: str | None = None) -> None:
        """A modal window opens (WindowStack.Add): the game pauses until it is answered."""
        window = {"type": type_, "force_pause": True, "text": text, "choices": list(choices)} | ({"title": title} if title else {})
        self.dialogs.append(window)
        self.add_event("dialog", f"{type_}: {text[:160]}", data=_describe(window, -1))

    def crash(self) -> None:
        """The game process dies: the bridge stops answering, and the restarted game has a new ledger at the main menu."""
        self.alive, self.state, self.ledger = False, "menu", []

    def advance(self, hours: float) -> None:
        before = self.day
        self.tick += int(hours * TICKS_PER_HOUR)
        if self.day != before:
            self.add_event("day", f"day {self.day} begins")

    async def run_clock(self, hours_per_second: float = 0.5, raid_every_days: int = 3) -> None:
        """Advance time like a running game: faster at higher speeds, stopped while paused or while a modal dialog is open;
        a raid every few days, a quest letter and a dialog on the days between."""
        while True:
            await asyncio.sleep(0.5)
            if self.state == "playing" and not self.paused and self.speed > 0 and not any(d["force_pause"] for d in self.dialogs):
                day = self.day
                self.advance(hours_per_second * 0.5 * self.speed)
                if self.day == day:
                    continue
                if self.day % raid_every_days == 0:
                    self.add_event("hostile_group", "A pirate band of 3 raiders is approaching from the east.")
                elif self.day % raid_every_days == 1:
                    self.add_letter("Trade request", "A nearby settlement asks for 200 wood in exchange for 150 silver. Deadline: 5 days.",
                                    ["Accept", "Reject"], quest=self.day)
                else:
                    self.open_dialog("A wanderer asks to join the colony. She is a skilled cook.", ["Accept", "Reject"])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if not self.alive:
            raise httpx.ConnectError("the fake game is down", request=request)
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"ok": True, "mainThreadAlive": True, "frames": 1})
        if path == "/methods":
            return httpx.Response(200, json={"ok": True, "result": self.methods})
        if path == "/events":
            since = int(request.url.params.get("since", 0))
            events = [e for e in self.ledger if e["seq"] > since]
            return httpx.Response(200, json={"ok": True, "result": {"events": events, "last_seq": len(self.ledger)}})
        if path == "/screenshot":
            buf = io.BytesIO()
            Image.new("RGB", (int(request.url.params.get("width_px", 1024)), int(request.url.params.get("height_px", 768))), (60, 90, 40)).save(buf, format="PNG")
            return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})
        if path == "/rpc":
            body = json.loads(request.content)
            method, params = body.get("method", ""), body.get("params") or {}
            self.calls.append((method, params))
            try:
                return httpx.Response(200, json={"ok": True, "result": self.rpc(method, params)})
            except KeyError as e:
                return httpx.Response(200, json={"ok": False, "error": str(e.args[0])})
        return httpx.Response(404, json={"ok": False, "error": "not found"})

    def rpc(self, method: str, p: dict[str, Any]) -> Any:
        known = {m["method"] for m in self.methods}
        if method not in known:
            raise KeyError(f"unknown method {method!r}")
        names = {c["name"] for c in self.colonists} | {c["id"] for c in self.colonists}
        match method:
            case "game.status":
                return {"state": self.state, "tick": self.tick, "day": self.day, "hour": self.hour, "season": "Spring", "speed": self.speed,
                        "paused": self.paused, "colonists": len(self.colonists), "seq": len(self.ledger), "seed": self.seed}
            case "game.speed":
                self.speed = int(p.get("speed", 1))
                return {"speed": self.speed}
            case "game.pause":
                self.paused = bool(p.get("paused", True))
                return {"paused": self.paused}
            case "game.new_game":
                self.state, self.seed, self.tick = "playing", str(p.get("seed", "x")), 60_000
                self.add_event("game", "new game started")
                return {"started": True}
            case "game.save":
                self.saves[str(p["name"])] = {"tick": self.tick, "seed": self.seed, "colonists": [dict(c) for c in self.colonists]}
                return {"saved": p["name"]}
            case "game.load":
                save = self.saves[str(p["name"])]
                self.state, self.tick, self.seed, self.colonists = "playing", save["tick"], save["seed"], [dict(c) for c in save["colonists"]]
                self.add_event("game", f"loaded save {p['name']}")
                return {"loading": p["name"]}
            case "steward.enable" | "steward.orders.set" | "game.dev_mode":
                return {"ok": True}
            case "game.list_saves":
                return [{"name": name, "modified": "now"} for name in self.saves]
            case "state.summary":
                return {"day": self.day, "hour": self.hour, "season": "Spring", "weather": "Clear", "temp_outdoor": 14, "colonists": len(self.colonists),
                        "colonist_list": self.colonists, "wealth": 14_500, "food_days": 6.5, "mood_avg": 62, "research_done": 3, "threat_points": 120,
                        "alerts": [], "key_stocks": dict(self.stocks), "outside_storage": {"stacks": 4, "rotting": 0, "storage_cells_free": 30},
                        "zones": [{"label": "rice", "type": "growing:Plant_Rice", "cells": 40, "at": [100, 100]}],
                        "hostiles": [{k: h[k] for k in ("id", "name", "def", "pos", "faction") if k in h} for h in self.hostiles],
                        "steward": {"scorer": True, "stock": True, "posture": self.posture["label"] if self.posture else None, "stock_brief": [],
                                    "problems": [], "orders_active": [], "rally": False}}
            case "state.base":
                return {"home_center": [120, 120], "rooms": self.rooms, "trapped_colonists": [], "furniture_not_in_any_room": None,
                        "structures_outside_rooms": {}, "blueprints_pending": 0, "frames_in_progress": 0, "anchors": []}
            case "state.threats":
                return {"hostiles": self.hostiles, "threat_points": 120, "home_center": [120, 120]}
            case "state.alerts":
                return []
            case "state.letters":
                return [dict(letter) for letter in self.letters]
            case "state.dialogs":
                return [_describe(d, i) for i, d in enumerate(self.dialogs)]
            case "ui.letter":
                return self._answer_letter(p)
            case "ui.dialog":
                return self._answer_dialog(p)
            case "steward.posture":
                return self._set_posture(p)
            case "steward.status":
                return {"enabled": {"scorer": True, "stock": True}, "posture": self.posture, "stock": [], "problems": [], "pawns": []}
            case "ui.draft" | "ui.goto":
                if p.get("pawn") not in names:
                    raise KeyError(f"no pawn {p.get('pawn')!r}")
                return {"pawn": p["pawn"], "ok": True}
            case "ui.build":
                if not p.get("def"):
                    raise KeyError("def is required")
                return {"placed": [[120, 120]], "failed": []}
            case "state.research":
                return {"current": None, "available": [{"def": "Batteries", "cost": 400}, {"def": "SolarPanels", "cost": 600}], "finished": 3}
            case "state.pawns":
                return self.colonists
            case "state.pawn":
                match = [c for c in self.colonists if p.get("pawn") in (c["name"], c["id"])]
                if not match:
                    raise KeyError(f"no pawn {p.get('pawn')!r}")
                return {**match[0], "skills": {"Shooting": 6, "Construction": 5, "Growing": 4}, "traits": ["Industrious"], "break_thresholds": [35, 20, 5],
                        "needs": {"Food": 70, "Rest": 40, "Joy": 30}, "thoughts": [{"label": "Ate without table", "mood": -3}, {"label": "Slept outside", "mood": -4}]}
            case "steward.orders":
                return [{"id": o, "enabled": True, "summary": "idle", "acting_on": 0} for o in ("combat", "rescue", "unforbid", "fire")]
            case "map.find":
                things = [t for t in self.things if all(t.get(k) == p[k] for k in ("def", "kind") if k in p)]
                if not things and p.get("kind") == "tree":
                    things = [{"id": f"Tree{i}", "def": "Plant_TreeOak", "pos": [i % 250, i // 250]} for i in range(600)]
                things = things[:int(p.get("limit", 50))]
                return {"count": len(things), "near": [120, 120], "things": things}
            case "engine.get":
                return 5.0 if str(p.get("path", "")).endswith(".plant.growDays") else {}
            case "state.designations":
                return {}
            case "map.detail":
                return {"centre": [120, 120], "grid": ".....\n..@..\n.....", "things": [{"id": "Bed1", "def": "Bed", "pos": [121, 119], "state": "built"}]}
            case "map.view" | "map.overview":
                return {"grid": ".....\n..@..\n.....", "legend": "@ colonist"}
            case "state.bills":
                return self.bills.get(p["thing"], [])
            case "ui.add_bill":
                self.bills.setdefault(p["thing"], []).append({"recipe": p["recipe"], "mode": p.get("mode"), "target": p.get("count")})
                return {"added": p["recipe"]}
            case "ui.bill" if p.get("action") == "delete":
                del self.bills[p["thing"]][int(p["index"])]
                return {"deleted": True}
            case "anchor.list" | "state.rooms" | "state.quests" | "state.storage":
                return []
            case _ if method.startswith(("ui.", "steward.", "anchor.", "game.")):
                return {"done": True}
            case _:
                return {}

    def _answer_letter(self, p: dict[str, Any]) -> dict[str, Any]:
        letter = next((x for x in self.letters if x["id"] == int(p["id"])), None)
        if letter is None:
            raise KeyError("no letter with that id (state.letters)")
        if p.get("action") == "dismiss":
            self.letters.remove(letter)
            return {"dismissed": letter["id"]}
        if not letter.get("choices"):
            raise KeyError("letter has no choices")
        chosen = _pick(letter["choices"], p.get("choice"))
        self.letters.remove(letter)
        return {"chose": chosen, "letter": letter["id"]}

    def _answer_dialog(self, p: dict[str, Any]) -> dict[str, Any]:
        if "i" in p:
            if not 0 <= int(p["i"]) < len(self.dialogs):
                raise KeyError("window index out of range")
            window = self.dialogs[int(p["i"])]
        elif self.dialogs:
            window = self.dialogs[-1]
        else:
            raise KeyError("no open dialog")
        if p.get("close"):
            self.dialogs.remove(window)
            return {"closed": window["type"]}
        chosen = _pick(window["choices"], p.get("choice"))
        self.dialogs.remove(window)
        self.add_event("dialog_answered", f"chose '{chosen}'")
        return {"chose": chosen, "next": None}

    def _set_posture(self, p: dict[str, Any]) -> dict[str, Any] | None:
        preset = p.get("preset") or (p.get("label") if p.get("label") in POSTURE_PRESETS else None)
        if p.get("clear") or preset == "normal":
            self.posture = None
            return None
        if preset is not None and preset not in POSTURE_PRESETS:
            raise KeyError(f"unknown preset '{preset}'. Known: {'|'.join(POSTURE_PRESETS)}")
        if preset is None and not any(p.get(k) for k in ("work", "weights", "targets")):
            raise KeyError("give preset (defend|build|harvest|recover|normal), or label + work/weights/targets, or clear:true")
        self.posture = {"label": p.get("label") or preset or "custom", "expires_in_hours": float(p.get("hours", 12)),
                        "work": dict(p.get("work") or {}), "weights": dict(p.get("weights") or {}), "targets": dict(p.get("targets") or {})}
        return self.posture


POSTURE_PRESETS = ("normal", "defend", "build", "harvest", "recover")


def _describe(window: dict[str, Any], index: int) -> dict[str, Any]:
    """DialogRpc.Describe for a Dialog_NodeTree or a Dialog_MessageBox."""
    out = {"i": index, "type": window["type"], "force_pause": window["force_pause"]} | ({"title": window["title"]} if "title" in window else {})
    return out | {"text": window["text"], "choices": [{"i": i, "label": c, "disabled": False, "reason": None} for i, c in enumerate(window["choices"])]}


def _pick(choices: list[str], choice: Any) -> str:
    """A choice by index, by label (case-insensitive), or by a part of a label, as the mod matches it."""
    if isinstance(choice, int):
        if 0 <= choice < len(choices):
            return choices[choice]
    else:
        label = str(choice or "").lower()
        for match in ([c for c in choices if c.lower() == label], [c for c in choices if label in c.lower()]):
            if match:
                return match[0]
    raise KeyError("no such choice. Available: " + " | ".join(choices))
