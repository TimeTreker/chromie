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
- `observer`: may produce comparison evidence but cannot commit or execute.

After the Goal-Driven Cognitive Core's current Goal-driven Runtime acquires
authoritative ownership, any planning, composition, host-validation, or
state-commit failure is fail-closed. The same turn cannot transfer semantic authority to a retired planner or adapter.

Speech composition and user-task execution may be prepared or scheduled
independently from immutable projections of that authoritative turn. Parallel
output preparation does not create another semantic owner. Planner owns each
Communicative Activity's function, exact words, timing, truth stage, provenance,
and constraints; Goal Interpretation owns none of those fields. Trusted Runtime
and Host bind terminal results to exact request/Goal provenance as Evidence, then
reactivate Fast Planner. Result contents cannot bypass Planner or infer their own
Goal. A later Planner pass may omit an already-delivered act or author a genuinely
different delta.

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

## Approved semantic boundary

Goal Interpretation performs WHAT-only semantic interpretation. Its target model-facing
contract emits provider-neutral `responsibilities[]`, material bindings,
Goal relationships, and bounded unresolved meaning. It does not author Work, Primary
Activities, Plan structure, execution lanes, realization, Capability IDs, executable
arguments, provider requests, planning InformationGaps, input-source/default policy,
clarification selection, or `actions[]`; Goal Association owns canonical Goal state and
Planner owns the first Work/Activity contract. Fast Planner also owns execution-input
completeness and source strategy. That ownership cannot be used to reinterpret,
widen, narrow, or invent Responsibility meaning. No maintained `RouteDecision` or
legacy Agent semantic compatibility surface remains on the Core path.

## Entrypoint ownership

| Entrypoint | Semantic owner | Role | Planner path | Failure behavior |
|---|---|---|---|---|
| Orchestrator turn in `apply` | Goal-Driven Cognitive Core | authoritative | Goal Interpretation → concurrent Fast Planner / Goal Association → optional Deep Planner for complex HOW → Goal-grouped Trusted Capability Runtime → Evidence re-entry | Once ownership is acquired, any semantic, validation, execution-preparation, or Goal-state error fails closed. |
| Orchestrator turn in `report_only` | Goal-Driven Cognitive Core | observer | Same bounded cognitive stages, evidence only | No semantic state, user-visible speech, or execution authority is committed by the observer result. |
| Cognitive Gateway protective reflex | Host deterministic control | pre-semantic | Stop/cancel/emergency/silence policy only | Never enters ordinary Goal semantics merely to enact a reflex. |
| Agent module endpoints | The named cognitive owner only | bounded module authority | `/cognitive-core/interpret`, Planner, Goal Association, Reflection, Social Attention, Agent Skill, tool, and TaskGraph contracts | Endpoint failure remains local to that bounded contract; it cannot reopen a second semantic planner. |

The maintained first user-facing speech path is Fast-Planner-owned. Goal
Interpretation emits Responsibility evidence only. Fast Planner may author one
immediately realizable Communicative Activity before Goal Association has
finished committing canonical Goal identity. Once GA commits, Runtime binds that
same delivered/scheduled Activity to the canonical Goal; Goal binding is not a
reason to author or play a second equivalent utterance. This changes latency,
not semantic or effect authority. Capability-dependent factual answers still
require matching trusted Evidence.

When Goal Association explicitly binds one Goal with `entity_type=action_list`,
Fast and Deep Planning require a bounded model-authored semantic completeness
audit before accepting an effectful Plan. The audit can only accept or reject;
it cannot add steps, choose a Capability, revise the Plan, or authorize
execution. Fast rejection escalates to Deep Planning. Deep rejection or audit
unavailability removes every executable step and returns clarification. This is
a fail-closed validation of the current Planner's coverage claim, not another
planning authority or a Host phrase-to-action rule.

`GET /semantic-authority` exposes the maintained machine-readable authority
matrix from the Agent service.

## Retired semantic fallbacks

The old CapabilityAgent semantic planner, direct-LLM Host path, route/intent
projection, and emergency semantic fallback gates are not part of the maintained
runtime. A disabled lane or failed authoritative turn cannot transfer semantic
authority to another planner. Deprecated test/archive representations may be read
only as evidence; they do not become production execution authority.

## Runtime modes and failure behavior

`apply` is the maintained semantic mode. Planner output is mechanically projected
to a runtime lane from the terminal `CanonicalPlan` (`chat`, `memory`, `tool`,
`robot_action`, or `unsupported`); GI does not emit or own that lane. A lane not
allowed by `ORCH_COGNITIVE_APPLY_LANES` fails closed. Once Goal-driven semantic
ownership begins, technical failure, terminal-lane mismatch, Planner-response
projection failure, trusted runtime rejection, or Goal-state commit failure cannot
transfer the same turn to another semantic planner.

`report_only` may run the same cognitive stages as an observer and retain
diagnostics, but it has no authority to commit user-visible speech, Goal state,
or effects. `off` disables the Goal-driven semantic runtime for diagnostics and
fails ordinary cognition closed; it is not a rollback into a legacy planner.

The dependency-light authority audit is:

```bash
python scripts/semantic_authority_audit.py
PYTHONPATH=agent:. python -m unittest -v tests.test_semantic_authority
```

These checks establish code-path ownership and fail-closed boundaries. They do
not establish live-model semantic quality or robot execution correctness.

## Live validation still required

On the NVIDIA workstation, retain evidence for:

- real Goal Association and Planner outputs across common and ambiguous turns;
- execute-plus-clarify multi-goal continuation;
- terminal interrupt handling without post-interrupt semantic re-entry;
- Soridormi/MuJoCo skill execution and safe-idle closure;
- voice ASR/TTS behavior.

A live failure does not reopen another planner during the same turn. Recovery
must use the current Goal/turn continuation mechanisms or begin a new user turn;
there is no emergency semantic compatibility planner.

## Exact Capability identity

Planner-selected Capability identity and semantic arguments remain Planner-authored.
Trusted Host/runtime validation may check the exact Capability against the live
catalog and validate arguments against that Capability's schema, but it must not
substitute a nearby Capability, translate one Capability's arguments into another
schema, or clamp values as a semantic rewrite. Invalid output fails closed or
returns to the owning Planner's bounded repair/escalation path.
