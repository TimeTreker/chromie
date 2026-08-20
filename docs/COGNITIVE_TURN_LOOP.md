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

The direct no-planner `spoken_response` transition and independently scheduled
validated response stages described below are accepted post-evidence contract
work, not implementation claims created by this documentation update. Current
behavior and evidence remain authoritative in [STATUS.md](STATUS.md).

## Bounded addressedness before Core semantics

The Gateway's focused Attention Review consumes the latest transcript, Host engagement
evidence, and a bounded recent-dialogue projection. Recent exchange is context, not an
automatic addressedness grant: a temporary user-authored rule such as "wait until I say
Chromie" can suppress ambient nearby speech while allowing a later explicitly addressed
turn. The Attention model makes one judgment only. Invalid/unavailable output fails open
to ordinary Core cognition; there is no Attention repair or suppression-review chain.

## 1. Decision

Chromie uses a **manager-owned, evidence-driven cognitive turn loop**:

```text
receive
  -> admit or protect
  -> Goal Interpretation reads bounded Session Context
  -> concurrently:
       Fast Planner authors the first Activity Plan
       Goal Association commits canonical Goal identity/updates
  -> realize the Planner's exact Communicative-Activity wording without
     adding another semantic response author
  -> bind Activities into per-Goal task-list views
  -> validate, authorize, and resource-schedule ready Work
  -> resolve execution inputs or ask a user-resolvable clarification; use Deep Planner for complex HOW
  -> observe structured results and reconcile every Goal against Evidence
  -> re-enter Fast Planner on trusted Evidence for the still-needed response
  -> close, wait, or reactivate later from new evidence/state
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
- selection of bounded Agent, tool, memory, and Trusted Capability Runtime work;
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

Speech composition and user-task execution may be prepared or scheduled
independently, including with bounded parallel model calls, but they consume
the applicable immutable authoritative state: the same Core-owned turn, plus
Goal versions, a Canonical Plan, and evidence when each exists. This output
scheduling does not transfer semantic or conversation authority to a response
composer or execution specialist.

### Maintained module I/O and non-ownership boundaries

| Module | Authoritative input | Authoritative output | Must not decide |
|---|---|---|---|
| Cognitive Gateway | captured turn, bounded Host context, deterministic protective controls | admitted immutable `UserTurnEnvelope` or protective outcome | user Goal, Capability, Plan, or social expression |
| Goal Interpretation | admitted turn plus bounded Situation/continuity context | provider-neutral Responsibilities, bindings, qualifiers, and unresolved meaning | Capability input gaps, clarification policy, Goal continuity, or Work |
| Fast Planner first/advance phases | GI Responsibilities, applicable schemas/catalog, trusted context | exact early Communicative Activity and provisional safe Work where eligible | canonical Goal identity or result claims without Evidence |
| Goal Association | unchanged GI result plus bounded retained Goals | Canonical Goal create/associate/update DTO | `requires_replan`, Work compatibility, Capability, cancellation, or next action |
| Fast/Deep Planner Work Reconciliation | Canonical Goals, open Responsibilities, Situation, Evidence, and bounded queued/running/completed Work | complete desired `CanonicalPlan`; explicit `reuse_activity_id` selections | execution truth or Host/runtime mutation |
| Host Orchestrator and Trusted Capability Runtime | validated Plan plus exact live request/version/state/resource/safety bindings | accepted/rejected dispatch, reuse/cancellation receipts, traces, and typed Evidence | semantic compatibility, Goal meaning, or rewritten Planner wording |
| Evidence re-entry and Responsibility reconciliation | Host-bound terminal Evidence plus still-open Canonical Goal | truthful response, follow-on Plan, wait/failure state, and eventual Responsibility closure | fabricated completion or conversion of stale/unbound output into Goal Evidence |

## 3. Turn state machine

Every received input has one stable `turn_id`. The normal path is:

```text
RECEIVED
  -> ADMITTED
  -> GOALS_RESOLVED
     -> COMMUNICATIVE_ACTIVITY_READY
     or
     -> PLAN_VALIDATED
        -> WAITING_FOR_CONFIRMATION | EXECUTING | COMMUNICATIVE_ACTIVITY_READY
        -> OUTCOMES_RECONCILED
        -> EVIDENCE_RESPONSE_READY
  -> CLOSED | WAITING_FOR_USER | REPLAN_REQUIRED
