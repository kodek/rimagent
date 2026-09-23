"""Production tables and their bills: a status read, and a bill fixer that adds standard bills and removes duplicates."""
import asyncio
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

tools = FunctionToolset()
STANDARD = {  # table def: (recipe, repeat mode, count)
    "FueledStove": ("CookMealSimple", "TargetCount", 20),
    "ElectricStove": ("CookMealSimple", "TargetCount", 20),
    "Campfire": ("CookMealSimple", "TargetCount", 10),
    "ButcherSpot": ("ButcherCorpseFlesh", "Forever", 1),
    "TableButcher": ("ButcherCorpseFlesh", "Forever", 1),
    "TableStonecutter": ("Make_StoneBlocksAny", "Forever", 1),
    "TableSculpting": ("Make_SculptureSmall", "TargetCount", 3),
}
STOVES = ("FueledStove", "ElectricStove")


async def _call(ctx: RunContext, method: str, **params: Any) -> Any:
    return await ctx.deps.bridge.call(method, params)


async def _tables(ctx: RunContext) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    buildings = await _call(ctx, "map.find", kind="building", limit=500)
    tables = [t for t in buildings["things"] if t["def"] in STANDARD]
    bills = await asyncio.gather(*(_call(ctx, "state.bills", thing=t["id"]) for t in tables))
    return list(zip(tables, bills, strict=True))


@tools.tool
async def production_status(ctx: RunContext) -> dict[str, Any]:
    """Every production table with its bills (duplicates flagged), corpses to butcher, foods in stock, food days."""
    tables, corpses, foods, summary = await asyncio.gather(
        _tables(ctx), _call(ctx, "map.find", kind="corpse", limit=60), _call(ctx, "state.stocks", category="Foods"), _call(ctx, "state.summary"))
    rows, duplicates = [], []
    for table, bills in tables:
        recipes = [b["recipe"] for b in bills]
        rows.append({"def": table["def"], "id": table["id"], "at": table.get("pos"),
                     "bills": [{k: b.get(k) for k in ("recipe", "mode", "target", "suspended")} for b in bills]})
        duplicates += [{"id": table["id"], "recipe": r} for r in sorted({r for r in recipes if recipes.count(r) > 1})]
    animal = [c for c in corpses["things"] if not c["def"].startswith("Corpse_Human")]
    butchering = any(b["recipe"] == "ButcherCorpseFlesh" for _, bills in tables for b in bills)
    notes = ["animal corpses but no butcher bill"] if animal and not butchering else []
    notes += [f"duplicate bills on {d['id']}: {d['recipe']} (ensure_bills removes them)" for d in duplicates]
    return {"tables": rows, "duplicates": duplicates, "food_days": summary.get("food_days"), "foods": foods,
            "corpses": {"animal": len(animal), "human": len(corpses["things"]) - len(animal),
                        "nearest_animal": [{k: c.get(k) for k in ("id", "of", "pos", "rotting", "forbidden", "dist")} for c in animal[:6]]},
            "notes": notes}


@tools.tool
async def ensure_bills(ctx: RunContext, dry_run: bool = False) -> dict[str, Any]:
    """Give each production table its standard bill when it has none, and delete duplicate bills of one recipe.
    No cooking bill on a campfire when a stove exists. Run it after a work table is built.

    Args:
        dry_run: Only report what it would change.
    """
    tables = await _tables(ctx)
    stove = any(t["def"] in STOVES for t, _ in tables)
    added, removed = [], []
    for table, bills in tables:
        recipe, mode, count = STANDARD[table["def"]]
        recipes = [b["recipe"] for b in bills]
        if recipe not in recipes and not (table["def"] == "Campfire" and stove):
            added.append({"id": table["id"], "recipe": recipe, "mode": mode, "count": count})
            if not dry_run:
                await _call(ctx, "ui.add_bill", thing=table["id"], recipe=recipe, mode=mode, count=count)
        for index in range(len(recipes) - 1, -1, -1):
            if recipes[index] in recipes[:index]:
                removed.append({"id": table["id"], "recipe": recipes[index], "index": index})
                if not dry_run:
                    await _call(ctx, "ui.bill", thing=table["id"], index=index, action="delete")
    return {"added": added, "removed": removed, "dry_run": dry_run}


@dataclass
class Production(AbstractCapability):
    def get_toolset(self):
        return tools
