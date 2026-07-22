# Goal-Driven Cognitive Architecture

Status: Maintained architecture constitution
Scope: Chromie cognition, planning, interaction, validation, and execution
Implementation state: Implemented through the unified PR1-PR8 cognitive runtime;
retained live-text and MuJoCo evidence for that authoritative path remains open

## 1. Purpose

Chromie has migrated its maintained semantic-planning path from a skill-routed
interaction system to a goal-driven cognitive runtime. This document defines
the architectural principles and contracts that current and future Router,
Agent, memory, planning, social interaction, and execution work must follow.

The central change is simple:

> Chromie plans to satisfy user goals. It does not merely match utterances to
> skills.

This document is intentionally more stable than any individual prompt, model,
service, or implementation. Models, prompts, and internal modules may change.
The cognitive invariants defined here should change only through explicit
architecture review.

## 2. Motivation

A skill-first system tends to fail in predictable ways:

- a compound request is narrowed to the first recognized skill;
- every new utterance is treated as a new task;
- parameters are filled or rejected without considering consequence;
- a planner partially emits actions before the complete goal is understood;
- social gestures become user tasks;
- semantic interpretation leaks into deterministic runtime code;
- deep planning loops back through fast routing and loses context;
- speech claims diverge from committed execution.

The live interaction history that motivated this RFC includes examples such as:

- “walk forward for fifteen seconds while blinking” becoming only walking;
- “make it iced” becoming a new task instead of modifying the coffee goal;
- “what parameter is missing?” losing the original information gap;
- a generic clarification being spoken while a partial action still executes;
- a backend model describing itself instead of speaking as Chromie;
- fixed gestures being added to every chat turn regardless of context.

These are not isolated prompt defects. They are signs that the architecture
needs a stable semantic object above routes and skills: the user goal.

## 3. Constitutional principles

### 3.1 Goal first

The primary cognitive object is the user’s desired outcome, not a route,
intent, capability, or skill.

A skill is one possible means of satisfying a goal. The same goal may be
satisfied through different skills, composed plans, observation, clarification,
or an alternative plan depending on context.

### 3.2 Continuity before creation

Every user turn must first ask:

> Does this belong to something Chromie is already doing, discussing, waiting
> for, or recently completed?

Only after goal association should Chromie decide whether the turn creates one
or more new goals.

This prevents task explosion and preserves conversational continuity.

### 3.3 Coverage before matching

A planner must evaluate whether the complete user goal is covered. Finding one
matching skill is insufficient.

For a request containing walking and blinking, recognizing `walk_forward` does
not establish complete coverage. Partial coverage must escalate or clarify; it
must never silently become execution.

### 3.4 Meaning before skills

The model interprets the user’s meaning, relationships, constraints, and
priorities before choosing implementation capabilities.

Normal semantic understanding must not be implemented through phrase tables,
regex intent rules, hidden skill maps, or action-name keyword branches.

### 3.5 Single-direction cognition

The normal planning path is monotonic:

```text
associate → segment → fast plan → deep plan if needed → validate → commit → execute
```

The Deep Planner never sends a goal back to the Fast Planner for another
semantic decomposition pass.

Both planners may use the same capabilities and shared planning primitives.
They differ in context breadth, latency budget, and planning depth—not in skill
ownership.

### 3.6 Planning before execution

No model may directly execute, authorize, or commit a side effect.

Every plan, regardless of planner tier, must enter the same deterministic
validation and commitment boundary.

### 3.7 Evidence before claim

Chromie may claim completion, observation, tool results, memory writes, or
physical execution only when trusted runtime evidence supports the claim.

A model proposal is not evidence.

### 3.8 Validator authority

The validator is the authority for structural correctness, current capability
availability, schemas, provider state, resource conflicts, confirmations,
versions, authorization, and execution grants.

The validator does not decide what the user meant or what alternative best
preserves the user’s goal.

### 3.8.1 Single semantic authority

For an enabled route, one turn has one authoritative semantic planner. In
maintained `apply` mode that owner is the unified Goal-driven Runtime. Exact
Router actions may be consumed only as compatibility-adapter input; they do not
form a second semantic plan, and a turn acquired by the Goal-driven Runtime
cannot fall through to the old CapabilityAgent planner after a failure.

The old CapabilityAgent semantic planner is retained only as an explicit
emergency path. It requires the host gate, the Agent gate, and an authoritative
emergency claim whose non-empty `turn_id` exactly matches the request turn.
Missing, empty, or cross-turn claims fail closed before model planning. The
claim is internal routing metadata, not caller authentication or a consumed
single-use nonce. Emergency compatibility does not widen execution authority:
its output still crosses the same host validation, confirmation, Skill Runtime,
provider, and evidence boundaries.

