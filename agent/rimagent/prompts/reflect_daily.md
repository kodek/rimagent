Daily reflection, day {days}. Reason: {reason}

The game is paused. Review what happened since the last reflection and make the brain better at this exact situation. Be concrete: numbers, coordinates, tool names, event kinds, thresholds. Vague advice is worthless.

## Timeline since the last reflection

{timeline}

## Notebook

{notebook}

## Journal (recent)

{journal}

## Skills

{skills_index}

## Scores

{scores}

## What to do, in order

1. Name the 1-3 things that went wrong or cost the most steps in this period (a raid handled late, food_days falling, blueprints nobody built, a tool called with bad params repeatedly, a mental break you saw coming).
2. For each, make ONE durable fix:
   - a skill edit (`skill_read` then `skill_write` with the same name; tighten with the numbers you now know — day of the first raid, how many cells of rice were enough, which door held) or a new skill only if no existing one covers the trigger;
   - a watcher (`watcher_write`) if you reacted to the same event kind more than once by hand (draft fighters on `hostile_group`, unforbid drops on the drop-pod message, wake on `colonist_downed`, flee fire); keep it event-driven and cheap;
   - a tool (`tool_write`) if you repeated the same 3+ call computation (prototype with `run_python` first; check `tool_list` for load errors afterwards).
3. Rewrite the notebook (`notebook_write`, under 6000 chars): current plan for the next 2 days, pawn roles, threats, open problems, what to check next step, key coordinates.
4. `journal_append` exactly one entry if — and only if — you learned something that will be true in the next game too. Otherwise skip it.
5. Call `end_turn` with `wake_in_hours` for the next play step.

Keep visible text to a few lines; the work is in the tool calls.
