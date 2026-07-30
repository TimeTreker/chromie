# Chromie Voice Assistant

Chromie is a local-first realtime interaction control plane for voice assistants
that can invoke trusted embodied skills. It combines host audio and interruption,
containerized ASR/Cognitive Gateway/Goal-Driven Cognitive Core/TTS services, native structured interaction, and
optional Soridormi-backed simulator or robot skills.

The long-term goal and ownership boundaries are defined in the
[Project Charter](docs/PROJECT_CHARTER.md).

Chromie also adopts a Runtime Observability architecture. Runtime Trace records
architecture-independent execution topology and timing; Runtime Events package
immutable evidence for the external data loop; Experience Episodes preserve
semantic interaction history; and Scenario Candidates are derived offline under
human review. See
[Runtime Observability Architecture](docs/RUNTIME_OBSERVABILITY_ARCHITECTURE.md).
The default-off implementation now provides generic nested spans, cross-service
trace fragments, topology-aware summaries, detached voice-session traces,
VAD/ASR and execution/audio milestones, bounded resource samples, active-trace
restart recovery, configurable latency/sampling retention, optional Runtime
Events, and active-trace attachment to cognitive-integrity incidents. GPU
telemetry is now collected through an optional non-blocking provider, and
retained trace reports can be evaluated by explicit evidence-qualified latency
gates. Real simulator/hardware baselines and approved thresholds remain
environment-specific evidence work rather than inferred release claims.

> **Current state:** the Goal-driven Runtime is implemented as Chromie's single
> semantic authority: Goal Association -> Fast/terminal Deep Planning ->
> prospective Response Composition -> trusted execution -> deterministic
> per-goal outcome reconciliation -> speech-only final response. A frozen
> `UserTurnEnvelope` now preserves the admitted Gateway input through this loop.
> The contracts and host path are automatically verified and default to
> authoritative chat in the common safe base; the maintained Soridormi launcher
> widens authority to simulator robot actions. Historical voice-pipeline and
> text-to-MuJoCo evidence remains valid only for its recorded legacy revisions.
> A clean live rerun of the current authority path is still required before
> target validation. No release version or publication target is planned. See
> [Status](docs/STATUS.md) and [Roadmap](ROADMAP.md).
>
> **Implemented Agent Skills architecture:** Agent Skills are passive,
> owner-approved methods selected by Agents to inform Plans. The repository now
> includes grounded external-information and weather methods. Executable
> operations still use registered `capability_id` contracts through the Trusted
> Capability Runtime.

中文概览见 [Chromie 中文指南](docs/PROJECT_GUIDE.zh-CN.md)。

## Architecture

```text
Host Orchestrator
  microphone -> VAD -> ASR -> Cognitive Gateway
    |-> Protective Reflex -> immediate stop/cancel (no model wait)
    `-> immutable admitted UserTurnEnvelope -> Goal-driven Cognitive Core
        -> Goal Association -> model-authored Agent Skill selection and bounded projection disclosure
        -> Fast Planner -> terminal Deep Planner when needed
        -> prospective Response Composer -> strict InteractionResponse
        -> Trusted Capability Runtime (legacy code name: Skill Runtime)
        -> named capability -> Soridormi MCP
        -> structured results and traces
        -> exact plan/request/result join -> per-goal outcome reconciliation
        -> speech-only final response -> TTS -> speaker

Docker: ASR, Agent (Cognitive Core), Ollama, TTS
Soridormi: embodied planning, simulator/robot execution, monitoring, stop,
           emergency stop, recovery, and hardware commissioning
