# Quick Router Task Planning

This document records the task-planning contract for Chromie's fast Router
model and the deterministic validation layer around it.

## Design Position

The second Router is both a router and a bounded fast planner.

It uses the latest ASR text, compact session context, and the common skill
catalog to decide:

- which route should handle the request;
- whether the request can be represented by common skills immediately;
- which exact common skill tasks to propose;
- how confident it is in each proposed task.

This is why the stage is called quick: it uses a small model and a compact
common catalog. It is not limited to one task.

## Output Contract

For a single clear common skill, the Router may return:

```json
{"route":"robot_action","intent":"capability:soridormi.blink_eyes","confidence":0.91}
```

For a compound common-skill request, the Router may return:

```json
{
  "route": "robot_action",
  "intent": "compound_common_catalog_task",
  "confidence": 0.87,
  "actions": [
    {
      "capability_id": "soridormi.walk_forward",
      "args": {"duration_s": 20},
      "sequence": 0,
      "timing": "sequential",
      "confidence": 0.91
    },
    {
      "capability_id": "chromie.speak",
      "args": {"text": "A short joke selected by the model."},
      "sequence": 1,
      "timing": "parallel",
      "confidence": 0.86
    }
  ]
}
```

Each action confidence is the model's confidence in that specific skill choice
and its arguments. It is separate from the whole-route confidence.

## Speech Is A Skill

Chromie should not treat speech and body action as fundamentally different
planner outputs. Speaking is a skill task when it is part of the user-requested
work.

In mixed requests, use `chromie.speak` with `args.text`. Do not hide that speech
inside unstructured chat text, and do not emit a fake spoken acknowledgement that
claims a body action happened.

## Validation

Deterministic validation does not choose the normal activity. It only checks
the task proposals before they can enter the executable task surface:

- every `capability_id` exists in the supplied common catalog;
- every non-speech action is available and interaction-executable;
- `chromie.speak` includes non-empty `args.text`;
- each action confidence is valid and above the Router threshold;
- no placeholder skill ID or raw low-level robot command is accepted.

When accepted, the Router copies action confidence into `metadata.task_list[]`
and `metadata.task_proposals[]`. The Agent also copies it into each emitted
`SkillRequest.metadata.router_action_confidence` for later trace evidence.

## Low-Confidence Handoff

If a required action in a compound plan is below confidence threshold, Chromie
must not execute only the high-confidence subset. The whole quick plan delegates
to `deep_thought`.

The handoff may include a short truthful thinking prelude:

```json
{
  "route": "deep_thought",
  "intent": "deep_thought_low_confidence",
  "speak_first": "Give me a moment to think that through."
}
```

That prelude is a speech task for the user experience. It must not claim
execution, completion, memory writes, tool results, or physical success.

The Router preserves the quick proposal ledger in
`metadata.quick_router_review_request`:

```json
{
  "schema_version": 1,
  "review_status": "needs_review",
  "execution_state": "not_committed",
  "quick_route": "robot_action",
  "quick_intent": "compound_common_catalog_task",
  "quick_actions": [],
  "quick_task_list": [],
  "quick_task_proposals": []
}
```

Deepthinking receives this object in upstream route context and must answer
through its own `quick_review` field:

```json
{
  "tasks": [],
  "quick_review": {
    "decision": "accept|revise|supersede",
    "reason": "short review note",
    "superseded_task_ids": []
  },
  "reason": "short audit note"
}
```

When the decision is `revise` or `supersede`, the Agent records
`superseded_task_proposals` so the Orchestrator ledger can show which quick
proposal was replaced by deepthinking output.

## Merge Model

The Orchestrator treats Router output as task proposals, not as final
authorization.

The merge policy is:

- deterministic emergency tasks have priority and can be applied immediately;
- quick Router common-skill tasks are accepted only after validation;
- low-confidence, invalid, rare, or complex proposals are delegated to
  deepthinking;
- deepthinking may accept, revise, or supersede quick proposals;
- Skill Runtime and Soridormi remain the final execution authority for embodied
  skills, safety, monitoring, cancellation, confirmation, and completion.

## Parallel Compute Boundary

If the computer has enough compute, the Orchestrator may later start a
preliminary deepthinking pass in parallel with the quick Router. That
optimization must still use the same commit rules:

- quick high-confidence low-risk tasks may commit only after validation;
- quick low-confidence or invalid tasks stay `not_committed`;
- deepthinking must receive `quick_router_review_request` before it is allowed
  to accept, revise, or supersede a concrete quick task list;
- if a preliminary parallel deepthinking pass started before quick output was
  available, it is advisory only and cannot be used as the final review of
  quick proposals unless a follow-up review includes those proposals.

The implemented substrate is therefore the shared review ledger first, and
parallel scheduling can be added without changing the model-facing task
contract.

## Plan

1. Keep the common/rare catalog split owner-curated.
2. Keep all common skills compact enough for the quick Router prompt.
3. Require `actions[].confidence` for compound quick plans.
4. Reject or delegate malformed and low-confidence action proposals before they
   reach Agent execution.
5. Pass low-confidence quick proposals to deepthinking through
   `quick_router_review_request`.
6. Preserve confidence and accept/revise/supersede decisions in Router and Agent
   task evidence.
7. Add real daily-life scenarios whenever a live voice or simulator run reveals
   a confusing behavior.
