from rimagent.registry import tool

@tool("build_room",
      "Builds a complete room with walls, floor, and furniture in one call.",
      {"walls_rect": "rect=[minX, minZ, w, h] for the wall outline",
       "floor_rect": "rect=[minX, minZ, w, h] for the floor (inside walls)",
       "furniture": "list of dicts: [{'def': 'Bed', 'at': [x,z], 'rot': 'N'}, ...]"})
def build_room(ctx, walls_rect, floor_rect, furniture=None):
    """
    Automates the multi-call pattern of building a room.
    Example:
    build_room(walls_rect=[10,10,5,5], floor_rect=[11,11,3,3], furniture=[{'def':'Bed','at':[12,12],'rot':'N'}])
    """
    ops = []
    # 1. Walls (outline)
    ops.append({"def": "Wall", "rect": walls_rect})
    
    # 2. Floor (fill)
    ops.append({"def": "WoodPlankFloor", "rect": floor_rect, "fill": True})
    
    # 3. Furniture
    if furniture:
        for item in furniture:
            op = {"def": item["def"]}
            if "at" in item: op["at"] = item["at"]
            if "rot" in item: op["rot"] = item["rot"]
            if "stuff" in item: op["stuff"] = item["stuff"]
            ops.append(op)
            
    return ctx.bridge.call("ui.build_many", ops=ops)
