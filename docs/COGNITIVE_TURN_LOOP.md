# Cognitive Turn Loop / 认知话轮循环

Status: authoritative design and implemented contract baseline for one complete
admitted interaction turn. The
[Cognitive Gateway](COGNITIVE_GATEWAY.md) owns input admission and protective
reflexes. The
[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
remains the cognitive constitution. This document owns the executable
turn-loop, delegation, observation, outcome-reconciliation, and final-response
boundary between them. The host now closes effectful cognitive turns through
the immutable plan/request/result join, per-goal reconciliation, goal-state
commit, and a validated speech-only outcome response. Automated contract
evidence exists; retained provider-backed and live robot evidence remains open
and is owned by [STATUS.md](STATUS.md).

## 1. Decision

Chromie uses a **manager-owned, evidence-driven cognitive turn loop**:

```text
receive
  -> admit or protect
  -> understand goals
  -> plan complete goal coverage
  -> validate and authorize
  -> delegate bounded work
  -> observe structured results
  -> reconcile every goal against evidence
  -> compose one final response
  -> close, wait, or replan
```

This is the robot equivalent of a general tool-using agent loop, but it is not
a claim about ChatGPT's private implementation. OpenAI's public Agents SDK
describes a runner that repeatedly inspects model output, executes tool calls
or handoffs, returns results to the model, and stops at a final output. Its
public orchestration guidance distinguishes a manager that keeps conversation
control while invoking specialists from a handoff that transfers control.
Chromie adopts the manager pattern because one authority must retain user-goal,
confirmation, resource, physical-safety, evidence, and final-response
responsibility.

Public references:

- [OpenAI Agents SDK: Running agents](https://openai.github.io/openai-agents-python/running_agents/)
- [OpenAI Agents SDK: Agent orchestration](https://openai.github.io/openai-agents-js/guides/multi-agent/)
- [OpenAI API developer quickstart: tools and agents](https://platform.openai.com/docs/quickstart)

These references inform the generic loop shape only. Chromie's contracts,
models, deployment, safety boundaries, and physical execution remain local
project decisions.

The public SDK describes interfaces for developer-built agent applications; it
is not documentation of ChatGPT's product architecture, hidden reasoning,
training system, or proprietary orchestration. Chromie does not infer or try to
reproduce private chain-of-thought. Terms such as understand, plan, delegate,
observe, reconcile, and respond name Chromie's own auditable contract stages,
not claimed internal ChatGPT modules.

## 2. Ownership

The Cognitive Gateway owns:

- immutable input capture and normalization;
- deterministic protective reflexes;
- bounded attention review;
- source-attributed context assembly;
- turn admission.

The Goal-Driven Cognitive Core is the sole cognitive manager and final semantic
and conversational authority for every admitted turn. It owns:

- intent and goal understanding;
- goal continuity and independent-goal segmentation;
- complete canonical planning;
- selection of bounded Agent, tool, memory, and Skill Runtime work;
- outcome reconciliation against each goal;
- replan, clarification, failure, or completion decisions;
- the final user-facing response.

Specialist Agents, tools, memory providers, and Soridormi:

- receive bounded assignments;
- operate only within their declared capability and authorization;
- return structured results and evidence;
- never widen the user goal;
- never become the final conversation authority.

The host Orchestrator is the trusted runtime controller, not a second cognitive
manager. It enforces timeouts, cancellation, confirmation, resource policy,
schema validation, result correlation, playback ordering, and legal transitions
between loop states. It may reject invalid Core output and render a
contract-defined conservative fallback, but it cannot reinterpret the user
goal, invent a replacement plan or outcome, or transfer final conversation
authority to a specialist. Soridormi remains the authority for embodied
planning, execution, resource safety, stop/emergency behavior, and hardware
commissioning.

## 3. Turn state machine

Every received input has one stable `turn_id`. The normal path is:

```text
RECEIVED
  -> ADMITTED
  -> GOALS_RESOLVED
  -> PLAN_VALIDATED
  -> WAITING_FOR_CONFIRMATION | EXECUTING | READY_TO_RESPOND
  -> OUTCOMES_RECONCILED
  -> RESPONSE_COMPOSED
  -> CLOSED | WAITING_FOR_USER | REPLAN_REQUIRED
```

Alternative terminal ingress states are:

- `SUPPRESSED` for policy-qualified ambient or unusable input;
- `REFLEX_APPLIED` for a deterministic control that needs no ordinary
  cognition;
- `REFLEX_AND_ADMITTED` when the control must also be retained for goal-state
  reconciliation and a possible concise response.

`REPLAN_REQUIRED` may return only to canonical planning, with a bounded budget
and the original goals intact. It cannot return to input classification, widen
the goal, bypass a new material confirmation, or repeat a physical action
without fresh authorization. Physical TaskGraph work remains sequential.

## 4. Gateway-to-Core contract

The Gateway emits a versioned `UserTurnEnvelope`. It is the only canonical
input object for a new Core turn.

Required fields:

- stable `turn_id`, `session_id`, and `conversation_id`;
- channel and receive timestamp;
- immutable original input;
- normalized input and language hint;
- bounded input-quality evidence;
- `ReflexOutcome`;
- an attention finding;
- source- and freshness-aware context references;
- one admission disposition.

The envelope deliberately excludes:

- ordinary intent;
- goal meaning or goal IDs;
- a compatibility route;
- selected Agents, tools, skills, or capabilities;
- a plan or authorization;
- an execution claim;
- response text.

The current compatibility adapter projects only an admitted envelope into the
existing Core call shape and preserves the envelope and correlation IDs in
context and response metadata. `RouteDecision` remains an advisory
source-effect and rollout-lane bound, not the primary cognitive object.
Suppressed, unusable, and reflex-only envelopes cannot be projected into
ordinary Core cognition.

## 5. Goal understanding and planning

The Core first associates the admitted turn with active goals. It then creates
only genuinely independent new goals and produces one canonical plan that
covers every goal.

The planning path is:

```text
UserTurnEnvelope
  -> GoalAssociationResolution
  -> Fast Planner
  -> terminal CanonicalPlan
     or explicit escalation to Deep Planner
  -> deterministic validation
  -> confirmation and commitment
```

Fast and Deep planning use the same `CanonicalPlan` contract. Model reasoning
chooses semantic goals, plan steps, parameters, ordering, and per-goal
prospective outcomes. Deterministic code checks schemas, capability
availability, source-effect bounds, resources, confirmation requirements, and
forbidden low-level controls. Validation cannot invent missing meaning or
rewrite the plan into a nearby action.

## 6. Delegation model

Chromie uses manager-owned delegation:

```text
Core
  -> Agent/tool/Skill request A
  -> Agent/tool/Skill request B
  -> ...
  <- structured result A
  <- structured result B
  -> Core outcome reconciliation
```

Specialists may be implemented as Agents, tools, memory providers, or
Soridormi skills. Their implementation category does not change the contract.
Every request is bound to:

- the admitted turn;
- canonical plan ID and fingerprint;
- canonical step ID;
- one or more source goal IDs;
- exact skill identity and version;
- the exact canonical arguments and execution timing;
- the full committed SHA-256 identity of a versioned, non-empty declared output
  schema and bounded observation limits;
- timeout, cancellation, confirmation, and idempotency policy.

Independent non-physical work may use bounded concurrency only when capability
and resource contracts allow it. Physical work remains sequential. A specialist
handoff is an implementation detail; it never transfers ownership of the user
conversation or final answer away from the Core.

## 7. Execution outcome contract

Execution results return through a versioned `ExecutionOutcomeBundle`. It is
constructed by deterministic joins over the immutable plan, committed
requests, and trusted `SkillResult` or provider evidence. It is never inferred
from generated speech.

The bundle contains:

- `outcome_id`, `turn_id`, and `interaction_id`;
- canonical plan ID and fingerprint;
- one evidence record per planned effectful request;
- exact plan-to-request correlation over step, skill, arguments, timing, and
  source goals, followed by exact request-to-result/trace correlation over
  request, skill/version, provider, trace, and timestamps;
- terminal status, a schema-validated bounded `ModelObservation` or explicit
  observation-unavailable state, reason, trace, and timestamps;
- one reconciled outcome per canonical goal;
- explicit missing or `not_run` results;
- aggregate status derived from the per-goal outcomes;
- separately identified provider postcondition evidence.

An absent result is `not_run` or unknown, never success. If cancellation
propagates before per-request terminal evidence is returned, the host
conservatively records each affected committed request as `cancelled` with an
unknown-start diagnostic rather than asserting it never ran. An unknown or
uncommitted runtime result fails exact reconciliation; only a result for an
explicitly committed auxiliary social-attention request may be excluded.
Pre-action speech and auxiliary social attention do not satisfy an effectful
user goal. Provider postcondition evidence such as `safe_idle=true` may support
a safety claim, but does not by itself prove every requested goal completed.

Per-goal outcomes retain distinctions among:

- `completed`;
- `partial`;
- `failed`;
- `refused`;
- `timed_out`;
- `cancelled`;
- `not_run`.

Exact per-goal and per-step statuses are always retained. `partial` is used
only when completed work and unresolved work coexist. Heterogeneous outcomes
with no completed work aggregate conservatively as `failed`; that aggregate
does not erase the underlying `refused`, `timed_out`, `cancelled`, or `not_run`
records.

### 7.1 Specialist output and model-observation boundary

Before delegated work can be committed, its registered capability or provider
manifest must declare a versioned, non-empty output schema. An absent schema,
`{}`, or an unconstrained accept-anything object is not a valid declaration. A
capability with no domain payload still declares an explicit unit-result schema
with its terminal status and evidence fields. At plan-to-request commitment, the
host stores the full SHA-256 identity of the canonical output schema in a
closed, validated `SkillRequest` field; it does not copy the raw schema into
request metadata. At closure, the current trusted `SkillDefinition` schema is
usable only when its digest exactly matches that commitment. A missing
commitment, missing definition, changed or invalid schema, or an empty schema
produces `schema_unavailable` with a bounded reason and exposes no provider
payload. This also keeps Soridormi capabilities whose current catalog omits an
output schema fail-closed during migration.

Raw Agent, tool, memory, and provider output never enters a model prompt
directly. The trusted host first validates correlation and schema, then creates
a `ModelObservation` through a deterministic projection that:

- includes only allowlisted semantic result fields;
- enforces configured byte, character, item-count, nesting, and context-budget
  limits;
- redacts credentials, secrets, sensitive values, and provider-internal data;
- excludes binary payloads and raw motor, joint, actuator, torque, controller,
  bus, and other low-level robot fields;
- treats prompt-like text in tool output as untrusted data, never authority;
- records schema identity, provenance, validation status, and explicit
  truncation or redaction flags.

Only that bounded observation may reach Core reconciliation, replanning, or
response composition. The retained audit record preserves the validation and
projection decision plus a content digest under the evidence-retention policy;
it does not make raw secrets model-visible. Schema failure, projection failure,
or an empty required observation fails closed as `observation_unavailable`.
Trusted terminal status may still be recorded, but the Core cannot invent the
missing payload or make a claim that depends on it.

## 8. Outcome reconciliation and speech contracts

Outcome reconciliation is a Core stage after execution. It:

1. verifies plan, step, request, and goal correlations;
2. updates goal state atomically with trusted evidence;
3. compares observed outcomes with goal success criteria;
4. decides whether each goal is completed, waiting, recoverable, failed,
   cancelled, or needs a bounded replan;
5. exposes one immutable result bundle to the final response composer.

### 8.1 Pre-execution speech

For effectful work, the pre-execution response contract is prospective. It may
acknowledge the understood request, ask for confirmation or clarification,
state that a validated action is about to begin, provide a state-validated
progress update, or explain refusal/unavailability. It must not claim that a
tool found a result, an action completed, the robot is safe, or a user goal was
satisfied. Speech such as "I'm starting" requires committed execution state;
planning output alone is insufficient.

Pre-execution speech is never execution evidence and never closes an effectful
goal. A non-effectful conversational turn may move directly to
`READY_TO_RESPOND`; its Core-owned answer is final for that turn and is grounded
in the admitted input and any validated context or retrieval evidence, not in a
fictional execution result.

### 8.2 Evidence-bound post-execution speech

For effectful work, the current deterministic post-execution composer runs only
after terminal results have been joined and every executable goal has been
reconciled and committed. It receives the immutable outcome bundle and bounded
`ModelObservation` values, and returns speech only. It cannot add skills,
actions, goal changes, retries, or authorizations. Its structured claims
reference exact goal and evidence IDs, and the host validates them against the
outcome bundle. A future model-assisted composer must obey this same boundary.

The final response must:

- cover every relevant goal exactly once;
- distinguish success, partial completion, failure, timeout, refusal,
  cancellation, and `not_run`;
- include useful trusted tool output when present;
- avoid internal IDs and implementation narration;
- make no completion, observation, memory, movement, or safety claim without
  matching evidence;
- be emitted once for the reconciled interaction.

Only speech with a completed delivery result is added to model-visible
conversation history. The same rule applies to host confirmation and recovery
prompts: a scheduler, provider, or playback-start failure cannot create an
assistant turn that the user never heard.

The current deterministic composer is the conservative, language-matched
status path. If its input validation or composition fails, the host retains the
execution evidence and suppresses an unvalidated outcome response; failure
cannot erase evidence or turn an uncertain result into success.

### 8.3 Recovery is a confirmed child plan

A recoverable embodied failure does not mutate or replay the parent plan. The
host selects only the failed recoverable Soridormi steps, constructs a new
immutable `CanonicalPlan` with `plan_relation=recovery_subset`, records the
parent plan ID and fingerprint, and gives the child plan its own ID and
fingerprint. Retry requests receive new request and idempotency identities and
must match that child plan exactly.

The child plan requires fresh request-bound confirmation and then re-enters the
normal validation, Skill Runtime, Soridormi preflight, outcome reconciliation,
and final-response path. Earlier completed sibling goals remain in parent
history and are not overwritten or replayed. If a complete child plan cannot be
constructed, any committed sibling lacks a terminal result, a non-recoverable
sibling exists, the retry budget is exhausted, or confirmation is absent, no
retry runs.

## 9. Stop, cancel, and emergency input

A stop command is both input and control:

```text
receive stop input
  -> create stable turn identity
  -> revoke stale approvals synchronously
  -> begin deterministic cancellation before model work
  -> for embodied emergency, dispatch the dedicated Soridormi E-stop contract
  -> retain ReflexOutcome and provider cancellation evidence
  -> reconcile affected goals as cancelled, recoverable, or uncertain
  -> optionally speak one concise evidence-grounded acknowledgement
```

The Gateway and host implement this recognition and control path
deterministically; no LLM decides whether to send, delay, override, or resume
it. Pending approval is revoked before the first await, and a following turn
cannot cancel an active protective-reflex lifecycle. Recording and final
response never delay stopping. A later semantic stage may clarify what was
affected, but it cannot undo the stop or silently resume work.

The first operational phase dispatches output invalidation, scoped runtime
cancellation, and dedicated E-stop work concurrently, with safety operations
scheduled before audio teardown. A blocked playback/device lock therefore does
not delay the runtime cancel or E-stop dispatch. Dispatch failures, provider
cancel failures, and E-stop evidence stay separate; safe idle still requires
its own trusted Soridormi postcondition.

`global_emergency` additionally cancels every unfinished host interaction
workflow, including preflight work that has not registered a runtime request.
That host sweep still runs if scoped runtime dispatch fails, preventing an
older interaction from starting after the emergency turn. The cancellation
receipt preserves the interaction-qualified host task requests.

Cancellation is bound to execution scope, not to whichever goal happens to be
most recent in memory:

- `output_only` selects speech-output requests in the bound interaction;
- `embodied_motion` selects requests whose trusted capability definition
  declares a physical-motion effect;
- `current_interaction` selects every unfinished request in the foreground
  interaction;
- the runtime-level `specific_goal` contract requires exact authoritative goal
  IDs, committed plan ID, and fingerprint, and selects only structured
  skill/effect requests wholly owned by those goals;
- `global_emergency` selects every unfinished runtime request, cancels every
  unfinished host interaction workflow, and additionally dispatches the
  dedicated Soridormi E-stop path for embodied execution.

The trusted runtime applies a scope to both running and queued work. It records
running cancellation separately from `cancelled_before_start`, leaves completed
work unchanged, and returns the selected request, interaction, and goal IDs.
Independent unselected work continues; existing sequencing, dependency, and
required-delivery barriers still apply. Selected non-interruptible work and
provider cancellation failures remain explicit unknown/not-stopped evidence. A
request shared by targeted and untargeted goals is a deterministic scope
conflict, not permission to cause an unreported collateral cancel.

The host now reconciles every fixed-reflex receipt through Conversation State in
one transaction. Exact request bindings close a Goal only when all of its
remaining committed work is proven cancelled. Domain-limited cancellation may
leave a Goal `recoverable` with unaffected work still pending; provider failure,
non-interruptible work, an unselected request under a broad scope, or a
Host-preflight cancellation with unknown start state produces
`cancellation_uncertain` instead of a false success. `output_only` may stop
pre-action speech without changing the embodied Goal whose execution request was
not selected. The receipt, request statuses, remaining request IDs, scope
widening, and uncertainty reasons stay attached to the Goal and its pending
execution record.

The confirmation dialogue normally owns one token for a whole staged response.
Fixed reflex scopes remain conservative: `output_only` preserves that token,
while a motion stop revokes the whole token when any confirmed request is
motion-bound or cannot be classified safely. That synchronous revocation is
committed with the broad runtime receipt in the same Conversation State
transaction, so Goal state and confirmation records cannot independently claim
different outcomes. Named `specific_goal` cancellation uses a narrower
contract. The host removes only requests wholly owned by the
target Goals, creates an immutable `confirmation_remainder` child plan for the
unaffected Goals, gives its requests fresh identities, and installs a fresh
single-use token only after the cancellation evidence and Goal-state transition
commit. A request or plan step shared by targeted and preserved Goals is not
separable and fails closed.

For non-urgent named cancellation, the Core resolves semantic Goal IDs only.
The trusted host maps those IDs to the exact active interaction, committed plan
ID and fingerprint, then dispatches `specific_goal` to Skill Runtime. Goal state
is mutated only after the host validates one exact receipt for every
execution-bound target, including selected requests and any stale, shared-owner,
non-interruptible, provider-failure, dispatch-failure, or provider-widening
evidence. The validated target cancellation, coaffected Goal transitions, and
confirmation-token replacement are committed through one Conversation State
transaction plus a compare-and-swap of the prepared token without an intervening
await. State-only Goals may close without runtime dispatch. If runtime/provider
cancellation was attempted but receipt reconciliation or durable Goal-state
commit cannot be verified, the user-facing result is explicitly uncertain; the
host must not claim the action never started or the Goal was cancelled. Current
Soridormi motion cancellation is global-domain, so a specific physical target
may widen to `embodied_motion`; every coaffected request and Goal is retained in
the receipt and reconciled rather than reported as exact isolation.

Goal-owned cognitive speech now carries source Goal IDs and exact plan identity
into its runtime request. Unfinished speech can therefore participate in named
cancellation. The maintained local output provider owns a shared playback
resource, so provider cancellation may widen a target to `output_only` and
abort all coaffected pending or active output; the receipt records that
widening. Already completed or already heard speech cannot be retracted.
Likewise, `embodied_motion` remains scoped to the host execution ledger. Only
`global_emergency` independently dispatches the dedicated Soridormi E-stop for
motion outside or stale relative to that ledger.

Recognizing an emergency-stop phrase and entering generic cancellation is not
proof that a dedicated Soridormi E-stop ran or that the robot reached safe
idle. For embodied motion, Soridormi alone owns controller-level stop/E-stop
execution and the resulting safe-state postcondition. The host must use that
dedicated contract for an embodied emergency; generic task cancellation is not
a substitute. The current host dispatches the dedicated E-stop, retains success, failure, or
unavailable evidence in the cancellation receipt, and atomically reconciles
ledger-bound Goal cancellation separately from the safety postcondition. A Goal
may be cancelled while `safe_idle_verified=false`; this records the user's
cancelled work without inventing a controller-safe-state claim. The Core owns
any spoken acknowledgement and cannot overrule Soridormi's safety authority. E-stop and safe-idle claims require explicit correlated Soridormi
evidence.

## 10. Failure and loop limits

The loop is bounded:

- one contract repair per model stage;
- one configured semantic replan budget;
- explicit tool and provider timeouts;
- cancellation propagated through the host and provider;
- no unlimited Agent handoff or tool-call loop;
- no automatic retry of material physical work;
- no final completion claim from prospective planning output;
- no stale final response after a newer turn or protective reflex preempts the
  interaction.

Failures remain attributed to their earliest responsible boundary:

- Gateway/admission;
- goal association;
- Fast or Deep planning;
- deterministic validation or authorization;
- Agent/tool/provider execution;
- outcome correlation and reconciliation;
- final response composition or delivery.

## 11. Observability

The loop records contracts and decisions, not hidden model reasoning:

- `UserTurnEnvelope` identity, quality, reflex, attention, context references,
  and admission;
- Goal Association and canonical goal IDs;
- planner tier, plan fingerprint, validation, confirmation, and commitment;
- delegated request identities and source goal IDs;
- every execution result and missing result;
- declared output-schema identity and validation outcome;
- model-observation projection policy, size, redaction/truncation flags, and
  content digest, without logging raw secrets or low-level control fields;
- per-goal reconciled outcomes;
- replan, clarification, or terminal decision;
- final response claims and delivery result;
- cancellation and provider postconditions.

One trace should answer: what entered, what Chromie understood, what it planned,
what was authorized, what actually ran, what evidence returned, how each goal
ended, and why Chromie said the final words.

## 12. Compatibility and migration

The contract-first loop baseline is implemented:

1. `UserTurnEnvelope` is built and dual-recorded;
2. the compatibility adapter preserves current Router/Core wire behavior while
   allowing only admitted envelopes into Core;
3. configured authoritative lanes use Goal Association, canonical planning,
   deterministic validation, and manager-owned delegation;
4. committed requests bind exact plan/step/skill/arguments/timing/schema
   identity;
5. `ExecutionOutcomeBundle` joins results and traces to the immutable plan,
   retains exact per-goal states, and commits them to goal state;
6. bounded schema-validated `ModelObservation` values are the only provider
   payloads visible to outcome response composition;
7. stale, cancelled, superseded, or recovery-waiting turns retain their
   evidence while suppressing late final speech;
8. recoverable embodied failures use a separately fingerprinted,
   confirmation-bound child plan.

Remaining migration work is to extract the five physical Gateway modules,
separate Attention Review from compatibility Router semantics, derive
`RouteDecision` only for older consumers, widen authority only with retained
evidence, and deprecate Router names only after parity and rollback coverage.

Existing `chromie-router`, `/route`, `ROUTER_*`, and Router log names remain
valid compatibility interfaces during this sequence.

## 13. Acceptance boundary

Required Level A cases include:

- a direct question becomes one admitted turn and one final answer;
- a mixed-language compound request preserves and covers every goal;
- independent tool results are correlated and summarized once;
- one success plus one failure remains a mixed result;
- a missing provider result becomes `not_run`;
- propagated cancellation with unavailable per-request terminal evidence stays
  `cancelled` with unknown-start diagnostics rather than becoming `not_run`;
- an uncommitted runtime result fails exact reconciliation;
- an absent, empty, or wildcard output schema fails closed before its result can
  become model-visible;
- oversized, secret-bearing, binary, prompt-like, or low-level robot output is
  bounded or redacted before the Core observes it;
- pre-execution speech cannot claim a result, while post-execution speech can
  claim only reconciled evidence;
- a timeout, refusal, cancellation, or stop never becomes completion;
- an unknown goal, step, request, evidence ID, or stale fingerprint fails
  closed;
- final response composition emits no skill or action;
- a newer turn or protective reflex suppresses stale final speech;
- an undelivered confirmation, recovery, or final response does not enter
  model-visible history;
- an embodied emergency dispatches Soridormi's dedicated E-stop contract;
  generic cancellation cannot support an E-stop or safe-idle claim;
- dedicated E-stop and safe-idle claims require explicit correlated Soridormi
  evidence.

Level A and unit tests prove contract behavior only. Provider-backed live-text,
simulator, microphone, and physical-robot claims require their corresponding
retained evidence. Current evidence status is reported in
[STATUS.md](STATUS.md).
