# Social Attention Behavior Domain

## Decision

Social Attention is a high-level interaction behavior domain, not one fixed
skill, not a phrase-to-action routing rule, and not a deployment-backend policy.
During interaction, the model may coordinate context-appropriate language
expression, gaze, blink, nod, head orientation, posture, another
catalog-supplied behavior, or no expression.

Chromie decides whether a social expression is appropriate, what social purpose
it serves, and how strong it should be. Soridormi decides how the currently
attached body realizes the selected named skill.

The deterministic host never maps phrases such as "pay attention" or "I am
sad" to a fixed gesture. It supplies bounded interaction context, the
owner-approved mind profile, and the eligible semantic capability catalog, then
validates the model-authored plan.

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
  chooses an optional semantic social behavior
  submits the named skill and semantic arguments
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

A capable simulator should preserve the same named-skill semantics, observable
behavior, and execution-result contract expected from a commissioned physical
provider. Moving from simulation to hardware should therefore change the
Soridormi backend, controller, calibration, and safety envelope, not Chromie's
social reasoning or plan shape.

## Social interaction style belongs to the mind

How frequently Chromie uses Social Attention should come from the
owner-approved mind profile and the current interaction, not from the execution
environment.

The accepted target model is an owner-approved social interaction style with
continuous tendencies such as:

- `courtesy`: willingness to acknowledge, attend, thank, apologize, and defer;
- `expressiveness`: overall strength and frequency of visible social cues;
- `initiative`: willingness to add an unrequested but useful auxiliary cue;
- `restraint`: preference for stillness when a cue would be repetitive,
  distracting, or artificial;
- cooldown and repetition limits that keep behavior natural.

Named presets may be offered as profile authoring conveniences:

| Style | Typical behavior |
|---|---|
| `courteous` | More acknowledgement, gaze, light nods, and context-sensitive expression, while respecting cooldown and urgency. |
| `neutral` | Social cues at important conversational moments, but not on every turn. |
| `reserved` | Rare auxiliary body expression; stillness is normally preferred. |

These are personality tendencies, not deterministic gesture tables. Even a
courteous profile may choose `none`, and an urgent stop or safety turn must
suppress decorative expression.

The shared `MindProfile.social_interaction_style` contract now carries bounded
courtesy, expressiveness, initiative, restraint, cooldown, and repetition
guidance. It remains owner-approved configuration rather than
experience-auto-mutable behavior.

## Two interaction roles

### Explicit user goal

When the user requests a concrete action, for example "blink twice" or "look at
me for two seconds", that action remains a normal CanonicalPlan goal. It is not
optional and cannot be replaced with a different social gesture.

The behavior may still be classified in the `social_attention` domain for
observation and analysis, but its interaction role is
`explicit_user_goal`.

### Auxiliary expression

When the model adds language style or body expression to support the
interaction, the role is `auxiliary_expression`. It is advisory, lower priority
than the user task, and may be dropped on target uncertainty, resource conflict,
confirmation requirements, invalid parameters, latency pressure, emergency
priority, or repetition/cooldown policy.

Auxiliary expression can never satisfy, replace, delay, or claim completion of a
user goal.

## Model-owned plan

The model authors:

- the social purpose, such as listening, empathy, acknowledgement, engagement,
  turn taking, deference, or neutral presence;
- whether expression is useful for this turn;
- language style and pacing adaptation;
- zero or more exact capability IDs from the supplied candidates;
- capability arguments, timing, social function, target selection, and
  schema-valid semantic intensity parameters such as amplitude or duration.

The model should consider the owner-approved interaction style together with:

- the current speech act and relationship context;
- user affect and engagement evidence;
- conversation phase and turn-taking state;
- primary task urgency and resource needs;
- recent auxiliary behaviors, cooldown, and repetition;
- currently available semantic capabilities and target evidence.

A plan may use body expression, speech adaptation, both, or neither. The
Response Composer owns coordination of the actual response text and auxiliary
body plan so they express one coherent purpose. The standalone native
compatibility planner remains body-only and sets speech adaptation to `none`.

Current-compatible example shape:

```json
{
  "behavior_domain": "social_attention",
  "interaction_role": "auxiliary_expression",
  "purpose": "acknowledgement",
  "decision": "express",
  "speech_expression": {
    "mode": "adapt",
    "style": "warm",
    "pacing": "normal",
    "reason": "Acknowledge the greeting naturally."
  },
  "behaviors": [
    {
      "skill_id": "soridormi.nod_yes",
      "args": {"count": 1, "amplitude": 0.3, "duration_s": 1.0},
      "timing": "parallel",
      "social_function": "acknowledge"
    }
  ]
}
```

