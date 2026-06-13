# Chromie Operations Runbook

This runbook contains commands and recovery procedures. Use
[Current Implementation Status](docs/STATUS.md) for claims about completion and
[Configuration Reference](docs/CONFIGURATION.md) for variable semantics.

Run commands from the repository root unless stated otherwise.

## 1. Inspect configuration

```bash
cp -n .env.local.example .env.local
./scripts/show_profile.sh
```

Generated files:

```text
.env.runtime
.chromie/system_info.env
```

Do not hand-edit `.env.runtime`.

## 2. Start Docker services

First build:

```bash
BUILD=1 ./scripts/start_services.sh
```

Normal start:

```bash
./scripts/start_services.sh
```

Clean rebuild:

```bash
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
```

Stop services:

```bash
docker compose --env-file .env.runtime down
```

## 3. Prepare Ollama

```bash
set -a
source .env.runtime
set +a

docker compose --env-file .env.runtime exec chromie-llm ollama list
docker compose --env-file .env.runtime exec chromie-llm \
  ollama pull "$AGENT_MODEL"
./scripts/warm_ollama.sh
```

## 4. Configure and start host audio

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
cp -n orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE`, then start:

```bash
./scripts/start_orchestrator.sh
```

Manual launch, after dependencies are installed:

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

Do not launch from inside `orchestrator/`; repository-relative imports and paths
assume the project root.

## 5. Select the interaction mode

### Compatibility voice path

Use the defaults:

```env
ORCH_ENABLE_ROUTER=1
ORCH_ENABLE_AGENT=1
ORCH_ENABLE_INTERACTION_RESPONSE=0
```

### Structured speech-only path

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=0
```

### Structured MuJoCo path

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_AUTO_CONFIRM_SIM_SKILLS=1
ORCH_SORIDORMI_MANIFEST=capabilities/soridormi.json
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

Restart the Orchestrator after changing host feature gates.

## 6. Health checks

```bash
docker compose --env-file .env.runtime ps
curl -fsS http://127.0.0.1:8091/health | python -m json.tool
curl -fsS http://127.0.0.1:8091/routes | python -m json.tool
curl -fsS http://127.0.0.1:8092/health | python -m json.tool
curl -fsS http://127.0.0.1:8092/capabilities | python -m json.tool
curl -fsS http://127.0.0.1:8092/task-graphs/scheduler/status | python -m json.tool
curl -fsS http://127.0.0.1:11434/api/tags | python -m json.tool
```

## 7. Automated tests

```bash
./scripts/run_tests.sh
```

Documentation-only check:

```bash
python scripts/check_docs.py
```

## 8. GPU and TTS verification

```bash
./scripts/verify_tts_gpu.sh
./scripts/gpu_smoke_test.sh
```

Start existing images and generate real TTS audio:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

Dry-run the planned checks:

```bash
DRY_RUN=1 ./scripts/gpu_smoke_test.sh
```

A dry run is not target evidence.

## 9. Soridormi capability checks

Set the live endpoint:

```bash
export SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

Probe schema compatibility in the deployed Agent environment:

```bash
./scripts/build_runtime_env.sh
docker compose --env-file .env.runtime up -d chromie-agent
docker compose --env-file .env.runtime exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

The Agent service has `host.docker.internal:host-gateway` configured for Linux.
Use a Docker service hostname instead when Soridormi is attached to the same
network.

List the active Agent registry:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest capabilities/soridormi.json
```

Generate LLM-visible context:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest capabilities/soridormi.json \
  --llm-context --language en
```

Safe status and zero-motion planning acceptance:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

Runtime-backed simulator preflight:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --runtime-preflight \
  --expected-backend runtime \
  --expected-mode sim
```

## 10. Structured text acceptance

```bash
PYTHONPATH=. python scripts/interaction_text_acceptance.py nod
```

Cancellation example:

```bash
PYTHONPATH=. python scripts/interaction_text_acceptance.py nod \
  --cancel-after-s 0.2
```

This is headless evidence. It does not use the microphone or physical speaker.

## 11. Guarded recovery acceptance

Disposable Soridormi dry-run process:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --guarded-dry-run
```

