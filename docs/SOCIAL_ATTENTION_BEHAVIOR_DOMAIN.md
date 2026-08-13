# Social Attention Behavior Domain

## Decision

Social Attention is Chromie's background social-decoration cognition.

It does **not** decide the primary thing Chromie is trying to accomplish. It
may add small, optional, non-disruptive embodied cues around an interaction that
is already happening so that the same primary behavior feels socially present
rather than mechanically isolated.

A greeting illustrates the boundary:

```text
Primary responsibility
  greet Alice
    |
    +-- Vocal: "Hello!"
    |
    `-- optional Social Attention decoration
          +-- look toward Alice
          +-- natural blink
          +-- small nod / wave
          `-- slight posture or body orientation
```

The greeting remains the greeting. Social Attention does not rewrite the text,
create another Goal for the blink, or make the greeting incomplete when an
optional decoration cannot run.

In this document, **decoration** means semantic subordination, not meaningless
random animation. A decoration is socially contextual, attached to a real
interaction state, and lower priority than the responsibility it accompanies.

## Core invariants

Social Attention obeys all of the following:

1. **Not a Goal.** It does not create a user-facing Goal or Responsibility.
2. **Not an execution lane.** Chromie's maintained execution lanes are Vocal
   and Activity. Accepted Social Attention body requests execute through
   Activity.
3. **Not a speech owner.** It never authors, rewrites, paraphrases, or changes
   the semantic content of ResponsePlan/Vocal output.
4. **Anchored.** A decoration must accompany a meaningful social interaction
   state such as listening, speaking, ongoing Activity, turn-taking, waiting in
   an active interaction, or another evidence-backed social event. It does not
   manufacture standalone work merely so that Chromie can move.
5. **Small and non-disruptive.** Typical candidates are gaze, blink, a small
   nod, a small wave, a smile when supported by embodiment, or slight posture /
   body orientation. The live capability catalog remains authoritative.
6. **Optional and fail-soft.** Invalid, slow, unavailable, conflicting, or
   unnecessary decoration is dropped. It must not delay, replace, cancel, or
   fail the primary behavior.
7. **Interruptible and subordinate.** Emergency handling, explicit user
   actions, confirmation, Vocal delivery, and primary Activity always have
   priority.
8. **No completion authority.** Decoration evidence can say that a decoration
   ran; it cannot satisfy or prove completion of the primary Goal.

A socially important event that genuinely changes what Chromie should do next
is no longer merely decoration. It must be elevated through normal Cognitive
Core / Goal reasoning rather than smuggled into `SocialAttentionPlan`.

## Same motion, different semantic role

The semantic role comes from **why the motion exists**, not from the actuator or
Capability ID.

```text
User: "Blink twice."
  -> Activity responsibility
  -> required CanonicalPlan work
  -> completion-relevant evidence

Chromie greets someone and naturally blinks
  -> Social Attention decoration
  -> optional Activity execution
  -> no Goal completion authority
```

Both paths may eventually use the same qualified `soridormi.blink_eyes`
Capability. The first is requested work; the second is auxiliary social
appearance. Trusted metadata and reconciliation must preserve that distinction.

### Explicit action plus social framing

An explicit body request stays exact primary Activity even when its wording also
suggests a social purpose. Social Attention may reason over that supplied
meaning, but it cannot reinterpret, replace, or embellish the required action
itself.

For example:

- "Blink twice" requires exactly the primary blink work. If the surrounding
  interaction merely looks like a capability test, stillness around it may be
  the most natural Social Attention decision.
- "Blink twice and be cute" still requires exactly two primary blinks. The
  playful framing may support one **different**, compatible auxiliary cue, such
  as a small head tilt or nod, when an eligible Capability, owner-approved style,
  recent-decoration evidence, and resource policy all support it.
- "Do something cute" does not specify a required motion. It belongs in normal
  Cognitive Core / Goal reasoning, which may choose the primary behavior; it is
  not reduced to optional Social Attention decoration.

The model owns this semantic judgment from the utterance and supplied Core
context. The Host does not map words such as "cute" to a gesture. Trusted code
only guarantees containment: an auxiliary proposal cannot duplicate a primary
Capability, change its arguments or completion meaning, or overlap an exclusive
group/resource. Explicit exact-only action, stillness, emergency state,
incompatibility, repetition, or weak contextual support resolves to no
decoration. A pleasant surprise therefore means bounded contextual variation,
not a random extra movement.

## Interaction anchor versus idle embodiment

Social Attention is not a generic idle-animation system.

