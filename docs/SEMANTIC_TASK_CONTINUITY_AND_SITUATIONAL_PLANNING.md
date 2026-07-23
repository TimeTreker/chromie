# Semantic Task Continuity and Situational Planning

## Status

**Design status:** historical staged design whose core continuity and
multi-goal response contracts are now integrated in the unified Goal-driven
Runtime; generalized observation and richer situational planning remain open.

**Design refresh date:** 2026-07-12.

The PR1-PR5 slices recorded below added shared semantic-task contracts, bounded
active-task snapshots, Router-proposed advisory operations, a dedicated Task
Continuity model endpoint, deterministic versioned goal updates, replay
protection, structured capability-planning information gaps, staged
report/apply rollout, and structured ResponsePlan claim validation. The later
Goal-driven Runtime now owns continuity-before-creation, atomic Goal-state
application, Fast/Deep multi-goal planning, and response composition. This
document remains the design history for the broader situational-planning target;
current implementation and evidence claims belong in `STATUS.md`.

Related documents:

- [Project Charter](PROJECT_CHARTER.md)
- [Chromie Mind, Principles, and Experience](chromie_mind.md)
- [Orchestrator Task Proposal Merge](ORCHESTRATOR_TASK_PROPOSAL_MERGE.md)
- [Memory Extraction](MEMORY_EXTRACTION.md)
- [General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md)
- [Current Implementation Status](STATUS.md)

## Problem

Chromie can already split one utterance into separately governed route lanes,
propose tasks, delegate complex work to deeper reasoning, validate skills, and
retain proposal and execution evidence. The next architectural problem is not
another fixed intent taxonomy. It is preserving the user's semantic goals over
multiple turns while selecting executable methods only after the current
context, capability catalog, schemas, permissions, and provider state are
known.

For example:

```text
User: Bring me a coffee, and check the weather.
Chromie: ...
User: Make the coffee iced.
```

The second turn is normally not a new isolated task. It modifies the active
coffee goal while leaving the weather task unchanged. The system must understand
that relationship semantically, update the goal, invalidate or revise affected
planning artifacts, and tell the user what changed. It must not rely on a
phrase table, regex, entity-overlap score, or a fixed `obtain_coffee` intent.

The same architecture should generalize to:

```text
Make that one smaller.
Do not send it yet.
Give Alice's one no sugar, but mine with ice.
Actually, keep the first route and cancel the second.
Use the usual setting, but deliver it upstairs.
```

## Core Principles

1. **Goals are open semantic descriptions, not fixed action enums.**
   The system should preserve what outcome the user wants in natural,
   structured semantics. It should not require a predefined goal such as
   `user_obtain_coffee`.
2. **Skills are grounded during planning, not invented during routing.**
   A planner may select one exact catalog skill, compose several skills, acquire
   missing context, ask for clarification, or conclude that no executable path
   exists.
3. **One independent user responsibility normally becomes one RouteItem.**
   Implementation steps belong to a TaskGraph or provider task, not separate
   routes.
4. **Every turn may continue, revise, answer, confirm, cancel, or query an
   existing task.**
   Task continuity is evaluated before treating the utterance as a new task.
5. **Semantic decisions belong to models operating over bounded structured
   context.**
   Regexes, phrase tables, and lexical scores must not decide normal task
   association, goal revision, or planning.
6. **Deterministic code remains authoritative for safety and facts.**
   Emergency controls, schema validation, task lifecycle, authorization,
   confirmation validity, version checks, commit state, and execution evidence
   remain code-enforced.
7. **Update the goal before rewriting the plan.**
   “Make it iced” changes a goal constraint. A planner then decides whether the
   implementation requires a different machine program, an ice skill, an
   available finished drink, a service order, or a refusal.
8. **Clarification is a normal planning result, not task failure.**
   The original task remains active while waiting for the missing information.
9. **Immediate speech is interaction feedback, not an independent task route.**
   It may acknowledge, evaluate, clarify, or report state, but it must not claim
   unverified execution or completion.
10. **No executable path means an honest limitation.**
    The model must not substitute a similar skill or fabricate a capability.

## Conceptual Model

### Turn

One user utterance plus its bounded context and resulting semantic operations.
A turn can affect zero, one, or several persistent tasks.

