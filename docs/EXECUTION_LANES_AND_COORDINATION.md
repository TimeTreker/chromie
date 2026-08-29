# Execution Lanes and Coordination

## Status

The [Project Charter](PROJECT_CHARTER.md) expanded primary diagram is the
authoritative main workflow. This document elaborates only the `realization`
branches beneath semantic Primary Activities; the lane topology below is not a
second or alternative primary architecture.

Chromie has one Goal-Driven Cognitive Core and two execution lanes:

```text
Chromie Cognitive Core
├── Vocal Execution Lane
└── Activity Execution Lane
      └── Capability Providers
          ├── Soridormi
          ├── Media Playback
          ├── External Information
          ├── Weather
          ├── Memory
          └── future providers

Planner-owned auxiliary Activities
  └── may add optional embodied decoration around an anchored Main Activity
      └── accepted body decoration executes through Activity
```

The shared contracts and maintained runtime support explicit best-effort
coordination between Vocal and Activity. Social Attention is deliberately not a
third lane or background cognition. It is a Planner-owned behavior domain for small auxiliary
body decoration such as gaze, blink, nod, a small wave, or slight posture /
orientation when the live catalog and interaction make that appropriate.

### Terminology boundary: semantic Activity is not the Activity Execution Lane

The word **Activity** appears at two layers and must not be collapsed:

- **Responsibility/Goal** is above Activity and may own one or many semantic Work
  Activities. The boundary may change with provider capability: one high-level
  provider workflow can stay atomic while lower-level providers require several
  Activities.
- **Primary semantic Activity** answers **what Chromie is doing**: greet Alice,
  tell a joke, walk forward, sing a song, hand over water, show/play something.
  This concrete Work/Plan act is the Social Attention anchor.
- **Activity Execution Lane** is the maintained runtime lane for non-Vocal
  Capability execution. It is an implementation mechanism, not an Activity
  ontology.
- **Vocal Expression** is one personal-voice realization family. Speaking is
  represented by `mode=speech`; expressive speech, recitation, singing, humming,
  and nonverbal vocalization are other modes. The **Vocal Execution Lane** runs
  those modes.

Therefore `speech`, `singing`, `body`, and `media` are not peer Primary-Activity
categories. A semantic greeting can be realized by Vocal Expression plus compatible
body work and still remain one greeting Activity. Independent semantic `walk` and
`sing` responsibilities remain distinct Activities even when their execution lanes
overlap in time.

This is not a second brain, a second planner, or a provider-selection shortcut.
Goal meaning, Goal Association, planning, and response meaning remain owned by
the one Cognitive Core. Social Attention cannot author response text, create a
Goal, own completion, or enter lane coordination.

The current source can start eligible requests concurrently inside the Trusted
Capability Runtime, but its maintained coordinator still aggregates terminal results
behind the originating execution call. The approved `CapabilityRuntime` target removes
that batch-completion barrier: each request has an independent asynchronous lifecycle and
publishes correlated runtime events as progress or terminal results arrive. This does not
create another execution lane or change semantic Activity ownership. A synchronized
cross-provider start barrier, atomic multi-provider cancellation, and verified temporal-
overlap evidence still require explicit provider/runtime contracts and are not implied by
ordinary asynchronous dispatch.

## Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Cognitive Core / primary Planner | user meaning, Goal lifecycle, Main Activities, response meaning, temporal intent, and optional auxiliary decoration in one Plan result | motor control, provider internals |
| Vocal Execution Lane | realization of one personal `Vocal Expression`: speaking (`mode=speech`), expressive speech, recitation, singing, humming, nonverbal vocalization; playback/interruption/cancellation/output ordering | independent personality, semantic Primary-Activity meaning, or existing-media lifecycle ownership |
| Activity Execution Lane | non-Vocal provider calls, primary execution work, optional Social Attention body decoration, asynchronous lifecycle monitoring, cancellation, recovery, and correlated outcome collection | Goal or semantic Primary-Activity meaning, or raw motor control |
| Soridormi | embodied feasibility, body arbitration, safety supervision, controller execution, stop, recovery, and physical evidence | conversational meaning or provider selection |

The Activity lane executes work; it does not own Goals. Optional Social
Attention decoration also executes through Activity, but carries
`auxiliary_plan_activity=true` and `execution_role=social_decoration` so it
cannot be mistaken for primary completion work. Vocal delivers Chromie-authored
personal voice output; it is not a separate conversational agent.

