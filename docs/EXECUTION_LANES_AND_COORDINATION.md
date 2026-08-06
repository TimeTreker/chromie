# Execution Lanes and Coordination

## Status

Chromie has one Goal-Driven Cognitive Core and three concurrent coordination
lanes:

```text
Chromie Cognitive Core
├── Social-Attention Proposal Lane
├── Speaking Execution Lane
└── Activity Execution Lane
      └── Capability Providers
          ├── Soridormi
          ├── External Information
          ├── Weather
          ├── Memory
          └── future providers
```

The shared contracts and maintained runtime now support explicit best-effort
coordination across those lanes. This is not a second brain, a second planner,
or a provider-selection shortcut. Goal meaning, Goal Association, planning, and
response meaning remain owned by the one Cognitive Core.

The current implementation provides best-effort parallel start through the
Trusted Capability Runtime. It does not yet claim a synchronized cross-provider
start barrier, atomic multi-provider cancellation, or verified temporal-overlap
evidence. Those require a later runtime contract and provider support.

## Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Cognitive Core | user meaning, Goal Association, Goal lifecycle, planning, response meaning, temporal intent | motor control, provider internals |
| Social-Attention Proposal Lane | bounded social proposals such as attention, natural blink, gaze, acknowledgement, or restraint | independent speech meaning, Goal creation, motor authorization |
| Speaking Execution Lane | TTS, playback, vocal performance capabilities, interruption, cancellation, and output ordering | independent personality or semantic planning |
| Activity Execution Lane | exact provider calls, task execution, monitoring, cancellation, recovery, and outcome collection | Goal meaning or raw motor control |
| Soridormi | embodied feasibility, body-lane arbitration, safety supervision, controller execution, stop, recovery, and physical evidence | conversational meaning or provider selection |

The Activity lane executes work for Goals; it does not own those Goals.
Social Attention proposes socially appropriate behavior; it does not directly
operate the body. Speaking delivers model-authored communication; it is not a
separate conversational agent.

## Soridormi embodied compilation contract

Soridormi is a peer Capability Provider beneath Chromie's Activity lane. It
does not own user meaning, Goals, or cognitive planning. Chromie's Cognitive
Planner selects exact semantic capabilities first; the Runtime Coordinator then
groups exact same-provider body members for deterministic embodied compilation.

Soridormi's canonical live declaration is the nested `concurrency` object:

```json
{
  "skill_id": "walk_forward",
  "concurrency": {
    "ability_class": "locomotion_whole_body",
    "control_coupling": "primary_body_controller",
    "write_resources": ["body.primary_motion"],
    "safety_preemption": "safe_hold"
  }
}
```

```json
{
  "skill_id": "blink_eyes",
  "concurrency": {
    "ability_class": "subtle_expression",
    "control_coupling": "independent_output",
    "write_resources": ["visual.eyes"],
    "parallel_safe_with": ["locomotion_whole_body"]
  }
}
```

Chromie preserves `ability_class`, `control_coupling`, exact provider resource
names, locomotion envelopes, and safety-preemption policy. It never assigns
those values from a skill name or user phrase. Flattened `body_lane` and
`resource_claims` fields are compatibility projections only; the nested
provider contract remains authoritative.

When a parallel batch contains multiple exact Soridormi body capabilities, the
Trusted Capability Runtime does not start them as independent physical calls.
It asks the provider adapter to execute one provider-local group:

```text
exact planner-selected body members
  -> soridormi.activity.compile
  -> Soridormi resource/controller/safety validation
  -> soridormi.activity.execute
  -> per-member authoritative evidence
```

`compile` is deterministic embodied compilation, not cognitive planning. It may
reject duplicate resources, two primary locomotion members, an unsafe overlay,
or unavailable body state. It does not decide whether Chromie should walk,
blink, look, speak, or sing.

Speech remains a peer Chromie Speaking-lane execution linked through the same
`coordination_id`. Soridormi never owns speech meaning or playback.

## Lane-coordination contract

`LaneCoordinationGroup` records model-authored execution overlap after the
Canonical Plan already exists. It does not create capabilities or authorize an
effect.

```json
{
  "coordination_id": "performance_1",
  "relation": "parallel",
  "lanes": ["speaking", "activity", "social_attention"],
  "activity_step_ids": ["step_walk"],
  "start_policy": "best_effort_parallel",
  "failure_policy": "independent",
  "reason_summary": "Walk while speaking and blinking."
}
```

The participating response stage copies the same identifier:

```json
{
  "text": "我来啦。",
  "speech_act": "inform",
  "commitment_state": "in_progress",
  "must_not_claim_completion": true,
  "covers_goal_ids": ["goal_performance"],
  "coordination_id": "performance_1",
  "delivery_role": "activity_companion"
}
```

An auxiliary social proposal may join the same group:

```json
{
  "capability_id": "soridormi.blink_eyes",
  "args": {"count": 2},
  "timing": "parallel",
  "social_function": "engagement",
  "coordination_id": "performance_1"
}
```

The referenced Canonical Plan activity steps must already use
`timing=parallel`. The Response Composer cannot convert a sequential activity
step into a parallel one.

