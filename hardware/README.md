# Chromie Hardware Daemon

This directory contains Chromie's legacy host-side compatibility daemon. It
supports the original `AgentResult.actions` path and GPU-free control-plane
tests. It is not the primary embodiment boundary for the current alpha
interaction architecture.

New robot-body behavior must be exposed as validated named skills through the
host Skill Runtime and Soridormi MCP. Soridormi owns embodied planning,
resource policy, stop/emergency behavior, simulator integration, and real
hardware commissioning.

## Current implementation status

The daemon currently instantiates `HardwareService()` with `MockRobotDriver`.
Although `HARDWARE_DRIVER` and serial-related environment names/files exist in
the repository, `daemon.py` does not select a serial or production driver. In
this revision, every daemon launch therefore uses the mock driver.

Do not treat the presence of serial adapter code or configuration names as
hardware acceptance evidence.

## HTTP API

Default address: `http://127.0.0.1:8095`

- `GET /health` — service, driver, and state summary
- `GET /state` — current mock robot state
- `POST /actions` — submit a compatibility action
- `GET /actions/{action_id}` — retrieve the retained result
- `POST /emergency_stop` — set the mock emergency-stop state
- `POST /reset_emergency_stop` — clear the mock emergency-stop state

Results are retained in process memory only.

The service rejects:

- actions with `requires_confirmation=true`; confirmation must be resolved
  before this boundary;
- action types in the `unsafe.*` namespace.

Those checks are compatibility safeguards, not a substitute for Soridormi's
physical safety contract.

## Run on the host

From the repository root:

```bash
python3 -m venv hardware/.venv
source hardware/.venv/bin/activate
pip install -r hardware/requirements.txt
python -m hardware.daemon
```

Configuration actually consumed by `daemon.py`:

```env
HARDWARE_HOST=127.0.0.1
HARDWARE_PORT=8095
HARDWARE_DRIVER=mock
```

`HARDWARE_DRIVER` is reported as deployment intent but is not currently wired
to driver selection. `HARDWARE_SERIAL_PORT`, `HARDWARE_SERIAL_BAUD`, and
`HARDWARE_ACTION_TIMEOUT_MS` should not be documented as active daemon behavior
until implementation selects and uses them.

## Example mock action

```bash
curl -X POST http://127.0.0.1:8095/actions \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "robot_pose_controller",
    "type": "head.turn",
    "params": {"yaw_degrees": -20, "pitch_degrees": 0, "duration_ms": 600}
  }'
```

## Design rule

Do not add LLM-visible raw motor, torque, joint-target, or actuator-control
interfaces here. The strict interaction contracts reject such low-level fields,
and production embodiment belongs behind Soridormi's named, schema-validated,
safety-scoped skills.
