# Goal-Driven Cognitive Architecture

Status: Proposed architecture constitution
Scope: Chromie cognition, planning, interaction, validation, and execution
Implementation state: Design only; this document does not claim runtime support

## 1. Purpose

Chromie is evolving from a skill-routed interaction system into a goal-driven
cognitive runtime. This document defines the architectural principles and
contracts that future Router, Agent, memory, planning, social interaction, and
execution work must follow.

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

Partial satisfaction is not authorization to execute a degraded plan.

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
step is committed.

An invalid second step must not leak a valid first step into execution.

## 12. Social interaction layer

### 12.1 Three coordinated plans

A turn may produce:

```text
Speech Plan
Social Attention Plan
User Task Plan
```

They share turn context but have separate semantics and commitment rules.

### 12.2 Attention is an objective

The social planner decides whether and how to express attention. Blinking is one
possible behavior, not a mandatory response rule.

Possible outcomes include:

- look toward the active user;
- maintain relaxed gaze;
- blink naturally;
- nod subtly;
- shift head orientation;
- remain still;
- suppress gestures due to task conflict.

### 12.3 Target evidence

Target priority:

1. live perceived user;
2. structured conversational target;
3. calibrated installation fallback;
4. no targeted behavior.

A calibrated right-side position is a prior, not a permanent truth.

### 12.4 Auxiliary status

Social attention skills are marked auxiliary and excluded from user-goal
creation, task-continuity proposals, and primary task completion claims.

### 12.5 Failure isolation

Optional social behavior may be dropped for latency, target uncertainty,
resource conflicts, safety, invalid schema, or provider unavailability without
changing the user’s main task.

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

## 19. Implementation roadmap

This RFC is implemented through staged pull requests. Each stage begins with
retained scenarios and does not claim later-stage behavior.

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

Deliver:

- staged `off`, `report_only`, and `apply` rollout;
- migration from task continuity to goal continuity;
- complete scenario library from retained live failures;
- live text evidence;
- MuJoCo evidence;
- operational metrics and rollback.

Exit criteria:

- all dependency-light tests pass;
- scenario library passes;
- retained text and simulator evidence;
- no release claim beyond collected evidence.

## 20. Migration strategy

Current routes, route items, semantic tasks, and task proposal ledgers remain
compatibility surfaces during migration.

Migration rules:

- do not delete current safety or evidence boundaries;
- introduce goal contracts alongside existing task contracts;
- run new association and planning in report-only mode first;
- compare goal coverage and committed skills against current behavior;
- enable apply mode per lane and scenario class;
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
