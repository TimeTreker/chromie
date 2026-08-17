# Single Semantic Planning Authority

## Purpose

Chromie permits exactly one semantic planning authority for one routed turn.
Routing, observation, schema validation, skill adaptation, confirmation, and
execution may involve multiple components, but they must not independently
reinterpret the same user goal after an authoritative planner has started.

The Cognitive Gateway precedes this semantic boundary. It owns ingress,
protective reflexes, and attention/admission, but not goal meaning or planning.
The Goal-Driven Cognitive Core, implemented today by the unified Goal-driven
Runtime for acquired lanes, is the semantic planning authority.

This boundary is separate from robot validation. It can be automatically
verified without a GPU, Ollama, Soridormi, MuJoCo, a microphone, or physical
hardware. Live services are still required to validate model quality and robot
behavior.

## Maintained invariant

A turn carries one `context.semantic_authority` claim. The claim records an
owner and one of three roles:

- `authoritative`: may resolve user goals and produce the semantic plan;
- `observer`: may produce comparison evidence but cannot commit or execute;
- `adapter`: may validate and materialize an already-selected exact action but
  cannot reinterpret the utterance.

After the Goal-Driven Cognitive Core's current Goal-driven Runtime acquires
authoritative ownership, any planning, composition, host-validation, or
state-commit failure is fail-closed. The same turn cannot re-enter the legacy
CapabilityAgent planner.

Speech composition and user-task execution may be prepared or scheduled
independently from immutable projections of that authoritative turn. Parallel
output preparation does not create another semantic owner: a response composer
cannot reinterpret Goals or authorize effects, and an execution specialist
cannot become the conversation authority. Wording ownership is per conversational
act: a Fast-Planner immediate conversational Activity, a Tool Result
act, and a Response-Composition act each retain exactly one writer, while later
stages may only bind/reuse the exact act or author a genuinely different delta.

Cross-cutting evidence qualification, retention/privacy policy, and bounded
adaptation are not additional semantic owners. They refine factual/context input to
existing owners and cannot inherit downstream Goal, Plan, authorization, or effect
authority.

Single semantic authority does not freeze capability granularity. A provider may
change which bounded capabilities it advertises as its implementation improves.
Chromie plans only across the capabilities visible in the current catalog: one
provider capability may cover a complete Goal today, while the same Goal may require
a composition of several advertised capabilities on another body or provider
version. A provider may plan arbitrarily deeply inside an already-selected
capability, but it cannot reinterpret the user Goal or plan across capabilities it
does not own. The live capability contract, not a permanent architectural layer or
capability name, is the decomposition boundary.

## Current compatibility boundary

The service currently named Goal Interpreter still performs the deployed emergency
filter and addressedness review in addition to Fast semantic interpretation. Its
maintained model-facing contract emits provider-neutral `responsibilities[]`, material
bindings, and optional immediate communication. It does not author Work, Primary
Activities, Plan structure, execution lanes, realization, Capability IDs, executable
arguments, provider requests, or `actions[]`; Goal Association owns canonical Goal
state and Planner owns the first Work/Activity contract. The shared `RouteDecision` and legacy Agent
entrypoints retain older action/task fields only as compatibility surfaces. Those
fields are not current Fast Goal Interpreter authority and cannot become a second
semantic plan after the Goal-driven Runtime acquires a turn.

## Entrypoint ownership

| Entrypoint | Semantic owner | Role | Planner path | Failure behavior |
|---|---|---|---|---|
| Orchestrator turn in `apply`; mapped route lane is allowlisted and apply preconditions pass | Goal-Driven Cognitive Core (current Goal-driven Runtime) | authoritative | Goal Interpretation → Responsibility evidence → pre-Goal Fast Planner advancement → optional immediate Activity + optional Goal Association → canonical Fast/Deep Planner when required → Response Composer → trusted adapter | Fail closed after ownership is acquired. |
| Orchestrator turn in `apply`; mapped route lane is excluded | Goal-Driven Cognitive Core policy boundary | authoritative fail-closed | No semantic planner is entered; deprecated externally supplied `actions[]` remain unexecuted compatibility input only | Return a typed no-action/error outcome without legacy semantic re-entry. |
| Orchestrator turn in `report_only` | Goal-Driven Cognitive Core (current Goal-driven Runtime) | observer | Same stages, evidence only | The existing routed Agent path remains the only authority. |
| Agent `/interaction` or `/run` with deprecated exact `actions[]` compatibility input | No new semantic planner; legacy action materializer | adapter | Schema validation and `CapabilityRequest` materialization only | Invalid actions are blocked or clarified; no LLM reinterpretation and no claim that Fast Goal Interpretation authored them. |
| Explicit compatibility emergency | Legacy CapabilityAgent | authoritative | Legacy capability semantic planner | Requires both service gates and a per-turn emergency claim. |

The maintained direct speech-only path is Fast-Planner-owned. Goal Interpretation emits
Responsibility evidence only. Fast Planner may determine that a simple non-effectful
conversational Responsibility is completeable immediately, author the conversational
Activity, and return no Goal/Deep continuation; Runtime then delivers it through the
trusted Vocal path without creating a persistent Goal or invoking Response Composer for
the same act. This changes latency, not effect authority. Capability-dependent reads are
not this terminal branch; Fast Planner requests Goal Association for their persistent
fresh-evidence responsibility and factual speech follows trusted execution evidence.

