# Chromie Voice Assistant

Chromie is a local-first realtime interaction control plane for voice assistants
that can invoke trusted embodied skills. It combines host audio and interruption,
containerized speech and cognition services, structured capability requests, and
optional Soridormi-backed simulator or robot skills.

The long-term goal and ownership boundaries are defined in the
[Project Charter](docs/PROJECT_CHARTER.md).

Chromie can retain correlated traces, events, resource samples, and reviewed
experience artifacts. See
[Runtime Observability Architecture](docs/RUNTIME_OBSERVABILITY.md).

> **Current state:** the Goal-driven Runtime is implemented as Chromie's single
> semantic authority with readiness-driven continuous progress. After admitted
> Fast Understanding, complete native conversational answers, and exact capability
> work candidates may advance independently while Goal Association continues;
> background Social Attention may independently prepare optional body decoration
> for the same anchored interaction. Native answers enter the existing Vocal runtime;
> trusted safe reads may start provider work early. Goal Association later binds
> those candidates to canonical Goals. Fully bound native conversation can close
> without Planner/Response-Composer model calls, and fully bound information reads
> may adopt a canonical Plan without a Fast-Planner call; other work falls through
> to Fast/terminal Deep Planning. Response Composition runs only when a new
> presentation decision is still needed, then trusted execution and
> deterministic per-goal reconciliation own completion truth. A frozen
> `UserTurnEnvelope` now preserves the admitted Gateway input through this loop.
> The contracts and host path are automatically verified and default to
> authoritative chat plus registered safe read-only tools in the common safe
> base; the maintained Soridormi launcher widens authority to simulator robot
> actions. The complete microphone/automated-audio -> Chromie -> Soridormi ->
> MuJoCo path is implemented. Retained evidence includes full synthetic and
> virtual-microphone MuJoCo runs, clean Goal-driven generated-voice evidence,
> clean Goal-driven MuJoCo execution/cancellation, and one supervised physical
> microphone -> audible-speaker turn. These artifacts are revision-bound, so a
> later source change does not silently inherit their exact-revision claim, but
> that provenance rule does not make the implemented core path unfinished.
> Issues #1, #5, #6, and #7
> have been merged to `main`; their retained evidence remains bound to the
> exact recorded revisions and does not automatically become evidence for a
> later merge commit. Any gate claim must use
> the exact output of a fresh `./scripts/run_tests.sh` run rather than a copied
> test count. A strict source-bound verifier for
> the current-revision microphone-to-audible-response loop is implemented. The
> latest automated generated-speech run exercised VAD, ASR, the live
> Gateway/Core, TTS, playback, and deterministic interruption on an RTX 5090.
> A separate clean supervised run has already validated the basic physical
> microphone -> ASR -> cognition -> TTS -> audible-speaker chain. Default
> audio selections now follow OS device changes during runtime, while explicit
> selections remain pinned; broader device distribution, acoustic barge-in,
> hot-plug, and latency characterization are optional qualification scopes, not
> missing core interaction functionality. Physical-robot deployment is likewise
> an optional Soridormi/provider integration and is not a Chromie completion
> condition. No release version
> or publication target is planned. See
> [Status](docs/STATUS.md) and [Roadmap](ROADMAP.md).
>
> **Implemented Agent Skills architecture:** Agent Skills are passive,
> owner-approved methods selected by Agents to inform Plans. The repository now
> includes grounded external-information and weather methods. Executable
> operations still use registered `capability_id` contracts through the Trusted
> Capability Runtime.
> Provider-neutral physical and informational acquisition now share a typed
> `AcquireAndDeliverResource` Goal. Soridormi, external-information, weather,
> memory, and future integrations remain peer Capability Providers selected only
> by planning from exact registered semantic scope. See
> [Resource Acquisition and Delivery](docs/RESOURCE_ACQUISITION_AND_DELIVERY.md).
> Chromie has two execution lanes beneath the one Cognitive Core: Vocal and
> Activity. Social Attention is background social-decoration cognition, not a
> third lane; accepted decoration executes through Activity with no Goal-completion
> authority. Soridormi remains a peer Capability Provider beneath Activity and
> owns its subtle-expression, locomotion/whole-body, and safety arbitration. See
> [Execution Lanes and Coordination](docs/EXECUTION_LANES_AND_COORDINATION.md).