A blink while Chromie is actively listening can be Social Attention because it
belongs to a live social interaction. A purely autonomous blink while no social
interaction exists may still be desirable for embodiment realism, but that is a
separate baseline embodiment/liveliness concern and must not be represented as a
fake Social Attention Goal or event.

This prevents Social Attention from degrading into random gesture generation.
The model should be reasoning about a social situation, not decorating elapsed
time.

## Embodiment-independent boundary

Chromie's cognitive and interaction layers must not distinguish a simulator
from a physical robot. For Chromie, a named ability such as
`soridormi.nod_yes`, `soridormi.look_at_person`, or
`soridormi.blink_eyes` has one semantic contract regardless of the provider
backend.

The boundary is:

```text
Chromie
  understands the interaction
  decides whether a small social decoration is useful
  selects an eligible semantic body Capability
        |
        v
Trusted Capability Runtime
  validates schema, availability, policy, resources, and priority
        |
        v
Soridormi
  selects the configured simulator or physical provider
  converts semantic arguments into body-specific control
  applies calibration, limits, collision checks, stop, and recovery
```

Simulation and physical deployment may appear in provider diagnostics, runtime
traces, commissioning configuration, and Soridormi safety logic. They must not
appear as a Social Attention decision dimension, candidate-selection rule,
model prompt preference, or personality mode inside Chromie.

Moving from simulation to hardware should change the Soridormi backend,
controller, calibration, and safety envelope, not Chromie's Social Attention
meaning or plan shape.

## Social interaction style belongs to the Mind

How frequently Chromie adds social decoration comes from the owner-approved
Mind profile and current interaction, not from the execution environment.

The shared Social Interaction Style carries tendencies such as:

- `courtesy`: willingness to acknowledge, attend, thank, apologize, and defer;
- `expressiveness`: overall strength and frequency of visible social cues;
- `initiative`: willingness to add an unrequested but useful small cue;
- `restraint`: preference for stillness when a cue would be repetitive,
  distracting, artificial, or unnecessary;
- cooldown and repetition limits that keep behavior natural.

Named presets remain profile-authoring conveniences through
`ORCH_SOCIAL_INTERACTION_STYLE_PRESET`:

| Style | Typical decoration behavior |
|---|---|
| `courteous` | More context-appropriate gaze, light nods, and acknowledgement cues while respecting urgency and cooldown. |
| `neutral` | Small cues at meaningful conversational moments, not every turn. |
| `reserved` | Rare auxiliary body decoration; stillness is usually preferred. |

These are tendencies, not gesture tables. Even a courteous profile may choose
`none`, and emergency or safety work suppresses decoration.

The style influences whether and how strongly Chromie decorates the interaction.
It does **not** give Social Attention ownership of response wording. Vocal style,
word choice, personality expression, and conversational semantics remain with
the applicable cognitive/response owner.

## Model-owned decoration plan

`SocialAttentionPlan` is advisory and body-only. The model decides:

- whether a decoration is useful for the current anchored interaction;
- its social purpose, such as listening, acknowledgement, engagement, empathy,
  turn-taking, deference, or neutral presence;
- zero or more exact body Capability IDs from the supplied candidates when
  `decision=none`, or at least one when `decision=express`;
- capability arguments, social function, target selection, and bounded semantic
  intensity parameters supplied by the public schema.

When primary Activity already owns an exact Capability, the model may select
only a different compatible auxiliary candidate. Selecting none remains valid
and often preferable.

It does **not** decide speech text, speech style fields, user Goal meaning,
provider identity, or motor implementation.

Example:

```json
{
  "behavior_domain": "social_attention",
  "interaction_role": "auxiliary_expression",
  "purpose": "acknowledge",
  "decision": "express",
  "target": {
    "target_ref": "person:alice",
    "source": "conversation_context",
    "confidence": 0.9
  },
  "behaviors": [
    {
      "capability_id": "soridormi.nod_yes",
      "args": {"count": 1, "amplitude": 0.3, "duration_s": 1.0},
      "timing": "parallel",
      "social_function": "acknowledge"
    }
  ]
}
```

`interaction_role=auxiliary_expression` means auxiliary embodied expression in
this contract. It does not imply a second speech-expression channel.

## Capability discovery

Capabilities may declare one or more behavior domains. The checked-in
`capabilities/behavior_domains.json` supplements semantic taxonomy for current
Soridormi named skills. Candidate discovery selects available,
interaction-executable entries tagged `social_attention` without using
simulator or hardware-provider metadata.

