"""A map screenshot with a coordinate grid and numbered marks on buildings (Set-of-Mark), for `look` and the dashboard."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pydantic_ai import BinaryContent, RunContext, ToolFailed
from pydantic_ai.toolsets import FunctionToolset

from ..bridge import Bridge, BridgeError
from ..deps import Deps

WIDTH_PX, HEIGHT_PX = 1024, 768
MAX_MARKS = 60
UNMARKED = ("Wall", "Door", "Fence", "Sandbag", "Conduit", "Barricade", "Embrasure", "Column")


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def annotate(png: bytes, cx: int, cz: int, cells_wide: float, things: list[dict[str, Any]], marks: bool = True) -> tuple[bytes, dict[int, dict[str, Any]]]:
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    wpx, hpx = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cell = wpx / cells_wide

    def px(x: float) -> float:
        return wpx / 2 + (x - (cx + 0.5)) * cell

    def py(z: float) -> float:
        return hpx / 2 - (z - (cz + 0.5)) * cell

    label, mark = _font(max(10, int(cell * 0.9))), _font(max(11, int(cell * 1.1)))
    half_w, half_h = cells_wide / 2, cells_wide * hpx / wpx / 2
    for x in range(int(cx - half_w) - 1, int(cx + half_w) + 2):
        if x % 5 == 0:
            draw.line([(px(x), 0), (px(x), hpx)], fill=(255, 255, 255, 130 if x % 10 == 0 else 70))
            draw.text((px(x) + 2, 2), str(x), fill=(255, 255, 0, 230), font=label)
    for z in range(int(cz - half_h) - 1, int(cz + half_h) + 2):
        if z % 5 == 0:
            draw.line([(0, py(z)), (wpx, py(z))], fill=(255, 255, 255, 130 if z % 10 == 0 else 70))
            draw.text((2, py(z) - 12), str(z), fill=(255, 255, 0, 230), font=label)
    table: dict[int, dict[str, Any]] = {}
    if marks:
        for thing in things:
            pos = thing.get("pos")
            if not pos or any(k in str(thing.get("def", "")) for k in UNMARKED) or len(table) >= MAX_MARKS:
                continue
            n = len(table) + 1
            x, y, r = px(pos[0] + 0.5), py(pos[1] + 0.5), max(7.0, cell * 0.45)
            color = (80, 160, 255, 235) if thing.get("state") == "built" else (255, 80, 80, 235)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(0, 0, 0, 255))
            draw.text((x - draw.textlength(str(n), font=mark) / 2, y - r * 0.8), str(n), fill=(255, 255, 255, 255), font=mark)
            table[n] = {k: thing.get(k) for k in ("id", "def", "state", "rot", "size")} | {"at": pos}
    out = io.BytesIO()
    Image.alpha_composite(img, overlay).convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue(), table


@dataclass(frozen=True)
class MarkedMap:
    image: bytes
    centre: tuple[int, int]
    marks: dict[int, dict[str, Any]]


async def marked_map(bridge: Bridge, x: int | None = None, z: int | None = None, w: float = 60, around: str | None = None,
                     marks: bool = True) -> MarkedMap:
    if around:
        centre = (await bridge.call("map.detail", {"around": around, "w": 4, "h": 4}))["centre"]
    elif x is not None and z is not None:
        centre = [x, z]
    else:
        centre = (await bridge.call("state.base"))["home_center"]
    cx, cz = int(centre[0]), int(centre[1])
    png = await bridge.screenshot(cx, cz, w, WIDTH_PX, HEIGHT_PX)
    detail = await bridge.call("map.detail", {"x": cx, "z": cz, "w": min(60, int(w)), "h": min(60, int(w * HEIGHT_PX / WIDTH_PX) + 2)})
    image, table = annotate(png, cx, cz, w, detail.get("things") or [], marks)
    return MarkedMap(image, (cx, cz), table)


vision = FunctionToolset[Deps](id="vision")


@vision.tool
async def look(ctx: RunContext[Deps], x: int | None = None, z: int | None = None, w: float = 60, around: str | None = None,
               marks: bool = True) -> list[dict[str, Any] | BinaryContent]:
    """Look at the map as an image with a coordinate grid (every 5 cells) and numbered marks on buildings and blueprints.
    Returns [mark table (number -> id, def, cell), image]. End the code with this list to see the image.
    Use rw_map_detail for exact placement.

    Args:
        x: Centre x (default: home).
        z: Centre z (default: home).
        w: Cells wide.
        around: Thing id, pawn or anchor to centre on.
        marks: Draw numbered marks on things.
    """
    try:
        seen = await marked_map(ctx.deps.bridge, x, z, w, around, marks)
    except BridgeError as e:
        raise ToolFailed(str(e)) from e
    return [{"centre": list(seen.centre), "cells_wide": w, "marks": seen.marks,
             "note": "grid lines every 5 cells; yellow labels are x (top) and z (left)"},
            BinaryContent(data=seen.image, media_type="image/png")]