中文概览见 [Chromie 中文指南](docs/PROJECT_GUIDE.zh-CN.md)。

## Architecture

```text
Host Orchestrator
  microphone -> VAD -> ASR -> Cognitive Gateway
    |-> Protective Reflex -> immediate stop/cancel (no model wait)
    `-> immutable admitted UserTurnEnvelope -> Goal-driven Cognitive Core
        -> Fast Understanding
           |-> complete native response -> Vocal --- .
           |-> exact capability progress candidate ----|
           |      `-> readiness-qualified safe read ---|
           |-> background Social Attention decoration |
           `-> Goal Association -----------------------+-> canonical Goal state
                                                        |
        -> exact ready-progress adoption OR Fast Planner -> terminal Deep Planner when needed
        -> Response Composer only when a new presentation decision is still needed
        -> Trusted Capability Runtime (`CapabilityRuntime`)
        -> named capability -> Soridormi / peer providers
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

## Implemented core path and retained evidence

The core interaction architecture is implemented:

- Capture microphone audio, transcribe final utterances, and play ordered TTS.
- Admit normal turns through Cognitive Gateway before Goal-driven reasoning.
- Handle stop, cancel, emergency, silence, and unusable audio deterministically.
- Let the LLM interpret Goals, choose passive Agent Skills, and propose Plans.
- Validate, authorize, schedule, cancel, and record named Capability execution.
- Keep provider adaptation inside trusted Capability adapters.
- Reconcile external results against the exact request before factual speech.
- Delegate embodied feasibility, collision safety, stop, and recovery to
  Soridormi.
- Retain runtime traces, execution receipts, evidence manifests, and acceptance
  reports.
- Evaluate behavior through module, integration, E2E, stress, and General
  Ability tooling.

Retained target evidence additionally proves:

- full synthetic and virtual-microphone speech input through VAD, ASR,
  cognition, Trusted Capability Runtime, TTS, and MuJoCo on their recorded
  revisions;
- clean Goal-driven compound MuJoCo execution, deterministic provider-start
  cancellation, Goal reconciliation, and safe-idle recovery;
- clean generated-speech VAD/ASR/Gateway/Core/TTS/playback and interruption; and
- one supervised physical microphone -> ASR -> cognition -> TTS -> audible
  speaker turn.

## Remaining qualification, not missing core functionality

- clean full-matrix generated-speech acceptance after the post-merge fixes;
- positive Agent Skill selection with trustworthy real provider-backed weather
  execution and follow-up conversation;
- the reviewed Social Attention live baseline;
- second-machine LAN exposure validation;
- broader/bilingual audio quality, physical acoustic barge-in, hot-plug, and a
  declared latency budget; and
- exact-revision rebinding when a release or publication claim requires it.

Physical robot/Jetson deployment is deliberately absent from this list. Chromie
uses provider-neutral semantic capabilities and does not need to know whether
Soridormi executes them in MuJoCo or on a commissioned body. Physical deployment
may be qualified separately for that provider, but it is not a core project
goal or release gate.

Until the canonical gate, narrow live voice proof, and default target-evidence
profile close, new architecture layers, ordinary behavior flags, standalone
design documents, and project terminology are frozen unless required to remove
a demonstrated blocker. These are exact-revision delivery/provenance gates, not
evidence that the already-implemented core voice/MuJoCo path is absent.

## Quick start

Requirements: Linux, Docker Compose, an NVIDIA runtime for GPU deployment,
Python 3.11, and host audio dependencies.

Chromie launchers select one maintained operator mode rather than asking the
operator to assemble many feature booleans:

| Launcher | Mode |
|---|---|
| `scripts/start_services.sh` | `services` |
| `scripts/start_orchestrator.sh` | `speech` |
| `scripts/start_chromie.sh` / `scripts/start_voice_mujoco.sh` | `voice_mujoco` |
| target-evidence closure | `qualification` |

