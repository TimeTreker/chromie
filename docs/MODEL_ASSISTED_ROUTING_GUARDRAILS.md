# Model-Assisted Routing Guardrails

This document records the routing safety rule for Chromie's small Router model,
currently configured as `qwen3:0.6b` in common profiles.

## Position

The Router model is a fast semantic helper. It may propose a route for normal
requests, but it is not the authority for understanding, execution, safety, or
physical behavior.

Chromie must treat model-assisted routing as advisory control-plane data. A
wrong model answer should be caught by deterministic controls, catalog
constraints, schema validation, runtime policy, provider refusal, or
clarification fallback before it can become a harmful action.

The current runtime uses a staged route pipeline:

```text
emergency filter
  -> quick intent router
  -> deep_thought handoff when quick confidence is low or planning is needed
  -> schema/runtime/provider validation
```

The emergency filter is deterministic and fastest. The quick intent router is
normally the small Router model (`qwen3:0.6b`) with catalog candidates and
bounded context. The deepthinking Agent uses the larger Agent model for
low-confidence or explicitly complex requests.

Every stage may propose high-level tasks or actions. Chromie records those
proposals in `RouteDecision.metadata.route_stage_outputs` and merges them into
`RouteDecision.metadata.task_list`. This task list is not authorization: it is
the inspectable plan substrate that later validators, agents, Skill Runtime,
and providers must accept before anything executes.

## Required layers

1. Deterministic operational controls bypass the model.
   Stop, cancel, emergency, ignore, silence, and unusable-audio paths must stay
   rule-based and deterministic.
2. The capability catalog bounds the model's choices.
   The model may select from known routes, capabilities, or task types. It must
   not invent skills, body controls, hardware state, or hidden provider support.
3. Low confidence means delegate, clarify, or fail closed.
   Ambiguous or low-confidence quick routes should normally enter
   `deep_thought` so the larger model can reason with session memory.
   Unsupported or unavailable requests should ask a question, return a
   structured refusal, or fall back to safe chat/ignore.
   If the quick model returns a deterministic-only operational route such as
   `interrupt` or `ignore` after the emergency filter has already passed, the
   Router does not let that model output stop the robot. Clear body commands
   with executable catalog candidates are recovered as `robot_action` for Agent
   capability planning; non-action cases are delegated or clarified.
4. Schemas and policies revalidate everything.
   `RouteDecision`, `InteractionResponse`, Skill Runtime requests, TaskGraphs,
   and MCP calls must be validated after model output is produced.
5. Runtime registries remain authoritative.
   The Agent capability registry and host Skill Registry must resolve
   capabilities again before execution. Router output alone never authorizes a
   provider call.
6. Soridormi remains authoritative for the body.
   Chromie can request high-level goals such as `approach_target` or
   `navigate_to_location` only when Soridormi declares them. Soridormi preview,
   refusal, task events, cancellation, and safe-idle status decide the embodied
   result.
7. Physical execution requires separate evidence.
   No model route, TaskGraph, or natural-language answer can claim physical
   completion without retained simulator or commissioned hardware evidence for
   that exact path.

## Failure posture

If the model chooses the wrong route, the expected outcome is not "execute the
wrong action." The expected outcome is one of:

- deterministic interrupt/ignore handling wins before model routing;
- an invalid model `interrupt`/`ignore` after that filter is recovered to
  catalog-bounded `robot_action` only when the text clearly asks for body action;
- the quick Router model returns low confidence and Chromie delegates to
  `deep_thought`;
- catalog or schema validation rejects the route;
- native InteractionRuntime corrects or refuses the route;
- Skill Runtime cannot resolve or authorize the skill;
- Soridormi refuses or blocks the task with reason metadata;
- Chromie asks for clarification.

## Next work implications

Before broadening rich embodied routing, add tests and acceptance cases that
prove model-assisted routes cannot bypass:

- emergency-filter deterministic routing;
- capability-catalog availability;
- confidence thresholds;
- strict low-level-field rejection;
- request-bound confirmation;
- Soridormi task preview/refusal/event monitoring;
- physical-motion gates.

This guardrail applies whether the small Router model is Qwen, another local
model, or a future classifier. Model quality can improve routing convenience,
but safety must come from bounded contracts and deterministic runtime policy.
