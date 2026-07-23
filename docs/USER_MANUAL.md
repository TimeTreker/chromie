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

For the normal microphone, speaker, and MuJoCo viewer operator loop, use the
paired launcher from the Chromie repository:

```bash
./scripts/start_voice_mujoco.sh --soridormi-repo ../soridormi
```

This starts Soridormi MuJoCo, Soridormi runtime MCP, Chromie ASR/TTS/Router/Agent,
and the host Orchestrator. After it prints `Chromie voice-to-MuJoCo is ready`,
say a supervised request such as:

```text
Please nod twice.
Look at me for three seconds.
What is the robot status?
Stop.
```

Use a headless simulator when no graphical desktop is available:

```bash
./scripts/start_voice_mujoco.sh --soridormi-repo ../soridormi --no-viewer
```

From another terminal, check readiness and recent logs:

```bash
./scripts/status_voice_mujoco.sh
./scripts/check_voice_mujoco_logs.sh
```

Stop the paired stack with `Ctrl+C` in the launcher terminal or:

```bash
./scripts/stop_voice_mujoco.sh
```

The lower-level manual startup remains available when you want separate
Soridormi and Chromie terminals.

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

Start Chromie from the Chromie repository. For text diagnostics, attach the
services to Soridormi MCP and skip the host microphone/speaker Orchestrator:

```bash
cd ../chromie
./scripts/start_chromie.sh --mcp-url http://127.0.0.1:8000/mcp --keep-services --no-orchestrator
```

Use Chromie's Compose wrapper for service inspection. Startup generates a root
`.env` so plain `docker compose` can interpolate required variables, but the
wrapper is preferred because it always passes the intended runtime env and
Compose file explicitly.

```bash
./scripts/compose.sh logs -f chromie-llm
./scripts/compose.sh ps
```

## Text Input To MuJoCo

Use this when you want to skip microphone and ASR while still testing routing,
the maintained goal-driven runtime, the trusted Skill Runtime, live Soridormi
MCP, and MuJoCo execution.

If the paired stack is already running, the compact no-microphone wrapper is:

```bash
./scripts/run_voice_mujoco_text_case.sh "Please nod twice." --speaker
./scripts/run_voice_mujoco_text_case.sh "Look at me for three seconds." --no-speaker
./scripts/run_voice_mujoco_text_case.sh \
  "please walk forward at 0.20 for 10 seconds and turn your head right and blink your eyes" \
  --no-speaker
```

The first command also checks speaker playback; the second is better for
headless automation. The wrapper uses goal-driven apply by default; pass
`--legacy-agent-runtime` only for an explicitly labelled compatibility check.

The text request is the only input Chromie uses for routing and skill planning.
`--expect-*` flags are optional post-run assertions for regression tests; they
are not sent to Router, Agent, or Soridormi and are not needed for natural
operator rehearsal.

```bash
conda run -n Chromie python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
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

The runner also prints compact `[interaction-text-mujoco][debug]` lines for
the route, staged task list, emitted skills, speech count, and errors.
Open `summary.json` first. A passing run has:

- `ok: true`;
- the expected ordered Soridormi skills;
- each Soridormi result marked `completed`;
- `status_before.safe_idle: true` and `status_after.safe_idle: true`;
- `status_after.active_task: null`;
- `status_after.emergency_stop: false`;
- `status_after.fallen` absent or false.

For diagnostic provenance, include `--soridormi-repo` so the summary records a
declared paired-checkout revision and clean state in addition to the manifest
revision. That path does not identify the source executing behind the MCP
endpoint. Retained target validation additionally requires a matching
endpoint-reported Soridormi revision, which the current runner does not obtain.

To diagnose the failure class where a physical request is misrouted through
deep thought and internal plan text leaks into TTS, run the same checker in
preview mode with internal speech rejection enabled:

```bash
conda run -n Chromie python scripts/interaction_text_mujoco_check.py \
  "Wal forward for 15 seconds, quickly." \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --preview-only \
  --no-speaker \
  --expect-skill soridormi.walk_forward \
  --reject-internal-speech
