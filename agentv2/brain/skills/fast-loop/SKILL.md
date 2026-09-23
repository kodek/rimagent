---
name: fast-loop
description: Pull in before you write, edit, test, label or promote a fast-loop policy (brain/policies/*.yaml), or when the Fast loop section shows escalations, disagreements or an invalid policy.
metadata:
  wake-on: "fast loop, policy, escalat, jev, directive"
---
# The fast loop

The fast loop runs your policies beside you, all the time. Each decision is one Jev request: about 0.3 s, a fraction of
a cent. Jev answers yes/no (noul), choice and score questions about a JSON state with probabilities. It cannot write
text, count, do math or compare dates, and more unrelated text makes it worse. So:
- Ask small, literal questions, one condition each. Put the edge cases into the criteria text.
- Give numbers as the colony features do: `food: "4.5 (low: under 5 days)"`. Jev reads the band, not the number.
- Every choice that acts has an `escalate` label that says when you must decide.

## What Jev sees
`{"directive": <your purpose, priorities_in_order, never, report_when, guidance for this policy's domain>, "colony": <the
features the policy lists>, <the thing: "event", "letter", "dialog" or "posture">}`. Without a valid directive the
directive is "none", and a policy only watches unless it has `safe_without_directive: true`. When the directive has
`report_when`, the loop adds the question report_up itself and escalates when it fires.

## The format
```yaml
description: one line
subject: letters            # events | letters | dialogs | posture
domain: letters             # optional: the key of set_directive(guidance=...); default the subject
triggers:
  events: [letter, quest]   # ledger kinds that run it
  every_seconds: 30         # and/or every_hours: 2 (in-game)
claims: [letter]            # optional: events it answers instead of waking you (letters: letter; dialogs: dialog)
features: [time, colonists, food, mood, danger, hostiles]   # also: wealth, research, steward, alerts
questions:
  reply:
    type: choice
    instructions: Which reply to this letter serves the directive best?
    options_from_subject: true          # the letter's, dialog's or posture's own options become labels
    criteria: {escalate: When you must decide.}   # more labels, or descriptions for the options
  risky:
    type: noul
    instructions: Does accepting put a colonist's life at risk?
    criteria: {"true": ..., "false": ...}
  urgency:
    type: score
    instructions: How soon must the colony act?
    criteria: [not at all, within a day, within hours, now]   # 2-10 levels, lowest first
decide:
  act_with: reply           # the choice whose label the subject carries out (events cannot act)
  min_confidence: 0.6       # below it: on_doubt (escalate or skip)
  vetoes: {risky: 0.5}      # a noul at or above -> no action, it escalates; an acting policy needs one
  escalate_if: {urgency: 2.5}   # noul probability or expected score at or above -> escalate
  dwell_hours: 3            # in-game hours between two actions on the same thing
params: {hours: 6}          # posture: how long a posture lasts
budget: {calls_per_minute: 30, actions_per_hour: 6}
safe_without_directive: false
```
What each subject does with the label it acts with: letters `ui.letter` (choose), dialogs `ui.dialog`, posture
`steward.posture` (preset). An events policy only escalates. A veto sends the whole decision to you, whatever label won.

## Stages and evidence
shadow (logs what it would do) -> canary (acts gate.canary_actions times) -> active. `promote_policy` checks the
evidence: shadow -> canary needs held-out labels that agree; canary -> active needs actions without failures or wrong
labels. An edited file is a new version and starts in shadow again. The loop demotes a version whose actions are
labelled wrong. The operator can set any stage from the dashboard.

## Labels
- Your own answer to a letter, a dialog or a posture after the loop looked at it labels its decision automatically.
- `list_decisions(show="unlabelled")`, then `label_decisions([{id, truth, note}])`: truth is an option label, `escalate`
  (you had to decide) or `none` (nothing to do). Judge with hindsight: what happened after it.
- About a third of the decisions are held out: you never see their labels, and only the gate scores on them.

## Improve a policy
1. `list_decisions(policy=..., show="disagreements")`: where it and the labels differ.
2. Edit the question or the criteria text: name the case it got wrong, literally. Add a label or a feature if it
   lacked one.
3. `replay_policy(name)`: the new text on the labelled decisions you can see, against the labels and the old verdicts.
4. `test_policy(name)` on the live game, then `promote_policy(name)` when it is ready.
Write a new policy when you make the same kind of judgment by hand again and again.
