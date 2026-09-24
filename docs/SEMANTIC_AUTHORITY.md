# Single Semantic Planning Authority

## Accepted target and current-source boundary

The [Charter's Social Cognition amendment](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
splits ordinary communication from Work planning inside the same Cognitive Core.
Single semantic authority means one writer per semantic decision, not one model
invocation for every responsibility in a turn. Social Cognition owns exact
Communicative Activities; Planner owns Capability/Work decisions. UMI and GA keep
WHAT and canonical continuity respectively. Neither downstream role reinterprets
UMI or reviews/repairs the other's output.

The `context.semantic_authority` guard prevents a second Core or retired planner
from acquiring the turn. Within that Core, `/social-cognition` owns interaction
and exact input-snapshot binding. Fast/Deep Planner model DTOs contain Work and
communication Needs, with no writable utterance or social-expression fields.
The Host joins these distinct decisions without allowing either to repair the other.
Implementation evidence and remaining qualification gaps are owned by [STATUS](STATUS.md).

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

The maintained authority boundary applies Charter requirements `SPEECH-OWNER-001` and `PLANNER-AUTHORITY-001`.

## Maintained invariant

A turn carries one `context.semantic_authority` claim. The claim records an
owner and one of two roles:

- `authoritative`: may resolve user goals and produce the semantic plan;
- `observer`: may produce comparison evidence but cannot commit or execute.

After the Goal-Driven Cognitive Core's current Goal-driven Runtime acquires
authoritative ownership, any planning, composition, host-validation, or
state-commit failure is fail-closed. The same turn cannot transfer semantic authority to a retired planner or adapter.

Speech composition and user-task execution may be prepared or scheduled
independently from immutable projections of that authoritative turn. Parallel
output preparation does not create another semantic owner. SC owns each
Communicative Activity's function, exact words, timing, truth stage, provenance,
and constraints; User Meaning Interpretation owns none of those fields. Trusted Runtime
and Host bind terminal results to exact request/Goal provenance as Evidence, then
reactivate Planner for Work and SC for communication with bounded current-state
views. Result contents cannot bypass those authorities or infer their own Goal. Confirmation/cancellation mechanisms likewise own
only authorization/control facts and may not turn those facts into ordinary dialogue.
Named-Goal cancellation records bounded `GoalCancellationEvidence` after deterministic
dispatch/reconciliation and re-enters the same Planner state path used for trusted runtime
Evidence. If cancellation invalidates a pending confirmation, Host revokes the stale token
as a whole; it never invents a narrowed child Plan, replacement prompt, or sibling
remainder speech. A later Planner pass may establish an answer Need, author genuinely new Work,
reuse/cancel/replace current Work, wait, or emit no Activity; it must not repeat the
terminal or cancelled Activity merely because Evidence arrived.

Cross-cutting evidence qualification, retention/privacy policy, and bounded
adaptation are not additional semantic owners. They refine factual/context input to
existing owners and cannot inherit downstream Goal, Plan, authorization, or effect
authority.

Optional social decoration belongs to SC in the same complete interaction decision.
`SocialCommunicativeAct.auxiliary_activities[]` is bound to its exact SC snapshot and
act identity and is structurally outside Goal-owned `steps[]`; Runtime may validate,
execute, or suppress the exact proposal, never reselect it. Auxiliary-only events
cannot create a Goal-scoped `CognitiveOpportunity` or borrow Goal identity.

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

User Meaning Interpretation performs WHAT-only semantic interpretation. Its target model-facing
contract emits complete provider-neutral `responsibilities[]`, requested result
types, source evidence and bounded unresolved meaning. It emits neither parameter
bindings nor Goal relationships. It does not author Work, Primary
Activities, Plan structure, execution lanes, realization, Capability IDs, executable
arguments, provider requests, planning InformationGaps, input-source/default policy,
clarification selection, or `actions[]`; Goal Association owns association with retained canonical
Goal history, while trusted lifecycle code materializes new Goal identity/fields mechanically from
accepted UMI WHAT when no retained Goal matches. Planner owns the first Work/Activity contract,
execution-input completeness, and
source strategy. Fast/deep are cognition passes of that same Planner authority. That ownership cannot be used to reinterpret,
widen, narrow, or invent Responsibility meaning. No maintained `RouteDecision` or
legacy Agent semantic compatibility surface remains on the Core path.

WorkDAG does not add another semantic owner. Goal Association may associate/update retained
canonical Goal truth but cannot model-author a fresh Goal interpretation or edit graph topology.
Trusted lifecycle materialization of an unassociated Responsibility copies UMI-owned semantics
without becoming another semantic owner. Planner alone may retain the current WorkDAG,
author its exact next revision, merge coherent planned Work, or create a new WorkDAG.
DAGEngine advances execution state and reports Evidence only; normal node completion may
continue mechanically without a Planner turn, while material invalidation re-enters Planner.

Social Cognition owns Goal-free communication through `/social-cognition`, using
the same complete transaction as other trusted state triggers. The request grants
no Responsibility, task Goal, requested Work or effect authorization. It may produce
silence, exact verbal acts and optional eligible social expression. Existing Runtime
owns all safety and delivery. Environment source adapters still own perception facts;
SC does not infer missing identity or audience. Ordinary turns and trusted Situation wakes use the same interaction authority.

## Entrypoint ownership

| Entrypoint | Semantic owner | Role | Planner path | Failure behavior |
|---|---|---|---|---|
| Orchestrator turn in `apply` | Goal-Driven Cognitive Core | authoritative | User Meaning Interpretation → independent SC / Planner fast pass / Goal Association → optional Planner deep pass for complex HOW → asynchronous Trusted Capability Runtime → Runtime event / Evidence → CognitiveOpportunity → Planner re-entry when useful | Once ownership is acquired, any semantic, validation, execution-preparation, or Goal-state error fails closed. |
| Orchestrator turn in `report_only` | Goal-Driven Cognitive Core | observer | Same bounded cognitive stages, evidence only | No semantic state, user-visible speech, or execution authority is committed by the observer result. |
| Trusted Goal-free Situation | Goal-Driven Cognitive Core; SC owns communication | authoritative, communication-only | Situation → bounded Social Cognition invocation → exact Activity → existing delivery runtime; no synthetic Goal or Capability Work | Invalid provenance/identity/repair fails before Memory or delivery; unavailable cognition remains quiet. |
| Cognitive Gateway protective reflex | Host deterministic control | pre-semantic | Stop/cancel/emergency/silence policy only | Never enters ordinary Goal semantics merely to enact a reflex. |
| Agent module endpoints | The named cognitive owner only | bounded module authority | `/cognitive-core/interpret`, Work Planner, Social Cognition (including optional expression), Goal Association, Reflection, Agent Skill, tool, and WorkDAG contracts | Endpoint failure remains local to that bounded contract; it cannot reopen a second semantic planner. |

The first user-facing speech path belongs to SC. One accepted UMI result can start
SC, GA and Work planning independently. At that point SC may acknowledge understanding
or remain silent; it cannot predict unfinished Work decisions. Canonical Goal binding
does not itself require another utterance. Required answer/input/confirmation Needs
are joined to the exact validated Plan; factual results require admitted Evidence.

For Goal-bound planning, each Fast or Deep invocation authors its complete Plan,
per-Goal outcomes and grounding/coverage evidence in its primary result. A Goal
with `entity_type=action_list` does not introduce an exception
to Charter principles 30–31. A second model call must not audit, accept/reject,
complete, or repair that same semantic decision. Schema and Host checks enforce
declared references, cardinality, provenance, Capability and execution invariants;
passing them does not prove arbitrary natural-language semantic completeness.
Use the [acceptance claim boundaries](ACCEPTANCE.md#scope-of-validation-and-semantic-evidence)
to distinguish these checks from semantic qualification, target validation and
release readiness; model-authored coverage and satisfaction are not independent proof.

Before commitment, genuinely unresolved HOW may use the designated single
source/context-based delegation to Deep Planner. Deep receives authoritative
Responsibilities/Goals and current context, not a Fast candidate Plan to judge or
rewrite. A technical/contract failure or a review verdict cannot authorize that
delegation. Deep rejection is terminal for that attempt, and a completed decision
cannot be reopened by another model review. New authoritative Goal, Work, Evidence
or Situation state may independently trigger the existing scoped Planner path.

Structural regeneration is separate from semantic reconsideration and is permitted
only by the particular role's existing contract. Current Fast/Deep Planner do not
invoke same-tier repair generations. GA's separately bounded container repair must
preserve every primary claim through deterministic preflight and comparison; it
does not authorize Planner review or semantic rewriting. See the
[turn-loop depth and repair contract](COGNITIVE_TURN_LOOP.md#30-fastdeep-escalation-is-cognition-depth-not-repair).

UMI's parser and projection have the following #40 classification. A deterministic
operation is permitted because it preserves an explicit contract, not merely
because it uses no model. Primary and designated Deep use the same boundary.

| Operation | Maintained rule and owner |
| --- | --- |
| JSON transport wrapper | UMI parser accepts a complete object or one complete JSON fence. It rejects leading/trailing prose, duplicate keys and non-finite constants; it cannot select a convenient object or silently replace an earlier claim. |
| Responsibility semantic bindings versus Goal/Work fields | Permit only sparse source/context-grounded semantic bindings that conserve WHAT (for example place, time, count, measurement, ordering). Reject Goal relationship/ID, Capability/provider, execution, raw-input, and Planner-realization fields. GA owns continuity; Planner owns HOW. |
| Missing confidence or required Responsibility meaning | Reject; Host does not derive aggregate confidence from sibling scores or invent required output mode, outcome or local reference. |
| Semantic uncertainty | UMI alone authors typed `UserMeaningUncertainty` objects with a local ref, kind, description and affected Responsibility refs after bounded context is exhausted. Missing execution/provider inputs are not semantic uncertainty. GA may resolve only exact refs through validated canonical continuity; only the remainder may reach clarification. |
| Source evidence | Validate exact known token references, source order and non-overlap. This does not prove semantic completeness or permit Host resegmentation. |
| IDs and text | Require authored local refs, result type, text and confidence; do not invent missing meaning. |
| Planner argument and time citations | Check exact owning intent excerpts and DTO/argument consistency. Planner owns extraction and conversion; semantic correctness requires native qualification. |
| Semantic reconsideration | No retry for invalid UMI semantics. Only an accepted result with genuinely unresolved meaning permits its one designated source-based Deep invocation. |

These rules do not make all natural-language meaning mechanically provable. GA's
separate lossless container repair and Planner's no-repair rules remain unchanged.

Offline semantic qualification may review retained primary results under the
[frozen-cohort method](LLM_PROMPT_QUALIFICATION_METHOD.md). Its judgments remain
evaluation evidence: they cannot replace candidate results, mutate Runtime state,
or feed a repair back into the current online decision.

`GET /semantic-authority` exposes the maintained machine-readable authority
matrix from the Agent service.

## Retired semantic fallbacks

The old CapabilityAgent semantic planner, direct-LLM Host path, route/intent
projection, and emergency semantic fallback gates are not part of the maintained
runtime. A disabled lane or failed authoritative turn cannot transfer semantic
authority to another planner. Deprecated test/archive representations may be read
only as evidence; they do not become production execution authority.

## Runtime modes and failure behavior

`apply` is the maintained semantic mode. The terminal `CanonicalPlan` is validated
directly against declared Capability schemas, semantic scope, safety, confirmation,
resource, concurrency, availability, and provider contracts. There is no intermediate
`chat`/`memory`/`tool`/`robot_action` semantic lane. Once Goal-driven semantic
ownership begins, technical failure, Planner-response projection failure, trusted
runtime rejection, or Goal-state commit failure cannot transfer the same turn to
another semantic planner.

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
schema, or clamp values as a semantic rewrite. Invalid output fails closed;
genuinely unresolved HOW may use only the source-based depth contract above,
never a model review or repair of the rejected Plan.
