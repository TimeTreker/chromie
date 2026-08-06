# Execution Lanes and Coordination

## Status

Chromie has one Goal-Driven Cognitive Core and three semantic coordination
lanes:

```text
Chromie Cognitive Core
├── Social-Attention Proposal Lane
├── Speaking Lane
│     └── platform-neutral Vocal Plan
└── Activity Lane
      └── platform-neutral Capability Plan
```

The approved target execution boundary is:

```text
Chromie Interaction Orchestrator
├── validates authorization, confirmation, cancellation scope, and Goal binding
├── dispatches platform-neutral vocal and activity requests
└── correlates provider evidence with the active interaction
                 │
                 ▼
Soridormi Execution Runtime
├── body execution
├── vocal execution: speech, expressive speech, recitation, singing, humming
├── media execution: music, recordings, and sound effects
├── provider-local preparation, scheduling, synchronization, and cancellation
└── normalized per-member execution evidence
                 │
                 ▼
Soridormi Platform Provider
└── MuJoCo, physical robot, desktop audio, sensors, and device drivers
```

External-information and memory capabilities may remain platform-neutral peer
providers when they do not depend on a robot platform. Platform-facing body,
vocal, media, sensor, and device adaptation must converge behind Soridormi.

This target is an approved architecture direction, not a claim about current
implementation. At the current revision, TTS synthesis and playback are still
owned by the Chromie Host, Soridormi mainly executes body capabilities, and
cross-provider start is best effort. Migration must preserve current behavior
until equivalent receipts, cancellation, and target evidence exist.

## Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Cognitive Core | user meaning, Goal Association, Goal lifecycle, planning, response meaning, vocal mode, and temporal intent | device selection, synthesis, motor control, provider internals |
| Social-Attention Proposal Lane | bounded social proposals such as attention, natural blink, gaze, acknowledgement, or restraint | independent speech meaning, Goal creation, execution authorization |
| Speaking Lane | the communicative outcome and a typed vocal plan such as speech, recitation, singing, or humming | audio-device selection, synthesis implementation, or a false performance claim |
| Activity Lane | exact capability work such as body action, media playback, information lookup, or device control | Goal meaning, raw device commands, or provider-local scheduling |
| Chromie Interaction Orchestrator | session and turn lifecycle, VAD/ASR coordination, Gateway/Core dispatch, confirmation and cancellation semantics, authorization, high-level lane relation, and end-to-end evidence correlation | TTS synthesis, PCM device playback, motor control, or platform adaptation |
| Soridormi Execution Runtime | provider-local compilation, preparation, execution, resource arbitration, time coordination, cancellation, recovery, and normalized evidence for platform-facing capabilities | user meaning, Goal mutation, response authorship, or widening authorization |
| Soridormi Platform Provider | simulator or hardware adaptation, microphone and speaker devices, sensors, controllers, drivers, calibration, state estimation, and hardware safety | cognitive planning or user-facing semantics |

The Activity lane executes work for Goals; it does not own those Goals.
Social Attention proposes socially appropriate behavior; it does not directly
operate the body. Speaking describes how Chromie communicates; it is not a
separate conversational agent. Soridormi executes authorized outcomes but never
decides what the user meant.

## Soridormi execution-runtime and platform-provider contract

The target Soridormi project has two logical containers:

```text
soridormi-runtime
= stable high-level capability execution, resource and safety coordination,
  multimodal preparation, cancellation, recovery, and evidence

soridormi-platform
= exactly one active simulator or physical-platform adapter, including device
  drivers, audio devices, sensors, calibration, and hardware safety
```

Chromie's Planner selects exact semantic capabilities and preserves user-level
timing. It does not select a motor controller, TTS backend, sound device, robot
SDK, or simulator implementation. The Chromie authorization boundary validates
the request and sends an immutable execution envelope. Soridormi may reject an
unsupported or unsafe envelope, but it cannot reinterpret the Goal or silently
substitute a different user outcome.

The existing body declaration remains useful inside the wider Soridormi runtime.
For example:

```json
{
  "capability_id": "body.walk_forward",
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
  "capability_id": "expression.blink_eyes",
  "concurrency": {
    "ability_class": "subtle_expression",
    "control_coupling": "independent_output",
    "write_resources": ["visual.eyes"],
    "parallel_safe_with": ["locomotion_whole_body"]
  }
}
```

Vocal and media providers must declare equivalent capability and resource facts,
for example supported vocal modes, streaming support, timing marks, audio-output
claims, interruption behavior, and whether a prepared start is available.
Chromie must not infer those facts from a capability name or user phrase.