```

This writes the normal text-MuJoCo evidence bundle and fails if Chromie emits
no walking skill, routes to the wrong final mode, or speaks planner labels such
as `Task Split`, `Key Risk`, `Next Step`, or model-facing `soridormi.*` skill
IDs.

## General Ability Text Probes

Use the general ability runner for Cognitive Gateway/Core text behavior that is
not just a single motion skill: false-belief questions, compliments, discourse
markers, unsupported requests, deep-thinking handoff, emergency stop, mixed
speech/body cases, noisy ASR-like input, and Chinese/English ambiguity.

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py --list
conda run -n Chromie python scripts/general_ability_acceptance.py --mode check
conda run -n Chromie python scripts/general_ability_acceptance.py --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

By default `--mode live-text` is preview-only, headless, and no-microphone. The
scenario text is the only user input. Expected routes, skills, and speech
snippets are checked after Chromie has already planned its response. Use
`--execute` only when you intentionally want emitted Soridormi skills to run in
the supervised simulator.
The optional `--soridormi-repo` value is recorded as a declared paired checkout
for diagnostics; it does not identify the source running behind the MCP
endpoint.

The old standalone text scenario suite and text skill sweep commands have been
removed and should not be used as behavior-quality evidence.

## Voice Modes

Use voice modes when you need audio pipeline evidence. Start the external
Soridormi MCP endpoint separately first; `--start-services` starts Chromie
services only.

```bash
python scripts/voice_acceptance.py --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

Modes:

| Mode | Use |
|---|---|
| `synthetic` | TTS-generated input through VAD and ASR. Good automated regression. |
| `virtual-mic` | Pulse/PipeWire virtual microphone path. Good host audio-device regression. |
| `acoustic` | Generated speech through the configured host output/input path. Physical audio-path regression, but not a human voice-device claim. |
| `supervised` | Real microphone and speaker. Use only for a physical voice-device release claim. |

All four modes require a separately running Soridormi endpoint. A supplied
`--soridormi-repo` records a declared paired checkout but does not prove the
endpoint executes it; current bundles remain outside release-policy evaluation
until the endpoint reports a matching source revision. The historical text-to-MuJoCo closure does
not require the supervised real-microphone run.

## Expected Robot Semantics

- `walk ahead` means a body velocity skill, not a head gesture. If no speed is
  given, Chromie uses a normal safe forward speed of `0.18 m/s`. Requested
  forward speeds above the current Soridormi runtime limit of `0.20 m/s` are
  changed back to normal speed and Chromie tells you.
- `turn left` or `turn right` means body yaw in place, not only looking with the
  head.
- `turn your head left/right` and `look left/right` mean the head-only
  `soridormi.look_direction` skill.
- `nod` and `shake head` are head gestures.
- `walk ... with nodding/shaking your head` is accepted by the text route, but
  the physical skills are serialized for now: body movement first, then the head
  gesture. This preserves the current physical-work safety boundary.
- `sing a song` is speech-only chat unless the request also asks for body
  motion. Phrases such as `go ahead and sing` are treated as permission to
  speak, not as a walking command.
- `sing a song while walking` is handled as speech plus the walking skill. The
  speech uses a short original line and still applies the same walking safety
  normalization. Chromie waits until that speech is actually audible before
  starting the body walk, so the song and walk overlap.
- Chat-only speech is speech-only by default. Architecture validation can opt in
  to reviewed simulator-only gestures with `AGENT_SOCIAL_ATTENTION_MODE=sim_only`;
  leave it `off` for latency-sensitive or strict behavior tests. The older
  `AGENT_EXPRESSIVE_BODY_CUES` name is only a compatibility alias when the main
  setting is absent.
- Compound requests should preserve order unless a safety or validation rule
  refuses the request.

## Stop And Recovery

Stop Chromie services:

```bash
./scripts/compose.sh down
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