### RouteItem

One independently governed user-facing responsibility, such as:

- answer a conversational question;
- update a memory preference;
- query weather;
- pursue a physical or service goal;
- cancel an existing task.

A RouteItem is not a list of implementation steps.

### Semantic Goal

A versioned description of the outcome the user wants. The minimum contract is
an open semantic description plus the source utterance. Optional structure
supports later revision and planning.

```json
{
  "goal_id": "goal-001",
  "version": 1,
  "description": "Prepare or obtain a coffee and deliver it to the current user.",
  "source_text": "Bring me a coffee.",
  "beneficiary": "current_user",
  "object": {
    "description": "a coffee"
  },
  "constraints": {},
  "success_criteria": [
    "The current user receives a drink that satisfies the confirmed constraints."
  ]
}
```

`description`, `source_text`, and nested semantic values are not required to
come from a global ontology. Specific skill schemas may normalize them only
when a concrete capability is selected.

### Task

A persistent runtime record that owns a semantic goal, lifecycle, planning
state, information gaps, confirmations, commitments, and evidence.

### Task Operation

The semantic relationship between the current turn and task state.

Recommended operations:

```text
create
modify
clarification_answer
confirm
reject
cancel
pause
resume
query_status
correct
replace
```

`task_operation` is orthogonal to `route`. For example, a turn can be
`route=deep_thought` and `task_operation=modify`, or `route=tool` and
`task_operation=create`.

### Information Gap

A structured fact required before planning or execution can proceed.

```json
{
  "gap_id": "gap-temperature",
  "description": "The user's preferred coffee temperature.",
  "blocking": true,
  "required_for": ["select preparation method"],
  "preferred_resolution": "ask_user",
  "candidate_values": ["hot", "iced"]
}
```

### Plan

A versioned method proposed to satisfy one semantic goal. It may contain direct
skills, TaskGraph nodes, observations, tools, provider tasks, clarification
waits, or a structured unavailable result.

### ResponsePlan

The interaction feedback plan for a turn or task. It is separate from task
routing and execution planning.

```text
immediate -> pre_action -> progress -> final
```

## Current Architecture Baseline

This proposal builds on current implemented foundations:

- deterministic stop, cancel, emergency, silence, and unusable-audio handling,
  with semantic ambient addressedness isolated from task planning;
- quick LLM routing with multi-route output;
- `RouteDecision.routes[]`, task proposals, desired abilities, and route-stage
  metadata;
- bounded conversation and pending-task context;
- owner-approved mind and policy context groups;
- Agent capability planning and deepthinking paths;
- shared task-proposal ledger states including advisory, committed,
  not-committed, rejected, missing ability, and superseded;
- native structured interaction and trusted Skill Runtime;
- TaskGraph planning and guarded execution contracts;
- Soridormi capability, preview, submit, event, cancellation, refusal, and
  safe-idle boundaries.

The design must preserve the current rule that model output is advisory until
validated and committed by trusted runtime code.

The current reliability slice also makes `report_only` asynchronous, returns an
empty diagnostic result when its model is unavailable, and removes normal-language
forward-motion/compound phrase recovery from deterministic Router validation.
Generic chat outputs can be rechecked by a second bounded semantic call when the
ability catalog exposes executable embodied affordances; that call remains a
proposal source, not execution authority.

## Current Implementation Slice

The first dependency-light slice is implemented in the current repository:

- `shared/chromie_contracts/semantic_task.py` defines versioned contracts for
  open semantic goals, task operations, active-task snapshots, information
  gaps, planning results, and response plans;
- `ConversationStateManager` exposes bounded active-task snapshots and
  deterministically validates and applies model-proposed create, modify,
  clarification-answer, confirm, reject, cancel, pause, resume, query, correct,
  and replace operations;
- semantic goal changes increment `goal_version`, supersede affected plan
  versions, invalidate stale confirmations, and retain operation history;
- operation IDs are replay-safe so retries do not duplicate task creation or
  apply one semantic update twice;
- the quick Router prompt receives the bounded active-task snapshot and may emit
  advisory `metadata.semantic_task_operations`; normal association is explicitly
  meaning-based and may not be decided by regexes, phrase tables, lexical
  overlap, or recency alone;
