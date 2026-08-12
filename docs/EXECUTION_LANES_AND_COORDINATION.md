# Execution Lanes and Coordination

## Status

Chromie has one Goal-Driven Cognitive Core and three concurrent coordination
lanes:

```text
Chromie Cognitive Core
├── Social-Attention Proposal Lane
├── Vocal Execution Lane
└── Activity Execution Lane
      └── Capability Providers
          ├── Soridormi
          ├── Media Playback
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
| Vocal Execution Lane | authored speech, TTS/vocal playback, vocal performance capabilities, interruption, cancellation, and output ordering | independent personality, semantic planning, or existing-media lifecycle ownership |
| Activity Execution Lane | exact provider calls, task execution, monitoring, cancellation, recovery, and outcome collection | Goal meaning or raw motor control |
| Soridormi | embodied feasibility, body-lane arbitration, safety supervision, controller execution, stop, recovery, and physical evidence | conversational meaning or provider selection |

The Activity lane executes work for Goals; it does not own those Goals.
Social Attention proposes socially appropriate behavior; it does not directly
operate the body. Vocal delivers Chromie-authored personal voice output; it is not a
separate conversational agent.

## Continuous Social Attention

Social Attention is a concurrent interaction lane, not an ornament attached only
to a final spoken response. It may be reconsidered when meaningful interaction
state changes, including:

- a user starts or finishes addressing Chromie;
- fast understanding becomes sufficient to acknowledge or begin safe progress;
- Activity or information acquisition starts, waits, changes, completes, or
  fails;
- new scene/target evidence becomes available;
- interruption or cancellation changes the interaction; and
- Vocal output starts, continues, or completes.

These triggers provide *state*, not hardcoded gestures. The Social-Attention
cognition still decides whether expression is useful and may choose
`decision=none`. It consumes a bounded social projection of the one Core-owned
interaction together with Chromie's stable Mind. It therefore does not need to
wait for a complete Goal graph when the available scene and interaction evidence
already support a harmless expression. Conversely, target-specific gaze or
other claims that require scene evidence remain unavailable until that evidence
exists.

Response Composer may coordinate body expression with authored speech when one
joint decision is useful, but it is not the exclusive owner or only trigger of
Social Attention. A separate Social-Attention model path, when used, remains an
auxiliary proposal mechanism rather than a second semantic planner.

When the runtime already knows the reviewed live set of eligible social
Capabilities, the model-facing contract should make invented identifiers
unrepresentable: `capability_id` is constrained to the exact supplied candidate
IDs, while trusted code still validates arguments, target evidence, resources,
safety, and provider availability. The model decides *whether* and *which*
eligible expression is appropriate; it does not reconstruct machine identifiers.

Optional Social Attention must fail soft with respect to unrelated primary work.
A slow, invalid, unavailable, or rejected social proposal must not delay an
otherwise-ready safe read or cancel a valid primary Activity Plan. Coordination
creates a dependency only when the intended behavior actually requires one.

Example interaction:

```text
user speaks
  -> Social Attention may orient/listen

fast understanding becomes sufficient
  -> optional acknowledgement expression
  -> safe information acquisition may start independently

provider result arrives
  -> Social Attention may re-engage

Chromie answers
  -> speech and optional expression may be coordinated
