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

## Current focus - Voice-to-MuJoCo alpha

### Objective

Publish a narrowly scoped alpha proving the complete voice, interaction,
confirmation, named-skill, cancellation, and recovery loop in MuJoCo.

The implementation is complete. Remaining work is evidence and release closure.
The Linux/GPU, virtual-microphone, and supervised runs are currently deferred
until development returns to the reference environment. This milestone remains
an open release gate; its scope is frozen except for defects.

### Exit criteria

- `./scripts/run_tests.sh` passes from the candidate revision;
- automatic `synthetic` and `virtual-mic` matrices pass all seven cases;
- `supervised` mode passes all seven cases on the declared reference host;
- `verify_m13_evidence.py --require-clean` accepts the supervised bundle;
- operator notes confirm audible output, request-bound approval and denial,
  simulator safe idle, cancellation, and recovery;
- exact Chromie and Soridormi revisions are retained;
- `release/compatibility.json` has no release blocker;
- a clean `0.1.0-alpha.1` bundle is published as a prerelease.

This alpha does not claim production robot support, verified Jetson packaging, or
unattended operation.

The acceptance scripts and evidence directories still use the historical `m13`
name. That identifier is retained for compatibility only.

## Next phase - Robust simulation and provider readiness

The Chromie-side implementation and automated verification for this milestone
are complete. Milestone closure now waits for live Soridormi simulator,
hardware-shadow, hardware-dry-run, and fault-injection evidence on the reference
environment. This work does not close the alpha, remove its release blocker, or
make the candidate publishable.

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

## Physical pilot

### Objective

Commission one explicitly supported robot configuration through a progressive,
supervised rollout.

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