- the Orchestrator applies accepted semantic operations before downstream Agent
  planning and rebuilds the same-turn context;
- Capability Agent planning reports `direct_skill`, `composed_plan`,
  `safe_adjustment`, `alternative_plan`, `needs_clarification`, or `unavailable`
  metadata and converts missing required schema fields into structured
  information gaps;
- compound embodied requests are reconstructed by the model as complete outcomes
  with explicit parallel/sequential relations. Provider resource and concurrency
  metadata are evidence, while missing provider metadata remains unknown rather
  than being converted into a hardcoded compatibility rule;
- all model-proposed skill steps are schema-validated before any step is committed.
  A malformed or unavailable sub-step rejects the entire effectful plan, so a
  clarification response cannot coexist with a leaked partial execution;
- a material alternative plan is retained as a complete pending proposal with
  the model-authored explanation and is never simulator-auto-confirmed. The host
  waits for user confirmation tied to that plan version before execution;
- legacy normal-language capability parsers for action names, counts, speeds, and
  durations are removed from the Capability Agent. Deterministic code remains
  responsible only for contract validation, resource arbitration, confirmation,
  authorization, and evidence;
- planning results are bound to a task and goal version; stale results are
  retained as rejected metadata rather than changing the newer task;
- ordinary chat no longer opens or rebinds a task merely because a phrase looks
  referential;
- `agent/app/task_continuity.py` provides a dedicated semantic Task Continuity
  model endpoint that receives bounded active-task snapshots, treats Router
  output as advisory, emits deterministic replay-safe operation IDs, and rejects
  unknown-task or below-threshold operations;
- the Orchestrator supports `off`, `report_only`, and `apply` rollout modes. In
  apply mode, the dedicated continuity result becomes authoritative for semantic
  task operations while deterministic lifecycle validation remains in the host;
- an authoritative empty continuity result prevents the legacy route fallback
  from inventing a new task merely because the route is `deep_thought`;
- structured immediate `ResponsePlan` stages are checked against current task
  status and trusted evidence before fast-first playback. Unscoped or
  unsupported accepted/executing/completed/failed/cancelled claims are rejected;
- validated ResponsePlan speech uses structural claims instead of the legacy
  phrase blacklist as its primary truthfulness boundary. Legacy fast-speech
  fields retain the conservative fallback filter.

At the completion of these historical PR1-PR5 slices, automated verification
did not yet provide full multi-goal response composition, bounded model repair,
generalized observation planning, affordance-rich capability contracts,
live-text evidence, simulator evidence, or any widened physical execution
claim. The dedicated continuity path was therefore default-off. The later
unified Goal-driven Runtime supplied multi-goal composition and bounded
same-stage repair; generalized observation planning and current target evidence
remain open.

## Target Runtime Flow

```text
User turn
  -> deterministic emergency/reflex filter
  -> quick semantic route and independent-goal split
  -> semantic task continuity resolution
  -> goal create/update proposal
  -> deterministic task/lifecycle validation
  -> situational capability planning
       -> direct skill
       -> composed plan
       -> acquire context
       -> ask clarification
       -> unavailable/refused
  -> semantic interaction composition
  -> deterministic speech-claim validation
  -> Orchestrator commit and scheduling
  -> Skill Runtime / tools / memory / Soridormi
  -> execution evidence and task-state update
  -> progress/final response from trusted state
```

The stages may be combined in one model call for simple cases, but their
contracts and authority must remain distinct.

## Routing Model

### Fast paths

Simple turns should remain simple.

#### Casual conversation

```json
{
  "route": "chat",
  "intent": "casual conversation",
  "confidence": 0.98
}
```

No full capability catalog, environment planning, or TaskGraph is required.
The conversational response may be the final response.

#### Explicit direct skill

A Router may propose an exact skill only when the user explicitly specifies the
method and one catalog capability clearly matches with sufficient parameters.

```text
User: Nod twice.
```

```json
{
  "route": "robot_action",
  "intent": "capability:soridormi.nod_yes",
  "confidence": 0.97,
  "actions": [
    {
      "capability_id": "soridormi.nod_yes",
      "args": {"count": 2},
      "confidence": 0.97
    }
  ]
}
```

The proposal still requires normal schema, policy, confirmation, availability,
and provider validation.

