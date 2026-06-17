# Chromie Roadmap

This document is the authority for delivery order and milestone exit criteria.
The stable mission is defined in
[Project Charter](docs/PROJECT_CHARTER.md). Current implementation and evidence
are tracked in [Status](docs/STATUS.md).

## Planning model

Chromie uses a small number of outcome milestones. Historical implementation
increments are not maintained as separate planning units.

- Only one delivery milestone is active at a time.
- A milestone closes only when its implementation and required evidence exist.
- Default-off experimental work is not release support.
- Older evidence tools retain legacy names such as M3, M5, or M13 for
  compatibility; those names do not create additional active milestones.
- Future work must preserve the ownership and safety boundaries in the charter.

## Completed foundations

Earlier work previously labeled M0-M12 is now represented by two completed
capability foundations:

| Foundation | Included outcomes | State |
|---|---|---|
| Realtime interaction foundation | Five-service runtime, host audio/VAD/playback, deterministic routing, contracts, generated configuration, GPU and target tooling | Implemented and automatically verified; some target evidence remains open |
| Structured embodiment foundation | Native interaction, Skill Runtime, Soridormi named skills, TaskGraphs, confirmation, cancellation, bounded scheduling, traces, and MuJoCo integration | Implemented and automatically verified locally and in simulation |

The old M0-M12 numbering remains visible only in historical commits, tool names,
and evidence references. It should not drive new scope.

## Completed phase - Text-to-MuJoCo interaction closure

### Objective

Close the historical M13 interaction milestone by proving the deterministic
text-input path through Router, native `/interaction`, trusted Skill Runtime,
Soridormi named skills, MuJoCo execution, and safe-idle recovery.

This phase is complete. The retained `text-mujoco` evidence proves a compound
text request is routed into ordered walking, nodding, and turning skills, all
executed by Soridormi in MuJoCo, with the simulator returning to safe idle. The
automatic synthetic and virtual-microphone matrices remain retained regression
evidence for the broader voice pipeline.

Physical microphone recognition and speaker quality are deliberately excluded
from M13 closure. They remain an audio-device validation track for any future
release claim that includes real voice input/output support.

### Exit criteria

- `./scripts/run_tests.sh` passes from the candidate revision;
- automatic `synthetic` and `virtual-mic` matrices pass all seven cases;
- the deployed text-to-MuJoCo check passes against live Soridormi MCP and MuJoCo;
- retained text evidence shows ordered `walk_velocity`, `nod_yes`, and
  `turn_in_place` execution plus safe idle;
- exact Chromie and Soridormi revisions are retained;

This closure does not claim robust human ASR, physical microphone/speaker
quality, production robot support, verified Jetson packaging, or unattended
operation.

The voice acceptance scripts and evidence directories still use the historical
`m13` name. That identifier is retained for compatibility only.

## Open evidence track - Physical audio validation

Physical voice validation is no longer a blocker for M13 text interaction
closure. Before publishing a release that claims support for real microphone and
speaker operation, retain a clean supervised bundle, operator review, and
release evidence that cover microphone choice, room noise, ASR recognition,
audible output, barge-in, request-bound approval and denial, cancellation, stop,
and simulator recovery.

## Completed phase - Robust simulation and provider readiness

This milestone is complete for the high-level provider contract. Soridormi
revision `4afb4bc6411db4a4194e97349d9466a62efd2f24` supplies live no-motion
`sim`, `hardware_shadow`, and `hardware_dry_run` profiles plus test-only fault
injection. All three profiles pass conformance and parity, and the live
16-scenario fault matrix passes its terminal-state, latency, and safe-idle
checks.

The provider-readiness run used a local macOS ARM64 MCP endpoint and did not
command MuJoCo actuators or physical hardware. Separate Linux RTX 5090
Voice-to-MuJoCo automated evidence now passes; supervised physical audio and
real-hardware evidence remain separate release tracks.

### Objective

Prove that the system fails safely under non-ideal conditions and that a
physical provider can replace the simulator provider without changing
Chromie's model-facing semantics.

This combines the former “robust simulation” and “hardware-neutral
commissioning contract” proposals because fault behavior and provider
conformance must be designed and verified together.

### Work

- add Soridormi-owned fault injection for latency, jitter, dropped status,
  timeout, unavailable skills, blocked paths, partial execution, restart, and
  monitor failure;
- add Chromie integration cases for provider timeout, disconnect, malformed
  result, cancellation races, and safe user-facing fallback;
- define repeatable scenario batches and thresholds for success, timeout,
  cancellation latency, and safe idle;
- stabilize versioned named-skill request, progress, terminal status, and error
  semantics;
- define provider conformance tests shared by simulator and physical backends;
- add shadow and dry-run commissioning modes;
- define calibration, timing, health, stop, recovery, and evidence requirements;
- keep device drivers and physical safety implementation in Soridormi.

### Exit criteria

- every versioned fault scenario ends in its expected terminal state;
- no injected failure bypasses confirmation, cancellation, stop, or emergency
  policy;
- simulator providers pass the provider conformance suite;
- a no-motion physical-provider skeleton passes the same contract tests;
- shadow and dry-run modes produce comparable, replayable traces;
- no model-facing contract contains device-specific low-level controls;
- a commissioning checklist is sufficient to select the first reference robot.

## Current phase - Physical pilot preparation

### Objective

Select and prepare one explicitly supported robot configuration for a
progressive, supervised rollout. Until the candidate identity, independent
emergency stop, and no-motion prerequisites are reviewed, development remains
in preparation and does not authorize physical motion.

The first preparation gate is a versioned, machine-readable candidate manifest.
It must pin hardware and software identity, define one bounded low-risk skill,
record exclusions, and fail closed on missing safety or calibration evidence.

### Sequence

1. no-motion health and state inspection;
2. shadow recommendations;
3. dry-run with operator approval;
4. one low-risk skill at limited speed and workspace;
5. supervised cancellation, stop, emergency stop, and recovery;
6. bounded multi-skill TaskGraphs;
7. narrowly scoped physical prerelease.

### Exit criteria

- exact hardware, firmware, sensors, drivers, and Soridormi revision are pinned;
- the candidate verifier reports `selected_for_pilot=true` while continuing to
  report `physical_motion_authorized=false`;
- calibration and latency measurements are retained;
- physical stop and recovery evidence is reviewed;
- communication loss and stale-command cases fail closed;
- the release names one supported configuration and all exclusions.

## Later work

Perception providers, privacy-controlled durable memory, longer recovery-aware
tasks, distributed observability, verified Jetson packaging, additional robot
platforms, and broader autonomy are candidates only after the physical pilot.

## Anti-drift checks

Before accepting major work, ask:

1. Does it close the active milestone or a documented release blocker?
2. Is the behavior owned by Chromie or Soridormi according to the charter?
3. Does it preserve deterministic controls and fail-closed authorization?
4. Is the required evidence level explicit?
5. Does it avoid binding the model-facing contract to one robot?

If the answer is no, defer the work or revise its scope.