### 3.9 Semantic choice, deterministic enforcement

LLMs decide semantic relationships, parameter importance, goal satisfaction,
alternative plans, and natural language.

Deterministic code enforces contracts and safety. It must not replace semantic
reasoning with action-specific rules.

### 3.10 Interaction is independent from task execution

Speech, social attention, and user-task execution are separate plans that may be
coordinated but must not be conflated.

A blink selected to express attention is not automatically part of the user’s
goal. An explicit user request to blink is.

Likewise, response transport is not a user-task step. In the maintained
Goal-driven Runtime, a conversational goal is a `respond` outcome and the
Response Composer owns its speech plan. A transport capability such as
`chromie.speak` may remain available to legacy/native interaction surfaces, but
it is not a Fast or Deep Planner leaf.

### 3.11 Truth over guessing

Chromie may use bounded ordinary defaults when the model judges a missing value
to be low-consequence and the schema permits it. Material, risky, costly,
irreversible, or authorization-related parameters require user input or trusted
context.

When uncertain, Chromie asks naturally and specifically.

### 3.12 Graceful degradation

Optional cognition may fail without corrupting the primary task. Social
attention, response polish, and report-only review must not block or fabricate
execution.

## 4. Core cognitive objects

### 4.1 User turn

A bounded user contribution containing the original utterance, ASR confidence
and quality signals, conversation identity, current environment snapshot, and
turn metadata.

A user turn is evidence. It is not itself a goal.

### 4.2 Semantic goal

A versioned representation of a desired outcome.

A goal should preserve natural meaning rather than forcing every request into a
fixed taxonomy.

Suggested shape:

```json
{
  "goal_id": "goal_123",
  "version": 3,
  "description": "Walk forward for fifteen seconds while blinking naturally",
  "source_text": "往前走十五秒，然后边走边眨眼睛",
  "beneficiary": "user",
  "constraints": {
    "duration_s": 15,
    "relationship": "concurrent"
  },
  "success_criteria": [
    "forward movement completes",
    "blinking occurs during movement"
  ],
  "status": "active"
}
```

### 4.3 Goal set

The set of independent goals found in one user turn after association with
existing goals.

One utterance may create zero, one, or multiple new goals. A modification to an
existing goal does not automatically create a new goal.

### 4.4 Goal relationship

The semantic relationship between the current turn and existing goals.

Supported relationships should include:

- `continue`
- `modify`
- `clarification_answer`
- `confirm`
- `reject`
- `cancel`
- `pause`
- `resume`
- `query_status`
- `correct`
- `replace`
- `merge`
- `split`
- `reference`
- `new`

These relationships are model-proposed and deterministically validated against
known goal IDs and lifecycle state.

### 4.5 Information gap

A structured fact required to continue planning.

```json
{
  "gap_id": "goal_123:duration_s",
  "description": "walking duration in seconds",
  "importance": "material",
  "blocking": true,
  "preferred_resolution": "ask_user"
}
```

Information gaps remain attached to the original goal and survive turns.

### 4.6 Canonical plan

The only plan format accepted by validation and execution, regardless of
planner tier.

```json
{
  "plan_id": "plan_456",
  "goal_id": "goal_123",
  "goal_version": 3,
  "plan_version": 2,
  "planner_tier": "deep",
  "coverage": "complete",
  "relation": "exact",
  "steps": [
    {
      "step_id": "step_walk",
      "skill_id": "soridormi.walk_forward",
      "args": {"duration_s": 15, "speed": "quick"},
      "timing": "parallel"
    },
    {
      "step_id": "step_blink",
      "skill_id": "soridormi.blink_eyes",
      "args": {"count": 4},
      "timing": "parallel"
    }
  ],
  "information_gaps": [],
  "requires_confirmation": true
}
```

### 4.7 Social attention plan

An auxiliary interaction plan describing optional nonverbal attention.

It is not a user goal unless the user explicitly requested the behavior.

### 4.8 Execution evidence

Trusted records from Skill Runtime, tools, memory stores, and Soridormi that
prove what was attempted and what completed.

### 4.9 Experience record

A retained interaction outcome used for evaluation, scenario mining, and
owner-reviewed improvement. Experience never silently changes safety policy or
core principles.

## 5. End-to-end cognitive pipeline

