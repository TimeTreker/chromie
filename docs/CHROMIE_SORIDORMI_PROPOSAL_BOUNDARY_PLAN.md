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

### Explicit proposal semantics at the Soridormi boundary

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

### Dynamic Soridormi named-skill discovery

Status: implemented in the dynamic catalog refresh patch.

The Orchestrator-side SkillRegistry must not treat the Soridormi catalog as a
one-time boot import. Soridormi may add, remove, or re-enable named skills while
Chromie is running. The host therefore refreshes `soridormi.skill.list` by TTL,
forces a refresh when a requested `soridormi.*` skill is unknown or previously
absent, upserts live definitions, and marks missing live skills unavailable
instead of silently keeping stale executable definitions.

Catalog application is atomic in both the Agent-visible capability view and
the trusted host registry: a malformed or duplicate entry rejects the whole
refresh, preserves the last complete snapshot, and cannot leave the planner and
executor with different partial catalogs.
Chromie also assigns every imported named skill one versioned, closed
adapter-result schema. Soridormi still owns the body-side plan and execution,
while the adapter projects a successful terminal result into bounded fields
such as completion, skill identity, mode, no-motion/recommendation state, and a
short summary. Raw or undeclared provider payload is not committed as
model-visible evidence.

This keeps the generic `SoridormiNamedSkillAdapter` as a protocol adapter
rather than a per-skill registry. `SoridormiMcpSkillProvider` remains only as
a backward-compatible alias for older imports.

### Conditional deep-thinking delegation policy

Status: implemented in the conditional deepthinking policy patch.

The Orchestrator now has a `DeepThinkingDelegationPolicy` helper. It decides
whether to involve the `deepthinking_agent`; it does not decide whether physical
skills bypass SkillRuntime.

The policy is configurable by route type. It delegates semantic work for
explicit deep-thought route items, missing/partial capability matches, ambiguous
or frustrated user state, live-perception dependencies, high-risk physical goals
such as navigation or manipulation, and route-specific low confidence. Simple
exact low-risk body cues can remain fast proposals.

### Compound fast-route proposals with mandatory runtime gates

Status: implemented in the compound Route2 proposal patch.

Allow ordered action lists for simple combined commands such as "nod and say
hello." Router-provided compound actions are converted into ordered
`SkillRequest` proposals by `capability_agent`, not into direct body commands.
Those requests now carry explicit proposal metadata, route-stage provenance,
compound action position, catalog safety metadata, and runtime validation flags
so the Soridormi boundary can audit how the request was formed.

If any action in the compound request is high-risk, ambiguous, unavailable, or
perception-dependent, the compound request must escalate to a deeper agent path.
The conditional deep-thinking policy therefore treats Router action
`capability_id` values, action-level live-perception flags, and selected
capability risk metadata as first-class escalation evidence.

### Confirmed bounded recovery protocol

Status: implemented for single Soridormi `SkillResult` failures; TaskGraph
node-level residual recovery remains part of the residual-replan work.

Recoverable Soridormi failures now use a bounded, request-bound recovery
confirmation instead of a generic failure message or an automatic retry:

```text
recoverable_failure
  -> explain and ask for user preference
  -> if there is no confirmation, do not retry and keep the conservative state
  -> on user confirmation, re-enter preflight/confirmation/SkillRuntime
  -> stop after retry budget and explain the conservative fallback
```

The implementation deliberately treats the user's reply as preference, not as
physical authorization. An approved recovery retry is represented as a new
`InteractionResponse` with retry request IDs and `requires_confirmation=True`;
it then goes through the existing SkillRuntime and Soridormi plan/monitor/execute
boundary again. Safety refusals, cancellations, and timeouts do not trigger
this B-level recovery path.

Config controls:

- `ORCH_BODY_RECOVERY_MAX_ATTEMPTS`, default `1`;
- `ORCH_BODY_RECOVERY_CONFIRMATION_TTL_S`, default `10`.

The confirmation timeout is conservative: if the user does not confirm, Chromie
does not retry. Late confirmation replies expire through the same
request-bound confirmation dialogue used for normal physical confirmations.

### Residual TaskGraph replanning