### Situational goals

When the user requests an outcome rather than an explicit method, or method
selection depends on role, environment, permission, resources, or multiple
possible implementations, the Router should preserve an open goal and delegate
planning.

```json
{
  "route": "deep_thought",
  "intent": "user requests a coffee to be prepared or obtained",
  "confidence": 0.95,
  "metadata": {
    "task_operation": "create",
    "goal": {
      "description": "Prepare or obtain a coffee and deliver it to the current user.",
      "source_text": "Bring me a coffee.",
      "constraints": {}
    },
    "requires_capability_planning": true
  }
}
```

The Router must not invent a hidden fixed action ID for this goal.

## Independent Goals Versus Plan Steps

The split rule is:

> Router splits the responsibilities the user gives Chromie. Planner splits how
> each responsibility can be fulfilled.

Example:

```text
Remember that I drink Americano, then bring me a coffee.
```

This contains two independently governed responsibilities:

1. update a preference;
2. pursue the coffee goal.

It may produce two RouteItems because they have separate authorization,
lifecycle, and failure semantics.

By contrast:

```text
Check whether there is coffee; if not, make some.
```

This is normally one goal with a conditional plan, not two independent routes.

```text
Goal: provide coffee to the user
Plan:
  observe available coffee
  if available -> retrieve and deliver
  else -> select a supported preparation path
```

## Semantic Task Continuity

Every non-reflex turn should be evaluated against a bounded snapshot of active
and recently relevant tasks before a new task is created.

### Input snapshot

```json
{
  "current_utterance": "Make the coffee iced.",
  "recent_turn_summary": "The user requested coffee and a weather lookup.",
  "active_tasks": [
    {
      "task_id": "task-coffee-001",
      "goal_summary": "Prepare or obtain coffee for the current user.",
      "goal_version": 1,
      "status": "planning",
      "known_constraints": {},
      "open_information_gaps": [],
      "committed_actions": []
    },
    {
      "task_id": "task-weather-002",
      "goal_summary": "Check the requested weather.",
      "goal_version": 1,
      "status": "running",
      "known_constraints": {}
    }
  ],
  "last_system_question": null
}
```

### Proposed semantic result

```json
{
  "operation": "modify",
  "target_task_ids": ["task-coffee-001"],
  "confidence": 0.98,
  "relationship": "constraint refinement",
  "goal_update": {
    "description": "Prepare or obtain an iced coffee and deliver it to the current user.",
    "constraint_updates": {
      "temperature": "iced"
    }
  },
  "requires_replan": true
}
```

This judgment belongs to a semantic model. The model should reason from the
utterance meaning, task goals, open questions, conversation state, and task
lifecycle. It must not decide using keyword rules, phrase lists, regexes,
entity overlap, or recency alone.

Candidate retrieval may reduce the active-task set presented to the model, but
retrieval is advisory. It may not choose the target task.

### Ambiguity

If the user previously requested coffee for two people and then says only:

```text
Make it iced.
```

and the context does not establish which drink is intended, the model should
return clarification instead of guessing.

## Goal and Plan Versioning

Goal updates and plan updates must be retained as versions, not destructive
rewrites.

```text
task-coffee-001
  goal v1: coffee, temperature unspecified
  plan v1: selected initial preparation path
  user delta: temperature=iced
  goal v2: iced coffee
  plan v1: superseded
  plan v2: selected iced-coffee path or unavailable result
```

A goal change may invalidate:

- a pending clarification;
- a plan;
- a request-bound confirmation;
- queued but uncommitted actions;
- an execution grant tied to an older fingerprint.

The Orchestrator must enforce version and fingerprint validity. A semantic model
may propose which artifacts are affected, but it cannot declare the update
committed.

## Situational Capability Planning

The planner receives:

- the current semantic goal version;
- role and relationship context when relevant;
- bounded world and runtime facts with source and freshness;
- available capabilities and schemas;
- current provider mode and availability;
- permissions, confirmation, cost, privacy, and safety policy;
- prior plan and execution evidence when revising.

The planner returns one of these result classes:

```text
direct_skill
composed_plan
safe_adjustment
alternative_plan
needs_context
needs_clarification
needs_confirmation
unavailable
refused
```

### Direct skill

