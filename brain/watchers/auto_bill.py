"""Add the standard bill the moment a production table is built.

I kept doing this by hand: notice a new stove/butcher spot/stonecutter/art bench,
find its id, then ui.add_bill — and once I stacked a duplicate butcher bill.
This reacts to `built` ledger events only (cheap, no polling).

Verified recipe defNames (defs.get, this episode):
  FueledStove/ElectricStove -> CookMealSimple (TargetCount 20)
  ButcherSpot               -> ButcherCorpseFlesh (Forever)
  TableStonecutter          -> Make_StoneBlocksAny (Forever)
  TableSculpting            -> Make_SculptureSmall (TargetCount 3)
Campfire is deliberately excluded (I run cooking on the stove once one exists).
"""

BILLS = {
    "FueledStove": ("CookMealSimple", "TargetCount", 20),
    "ElectricStove": ("CookMealSimple", "TargetCount", 20),
    "ButcherSpot": ("ButcherCorpseFlesh", "Forever", 0),
    "TableStonecutter": ("Make_StoneBlocksAny", "Forever", 0),
    "TableSculpting": ("Make_SculptureSmall", "TargetCount", 3),
}

# label fragment in the ledger text -> defName (fallback when the event has no def)
LABELS = [
    ("fueled stove", "FueledStove"),
    ("electric stove", "ElectricStove"),
    ("butcher spot", "ButcherSpot"),
    ("butcher table", "ButcherSpot"),
    ("stonecutter", "TableStonecutter"),
    ("art bench", "TableSculpting"),
    ("sculpting", "TableSculpting"),
]


def watch(ctx, events):
    out = []
    for e in events:
        try:
            if e.get("kind") != "built":
                continue
            data = e.get("data")
            if not isinstance(data, dict):
                data = {}
            d = e.get("def") or e.get("defName") or data.get("def") or data.get("defName")
            text = (e.get("text") or "").lower()
            if not d:
                for frag, dd in LABELS:
                    if frag in text:
                        d = dd
                        break
            if d not in BILLS:
                continue
            thing = e.get("thing") or data.get("thing") or data.get("id")
            rec, mode, count = BILLS[d]
            if thing:
                out.append({
                    "type": "action", "method": "ui.add_bill",
                    "params": {"thing": thing, "recipe": rec, "mode": mode, "count": count},
                    "note": "auto bill %s on new %s" % (rec, d),
                })
            else:
                out.append({
                    "type": "alert", "wake": False,
                    "text": "new %s built but no thing id in event; add %s by hand" % (d, rec),
                })
        except Exception:
            pass
    return out