```

Alternative terminal ingress states are:

- `SUPPRESSED` for policy-qualified ambient or unusable input;
- `REFLEX_APPLIED` for a deterministic control that needs no ordinary
  cognition;
- `REFLEX_AND_ADMITTED` when the control must also be retained for goal-state
  reconciliation and a possible concise response.

`REPLAN_REQUIRED` is a task-lifecycle state for unfinished Responsibility after
new user meaning, trusted observations, failed Work, dependency change, or other
new authoritative state. It is not permission to repair a rejected model output.
It may return only to canonical planning with the original/current Goal authority
intact. It cannot return to input classification, widen the Goal, bypass a new
material confirmation, or repeat a physical action without fresh authorization.
Physical TaskGraph work remains sequential.

### 3.0 Fast/Deep escalation is cognition depth, not repair

Fast handles cognition that is sufficiently obvious and cheap for the contemplated
progress. Deep is exceptional and receives authoritative source evidence when
remaining uncertainty or consequence justifies broader reasoning. A numeric confidence
score is evidence, not the sole escalation switch. Harmless ordinary conversation
should not pay a Deep-thinking tax merely because confidence is imperfectly calibrated.

The stage boundary remains exact. Fast Goal Interpretation may escalate once to Deep
Goal Interpretation for genuine consequential ambiguity in the person's intended
outcome, scope, or referent. Fast Planner may escalate once to Deep Planner for complex
HOW, dependencies, alternatives, or safety/resource reasoning. A missing execution
input or external result is not by itself a reason for Deep GI, and Deep Planner cannot
reinterpret Responsibility. A mechanically malformed DTO may be regenerated once under
the same meaning and schema. A semantic/grounding/coverage failure is not repaired by
rewriting previous model output; terminal Deep rejection fails closed or leads Planner
to a genuine user-resolvable clarification. The Host validates and contains; it does
not become a third semantic planner.

### 3.1 Continuous progress and the critical path

The state machine above records authoritative semantic, authorization, and
evidence milestones. It is **not** a requirement that every model call,
read-only acquisition, response preparation step, or Social-Attention proposal
wait for the previous box to finish in wall-clock time.

For each prospective piece of progress, Chromie evaluates four independent
questions:

1. is the current model-authored meaning sufficient for this exact progress;
2. are the required inputs, evidence, schemas, and dependencies already
   available;
3. do effect, safety, prohibition, confirmation, authorization, and resource
   boundaries allow this progress now; and
4. can later cognition refine Goal relationships without making this already
   allowed progress unsafe or falsely treating it as completion?

When the answers are sufficient, that part may advance while unrelated cognition
continues **only inside the authority already established for that part**. This is
the general runtime rule behind responsive conversation and later parallel work. Goal
Interpretation itself stops at Responsibility evidence; once that WHAT is sufficient,
Fast Planner is the first HOW owner. It must not be implemented as a greeting/weather
phrase rule, route shortcut, or second semantic authority.

One validated GI result first enters Fast Planner's bounded first-response phase. It
may author one immediately realizable Communicative Act. One bounded same-owner
Epistemic Qualification then accepts or rejects that immutable Act against the current
truth stage and admitted Evidence. It cannot rewrite, repair, retry, choose another Act,
or affect Goal/Capability decisions; failure is silence for this phase. After that
decision, Fast Advance cannot author or salvage substitute progress wording, and the same Fast Planner's
remaining Activity planning and Goal Association fan out concurrently from the
unchanged GI result. GA independently remains the only canonical Goal commit authority.
This is phased readiness inside one Planner, not an independent response author. The
resulting Fast Plan mechanically retains the already-committed Act and may contain
additional Communicative Acts and Capability Activities with explicit
sequential/parallel relations. A greeting can therefore be one complete Communicative
Act while GA records the conversational Goal; a weather request can contain a progress
Communicative Act and
an exact weather-read Activity in parallel.

GI reports only bounded unresolved meaning; it does not turn every absent value into an
InformationGap or decide which Capability inputs are required. Fast Planner compares the
immutable Responsibility with applicable planning, Agent-Skill, Capability, safety, and
provider contracts. It owns planning InformationGaps and the resolution order: explicit
or contextual evidence, trusted observation/query, an owner/schema default, a permitted
consequence-bounded ordinary default, user clarification, or fail closed. It asks only
when the user can resolve the need, the answer materially changes the next action, and no
safer authorized source is sufficient. Capability schemas constrain realization but
cannot redefine user meaning.

A short answer such as “Green tea” is read by the next GI against the pending
clarification and active Goal/Activity Context, emitted as a `modify`/`clarify`
relationship with the resolved semantic binding, and committed by GA as a new Goal
version. The pending Activity retains whether the question came from GI unresolved
meaning or a Planner-owned input need; this continuity does not transfer source-policy
ownership into GI. Deep Planner is reserved for complex HOW, dependencies, alternatives,
or consequential planning—not for asking a question Fast Planner already knows it must
ask.

Safe, side-effect-free, schema-valid reads may start without awaiting GA once their
Capability also explicitly declares parallel safety, needs no confirmation, and is
available. Their stable runtime request identity initially carries GI Responsibility
refs, never an inferred Goal ID. GA commits only Canonical Goal continuity and emits no
Work/replan decision. When a Goal commit intersects retained or provisional Work, the
canonical Fast Planner receives that Goal plus the relevant queued/running/completed
Activity and result state. It semantically decides which existing Activities still
advance the Responsibility and authors the complete desired Plan. A task shared by
multiple Goals still has one request identity and executes once.

Planner explicitly selects provisional Work for reuse through
`CanonicalPlanStep.reuse_activity_id` and complete Capability/argument/Goal/timing
semantics. Host validation checks that the
selected Runtime request, version, state, ownership, and exact Work match the snapshot;
it does not interpret Goal prose, relationship enums, result payloads, or Plan omission
as a compatibility decision. A newer state fails closed for the current dispatch; the
corresponding Runtime/Evidence change is the next bounded Planner-reactivation event
rather than a Host repair.
Runtime reuses validated Work or cancels pending/cancellable Work only after the Planner
decision and executes the corrected Plan. An incompatible observation that completed
before cancellation remains
unbound audit Evidence and cannot support Goal completion or response claims. Deep Plan
revisions follow the same cancel-pending/preserve-completed rule; neither result payloads
nor the Host infer a semantic correction.

Retained Runtime Work and same-turn provisional Work share the bounded
`work_reconciliation_activities` Planner input. Each item exposes one stable Activity
identity and its immutable Capability/argument/ownership/timing projection. A retained
request may be reused only when Planner selects the complete retained set with no
additional step; the new Plan is reconciliation-only, Runtime leaves the original
submission and Goal execution binding in place, and Host records or dispatches no
duplicate execution. If different or additional Work is needed, Planner omits all reuse
selections and authors the complete replacement Plan; Runtime validates and cancels the
old cancellable group before replacement dispatch. This atomic-group rule is the current
safe Runtime boundary, not a semantic judgment by Host.

This reconciliation repeats from meaningful state changes while Responsibility remains
open. A user update may require GI/GA before planning; provider Evidence, failure,
timeout, dependency readiness, or another trusted Work/Situation event can reactivate
Planner directly with the already-canonical Goal. Ordinary progress churn is filtered,
and an open Goal may wait passively without an always-running LLM.

Effectful work is different. Physical motion, object manipulation, writes,
message sending, media effects, and other committed side effects remain behind
the applicable canonical planning, confirmation, authorization, resource, and
provider-safety barriers. Sufficient understanding may allow cognition,
clarification, safe preparation, refusal, or another harmless branch to advance,
but it is not execution authorization.

The same principle applies to optional presentation work. Mechanical validation
and acoustic realization of a Planner-owned Communicative Activity must not become
a barrier to already-authorized work. Social
Attention is considered only when a concrete semantic primary human-observable
Activity exists: for example greeting, telling a joke, walking, singing, handover,
or show/play behavior. Vocal/Activity execution lanes, Vocal Expression modes,
Capability/provider requests, and transport objects describe realization only and
cannot create a Primary-Activity identity. Internal cognition or evidence arrival
cannot create a decoration opportunity by itself. Presentation
failure remains local and must not reopen Goal Interpretation, planning, or another
semantic reviewer. Runtime qualification should measure
at least the time to the first meaningful reaction and the time to the first
useful result separately; reducing one must not hide a long unnecessary critical
path in the other.

Example:

```text
existing Goal: go out for dinner tonight

