def watch(ctx, events):
    """Alert when Kat's mood drops below 25% (buffer before 20% major break)."""
    # Only react to relevant events or check state periodically
    # We'll check on day ticks and colonist_downed events
    relevant_kinds = {'day', 'colonist_downed', 'mental_break', 'incident'}
    if not any(e.get('kind') in relevant_kinds for e in events):
        return []
    
    # Read Kat's mood via engine
    try:
        mood = ctx.bridge.call('engine.get', path='Pawn:Human932.needs.mood.CurLevel')
        mood_pct = mood * 100 if mood is not None else None
    except Exception:
        return []
    
    if mood_pct is not None and mood_pct < 25:
        return [{
            'type': 'alert',
            'text': f'Kat mood {mood_pct:.0f}% - below 25% buffer, major break at 20%. Check: did she eat? Is catharsis fading? Build bedroom NOW.',
            'wake': True
        }]
    return []
