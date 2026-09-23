"""Add the standard bill the moment a production table is built (reacts to `built` events only).

Verified recipe defNames: FueledStove/ElectricStove -> CookMealSimple (TargetCount 20); ButcherSpot -> ButcherCorpseFlesh
(Forever); TableStonecutter -> Make_StoneBlocksAny (Forever); TableSculpting -> Make_SculptureSmall (TargetCount 3).
Campfire is left out on purpose: cooking moves to the stove once one exists."""

BILLS = {
    "FueledStove": ("CookMealSimple", "TargetCount", 20),
    "ElectricStove": ("CookMealSimple", "TargetCount", 20),
    "ButcherSpot": ("ButcherCorpseFlesh", "Forever", 0),
    "TableStonecutter": ("Make_StoneBlocksAny", "Forever", 0),
    "TableSculpting": ("Make_SculptureSmall", "TargetCount", 3),
}
LABELS = [("fueled stove", "FueledStove"), ("electric stove", "ElectricStove"), ("butcher spot", "ButcherSpot"),
          ("butcher table", "ButcherSpot"), ("stonecutter", "TableStonecutter"), ("art bench", "TableSculpting"),
          ("sculpting", "TableSculpting")]


def watch(events, status, memo):
    out = []
    for e in events:
        if e.get("kind") != "built":
            continue
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        d = e.get("def") or e.get("defName") or data.get("def") or data.get("defName")
        if not d:
            low = (e.get("text") or "").lower()
            for frag, dd in LABELS:
                if frag in low:
                    d = dd
                    break
        if d not in BILLS:
            continue
        thing = e.get("thing") or data.get("thing") or data.get("id")
        recipe, mode, count = BILLS[d]
        if thing:
            out.append({"type": "action", "method": "ui.add_bill", "params": {"thing": thing, "recipe": recipe, "mode": mode, "count": count},
                        "note": "auto bill " + recipe + " on new " + d})
        else:
            out.append({"type": "alert", "wake": False, "text": "new " + d + " built but the event has no thing id; add " + recipe + " by hand"})
    return out