The generated runtime manifest records the selected mode. Maintained modes use
Goal-driven apply lanes and keep legacy direct-LLM fallback disabled. See the
[Configuration Reference](docs/CONFIGURATION.md#maintained-operator-modes).

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
| Goal-driven speech | cognitive apply on, `chat,memory,tool` lanes, Soridormi skills off | Common safe base |
| Goal-driven MuJoCo | cognitive apply on, `chat,memory,robot_action,tool`, Soridormi skills on | Maintained simulator launcher |
| Physical robot | commissioned Soridormi plus physical gates | Optional provider integration; experimental and outside core acceptance |

Effectful providers and physical gates remain default-off in the common safe
base. Configuration semantics are maintained in
[Configuration Reference](docs/CONFIGURATION.md).

## Verify

```bash
./scripts/run_tests.sh
```

This runs the dependency-light automated suite and documentation checks. It does
not prove GPU, microphone, speaker, simulator, or hardware behavior.

For one revision-bound comprehensive collection that preserves deterministic
fixture truth, runs bilingual generated-speech closed-loop E2E, and packages
semantic-review evidence plus host/container/GPU/audio logs, run:

```bash
./scripts/qualification/run_comprehensive_test.sh --strict-exit
```

The comprehensive collector never requires operator speech. It generates
Chinese and English speech for monitor or acoustic capture, preserves failed
checks in the local raw archive, and never grants release qualification by
itself. Add `--sanitize-archive` to create a separate credential-, identity-,
and durable-memory-redacted upload copy; add `--sanitize-exclude-audio` when
audio must not leave the machine. Review conversational text even after
sanitization. `--strict-exit` returns nonzero only after evidence is written. For important prompt, reasoning, memory, routing,
response, or audio changes, retain clean before/after archives. Semantic bundles
may be judged independently by several configured model families:

```bash
./scripts/qualification/run_comprehensive_test.sh \
  --semantic-reviewers .chromie/semantic-reviewers.json
```

Compare a clean baseline and candidate archive after a large change:

```bash
python -m benchmarks.regression compare \
  --baseline ~/Downloads/chromie-baseline.tar.gz \
  --candidate ~/Downloads/chromie-candidate.tar.gz \
  --output benchmarks/reports/regression-comparison.json
```

Copy `benchmarks/manifests/semantic_reviewers.example.json`, verify current
provider model/base-URL values, assign honest model-family identities, enable
selected profiles, and keep API keys in environment variables. See the
[Benchmark Suite](docs/CHROMIE_BENCHMARK_SUITE.md#731-independent-multi-llm-adjudication).

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
- normal natural-language routing goes through model-authored typed meaning;
  complete non-effectful conversation uses the direct Core response path rather
  than a planner used merely to transport speech, bounded work stays on Fast
  Planner, and Deep records the wider semantic or safety/resource reason that
  required escalation instead of relying on deterministic guessing;
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
- [Status](docs/STATUS.md): current implementation and evidence
- [Roadmap](ROADMAP.md): active Issue and delivery order
- [Development Checkpoint](DEVELOPMENT_CHECKPOINT.md): exact resume point
- [Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md): behavior-change rules
- [Cognitive Gateway](docs/COGNITIVE_GATEWAY.md): input, reflex, attention, and turn-admission boundary
- [Cognitive Turn Loop](docs/COGNITIVE_TURN_LOOP.md): Core-managed delegation, evidence reconciliation, and final-response lifecycle
- [Agent Skills Architecture](docs/AGENT_SKILLS_ARCHITECTURE.md): Agent, Agent Skill, Plan, and Capability boundaries
- [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md): current source-bound evidence workflow
- [Acceptance](docs/ACCEPTANCE.md): evidence levels and claim limits
- [Operations Runbook](CHROMIE_RUNBOOK.md): startup and recovery
- [User Manual](docs/USER_MANUAL.md): current simulator operation
- [Documentation Index](docs/README.md): owner for every documentation fact