```text
User Turn
  ↓
Deterministic emergency / stop / audio-validity boundary
  ↓
Bounded active-goal projection
  ↓
Goal Association
  ├─ existing goal relationship
  ├─ ambiguity requiring natural clarification
  └─ no existing relationship
  ↓
Goal Segmentation
  ├─ update existing goals
  └─ create independent new goals
  ↓
Fast Planner per goal
  ├─ complete coverage → Canonical Plan
  └─ partial / uncertain / complex → Deep Planner
                                      ↓
                                Canonical Plan
  ↓
Deterministic Validator
  ├─ valid exact plan → commit or confirm
  ├─ valid material alternative → confirm
  ├─ information gap → wait for source
  ├─ unavailable / refused → explain
  └─ structured rejection → bounded replan by originating tier
  ↓
Skill Runtime / Tools / Memory / Soridormi
  ↓
Execution Evidence
  ↓
Response Plan + optional Social Attention Plan
  ↓
Experience and Scenario Mining
```

### 5.1 Model-facing Goal Association boundary

Goal Association must not expose Chromie's persistence and lifecycle objects
directly to the language model. Its model-facing output is intentionally small:

- relationships to exact active goal IDs;
- one natural-language description per independent new goal;
- or one natural clarification.

The host owns all transport and persistence mechanics, including turn IDs,
association IDs, goal IDs, versions, source text, default object/constraint
containers, metadata, and construction of the canonical
`GoalAssociationResolution`. Ignoring model-authored transport noise such as an
extra `id` is not semantic interpretation; semantic descriptions and
relationships still come only from the model and remain subject to schema and
host validation.

## 6. Goal continuity

### 6.1 Association precedes segmentation

The system must not begin by asking how many goals the current sentence
contains. It must first determine whether the sentence continues existing work.

Example:

```text
User: 给我拿杯咖啡。
Later: 冰的。
```

The second turn modifies the existing coffee goal. It does not create a new
“iced” goal.

Example:

```text
User: 给我拿杯咖啡。
Later: 顺便查一下天气。
```

The second turn creates a new weather goal while leaving the coffee goal
active.

### 6.2 Bounded candidate context

Goal association should consider a bounded projection of:

- active goals;
- goals waiting for user input;
- goals awaiting confirmation;
- recently completed or cancelled goals when reference is plausible.

It must not load unlimited history.

Candidate retrieval may narrow the context, but retrieval scores, recency,
entity overlap, and keyword matches are advisory only. They cannot decide the
relationship.

### 6.3 Ambiguity handling

When more than one active goal plausibly matches, Chromie asks a natural
question.

Bad:

> Select task ID goal_123 or goal_456.

Good:

> 你是说咖啡不用了，还是天气也不用查了？

The clarification wording is model-generated from goal summaries. Runtime code
only validates that referenced goal IDs exist.

### 6.4 Goal versioning

Every material goal modification increments the goal version.

A new goal version may invalidate:

- the previous plan;
- request-bound confirmation;
- queued work;
- an execution grant;
- stale response commitments;
- information gaps no longer relevant.

Old versions remain auditable and become superseded.

### 6.5 Goal continuity versus task lifecycle

Goal continuity is cognitive. Task lifecycle is operational.

- Goal continuity decides what the user is referring to.
- Runtime tasks record planning, waiting, confirmation, execution, completion,
  failure, or cancellation.

The two must be linked but not conflated.

The link is explicit and scoped. A model-facing semantic `goal_id` is not the
same identifier as the host `task_id`; the host resolves the semantic goal to
its owning task context and binds each canonical speech or skill request by
`source_goal_ids`. Provider completion, refusal, failure, timeout, or
cancellation updates every bound goal independently. A conversational
`respond` goal likewise remains active until its scoped speech request has
runtime delivery evidence; producing Response Composer text is not completion.
This prevents a completed compound action from remaining in the active-goal
projection and being accidentally associated with a later turn.

### 6.6 Active goals protect conversational continuity

A goal remains conversationally active while it is planning, waiting for user
input, awaiting confirmation, executing, paused, or recoverably blocked. It does
not become disposable merely because no provider request is currently running.

Soft-topic and idle-boundary heuristics must not clear active goals. A short
answer after a long pause may still resolve an existing information gap.
Candidate history remains bounded, but goal lifecycle is the authority for
whether continuity is still possible.

### 6.7 Explicit reset is narrower than semantic cancellation

Whole-conversation reset is an operational control and requires an explicit
whole-utterance instruction such as “start a new conversation” or “reset the
session.” Phrases such as “算了”, “不用了”, or “never mind” are semantically
ambiguous. They must reach Goal Association so the model can determine whether
one goal, several goals, or the current proposal is being cancelled.

A deterministic reset phrase table must never pre-empt normal goal association.

## 7. Multi-goal segmentation

### 7.1 Independent responsibility test

A turn contains multiple goals when it creates independent user outcomes that
may be planned, completed, cancelled, or reported separately.

Example:

> 记住我只喝美式，然后帮我拿杯咖啡，再查一下天气。

Possible goals:

1. remember a coffee preference;
2. obtain coffee;
3. retrieve weather.

### 7.2 Plan steps are not goals