```

The [Cognitive Gateway](docs/COGNITIVE_GATEWAY.md) is an ingress boundary,
not the semantic brain. It normalizes and admits turns, applies deterministic
protective reflexes, reviews attention, and assembles bounded context. Goal
meaning, capability grounding, planning, delegation, result reconciliation,
and final response remain the responsibility of the Goal-driven Cognitive
Core. The frozen version 1 `UserTurnEnvelope`, host admission adapter, local
protective-reflex/suppression paths, and configured-lane Core projection are
implemented. The five Gateway responsibilities are explicit logical modules in the host.
There is no independent Router service or `/route` compatibility API.

Chromie never gives raw motor, joint, actuator, or torque controls to the
language model. The legacy `hardware/` daemon is mock compatibility only.

## What works in source and automated tests

These are implementation claims, not current-revision live qualification:

- accepts microphone audio, detects speech, transcribes final utterances, and plays ordered TTS;
- admits normal turns through Cognitive Gateway before Goal-driven model reasoning;
- handles stop, cancel, emergency, silence, and unusable audio deterministically;
- lets the LLM interpret Goals, choose passive Agent Skills, and propose Plans;
- validates, authorizes, schedules, cancels, and records named Capability execution;
- keeps provider adaptation inside trusted Capability adapters rather than planner prompts;
- reconciles external results against the exact request before allowing factual speech;
- delegates embodied feasibility, collision safety, stop, and recovery to Soridormi;
- supports named Soridormi skills through MCP and MuJoCo-backed execution;
- retains runtime traces, execution receipts, evidence manifests, and acceptance reports;
- evaluates behavior through module, integration, E2E, stress, and General Ability tooling.

The current revision still needs retained source-bound evidence for:

- live Gateway/Core text interaction and active cancellation;
- positive Agent Skill selection with real provider-backed weather execution;
- paired Chromie/Soridormi MuJoCo execution and safe idle;
- the reviewed Social Attention live baseline;
- physical microphone and speaker behavior;
- second-machine LAN exposure validation;
- physical robot and Jetson deployment.

Until the default target-evidence profile closes, new architecture layers, ordinary
behavior flags, standalone design documents, and project terminology are frozen
unless they are required to remove a demonstrated evidence blocker.

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

Before every supported build/start, Chromie takes a fresh hardware snapshot,
auto-detects the matching committed profile, and generates a flattened
`.env.runtime`, `.env`, and `.chromie/runtime_profile.json`. Profile-owned
model/resource values cannot be replaced from `.env.local`; stale conflicting
local values are ignored with a warning and recorded in the runtime manifest.
Use `CHROMIE_ENV_STRICT=1` when CI should reject such conflicts. Do not edit the
generated files directly; use `./scripts/compose.sh` instead of plain Compose.

For complete setup, model warming, audio configuration, health checks, and
recovery, use the [Operations Runbook](CHROMIE_RUNBOOK.md).
For fresh-machine bootstrap, use [Chromie Deployment](docs/DEPLOYMENT.md) and
`./scripts/deploy_chromie.sh`.

## Deployment modes

| Mode | Key setting | State |
|---|---|---|
| Compatibility voice | cognitive runtime off, explicit legacy path | Emergency rollback only |
| Goal-driven speech | cognitive apply on, `chat,tool` lanes, Soridormi skills off | Common safe base |
| Goal-driven MuJoCo | cognitive apply on, `chat,robot_action,tool`, Soridormi skills on | Maintained simulator launcher |
| Physical robot | commissioned Soridormi plus physical gates | Experimental, unsupported |

Effectful providers and physical gates remain default-off in the common safe
base. Configuration semantics are maintained in
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
For behavior-quality changes, also use the general ability acceptance runner
documented in
[General Ability Test Reconstruction](docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

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
| `orchestrator/` | Host audio, interruption, conversation state, and Trusted Capability Runtime |
| `agent/app/cognitive_core/goal_interpreter/` | Compatibility Cognitive Gateway backend for attention review and advisory routing |
| `agent/` | Native interaction, capabilities, and TaskGraph APIs |
| `asr/`, `tts/` | Speech services |
| `shared/` | Shared contracts and scheduling primitives |
| `capabilities/` | Pinned external capability manifests and prompt-tier presets |
| `agent-skills/` | Repository-owned passive Agent Skill packages; mounted read-only and never execution-authoritative |
| `hardware/` | Legacy mock compatibility daemon |
| `scripts/` | Startup, validation, evidence, and release tooling |
| `docs/` | Project authority, interfaces, configuration, and decisions |
| `release/` | Candidate compatibility and release assets |

## Read next

- [Project Charter](docs/PROJECT_CHARTER.md): stable goal and boundaries
- [Cognitive Gateway](docs/COGNITIVE_GATEWAY.md): input, reflex, attention, and turn-admission boundary
- [Cognitive Turn Loop](docs/COGNITIVE_TURN_LOOP.md): Core-managed delegation, evidence reconciliation, and final-response lifecycle
- [Agent Skills Architecture](docs/AGENT_SKILLS_ARCHITECTURE.md): Agent, Agent Skill, Plan, and Capability boundaries
- [Agent Skills Implementation Plan](docs/AGENT_SKILLS_IMPLEMENTATION_PLAN.md): open issue and semantic delivery slices
- [Runtime Observability Architecture](docs/RUNTIME_OBSERVABILITY_ARCHITECTURE.md): trace, event, episode, and scenario relationships
- [Runtime Trace Contract](docs/RUNTIME_TRACE.md): architecture-independent trace-item schema and lifecycle
- [Status](docs/STATUS.md): what exists and what is evidenced
- [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md): current source-bound evidence workflow
- [Roadmap](ROADMAP.md): milestone order and exit criteria
- [SenseVoice ASR](docs/SENSEVOICE_ASR.md): runtime contract, model provenance,
  evaluation, and release evidence
- [TTS Provider Evaluation](docs/TTS_PROVIDER_EVALUATION.md): provider contract,
  common A/B matrix, candidate policy, and selection gates
- [User Manual](docs/USER_MANUAL.md): current simulator operation
- [Project Handoff](docs/HANDOFF.md): resume point for the next developer
- [Development Checkpoint](DEVELOPMENT_CHECKPOINT.md): exact resume point
- [Documentation Index](docs/README.md): owner for every documentation fact
