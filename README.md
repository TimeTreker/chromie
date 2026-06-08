# Chromie Voice Assistant

Chromie is a local, GPU-accelerated realtime voice assistant stack. It combines speech recognition, fast intent routing, multi-agent reasoning, a local Ollama model, and streaming speech synthesis.

中文读者可以从 [Chromie 中文项目指南](docs/PROJECT_GUIDE.zh-CN.md) 开始，了解架构、部署、验证与常见问题。

Project progress and the active milestone are tracked in [Chromie Roadmap](ROADMAP.md). The current milestone is **M5 - External capability deployment and acceptance**.

## Architecture

```text
host microphone
  ↓
host orchestrator        audio capture, VAD, interruption, session state
  ↓
chromie-asr              Faster-Whisper speech recognition
  ↓
chromie-router           fast route and intent decision
  ↓
chromie-agent            conversation, planning, safety, tools, memory
  ↓
chromie-llm              Ollama model server
  ↓
chromie-tts              OuteTTS / llama.cpp speech synthesis
  ↓
host orchestrator        playback and optional hardware actions
```

The central runtime boundary is:

> ASR, Router, Agent, LLM, and TTS run in Docker. The Orchestrator runs on the host because it owns microphone input, playback, audio-device selection, VAD, and interruption.

| Service | Runs on | Port | Purpose |
|---|---|---:|---|
| `chromie-asr` | Docker | `9001` | WebSocket speech recognition |
| `chromie-tts` | Docker | `5000` | WebSocket speech synthesis |
| `chromie-llm` | Docker | `11434` | Ollama model server |
| `chromie-router` | Docker | `8091` | Lightweight route and intent decision |
| `chromie-agent` | Docker | `8092` | Conversation and action planning |
| Orchestrator | Host | n/a | Realtime audio and service coordination |
| Hardware daemon | Host, optional | `8095` | Robot action execution |

## Requirements

The current desktop deployment targets Linux with:

- Docker and Docker Compose
- an NVIDIA GPU, driver, and NVIDIA Container Toolkit
- Conda for the host Orchestrator
- a microphone and speaker
- enough disk space for Hugging Face, Ollama, and TTS model caches

Check the basics:

```bash
nvidia-smi
docker compose version
conda --version
```

RTX 5090, RTX 4090 desktop/laptop, Jetson Thor, and Jetson Orin profiles are
detected automatically. GPU type changes model sizing and deployment details,
not Chromie's architecture or its Soridormi contract. Other NVIDIA GPUs use a
conservative fallback or an explicit `.env.local` profile override.

## Quick Start

### 1. Configure local overrides

Chromie generates `.env.runtime` from:

```text
.env.common
  + env/profiles/<detected-profile>.env
  + .env.local
```

Create the optional machine-local override file and inspect the selected profile:

```bash
cp .env.local.example .env.local
./scripts/show_profile.sh
```

Only put local overrides in `.env.local`. Do not edit generated `.env.runtime`.

### 2. Start Docker services

Build images on the first run:

```bash
BUILD=1 ./scripts/start_services.sh
```

On later runs:

```bash
./scripts/start_services.sh
```

The script creates `hf_cache/`, `ollama_data/`, and `recordings/`, generates `.env.runtime`, and starts all five Docker services.

### 3. Prepare the Ollama model

Check installed models:

```bash
docker compose --env-file .env.runtime exec chromie-llm ollama list
```

If the `AGENT_MODEL` shown by `./scripts/show_profile.sh` is missing, pull that exact model:

```bash
set -a
source .env.runtime
set +a
docker compose --env-file .env.runtime exec chromie-llm ollama pull "$AGENT_MODEL"
```

Warm the selected model:

```bash
./scripts/warm_ollama.sh
```

### 4. Select host audio devices

