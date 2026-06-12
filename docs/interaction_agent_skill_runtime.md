# Chromie-Soridormi Voice and Body Interaction Plan

Status: planned

Last reviewed: June 12, 2026

## Goal

Build the reusable interaction mainline in which a person speaks naturally and
the robot can answer through speech, body action, or both:

```text
microphone
  -> ASR
  -> Interaction Agent
  -> trusted Skill Runtime
  -> local speech and Soridormi body-skill providers
  -> speaker and robot
```

The first end-to-end acceptance example is:

```text
user: "hello"
robot: says "hello" and performs nod_yes
```

This is an acceptance example, not a special-case implementation. The same
contracts must support general requests such as looking, walking, stopping,
answering without motion, acting without speech, and asking for clarification.

## Ownership Boundary

Chromie is the robot brain. It owns:

- microphone session, VAD, interruption, ASR, TTS, and playback;
- conversation, memory, semantic intent, and high-level planning;
- selection of zero or more registered skills;
- coordination of speech and body skills;
- the trusted Skill Runtime, including validation, scheduling, cancellation,
  confirmation, and traces.

Soridormi is the robot cerebellum and body runtime. It owns:

- authoritative body-skill definitions and availability;
- body-skill argument validation and safety refusal;
- translation from named skills to bounded plans;
- MuJoCo or hardware execution, status, stop, and safe hold;
- low-level policy, controller, joint, and motor boundaries.

Chromie must never send raw joint targets, motor commands, or `action_14d`.
Soridormi must never receive raw natural language as a low-level control input.

## Target Architecture

```text
host microphone
  -> deterministic pre-router
       silence/noise handling
       interruption, stop, and emergency paths
  -> ASR
  -> Interaction Agent LLM
       understand intent
       generate natural-language reply
       select zero or more structured skills
  -> InteractionResponse
       speech[]
       skills[]
       coordination
  -> Chromie Skill Runtime
       schema and registry validation
       availability and precondition checks
       confirmation and safety policy
       scheduling, timeout, cancellation, and traces
  -> providers
       LocalSpeechSkillProvider -> TTS/playback
       SoridormiMcpSkillProvider -> MCP client
       CompositeSkillProvider -> registered compositions
  -> Soridormi MCP server
       named-skill validation and planning
       runtime-backed execution
       status, cancel, stop, and safe hold
  -> MuJoCo, then hardware after its separate safety gates
```

The MCP server remains part of the Soridormi deployment. Chromie's Skill
Runtime calls it through an MCP provider; it does not absorb the server or
Soridormi's execution authority.

## Interaction Agent

One capable LLM should own semantic understanding, conversation, routing, and
high-level skill composition. This component is called the Interaction Agent.
It replaces duplicate semantic decisions split between a small LLM router and a
talking LLM.

A deterministic pre-router remains necessary for operations that must not wait
for an LLM:

- silence and unusable audio;
- playback interruption and barge-in;
- explicit stop/cancel;
- emergency stop;
- service-unavailable fallback.

The Interaction Agent proposes an output. It does not directly invoke MCP,
hardware, or low-level actions.

## Interaction Contract

The response contract must represent speech only, action only, speech plus
action, clarification, refusal, and no response. A representative result is:

```json
{
  "speech": [
    {
      "text": "Hello, nice to see you.",
      "timing": "immediate"
    }
  ],
  "skills": [
    {
      "skill_id": "soridormi.nod_yes",
      "args": {
        "count": 2,
        "amplitude": "small"
      },
      "timing": "parallel"
    }
  ],
  "requires_confirmation": false
}
```

Required contract concepts:

- stable skill identifier and version;
- typed arguments;
- sequential or parallel timing;
- timeout and cancellation behavior;
- confirmation requirement;
- idempotency or request identity;
- result, refusal, failure reason, and trace identity.

Raw joints, motor commands, controller outputs, and `action_14d` are forbidden
fields at this boundary.

