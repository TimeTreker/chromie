# Project Handoff

Last updated: 2026-06-22

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

Soridormi's no-motion task and skill surface is now declared in the paired
capability snapshot. The next non-hardware implementation section is Chromie
routing into those declared task types while preserving Soridormi refusal
metadata. Navigation, approach, and delivery remain structured refusals until
Soridormi proves the required simulator pipelines. Motion-control model
training is deferred until task semantics, target-body evidence, calibration,
telemetry, and safety envelopes exist.

The small Router model is also not an execution authority. Treat
`qwen3:0.6b` as an advisory classifier only: deterministic controls,
capability-catalog constraints, confidence fallback, schemas, Skill Runtime
authorization, and Soridormi provider checks must catch wrong model routes.

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

The current task-agent routing, refusal-reporting, and host graph-dispatch
refresh after committed base `f4bbb2f` passed:

```text
python scripts/check_docs.py
python scripts/test_matrix.py taskgraph
python scripts/test_matrix.py soridormi
python -m unittest tests.test_agent_client
python -m unittest tests.test_soridormi_acceptance
python -m unittest tests.test_robot_candidate_verifier
python -m unittest tests.test_interaction_control_plane
python -m unittest tests.test_interaction_coordinator \
  tests.test_skill_runtime \
  tests.test_native_interaction_runtime \
  tests.test_task_graph_planning \
  tests.test_planning_task_graph_execution
python -m unittest tests.test_task_graph_planning \
  tests.test_planning_task_graph_execution \
  tests.test_soridormi_task_client \
  tests.test_soridormi_acceptance \
  tests.test_capability_catalog_service \
  tests.test_capability_aware_interaction
SORIDORMI_MCP_URL=http://127.0.0.1:8011/mcp \
  PYTHONPATH=/Users/chromie/github/chromie/agent:/Users/chromie/github/chromie \
  /tmp/soridormi-m5-py313/bin/python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json --task-agent-bridge
```

The task-agent bridge acceptance passed against a local Soridormi dry-run MCP
server with graph `soridormi-task-agent-acceptance-115cc864fd04`, backend
`local_tool_dry_run`, `no_motion=true`, `safe_idle=true`, and explicit
`capabilities`, `preview`, `submit`, and `events` nodes. This is no-motion
contract evidence only; it does not prove physical execution.

The full host `./scripts/run_tests.sh` attempt reached 326 tests and ended
`FAILED (failures=1, errors=9, skipped=2)`: service dependencies such as
`fastapi` were absent, one multiprocessing test could not create its forkserver
socket under the current sandbox, and one temp-path assertion saw
`/private/var` instead of `/var`. Run the full Level A suite in the
dependency-complete `chromie-agent` service environment before making new
release claims.

Previously focused text/M13 tests also passed:

```text
python -m unittest \
  tests.test_interaction_text_mujoco_check \
  tests.test_interaction_text_acceptance \
  tests.test_m13_acceptance
```

## Resume Sequence

1. Keep physical-motion gates off.
2. Route rich user requests into Soridormi-declared no-motion task types before
   training motion-control models.
3. Preserve model-assisted routing guardrails. Qwen may propose normal routes,
   but stop/cancel/ignore stay deterministic, unknown or low-confidence routes
   clarify/refuse, and execution still requires registry/runtime/provider
   validation.
4. Keep the Soridormi task-agent snapshot aligned with Soridormi's
   authoritative manifest.
5. Continue acceptance tests for task capability inspection, preview, submit,
   event monitoring, refusal, blocked-subsystem reporting, timeout, and
   cancellation semantics. Use trace `outcome_summary` as the deterministic
   result source when adding report/speech nodes.
6. Preserve the no-motion `--task-agent-bridge` acceptance as the bridge
   contract gate; rerun it when Soridormi's task API snapshot changes.
7. Add Chromie routing only for Soridormi-declared task types; keep missing
   navigation, approach, and manipulation goals as structured refusals or
   clarifications rather than velocity recipes.
8. Select one reference robot candidate.
9. Fill the ignored real candidate record under `.chromie/commissioning/` using
   `commissioning/reference_robot_candidate.schema.json`.
10. Verify candidate identity, independent emergency stop, network, workspace,
   software revisions, calibration ownership, referenced evidence files,
   evidence-root containment, provider-manifest revision matching, calibration
   hashes, and no-motion procedures.
11. Continue with no-motion health and shadow/dry-run checks before any bounded
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