```

No stage above requires a gesture, and none gives Social Attention authority over
the user's Goal.

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

Speech remains a peer Chromie Vocal-lane execution linked through the same
`coordination_id`. Soridormi never owns speech meaning, TTS playback, or peer
media execution.

## Lane-coordination contract

`LaneCoordinationGroup` records model-authored execution overlap after the
Canonical Plan already exists. It does not create capabilities or authorize an
effect.

```json
{
  "coordination_id": "performance_1",
  "relation": "parallel",
  "lanes": ["vocal", "activity", "social_attention"],
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
Host may reuse an exact source-authored, mechanically validated current-turn
`robot_action` Fast Response as `pre_action` coverage. It may not invent text, cover a clarification
or unavailable Goal mechanically, or change the immutable Capability Plan.

Optional Social Attention is likewise not execution authority. A model output
that selects `decision=express` but contains neither a valid body behavior nor
`speech_expression.mode=adapt` is normalized to an explicit `decision=none`
before nested DTO validation. The empty auxiliary expression is dropped while
the immutable mixed or Activity Plan remains available to Runtime.

Eligible `tool`, `robot_action`, and `deep_thought` fast acknowledgements receive
an independent semantic review before playback. Persona may shape wording but
may not invent another errand, destination, person, object, household activity,
unsupported ability, or external result. Tool speech is restricted to the typed
`acknowledge_and_check`/`checking_only` act; memory speech remains suppressed
until commit. The Host may use its bounded low-commitment generic cache for any
suppressed, unavailable, or invalid dynamic acknowledgement.

## Runtime behavior

The maintained runtime:

1. validates all coordination references and lane membership;
2. requires referenced activity steps to be parallel Canonical Plan steps;
3. keeps ordinary pre-action speech behind the playback-start barrier;
4. runs Vocal and peer-provider Activity work as a best-effort parallel
   batch;
5. groups compatible same-provider Soridormi body members into one deterministic
   embodied compilation and execution;
6. requires explicit provider concurrency metadata for Social Attention overlap;
7. maps Soridormi aggregate member evidence back to the original request IDs and
   Goal-owning steps;
8. records lane membership and coordination IDs in interaction evidence; and
9. reconciles each Goal only from its own capability-specific outcome evidence.

Cross-provider Vocal/body start remains best-effort. Inside Soridormi, body
members are compiled and cancelled as one provider-local physical activity. A
future cross-provider contract may add prepared states, a shared monotonic start
barrier, measured overlap, and explicit degraded/optional outcome vocabulary.

## Typed Goal completion contract

Validated Goals retain five separate completion facts instead of overloading
`responsibility_kind`:

```text
responsibility_kind  human completion modality
execution_lane       vocal | activity | none
output_mode          speech | expressive_speech | recitation | singing | humming
                     | nonverbal_vocalization | body_action | media_playback
                     | capability_work | other
provider_required    exact provider evidence required beyond ordinary speech
media_operation      play | pause | resume | seek | stop | volume | status | none
```

The live model schema exposes the semantic completion choice `output_mode` and,
only when needed for media lifecycle semantics, `media_operation`. The Host
deterministically materializes `responsibility_kind`, `execution_lane`, and
`provider_required` from `output_mode`; those redundant system invariants are
not independent LLM decisions. A bounded legacy mapping keeps retained replay
and old test DTOs readable without reopening that model-facing state space.
`output_mode=speech` materializes ordinary Vocal speech delivery without a
mode-specific provider requirement. Mode-specific vocal outputs materialize
Vocal output with provider evidence required. `chromie.vocal.perform` is the exact source
contract for qualified provider execution, but the default catalog remains
unavailable and advertises no modes. Planner may execute one such Goal only when
a qualified declaration advertises the authoritative `output_mode`; otherwise
it must return a per-Goal unavailable, refused, or clarification outcome rather
than generic `respond`. Activity, body, and media execution remain separate. A
normal vocal Goal cannot carry `resource_responsibility`.

## One personal voice

`Vocal` is Chromie's personal-voice execution domain:

```text
Vocal
├── speech
├── expressive_speech
├── recitation
├── singing
├── humming
└── nonverbal_vocalization
```

These are different semantic outcomes but one embodied personal voice. They
share one execution-time resource:

```text
chromie.voice: exclusive
```

So `speech + singing`, `speech + humming`, and `singing + recitation` must
serialize. Compatible Activity can still overlap Vocal work: `walk + singing`,
`blink + speech`, and `walk + blink + singing` are valid when their providers
are otherwise qualified.

Capabilities answer **what can be done**; execution resources answer **what can
coexist**. The Cognitive Core plans with both truths, and the Trusted Capability
Runtime mechanically contains a bad parallel plan. This rule reuses the existing
`ResourceArbiter`; it does not create a second Resource Manager.

`chromie.voice` is not the Goal-level acquire/deliver `Resource` responsibility,
and it is not identical to the physical speaker. Existing-media playback remains
Activity. A qualified mixer may overlap Media and Vocal under
`duck_media_during_vocal`.

Ordinary TTS historically released its runtime request at `playback_started`,
while PCM continued playing. The maintained playback lifecycle therefore exposes
a separate terminal voice-release fact. Body Activity may still begin at the
playback-start barrier, but a following Vocal mode cannot acquire `chromie.voice`
until prior TTS has actually stopped producing Chromie's voice.

## Existing media playback

Playing existing music, recordings, streams, or sound effects is Activity work,
not authored vocal performance. A qualified peer provider exposes only the
stable `chromie.media.play|pause|resume|seek|stop|volume|status` family. The
backend name stays behind the Trusted Capability Runtime, while
`media_operation` binds each media Goal to exactly one public operation from
Goal Association through planning and evidence. Persistent controls correlate
through a provider-returned `playback_id`; ordinary TTS delivery and
`chromie.vocal.perform` cannot satisfy that Goal.

When a response stage intentionally overlaps a media Activity step, both must
reference one explicit `LaneCoordinationGroup`. The Host requires the qualified
provider's `duck_media_during_vocal` contract and copies its gain, attack,
and release values onto the Vocal item and media request. Missing or
conflicting mixer declarations fail closed before execution. This runtime
coordination metadata neither merges nor rewrites the Vocal and media Goals.

Media remains independently cancellable. `output_only` selects Vocal output,
`media_output` selects media work across open runtime interactions, and
`current_interaction` selects all eligible work in the foreground interaction.
Each scope returns correlated selected/active/queued/provider-failure evidence;
none of those receipts by itself proves audible silence or a target safe state.

## Singing

Ordinary speech and singing belong to the Vocal lane, including when the user embeds
the vocal request inside a compound body command such as walking while singing.
Lane classification follows the channel that completes the outcome, not the
sentence's verb form or the surrounding robot-action route. Singing must never
be reclassified as `express_attention` or another body action merely because it
is coordinated with motion.

Ordinary TTS is not proof of a singing capability. Chromie may claim singing
only when a qualified provider advertises `singing` on
`chromie.vocal.perform` and returns exact completed mode and audible-delivery
evidence. The maintained default has no qualified mode, so Chromie may speak
text but must not claim melodic performance; it should report the missing vocal
capability or offer a clearly labeled alternative while leaving requested body
actions independently planable.

An executable vocal-performance step remains a Vocal member during
cross-lane coordination. `LaneCoordinationGroup.vocal_step_ids` binds those
provider steps, while `activity_step_ids` binds Activity work. Response Composer
may coordinate both in one parallel group, but it cannot relabel the vocal step
as Activity or treat an acknowledgement through `chromie.speak` as performance
evidence.

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
- one coordinated Vocal speech stage;
- no pending confirmation;
- playback evidence and activity outcome evidence; and
- truthful speech that does not claim activity completion before the outcome.

### Walk, blink, and sing

This remains partially unavailable until a target-qualified provider advertises
the requested mode. Source tests prove the exact contract with a fake recitation
provider only; the planner must not substitute ordinary speech for singing.

### Walk and play existing audio

Acceptance requires two independently owned Activity Goals and exact parallel
steps: a Soridormi body capability and `chromie.media.play`. The plan remains in
the robot-action authority envelope because it includes body work, while media
completion and cancellation remain owned by the peer media provider. The
response must describe existing-audio playback and must not call it singing.