## Planner-owned Social Attention

Fast Advance and canonical Fast/Deep Planner calls may author bounded
`auxiliary_activities[]` beside their Main Activities. Fast First Response has no
auxiliary surface. Empty output is normal. There is no later social model call or
event-driven reconsideration solely because an Activity becomes ready, target evidence
changes, or execution completes.

Fast understanding, Goal Association, provider readiness, Evidence arrival, and
Vocal/Activity lane transitions are **not anchors**. Only a human-observable
Planner-authored Communicative Act, Plan response, or Plan step can be an anchor.
A decoration is useful only when it supports that Activity and remains small,
non-disruptive, interruptible, optional, and subordinate.

Social Attention must not become a generic idle-animation loop. A blink attached to
an active Main Activity may be decoration; an autonomous idle blink with no interaction
anchor belongs to baseline embodiment/liveliness.

The same Fast/Deep Planner primary result is the single semantic writer for optional
decoration, exact wording, speech acts, and Vocal style. Runtime validates and
materializes the exact auxiliary proposal through Activity; it may suppress but never
reselect or retarget it. Eligible candidates are decoder-constrained from the live
catalog. Trusted code checks arguments, target evidence, resources, safety, provider
availability, and concurrency without reconstructing controller policy.

Optional decoration fails soft with respect to primary work. An invalid, stale,
unavailable, conflicting, or rejected auxiliary proposal must not delay ready Vocal or
Activity work and must not change Goal truth. Auxiliary-only changes/results cannot
construct a Goal-scoped `CognitiveOpportunity`.

Example:

```text
Goal: greet Alice
  -> Vocal says "Hello!"
  -> the same Planner result may optionally propose look/blink/small wave
       -> accepted decoration executes as auxiliary Activity
       -> decoration failure does not make the greeting Goal false
```

If the user explicitly asks "blink twice", that blink is instead primary
Activity responsibility. The physical Capability may be the same; the semantic
role and completion authority are not.

Social meaning may coexist with that exact responsibility. For "blink twice and
be cute", Core still owns the two required blinks. The primary Planner
may use the supplied playful framing to propose one different compatible cue;
it may not issue another blink, change the count, replace the primary action, or
claim its completion. Trusted Runtime rejects duplicate Capability IDs and
declared resource/exclusive-group conflicts. When the request is exact-only,
calls for stillness, lacks sufficient social support, or has no compatible cue,
the auxiliary decision is `none`.

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
Canonical Plan already exists. It coordinates only the two execution lanes:
Vocal and Activity. It does not create capabilities, authorize an effect, or
represent Social Attention.

```json
{
  "coordination_id": "performance_1",
  "relation": "parallel",
  "lanes": ["vocal", "activity"],
  "activity_step_ids": ["step_walk"],
  "start_policy": "best_effort_parallel",
  "failure_policy": "independent",
  "reason_summary": "Walk while speaking."
}
```

The participating response stage may copy the same identifier:

```json
{
  "text": "我来啦。",
  "speech_act": "inform",
  "commitment_state": "in_progress",
  "must_not_claim_completion": true,
  "covers_goal_ids": ["goal_walk"],
  "coordination_id": "performance_1",
  "delivery_role": "activity_companion"
}
```

An auxiliary Social Attention decoration does **not** join that coordination group and does
not carry `coordination_id`:

```json
{
  "capability_id": "soridormi.blink_eyes",
  "args": {"count": 1},
  "timing": "parallel",
  "social_function": "engagement"
}
```

If accepted, the Host materializes that body decoration as auxiliary Activity.
Actual overlap with primary body realization through the Activity Execution Lane is then decided mechanically from the
runtime batch and provider concurrency/safety declarations. Cross-lane
coordination IDs are not reused as embodied-provider grouping semantics.

The referenced Canonical Plan Activity steps must already use
`timing=parallel`. The Host cannot convert a sequential primary step
into a parallel one.

## Playback and confirmation rules

Ordinary pre-action acknowledgement remains playback-barriered:

```text
say “我准备开始了”
→ playback starts
→ effectful activity may begin
```

Speech participates in Activity overlap only when the Planner explicitly marks
it with a coordination group and
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

Optional Social Attention is likewise not execution authority. A malformed or invalid
`auxiliary_activities[]` proposal is suppressed at the bounded Runtime boundary.
Runtime cannot replace it, and decoration cannot fall back to changing
speech text. Dropping optional decoration leaves the immutable Vocal/Activity
work unchanged.