Use one exact skill when it clearly satisfies the goal and all required inputs
are grounded.

### Composed plan

Combine exact registered capabilities when their declared semantics and schemas
provide a credible path to the requested outcome.

The planner must not infer that similarly named skills compose safely unless the
capability contracts support that composition.

### Safe adjustment

Use a bounded adjustment only when the planner concludes from supplied policy,
provider, and runtime evidence that the change preserves the material user goal.
The model must explain the adjustment naturally. A material goal change must be
represented as an alternative plan instead of silently executed.

### Alternative plan

When the exact timing, composition, or method cannot be supported but a credible
alternative exists, the model returns the full alternative—not a partially
executable remainder—and asks for confirmation in natural language. No effectful
step is committed until the confirmed plan version matches the proposal.

Deterministic code does not decide that a particular pair of actions should be
sequential or parallel from their names. It validates model-authored timing
against explicit provider/resource evidence and safely treats absent evidence as
unknown.

### Needs context

When the missing fact is an environment or runtime fact, plan an observation or
trusted query rather than asking the user to guess.

Examples:

- whether ice is available;
- whether a machine is online;
- whether a cup is reachable;
- whether a provider is in simulator or hardware mode.

### Needs clarification

When the missing information is user intent, preference, target, permission, or
another fact only the user can authoritatively provide, retain the original task
and ask a concise question.

### Unavailable

If no direct skill, valid composition, trusted delegation, or context-acquisition
path can satisfy the goal, report the limitation honestly. Do not create a
fictional skill or substitute an unrelated capability.

## Missing Parameters and Clarification

Schema validation may deterministically identify missing required fields. A
model should then determine whether the value is already implied by semantic
context and, if not, how it should be resolved.

Resolution classes:

```text
ask_user
observe_environment
query_trusted_service
use_owner_approved_preference
use_safe_default
unresolvable
```

The semantic planner, not a phrase rule, chooses among these classes from the
complete utterance, the field schema, explicit schema defaults, field bounds,
capability safety class, effects, provider constraints, and the consequence of
being wrong. A low-consequence and easily reversible field may be filled with an
explicit schema default or a conservative bounded value. For example, when a
blink capability requires a count but the user simply asks Chromie to blink,
the model may choose an ordinary small count and record that decision as
`use_safe_default`.

A parameter that materially changes duration, direction, target, authorization,
cost, irreversible effects, or physical risk remains an information gap. The
planner must ask for the specific missing fact rather than saying only that the
action cannot be performed. The clarification should name the field in natural
language and may offer valid candidate values when the schema supplies them.

Deterministic code does not classify the semantic importance of a parameter. It
validates the model-proposed value against the schema and provider state, or
validates the structured information gap when the model decides to ask. If the
parameter-resolution model is unavailable, the fail-closed fallback may list
the exact schema-derived gaps, but it must not invent a semantic default.

Example planning result:

```json
{
  "planning_result": "needs_clarification",
  "task_id": "task-coffee-001",
  "goal_version": 1,
  "information_gaps": [
    {
      "gap_id": "gap-temperature",
      "description": "The user's preferred coffee temperature.",
      "blocking": true,
      "required_for": ["select preparation capability"],
      "preferred_resolution": "ask_user",
      "candidate_values": ["hot", "iced"]
    }
  ],
  "response_proposal": {
    "speech_act": "clarify",
    "text": "Would you like it hot or iced?"
  }
}
```

The task transitions to `waiting_for_user`. A later answer such as “Iced, no
sugar, and make it large” may resolve both asked and additional semantically
relevant constraints in the same task.

After the answer:

```text
waiting_for_user
  -> semantic task association
  -> goal update
  -> planning
  -> validation
  -> confirmation if required
  -> commitment and execution
```

Information completion never bypasses replanning and validation.

## Response Architecture

### Immediate response is not a RouteItem

An immediate response belongs to the interaction plan for the current turn or
task. It should communicate what Chromie has heard or is doing without creating
an extra user responsibility.

Recommended stages:

```text
immediate
pre_action
progress
final
```

Example:

```json
{
  "response_plan": {
    "immediate": {
      "text": "Okay, I will check how I can get that for you.",
      "speech_act": "acknowledge",
      "commitment_state": "evaluating",
      "must_not_claim_completion": true
    }
  }
}
```

