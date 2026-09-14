# Execution Lanes and Coordination

## Status

The [Social Cognition target](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
owns communication and optional social expression; Work Planner owns requested
work. The owner authorized scheduler alignment on 2026-09-14. The existing
Trusted Capability Runtime now keeps separate Vocal and Activity waiting queues
under one resource/safety arbiter. With total capacity greater than one, one slot
is reserved for Vocal; Activity can use the remaining slots concurrently. At a
configured total of one, execution is necessarily serial. Eligible waiters retain
FIFO order within their lane; resource-blocked work holds no partial reservation.

The [Project Charter](PROJECT_CHARTER.md) remains the authoritative main workflow.
These are execution mechanisms below semantic Activities, not separate minds:

```text
SC / Work Planner author exact acts and temporal relationships
  -> Trusted Capability Runtime
       -> Vocal queue: ordered personal voice
       -> Activity queue: compatible non-Vocal providers
            -> Soridormi owns embodied preparation, execution and safety
       -> one arbiter reserves capacity and exact resources across both queues
```

`prepared_start` coordinates declared members after their preparation boundaries.
Ordinary independent tasks remain independently schedulable. Social Attention is
a behavior domain expressed through Activity, not a third execution lane.

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

## Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Work Planner | requested work, exact Capability selection, temporal intent and Goal coverage | SC wording, motor control or provider internals |
| Social Cognition | communication, silence and optional social expression in its primary result; exact observable act anchors | rewriting Work or claiming unobserved completion |
| Vocal lane / Host | personal voice preparation, ordered playback, interruption and delivery evidence | conversational meaning |
| Activity lane / Runtime | provider lifecycle, resource admission, coordinated release and correlated outcomes | Goals or raw motor control |
| Soridormi | embodied feasibility, compilation, safety supervision, execution, stop and recovery | conversational meaning or cognitive provider selection |

## Social Attention

SC may author `auxiliary_activities[]` attached to its exact observable
Communicative Act. Empty output is normal; a nonverbal act may have no speech.
The Host materializes that result in the same InteractionResponse as its anchored
speech, without a decoration-only model call. It validates catalog grounding,
arguments, target evidence, freshness, resource compatibility and safety; it may
suppress the exact proposal but never replace or retarget it.

Accepted decoration carries `source=social_cognition_auxiliary_activity`,
`semantic_owner=social_cognition`, `auxiliary_plan_activity=true` and
`execution_role=social_decoration`, with no Goal ownership. A requested blink is
primary work even if it uses the same provider Capability. Optional decoration
cannot satisfy or change a Work Goal and its terminal result goes to the social
interaction ledger. An unavailable optional provider leaves anchored speech
eligible, with the failed admission retained explicitly.

Social Attention is not an idle-animation loop. An autonomous blink without a
social interaction anchor belongs to baseline embodiment. GI/GA execution and
provider transitions are evidence for SC consideration, not themselves observable
act anchors. Situation-triggered SC uses the same materialization and freshness
checks as other SC entry points.

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

When an independent best-effort batch contains multiple exact Soridormi body capabilities, the
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
make Social Attention a third lane.

```json
{
  "coordination_id": "performance_1",
  "relation": "parallel",
  "lanes": ["vocal", "activity"],
  "activity_step_ids": ["step_walk"],
  "start_policy": "prepared_start",
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

An accepted SC auxiliary expression uses the same Runtime coordination identity
as its exact anchored speech. The Host derives that identity from the SC request
and immutable act anchor; it does not infer a relationship from wording. This
identity is not Soridormi body-compilation authority. Wordless expression enters
Activity directly without inventing a Vocal member.

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

Response presentation and optional Social Attention are not execution authority.
Invalid optional decoration is suppressed with a retained reason; it cannot alter
speech or the immutable Work Plan. Canonical Charter principles 30–31 govern
semantic ownership and forbid a second semantic review/repair invocation.

## Runtime behavior

For `prepared_start`, Runtime validates exact contiguous parallel membership and
provider readiness support, then atomically admits required members across lanes
with all declared resources. An optional SC member joins only if compatible
capacity/resources are immediately available. It cannot delay required admission.

Local speech readiness means first nonempty PCM and output preparation; Soridormi
readiness means a created plan, safety monitoring and accepted confirmation or
trusted low-risk SC preflight. Neither readiness event is user-visible completion.
Required members wait at one Host monotonic release barrier. Optional members
still unready at release are omitted; required preparation failure prevents every
member from beginning. Unsupported providers fail explicitly rather than silently
running without the declared timing contract.

After release, members complete and free their own slots/resources independently.
Cancellation and timeout retain existing provider safety ownership. A required
member failure after release does not undo another member's effects; there is no
atomic distributed rollback. Each result retains readiness/release evidence,
omission/error information and its original request identity. Actual playback and
provider terminal evidence remain separate from the release event.

The initial prepared-start adapters cover Host speech and individual Soridormi
plans. Other adapters, including the generic Vocal-performance backend, require
an explicit preparation boundary before they can join. Conflicting simultaneous
body plans fail closed; no physical WorkDAG parallelism is introduced. Independent
best-effort body batches retain Soridormi's existing provider-local compilation.

The common release is a Host scheduling guarantee, not proof of identical physical
onset, equal duration or word/gesture alignment. Device/network latency and physical
onset tolerance need separately retained target measurements. `best_effort_parallel`
remains an explicit weaker overlap policy and carries no prepared-start guarantee.

Current evidence is retained in `.chromie/acceptance/lane-coordination-20260914/`.
The bound controlled speech+blink proof records a 719 ms difference in preparation
readiness followed by one shared Host release, both terminal completions and safe
idle. It uses real TTS with discarded PCM and a deployed simulator, not native SC
inference or physical observation. See [Status](STATUS.md) for broader verification
and unresolved native-model failures.

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
Independent submissions acquire the complete declared resource set at that same
boundary. Compiled provider groups reserve every member's claims and exclusive groups,
so compilation cannot bypass another interaction's claim. Exact names, waiting and
cancellation are defined by the [shared arbiter contract](../shared/README.md#chromie_runtime).

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
