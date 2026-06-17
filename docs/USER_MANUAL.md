# User Manual

This manual is for an operator using Chromie with Soridormi in simulation. It
keeps the day-to-day commands in one place while the detailed authority remains
in [Status](STATUS.md), [Acceptance](ACCEPTANCE.md), and the
[Operations Runbook](../CHROMIE_RUNBOOK.md).

## Safety Rules

- Use MuJoCo `sim` mode unless a separate physical commissioning plan says
  otherwise.
- Keep physical-motion gates off for real hardware.
- Do not edit `.env.runtime`; regenerate it with the startup scripts.
- Treat text and voice requests as proposals until the trusted runtime
  authorizes execution.
- Use deterministic stop, cancel, and emergency paths for interruption.
- Do not expose raw motor, joint, torque, actuator, or controller-array values
  to the model-facing contracts.

## Daily Startup

From the Chromie repository:

```bash
cp -n .env.local.example .env.local
./scripts/show_profile.sh
./scripts/build_runtime_env.sh
```

Start Soridormi with the MuJoCo viewer from the sibling Soridormi repository:

```bash
cd ../soridormi
./scripts/start_soridormi_mujoco.sh
```

Leave that terminal running. It should report:

```text
MuJoCo:  127.0.0.1:5555
MCP:     http://127.0.0.1:8000/mcp
Viewer:  enabled
```

Start Chromie services from the Chromie repository:

```bash
cd ../chromie
./scripts/start_services.sh
```

## Text Input To MuJoCo

Use this when you want to skip microphone and ASR while still testing routing,
Agent `/interaction`, the trusted Skill Runtime, live Soridormi MCP, and MuJoCo
execution.

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
  --expect-arg 2:yaw_radps=-0.12
```

Add `--no-speaker` for headless automation. Evidence is written under:

```text
.chromie/acceptance/text-mujoco/<id>/
```

Open `summary.json` first. A passing run has:

- `ok: true`;
- the expected ordered Soridormi skills;
- each Soridormi result marked `completed`;
- `status_after.active_task: null`;
- `status_after.emergency_stop: false`;
- `status_after.fallen` absent or false.

## Skill Sweep

Preview maintained text prompts without executing robot motion:

```bash
python scripts/interaction_text_skill_sweep.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

List built-in cases:

```bash
python scripts/interaction_text_skill_sweep.py --list-cases
```

Execute a selected case only while supervising the simulator:

```bash
python scripts/interaction_text_skill_sweep.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --execute \
  --case walk_velocity
```

## Voice Modes

Use voice modes when you need audio pipeline evidence:

```bash
python scripts/m13_voice_acceptance.py --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

Modes:

| Mode | Use |
|---|---|
| `synthetic` | TTS-generated input through VAD and ASR. Good automated regression. |
| `virtual-mic` | Pulse/PipeWire virtual microphone path. Good host audio-device regression. |
| `supervised` | Real microphone and speaker. Use only for a physical voice-device release claim. |

M13 text closure does not require the supervised real-microphone run.

## Expected Robot Semantics

- `walk ahead` means a body velocity skill, not a head gesture.
- `turn left` or `turn right` means body yaw in place, not only looking with the
  head.
- `nod` and `shake head` are head gestures.
- Compound requests should preserve order unless a safety or validation rule
  refuses the request.

## Stop And Recovery

Stop Chromie services:

```bash
docker compose --env-file .env.runtime down
```

Stop Soridormi by pressing `Ctrl+C` in the launcher terminal.

If Soridormi reports an active emergency stop, complete Soridormi's recovery
procedure before running more motion. Do not clear or ignore emergency state
from Chromie.

## Troubleshooting

If a text check says `No module named 'aiohttp'`, use the managed runtime:

```bash
conda run -n Chromie python scripts/interaction_text_mujoco_check.py --help
```

If the Agent does not load Soridormi capabilities, confirm the service runtime
has the manifest:

```bash
curl -fsS http://127.0.0.1:8092/capabilities/catalog | python -m json.tool
```

If MuJoCo does not move, confirm Soridormi is in `sim` mode and safe idle before
the run.

Prefer the structured evidence files over visual memory when diagnosing a run:

```text
route.json
interaction_response.json
execution.json
status_before.json
status_after.json
summary.json
```
