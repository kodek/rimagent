from rimagent.registry import tool


@tool("letter_triage",
      "One-call pending-letter decision table: every letter on screen with its id, "
      "label, choices, and a recommended choice + one-line reason. Collapses the "
      "rw_state_letters + reasoning loop so you can then issue rw_ui_letter choices "
      "in a batch. Run when pending_letters > 0 instead of reading letters one by one.",
      {})
def letter_triage(ctx):
    try:
        letters = ctx.bridge.call("state.letters")
    except Exception as e:
        return {"error": f"state.letters failed: {e}", "letters": []}
    if not isinstance(letters, list):
        letters = (letters or {}).get("letters", []) if isinstance(letters, dict) else []

    out = []
    for L in letters:
        if not isinstance(L, dict):
            continue
        lid = L.get("id")
        label = (L.get("label") or L.get("text") or "").strip()
        choices = L.get("choices") or []
        if isinstance(choices, dict):
            choices = list(choices.keys())
        rec, why = _recommend(label, choices)
        out.append({
            "id": lid,
            "label": label[:120],
            "choices": choices,
            "recommended": rec,
            "reason": why,
        })
    return {"pending": len(out), "letters": out}


def _recommend(label, choices):
    t = label.lower()
    # order matters: most specific first
    if any(k in t for k in ("raid", "attack", "war", "enemy", "hostile")):
        return "Accept", "engaging a raid is the default; reject only if you have a reason to ignore it"
    if "quest" in t:
        # default: accept small/neutral quests, reject ones that send pawns far away
        return (choices[0] if choices else "Accept"), \
            "read the quest text; accept if it is local and the reward is worth it, reject if it sends pawns far from base"
    if "trade" in t or "caravan" in t or "merchant" in t:
        return "Accept", "trade caravans are net-positive early (steel, cloth, components); accept"
    if "refugee" in t or "arriving" in t or "join" in t:
        return "Accept", "colonists add workforce; accept unless you are at bed/food capacity"
    if "letter" in t or "diplomat" in t or "faction" in t:
        return "Accept", "diplomatic letters are usually harmless; accept to keep relations"
    if "gift" in t or "tribute" in t:
        return "Accept", "accept the gift"
    # fallback: first choice, flag for manual review
    return (choices[0] if choices else None), \
        "UNRECOGNIZED LETTER - read the full text and decide manually before choosing"