## Playback and confirmation rules

Ordinary pre-action acknowledgement remains playback-barriered:

```text
say “我准备开始了”
→ playback starts
→ effectful activity may begin
```

Speech participates in Activity overlap only when the Response Composer
explicitly marks it with a coordination group and
`delivery_role=activity_companion` or `performance`.

Confirmation and waiting speech never overlap the effect it is authorizing:

```text
ask for confirmation
→ wait for user
→ authorize
→ begin coordinated activity
```

A provider confirmation requirement remains authoritative. Lane coordination
cannot weaken confirmation, capability availability, argument validation,
resource conflict checks, or provider safety.

Response presentation is not execution authority. Malformed optional
`lane_coordination` members are pruned before DTO validation when their lane
membership or activity references cannot be reconciled with the immutable
Canonical Plan. A presentation-only failure must not cancel an otherwise valid
pure Activity Plan. After one bounded model repair, a non-confirmation
`execute` Plan may reuse an exact model-authored current-turn acknowledgement
as its existing playback-start barrier and continue to the Trusted Capability
Runtime. This fail-soft path never invents speech, selects a Capability, removes
confirmation, or applies to mixed, clarification, or confirmation-bound Plans.

For a non-confirmation `mixed` Plan, the requested spoken outcome and the
pending Activity acknowledgement may occupy separate ResponsePlan stages. If
the model covers all non-execute Goals but omits only execute Goal coverage, the
Host may reuse an exact independently reviewed current-turn `robot_action` fast
utterance as `pre_action` coverage. It may not invent text, cover a clarification
or unavailable Goal mechanically, or change the immutable Capability Plan.

Optional Social Attention is likewise not execution authority. A model output
that selects `decision=express` but contains neither a valid body behavior nor
`speech_expression.mode=adapt` is normalized to an explicit `decision=none`
before nested DTO validation. The empty auxiliary expression is dropped while
the immutable mixed or Activity Plan remains available to Runtime.

Every pending-work fast acknowledgement (`tool`, `robot_action`, `deep_thought`,
and `memory`) receives an independent semantic review before playback. Persona
may shape wording but may not invent another errand, destination, person, object,
household activity, or unsupported ability. Before provider evidence exists,
fast speech may say that Chromie will check, but may not predict weather,
measurements, conditions, recommendations, or results. If review is unavailable
or invalid, the dynamic utterance is suppressed so the Host can use its bounded
low-commitment cached fallback.

## Runtime behavior

The maintained runtime:

1. validates all coordination references and lane membership;
2. requires referenced activity steps to be parallel Canonical Plan steps;
3. keeps ordinary pre-action speech behind the playback-start barrier;
4. runs Speaking and peer-provider Activity work as a best-effort parallel
   batch;
5. groups compatible same-provider Soridormi body members into one deterministic
   embodied compilation and execution;
6. requires explicit provider concurrency metadata for Social Attention overlap;
7. maps Soridormi aggregate member evidence back to the original request IDs and
   Goal-owning steps;
8. records lane membership and coordination IDs in interaction evidence; and
9. reconciles each Goal only from its own capability-specific outcome evidence.

Cross-provider Speaking/body start remains best-effort. Inside Soridormi, body
members are compiled and cancelled as one provider-local physical activity. A
future cross-provider contract may add prepared states, a shared monotonic start
barrier, measured overlap, and explicit degraded/optional outcome vocabulary.

## Singing

Speaking and singing belong to the Speaking lane, including when the user embeds
the vocal request inside a compound body command such as walking while singing.
Lane classification follows the channel that completes the outcome, not the
sentence's verb form or the surrounding robot-action route. Singing must never
be reclassified as `express_attention` or another body action merely because it
is coordinated with motion.

Ordinary TTS is not proof of a singing capability. Chromie may claim singing
only when an exact vocal Capability Provider advertises and completes a suitable
contract, for example `chromie.vocal.perform`. Until then, Chromie may speak or
recite text but must not claim melodic performance; it should report the missing
vocal capability or offer a clearly labeled alternative while leaving requested
body actions independently planable.

## Self-concept boundary

Provider backend, simulator or hardware mode, controller identity, and test
configuration remain engineering evidence. They do not change Chromie's
ordinary self-concept or lane architecture. The same semantic request and lane
contract apply across provider deployments; the provider may realize or safely
reject the request according to its own evidence and safety state.

## Acceptance examples

### Walk and blink

Acceptance requires:

- separate user responsibilities or one compound Goal with explicit parallel
  temporal meaning;
- exact walking and blinking capabilities;
- distinct provider-declared body lanes, exclusive groups, and resources;
- both capabilities marked parallel-safe;
- Soridormi outcome evidence for both members; and
- no completion claim derived from only one member.

### Walk and speak

Acceptance requires:

- one parallel Activity step;
- one coordinated Speaking stage;
- no pending confirmation;
- playback evidence and activity outcome evidence; and
- truthful speech that does not claim activity completion before the outcome.

### Walk, blink, and sing

This remains partially unavailable until a genuine vocal-performance
capability exists. The planner must not substitute ordinary speech for singing.
