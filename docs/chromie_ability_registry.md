# Chromie High-Level Ability Registry

Chromie's high-level ability registry is a static cognitive ontology. It names
responsibilities that Chromie can understand and describe; it is not an
execution catalog, a speech-template library, a body-backend selector, or a
second semantic router.

The registry is implemented in `orchestrator/runtime/abilities.py`.

## Status model

| Status | Meaning |
|---|---|
| `available` | The owning Chromie component exists and may participate when the normal cognitive and runtime contracts select it. |
| `stub` | The ontology entry has no implemented owner yet. |
| `planned` | The responsibility is reviewed but not implemented. |
| `known_missing` | Chromie understands the responsibility, but no trusted implementation exists. |
| `forbidden` | The responsibility must not be offered under current policy. |
| `disabled` | An implementation exists but is disabled by a runtime gate. |

`available` means only that the responsible component exists. It does **not**
authorize execution, select a Capability, generate wording, bypass
confirmation, or prove provider availability.

The ontology deliberately has no simulator-only or hardware-only state. Chromie
does not decide whether Soridormi is simulated or physical. Backend selection,
physical feasibility, collision safety, emergency stop, and recovery remain
Soridormi responsibilities.

## Responsibility map

The ontology groups stable responsibility names such as:

| Family | Examples |
|---|---|
| Cognition | turn interpretation, clarification, deep reasoning, task planning |
| Speech | pending acknowledgement, answer, confirmation, progress, failure |
| Memory | retain, recall, summarize, or explicitly reset session context |
| Social | attention, greeting, optional expression, gaze, nodding |
| Body | walking, turning, stop, posture, recovery |
| Manipulation | pick, place, handover |
| Navigation | follow, approach, go to a location |
| Environment | operate a door, light, or surface |
| Task | confirm, cancel, monitor, or execute through trusted boundaries |
| Safety | validate authority, refuse unsafe work, preserve stop priority |
| State | report runtime state or missing ability |

The entries describe **which component owns a responsibility**. They do not
contain user-facing templates, Provider arguments, calibrated motion values, or
fixed semantic routing rules.

## Speech ownership

The ontology never writes the sentence spoken to the user.

- pending acknowledgements are model-authored and validated against real pending
  work;
- normal answers, clarification, confirmation, progress, unavailable, and
  failure speech belong to Response Composer or the bounded model-owned speech
  path;
- a terminal missing-ability response is one complete model-authored conversational
  act: it first acknowledges the understood user outcome, then states the current
  capability limitation in Chromie's owner-approved voice, with a natural apology
  when appropriate. The Host does not prepend a fixed apology or rewrite the failure
  state. The response must not imply that a provider was queried, that execution was
  attempted, or that an empty result was observed;
- final factual speech waits for trusted Evidence;
- the Host may schedule, cancel, validate, and deliver speech, but it does not
  select wording from ontology templates.

## Static ontology versus live Capability catalog

```text
Static ability ontology
  -> names broad responsibilities and missing areas

Agent Skills
  -> teach optional reusable methods to LLM-driven Agents

Live Capability catalog
  -> supplies exact executable capability_id, schema, availability,
     confirmation, resources, and Provider provenance

Canonical Plan
  -> records the Agent's situation-specific decision

Trusted Capability Runtime
  -> validates and executes only registered Capabilities
```

A `known_missing`, `planned`, or `stub` ontology entry may help Chromie reason
honestly about an unsupported request, but it can never be sent to Trusted
Capability Runtime. Embodied work requires an exact live Provider Capability
and the normal Plan, authorization, confirmation, scheduling, runtime, and
Provider gates.

The Host does not infer body availability from dry-run mode, simulator identity,
hardware identity, or a launcher profile. See
[Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md).

A speech Capability is never a substitute for a missing substantive Capability.
`chromie.speak` can deliver a truthful limitation, but it cannot satisfy a request for
external retrieval, recommendation, navigation, manipulation, or another effect merely
by describing that request. The missing-ability terminal therefore carries no executable
actions.

## Fast response and Social Attention

Fast speech is model-authored from the current Goal and verified pending work.
The Host may validate truth, timing, and delivery barriers, but it does not map
routes to fixed acknowledgement sentences.

Optional Social Attention is selected separately by the model from the live
Capability catalog under the owner-approved interaction style. It remains
parallel-only, optional, and lower priority than emergency handling, speech, and
explicit user Goals. The ontology does not inject a fixed gesture when deep
reasoning starts.

Validate the maintained text-to-provider path with:

```bash
./scripts/run_voice_mujoco_text_case.sh --no-speaker "Please nod twice."
```