For ordinary conversation, `immediate` may also be the final response. For tool,
planning, or embodied work, it is normally only a low-commitment prelude.

### Semantic composition versus deterministic arbitration

Semantic combination of multiple goals and natural speech belongs to a model,
for example an Interaction Planner or Response Composer.

The Orchestrator must not pretend that string templates or rule concatenation
are semantic reasoning. Its responsibilities are deterministic:

- validate task and goal IDs;
- validate lifecycle transitions and versions;
- enforce cancellation and interrupt priority;
- check schema, policy, provider, and confirmation requirements;
- commit or reject proposals;
- schedule speech without overlap;
- suppress stale progress and completion messages;
- attach execution evidence;
- prevent older plans from executing after supersession.

A model may propose one natural response covering several RouteItems. The
Orchestrator validates that its commitments are allowed by current task state.

### Speech claims

Model-generated speech should optionally declare structured claims, such as:

```text
heard
evaluating
accepted
waiting_for_user
executing
completed
failed
cancelled
memory_committed
tool_result_available
```

A deterministic claim validator checks those claims against trusted state.
Invalid speech is repaired by the model with structured error feedback or
replaced by a safe fallback.

## Responsibility Boundaries

### Quick Router model

- identify independent semantic responsibilities;
- choose a lightweight context profile;
- produce simple direct routes when appropriate;
- preserve open semantic goals for situational work;
- propose exact skills only for clear direct-action requests;
- never authorize, execute, or claim completion.

### Task Continuity / Interaction Planner model

- determine how the current utterance relates to active tasks;
- propose create, modify, clarification, correction, confirmation, cancellation,
  or status operations;
- preserve goal continuity across paraphrases and indirect references;
- propose goal relationships and a natural immediate ResponsePlan;
- return clarification when task association remains ambiguous;
- never commit a task update or side effect.

### Capability Planner model

- ground a semantic goal against current capability descriptions and schemas;
- produce a direct skill, composed plan, context request, clarification request,
  or unavailable result;
- preserve the user's requested outcome while changing implementation methods;
- never invent capabilities or low-level controls.

### Orchestrator

- own task IDs, versions, state transitions, proposal ledgers, and commitments;
- validate and apply semantic task-operation proposals;
- invalidate stale confirmations and plans;
- enforce deterministic controls and authorization;
- coordinate trusted services and retain evidence;
- never perform semantic task association through regex or phrase rules.

### Skill Runtime and Soridormi

- validate trusted execution requests;
- enforce confirmation, scheduling, timeout, cancellation, and safety policy;
- preview, execute, monitor, refuse, stop, and recover embodied work;
- remain the authority for real execution and provider evidence.

## Proposed Contracts

The following shapes are directional and should become versioned shared
contracts before runtime adoption.

### Semantic task operation

```json
{
  "schema_version": 1,
  "operation_id": "turn-42-op-1",
  "operation": "modify",
  "target_task_ids": ["task-coffee-001"],
  "confidence": 0.98,
  "relationship": "constraint refinement",
  "goal_update": {
    "description": "Prepare or obtain an iced coffee for the current user.",
    "constraint_updates": {
      "temperature": "iced"
    }
  },
  "requires_replan": true,
  "reason_summary": "The user refined the active coffee request."
}
```

`reason_summary` is an audit summary, not chain-of-thought.

### Task context snapshot

```json
{
  "schema_version": 1,
  "task_id": "task-coffee-001",
  "status": "planning",
  "goal": {},
  "goal_version": 2,
  "plan_version": 1,
  "open_information_gaps": [],
  "confirmation": null,
  "commitment_state": "evaluating",
  "last_user_update": "Make the coffee iced.",
  "evidence_summary": {}
}
```

### Planning result

```json
{
  "schema_version": 1,
  "task_id": "task-coffee-001",
  "goal_version": 2,
  "result": "composed_plan",
  "plan": {},
  "information_gaps": [],
  "unavailable_reason": null,
  "response_proposals": []
}
```

## Example: Coffee, Weather, and a Later Revision

### Turn 1

```text
Bring me a coffee and check the weather.
```

Semantic split:

```text
RouteItem A: pursue the coffee outcome
RouteItem B: query weather
```

