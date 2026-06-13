# Chromie Voice Assistant

Chromie is a local, GPU-accelerated realtime voice assistant and embodied-agent
orchestration stack. It combines host-side audio/VAD/playback, containerized
ASR, deterministic routing, local Ollama reasoning, structured interaction,
streaming TTS, and optional named robot skills provided by Soridormi.

> **Current status:** the repository is at **M13 — Native Interaction Agent and
> end-to-end voice acceptance**. Native `/interaction`, structured session-event
> evidence, the guided microphone/MuJoCo acceptance runner, evidence verification,
> and `v0.1.0-alpha.1` candidate packaging are implemented. M13 remains open until
> spoken request-bound confirmation and a real reference-host evidence bundle are
> completed and reviewed. See [Current Implementation Status](docs/STATUS.md).

中文说明见 [Chromie 中文项目指南](docs/PROJECT_GUIDE.zh-CN.md)。

## What works today

- A five-service Docker stack: ASR, TTS, Ollama, Router, and Agent.
- A host Orchestrator for microphone capture, VAD, barge-in, playback, short-term
  conversation state, and trusted Skill Runtime coordination.
- The established `RouteDecision -> AgentResult` voice path with deterministic
  fallback behavior.
- A shared `InteractionResponse` contract and native `POST /interaction`
  runtime, with strict validation and an explicit legacy-adapter rollback mode.
- A trusted Skill Runtime with speech and Soridormi named-skill providers,
  bounded scheduling, confirmation checks, timeout, cancellation, and traces.
- Capability-registry validation and live MCP schema probing.
- TaskGraph planning, dry run, read-only/planning execution, guarded execution,
  one-time confirmation grants, cancellation, emergency fallbacks, and bounded
  parallel non-physical work.
- GPU-free regression tests plus GPU, simulator, and supervised target
  acceptance tooling.
- Correlated JSONL session-event capture and a guided seven-case microphone/
  MuJoCo evidence runner.
- Versioned `v0.1.0-alpha.1` candidate notes, compatibility declaration, source
  archive generation, checksums, and strict release gating.

## What is not closed yet

- Non-skippable body-skill confirmation is not yet a complete spoken,
  request-bound user dialogue.
- The guided microphone matrix and evidence verifier exist, but no real
  reference-host bundle is committed or declared accepted in this snapshot.
- The alpha packaging path is prepared but intentionally non-publishable while
  tracked M13 blockers remain.
- M3 GPU and M5 supervised target evidence remain open operational tracks.
- Jetson profiles are configuration profiles, not proof of complete ARM64 image
  compatibility.
- The host hardware daemon is a legacy mock compatibility path; real embodied
  execution belongs in Soridormi.
- No official release package or compatibility guarantee exists yet.

## Runtime architecture

```text
Host
  microphone -> VAD -> Orchestrator
                    -> ASR WebSocket
                    -> Router HTTP
                    -> Agent HTTP
                    -> trusted Skill Runtime
                         -> local speech -> TTS WebSocket -> speaker
                         -> Soridormi named skill -> MCP -> simulator/robot

Docker
  chromie-asr     Faster-Whisper
  chromie-tts     OuteTTS / llama.cpp
  chromie-llm     Ollama
  chromie-router  deterministic and optional LLM routing
  chromie-agent   conversation, native interaction, capabilities, TaskGraph
```

Ownership rules:

- The host Orchestrator owns realtime audio, playback, interruption, session
  state, and Skill Runtime coordination.
- The Agent proposes speech, named skills, and TaskGraphs. It does not access
  microphone, speakers, MCP, or robot hardware directly.
- Soridormi owns embodied planning, execution policy, safety monitoring,
  stop/emergency behavior, resource exclusivity, and hardware commissioning.
- The legacy host hardware daemon is retained for mock/control-plane
  compatibility only.

## Deployment modes

| Mode | Key settings | Current support state |
|---|---|---|
| Compatibility voice | defaults from `.env.common` | Main working voice path |
| Structured speech-only | `ORCH_ENABLE_INTERACTION_RESPONSE=1`, Soridormi skills off | Implemented; useful for rollout validation |
| Structured MuJoCo | structured path plus `ORCH_ENABLE_SORIDORMI_SKILLS=1` and live MCP URL | Implemented behind flags; headless text acceptance exists |
| Physical hardware | guarded feature gates plus commissioned Soridormi hardware | Experimental; not release ready |

## Requirements

The primary deployment target is Linux with:

- Docker and Docker Compose;
- an NVIDIA GPU, driver, and NVIDIA Container Toolkit;
- Python 3.11 and Conda or an equivalent host environment;
- a microphone and speaker;
- disk space for Hugging Face, Ollama, and TTS caches.

Check the basics:

```bash
nvidia-smi
docker compose version
conda --version
```

## Quick start

### 1. Select and inspect the hardware profile

```bash
cp .env.local.example .env.local
./scripts/show_profile.sh
```