`AGENT_SOCIAL_ATTENTION_CAPABILITIES` is an optional operator allow-list or
extension, not the primary fixed candidate list. Its default is empty.

A Capability may belong to multiple domains. A head turn can be an explicit
Activity responsibility, a perception behavior, or optional Social Attention
decoration depending on the owning intent. Capability taxonomy does not decide
that semantic role.

The model-facing projection removes provider backend identity and excludes
low-level calibration/control fields. Target evidence contains only semantic
identity and relative direction. Soridormi converts those semantics into
embodiment-specific controller values.

## Host and runtime authority

The Host / Trusted Capability Runtime may:

- validate exact catalog membership and argument schemas;
- verify target evidence;
- enforce confirmation, safety, and availability policy;
- reject low-level motor fields;
- detect resource and embodied-concurrency conflicts with primary Activity;
- reject an auxiliary Capability that duplicates explicit primary Activity;
- cap auxiliary behavior count;
- apply emergency, latency, cooldown, and repetition suppression;
- require Social Attention body requests to remain parallel and conflict-free;
- drop invalid optional decoration;
- record accepted-request and terminal decoration evidence separately from Goal
  completion.

The Host must not:

- inspect user phrases and map them to a fixed social gesture;
- replace an explicit requested action;
- generate a gesture sequence from a social-purpose string;
- invent response text or emotional interpretation for Social Attention;
- let decoration delay Vocal, emergency handling, or primary Activity;
- select, suppress, or authorize decoration because the active body is a
  simulator versus physical robot.

Materialized Social Attention body requests carry:

```text
execution_lane = activity
execution_role = social_decoration
auxiliary_social_attention = true
```

That metadata is the trusted distinction between optional decoration and a
primary Activity responsibility.

## Relationship to execution coordination

Chromie has two maintained execution lanes:

```text
Vocal
Activity
```

`LaneCoordinationGroup` coordinates only those two lanes. Social Attention never
appears in `lanes`, and a `SocialAttentionBehavior` never carries a
`coordination_id`.

When decoration is accepted, it becomes optional Activity work. If it overlaps
other body Activity, the Trusted Capability Runtime and provider concurrency
contract decide whether those exact body members may coexist. Compatible
same-provider Soridormi members are compiled as one provider-local physical
batch. This is body execution arbitration, not a third cognitive or execution
lane.

The Interaction Ledger may still retain a `social_attention` **event domain** so
later cognition can distinguish decoration evidence from primary Activity
evidence. That event-domain label is deliberately not an execution-lane label.

## Soridormi authority

Soridormi owns:

- simulator-versus-physical backend selection;
- semantic-skill implementation for the attached body;
- controller and model selection;
- calibration and body-specific parameter conversion;
- joint, velocity, acceleration, force, and torque limits;
- collision, balance, stop, emergency-stop, recovery, and safe-idle behavior;
- provider health and execution evidence.

A provider may clamp or reject an otherwise valid semantic decoration when the
body cannot execute it safely. That is a provider execution result, not an
alternate Chromie cognition mode.

## Runtime policy

| Mode | Meaning |
|---|---|
| `off` | Owner-selected or diagnostic suppression; do not plan auxiliary Social Attention. |
| `report_only` | Retain the advisory decoration decision/evidence, but do not materialize body requests. |
| `on` | After normal validation, materialize optional body decoration through Activity. |

The maintained default is `on`. Contextual model selection may always produce
`decision=none`.

## Testing and acceptance

Tests should prove the semantic boundary rather than one fixed gesture:

- `SocialAttentionPlan` cannot author speech-expression fields;
- Social Attention is absent from `ChromieExecutionLane`;
- `LaneCoordinationGroup` accepts Vocal/Activity only;
- materialized decoration uses Activity plus
  `auxiliary_social_attention=true`;
- decoration cannot satisfy primary Goal completion;
- explicit "blink twice" remains required Activity while an incidental blink is
  optional decoration;
- social framing may justify a different compatible cue but never a duplicate
  or mutation of the explicit action;
- a decoration conflict/failure does not fail unrelated primary work;
- backend metadata changes do not change Chromie's social decision semantics;
- target-specific decoration requires evidence for that target;
- repeated or unnecessary decoration may validly resolve to `decision=none`;
- same-provider body overlap is accepted or rejected by declared provider
  concurrency and safety, not by Capability-name heuristics.

See [Execution Lanes and Coordination](EXECUTION_LANES_AND_COORDINATION.md) for
the execution boundary and [Project Charter](PROJECT_CHARTER.md) for the
constitutional rule.