The weather task may proceed through a tool lane. The coffee goal is retained
as an open semantic goal and sent to situational planning.

Immediate response may be semantically composed:

```text
Okay. I will check the weather and see how I can get the coffee for you.
```

This acknowledges both tasks but does not claim the coffee can already be
produced or delivered.

### Turn 2

```text
Make the coffee iced.
```

The Task Continuity model proposes a modification to the coffee task only. The
Orchestrator validates that the task is still modifiable, writes goal version 2,
marks the affected plan version superseded, and requests replanning.

The planner may discover:

- one direct iced-coffee capability;
- a valid composition involving preparation and ice;
- an existing iced drink that can be retrieved;
- a need to observe whether ice exists;
- no executable path.

Only after that result may Chromie say one of the following:

```text
I changed the coffee request to iced and am checking the available preparation path.
```

```text
I changed it to iced, but there is no available ice or iced-coffee capability. Would you like it hot instead?
```

The weather task remains unchanged.

## Prompt Requirements

Semantic task-continuity prompts should use the existing context-group order:

```text
Global Context Group
Session Context Group
Current Job
Task Context Group
Cost Function
Output Contract
```

### Current Job

```text
Determine how the latest user utterance relates to the supplied active goals
and tasks. Propose structured task operations only. Do not execute, authorize,
or claim that an update has been applied.
```

### Generalization rule

```text
Reason from meaning, conversation context, semantic goals, unresolved questions,
and task state. Do not decide task association through phrase rules, regexes,
keyword overlap, fixed intent labels, or recency alone. Retrieval signals may
select candidates for context but are not the semantic decision.
```

### Cost function

```text
Preserve task continuity before creating unnecessary new tasks.
Preserve the user's intended outcome before preserving an old plan.
Meaning and context before lexical overlap.
Observed or trusted facts before assumptions.
Clarify before attaching a modification to the wrong task.
Update goals before rewriting execution steps.
Small and reversible before broad and irreversible.
Honest unavailability before invented capability.
```

### Output contract

The output must be compact structured JSON. It may contain semantic summaries
and confidence but no chain-of-thought, hidden analysis, raw scratchpad, or
execution claims.

## Implementation Sequence

### PR0 - Contracts and fixtures — first slice implemented

- Add shared versioned contracts for `SemanticGoal`, `TaskContextSnapshot`,
  `SemanticTaskOperation`, `InformationGap`, `PlanningResult`, and
  `ResponsePlan`.
- Add contract-only examples and validation tests.
- Do not change runtime behavior.

### PR1 - Task context projection — first slice implemented

- Extend conversation/task state to expose a bounded active-task snapshot.
- Include task ID, semantic goal summary, goal version, state, open gaps,
  confirmation state, and compact evidence.
- Keep raw conversation and full execution logs out of normal prompts.

### PR2 - Advisory task-continuity model — implemented with staged rollout

- Add a dedicated semantic Task Continuity model endpoint.
- Support host `off`, `report_only`, and `apply` modes; repository default remains
  `off` while report-only evidence is collected.
- Retain the model result, accepted/rejected operation diagnostics, and stable
  operation IDs.
- In apply mode, let only the deterministic host apply validated operations and
  mark the result authoritative so legacy route fallback cannot invent tasks.

### PR3 - Versioned goal updates — first slice implemented

- Let the Orchestrator validate and apply approved semantic operations.
- Add goal versions, plan versions, operation IDs, and supersession links.
- Invalidate stale confirmation fingerprints and queued uncommitted work.
- Preserve the task-proposal ledger as the audit substrate.

### PR4 - Planning information gaps — first slice implemented

- Extend the Capability Planner to return structured result classes and
  information gaps.
- Add `waiting_for_user` and context-acquisition states.
- Bind clarification answers back to the original task.

### PR5 - Semantic ResponsePlan and claim validation — first slice implemented

The runtime also implements a startup-primed cached-audio hedge for generic
low-commitment acknowledgements. This removes realtime LLM/TTS generation from
the first-audio path while preserving semantic routing and deterministic claim
validation. The cue is suppressed when final speech is ready before the hedge
threshold and cancelled if queued but not yet audible.