## Skill Registry

Chromie maintains the global registry used by the Interaction Agent and Skill
Runtime. Entries can be backed by:

- local providers, such as speech;
- MCP providers, such as Soridormi body skills;
- composite providers, which coordinate registered skills.

Soridormi remains authoritative for body-skill schemas and live availability.
Chromie imports that metadata instead of maintaining a divergent hand-written
copy.

Initial body skills for integration:

- `soridormi.nod_yes`;
- `soridormi.look_at_person`;
- `soridormi.express_attention`;
- bounded walking and turning skills;
- `soridormi.stop`.

Unavailable hardware skills must remain visible as unavailable and must fail
with an explicit reason.

## Relationship to TaskGraph

TaskGraph remains useful as an internal representation for complex,
multi-provider execution. It is not the primary user-facing output of the
Interaction Agent.

The expected layering is:

```text
InteractionResponse
  -> validated SkillRequest objects
  -> optional internal TaskGraph for scheduling
  -> provider calls
```

This keeps ordinary speech and gestures simple while preserving the existing
guarded graph executor for complex tasks.

## Implementation Plan

### I0 - Freeze Cross-Project Contracts

Status: complete in Chromie as of June 12, 2026.

Deliver:

- `InteractionResponse`, `SkillRequest`, `SkillResult`, and `SkillTrace`
  schemas;
- provider, cancellation, timing, and confirmation contracts;
- registry metadata and versioning rules;
- explicit forbidden low-level fields.

Gate:

- schema round-trip tests pass;
- unknown skills and invalid arguments are rejected;
- raw joint, motor, and `action_14d` fields are rejected;
- Chromie and Soridormi contract fixtures agree.

### I1 - Build the Chromie Skill Runtime

Status: complete in Chromie as of June 12, 2026. Production Orchestrator
wiring remains I4.

Deliver:

- skill registry and provider interface;
- local speech provider;
- MCP body-skill provider;
- sequential and parallel scheduler;
- timeout, cancellation, confirmation, and trace handling;
- compatibility adapter for current Agent results and TaskGraph execution.

Gate:

- speech-only request completes;
- action-only dry-run reaches the mock provider;
- parallel speech/body scheduling and sequential scheduling pass tests;
- interruption cancels all cancellable child work;
- no provider can bypass registry and policy validation.

### I2 - Expose Named Soridormi Skills over MCP

Status: complete in Soridormi and imported into Chromie's checked-in capability
fixture as of June 12, 2026.

Deliver:

- authoritative named-skill catalog with schemas and availability;
- named-skill plan and execution tools, separate from the existing bounded
  velocity-plan contract;
- runtime-backed status, cancellation, stop, and safe hold;
- adapters from social skills to the scripted keyframe executor and from
  locomotion skills to the existing controller/runtime.

Gate:

- `nod_yes`, `look_at_person`, and `express_attention` execute in MuJoCo
  through MCP;
- invalid and unavailable requests return stable refusal reasons;
- cancellation leaves Soridormi in a safe state;
- current velocity-plan clients remain compatible.

### I3 - Implement the Interaction Agent

Status: in progress. Chromie now exposes `POST /interaction`, returning the I0
`InteractionResponse` contract. The endpoint currently adapts the established
multi-agent result and translates known pose actions to Soridormi named skills;
the single semantic structured-output LLM path remains to be implemented.

Deliver:

- one semantic LLM path for understanding, reply generation, and skill choice;
- registry-aware structured output;
- validation repair and deterministic fallback;
- deterministic pre-router for interrupt, stop, emergency, and unusable input;
- migration path from the current Router/Agent split.

Gate:

- factual conversation produces speech only;
- an explicit gesture can produce action only;
- a greeting can produce speech and `nod_yes`;
- ambiguous or unsafe requests clarify or refuse;
- stop and emergency paths do not depend on LLM completion.

### I4 - Connect Orchestrator Execution

