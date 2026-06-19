# Project Handoff

Last updated: 2026-06-19

This handoff records the current resume point for a developer or operator who
needs to continue Chromie without replaying the full chat history.

## Current State

M13 text-to-MuJoCo interaction closure is complete. The retained text evidence
shows direct text input flowing through Router, Agent `/interaction`, the trusted
host Skill Runtime, live Soridormi MCP, and MuJoCo `sim` execution.

The current development focus is physical pilot preparation through the
Chromie/Soridormi task-agent boundary. Chromie can now represent richer
embodied requests as structured Soridormi task goals, attach stable
`client_task_ref` values, submit them through the planning TaskGraph executor,
and monitor `soridormi.task.events` until Soridormi reports a terminal state.
This is contract/no-motion preparation; it is not physical execution evidence.

Retained closure evidence:

```text
.chromie/acceptance/text-mujoco/20260617T081411Z
```

The tested request was:

```text
walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left
```

The expected ordered skills all completed:

```text
soridormi.walk_velocity
soridormi.nod_yes
soridormi.turn_in_place
```

The final Soridormi status was standing, with no active task and no emergency
stop.

## What M13 Does And Does Not Mean

Closed:

- text input routing to deterministic compound robot actions;
- native Agent `/interaction` contract generation;
- trusted Skill Runtime execution and ordered traces;
- live Soridormi named-skill execution in MuJoCo;
- safe-idle status after the text-driven run;
- automated synthetic and virtual-microphone regression evidence.

Not claimed by M13:

- robust human ASR;
- physical microphone or speaker quality;
- physical robot support;
- verified Jetson packaging;
- unattended operation.

Physical microphone/speaker validation is now a separate voice-device
release-support track. Run the supervised voice matrix only when the release
claim includes real audio devices.

## Latest Validation

The current docs-and-task-agent refresh at `5204ea1` passed:

```text
python scripts/check_docs.py
python -m unittest tests.test_soridormi_task_client \
  tests.test_planning_task_graph_execution \
  tests.test_soridormi_manifest_materialization \
  tests.test_provider_readiness_verifier
19 focused tests passed
```

The full host `./scripts/run_tests.sh` attempt did not complete in this minimal
host environment because service dependencies such as `fastapi` were absent and
one multiprocessing test could not create its forkserver socket under the
current sandbox. Run the full Level A suite in the dependency-complete
`chromie-agent` service environment before making new release claims.

Previously focused text/M13 tests also passed:

```text
python -m unittest \
  tests.test_interaction_text_mujoco_check \
  tests.test_interaction_text_acceptance \
  tests.test_m13_acceptance
```

## Resume Sequence

1. Keep physical-motion gates off.
2. Keep the Soridormi task-agent snapshot aligned with Soridormi's
   authoritative manifest.
3. Continue acceptance tests for task capability inspection, preview, submit,
   event monitoring, refusal, timeout, and cancellation semantics.
4. Select one reference robot candidate.
5. Fill the ignored real candidate record under `.chromie/commissioning/` using
   `commissioning/reference_robot_candidate.schema.json`.
6. Verify candidate identity, independent emergency stop, network, workspace,
   software revisions, calibration ownership, and no-motion procedures.
7. Continue with no-motion health and shadow/dry-run checks before any bounded
   physical skill execution.

## Useful Commands

Review status and roadmap:

```bash
python scripts/check_docs.py
./scripts/show_profile.sh
```

Run the text-to-MuJoCo closure check:

```bash
conda run -n Chromie python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --expect-skill soridormi.walk_velocity \
  --expect-skill soridormi.nod_yes \
  --expect-skill soridormi.turn_in_place \
  --expect-arg 0:vx_mps=0.2 \
  --expect-arg 0:duration_s=10 \
  --expect-arg 1:count=2 \
  --expect-arg 2:yaw_radps=-0.12 \
  --no-speaker
```

Run the full automated suite in the container runtime:

```bash
./scripts/compose.sh run --rm --no-deps \
  -v "$PWD:/workspace" -w /workspace \
  chromie-agent ./scripts/run_tests.sh
```

## Files To Read First

- [Project Charter](PROJECT_CHARTER.md)
- [Current Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [User Manual](USER_MANUAL.md)
