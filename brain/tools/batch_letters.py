from rimagent.registry import tool


@tool("batch_letters",
      "Issue all recommended letter choices in one call. Reads pending letters, "
      "applies the same recommendation logic as letter_triage, and issues "
      "rw_ui_letter for each. Returns what was chosen and any failures. "
      "Replaces N rw_ui_letter calls with one.",
      {"only_unrecognized": "if true, only issue choices for unrecognized letters (skip raid/trade/refugee auto-accepts)"})
def batch_letters(ctx, only_unrecognized=False):
    try:
        letters = ctx.bridge.call("state.letters")
    except Exception as e:
        return {"error": f"state.letters failed: {e}", "issued": []}

    if not isinstance(letters, list):
        letters = (letters or {}).get("letters", []) if isinstance(letters, dict) else []

    if not letters:
        return {"pending": 0, "issued": [], "note": "no pending letters"}

    results = []
    for L in letters:
        if not isinstance(L, dict):
            continue
        lid = L.get("id")
        label = (L.get("label") or L.get("text") or "").strip()
        choices = L.get("choices") or []
        if isinstance(choices, dict):
            choices = list(choices.keys())

        rec, why, auto = _recommend(label, choices)
        if only_unrecognized and auto:
            results.append({"id": lid, "label": label[:80], "skipped": True,
                            "recommended": rec, "reason": why})
            continue
        if rec is None:
            results.append({"id": lid, "label": label[:80], "skipped": True,
                            "recommended": None, "reason": "no choice available"})
            continue
        try:
            r = ctx.bridge.call("ui.letter", id=lid, action="choose", choice=rec)
            ok = not (isinstance(r, dict) and r.get("error"))
            results.append({"id": lid, "label": label[:80], "choice": rec,
                            "ok": ok, "result": r if not ok else None,
                            "reason": why})
        except Exception as e:
            results.append({"id": lid, "label": label[:80], "choice": rec,
                            "ok": False, "error": str(e)})

    issued = [r for r in results if not r.get("skipped")]
    return {"pending": len(letters), "issued": issued,
            "note": f"{len(issued)} letters handled, {len(letters)-len(issued)} skipped"}


def _recommend(label, choices):
    """Same logic as letter_triage, but returns (choice, reason, is_auto).
    is_auto=True means the choice is a safe default (raid/trade/refugee/diplomatic).
    is_auto=False means it needs manual review."""
    t = label.lower()
    if any(k in t for k in ("raid", "attack", "war", "enemy", "hostile")):
        return "Accept", "raid: accept to engage", True
    if "trade" in t or "caravan" in t or "merchant" in t:
        return "Accept", "trade: accept (steel, cloth, components)", True
    if "refugee" in t or "arriving" in t or "join" in t:
        return "Accept", "refugee: accept (adds workforce)", True
    if "gift" in t or "tribute" in t:
        return "Accept", "gift: accept", True
    if "letter" in t or "diplomat" in t or "faction" in t:
        return "Accept", "diplomatic: accept to keep relations", True
    if "quest" in t:
        # Quests need manual review: accept if local, reject if sends pawns far
        return (choices[0] if choices else None), \
            "quest: read text, accept if local, reject if sends pawns far", False
    # Beggars / resource requests: usually reject (costs resources, low reward)
    if "beggar" in t or "request" in t or "resources" in t:
        # Find the reject-like choice
        for c in choices:
            if "reject" in c.lower() or "refuse" in c.lower() or "decline" in c.lower():
                return c, "resource request: reject (low reward, costs resources)", True
        return (choices[-1] if choices else None), "resource request: reject", True
    # Fallback: first choice, flag for manual review
    return (choices[0] if choices else None), "UNRECOGNIZED - manual review", False