When Goal Association explicitly binds one Goal with `entity_type=action_list`,
Fast and Deep Planning require a bounded model-authored semantic completeness
audit before accepting an effectful Plan. The audit can only accept or reject;
it cannot add steps, choose a Capability, revise the Plan, or authorize
execution. Fast rejection escalates to Deep Planning. Deep rejection or audit
unavailability removes every executable step and returns clarification. This is
a fail-closed validation of the current Planner's coverage claim, not another
planning authority or a Host phrase-to-action rule.

`GET /semantic-authority` exposes the same machine-readable route matrix from
the Agent service.

## Legacy CapabilityAgent status

The CapabilityAgent remains in the repository for compatibility evidence and
emergency operation. In normal operation it is an adapter:

1. Deprecated compatibility `actions[]` supplied directly to legacy Agent entrypoints
   are validated and converted to `CapabilityRequest` objects without calling the
   CapabilityAgent LLM. Current Fast Goal Interpretation does not author this field.
2. A robot-action request without exact actions cannot invoke the old semantic
   planner by default.
3. The old planner runs only when all three conditions are true:
   - the Agent has `AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=1`;
   - the Orchestrator attaches a valid per-turn
     `legacy_capability_fallback` claim with `emergency_fallback=true` and a
     non-empty `turn_id` exactly matching the Agent request `sid`.

The two environment variables alone are not enough. The claim's exact turn
binding rejects an empty or cross-turn claim from silently widening authority.
This internal routing claim is not caller authentication and is not stored as a
single-use nonce: replaying the same valid claim with the same `sid` is not
independently prevented here. Keep the endpoint on its trusted network boundary
and keep both emergency gates off during normal operation.

The maintained launcher and common profiles keep the Agent emergency gate off.
The Host has no direct-LLM semantic rollback surface: once Goal-driven authority
is acquired, failures remain fail-closed and may only use bounded Host-owned
failure facts rather than transferring semantic authority to another planner.

## Disabled lanes versus failed authoritative turns

In the current compatibility topology, the Orchestrator first maps Goal Interpreter
routes to semantic lanes: `chat`, `clarify`, and `deep_thought` map to `chat`;
`robot_action`, `tool`, and `memory` retain their lane names; everything else
maps to `unsupported`. A mapped lane excluded by `ORCH_COGNITIVE_APPLY_LANES` fails closed before the
Goal-driven Runtime starts. It does not enter the retained CapabilityAgent
semantic planner, regardless of emergency-gate state. This lane mapping does
not make the Cognitive Gateway the owner of goal meaning.

Once Goal Association begins under authoritative `apply`, there is no
same-turn compatibility fallback. Technical failure, terminal-lane mismatch,
response-composition failure, trusted runtime rejection, or Goal-state commit
failure produces truthful no-action output and an `error` resolution.

## Offline equivalence and regression evidence

The migration keeps old planner behavior covered as explicitly labelled
emergency-fallback tests while adding boundary tests that establish:

- exact Goal Interpretation actions produce the same validated skill requests with the LLM
  available or unavailable;
- the CapabilityAgent LLM call count remains zero on adapter-only requests;
- neither a service gate nor a per-turn claim alone can enable the old planner;
- empty and mismatched turn claims are rejected before any LLM call;
- both gates plus the emergency claim enable the retained compatibility planner;
- Goal-driven failures never emit a `legacy_fallback` status;
- allowlisted mapped lanes at apply name Goal-driven Runtime as their only
  authority after acquisition, while excluded mapped lanes fail closed without
  legacy semantic re-entry;
- maintained profiles use `apply`, `fail_closed`, and disabled legacy gates.

Run the dependency-light audit with:

```bash
python scripts/semantic_authority_audit.py --check
```

Run the relevant regression tests with:

```bash
PYTHONPATH=agent:. python -m unittest -v tests.test_semantic_authority
```

These checks establish code-path ownership and deterministic adapter
compatibility. They do not establish live-model semantic quality or robot
execution correctness.

## Live validation still required

On the NVIDIA workstation, retain evidence for:

- real Goal Association and Planner outputs across common and ambiguous turns;
- execute-plus-clarify multi-goal continuation;
- terminal interrupt handling without post-interrupt semantic re-entry;
- Soridormi/MuJoCo skill execution and safe-idle closure;
- voice ASR/TTS behavior.

A live failure does not reopen the old planner during the same turn. Recovery
must start a new turn or use an explicitly initiated emergency compatibility
operation.

## Exact skill identity in compatibility planning

Even under the explicitly enabled emergency compatibility planner, the selected
named skill and its semantic arguments remain model-authored. The CapabilityAgent
may validate the selected skill against the live catalog and validate or repair
arguments against that same skill schema, but it must not substitute a nearby
skill, translate one skill's arguments into another schema, or clamp values as a
semantic rewrite. Invalid output fails closed or returns to model repair.