Chromie generates `.env.runtime` from `.env.common`, the selected
`env/profiles/*.env`, and `.env.local`. Do not edit `.env.runtime` directly.

### 2. Build and start Docker services

```bash
BUILD=1 ./scripts/start_services.sh
```

Later starts can omit `BUILD=1`:

```bash
./scripts/start_services.sh
```

### 3. Pull and warm the selected Ollama model

```bash
set -a
source .env.runtime
set +a

docker compose --env-file .env.runtime exec chromie-llm \
  ollama pull "$AGENT_MODEL"
./scripts/warm_ollama.sh
```

### 4. Configure host audio

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh

cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set explicit `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE` values in
`orchestrator/.env.local` when possible.

### 5. Start the host Orchestrator

```bash
./scripts/start_orchestrator.sh
```

Run only one Orchestrator process. The startup script uses a host lock to avoid
duplicate microphone sessions and repeated speech.

## Enable structured interaction

Speech-only structured rollout:

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=0
```

MuJoCo-backed named skills:

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_SORIDORMI_MANIFEST=capabilities/soridormi.json
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

Keep all physical TaskGraph gates off unless the deployment is supervised and
Soridormi is commissioned. See [Configuration Reference](docs/CONFIGURATION.md).

## Verify

Run GPU-free tests and documentation checks:

```bash
./scripts/run_tests.sh
```

Check deployed services:

```bash
docker compose --env-file .env.runtime ps
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
curl -fsS http://127.0.0.1:11434/api/tags
```

Run target GPU checks:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

Run Soridormi contract and text-interaction checks. The capability probe is
run inside the Agent container so it uses the deployed Agent dependencies:

```bash
./scripts/build_runtime_env.sh
docker compose --env-file .env.runtime up -d chromie-agent
docker compose --env-file .env.runtime exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  PYTHONPATH=. python scripts/interaction_text_acceptance.py nod
```

On Linux, Compose maps `host.docker.internal` through
`host-gateway`. If Soridormi is another container on the same Docker network,
use its service DNS name instead.

See [Acceptance and Evidence](docs/ACCEPTANCE.md) before claiming simulator,
target, or hardware validation.

Run the guided M13 microphone/MuJoCo matrix on the reference host:

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The host runner controls audio and evidence capture, while the Soridormi
capability probe runs in `chromie-agent` by default. Host-loopback MCP URLs are
automatically translated to `host.docker.internal` for that probe. Use
`--probe-runtime host` only in a development environment with
`agent/requirements.txt` installed.

For each utterance, press Enter once when ready. The runner displays a
three-second countdown followed by a prominent `SPEAK NOW` prompt, waits for
`asr_final`, and prints the detected transcript. It then waits for the case
events automatically. An operator verdict is requested only after all automated
checks pass; missing ASR or required events automatically fail the case and stop
the run by default.

Verify the resulting evidence bundle:

```bash
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<acceptance-id>
```

Prepare a non-publishable packaging rehearsal while the spoken-confirmation
blocker remains:

```bash
python scripts/prepare_alpha_release.py --preview \
  --evidence-dir .chromie/acceptance/m13/<acceptance-id>
```

## Repository layout

| Path | Purpose |
|---|---|
| `asr/` | Faster-Whisper WebSocket service |
| `tts/` | OuteTTS streaming WebSocket service and speaker tooling |
| `router/` | Route rules and optional LLM routing service |
| `agent/` | Multi-agent runtime, native interaction output, compatibility adapter, capability registry, and TaskGraph APIs |
| `orchestrator/` | Host audio loop, conversation state, interaction coordination, and Skill Runtime |
| `shared/` | Pydantic contracts and shared scheduling primitive |
| `capabilities/` | Trusted external capability manifests |
| `hardware/` | Legacy mock compatibility daemon |
| `scripts/` | Startup, profile, test, evidence, smoke, and release tooling |
| `docs/` | Status, architecture, API, configuration, acceptance, and release documentation |
| `release/` | Candidate version, compatibility declaration, and human-written release notes |

## Safety principles

- Model output never bypasses schema and policy validation.
- Low-level motor, joint, torque, and actuator fields are forbidden in shared
  interaction contracts.
- Confirmation, monitoring, cancellation, stop, and emergency paths are
  separate from normal reasoning.
- Simulation exemptions do not apply to hardware.
- Physical motion remains default-off and Soridormi-owned.

## Documentation

Use [Documentation Index and Governance](docs/README.md) as the map. The most
important documents are:

- [Current Implementation Status](docs/STATUS.md)
- [Roadmap](ROADMAP.md)
- [Development Checkpoint](DEVELOPMENT_CHECKPOINT.md)
- [Operations Runbook](CHROMIE_RUNBOOK.md)
- [Configuration Reference](docs/CONFIGURATION.md)
- [API Reference](docs/API_REFERENCE.md)
- [Acceptance and Evidence](docs/ACCEPTANCE.md)
- [Release and Packaging](docs/RELEASE.md)
