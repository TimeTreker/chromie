# Social Attention Behavior Domain

## Decision

Social Attention is a high-level behavior domain, not one fixed skill and not a
phrase-to-action routing rule. During interaction, the model may coordinate
context-appropriate language expression, gaze, blink, nod, head orientation,
posture, another catalog-supplied behavior, or no expression.

The deterministic host never maps phrases such as "pay attention" or "I am
sad" to a fixed gesture. It supplies context and the eligible capability
catalog, then validates the model-authored plan.

## Two interaction roles

### Explicit user goal

When the user requests a concrete action, for example "blink twice" or "look at
me for two seconds", that action remains a normal CanonicalPlan goal. It is not
optional and cannot be replaced with a different social gesture.

The behavior may still be classified in the `social_attention` domain for
observation and analysis, but its interaction role is
`explicit_user_goal`.

### Auxiliary expression

When the model adds language style or body expression to support the
interaction, the role is `auxiliary_expression`. It is advisory, lower priority
than the user task, and may be dropped on target uncertainty, resource conflict,
confirmation requirements, invalid parameters, or latency pressure.

Auxiliary expression can never satisfy, replace, or claim completion of a user
goal.

## Model-owned plan

The model authors:

- the social purpose, such as listening, empathy, acknowledgement, engagement,
  turn taking, deference, or neutral presence;
- whether expression is useful;
- language style and pacing adaptation;
- zero or more exact capability IDs from the supplied candidates;
- capability arguments, timing, social function, and target selection.

A plan may use body expression, speech adaptation, both, or neither. The
Response Composer owns coordination of the actual response text and the
auxiliary body plan so they express one coherent purpose. The standalone native
compatibility planner remains body-only and sets speech adaptation to `none`.

Example shape:

```json
{
  "behavior_domain": "social_attention",
  "interaction_role": "auxiliary_expression",
  "purpose": "empathy",
  "decision": "express",
  "speech_expression": {
    "mode": "adapt",
    "style": "empathetic",
    "pacing": "slower",
    "reason": "Match the user's emotional state."
  },
  "behaviors": [
    {
      "skill_id": "soridormi.look_at_person",
      "args": {"target_ref": "current_speaker"},
      "timing": "parallel",
      "social_function": "maintain_engagement"
    }
  ]
}
```

## Capability discovery

Capabilities declare one or more behavior domains. The checked-in
`capabilities/behavior_domains.json` supplements provider metadata for current
Soridormi skills. Candidate discovery selects available, interaction-executable
catalog entries tagged `social_attention`.

`AGENT_SOCIAL_ATTENTION_CAPABILITIES` is an optional operator allow-list or
extension, not the primary fixed candidate list. Its default is empty.

A capability may belong to multiple domains. A head turn can express social
attention, perception, navigation, or safety depending on the model-authored
purpose and owning task. Capability taxonomy does not decide the plan.

## Host authority

The host may:

- validate exact catalog membership and argument schemas;
- verify target evidence;
- enforce confirmation and safety policy;
- reject low-level motor fields;
- detect resource conflicts with the primary plan;
- cap auxiliary behavior count;
- drop invalid auxiliary expression;
- record execution and user-outcome evidence.

The host may not:

- inspect user phrases to select a social skill;
- replace an explicit requested action;
- generate a gesture sequence from a social purpose;
- invent a conversational answer or emotional interpretation;
- let auxiliary expression delay or override the user task.

## Testing

Black-box tests classify both explicit and auxiliary actions in the stable
`social_attention` observation domain while preserving their different
interaction roles. Abstract requests such as "show that you are listening"
should be judged for contextual appropriateness without requiring one specific
skill. Concrete requests such as "blink twice" require the exact observable
count.