Example:

> 先看看有没有咖啡，没有就做一杯。

This is one goal with a conditional plan, not two user goals.

### 7.3 Segmentation output

```json
{
  "associations": [],
  "new_goals": [
    {
      "description": "remember that the user drinks only Americano",
      "independent": true
    },
    {
      "description": "obtain a coffee for the user",
      "independent": true
    },
    {
      "description": "report the current weather",
      "independent": true
    }
  ]
}
```

### 7.4 Response composition

Multiple goals do not require multiple awkward acknowledgements. A response
composer may naturally consolidate them while preserving independent lifecycle
and evidence.

Semantic composition belongs to a model. The Orchestrator validates references,
commitments, versions, and evidence; it does not concatenate strings to imitate
understanding.

### 7.5 Independent goals may end the same turn differently

A multi-goal turn does not require one global terminal outcome. One independent
goal may be executable while another needs clarification, is unavailable, is
refused, or can be answered immediately. The canonical plan therefore records a
per-goal outcome and associates every executable step and information gap with
the goals it serves.

Example:

```text
User: 点一下头，再往前走。
Goal A: nod once          -> execute
Goal B: walk forward      -> clarify duration
```

The valid result may execute Goal A while keeping Goal B in
`waiting_for_user`. It must not execute an incomplete step for Goal B, and Goal
B must not prevent a fully independent, safe Goal A from completing.

A `mixed` canonical-plan disposition means complete accounting of all goals,
not complete satisfaction of every goal. Each goal retains its own disposition,
coverage, satisfaction, response, information gaps, and execution evidence.

## 8. Hierarchical planning

### 8.1 Fast Planner

The Fast Planner is a low-latency semantic planner over:

- the complete current goal;
- a compact self model;
- bounded active-goal context;
- common capabilities;
- essential provider and safety state.

It may:

- answer simple chat;
- produce a complete direct common-skill plan;
- propose a low-consequence bounded default;
- produce a social attention plan;
- escalate.

It must report coverage:

```text
complete | partial | uncertain
```

Only complete, high-confidence, structurally valid coverage may proceed to
validation.

The planner model emits a flat semantic DTO, not the canonical transport
envelope. Plan identity, schema version, planner tier, and authoritative
top-level Goal IDs are host-owned. Model-authored steps must name the exact
Goal IDs they serve through `source_goal_ids`.

For a Fast Planner request containing multiple authoritative goals, the model
emits one required decision record per Goal ID rather than a CanonicalPlan-shaped
step/outcome graph. Each decision selects exactly one common-catalog skill, a
direct conversational response, or semantic escalation. The host generates
step IDs and compiles ownership mechanically from the keyed decisions before
shared CanonicalPlan validation. Simple common-catalog `execute + respond`
combinations may terminate as `mixed`; goals requiring more than one skill,
clarification, unavailable or refused judgment, material alternatives, rare
capabilities, or broader context escalate. Contract failure is not semantic
escalation. The implemented contract and qualification matrix are defined in
[Fast Planner Multi-Goal Contract Path](FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md).

### 8.2 Deep Planner

The Deep Planner receives:

- the original user turn;
- complete associated goal state;
- any advisory fast-planner draft;
- the full capability registry;
- schemas and affordances;
- provider, environment, resource, and safety context;
- memory and trusted services;
- current information gaps and confirmations.

It may produce:

- exact plan;
- safe adjustment;
- alternative plan;
- partial plan requiring approval;
- context acquisition;
- specific clarification;
- unavailable;
- refused.

Deep Planner and single-goal Fast Planner use the shared flat
`PlannerModelOutput` boundary. Multi-goal Fast Planner uses the decoder-tight
`FastPlannerMultiGoalPlanOutput` boundary. In every case, the planner model owns
all semantic plan fields: disposition, coverage, steps, step identifiers,
skill selection, arguments, ordering, goal ownership, per-goal outcomes,
response content, and satisfaction judgments.

For complete multi-goal planning, per-goal outcomes form an exact object keyed
by every authoritative Goal Association ID. The key is the identity; an outcome
value cannot repeat or replace it. After validation, the host may only add the
canonical identity envelope and convert the goal-keyed object to the ordered
canonical outcome list. It must not compile, infer, or repair semantic plan
content from the user utterance.

`plan_relation` and `user_confirmation_required` are typed semantic decisions
at the model boundary. A safe adjustment or alternative must be executable and
must require confirmation. They are validated before being transferred to the
host-owned canonical envelope.

### 8.3 No planner loop

The Deep Planner does not send simple steps back to the Fast Planner.

Simple skills are leaf nodes in either planner’s canonical plan. Skills do not
belong to a planner tier.

### 8.4 Shared planner primitives

Both planners may use shared deterministic or retrieval primitives:

