# Chromie/Soridormi Proposal Boundary Plan

This decision document records the implementation plan after reviewing the
brain/body split suggestions against the current Chromie codebase. It keeps the
existing `Router -> Orchestrator -> Agent/InteractionResponse -> SkillRuntime ->
Soridormi provider` chain and strengthens it instead of replacing it with a
parallel dual-brain control loop.

## Decision

Chromie remains the semantic brain. Soridormi remains the embodied body runtime.
Chromie may propose speech, skills, and structured embodied goals, but it must
not command joints, motors, torques, controller arrays, grasp poses, or any
other low-level body control. Soridormi owns physical feasibility, realtime
safety, embodied planning, motion monitoring, execution, refusal, and recovery.

The architecture therefore stays:

```text
user input
  -> Router quick decision
  -> Orchestrator fast-first acknowledgement when useful
  -> Agent/InteractionResponse for capability, safety, and deep thinking
  -> SkillRuntime validation, confirmation, and provider dispatch
  -> Soridormi plan/monitor/execute boundary
```

The rejected alternative is always-on Route2/Route3 parallelism. Route2 should
remain fast and always available, but deeper reasoning should be conditionally
triggered when ambiguity, risk, missing capability, memory writes, side effects,
multistep planning, or live perception dependencies require it.

## Non-negotiable invariants

1. LLM confidence never authorizes physical execution.
2. Any Soridormi-bound request is a proposal-derived intent, not a command.
3. SkillRuntime and the Soridormi provider remain mandatory commit gates for
   physical skills.
4. Soridormi may refuse, reshape, stop, or recover from physical work without
   waiting for Chromie.
5. Chromie may explain Soridormi status to the user, but must not invent
   physical coordinates, poses, successful grasps, or completed movement.
6. User confirmation can update user preference; it cannot override Soridormi's
   physical safety or feasibility checks.
7. Emergency stop false-positive review may resume dialogue, but physical work
   must re-enter preflight or confirmation after a stop.

## Route2 / Route3 policy

Do not run Route3 for every turn. Use conditional deep reasoning.

Route2 may use the fast lane for:

- chat-only responses;
- TTS fillers and truthful prelude speech;
- exact, low-risk body cues such as simple nod or wave proposals, after normal
  SkillRuntime validation.

Route3 or a deeper agent path should be considered when any of these are true:

- route confidence is below the route-type threshold;
- the request is multistep or contains conditional logic;
- the request needs navigation, manipulation, live perception, external tools,
  or memory writes;
- the capability catalog match is partial, missing, or contradictory;
- the user state is ambiguous, frustrated, correcting Chromie, or expressing a
  safety/policy-sensitive preference;
- Route2 and a later semantic plan disagree on the emotional stance or task
  interpretation.

Important boundary: physical action always requires proposal and SkillRuntime
validation, but physical action does not automatically require the
`deepthinking_agent`. A simple exact-match gesture can remain a fast proposal;
a high-risk, ambiguous, multistep, or perception-dependent physical request
should use deeper reasoning.

## Implementation sequence

### Step 1 - Make proposal semantics explicit at the Soridormi boundary

Status in this patch: implemented for named-skill `create_plan` calls.

Add a `chromie_intent` object to the Soridormi plan request. This makes the
existing boundary protocol visible to Soridormi and logs without changing the
fact that Soridormi still owns planning and execution.

Required fields:

```json
{
  "execution_mode": "proposed",
  "execution_semantics": "proposal_from_chromie",
  "requires_runtime_validation": true,
  "interaction_id": "...",
  "request_id": "...",
  "skill_id": "soridormi.nod_yes",
  "upstream_skill_id": "nod_yes",
  "source_component": "agent.capability"
}
```

The field is intentionally sent at `soridormi.skill.create_plan`, not only at
`execute_plan`, because Soridormi's feasibility checks and plan shaping happen
while creating the body-owned plan.

### Step 2 - Add a conditional deep-thinking policy helper

Add a policy helper with a name such as `should_delegate_deepthinking()` rather
than `should_deepthink()`. The helper should decide whether to involve the
`deepthinking_agent`; it must not decide whether physical skills bypass
SkillRuntime.

The policy should be configurable by route type. A single hard-coded threshold
such as `0.8` is acceptable only as an initial default, not as the final safety
model.

### Step 3 - Support compound Route2 proposals without bypassing gates

Allow ordered action lists for simple combined commands such as "nod and say
hello." If any action in the compound request is physical, the compound result
becomes an InteractionResponse proposal. If any action is high-risk,
ambiguous, unavailable, or perception-dependent, the compound request must
escalate to a deeper agent path.

### Step 4 - Implement B-level recovery as a protocol, not a loop

Handle recoverable Soridormi failures through a bounded recovery state machine:

```text
recoverable_failure
  -> explain and ask for preference when useful
  -> timeout to conservative fallback
  -> on user confirmation, re-run preflight instead of direct retry
  -> stop after retry budget and explain
```

This needs two integration points:

- single `SkillResult` failures handled by `InteractionRuntimeCoordinator`;
- TaskGraph node failures handled by TaskGraph execution and replan logic.

Timeouts must be configurable. A development default can be short, but real
robots should use a longer prompt timeout than a simulator.

### Step 5 - Add residual replan support

Do not clear the entire plan when one step fails. Preserve:

- original goal;
- completed steps;
- failed step;
- failure code;
- current physical state summary from Soridormi;
- irreversible effects;
- Soridormi recommended next actions.

The next plan should cover only the remaining safe goal, or stop and explain
when no safe residual plan exists.

### Step 6 - Machine-readable live-perception dependencies

Represent perception-dependent body work with machine fields, not free-text
markers:

```json
{
  "requires_live_perception": true,
  "perception_dependency": "locate_object"
}
```

Chromie can reason over object names, user goals, and user-facing summaries.
Soridormi owns coordinates, grasp poses, motion trajectories, and realtime
closed-loop updates.

## Acceptance gates

A patch that changes this boundary must include tests proving at least one of
these behaviors:

- Soridormi plan calls carry `chromie_intent.execution_mode="proposed"`.
- LLM confidence does not bypass confirmation for physical skills.
- A physical skill still fails closed when confirmation or safety monitor state
  is missing.
- Recoverable Soridormi failures do not retry indefinitely.
- Residual replan preserves completed steps and current physical state.
- Perception-dependent plans do not contain invented coordinates from Chromie.

## Current patch scope

This patch implements Step 1 only and documents the full staged plan. It does
not introduce always-on dual-brain parallelism, physical fast-path execution, or
LLM-based physical critic behavior.
