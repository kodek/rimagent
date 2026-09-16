"""
Watcher: alert when a manhunter or predator hostile_group event fires.
The correct response is to order the chased colonist to run TO BASE,
NOT to send a second colonist to intercept far away.
"""

MANHUNTER_KEYWORDS = {
    "Manhunter", "manhunter", "MadAnimal", "madanimal",
    "Fleshbeast", "fleshbeast", "Fingerspike", "Toughspike", "Bulbfreak",
    "Wolf", "Cougar", "Bear", "Rat",
}

def _is_manhunter_or_predator(event):
    """Check if a hostile_group event is a manhunter/predator type."""
    text = event.get("text", "")
    data = event.get("data", {})
    # Check event text for manhunter/predator keywords
    for kw in MANHUNTER_KEYWORDS:
        if kw in text:
            return True
    # Check data for LordJob
    lord = data.get("lord", "") or data.get("lord_job", "") or ""
    for kw in MANHUNTER_KEYWORDS:
        if kw in lord:
            return True
    return False


def watch(ctx, events):
    results = []
    for ev in events:
        if ev.get("kind") != "hostile_group":
            continue
        if not _is_manhunter_or_predator(ev):
            continue
        text = ev.get("text", "")
        results.append({
            "type": "alert",
            "text": (
                f"MANHUNTER/PREDATOR: {text} | "
                "DO NOT send a second colonist to intercept far from base. "
                "Order the chased colonist to run TO BASE immediately. "
                "If the manhunter is 50+ cells from base, it is not an immediate base threat. "
                "If a colonist is already downed far from base, assess whether rescue is survivable."
            ),
            "wake": True,
        })
    return results