user: "Will it rain heavily in Chongqing today?"

Goal Interpretation
  `-- Responsibility: provide today's Chongqing weather
      bindings: location=Chongqing, time=today
      relationship: new/reference existing dinner Goal as context

Fast Planner first response
  `-- authored speaking Activity: prospective progress
        `-- same-owner truth qualification: accept or reject only

concurrent continuation
  |-- same Fast Planner
  |     `-- Capability Activity: exact weather lookup (parallel)
  `-- Goal Association
        `-- commit canonical weather Goal and its relationship to dinner

Trusted Capability Runtime
  |-- start eligible safe read without waiting for GA
  |-- bind the same request ID to the weather Goal task-list view
  `-- provider -> trusted observation

trusted observation + canonical Goal relationships
  -> evidence-qualified answer focused on whether rain affects the user's plan
```

The acknowledgement can overlap Goal Association because speech is already an
observable Activity. The weather lookup itself cannot: provider work begins only
after canonical Goal binding and Planner selection.

### 3.2 General Progress inside the Continuous Mind baseline

The implemented readiness paths establish one general invariant: a piece of
progress may advance when its own meaning, dependencies, risk, and authority are
sufficient, without waiting for unrelated cognition. The broader Continuous Mind
synthesis is now recorded in
[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#414-continuous-mind-synthesis--compressed-architecture-baseline).
It deliberately does not introduce one runtime manager or persistent DTO for
each cognitive term.

The target Mind state is small: Stable Mind, unfinished Responsibility represented
canonically by Goal, selective Memory, and a bounded live Situation. Situation is
soft, revisable, mostly reconstructable cognitive state rather than another
authoritative fact store. Evidence/Interaction Ledger, existing Progress/Plan/
request/execution/outcome artifacts, and provider capability/runtime truth remain
the grounding/action substrate around that Mind state.

The executable turn state machine in this document records committed milestones;
it must not be mistaken for a wall-clock cognition pipeline. Meaningful new
Evidence may revise Situation, make an open Goal actionable, invalidate a Work
assumption, complete/reopen a responsibility, or justify deeper cognition. The
reaction may be none, deterministic/local, fast, slow, or overlapping fast
progress plus slower reasoning. Open Goals wait for relevant state change rather
than being polled by a background thought loop.

When Situation or Goal meaning changes, existing downstream Work is reconsidered
for semantic compatibility rather than blindly invalidated by version mismatch.
Compatible Work survives; incompatible Work is revised, superseded, cancelled,
or replanned. Historical Evidence, trusted execution/outcome records, and already
delivered speech are never rewritten; correction proceeds forward.

The same separation applies to lifecycle. `planning`, `waiting_for_user`,
confirmation, `scheduled`, `running`, retry/recovery, provider failure, and
timeout are Work/runtime conditions. They are not the target Goal lifecycle
truth. An `ExecutionOutcome` records what happened in execution; a Goal closes or
reopens only through Responsibility reconciliation against its current meaning
and trusted evidence.

Some later sections still describe the currently implemented Task/Goal lifecycle
projection using workflow labels such as `waiting`, `recoverable`, `failed`, or
`timed_out`. Those descriptions remain implementation evidence, not the final
ontology. The first cleanup slice in the Roadmap separates that runtime Work
state from canonical Responsibility state; `STATUS.md` remains authoritative for
what has actually landed.

Before adding new runtime state, first map the behavior onto Goal, General
Progress, Interaction Ledger/Context, CanonicalPlan, ExecutionOutcome, Memory,
Capability/provider state, and bounded live Situation projections. A new
first-class concept still requires an independently necessary lifecycle or
authority that those owners cannot express without information loss.

## 4. Gateway-to-Core contract

The Gateway emits a versioned `UserTurnEnvelope`. It is the only canonical
input object for a new Core turn.

Signal fidelity and semantic confidence are separate. ASR confidence/input usability
is Gateway evidence about what signal was captured; it may inform later cognition but
is not a confidence score for what the user meant. Goal Interpretation and Goal
Association own semantic judgment independently from that input-quality evidence.

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

- ordinary Goal meaning or Goal IDs;
- Goal-Interpretation route/intent labels;
- selected Agents, tools, skills, or capabilities;
- a plan or authorization;
- an execution claim;
- response text.

An admitted envelope enters Goal Interpretation directly. The resulting
`CoreInterpretationResult` carries Responsibility evidence only and is converted into a
typed `CognitiveWorkRequest` for Goal Association and subsequent planning. No route/intent
compatibility projection is created or reconstructed on the maintained path. Suppressed, unusable, and reflex-only
envelopes cannot enter ordinary Core cognition.

## 5. Goal understanding and planning

Goal Interpretation emits provider-neutral contextual Responsibility evidence, including
the proposed relationship to supplied Goals and bounded unresolved meaning interpreted
against any pending clarification. It does not create planning InformationGaps. The same
result first enters Fast Planner's bounded first-response phase; after that commitment,
remaining Fast planning and Goal Association continue concurrently. Fast Planner authors
the complete first Activity Plan and owns execution-input resolution; GA alone commits the
canonical Goal relation. This is model-authored planning, never a Host greeting phrase
table or `route == chat` shortcut.

```text
UserTurnEnvelope + Session Context
  -> Goal Interpretation
  -> Fast Planner -> first Communicative Activity or silence
  -> concurrent continuation
       |-> same Fast Planner -> remaining Activity Plan
       |     |-> Capability and still-needed Communicative Activities
       |     |-> input resolution or a user-resolvable clarification
       |     `-> Deep Planner only for complex HOW
       `-> Goal Association -> canonical Goal commit/version
  -> Host validates and Vocal Runtime mechanically realizes exact Planner wording
  -> deterministic Responsibility-to-Goal binding
  -> Goal-grouped Runtime task-list views
  -> terminal CanonicalPlan / Plan revision
  -> deterministic validation
  -> resource-aware scheduling, confirmation, and commitment
```

Fast and Deep canonical planning use the same `CanonicalPlan` contract. Fast Goal
Interpretation contributes provider-neutral Responsibility evidence; it does not author
response wording, Work, a Primary-Activity contract, Plan steps, execution lanes,
realization, exact Capabilities, or executable arguments. `completion_requires_work` is
only a need-for-work fact, never a Work description. Fast Planner owns HOW; Goal
Association owns only canonical Goal continuity and commit. Planner model reasoning
then chooses semantic Work/Primary Activities, Plan steps, parameters, ordering, and
per-goal prospective outcomes. Deterministic
code checks schemas, capability
availability, source-effect bounds, resources, confirmation requirements, and
forbidden low-level controls. Validation cannot invent missing meaning or
rewrite the plan into a nearby action.

Fast Planner owns complete bounded capability work. A terminal Fast Plan whose
Goal grounding, exact Capability, arguments, deterministic safety/authorization, and
confirmation policy validate may commit directly to Trusted Capability Runtime; Deep
is not an execution prerequisite or reviewer. A Fast contract/grounding failure stops
that path instead of being repaired by Deep. Deep Planner is invoked only for
nontrivial dependency, material alternative, novelty/broader planning context,
Plan-coverage difficulty, or safety/resource reasoning that truly requires wider
cognition. Genuine ambiguity in Responsibility meaning belongs to Deep Goal
Interpretation before planning; Deep Planner may not repair or reinterpret it.
Independent Responsibilities may therefore progress at different cognitive
depths; once each has canonical Goal grounding, a confirmation-free safe read may
execute while unrelated deeper cognition continues. A purely mechanical Planner DTO/schema failure may be
regenerated once under the same semantic meaning. Fast planning-grounding/coverage
rejection may escalate once to Deep when broader reasoning is warranted. Deep
planning-grounding/coverage rejection is terminal for that cognition attempt and
must not trigger another same-tier semantic pass. A confidence number alone
neither permits a bypass nor requires escalation, and it never authorizes an
effect.

### 5.1 One Mind: stable cached prefix plus bounded live projections

All cognitive stages belong to one Chromie Mind; separate model calls do not
create separate personalities or semantic authorities. Prompt/context projection
is therefore both a latency boundary and an identity-consistency boundary.

The Mind has a low-churn **stable layer** and high-churn **live projections**.
The stable layer contains owner-controlled state that normally changes only by a
deliberate configuration/content revision:

- Chromie's identity and self-concept;
- personality and interaction/expression style;
- worldview and values; and
- concise hard-boundary principles covering safety, authorization,
  evidence-truth, semantic authority, and strict prohibitions.

Where supported by Ollama/model serving, this stable layer should be arranged as
a reusable prompt prefix so prefix/KV caching can avoid repeatedly evaluating the
same Mind text. Cacheability is an execution optimization, not a new semantic
authority: changing the owner-controlled Mind invalidates the relevant cached
prefix. Identity/style remains relevant across cognition. Worldview and values
are also stable and cacheable, but a bounded role should reason over only the
portion it needs rather than receive a large active instruction burden merely
because the text is stable.

The live layer is projected by responsibility:

- Gateway Attention receives ingress/attention evidence and only the bounded
  interaction context required to decide admission; it does not need the full
  Goal graph or capability catalog.
- Goal Interpretation receives the admitted turn, bounded recent dialogue,
  active/recent Goal and Task progress, discourse focus, and enough capability
  semantics to recognize what kind of progress is being requested.
- Goal Association receives the richer Goal/Task/discourse view needed to decide
  continuity, reference, modification, relationship, or genuinely new work.
- Fast Planner receives the resolved work plus only relevant exact capability
  candidates, schemas, dependencies, resource/confirmation facts, and current
  evidence. It is fast because the problem and live projection are bounded, not
  merely because a smaller model happens to be configured.
- Fast Planner Evidence re-entry receives the existing Goal responsibility,
  exact Host-bound terminal Evidence, already-delivered interaction delta, and
  the compact stable Mind rather than unrelated live state. The result cannot
  infer a new Goal from its contents.
- Social Attention receives current interaction events, scene/target evidence,
  recent expressive history, primary activity state, eligible exact social
  capabilities, and the compact stable Mind.
- Deep Planner is the deliberate rich-context HOW path. When planning complexity or
  consequence warrants escalation, it may receive broader Goal relationships,
  relevant long-term memory, environment, capability state, trustworthy
  evidence, alternatives, long-horizon context, and the explicit reason deeper
  reasoning was required. Its stable Mind prefix remains the same owner-controlled
  identity, worldview, values, style, and principles; Deep receives more *live*
  context, not a different person.

Dynamic domain knowledge is not part of that stable layer. "Do not intentionally
harm a person or perform clearly prohibited conduct" may be a concise persistent
principle; answering whether a specific act is legal in a particular jurisdiction
requires current legal information to be acquired through the information
capability path with source and freshness evidence. The same rule applies to
weather, news, prices, schedules, current policies, and other externally changing
facts.

This projection rule applies to prompt design as well as data structures. The
stable Mind should be cache-friendly rather than re-tokenized as turn data, while
large history, catalog, evidence, memory, and world-state payloads remain dynamic
and are supplied only when the receiving cognition actually needs them.

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

Effectful requests and any request used directly as canonical Goal-completion
evidence remain bound to:

- the admitted turn;
- canonical plan ID and fingerprint;
- canonical step ID;
- one or more source goal IDs;
- exact skill identity and version;
- the exact canonical arguments and execution timing;
- the full committed SHA-256 identity of a versioned, non-empty declared output
  schema and bounded observation limits;
- timeout, cancellation, confirmation, and idempotency policy.

A bounded read-only acquisition that is allowed to start before canonical Goal
resolution is the narrow exception to the plan-first correlation shape, not to
evidence integrity. It must still retain the admitted turn identity, exact
capability and version, exact normalized arguments, committed output-schema
identity, provider/result provenance, cancellation/idempotency policy, and
timestamps. It may satisfy later canonical work only after deterministic exact
correlation establishes that the later Plan requested the same operation.
Otherwise it remains unused turn-scoped evidence and cannot complete a Goal or
silently replace the canonical request.

Independent non-physical work may use bounded concurrency only when capability
and resource contracts allow it. Physical work remains sequential. A specialist
handoff is an implementation detail; it never transfers ownership of the user
conversation or final answer away from the Core.

## 7. Execution outcome contract

Execution results return through a versioned `ExecutionOutcomeBundle`. It is
constructed by deterministic joins over the immutable plan, committed
requests, and trusted `CapabilityResult` or provider evidence. It is never inferred
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
Pre-action speech and auxiliary Social Attention decoration do not satisfy an effectful
user goal. Provider postcondition evidence such as `safe_idle=true` may support
a safety claim, but does not by itself prove every requested goal completed.

Exact correlation/schema validity proves evidence integrity, not every higher-level
claim's sufficiency. Where a Goal depends on a factual postcondition, the registered
capability/evidence contract may require claim-specific observation classes,
provenance/trust domains, freshness/validity, or corroboration. Provider declarations
say what can be observed; owner-reviewed policy says what is sufficient; trusted
Runtime checks it mechanically. Qualified factual state feeds existing Fast/Deep,
Goal/Planner, or Reflection paths and does not create a third routing/trigger system.

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
closed, validated `CapabilityRequest` field; it does not copy the raw schema into
request metadata. At closure, the current trusted `CapabilityDefinition` schema is
usable only when its digest exactly matches that commitment. A missing
commitment, missing definition, changed or invalid schema, or an empty schema
produces `schema_unavailable` with a bounded reason and exposes no provider
payload. This also keeps Soridormi capabilities whose compatibility catalog omits an
output schema fail-closed.

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
Planner-authored result communication. The retained audit record preserves the validation and
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
5. reactivates Fast Planner with one immutable, version-consistent
   Goal/Evidence result bundle.

Streaming changes scheduling, not authority. Raw model-token deltas, partial JSON,
private reasoning, and incomplete sentences are not speech contracts and must never
reach TTS. In maintained cognitive apply, Goal Interpretation does not author speech.
The first early speech contract is an independently worded, typed Fast-Planner
Communicative Act.
The Host may schedule that Activity as soon as its provider-free claim/effect boundaries,
turn correlation, cancellation generation, and Vocal transport contract validate; it
need not wait for Goal Association or unrelated later response fields. Goal
Interpretation has no parallel early-speech contract beside Fast Planner Activity.

Current-turn Communicative-Act reuse is correlated by the exact speech-event
ID together with its turn, structured stage, purpose, route, intent,
commitment, source Goal IDs, canonical Plan identity/fingerprint, delivery
role, claim types, and completion-claim restriction. An event created before
Goal Association remains explicitly unbound; the Host does not invent Goal or
Plan provenance after delivery. Once an event is Goal-bound, a later response
stage cannot reassign it to unrelated canonical Goals or a different Plan.
Generated or scheduled state is not delivery evidence; only playback-started or
completed state satisfies the audible act. A ResponseStage may reference a
pending event without synthesizing a duplicate, and Runtime may fulfill that act
once if the referenced event becomes `not_delivered`. Text equality is checked
only to preserve event payload integrity. Independent result, failure,
limitation, clarification, confirmation, progress, and completion stages retain
their own delivery obligations.

Cross-lane awareness is transported through the append-only `Interaction
Ledger`. Existing owners append only typed facts they are qualified to observe:
playback owns audible speech, Cognitive Runtime owns Goal/Plan decisions, the
Trusted Capability Runtime owns committed provider work and Social Attention
results, and `ExecutionOutcomeBundle` closure owns trusted Activity and
provider-backed Vocal outcomes. No entry edits or upgrades another owner's
evidence.

Before Goal Association, bounded continuity remains available to Goal Interpretation and
Fast Planner. First, Gateway-admitted user turns are published immediately as accepted
dialogue history; this preserves references across overlapping turns without creating a
Goal or Task. Second, recent session events form volatile Interaction Context for Goal
Interpretation, Fast Planner, and Goal Association. Goal Interpretation receives that
dialogue together with compact active/recent Goal and Task/progress projections.
Goal Association receives the richer bounded Goal/Task/discourse view. Within one
conversation, Goal Association is serialized at its semantic-state boundary; a
later association refreshes continuity after the association already occupying that
boundary commits. Refreshed dialogue is causally cut at the current admitted turn,
so later speech can inform a follow-up but can never flow backward into an earlier turn.
After canonical Goal IDs exist, Runtime projects only Interaction Ledger events
bound to those Goals plus explicitly unbound Fast Planner Communicative Activities from the same turn. Fast
Planner, Deep Planner, and other later cognitive stages receive the bounded
Goal-scoped projection to decide the
still-needed delta. Scheduled speech remains distinct from audible speech,
committed work remains distinct from terminal evidence, and a speech event can
never become execution or completion evidence.

The maintained result-scheduling contract distinguishes result evidence from
speech scheduling. Dedicated safety/control evidence may deterministically
pre-empt current output; an ordinary progress or result stage remains ordered
until an appropriate speech opening; internal-only evidence updates Goal/task
state without creating a speech stage. A newer ordinary turn or output-only
barge-in may invalidate already-playing or obsolete queued audio, but it cannot
make an independent Goal's later evidence-bound result stale. Only explicit
scoped cancellation, supersession, or a Core-authorized semantic interruption
may suppress that future result obligation.

### 8.1 Pre-execution speech

For effectful work, the pre-execution response contract is prospective. It may
acknowledge the understood request, ask for confirmation or clarification,
state that a validated action is about to begin, provide a state-validated
progress update, or explain refusal/unavailability. It must not claim that a
tool found a result, an action completed, the robot is safe, or a user goal was
satisfied. Speech such as "I'm starting" requires committed execution state;
planning output alone is insufficient.

Pre-execution speech is never execution evidence and never closes an effectful
goal. Fast or Deep Planning may carry a prospective `response_text` alongside
executable steps when that text represents a still-needed conversational delta.
When a structurally valid Fast Plan escalates for a separate validation defect, the
source-authored candidate may be retained only as an undelivered advisory to Deep
Planning; retention makes no truth claim, is never delivery evidence, and must be
reconsidered against the Interaction Ledger and current Plan authority;
`chromie.speak` still does not become a task-plan leaf. Planner uses the Plan and
Interaction Context to author, reuse, or omit that exact Communicative Activity
according to what is actually new; the Host validates but does not rewrite it. A
non-effectful conversational turn
may move directly to `READY_TO_RESPOND`; its Core-owned answer is final for that
turn and is grounded in the admitted input and any validated context or retrieval
evidence, not in a fictional execution result.

An immediate acknowledgement may claim only hearing or evaluation. A proposal
or confirmation requires a validated plan and the applicable confirmation
state. Speech such as "I'm starting" requires committed execution, and a
progress update requires correlated runtime evidence. Cancellation invalidates
stages that have not begun; speech already heard remains delivery evidence.

### 8.2 Evidence-bound post-execution speech

After terminal results have been joined and every executable Goal reconciled, the Host
reactivates Fast Planner with the immutable Goal/Evidence result bundle. Fast Planner,
not a deterministic or model-backed post-execution composer, owns the human-relevant
answer/follow-up/silence decision and exact wording. It cannot treat the result as a new
user turn, reassign it to another Goal, or add execution authority. Before Runtime
commits an answer, one bounded same-owner Epistemic Qualification accepts or rejects
the immutable wording against the exact Goal/Evidence snapshot. It cannot rewrite the
answer; rejection or unavailability delegates once through the existing Deep-Planner
path or fails closed. The Host only validates provenance, structured claim boundaries,
and delivery.

The final response must:

- cover every relevant goal exactly once;
- distinguish success, partial completion, failure, timeout, refusal,
  cancellation, and `not_run`;
- include useful trusted tool output when present;
- avoid internal IDs and implementation narration;
- make no completion, observation, memory, movement, or safety claim without
  matching evidence;
- treat missing historical evidence as `unknown` unless the relevant collection and
  retention policy establishes complete closed-world coverage; ordinary response
  wording must be able to say that Chromie cannot confirm or rule something out;
- be emitted once for the reconciled interaction.

Only speech with a completed delivery result is added to model-visible
conversation history. The same rule applies to host confirmation and recovery
prompts: a scheduler, provider, or playback-start failure cannot create an
assistant turn that the user never heard.

Delivered post-execution tool speech is retained with a Host-authored
evidence-bound marker plus its source Goal and Canonical Plan IDs. A later turn
may use that bounded user-visible dialogue to interpret or restate the same
terminal Goal, preserving its measurements and conditions exactly. The
verified-tool index alone contains no result facts and cannot authorize a
direct external-fact response; without matching delivered dialogue, the plan
must retrieve exact evidence, perform a fresh read, or escalate.

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
normal validation, Trusted Capability Runtime, Soridormi preflight, outcome reconciliation,
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
ID and fingerprint, then dispatches `specific_goal` to Trusted Capability Runtime. Goal state
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

- at most one mechanical DTO regeneration at a model stage that owns a structured-output contract;
- no same-tier semantic replan budget;
- explicit tool and provider timeouts;
- cancellation propagated through the host and provider;
- no unlimited Agent handoff or tool-call loop;
- no automatic retry of material physical work;
- no final completion claim from prospective planning output;
- ordinary newer turns preserve independent in-flight work rather than
  preempting it;
- no stale final response after explicit control or a Core-authorized decision
  preempts an interaction.

Failures remain attributed to their earliest responsible boundary:

- Gateway/admission;
- goal association;
- Fast or Deep planning;
- deterministic validation or authorization;
- Agent/tool/provider execution;
- outcome correlation and reconciliation;
- final Planner communication or delivery.

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

The runtime records direct/Fast/Deep path classification and the reason for a
Deep invocation. Session evidence also records TTS request, first PCM, and
playback events, but the qualification trace still needs one correlated
first-valid-speech-commitment boundary plus model queue/evaluation and
contract-repair count/duration before it can support an end-to-end response-
latency claim. Do not infer those missing slices from unrelated timestamps.

One trace should answer: what entered, what Chromie understood, what it planned,
what was authorized, what actually ran, what evidence returned, how each goal
ended, and why Chromie said the final words.

## 12. Implemented boundary and retained contract names

The contract-first loop baseline is implemented:

1. `UserTurnEnvelope` is built and dual-recorded;
2. the Cognitive Gateway projects only admitted envelopes into the Agent-owned
   Goal-Driven Cognitive Core;
3. configured authoritative lanes use Goal Association, canonical planning,
   deterministic validation, and manager-owned delegation;
4. committed requests bind exact plan/step/skill/arguments/timing/schema
   identity;
5. `ExecutionOutcomeBundle` joins results and traces to the immutable plan,
   retains exact per-goal states, and commits them to goal state;
6. bounded schema-validated `ModelObservation` values are the only provider
   payloads visible to Planner post-Evidence communication;
7. ordinary overlapping turns retain independent lifecycle identity, while
   explicitly cancelled, superseded, stale-output, or recovery-waiting turns
   retain their evidence and suppress only invalid late final speech;
8. recoverable embodied failures use a separately fingerprinted,
   confirmation-bound child plan.

The five Gateway responsibilities remain logically distinct even when co-deployed.
The Core uses typed Goal Interpretation and `CognitiveWorkRequest` contracts; no
route/intent compatibility projection remains in the maintained path.

The maintained external cognitive endpoint is `chromie-agent`
`POST /cognitive-core/interpret`. There is no `/route` compatibility API or
independent Goal Interpreter service.

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
- final Communicative Activity emits no skill or action;
- an independent ordinary newer turn does not cancel earlier work;
- explicit deterministic or Core-authorized interruption suppresses stale final
  speech only within its effective scope;
- an undelivered confirmation, recovery, or final response does not enter
  model-visible history;
- an embodied emergency dispatches Soridormi's dedicated E-stop contract;
  generic cancellation cannot support an E-stop or safe-idle claim;
- dedicated E-stop and safe-idle claims require explicit correlated Soridormi
  evidence.

Current Level A requirements enforce that a grounded greeting or direct speech-
only answer invokes neither planner and emits one answer; complete bounded
capability work terminates at Fast when validation accepts it; and work whose
semantic complexity or safety/resource reasoning requires the wider boundary
records a specific Deep reason. Runtime latency and physical-audio claims still
require their separately retained target evidence.

Level A and unit tests prove contract behavior only. Provider-backed live-text,
simulator, microphone, and physical-robot claims require their corresponding
retained evidence. Current evidence status is reported in
[STATUS.md](STATUS.md).