Status: in progress. The host Orchestrator can consume `POST /interaction`
behind `ORCH_ENABLE_INTERACTION_RESPONSE`, schedule local speech through the
trusted runtime, lazily import Soridormi's live named-skill catalog, execute
opaque named-skill plans over MCP, and cancel active runtime work on
interruption. Headless text-input acceptance now passes against the live
MuJoCo-backed Soridormi runtime. The production rollout remains default-off
pending native Interaction Agent output and microphone acceptance.

Deliver:

- Orchestrator execution of validated Interaction Agent results;
- TTS/body parallelism and ordering;
- barge-in, session lifecycle, cancellation, and trace correlation;
- removal of the current log-only body-plan behavior from the production path.

Gate:

- [Passed headless] text input reaches the Agent compatibility adapter, trusted
  Skill Runtime, local speech, Soridormi MCP, and real MuJoCo execution;
- microphone input reaches ASR, Interaction Agent, Skill Runtime, TTS, and
  Soridormi;
- one utterance produces one coordinated response;
- interruption stops speech and body work without leaving an orphaned plan.

### I5 - Cross-Project MuJoCo Acceptance

Run both deployments and retain evidence for:

| User request | Expected result |
|---|---|
| "Hello" | speech plus `nod_yes` |
| "Look at me" | acknowledgement plus `look_at_person` |
| "Are you listening?" | speech plus `express_attention` |
| "Nod" | `nod_yes`, with optional brief speech |
| "Stop" | immediate speech/body cancellation and safe hold |
| Unsupported or unsafe action | clarification or explicit refusal |

Gate:

- traces correlate ASR text, InteractionResponse, Skill Runtime, MCP request,
  and Soridormi execution;
- no raw low-level command crosses the brain/body boundary;
- stop latency meets the agreed bound;
- no test leaves an executing plan, emergency latch, or fallen robot.

### I6 - Hardware Enablement

Hardware is not part of the initial mainline. Begin only after:

- all I5 MuJoCo gates pass;
- Soridormi H3-H5 hardware commissioning gates pass;
- each enabled skill has hardware-specific limits and availability;
- supervised stop and recovery procedures are accepted.

## Development Order

Implement in this order:

1. I0 contracts.
2. I1 Skill Runtime with mock providers.
3. I2 Soridormi named-skill MCP support.
4. I3 Interaction Agent structured output.
5. I4 Orchestrator execution.
6. I5 full MuJoCo voice-to-speech-and-action acceptance.
7. I6 hardware enablement later.

The mainline is the priority. Model fine-tuning and small optimizations should
wait unless a measured failure blocks an acceptance gate.

## Current Gap Summary

Available now:

- Chromie realtime microphone, ASR, conversation, TTS, interruption, registry,
  guarded MCP invocation, TaskGraph validation, cancellation, and traces;
- Chromie interaction contracts and trusted Skill Runtime with registry
  validation, local speech, mock and Soridormi MCP providers, sequential and
  parallel scheduling, confirmation, timeout, cancellation, traces, and legacy
  AgentResult/TaskGraph adapters;
- Soridormi runtime-backed MCP transport, bounded velocity plans, named-skill
  discovery/planning/execution, status, cancellation, emergency stop, safe
  hold, and scripted social skills.

Still required:

- native Interaction Agent structured speech-plus-skills generation without
  the compatibility adapter;
- text-input acceptance of the flagged production Orchestrator loop and
  microphone acceptance through ASR and TTS;
- the remaining coordinated speech/body acceptance matrix and retained trace
  evidence.

Headless evidence retained on June 12, 2026:

- live capability probe advertised all 12 expected Soridormi MCP tools;
- `nod` produced local speech and completed a non-dry-run
  `soridormi.nod_yes` MuJoCo execution in 7.177 seconds;
- cancellation after 0.5 seconds completed in 0.563 seconds and left
  `active_task` clear with the emergency stop unlatched.
