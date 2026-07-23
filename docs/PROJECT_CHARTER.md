# Chromie Project Charter

This document defines the stable purpose and boundaries of Chromie. It should
change rarely. Current implementation and evidence belong in
[STATUS.md](STATUS.md); delivery order belongs in [ROADMAP.md](../ROADMAP.md).

## Mission

Chromie is a local-first realtime interaction control plane for voice assistants
that can invoke embodied capabilities safely.

The intended user experience is:

```text
natural speech
-> Cognitive Gateway: normalize, apply protective reflexes, and review attention
-> Goal-Driven Cognitive Core: understand goals, decompose, plan, and coordinate
-> validated speech and named-skill requests
-> trusted execution
-> observable completion, failure, cancellation, or recovery
-> concise spoken feedback
```

Chromie should make this loop responsive, interruptible, understandable, and
portable across a simulator and later physical robots without exposing low-level
robot controls to a language model.

## Product outcome

A successful Chromie release lets an operator:

- speak naturally and receive timely local responses;
- request a trusted high-level embodied skill;
- understand what will happen before risky work begins;
- approve, decline, interrupt, cancel, or stop work deterministically;
- see correlated evidence of what was proposed, authorized, executed, and
  recovered;
- move the same high-level interaction contract from simulation to a
  commissioned physical provider.

## System boundaries

### Chromie owns

- microphone capture, VAD, ASR coordination, playback, and barge-in;
- the Cognitive Gateway ingress boundary: input normalization, deterministic
  protective reflexes for stop, cancel, emergency, silence, and unusable audio,
  and bounded attention/admission review; attention review cannot authorize
  effects and direct or unclear turns fail open to cognition;
- conversation state and user-facing interaction semantics;
- the Goal-Driven Cognitive Core: goal meaning and continuity, semantic
  decomposition and planning, outcome reconciliation, and response composition;
- native structured Agent output and strict model-facing contracts;
- trusted Skill Runtime validation, authorization, scheduling, timeout, and
  cancellation;
- evidence capture, acceptance tooling, deployment configuration, and release
  packaging.

### Soridormi owns

- embodied planning and execution;
- simulator and physical providers;
- robot resource exclusivity across processes;
- motion monitoring, stop, emergency stop, and recovery;
- device drivers, calibration, state estimation, and hardware commissioning.

### The language model may

- interpret user intent;
- produce concise speech;
- select registered named skills;
- propose validated TaskGraphs.

### The language model must never

- authorize its own side effects;
- bypass confirmation or safety policy;
- act as the sole authority for route, capability, or physical execution
  decisions;
- send raw motor, joint, actuator, torque, controller-array, or bus commands;
- decide deterministic operational controls;
- claim execution succeeded without provider evidence.

The legacy host hardware daemon is mock compatibility infrastructure, not a
future production robot backend.

### Cognitive boundary

The Cognitive Gateway is the narrow ingress, protective-reflex, and attention
boundary. It decides whether a turn must be acted on immediately for operational
safety, admitted to cognition, or ignored as confidently ambient input. It does
not own final user-goal meaning, task decomposition, planning, agent selection,
or response composition.

The Goal-Driven Cognitive Core owns those semantic decisions. Stop and emergency
commands are still user inputs, but their immediate protective effect must not
wait for model inference; the resulting control and evidence can then be
incorporated into goal and response state.

The deployed service currently named Router is a compatibility implementation
that still combines Gateway responsibilities with semantic/advisory routing.
That service topology must not be mistaken for the intended ownership boundary,
and its migration status is reported in [STATUS.md](STATUS.md).

## Engineering principles

1. **High-level contracts stay stable.** Simulation and physical providers
   should implement the same named-skill and result semantics.
2. **Robot thinking belongs to the Cognitive Core, models, and contracts.**
   Outside deterministic operational controls, normal conversation, memory,
   tool, robot-action,
   capability-selection, body-goal interpretation, planning, low-confidence
   correction, and deep-thought behavior must be decided by LLM reasoning over
   language meaning, bounded context, capability descriptions, schemas, and
   task memory. Catalog search, score thresholds, regression fixtures, regexes,
   and phrase tables may retrieve candidates or validate and reject model
   output, but they must not decide ordinary robot intent or planning by
   themselves.
3. **General competence beats case patches.** Reported utterances and scenario
   fixtures are probes into broad robot abilities, not the product goal by
   themselves. A fix should improve the reusable capability class behind the
   failure, such as robust intent understanding, stable catalog grounding,
   natural uncertainty handling, composable high-level action planning,
   truthful embodied speech, or valid end-to-end evidence. Do not tune Chromie
   only to pass the last visible sentence while leaving the underlying ability
   brittle.
4. **Risky behavior fails closed.** Disabled, unavailable, malformed, expired,
   or unconfirmed work does not execute.
5. **Operational controls stay deterministic.** Stop, cancel, emergency,
   silence, and unusable-audio paths do not depend on model judgment.
6. **Rule-based routing stays narrow.** Phrase and pattern rules belong only to
   the deterministic operational filter. Normal conversation, tool, memory,
   robot-action, and deep-thought intent must come from bounded model
   understanding and contract validation, or else clarify, delegate to deeper
   reasoning, or fail closed.
7. **Simulation precedes hardware.** Logical closure, failure handling, and
   recovery are proven in simulation before physical commissioning.
8. **Evidence is part of the product.** Implemented, automatically verified,
   target validated, and release ready are separate states.
9. **Physical rollout is progressive.** Shadow, dry-run, bounded single-skill,
   supervised multi-skill, and broader autonomy are distinct gates.
10. **Local-first does not mean opaque.** Failures, fallbacks, authorization,
   timing, and recovery causes remain inspectable.

## Non-goals

Chromie is not:

- a low-level robot controller or replacement for vendor control loops;
- a general-purpose distributed workflow engine;
- a durable personal-memory platform;
- an unattended physical-robot autonomy product in the current development scope;
- proof that every hardware profile, GPU, audio device, or robot is supported.

## Definition of success

Work advances the project only when it improves at least one of these outcomes
without weakening the others:

- interaction quality and latency;
- deterministic safety and recovery;
- contract portability across providers;
- measurable simulator or target evidence;
- operability, privacy, and release supportability.

New features that do not help close the current milestone, remove a documented
blocker, or strengthen one of these outcomes should normally wait.
