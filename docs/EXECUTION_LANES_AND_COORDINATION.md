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

## Soridormi body lanes

Soridormi is a peer Capability Provider beneath Chromie's Activity lane. For
safe body concurrency, Soridormi may advertise these body-lane identities:

```text
Soridormi
├── subtle_expression
├── locomotion
├── whole_body
└── safety
```

Typical ownership:

| Body lane | Examples | Typical resource claims |
|---|---|---|
| `subtle_expression` | blink, eye expression, bounded gaze, small compatible gestures | `eye_expression`, `head_overlay` |
| `locomotion` | walk, turn, bounded base motion | `base_motion`, `balance_control` |
| `whole_body` | recovery, jump, coordinated full-body performance | `whole_body`, `balance_control` |
| `safety` | emergency stop, fall recovery, collision response | provider-defined safety authority |

The body-lane name is provider evidence, not a Host rule. Chromie never infers
`blink -> subtle_expression` or `walk -> locomotion` from capability names or
user phrases. Soridormi must explicitly declare `body_lane`, resource claims,
parallel safety, and an exclusive group in its live skill catalog.

Example provider declarations:

```json
{
  "id": "walk_forward",
  "body_lane": "locomotion",
  "can_run_parallel": true,
  "exclusive_group": "soridormi.base_motion",
  "resource_claims": ["base_motion", "balance_control"]
}
```

```json
{
  "id": "blink_eyes",
  "body_lane": "subtle_expression",
  "can_run_parallel": true,
  "exclusive_group": "soridormi.eye_expression",
  "resource_claims": ["eye_expression"]
}
```

Those declarations allow walking and blinking to overlap when Soridormi's
safety authority accepts them. They still prevent two conflicting locomotion
skills from running together.

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

## Runtime behavior

The maintained runtime:

1. validates all coordination references and lane membership;
2. requires referenced activity steps to be parallel Canonical Plan steps;
3. keeps ordinary pre-action speech behind the playback-start barrier;
4. emits coordinated speech, activity, and social-expression requests as
   parallel Trusted Capability Runtime requests;
5. requires explicit provider parallel metadata for Social Attention overlap;
6. rejects conflicting exclusive groups or resource claims;
7. records lane membership and coordination IDs in interaction evidence; and
8. reconciles each Goal only from capability-specific outcome evidence.

The Trusted Capability Runtime currently starts compatible parallel requests as
one asynchronous batch. This provides best-effort overlap, not synchronized
start-time proof. A future coordinated-bundle contract may add prepared states,
a shared monotonic start barrier, bundle cancellation, member criticality, and
measured overlap.

## Singing

Speaking and singing belong to the Speaking lane, but ordinary TTS is not proof
of a singing capability. Chromie may claim singing only when an exact vocal
Capability Provider advertises and completes a suitable contract, for example
`chromie.vocal.perform`. Until then, Chromie may speak or recite text but must
not claim melodic performance.

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
