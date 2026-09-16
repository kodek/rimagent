from rimagent.registry import event

@event("hostile_group")
def defend_on_raid(ctx, event):
    """
    Automatically sets a defensive posture for 6 hours when a hostile group appears.
    """
    return [
        {
            "type": "action",
            "method": "steward.posture",
            "params": {"label": "defend", "hours": 6},
            "note": f"Automated defense posture triggered by {event.kind}: {event.text}"
        }
    ]