Only add `--exercise-emergency-stop` when the process may be restarted.

Supervised runtime cancellation:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --exercise-runtime-cancellation
```

This intentionally leaves Soridormi emergency-stopped. Follow the Soridormi
recovery procedure and verify ready/safe-idle state before further motion.

## 12. M3/M5 target evidence

```bash
SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 \
  ./scripts/m5_target_acceptance.sh
```

Evidence appears under `.chromie/acceptance/<id>/`. The runner combines runtime
preflight, GPU smoke, and cancellation/emergency fallback. After it passes,
record the recovery result; the script itself leaves e-stop active.

Command rehearsal:

```bash
SUPERVISED_ACCEPTANCE=1 M5_DRY_RUN=1 \
  SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  ./scripts/m5_target_acceptance.sh
```

## 13. M13 voice acceptance

Run the automatic synthetic matrix first. It generates input WAV files with the
existing TTS service and injects them through the Orchestrator's private stdin
audio path, so the test still crosses VAD, ASR, Router, native Agent output,
Skill Runtime, response TTS, and Soridormi without relying on a person speaking:

```bash
python scripts/m13_voice_acceptance.py \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The run is fully automatic. The terminal displays generated fixture paths, ASR
transcripts, Router results, proposed skill IDs, skill results, and final case
verdicts. Validate this regression evidence with:

```bash
python scripts/verify_m13_evidence.py --allow-automated \
  .chromie/acceptance/m13/<id>
```

To include the host audio-device capture path without using a physical
microphone, run:

```bash
python scripts/m13_voice_acceptance.py \
  --mode virtual-mic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

This requires `pactl` and `paplay`. The runner creates a temporary null sink,
uses its monitor through `PULSE_SOURCE`, and removes the module during cleanup.
If a previous process was killed before cleanup, unload the stale module with
`pactl list short modules` followed by `pactl unload-module <id>`.

Finally, commit the candidate revision and run the real reference-host matrix:

```bash
python scripts/m13_voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

In supervised mode, press Enter once when ready, wait for `SPEAK NOW`, and speak
the displayed phrase. The runner prints the ASR result and session-scoped
pipeline trace. It asks for an audible/visual verdict only after all automated
checks pass. Verify release-closing evidence without `--allow-automated`:

```bash
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<id>
```

Automatic bundles are useful regression evidence but cannot close M13 because
they do not prove a real microphone, speaker, human pronunciation, room
conditions, or operator-observed simulator safety.

## 14. Logs

```bash
docker compose --env-file .env.runtime logs -f chromie-asr
docker compose --env-file .env.runtime logs -f chromie-router
docker compose --env-file .env.runtime logs -f chromie-agent
docker compose --env-file .env.runtime logs -f chromie-llm
docker compose --env-file .env.runtime logs -f chromie-tts
```

Useful Agent inspection:

```bash
curl -fsS http://127.0.0.1:8092/health | python -m json.tool
curl -fsS 'http://127.0.0.1:8092/capabilities/llm-context?language=en' \
  | python -m json.tool
```

## 15. Common recovery

### Duplicate replies

Verify only one Orchestrator owns the microphone:

```bash
pgrep -af 'orchestrator\.orchestrator'
```

The normal startup script uses `/tmp/chromie-orchestrator.lock`.

### TTS produces no audio

- Inspect `chromie-tts` logs.
- Verify `TTS_MAX_LENGTH` is a generation budget, not a character limit.
- Use `TTS_MAX_TEXT_CHARS` to shorten speech.
- Run `./scripts/verify_tts_gpu.sh`.

### Named skill fails before execution

- Confirm `ORCH_ENABLE_SORIDORMI_SKILLS=1`.
- Confirm `SORIDORMI_MCP_URL` is exported where the manifest is loaded.
- Run the capability probe.
- Compare live tool schemas to the pinned manifest revision.

### Emergency stop remains active

This is expected after cancellation/emergency acceptance. Do not bypass it in
Chromie. Follow Soridormi’s recovery process, then re-run status/preflight.