- project active goals;
- retrieve capability candidates;
- inspect schemas;
- fetch provider state;
- obtain environment observations;
- validate a canonical plan;
- compare goal and plan versions.

Shared primitives must not introduce a second semantic authority.

### 8.5 Bounded replan loop

A limited loop between a planner and the validator is allowed when validation
returns a structured rejection.

Example:

```text
plan v1: walk and blink concurrently
validator: concurrency not supported
plan v2: walk, then blink
result: material alternative requiring confirmation
```

Requirements:

- maximum replan count;
- explicit rejection reason;
- monotonically increasing plan version;
- no identical retry;
- same goal version unless the goal itself changes;
- clarification or unavailable result when the budget is exhausted.

## 9. Goal satisfaction and coverage

The planner’s objective is not “find a skill.” It is:

> Find a verifiable plan that maximizes satisfaction of the user’s goal within
> current safety, capability, authorization, and environment constraints.

Suggested output:

```json
{
  "coverage": "complete",
  "satisfaction": {
    "requested_outcomes": 2,
    "covered_outcomes": 2,
    "material_changes": [],
    "unresolved_constraints": []
  }
}
```

A numeric score may be useful diagnostically but must not replace semantic
explanation of what is covered, changed, or unresolved.

Planner satisfaction is prospective plan adequacy: it evaluates what the
proposed response and steps would satisfy if they complete successfully. It is
not execution progress. A fully covering plan may therefore be `exact` before
execution, while pending execution by itself is not an unmet planning
requirement. Completion speech and terminal Goal state still require trusted
runtime evidence.

Partial satisfaction is not authorization to execute a degraded plan.

For a mixed multi-goal plan, satisfaction thresholds apply to each executable
or directly answered goal. An unavailable, refused, or waiting goal may lower
the aggregate diagnostic score without invalidating a fully satisfied,
independent executable goal. Aggregate satisfaction remains useful for audit,
but it must not silently turn all-or-nothing behavior back on.

## 10. Parameter resolution

### 10.1 Semantic ownership

The planner decides whether a missing parameter can be supplied by:

- explicit user language;
- schema default;
- owner-approved preference;
- low-consequence ordinary default;
- current observation;
- trusted service;
- user clarification;
- or no valid source.

### 10.2 Consequence-aware choice

Low-consequence, reversible, bounded parameters may receive a model-selected
ordinary value when allowed by schema and policy.

Material examples that normally require stronger evidence include:

- duration or destination for movement;
- safety-sensitive speed;
- external cost;
- authorization;
- irreversible changes;
- privacy-sensitive disclosure;
- physical interaction with a person.

This is not a fixed field-name table. The model reasons from field description,
effects, bounds, provider constraints, and current context.

### 10.3 Specific clarification

Chromie should ask for the actual missing fact.

Bad:

> I need more parameters.

Good:

> 你希望我往前走多久？

When useful, the model may offer bounded choices naturally.

### 10.4 Persistence

A blocking information gap keeps the original goal active in
`waiting_for_user`. A later answer updates that goal and triggers replanning.

## 11. Alternative planning

### 11.1 Plan relations

Canonical plans should declare one of:

- `exact`
- `safe_adjustment`
- `alternative`
- `partial`
- `none`

### 11.2 Material alternatives require confirmation

If the requested goal cannot be satisfied exactly but a meaningful alternative
exists, Chromie proposes it naturally and executes nothing until the user
confirms.

Example:

> 我还不能确认边走边眨眼是否安全，但可以先走十五秒，再眨眼。可以吗？

### 11.3 Safe autonomous adjustment

A safe adjustment may proceed without an additional confirmation only when:

- it preserves the user’s material outcome;
- policy explicitly allows that class of adjustment;
- it does not add cost, risk, or irreversible effects;
- the adjustment is recorded and explained when relevant.

Reducing speed for stability may qualify. Dropping an explicitly requested
blink action usually does not.

### 11.4 Atomic commitment

All steps in a complete or alternative plan are validated before any effectful
step is committed. An invalid second step must not leak a valid first step into
execution.

Goal-state mutation also follows a two-phase boundary:

```text
associate and plan
-> compose response
-> trusted host prepares and validates the InteractionResponse
-> atomically commit all goal operations
-> confirm / execute
```

If host preparation, capability validation, or any goal operation fails, none of
the staged goal mutations from that turn become durable. Execution request IDs
and terminal provider evidence are then recorded against every source goal they
serve; optional social-attention requests never enter the primary user-goal
lifecycle.

Effect authority is also monotonic within one turn. The configured cognitive
lane allowlist says which kinds of plans the deployment can support, but the
current Router decision supplies the turn's maximum effect envelope. A
speech-only `chat` turn cannot become `robot_action` after Goal Association or
planning merely because both lanes are enabled. Such escalation stops at the
authority boundary before Response Composition, capability validation, or any
SkillRequest is emitted.