- At this slice, the Task Continuity endpoint could propose one immediate
  ResponsePlan across related RouteItems. Full multi-goal response composition
  was implemented later in the unified Goal-driven Runtime.
- Add structured commitment and speech claims.
- Validate immediate claims against trusted task status and evidence before
  fast-first playback.
- Reject unknown task scopes, premature accepted/executing/terminal claims, and
  unsupported evidence claims; retain safe legacy fallback speech.
- Add model repair and progress/final-stage claim validation in a later slice.

### PR6 - Affordance-rich capabilities

- Extend capability descriptions where needed with declared preconditions,
  effects, required observations, permissions, cost class, reversibility,
  compensation, and evidence requirements.
- Keep this metadata high-level and provider-neutral.
- Do not expose low-level robot controls.

### PR7 - Runtime integration and staged rollout

- Enable semantic continuity for text-only Level A tests first.
- Add live-text acceptance before simulator execution.
- Keep physical execution gates off.
- Retain exact model, prompt, capability, Chromie, and Soridormi revisions in
  evidence.

## Verification Strategy

### Generalization-oriented scenario families

Do not create one special rule for one sentence. Use semantic families with
paraphrases and context variations:

- direct task creation;
- implicit and explicit task modification;
- clarification answers;
- correction and replacement;
- cancel one task while preserving another;
- ambiguous reference requiring clarification;
- one goal with conditional plan steps;
- several independent goals in one utterance;
- no executable skill path;
- capability exists but required environment context is absent;
- update before commitment;
- update after confirmation;
- update during execution;
- update after an irreversible or completed step.

### Coffee continuity family

Representative turns should include:

```text
Bring me a coffee.
Make that one iced.
Actually, hot is fine.
Use my usual preference.
Do not add sugar.
Give Alice's one no ice, but mine iced.
The weather lookup can continue; cancel only the coffee.
```

The expected invariant is semantic continuity, not matching the word “coffee.”

### Required assertions

- no normal semantic association depends on regex or phrase tables;
- simple chat remains on the low-latency path;
- one semantic goal does not become multiple RouteItems merely because its plan
  has several steps;
- independent goals remain separately cancellable and observable;
- updates create new goal and plan versions;
- stale plans and confirmations cannot execute;
- missing user preferences create clarification gaps;
- missing world facts create observation or trusted-query requests;
- unavailable capability paths produce honest speech and no skill commitment;
- progress and completion speech match trusted runtime evidence;
- deterministic stop and cancel behavior does not regress.

## Focused Verification

```bash
python -m unittest tests.test_semantic_task_continuity
python -m unittest \
  tests.test_conversation_state \
  tests.test_capability_aware_interaction \
  tests.test_router_llm_prompt \
  tests.test_task_proposals \
  tests.test_semantic_task_continuity
python scripts/check_docs.py
./scripts/run_tests.sh
```

## Non-Goals

- Do not create a fixed ontology for every possible user goal.
- Do not add regex or phrase-rule task association for normal language.
- Do not let semantic models commit their own task updates or side effects.
- Do not make the Orchestrator a natural-language reasoning engine.
- Do not treat catalog retrieval score as the routing or planning decision.
- Do not infer real-world availability from language-model common knowledge.
- Do not require full situational planning for ordinary chat or clear direct
  skills.
- Do not widen the current physical-robot support claim.

## Exit Criteria

This architecture track is complete only when:

- shared contracts represent open semantic goals, task operations, versions,
  information gaps, planning results, and response plans;
- every turn can be semantically associated with active tasks without fixed
  goal enums or phrase-rule decisions;
- task updates preserve goal continuity and supersede affected plans safely;
- missing user-provided parameters enter a waiting-for-user flow and resume the
  original task after a semantic answer;
- capability planning can select a direct skill, compose a valid plan, request
  context, ask clarification, or report no executable path;
- semantic response composition is separated from deterministic lifecycle,
  authorization, and claim validation;
- simple chat and direct-skill latency do not regress materially;
- generalization-oriented Level A scenarios pass;
- a retained live-text run demonstrates task creation, multi-goal separation,
  later goal modification, clarification, replanning, and truthful feedback;
- simulator or physical claims remain governed by their existing evidence gates;
- `python scripts/check_docs.py` and `./scripts/run_tests.sh` pass.
