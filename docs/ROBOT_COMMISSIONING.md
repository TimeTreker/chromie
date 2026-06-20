# Reference Robot Commissioning Checklist

This checklist defines the evidence required to select the first reference
robot and advance it toward the Physical pilot. It does not authorize motion.
Soridormi owns drivers, calibration, state estimation, motion safety, stop,
recovery, and the final hardware commissioning decision. Chromie owns the
high-level contract, authorization evidence, trace comparison, and user-facing
terminal behavior.

## Candidate identity

Start from the versioned candidate contract:

```bash
python scripts/verify_robot_candidate.py \
  commissioning/reference_robot_candidate.example.json \
  --allow-draft
```

The checked-in example is intentionally incomplete. Store the real candidate
under ignored `.chromie/commissioning/` when it contains serial numbers,
network details, or operator identities. The verifier distinguishes structural
validity, readiness for no-motion review, and final candidate selection. It
always reports `physical_motion_authorized=false`.

- [ ] Record robot vendor, model, serial number, controller, firmware, sensors,
  host OS, network topology, and power constraints.
- [ ] Pin the Chromie and Soridormi revisions and the provider configuration.
- [ ] Name one initial low-risk skill and its workspace, speed, payload, and
  supervision limits.
- [ ] List unsupported skills, configurations, and operating conditions.

Reject a candidate whose exact hardware or software identity cannot be pinned.
Before marking a candidate selected, the default verifier command must pass:

```bash
python scripts/verify_robot_candidate.py \
  .chromie/commissioning/reference_robot_candidate.json \
  --evidence-root .chromie/commissioning \
  --verify-evidence-files \
  --write-report .chromie/commissioning/candidate-verification.json
```

The final-review verifier resolves relative evidence paths from the evidence
root and rejects references that escape that package. It checks the referenced
provider manifest, emergency-stop procedure and evidence,
stop/recovery/communication-loss procedures, and calibration artifact files.
The provider manifest's `metadata.upstream_commit` must match
`revisions.soridormi`, and calibration artifact hashes must match their
declared SHA-256 values. Use `--allow-draft` without file verification only
while collecting the local candidate package.

## No-motion prerequisites

- [ ] A physical emergency stop is reachable and independently tested under
  the robot manufacturer's procedure.
- [ ] Soridormi reports high-level health, mode, active task, emergency-stop
  state, and recovery readiness without exposing device control arrays.
- [ ] Calibration artifacts are timestamped, checksummed, and tied to the exact
  robot, sensors, firmware, and Soridormi revision.
- [ ] Communication loss, stale state, provider restart, and unavailable
  dependencies fail closed.
- [ ] Stop, emergency stop, cancellation, and recovery procedures name an
  operator and an observable success condition.

## Contract gates

Run the manifest preflight before starting target services:

```bash
python scripts/verify_provider_readiness.py preflight \
  --manifest capabilities/soridormi.json
```

Do not continue until it passes. Then run each gate independently and retain
the JSON output:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  python scripts/provider_conformance.py \
  --live --profile sim \
  --output evidence/provider-sim.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  python scripts/provider_conformance.py \
  --live --profile hardware_shadow \
  --output evidence/provider-shadow.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  python scripts/provider_conformance.py \
  --live --profile hardware_dry_run \
  --output evidence/provider-dry-run.json

python scripts/provider_conformance.py --compare \
  evidence/provider-sim.json \
  evidence/provider-shadow.json \
  evidence/provider-dry-run.json \
  --output evidence/provider-parity.json
```

- [ ] `hardware_shadow` returns `no_motion=true` and
  `recommendation_only=true`.
- [ ] `hardware_dry_run` returns `no_motion=true`.
- [ ] Both modes pass catalog, planning, monitor, cancellation, status,
  abstraction, and safe-idle checks.
- [ ] Their high-level call sequence, arguments, authorization context, and
  terminal statuses match the simulator trace.
- [ ] No model-facing output contains motor, joint, torque, actuator,
  controller-array, or bus-level fields.

## Timing and recovery evidence

- [ ] Declare target thresholds for scenario duration, timeout termination, and
  cancellation termination before running acceptance.
- [ ] Retain observed planning, monitoring, execution, cancellation, stop, and
  status latencies with clock source and sample count.
- [ ] Run the versioned provider fault matrix against Soridormi-owned live
  fault injection and retain every failed attempt and rerun.
- [ ] Verify safe idle after success, refusal, timeout, cancellation, provider
  disconnect, restart, partial execution, and monitor failure.
- [ ] Demonstrate that recovery clears or preserves emergency-stop state only
  according to the documented operator procedure.

## Selection decision

The candidate can be selected as the first reference robot only when:

- `verify_robot_candidate.py` reports `selected_for_pilot=true`;
- the referenced evidence files stay inside the evidence root;
- the provider manifest revision and calibration hashes match the candidate;
- every no-motion prerequisite and contract gate passes;
- the retained evidence identifies exact revisions and configuration;
- measured latencies satisfy the declared thresholds;
- stop and recovery evidence has been reviewed by the responsible operator;
- remaining exclusions are explicit; and
- real motion stays disabled until the Physical pilot's supervised motion gate.

Any missing identity, low-level contract leak, unsafe-idle result, trace drift,
unreviewed stop behavior, or threshold failure rejects the candidate.

Candidate selection still does not enable
`AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION` or authorize a Soridormi hardware
command. Motion requires the later supervised Physical pilot gate.

The completed directory must pass:

```bash
python scripts/verify_provider_readiness.py verify \
  evidence/provider-readiness/<run-id> --require-clean
```