For an accepted effectful plan, executable wording from the Response Composer
is not treated as execution evidence. The trusted adapter derives a short
prospective cue from the canonical plan and actual confirmation state, excludes
pre-execution progress/final claims, and requires playback to start before a
dependent physical request may begin. If that delivery barrier fails or times
out, all queued chunks from the cue are invalidated so delayed synthesis cannot
announce an action after the runtime has stopped it.

## 12. Social interaction layer

### 12.1 Social Attention is a behavior domain

A turn coordinates an immutable user task plan with response language and an
optional Social Attention expression plan. Social Attention is not one skill and
not a deterministic utterance-to-gesture mapping. It is a model-authored
interaction objective that may be expressed through language, body behavior,
both, or deliberate stillness.

The coordinated shapes are:

```text
Canonical User Task Plan
Response Plan
Auxiliary Social Attention Plan
```

### 12.2 Explicit goals and auxiliary expression

A concrete user request such as "blink twice" or "look at me" remains an
explicit CanonicalPlan goal. It is non-droppable and cannot be replaced with a
more convenient gesture.

Autonomous interaction expression uses
`interaction_role=auxiliary_expression`. It may support acknowledgement,
listening, engagement, empathy, turn taking, deference, neutral presence, or
another model-stated purpose. It cannot satisfy, replace, authorize, or claim
completion of a user goal.

### 12.3 Model authority

Response Composer sees the immutable terminal plan, actual response stages,
turn context, target evidence, and catalog candidates tagged with the
`social_attention` behavior domain. The model owns:

- whether expression is useful;
- the social purpose;
- speech style and pacing adaptation;
- exact candidate skill IDs, arguments, timing, social function, and target;
- the choice to use body expression, language adaptation, both, or neither.

The host does not map purposes or user phrases to actions. It validates catalog
membership, schemas, target evidence, resource conflicts, confirmation and
safety policy, low-level-field exclusion, auxiliary limits, and execution
evidence.

### 12.4 Capability taxonomy is not planning

Capabilities may declare multiple behavior domains. Gaze, blink, nod, head
orientation, posture, and bow are current Social Attention candidates, but the
same underlying motion can serve perception, navigation, or another domain in a
different plan. `capabilities/behavior_domains.json` supplements provider
metadata; it does not choose behavior.

### 12.5 Target evidence and conflict policy

Target priority is:

1. live perceived user;
2. structured conversational target;
3. calibrated installation fallback;
4. no targeted behavior.

Invalid or conflicting auxiliary body behaviors are dropped. A speech-only
adaptation may remain when body behavior is rejected. Auxiliary expression never
delays the primary task.

See [Social Attention Behavior Domain](SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md).

## 13. Deterministic validation and commitment

The validator checks:

- goal and plan versions;
- plan structure;
- exact skill IDs;
- argument schemas and bounds;
- capability availability;
- provider registration and state;
- resource claims and conflicts;
- timing declarations;
- confirmation requirements;
- policy and authorization;
- stale or superseded grants;
- forbidden low-level controls;
- claim/evidence consistency.

The validator must not:

- decide whether “ice it” modifies coffee;
- infer that blinking four times is natural;
- choose which active goal “cancel that” references;
- create an alternative plan;
- write user-facing clarification language.

## 14. Execution and evidence

Execution is owned by trusted runtimes:

- Skill Runtime;
- tools and trusted services;
- memory providers;
- Soridormi for embodied planning and execution.

Execution never rewrites the user goal. Runtime observations may trigger a new
plan version, but only the cognitive layer proposes a semantic goal change.

Every committed step records:

- request and plan IDs;
- goal and plan versions;
- provider;
- start and end state;
- cancellation state;
- result evidence;
- failure reason;
- resource and safety events.

## 15. Response architecture

### 15.1 Response stages

A response plan may contain:

- immediate low-commitment acknowledgement;
- pre-action confirmation;
- progress update;
- final result;
- clarification;
- refusal or unavailable explanation.

### 15.2 Claim validation

Speech claims must be structurally tied to task and evidence state.

Examples:

- “I’m checking” may be valid before a tool result.
- “I found…” requires tool evidence.
- “I’m walking” requires committed execution state.
- “Done” requires completion evidence.

### 15.3 Natural multi-goal composition

The response composer may combine updates naturally:

> 我已经记住你只喝美式。咖啡我先看看怎么拿，天气也在查。

The individual goals remain separately tracked even when speech is consolidated.