## Capability discovery

Capabilities declare one or more behavior domains. The checked-in
`capabilities/behavior_domains.json` supplements the semantic taxonomy for
current Soridormi named skills. Candidate discovery selects available,
interaction-executable catalog entries tagged `social_attention` without using
simulator or hardware provider metadata.

`AGENT_SOCIAL_ATTENTION_CAPABILITIES` is an optional operator allow-list or
extension, not the primary fixed candidate list. Its default is empty.

A capability may belong to multiple domains. A head turn can express social
attention, perception, navigation, or safety depending on the model-authored
purpose and owning task. Capability taxonomy does not decide the plan.

Candidate discovery may use semantic capability identity, availability,
interaction executability, schema, resource, and confirmation metadata. It must
not filter candidates because a provider is labelled `sim`, `hardware`, or any
other deployment backend.

## Host authority

The host may:

- validate exact catalog membership and argument schemas;
- verify target evidence;
- enforce confirmation and safety policy;
- reject low-level motor fields;
- detect resource conflicts with the primary plan;
- cap auxiliary behavior count;
- apply emergency and latency suppression;
- require auxiliary body requests to remain parallel and conflict-free;
- drop invalid auxiliary expression;
- record accepted-request evidence separately from execution and user outcomes.

The host may not:

- inspect user phrases to select a social skill;
- replace an explicit requested action;
- generate a gesture sequence from a social purpose;
- invent a conversational answer or emotional interpretation;
- let auxiliary expression delay speech, emergency handling, or the user task;
- select, suppress, or authorize Social Attention because the active body is a
  simulator or a physical robot.

## Soridormi authority

Soridormi owns:

- simulator-versus-physical backend selection;
- semantic-skill implementation for the attached body;
- controller and model selection;
- calibration and body-specific parameter conversion;
- joint, velocity, acceleration, force, and torque limits;
- collision, balance, stop, emergency-stop, recovery, and safe-idle behavior;
- provider health and execution evidence.

A physical provider may clamp or reject an otherwise valid semantic request
when the body cannot execute it safely. That is a provider execution result, not
an alternate Chromie cognition mode.

## Runtime policy

| Mode | Meaning |
|---|---|
| `off` | Owner-selected or diagnostic suppression; do not plan auxiliary Social Attention. |
| `report_only` | Compose and retain advisory evidence, but do not materialize auxiliary body requests. |
| `on` | Compose and, after normal validation, materialize optional auxiliary Social Attention. |

The maintained default is `on`. A legacy simulator-scoped environment value is
normalized to `on` at the configuration boundary because body-backend selection
belongs to Soridormi/provider. Unknown explicit values fail closed to `off`.
Contextual model selection may always produce `decision=none`.

## Implemented closure

The implementation now:

1. exposes only `off`, `report_only`, and `on` in the public contract;
2. supplies owner-approved Social Interaction Style and bounded recent accepted
   auxiliary-request evidence to Response Composer;
3. discovers and validates candidates without inspecting provider backend mode;
4. accepts installation calibration only when a provider supplies it as explicit
   target evidence;
5. requires auxiliary body requests to use `timing=parallel`, need no user
   confirmation, and avoid primary resource conflicts;
6. preserves explicit user actions as CanonicalPlan goals and never treats
   auxiliary requests as completion evidence;
7. keeps named-skill IDs and semantic argument schemas stable across Soridormi
   backends; and
8. leaves controller adaptation, calibration, motion limits, collision safety,
   stop, recovery, safe idle, and execution evidence below the Chromie boundary.

Automated contract and file-backed parity coverage is included. Retained live
provider-backed qualification remains separate evidence work.

## Testing

Black-box tests classify both explicit and auxiliary actions in the stable
`social_attention` observation domain while preserving their different
interaction roles. The same named-skill and semantic-argument scenario must
remain invariant when provider backend metadata changes. Abstract requests such
as "show that you are listening" should be judged for contextual appropriateness
without requiring one specific skill. Concrete requests such as "blink twice"
require the exact observable count and remain primary goals.

Backend-invariance tests should run the same semantic catalog and interaction
context with different provider deployment metadata and require the same
Chromie plan. Soridormi-specific tests then verify that each backend realizes or
safely rejects the semantic request according to its own controller and safety
contract.