Create and activate the Conda environment if it does not already exist, then install the host dependencies:

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
```

The environment name can be changed with `CHROMIE_CONDA_ENV` in `.env.local`.

Create the host audio configuration and list available devices:

```bash
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE` in `orchestrator/.env.local`. Prefer explicit hardware devices over generic entries such as `default`, `sysdefault`, `pipewire`, or monitor devices.

### 5. Start the host Orchestrator

```bash
./scripts/start_orchestrator.sh
```

The script activates the Conda environment named by `CHROMIE_CONDA_ENV`, installs changed host dependencies, warms Ollama, and runs:

```bash
python -m orchestrator.orchestrator
```

Run only one Orchestrator process. The startup script uses a lock file to prevent duplicate microphone sessions and duplicate spoken replies.

## Configuration

Hardware-specific defaults live in `env/profiles/*.env`; `.env.local` has the highest generated-config priority. Common overrides include:

```env
CHROMIE_HARDWARE_PROFILE=rtx4090
AGENT_MODEL=gemma4:e2b
ROUTER_USE_LLM=0
AGENT_MAX_SPEAK_CHARS=160
```

Keep the Router deterministic by default:

```env
ROUTER_USE_LLM=0
```

The Agent is the primary talking and planning component:

```env
AGENT_USE_LLM=1
```

Trusted external capability manifests can be mounted from `./capabilities` and
enabled with `AGENT_CAPABILITY_MANIFESTS`. See
[Capability Registry](docs/agent_capability_registry.md) for the fail-fast
loading rules and runtime inspection endpoints.

For Soridormi, set
`AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json` and provide
`SORIDORMI_MCP_URL`. Probe the live MCP endpoint against the checked-in
manifest before enabling TaskGraph execution.

Soridormi is the robot cerebellum: it owns embodied planning, safety, policy
execution, and robot feedback. Chromie owns conversation, global planning,
confirmation, and orchestration. The checked-in manifest is materialized from
[Soridormi's exported contract](https://github.com/TimeTreker/soridormi) with
only the deployment transport changed to MCP Streamable HTTP.

The projects remain separate deployments: Soridormi publishes a dedicated
`soridormi-mcp` container, while `chromie-agent` connects to it through
`SORIDORMI_MCP_URL`. Chromie does not embed Soridormi in its own images.

Set `AGENT_ENABLE_TASK_GRAPH_PLANNING=1` to opt eligible `tool` routes into
validated structured planning. Planned graphs are returned for inspection and
are not executed until a guarded `ToolInvoker` transport is configured.

`AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1` separately enables MCP execution
for graphs containing only side-effect-free read and planning capabilities.

`AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1` enables safe reads plus
stateful `planning_only` tools such as Soridormi plan creation. It still rejects
speech, writes, safety controls, and physical motion.

Guarded side effects and physical motion have separate, default-off deployment
gates. See [Task Graph](docs/agent_task_graph.md) for operator authorization,
node-bound confirmation, and safety-monitor requirements.

Use `AGENT_MAX_SPEAK_CHARS` or `TTS_MAX_TEXT_CHARS` to shorten speech. `TTS_MAX_LENGTH` is the TTS generation budget and should not be reduced to a small text-length value.

See [Hardware Profiles](HARDWARE_PROFILES.md) for profile selection, CUDA architecture, model sizing, and Jetson limitations.

## Verify

Check container health:

```bash
docker compose --env-file .env.runtime ps
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
curl -fsS http://127.0.0.1:11434/api/tags
```

Verify TTS GPU use:

```bash
./scripts/verify_tts_gpu.sh
```

Run the complete target-machine GPU smoke test after services are running:

```bash
./scripts/gpu_smoke_test.sh
```

To start existing images first and include a real TTS generation:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

The smoke test checks host/container GPU visibility, service health, Ollama inference, ASR/TTS WebSockets, and the TTS CUDA backend. It does not test microphone or speaker quality.

For M5 target acceptance, combine the GPU checks with Soridormi contract and
runtime-cancellation evidence:

```bash
SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 \
  ./scripts/m5_target_acceptance.sh
```

The generated evidence is stored under `.chromie/acceptance/`.

Watch the main logs:

```bash
docker compose --env-file .env.runtime logs -f chromie-agent
docker compose --env-file .env.runtime logs -f chromie-llm
docker compose --env-file .env.runtime logs -f chromie-tts
```

For common failures such as model timeouts, duplicate replies, CPU-only TTS, or incorrect playback speed, see [Chromie Operations Runbook](CHROMIE_RUNBOOK.md).

## Tests

Run the GPU-free control-plane suite:

```bash
INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
```

After dependencies are installed, use:

```bash
./scripts/run_tests.sh
```

The suite covers Router rules and mode selection, cross-service contracts, conversation state, Agent safety behavior, confirmation gating, and the mock hardware flow. It does not download models or require Docker, CUDA, audio devices, or robot hardware.

## Development Principles

- Keep Router decisions fast and deterministic.
- Keep conversation intelligence and action planning in the Agent.
- Keep realtime audio, interruption, playback, and action execution in the Orchestrator.
- Let only the Orchestrator call ASR, TTS, playback, and host hardware.
- Serialize TTS generation unless the backend is explicitly designed for concurrency.
- Keep fallbacks and timing visible in logs.

## Documentation

- [Roadmap](ROADMAP.md): current milestone, completed foundations, and acceptance criteria
- [中文项目指南](docs/PROJECT_GUIDE.zh-CN.md): Chinese architecture, setup, verification, and troubleshooting guide
- [Hardware Profiles](HARDWARE_PROFILES.md): runtime environment generation and hardware-specific defaults
- [Operations Runbook](CHROMIE_RUNBOOK.md): frequent startup and diagnostic commands
- [Orchestrator](orchestrator/README.md): host realtime audio runtime
- [Router](router/README.md): routing API and configuration
- [Agent](agent/README.md): multi-agent API and responsibilities
- [Hardware](hardware/README.md): optional host hardware daemon
- [Conversation State](docs/conversation_state.md): multi-turn context and conversation boundaries
- [Capability Registry](docs/agent_capability_registry.md): available Agent tools and safety visibility
- [Task Graph](docs/agent_task_graph.md): validated multi-step task planning and execution