The model-facing composer contract contains only response stages, optional
social attention, confidence, and rationale, with response coverage constrained
to the immutable plan's Goal IDs. The host owns composition identity, the
embedded canonical plan, and its fingerprint. Invalid model output may receive
one bounded repair in the same composer stage using the exact schema and
validation errors; it cannot trigger another semantic planner.

## 16. Scenario-driven development

Every meaningful behavior change follows:

```text
real interaction or explicit requirement
→ retained scenario
→ scenario fails
→ design review if needed
→ implementation
→ scenario passes
→ full regression
→ merge
```

The companion document
[Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md) defines the
required fixture structure, evidence boundaries, and review process.

## 17. Design invariants

The following are merge-blocking invariants:

1. Goal association occurs before new-goal creation.
2. A planner must preserve the complete user goal.
3. Partial coverage never becomes implicit execution.
4. Fast planning may complete or escalate; it does not partially commit.
5. Deep planning never routes semantic decomposition back to fast planning.
6. Both planner tiers output the same canonical plan contract.
7. Planners never execute or authorize side effects.
8. Validators never invent semantic meaning or user-facing answers.
9. Alternative plans that materially change the goal require confirmation.
10. Goal and plan versions remain explicit and auditable.
11. Stale confirmations and grants cannot execute.
12. Social attention is auxiliary unless explicitly requested.
13. Capability claims are grounded in current registry/provider evidence.
14. Execution claims require trusted evidence.
15. Missing information remains attached to the original goal.
16. Ambiguity is clarified naturally, without exposing internal IDs.
17. A failed optional subsystem cannot corrupt the primary task.
18. Runtime never silently fills semantic parameters through action-specific
    rules.

## 18. Prohibited anti-patterns

The following patterns violate this architecture:

- regex or phrase-table planning for normal language;
- hidden keyword-to-skill mapping;
- one new task per utterance;
- using recency alone to associate a turn with a goal;
- Router-selected first skill treated as the complete goal;
- partial action leakage from an invalid compound plan;
- Deep Planner calling Fast Planner for semantic decomposition;
- model output directly authorizing execution;
- deterministic code choosing conversational meaning;
- generic “missing parameters” responses with no structured gap;
- automatic execution of a material alternative;
- fixed gesture after every response;
- social gestures recorded as user-requested tasks;
- string concatenation presented as semantic response composition;
- speech claiming results before evidence;
- prompt branches such as “if the user says X, answer Y” used as the primary
  cognitive mechanism;
- implementation-component identity replacing Chromie’s speaking identity;
- unlimited active-goal or conversation context.

## 19. Implementation record

This constitution was implemented through staged PR1-PR8 work. The stage
descriptions below are an implementation record, not a statement that the
maintained runtime still runs those components as independent report-only
observers. Each stage began with retained scenarios and did not claim
later-stage behavior.

### PR1 — Goal contracts and continuity projection

Deliver:

- shared `SemanticGoal`, `GoalSet`, `GoalRelationship`, and version contracts;
- bounded active-goal projection;
- compatibility mapping from current semantic-task contracts;
- replay-safe operation IDs;
- no runtime behavior change by default.

Exit criteria:

- contract tests;
- active-goal projection tests;
- compatibility fixtures;
- documentation and dependency-light suite pass.

### PR2 — Goal association and segmentation

Deliver:

- model endpoint that associates a turn with existing goals;
- independent new-goal segmentation;
- natural ambiguity clarification proposal;
- report-only comparison against current routing/task proposals.

Exit criteria:

- coffee modification scenario;
- “cancel that” ambiguity scenario;
- multi-goal memory/coffee/weather scenario;
- no phrase/recency decision rules.

### PR3 — Canonical plan and Fast Planner

Deliver:

- shared canonical-plan schema;
- fast coverage decision: complete, partial, uncertain;
- direct simple chat and common-skill planning;
- partial coverage always escalates;
- common catalog remains an accelerator, not a boundary.

Exit criteria:

- simple blink direct plan;
- simple chat response;
- walk-and-blink cannot narrow to walking;
- identical validator path for fast plans.

### PR4 — Deep Planner and bounded replan

Deliver:

- full-registry deep planning;
- exact, safe-adjustment, alternative, clarification, unavailable, refused;
- structured validator rejection feedback;
- bounded same-tier replan;
- explicit no-return-to-fast invariant.

Exit criteria:

- conditional and composed plans;
- resource conflict alternative;
- replan-budget exhaustion behavior;
- no planner recursion.

### PR5 — Parameter resolution and goal satisfaction

Deliver:

- consequence-aware parameter-source decisions;
- structured information gaps;
- goal satisfaction/coverage report;
- natural specific clarification;
- resume original goal after a later answer.

Exit criteria:

- low-consequence blink default scenario;
- material movement-duration clarification scenario;
- observation-derived parameter scenario;
- no internal schema wording reaches users.