Eligible `tool`, `robot_action`, and `deep_thought` fast acknowledgements receive
an independent semantic review before playback. Persona may shape wording but
may not invent another errand, destination, person, object, household activity,
unsupported ability, or external result. Tool speech is restricted to the typed
`acknowledge_and_check`/`checking_only` act; memory speech remains suppressed
until commit. The Host may use its bounded low-commitment generic cache for any
suppressed, unavailable, or invalid dynamic acknowledgement.

## Runtime behavior

The maintained runtime:

1. validates Vocal/Activity coordination references and lane membership;
2. requires referenced primary Activity steps to be parallel Canonical Plan steps;
3. keeps ordinary pre-action speech behind the playback-start barrier;
4. runs Vocal and Activity work as a best-effort parallel batch;
5. materializes accepted Social Attention body decoration as auxiliary Activity
   with no Goal-completion authority;
6. groups compatible same-provider Soridormi body members from the actual
   parallel runtime batch into one deterministic embodied compilation and
   execution, independent of cross-lane coordination IDs;
7. requires provider concurrency metadata and safety validation for body overlap;
8. maps Soridormi aggregate member evidence back to original request identities
   while preserving primary-versus-decoration semantics; and
9. reconciles each Goal only from its own capability-specific outcome evidence.

Cross-provider Vocal/body start remains best-effort. Inside Soridormi, body
members are compiled and cancelled as one provider-local physical activity. A
future cross-provider contract may add prepared states, a shared monotonic start
barrier, measured overlap, and explicit degraded/optional outcome vocabulary.

## Typed Goal WHAT contract and execution projection

Canonical Goals do not persist execution-lane or provider-requirement metadata. Their
model-authored modality is the provider-neutral human outcome:

```text
output_mode  speech | styled_speech | recitation | singing | humming
             | nonverbal_vocalization | body_action | media_playback
             | information | stateful_effect | other
media_operation  play | pause | resume | seek | stop | volume | status | none
```

`media_operation` is meaningful only for `media_playback`. Goal Association preserves
these WHAT facts and semantic bindings; it does not decide Capability, Provider, Work,
execution lane, or fresh-Evidence need. Planner projects the current Goal into HOW using
trusted state/Evidence and the current Capability catalog. Ordinary `speech` may be a
direct Communicative Activity. Provider-backed vocal modes require an exact advertised
`chromie.vocal.perform` mode. `body_action`, `media_playback`, and `stateful_effect` require
a real effectful Capability or an explicit blocked outcome. `information` may be answered
from already trusted evidence/context; when represented as an information
`resource_responsibility`, factual completion requires trusted acquisition/retrieval
Evidence.

Execution lanes belong to selected Capability/Activity realization and Runtime
coordination, not to the Goal. This keeps WHAT stable even when a provider changes or a
future provider makes a formerly complex workflow atomic.

## One personal voice

`Vocal Expression` is Chromie's one personal-voice expression domain, realized
through the Vocal Execution Lane:

```text
Vocal Expression
├── mode=speech
├── mode=styled_speech
├── mode=recitation
├── mode=singing
├── mode=humming
└── mode=nonverbal_vocalization
```

These are expression **modes**, not sibling semantic Primary Activities. The semantic
Activity remains what Chromie is doing—for example tell a joke, sing a song, recite
a poem, or greet Alice. Different Activities may choose different Vocal modes as part
of their realization, but all personal Vocal modes share one execution-time resource:

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
and it is not identical to the physical speaker. Existing-media playback is realized
through the Activity Execution Lane, not through personal Vocal Expression. A qualified
mixer may overlap Media realization and Vocal work under `duck_media_during_vocal`.

Ordinary TTS historically released its runtime request at `playback_started`,
while PCM continued playing. The maintained playback lifecycle therefore exposes
a separate terminal voice-release fact. Compatible body work through the Activity
Execution Lane may still begin at the playback-start barrier, but a following Vocal
mode cannot acquire `chromie.voice` until prior TTS has actually stopped producing
Chromie's voice.

## Existing media playback

Playing existing music, recordings, streams, or sound effects is work realized through
the Activity Execution Lane, not authored Vocal Expression. A qualified peer provider exposes only the
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
provider steps, while `activity_step_ids` binds Activity work. Planner may
coordinate both in one parallel group, but neither it nor the Host may relabel the vocal step
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
