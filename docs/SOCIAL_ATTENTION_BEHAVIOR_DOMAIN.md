# Social Attention Behavior Domain

## Authority and purpose

The owner-approved Social Cognition amendment transfers optional communication
expression to Social Cognition's primary decision. It may use exact eligible
social-domain Capability proposals with its immutable communicative anchor;
Runtime/Soridormi retain validation and safe realization. This includes trusted
Situation-driven initiative without GI. No additional decoration model is added.
The representation below belongs to SC; Work Planner is not an expression author. Explicitly requested gestures remain
Goal-owned Planner Work. Source and evidence progress are tracked in
[Status](STATUS.md#social-cognition-migration).

The [Project Charter](PROJECT_CHARTER.md), especially Principles 29, 35, and 37,
is authoritative. This document defines the maintained optional social-decoration
contract; it does not introduce another cognitive stage.

Social Attention is a **behavior domain** for small, optional embodied expression
that accompanies a concrete human-observable Main Activity. It is not a separate
agent, Planner, Goal, execution lane, or post-response model call.

```text
GI / committed Work / trusted Situation / Evidence
  -> SC primary interaction decision
       -> exact communicative acts (spoken or nonverbal)
       -> optional expression anchored to those acts
  -> Runtime validates exact snapshot, act, target and resource authority
       -> execute the exact proposal, or suppress optional expression
```

SC decides wording and optional expression together from the same supplied state.
No separate decoration reviewer or social-attention model reopens its decision.
Planner independently owns requested task Work.

## Primary and auxiliary work

`CanonicalPlan.steps[]` contains Goal-owned executable Work. Every executable step
belongs to at least one Goal outcome and participates in Goal completion.

`SocialCommunicativeAct.auxiliary_activities[]` contains optional decoration. The field is
separate by construction so decoration:

- carries no Goal IDs and cannot satisfy, complete, replace, or authorize a Goal;
- is bound to the exact SC request snapshot and immutable act identity;
- is limited to a bounded set of low-risk, parallel, confirmation-free candidates;
- is always subordinate to an existing Main Activity anchor; and
- may disappear without changing the correctness of the Main Activity.

The same physical Capability can occupy either role. “Blink twice” makes blinking
Goal-owned primary Work in `steps[]`. A subtle blink accompanying a greeting can be
an auxiliary activity. Runtime determines neither role from the actuator nor from a
phrase; Planner owns explicitly requested actions; SC owns optional interaction expression.
An auxiliary activity must not duplicate a Capability already used by its anchor's
primary realization.

## SC input and output

SC receives the following in its primary interaction request:

- the semantic Main Activity or Plan response that may be decorated;
- current Responsibility, Goal, Work, Evidence, and interaction context;
- owner-approved Social Interaction Style;
- bounded recent auxiliary-behavior evidence;
- current semantic target evidence; and
- exact live catalog candidates tagged with `behavior_domains=[social_attention]`.

Candidate projection is mechanical. A candidate must be available, executable,
confirmation-free, parallel-capable with declared concurrency metadata, free of
model-facing low-level motor fields, and explicitly tagged for the behavior domain.
Provider, backend, calibration, controller, joint, and actuator identity are not
shown to the model.

SC emits an empty list unless expression materially improves a particular
Main Activity. Each `AuxiliaryPlanActivity` contains:

- a stable auxiliary activity ID;
- an anchor kind and exact anchor ID;
- one exact eligible Capability ID and schema-valid arguments;
- the fixed execution role `social_decoration` and parallel timing;
- a bounded social function and optional semantic target; and
- a short reason summary.

Internal milestones such as understanding ready, Goal Association, planning,
waiting, Work start, Evidence arrival, or lane transition are never anchors. Valid
anchors are immutable SC communicative acts from the same result. Requested body
Work remains Planner-owned and does not grant SC a substitute task or anchor.

## Runtime authority

Runtime is a validator and executor, not a social reasoner. Before dispatch it may
check only mechanical facts:

- the anchor still exists in the exact Plan revision;
- the Capability is the exact proposed live-catalog member and retains the
  `social_attention` behavior-domain tag;
- arguments match the declared schema and contain no forbidden low-level fields;
- the Capability remains available, confirmation-free, interruptible where needed,
  parallel-capable, and provider-safe;
- current target evidence still supports the exact proposed semantic target;
- the auxiliary Capability does not duplicate or conflict with primary work; and
- resource, concurrency, repetition, and bounded-count constraints still hold.

Runtime may execute the exact proposal or suppress it. It may not choose a nearby
Capability, change a target, rewrite arguments, generate gesture sequences, infer a
social purpose, or attach Goal ownership. If Alice leaves, Runtime drops “nod to
Alice”; it does not retarget the nod to Bob.

Accepted requests use `source=canonical_plan_auxiliary_activity`,
`auxiliary_plan_activity=true`, `execution_role=social_decoration`, and an empty
`source_goal_ids`. They execute through the existing trusted Activity runtime. The
result is retained as auxiliary-behavior evidence, not Goal-completion evidence.

## Failure, freshness, and re-entry

Auxiliary planning and execution are fail-soft. Malformed, stale, unavailable,
unsafe, conflicting, repetitive, late, or failed decoration is suppressed without:

- delaying or failing speech or primary Work;
- recomposing a response;
- mutating the Plan, Goal, or completion assessment;
- calling another model to repair, review, or reselect; or
- producing failure speech.

`CognitiveOpportunity.goal_ids` is non-empty by schema. Therefore an event that is
only about auxiliary decoration—target drift, invalidation, failure, completion, or
new decorative possibility—must never construct a `CognitiveOpportunity`, borrow a
Goal ID, or re-enter Planner. If the same world change also materially affects real
Goal-owned Work, that independent Goal-relevant transition may create an ordinary
bounded opportunity. Planner owns any new task Plan revision. The trusted state may separately inform SC; it does not grant an automatic gesture or repeat an old one.

This boundary deliberately accepts harmless imperfection. A missed blink or stale
nod ends locally. A new SC decision requires relevant trusted interaction state; it cannot manufacture Goal work.

## Target and repetition evidence

Target priority is:

1. a currently perceived and semantically identified interaction target;
2. a structured conversational target supported by current evidence; or
3. no targeted behavior.

Installation coordinates and calibration are not semantic target evidence.
Soridormi resolves an accepted semantic target for the active embodiment.

Recent accepted and terminal auxiliary evidence may be projected into a later
SC call to support restraint and variety. It does not create a global
turn cooldown: distinct Main Activities may independently receive no decoration or
one compatible decoration. Evidence never proves that a Goal progressed.

## Related boundaries

Startup orientation has no interaction anchor and remains Host-owned baseline
liveliness, not Social Attention. Idle animation is also outside this contract.
Speech remains an SC-owned Communicative Activity. Stop, cancel, emergency,
confirmation, body planning, motion safety, calibration, and recovery retain their
existing deterministic Host/Soridormi owners.

The executable contract and regression ownership are in
`shared/chromie_contracts/social_cognition.py`, SC schema/prompt tests, Runtime adapter
tests, and repository architecture guards. Historical Social Attention qualification
artifacts are evidence only and do not restore the retired independent writer.