### PR6 — Response and social interaction plans

Deliver:

- multi-goal response composition;
- validated response commitments;
- independent social attention plan;
- target-evidence and resource-conflict validation;
- latency-bounded optional behavior.

Exit criteria:

- attention and no-attention scenarios;
- live-target override scenario;
- long task acknowledgement without false completion;
- social behavior excluded from user tasks.

### PR7 — Runtime migration and retained evidence

Implementation status: the unified runtime, lane-gated rollout, rollback,
operational evidence recorder, classified acceptance tooling, and cognitive
text-to-MuJoCo entry point are implemented and automatically verified. Retained
live-text and MuJoCo target evidence remain open and must be collected on the
intended deployment.

Deliver:

- staged `off`, `report_only`, and `apply` rollout;
- lane-gated application with compatibility and fail-closed fallback policy;
- migration from task continuity to atomic Goal continuity application;
- trusted host validation and one bounded same-tier Deep revision;
- complete dependency-light cognitive runtime scenarios;
- operational evidence classification and rollback;
- live-text and MuJoCo evidence collection entry points.

Exit criteria:

- all dependency-light tests pass;
- cognitive scenario library passes;
- apply records are written only after trusted preparation and atomic Goal
  state application;
- retained live-text and simulator evidence are reviewed before target behavior
  is claimed;
- no release claim exceeds collected evidence.

Operational details are maintained in
[Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md).

### PR8 — Single semantic authority and model-facing contract hardening

Implementation status: the unified runtime is authoritative for configured
lanes, exact Router actions are adapter-only, and the legacy CapabilityAgent
planner is emergency-only behind matching per-turn authority. Goal Association
uses the exact model-facing schema while the host constructs canonical
persistence objects.

Exit criteria:

- authoritative turns do not fall through to a second semantic planner;
- emergency fallback requires both service gates and a non-empty matching-turn
  claim;
- model-facing Goal Association values are schema constrained and receive at
  most one bounded contract repair;
- contract exhaustion fails closed;
- automated authority and schema-boundary checks pass;
- retained live-text and MuJoCo evidence is reviewed before target behavior is
  claimed.

## 20. Migration strategy

Routes, route items, semantic tasks, and task proposal ledgers remain bounded
compatibility surfaces around the maintained Goal-driven Runtime.

Migration rules:

- do not delete current safety or evidence boundaries;
- introduce goal contracts alongside existing task contracts;
- use `report_only` only for explicit observation or rollout diagnosis, not as
  the maintained authority mode;
- compare goal coverage and committed skills before widening an apply lane;
- widen `apply` only per lane and reviewed scenario class;
- preserve rollback switches;
- remove compatibility semantics only after retained evidence.

## 21. Observability

The cognitive pipeline should record, without exposing private model reasoning:

- goal-association result and confidence;
- candidate goal IDs considered;
- goal segmentation count;
- fast coverage result;
- escalation reason;
- planner tier and duration;
- capability candidates supplied;
- canonical plan version;
- information gaps and resolution sources;
- validation rejection codes;
- confirmation binding;
- committed steps;
- execution evidence;
- response claims;
- optional attention status.

Logs should show decisions and contracts, not hidden chain-of-thought.

## 22. Non-goals

This RFC does not claim:

- general autonomous operation;
- unrestricted self-modifying prompts or policy;
- unbounded long-term memory;
- production physical-robot readiness;
- human-level perception;
- automatic approval of learned behavior;
- removal of deterministic safety controls;
- that every user turn requires deep planning;
- that a numerical satisfaction score alone can authorize execution.

## 23. Review checklist

Every cognition-related pull request should answer:

1. What user goal or relationship is preserved?
2. Does the change associate before creating new goals?
3. Can a compound goal be narrowed or partially executed?
4. Which planner tier owns the semantic decision?
5. Does the Deep Planner ever call the Fast Planner?
6. Is the output a canonical plan?
7. What does deterministic validation enforce?
8. Are alternatives and confirmations version-bound?
9. Are claims grounded in evidence?
10. Is social behavior separated from user-task semantics?
11. Which retained scenario failed before the change?
12. What evidence supports the resulting claim?

## 24. Definition of architectural success

Chromie satisfies this architecture when:

- users can continue, modify, correct, or cancel goals naturally across turns;
- one turn can create multiple independent goals without losing continuity;
- simple goals remain fast;
- complex goals escalate without semantic loss;
- both planner tiers produce the same validated plan format;
- no partial or unconfirmed degraded plan executes;
- parameter questions are specific and context-preserving;
- social behavior feels attentive but remains optional and grounded;
- speech, execution, and evidence remain consistent;
- every material behavior is protected by retained scenarios.
