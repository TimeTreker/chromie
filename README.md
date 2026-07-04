# Chromie Voice Assistant

Chromie is a local-first realtime interaction control plane for voice assistants
that can invoke trusted embodied skills. It combines host audio and interruption,
containerized ASR/Router/Agent/TTS services, native structured interaction, and
optional Soridormi-backed simulator or robot skills.

The long-term goal and ownership boundaries are defined in the
[Project Charter](docs/PROJECT_CHARTER.md).

> **Current state:** the historical M13 text-to-MuJoCo interaction milestone is
> closed. Retained RTX 5090 GPU smoke, synthetic, virtual-microphone, acoustic
> generated-speech, and text-to-MuJoCo evidence pass on the reference host.
> The next intended release tag is `0.0.1`. Chromie is the real host control
> plane; this release is limited to generated-speech and structured interaction
> evidence with Soridormi executing robot work through its MuJoCo `sim` mode.
> Real microphone/speaker validation remains a separate track before making a
> human voice-device support claim. See
> [Status](docs/STATUS.md) and [Roadmap](ROADMAP.md).

中文概览见 [Chromie 中文指南](docs/PROJECT_GUIDE.zh-CN.md)。

## Architecture

```text
Host Orchestrator
  microphone -> VAD -> ASR -> Router -> Agent
                             -> trusted Skill Runtime
                                  -> speech -> TTS -> speaker
                                  -> named skill -> Soridormi MCP

Docker: ASR, Router, Agent, Ollama, TTS
Soridormi: embodied planning, simulator/robot execution, monitoring, stop,
           emergency stop, recovery, and hardware commissioning
```

Chromie never gives raw motor, joint, actuator, or torque controls to the
language model. The legacy `hardware/` daemon is mock compatibility only.

## What works

- realtime microphone, VAD, ASR, routing, TTS, playback, and barge-in;
- ASR backend boundary with sherpa-onnx SenseVoice as the supported
  final-utterance default and Faster-Whisper retained as a selectable fallback
  and comparison path;
- deterministic stop, cancel, emergency, ignore, and silence handling;
- three-stage route flow: emergency filter, Qwen quick intent routing, and
  larger-model deepthought handoff when quick confidence is low or planning is
  needed;
- staged task/action proposals merged into `RouteDecision.metadata.task_list`
  before Agent and Skill Runtime validation;
- native strict `POST /interaction` plus explicit compatibility rollback;
- trusted Skill Runtime with validation, confirmation, timeout, cancellation,
  bounded scheduling, and traces;
- request-bound spoken approval and denial;
- Soridormi named-skill discovery and MuJoCo execution;
- TaskGraph validation and gated read, planning, guarded, and physical-policy
  paths;
- text-to-MuJoCo, synthetic, virtual-microphone, acoustic, supervised, GPU,
  simulator, and release acceptance tooling.

Physical microphone/speaker evidence, a reviewed voice-device release bundle,
verified Jetson packaging, and physical robot support remain open.

## Quick start

Requirements: Linux, Docker Compose, an NVIDIA runtime for GPU deployment,
Python 3.11, and host audio dependencies.

For the complete microphone -> Chromie -> Soridormi -> MuJoCo path, keep the
Chromie and Soridormi repositories next to each other and run:

```bash
./scripts/start_voice_mujoco.sh --build
```

After the first build, normal daily startup is:

```bash
./scripts/start_voice_mujoco.sh
```

This starts the MuJoCo viewer, runtime-backed Soridormi MCP service, all Chromie
containers, and the host audio Orchestrator. Press `Ctrl+C` to stop the stack, or
run `./scripts/stop_voice_mujoco.sh` from another terminal. See the
[Chinese voice-to-MuJoCo quick start](docs/VOICE_MUJOCO_QUICKSTART.zh-CN.md).

For individual component startup:

```bash
cp .env.local.example .env.local
./scripts/show_profile.sh
BUILD=1 ./scripts/start_services.sh
./scripts/setup_orchestrator.sh
./scripts/start_orchestrator.sh
```

Chromie generates `.env.runtime` from committed defaults, the selected hardware
profile, and `.env.local`. It also writes an ignored root `.env` so plain
`docker compose ...` commands can interpolate the same values. Do not edit
either generated file directly.

For complete setup, model warming, audio configuration, health checks, and
recovery, use the [Operations Runbook](CHROMIE_RUNBOOK.md).
For fresh-machine bootstrap, use [Chromie Deployment](docs/DEPLOYMENT.md) and
`./scripts/deploy_chromie.sh`.

## Deployment modes

| Mode | Key setting | State |
|---|---|---|
| Compatibility voice | `ORCH_ENABLE_INTERACTION_RESPONSE=0` | Main rollback path |
| Structured speech | interaction on, Soridormi skills off | Implemented |
| Structured MuJoCo | interaction and Soridormi skills on | Implemented behind flags |
| Physical robot | commissioned Soridormi plus physical gates | Experimental, unsupported |

Risky gates remain default-off. Configuration semantics are maintained in
[Configuration Reference](docs/CONFIGURATION.md).

## Verify

```bash
./scripts/run_tests.sh
```

This runs the dependency-light automated suite and documentation checks. It does
not prove GPU, microphone, speaker, simulator, or hardware behavior.

Higher-level evidence commands and claim rules are in
[Acceptance and Evidence](docs/ACCEPTANCE.md). Current simulator operational
commands are in the [Runbook](CHROMIE_RUNBOOK.md).

## Safety rules

- model output is a request, never authorization;
- low-level robot controls are forbidden in shared contracts;
- stop, cancel, emergency, silence, and unusable-audio paths are deterministic;
- normal robot thinking, including body-goal interpretation, capability choice,
  and planning, belongs to LLM reasoning over bounded contracts, not hardcoded
  phrase, regex, or regression-case matches;
- normal natural-language routing goes through the quick intent model, while
  low-confidence or complex requests go to deepthought instead of deterministic
  guessing;
- simulation exemptions never authorize hardware;
- physical execution stays default-off and Soridormi-owned;
- implementation, automated verification, target validation, and release
  readiness are reported separately.

## Repository

| Path | Responsibility |
|---|---|
| `orchestrator/` | Host audio, interruption, conversation state, and Skill Runtime |
| `router/` | Deterministic and optional LLM routing |
| `agent/` | Native interaction, capabilities, and TaskGraph APIs |
| `asr/`, `tts/` | Speech services |
| `shared/` | Shared contracts and scheduling primitives |
| `capabilities/` | Pinned external capability manifests |
| `hardware/` | Legacy mock compatibility daemon |
| `scripts/` | Startup, validation, evidence, and release tooling |
| `docs/` | Project authority, interfaces, configuration, and decisions |
| `release/` | Candidate compatibility and release assets |

## Read next

- [Project Charter](docs/PROJECT_CHARTER.md): stable goal and boundaries
- [Status](docs/STATUS.md): what exists and what is evidenced
- [Roadmap](ROADMAP.md): milestone order and exit criteria
- [ASR Backend Migration](docs/ASR_BACKEND_MIGRATION.md): sherpa-onnx goal,
  gates, and implementation sequence
- [User Manual](docs/USER_MANUAL.md): current simulator operation
- [Project Handoff](docs/HANDOFF.md): resume point for the next developer
- [Development Checkpoint](DEVELOPMENT_CHECKPOINT.md): exact resume point
- [Documentation Index](docs/README.md): owner for every documentation fact