During migration, the maintained body path may continue to use:

```text
exact planner-selected body members
  -> soridormi.activity.compile
  -> Soridormi resource/controller/safety validation
  -> soridormi.activity.execute
  -> per-member authoritative evidence
```

`compile` is deterministic execution compilation, not cognitive planning. The
same principle will later cover body, vocal, and media members in one
provider-local execution group. A shared start barrier or atomic cancellation
may be claimed only after Soridormi publishes and proves that contract.

Speech meaning remains owned by Chromie. The target moves vocal synthesis and
playback execution into Soridormi; it does not move response authorship,
personality, Goal meaning, or user-level interruption semantics there.

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

The maintained runtime currently:

1. validates all coordination references and lane membership;
2. requires referenced activity steps to be parallel Canonical Plan steps;
3. keeps ordinary pre-action speech behind the playback-start barrier;
4. runs Chromie-owned Speaking playback and peer-provider Activity work as a
   best-effort parallel batch;
5. groups compatible same-provider Soridormi body members into one deterministic
   embodied compilation and execution;
6. requires explicit provider concurrency metadata for Social Attention overlap;
7. maps Soridormi aggregate member evidence back to the original request IDs and
   Goal-owning steps;
8. records lane membership and coordination IDs in interaction evidence; and
9. reconciles each Goal only from its own capability-specific outcome evidence.

The target runtime keeps items 1, 8, and 9 in Chromie, while Soridormi assumes
provider-local preparation, execution, resource arbitration, synchronization,
and cancellation for body, vocal, and media output. The migration must not claim
synchronized start until prepared-state and monotonic-start evidence exists.

## Vocal modes, singing, and TTS

Speaking is a semantic lane with multiple execution modes. The first contract
change must represent at least:

```text
speech
expressive_speech
recitation
singing
humming
nonverbal_vocalization
```

A TTS provider may support only a subset. Expressive speech proves control over
speech prosody; it does not by itself prove stable singing, melody following, or
rhythmic lyric alignment. Soridormi must advertise supported modes and return
mode-specific execution evidence. Chromie may request only a declared mode and
may claim completion only from matching evidence.

Singing and humming remain Speaking-lane outcomes even when coordinated with
walking or blinking. Classification follows the output channel that completes
the responsibility, not the sentence's verb form or a surrounding
`robot_action` route. Singing must never become `express_attention`, a body
motion, media playback, or a generic acknowledgement.

The immediate semantic fix must also close the failure exposed by the retained
compound scenario:

- Goal Association must emit separate independently satisfiable Goals for body
  motion, vocal performance, and expression;
- a vocal Goal must not carry `resource_responsibility` merely because it needs
  an execution provider;
- semantic review of a suspicious compound decomposition must regenerate from
  the authoritative turn and typed context rather than copy the previous wrong
  DTO;
- Planner step ownership and per-goal step references must be mechanically
  consistent, and no outcome may reference an unknown step ID;
- unavailable singing must remain an honest per-goal outcome. Ordinary TTS,
  media playback, blinking, or attention expression cannot be substituted and
  described as singing.

The target vocal request is platform-neutral, for example:

```json
{
  "capability_id": "vocal.render",
  "args": {
    "mode": "singing",
    "content": "...",
    "accompaniment": "none"
  }
}
```

The exact public schema is owned by the implementation Issue and API review; the
example establishes semantic separation, not a frozen wire format.

## Media playback

Playing an existing song, recording, or sound effect is not TTS and is not a
Speaking outcome. It is an Activity capability, implemented by a media provider
inside Soridormi Runtime and rendered through the active platform's audio
output. `media.play` therefore has its own lifecycle, state, cancellation, and
evidence even when it shares an audio mixer with vocal output.

```text
"清唱一首歌"       -> Speaking / vocal.render(mode=singing)
"播放一首歌"       -> Activity / media.play
"边走边清唱"       -> Speaking + Activity coordination
"边走边播放音乐"   -> two Activity members coordinated by Soridormi
```

The shared mixer may duck, pause, or prioritize streams, but it cannot merge the
semantic contracts or convert one into the other.

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

The semantic contract requires three independent outcomes with one explicit
parallel relation. Exact execution requires Soridormi evidence for walking and
blinking plus matching `singing`-mode vocal evidence. Until a genuine singing
provider is declared and validated, the singing outcome is unavailable; the
planner must not substitute ordinary speech, media playback, or a body gesture.
Whether independently executable body members may proceed must be explicit in
the per-goal and coordination failure policy rather than inferred by the Host.
