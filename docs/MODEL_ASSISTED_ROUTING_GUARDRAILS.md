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

## Required layers

1. Deterministic operational controls bypass the model.
   Stop, cancel, emergency, ignore, silence, and unusable-audio paths must stay
   rule-based and deterministic.
2. The capability catalog bounds the model's choices.
   The model may select from known routes, capabilities, or task types. It must
   not invent skills, body controls, hardware state, or hidden provider support.
3. Low confidence means clarify or fail closed.
   Ambiguous, low-confidence, unsupported, or unavailable requests should ask a
   question, return a structured refusal, or fall back to safe chat/ignore.
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
- catalog or schema validation rejects the route;
- native InteractionRuntime corrects or refuses the route;
- Skill Runtime cannot resolve or authorize the skill;
- Soridormi refuses or blocks the task with reason metadata;
- Chromie asks for clarification.

## Next work implications

Before broadening rich embodied routing, add tests and acceptance cases that
prove model-assisted routes cannot bypass:

- quick-control deterministic routing;
- capability-catalog availability;
- confidence thresholds;
- strict low-level-field rejection;
- request-bound confirmation;
- Soridormi task preview/refusal/event monitoring;
- physical-motion gates.

This guardrail applies whether the small Router model is Qwen, another local
model, or a future classifier. Model quality can improve routing convenience,
but safety must come from bounded contracts and deterministic runtime policy.
