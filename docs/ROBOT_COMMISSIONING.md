# Reference Robot Commissioning Checklist

This checklist defines the evidence required to select the first reference
robot and advance it toward the Physical pilot. It does not authorize motion.
Soridormi owns drivers, calibration, state estimation, motion safety, stop,
recovery, and the final hardware commissioning decision. Chromie owns the
high-level contract, authorization evidence, trace comparison, and user-facing
terminal behavior.

## Candidate identity

- [ ] Record robot vendor, model, serial number, controller, firmware, sensors,
  host OS, network topology, and power constraints.
- [ ] Pin the Chromie and Soridormi revisions and the provider configuration.
- [ ] Name one initial low-risk skill and its workspace, speed, payload, and
  supervision limits.
- [ ] List unsupported skills, configurations, and operating conditions.

Reject a candidate whose exact hardware or software identity cannot be pinned.

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

Run each gate independently and retain the JSON output:

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

- every no-motion prerequisite and contract gate passes;
- the retained evidence identifies exact revisions and configuration;
- measured latencies satisfy the declared thresholds;
- stop and recovery evidence has been reviewed by the responsible operator;
- remaining exclusions are explicit; and
- real motion stays disabled until the Physical pilot's supervised motion gate.

Any missing identity, low-level contract leak, unsafe-idle result, trace drift,
unreviewed stop behavior, or threshold failure rejects the candidate.
