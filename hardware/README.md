# Chromie Hardware Daemon

Host-side hardware executor for Chromie robot actions.

This module is intentionally designed to run on the **host**, not in Docker, because real robot hardware often needs direct access to serial ports, USB devices, GPIO, cameras, motor SDKs, audio devices, or realtime scheduling.

The daemon exposes a small HTTP API used by `chromie-orchestrator`:

- `GET /health`
- `GET /state`
- `POST /actions`
- `GET /actions/{action_id}`
- `POST /emergency_stop`

By default it uses the mock driver, so you can test the full route → agent → action flow without real hardware.

## Run on host

```bash
cd hardware
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python daemon.py
```

Default server:

```text
http://127.0.0.1:8095
```

## Environment variables

```env
HARDWARE_HOST=127.0.0.1
HARDWARE_PORT=8095
HARDWARE_DRIVER=mock
HARDWARE_SERIAL_PORT=/dev/ttyUSB0
HARDWARE_SERIAL_BAUD=115200
HARDWARE_ACTION_TIMEOUT_MS=5000
```

## Example action

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

The daemon should execute **safe, validated, low-level actions** only.

It should not talk to ASR/TTS/LLM. It should not decide what Chromie should say. It should only execute hardware actions requested by the host orchestrator.