Status: implemented for failed/aborted TaskGraph traces and host TaskGraph skill results.

Do not clear the entire plan when one step fails. Preserve:

- original goal;
- completed steps;
- failed step;
- failure code;
- current physical state summary from Soridormi;
- irreversible effects;
- Soridormi recommended next actions.

The residual state is exported as `ExecutionTrace.residual_replan` and is
propagated through `chromie.task_graph.execute` failures when a host handler did
not already provide one. It records `completed_steps`, `failed_step`,
`failure_code`, `current_physical_state`, `irreversible_effects`,
`recommended_next_actions`, and a `replan_scope` whose mode is
`residual_only`.

This implementation deliberately does not automatically ask an LLM to retry or
execute a follow-up physical plan. The residual state is advisory context for a
later planner or user-facing explanation; any residual plan still has to be
newly validated and re-enter confirmation, SkillRuntime, and Soridormi safety
gates. The next plan should cover only the remaining safe goal, or stop and
explain when no safe residual plan exists.

### Post-interrupt review with a physical resume lock

Status: implemented for corrected `InteractionResponse` outputs and legacy
Agent actions.

When the Router emergency filter triggers an interrupt, the Orchestrator stops
output and cancels active interactions immediately. If optional post-interrupt
review later determines the ASR result was a false positive, corrected
speech-only dialogue may continue. Corrected physical work must not auto-resume,
even in simulator auto-confirm mode. Any corrected Soridormi or TaskGraph skill
is marked with:

```json
{
  "post_interrupt_physical_resume_lock": true,
  "post_interrupt_resume_policy": "requires_fresh_confirmation",
  "requires_runtime_validation": true
}
```

The lock forces request-bound confirmation and disables body auto-confirm for
that interaction. Confirmation still only restarts the normal preflight,
SkillRuntime, and Soridormi plan/monitor/execute path; it is not a resume of
the pre-stop physical state.

### Machine-readable live-perception dependency contract

Status: implemented for Router action proposals, capability-selected skills,
and Soridormi `chromie_intent` plan metadata.

Represent perception-dependent body work with machine fields, not free-text
markers:

```json
{
  "requires_live_perception": true,
  "perception_dependency": "locate_object",
  "physical_state_source": "soridormi_runtime",
  "chromie_must_not_provide_physical_coordinates": true,
  "soridormi_owns_pose_estimation": true
}
```

Chromie can reason over object names, user goals, and user-facing summaries.
Soridormi owns coordinates, grasp poses, motion trajectories, and realtime
closed-loop updates. The dependency contract lists only semantic dependencies
and expected feedback such as observation summaries, confidence, failure codes,
and recommended next actions.

### Soridormi proposal contract manifest

Status: implemented on the Chromie side by extending the Soridormi manifest and
provider call payload.

The `soridormi.skill.create_plan` schema now advertises an optional
`chromie_intent` object with proposal semantics and live-perception dependency
fields. Soridormi should treat these fields as audit and validation input:
Chromie is proposing intent, not commanding motion. Soridormi remains free to
validate, reshape, refuse, monitor, emergency-stop, and report recovery
recommendations.


### Explicit Soridormi adapter naming

Status: implemented as a safe class rename plus documentation.

The Orchestrator-side class that talks to Soridormi is now named
`SoridormiNamedSkillAdapter`. The older `SoridormiMcpSkillProvider` name remains
as a backward-compatible alias, but new code should use the adapter name. The
module docstring states the boundary explicitly: this is a Chromie-side
SkillRuntime adapter for the dynamic Soridormi MCP named-skill protocol; it is
not the body controller, hardware provider, motion planner, or per-skill
registry.

New Soridormi skills should continue to appear through `soridormi.skill.list`
and should not require new methods in this adapter. The adapter's job is only
to translate `soridormi.<skill_id>` requests into the shared plan/monitor/execute
protocol while carrying proposal and trace metadata.

### End-to-end architecture acceptance coverage

Status: implemented with integration coverage for the safety boundary.

The final acceptance tests cover the main safety chain across modules:

