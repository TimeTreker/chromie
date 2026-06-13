# Chromie Roadmap

The roadmap describes intent and exit criteria. For the exact implementation
and evidence state of the current revision, use
[Current Implementation Status](docs/STATUS.md).

## Status model

Milestone progress is reported on four independent axes:

- **Implementation** — code exists.
- **Automated verification** — repeatable tests exist.
- **Target validation** — retained evidence exists on the intended environment.
- **Release readiness** — supported packaging, compatibility, and operations
  exist.

An older target-evidence item can remain open while later implementation work
continues. Therefore open M3 or M5 evidence does not mean the repository is
still at M3 or M5.

## Current position

**Current engineering milestone: M13 — Native Interaction Agent and end-to-end
voice acceptance.**

M6–M12 are implemented to local or simulator gates. Native structured
`/interaction`, strict validation, compatibility controls, correlated session
evidence, the guided seven-case microphone runner, evidence verification, and
alpha candidate packaging are now implemented. M13 remains open because:

1. non-skippable skill confirmation is not yet a complete spoken,
   request-bound conversation flow;
2. the guided matrix has not yet produced a reviewed reference-host bundle;
3. older target-evidence tracks remain open and no alpha has been published.

## Milestone map

| Milestone | Implementation state | Remaining validation or release work |
|---|---|---|
| M0 — Runtime foundation | Complete | Maintain clean startup and generated configuration |
| M1 — Realtime voice loop | Complete | Retain reference audio-device evidence |
| M2 — Contracts and safety | Complete | Continue regression coverage as schemas evolve |
| M3 — Target GPU verification | Tooling complete | Run and retain results on the supported target |
| M4 — TaskGraph production integration | Complete | Keep execution gates default-off and policy-compatible |
| M5 — External capability deployment | Integration complete | Supervised target acceptance and recovery evidence remain open |
| M6 — Interaction contracts and trusted Skill Runtime | Complete | Maintain contract and provider conformance |
| M7 — Soridormi named-skill contract | Complete upstream and integrated | Keep live endpoint and pinned manifest compatible |
| M8 — Structured Interaction API | Complete; compatibility adapter retained | Native output delivered in M13 |
| M9 — Host interaction coordination | Complete behind flags | Rollout decision and full voice evidence deferred to M13 |
| M10 — Headless cross-project MuJoCo interaction | Complete | Microphone-driven matrix deferred to M13 |
| M11 — Shared scheduling and resource arbitration | Complete | Monitor deployment behavior and diagnostics |
| M12 — Parallel TaskGraph reliability and guarded rollout | Complete locally and in simulation | Physical deployment remains conservative and default-off |
| M13 — Native Interaction Agent and full voice acceptance | **In progress; acceptance/release tooling implemented** | Spoken confirmation and reviewed reference-host evidence remain; alpha candidate is not publishable yet |

## Completed foundations

### M0–M2

- five Docker services plus a host Orchestrator boundary;
- hardware-aware generated runtime configuration;
- realtime VAD, ASR, routing, Agent, TTS, playback, and barge-in;
- shared route, action, Agent, session, and interaction contracts;
- deterministic stop/ignore/fallback behavior;
- confirmation checks and a mock compatibility action flow.

### M3 operational tooling

- host and container GPU visibility checks;
- Compose health verification;
- Router-to-Agent deployed round trip;
- Ollama generation and GPU placement checks;
- ASR/TTS WebSocket health;
- TTS CUDA backend and optional non-empty synthesis checks.

The tooling exists; retained target evidence is still required.

### M4–M5

- active capability registry and fail-fast manifest loading;
- TaskGraph validation, dry run, planning, and transport-neutral invocation;
- read-only, planning-only, and guarded execution modes;
- graph-bound single-use confirmation grants;
- physical-motion gate, monitor proofs, cancellation, stop, and emergency
  fallbacks;
- pinned Soridormi manifest, schema probe, safe planning acceptance, dry-run
  guarded acceptance, and runtime cancellation tooling.

### M6–M10

- strict `InteractionResponse`, speech, skill, result, and trace schemas;
- recursive rejection of low-level robot control fields;
- local speech and Soridormi provider abstractions;
- host Skill Runtime scheduling, confirmation, timeout, cancellation, and
  traces;
- compatibility `POST /interaction` API;
- Orchestrator structured execution behind rollout flags;
- live named-skill catalog import and plan/monitor/execute flow;
- headless text-to-live-MuJoCo acceptance and cancellation.

### M11–M12

- shared process-local `ResourceArbiter`;
- bounded parallel read/planning execution;
- deterministic result order and execution-local state;
- exclusive-group serialization across concurrent work;
- retry, timeout, fallback, abort, and cancellation parity;
- guarded non-physical concurrency while physical nodes remain sequential;
- scheduler status diagnostics.

## M13 exit criteria

M13 is complete only when all criteria below are satisfied.

### Native interaction semantics

- One registry-aware semantic generation path returns `InteractionResponse`
  directly.
- The compatibility `/run` path remains available only as a documented rollback
  during migration.
- Invalid or unknown skills fail closed before provider calls.
- Deterministic stop, cancel, emergency, silence, and unusable-audio paths remain
  outside model discretion.

### Confirmation dialogue

- Non-skippable skills produce a clear user confirmation request.
- Approval is bound to the intended interaction or request and cannot be reused
  for another skill.
- Decline, timeout, and interruption produce no physical execution.
- Simulation-only exemptions remain explicit and cannot leak into hardware.

### End-to-end voice acceptance

Retain evidence for:

- speech only;
- speech plus named body skill;
- unavailable/invalid skill refusal;
- barge-in during speech;
- cancellation during a simulated body skill;
- explicit stop/emergency behavior;
- short-term conversation follow-up.

Evidence requirements are defined in
[Acceptance and Evidence](docs/ACCEPTANCE.md).

### Alpha release readiness

- supported reference host and Soridormi revision are declared;
- clean-checkout setup and rollback are tested;
- status, API, configuration, and support documentation match implementation;
- known limitations and default-off gates are visible;
- release artifacts and compatibility table are published.

## Current M13 work sequence

1. **Completed:** emit native `InteractionResponse` output from the specialized
   Agent pipeline without a final `AgentResult` conversion.
2. **Completed:** validate native output with the shared strict contracts and
   fail closed by default.
3. **Completed:** retain the compatibility adapter behind
   `AGENT_INTERACTION_OUTPUT_MODE`, with opt-in validation fallback controlled by
   `AGENT_NATIVE_INTERACTION_FALLBACK`.
4. **Completed:** add correlated JSONL session-event capture, a guided
   microphone/MuJoCo runner, redacted environment/audio metadata, and per-case
   operator verdicts.
5. **Tooling completed; target run pending:** execute all seven cases on the
   reference host and verify the retained bundle with
   `scripts/verify_m13_evidence.py --require-clean`.
6. **Candidate preparation completed; closure pending:** declare
   `0.1.0-alpha.1`, compatibility metadata, release notes, source-archive and
   checksum generation. The generator remains non-publishable while blockers
   exist.
7. Implement and evidence spoken request-bound confirmation, review the real
   evidence bundle, close applicable M3/M5 target tracks, then publish the first
   narrowly scoped alpha release.

## Post-M13 candidates

- richer perception and vision providers;
- durable memory with explicit privacy controls;
- longer-running recovery-aware tasks;
- distributed observability and durable trace storage;
- verified Jetson packaging;
- device-specific physical hardware releases.

These should not displace M13 acceptance and release work.
