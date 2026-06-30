# Model-Assisted Routing Guardrails

This document records the routing safety rule for Chromie's small Router model,
currently configured as `qwen3:0.6b` in common profiles.

## Position

Generalization ability is a core project principle. Normal user-facing
behavior should come from model understanding plus bounded contracts, not from
expanding phrase lists. Prompt examples are teaching signals for the model;
they must not become the implementation of normal conversation, tool, memory,
robot-action, capability-selection, or deep-thought behavior.

The Router model is a fast semantic helper. It may propose a route for normal
requests, but it is not the authority for understanding, execution, safety, or
physical behavior.

Chromie must treat model-assisted routing as advisory control-plane data. A
wrong model answer should be caught by deterministic controls, catalog
constraints, schema validation, runtime policy, provider refusal, or
clarification fallback before it can become a harmful action.

The current runtime has three decision stages, with validation guardrails
between them:

```text
emergency filter
  -> quick intent router
  -> route validation guardrails
  -> deep_thought handoff when quick confidence is low or planning is needed
  -> schema/runtime/provider validation
```

The emergency filter is deterministic and fastest. The quick intent router is
normally the small Router model (`qwen3:0.6b`) with catalog candidates and
bounded context. Route validation is deterministic but does not answer the user:
it only corrects capability-contract, availability, and safety impossibilities
and must not become another intent-understanding stage. The deepthinking Agent
uses the larger Agent model for low-confidence or explicitly complex requests.

The ownership invariant is:

- only the emergency filter may use rules or phrase patterns to determine a
  route;
- quick intent for normal language belongs to the catalog-bounded small Router
  model, not to regexes;
- capability selection belongs to the Agent model interpreting the user request,
  capability descriptions, and schemas, not to action phrase lists;
- deep reasoning, planning, and low-confidence correction belong to
  `deepthinking_agent`;
- spoken response quality for normal conversation belongs to model-based
  semantic review, not to phrase-pattern rejection lists in Agent code;
- spoken responses should answer directly and should not repeat, quote, or
  paraphrase the user's current words unless confirmation, clarification, or an
  explicit read-back is needed;
- deterministic validators may reject, repair, or clarify unsafe/impossible
  model outputs, but they must not answer knowledge questions or select normal
  chat/tool/memory/body intent by phrase matching.

Every stage may propose high-level tasks or actions. Chromie records those
proposals in `RouteDecision.metadata.route_stage_outputs` and merges them into
`RouteDecision.metadata.task_list`. This task list is not authorization: it is
the inspectable plan substrate that later validators, agents, Skill Runtime,
and providers must accept before anything executes.

The host can act on the first safe part of that substrate before every slower
proposal has arrived. Today this is limited to `ORCH_FAST_FIRST_RESPONSE_ENABLED`
speech: a short route-level phrase such as `Checking.` or `I'll answer.` after
Router returns. It is provisional and correctable. Later Agent or deep-thinking
output can amend the turn, ask a clarification, or cancel/stop work, but the
first phrase must never claim that a physical action or tool side effect has
already happened.

## Required layers

1. Deterministic operational controls bypass the model.
   Stop, cancel, emergency, ignore, silence, and unusable-audio paths must stay
   rule-based and deterministic. These hard filters should stay narrow and
   high-confidence; ambiguous or negated stop-related text should continue to
   quick intent routing. In code, `router/app/rules.py` is reserved for this
   narrow hard-control layer and may only produce `interrupt` or `ignore`,
   including obvious repeated filler or acknowledgment ASR hallucinations. Broad
   phrase routing and regex action parsing must not become normal hybrid
   language understanding.
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
   Router does not let that model output stop the robot, execute catalog
   motion, or trigger slow deep thought. It falls back to safe chat so the Agent
   can answer or ask for clarification. If the quick model chooses
   `deep_thought`, deterministic code must not override that by phrase
   matching.
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
- an invalid model `interrupt`/`ignore` after that filter falls back to safe
  chat rather than catalog motion or deep-thought detours;
- a model `robot_action` for a factual knowledge question is addressed by the
  Router prompt/review model and, if it reaches conversation, by semantic
  spoken-response review rather than phrase-based Agent rules;
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