- dynamically listed Soridormi skills execute through the generic adapter;
- Soridormi `create_plan` receives `chromie_intent.execution_mode="proposed"`;
- route provenance reaches the body-planning boundary;
- live-perception dependencies reach planning as semantic contract fields, not
  fabricated coordinates;
- post-interrupt corrected physical work cannot use simulator auto-confirm and
  requires fresh confirmation before planning;
- the old provider class name remains a compatibility alias for existing code.

### Addendum - Capability proposal adjudication

Status: implemented for catalog-backed `CapabilityAgent` plans.

The Capability Agent now treats LLM output as a skill proposal instead of a
final executable command. A plan item may include `semantic_intent`,
`proposed_args`, `parameter_grounding`, and `unmapped_intent`. These fields let
the LLM preserve human intent such as direction, speed, duration, target, or
object references without pretending that it has final physical authority.

The agent then adjudicates the proposal against the selected capability schema:

- only exact catalog `skill_id` values are accepted;
- enum strings may be normalized to schema tokens;
- numeric proposal fields can be bounded to schema limits when that produces a
  valid safer proposal;
- bounded numeric adjustments force request confirmation;
- unsupported modifiers stay in `unmapped_intent` instead of becoming invented
  schema fields;
- resulting `SkillRequest` metadata records the semantic intent, parameter
  grounding, requested vs. accepted args, and adjustment reasons.

This keeps the desired split: the LLM generalizes user language into a semantic
proposal; the capability layer accepts, adjusts, asks for confirmation, or
blocks based on the concrete catalog schema; `SkillRuntime` and Soridormi still
own runtime validation and physical execution authority.

## Acceptance gates

A patch that changes this boundary must include tests proving at least one of
these behaviors:

- Soridormi plan calls carry `chromie_intent.execution_mode="proposed"`.
- LLM confidence does not bypass confirmation for physical skills.
- A physical skill still fails closed when confirmation or safety monitor state
  is missing.
- Recoverable Soridormi failures do not retry indefinitely.
- Residual replan preserves completed steps and current physical state.
- Post-interrupt corrected physical skills require fresh confirmation and disable auto-confirm.
- Perception-dependent plans do not contain invented coordinates from Chromie.
- Soridormi `create_plan` advertises and receives proposal contract metadata.
- Capability Agent skill proposals carry adjudication metadata when parameters
  are accepted or safely bounded before confirmation.

## Current implemented scope

Implemented so far:

1. Explicit `chromie_intent.execution_mode="proposed"` metadata at the
   Soridormi `create_plan` boundary.
2. Dynamic Orchestrator-side Soridormi named-skill catalog refresh.
3. Conditional deep-thinking delegation policy for semantic escalation.
4. Compound Route2 actions remain ordered proposals with traceable route and
   catalog metadata, while high-risk `capability_id` actions and
   live-perception flags escalate to deeper reasoning.
5. B-level recoverable single-skill Soridormi failures stage a bounded
   request-bound recovery confirmation and never retry automatically.
6. Failed/aborted TaskGraph traces now carry structured `residual_replan`
   context preserving completed work, the failed step, physical state,
   irreversible effects, and Soridormi next-action hints for residual-only
   replanning.
7. Post-interrupt corrected physical work is locked behind fresh confirmation
   and cannot use simulator body auto-confirm.
8. Live-perception dependencies are represented as machine fields and passed to
   Soridormi without invented coordinates.
9. The Soridormi `create_plan` manifest and provider payload expose the
   proposal contract explicitly.
10. The Orchestrator-side Soridormi boundary is named and documented as
    `SoridormiNamedSkillAdapter`, with the older provider name kept as a
    compatibility alias.
11. Integration acceptance tests cover dynamic MCP skills, proposal metadata,
    live-perception contracts, and post-interrupt physical resume locking across
    module boundaries.
12. Capability Agent LLM plans are treated as semantic skill proposals. The
    agent records parameter grounding and can bound numeric fields to schema
    limits while requiring confirmation for adjusted physical proposals.

Still intentionally not implemented: always-on dual-brain parallelism, physical
fast-path execution from LLM confidence, LLM-based physical critic behavior,
unbounded recovery loops, automatic residual re-execution, and Chromie-side
low-level physical coordinates.
