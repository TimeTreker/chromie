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

The exact structured fields will be implemented in the shared `MindProfile`
contract. They remain owner-approved configuration rather than
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
`capabilities/behavior_domains.json` supplements provider metadata for current
Soridormi skills. Candidate discovery selects available,
interaction-executable catalog entries tagged `social_attention`.

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
- apply emergency, latency, cooldown, and repetition suppression;
- drop invalid auxiliary expression;
- record execution and user-outcome evidence.

The host may not:

- inspect user phrases to select a social skill;
- replace an explicit requested action;
- generate a gesture sequence from a social purpose;
- invent a conversational answer or emotional interpretation;
- let auxiliary expression delay or override the user task;
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

## Runtime policy target

The accepted target runtime gate is:

| Mode | Meaning |
|---|---|
| `off` | Diagnostic or owner-selected suppression; do not plan auxiliary Social Attention. |
| `report_only` | Plan and retain advisory evidence, but do not materialize auxiliary body skills. |
| `on` | Plan and, after normal validation, materialize auxiliary Social Attention. |

The maintained default should become `on`. Contextual selection may still
produce `decision=none`.

The current implementation still accepts `sim_only` and defaults to `off`.
That is now explicit architecture debt. The new implementation topic will remove
`sim_only`, remove provider-mode filtering from Chromie's Social Attention path,
change the maintained default to `on`, and fail clearly on stale `sim_only`
configuration rather than silently preserving the wrong ownership model.

## Open implementation topic

**Topic:** Embodiment-independent Social Attention and personality policy.

The implementation sequence is:

1. Simplify the policy contract to `off`, `report_only`, and `on`; remove
   `sim_only` from shared literals, launch configuration, Agent policy context,
   Response Composer validation, Host materialization, and tests.
2. Change the maintained Social Attention default from `off` to `on`; retain
   `off` and `report_only` for diagnostics, owner preference, and controlled
   comparisons.
3. Add an owner-approved social interaction style to `MindProfile`, including
   bounded courtesy, expressiveness, initiative, restraint, and repetition or
   cooldown guidance.
4. Supply that style and recent auxiliary-behavior evidence to Response
   Composer without introducing phrase rules or fixed gesture mappings.
5. Keep candidate discovery semantic and backend-independent; remove
   `metadata.mode=sim` eligibility checks from Chromie.
6. Keep simulator/physical selection and body-specific safety entirely in
   Soridormi/provider configuration.
7. Add scenario, contract, and end-to-end tests for personality tendencies,
   contextual `none`, emergency suppression, repetition control, explicit-goal
   priority, and backend invariance.
8. Retain live interaction evidence showing that the same Chromie plan contract
   works through the currently configured Soridormi backend.

## Acceptance criteria

The topic closes when:

- production Chromie configuration and policy schemas no longer contain a
  `sim_only` Social Attention mode;
- default startup enables Social Attention without a special architecture or
  simulator overlay;
- changing provider metadata between simulator and physical deployment does not
  change Chromie's candidate set or social plan when semantic capabilities,
  availability, and interaction context are otherwise identical;
- for capabilities exposed by multiple Soridormi backends, the same named skill
  and semantic arguments remain valid, with body-specific adaptation below the
  Chromie boundary;
- courtesy and expressiveness come from the owner-approved mind profile and
  influence model choice without becoming deterministic gesture frequencies;
- courteous, neutral, and reserved scenarios show different aggregate
  tendencies while every individual turn may still choose `none`;
- explicit user actions remain primary goals, emergency work suppresses
  auxiliary expression, and auxiliary behavior never delays first useful
  speech;
- automated contract, scenario, semantic-authority, documentation, and full
  regression gates pass;
- retained live evidence confirms contextually appropriate Social Attention and
  truthful execution reporting.

## Testing

Black-box tests classify both explicit and auxiliary actions in the stable
`social_attention` observation domain while preserving their different
interaction roles. Abstract requests such as "show that you are listening"
should be judged for contextual appropriateness without requiring one specific
skill. Concrete requests such as "blink twice" require the exact observable
count.

Backend-invariance tests should run the same semantic catalog and interaction
context with different provider deployment metadata and require the same
Chromie plan. Soridormi-specific tests then verify that each backend realizes or
safely rejects the semantic request according to its own controller and safety
contract.
