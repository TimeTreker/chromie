# Social Attention Behavior Domain

## Authority and purpose

The owner-approved Social Cognition amendment transfers optional communication
expression to Social Cognition's primary decision. It may use exact eligible
social-domain Capability proposals with its immutable communicative anchor;
Runtime/Soridormi retain validation and safe realization. This includes trusted
Situation-driven initiative without UMI. No additional decoration model is added.
The representation below belongs to SC; Planner is not an expression author. Explicitly requested gestures remain
Goal-owned Planner Work. Source and evidence progress are tracked in
[Status](STATUS.md#social-cognition-migration).

The [Project Charter](PROJECT_CHARTER.md), especially Principles 29, 35, and 37,
is authoritative. This document defines the maintained optional social-decoration
contract; it does not introduce another cognitive stage.

Social Attention is a **behavior domain** for small, optional embodied expression
that accompanies a concrete human-observable Main Activity. It is not a separate
agent, Planner, Goal, execution lane, or post-response model call.

```text
UMI / committed Work / trusted Situation / Evidence
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

## Long-running social skill

Owner decisions 2026-10-25 and 2026-10-28: Social Cognition orchestrates skills, never
motions. Continuous, closed-loop or timing-sensitive body behaviour toward a person is a
Soridormi skill; Social Cognition chooses only the skill, its target, and when it starts
and stops. If Soridormi lacks the skill, Social Cognition does not emit finer motion.

A **long-running social skill** is one Social-Cognition-chosen invocation of such a skill
(first: `soridormi.attend_to_person`) with a person target, a closed set of non-semantic
behaviours and a lifetime. Soridormi closes the perception loop every frame: gaze follow,
natural blinking and glancing away, a listening or thinking posture.

| | Auxiliary activity | Long-running social skill |
| --- | --- | --- |
| Anchor | one communicative act | the conversation |
| Duration | one bounded motion | until it ends (below) |
| Meaning | may carry meaning (a nod to one sentence) | none; it never nods or shakes the head |
| Loop | open loop | Soridormi follows the person every frame |

- Start and switch: only Social Cognition, in its existing primary decision (one optional
  field naming the target, behaviours and lifetime, or a stop), when a fresh addressed turn
  or a trusted Situation change wakes it. No new model call; the Planner is unchanged; no
  joint, angle or trajectory reaches a model contract.
- Target: a person the current Situation reports, by default the current speaker
  (`requester`). Runtime and Soridormi never retarget; another person needs a new Social
  Cognition decision.
- End: Social Cognition's stop; deterministic stop, cancel, emergency or silence (Host);
  5 s after the target is lost; conversation idle (the conversation-state idle limit,
  180 s); 10 minutes at most.
- Resources: Goal Work that claims the head suspends it, and Soridormi resumes it after
  release. A requested "look at me" stays Planner Work (`look_at_person`).
- Its start, suspension, resumption and end are interaction-ledger records, never Evidence
  that Chromie understood or that a Goal progressed.
- Social Cognition sees the option only when the live Soridormi catalog declares the skill;
  there is no environment switch.

Implementation (2026-10-28):

- Soridormi lists the skill in `soridormi.skill.list` with `lifecycle: long_running`, runs it
  through `soridormi.attention.start|status|stop`, and rejects it on the plan and activity
  paths. The Agent catalog and the Host named-capability import skip such entries, and the
  Planner never sees the lifecycle tools, so it is never a Planner step or an auxiliary
  activity.
- The Host owner is `LongRunningSocialSkill` (`orchestrator/runtime/long_running_social_skill.py`),
  held by the interaction runtime coordinator. It adds `long_running_social_skill`
  (`available`, `active`, target, posture, status, the last end) to every Social Cognition
  request context, and Social Cognition sees it under `social_expression`.
- `SocialCognitionOutput.social_skill` is `null`, `attend` (`soridormi.attend_to_person`, the
  `target_ref` trusted live perception shows, posture `listening` or `thinking`), `keep` or
  `stop`. The decoder offers only the branches `social_skill_options` allows. While the skill
  runs a communicating or silent decision offers `keep` (leave it as it is), another posture or
  person, and `stop`, never `null` or the run as it already is (live 2026-10-29: restating the run
  cost about 23 generated tokens per call, and without a short steady choice the model alternated
  postures). With nothing to decide, the field is absent, and `deliberate` forces `null` in every
  state (the running state had offered no `null` at the top level, and a deliberation failed the
  raw Schema, 422). The Agent validator and the Host
  provenance check apply the same rule; `keep`, and an unchanged attend from another provider,
  record nothing.
- The Host carries out a decision after the response that holds it, without delaying it. The
  decision applies to ingress, post-plan and Situation-triggered Social Cognition alike. An
  attend for the person already attended to changes only the posture; another person ends the
  run first.
- Ends: Social Cognition's stop; every reflex cancellation scope (stop, cancel, emergency,
  silence); a new conversation; `ORCH_CONVERSATION_IDLE_TIMEOUT_SEC` (180 s) without conversation
  activity or body work; Soridormi's own ends (the person unseen 5 s, 600 s, motion or
  emergency stop, simulator reset). A Host starting up stops a run no Host owns.
- Ledger records (`trusted_capability_runtime`, domain `social_attention`, no Goal IDs):
  `social_skill_started`, `_changed`, `_suspended`, `_resumed`, `_ended` (with the reason) and
  `_not_run`. Upkeep (the catalog offer every 30 s, the status every second, idle) runs in the
  ambient perception loop, never waits behind a decision being carried out, and never invokes
  cognition. Idle counts from the latest of the last conversation activity, the last body work
  and the run's start. A start that timed out is adopted when Soridormi reports it running; a
  stop that failed keeps the run and is retried; a run the Host does not track is stopped.

### Trusted current speaker

Which perceived person is speaking is a perception fact. Soridormi's scene observation
marks the current speaker (in simulation the scenario declares it; a speaker-localization
provider replaces that mock later). The Host copies only that mark into trusted target
evidence (`target_ref: "requester"`, `source: live_perception`) for Social Cognition and
the Runtime target check below; with no marked speaker the target is unavailable. The Host
never treats a perceived person as the speaker on its own. Auxiliary expression and the
long-running social skill use the same evidence.

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
Gestures are part of SC's communication: a nod, a look or a bow is an eligible
motion expression when Soridormi declares it a low-risk expressive skill
(`safety_class=low_risk_action` without a physical-motion effect, or a
`subtle_expression` ability). Locomotion, whole-body control, manipulation and
delivery are never decoration.
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

Accepted requests use `source=social_cognition_auxiliary_activity`,
`semantic_owner=social_cognition`, `auxiliary_plan_activity=true`,
`execution_role=social_decoration`, and an empty `source_goal_ids`. They execute through the existing trusted Activity runtime. The
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
Chromie describes the target in the agreed
[body target format](EXECUTION_LANES_AND_COORDINATION.md#body-target-descriptions)
(the current speaker is `"requester"`) and never sends body-frame yaw/pitch;
Soridormi resolves the person from its perception for the active embodiment. A
target it cannot find is a typed non-completion, never a straight-ahead look.

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
