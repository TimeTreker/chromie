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

> **Current state:** Chromie uses one Goal-driven semantic authority with
> event-driven, readiness-driven continuation. Goal Interpretation owns
> provider-neutral Responsibility / WHAT. The same admitted meaning can enter
> Planner and Goal Association concurrently: Planner owns detailed HOW, exact
> Communicative Activities and Capability Work, while Goal Association alone owns
> canonical Goal continuity. Planner has fast/deep cognition passes of the same
> authority; deep is used only when HOW warrants broader reasoning.
>
> Trusted Capability Runtime is asynchronous. Provider/Runtime events report what
> happened; Host correlation and validation materialize Evidence describing what
> is true. Responsibility/Goal state says what remains owed. A meaningful trusted
> Goal/Work/Evidence/Situation change may create an ephemeral
> `CognitiveOpportunity`, which can reactivate Planner with the bounded current
> state. Planner may answer, author genuinely new Work, reuse/cancel/replace
> existing Work, clarify, wait, or produce no new Activity. A callback never
> selects speech/action itself, and `Work Reconciliation` is not a mandatory
> cognitive stage.
>
> Safe side-effect-free reads may start before GA finishes when their declared
> Capability contract permits it. Terminal Evidence can then trigger a Planner
> decision while independent sibling Work is still running. Newly planned Work
> returns through the same trusted asynchronous Runtime; confirmation, privacy,
> safety, resource and provider contracts remain authoritative, and an internal
> event is never user consent. Background Social Attention remains optional
> body-only decoration attached to a concrete Main Activity and never delays or
> completes the primary Responsibility. Current implementation and qualification
> evidence are tracked separately in [Status](docs/STATUS.md).
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
Person / World
      │
  Perception
      ▼
Cognitive Gateway
      ▼
Goal Interpretation
      ▼
Responsibility / WHAT
      │
      ├───────────────────┐
      ▼                   ▼
Planner              Goal Association
fast/deep passes       Goal continuity
      │                   │
      ▼                   ▼
Plan / Activities    Canonical Goals
      │                   │
      └─────────┬─────────┘
                ▼
      Trusted Capability Runtime
                ▼
             Provider
                ▼
     asynchronous Runtime events   -- what happened
                │
          Host correlation
                ▼
             Evidence              -- what is true
                │
 Responsibility + Goal + Situation + Work + Evidence
                ▼
       meaningful state transition
                ▼
       CognitiveOpportunity
                ▼
          Planner re-entry
                │
     0..N Activity changes or none
                └──────────────→ Trusted Capability Runtime

Vocal/TTS is one Activity realization; Soridormi is a peer embodied Provider.
Protective Reflex stays deterministic and may stop/cancel without model wait.
```

The diagram above is the canonical ownership path. The complementary
[episode-centered Continuous Mind workflow](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#41412-human-like-behavior-emerges-across-time)
shows how conversation, Work, Evidence, correction, waiting, and reactivation overlap
over time to produce coherent human-like interaction without adding another semantic
authority.

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
- broader/bilingual audio quality, physical acoustic barge-in, hot-plug, and
  current-revision qualification against the declared warm interaction latency targets; and
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

The generated runtime manifest records the selected mode. Maintained modes use the single Goal-driven `apply` path and keep legacy direct-LLM
fallback disabled. Capability eligibility comes from typed provider contracts. See the
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
| Diagnostic cognition | cognitive runtime disabled or report-only | Fail-closed / evidence-only diagnostics; never a legacy semantic fallback |
| Goal-driven speech | cognitive apply on, Soridormi body provider off | Common safe base; eligible work comes from typed Goal/Capability contracts |
| Goal-driven MuJoCo | cognitive apply on, Soridormi body provider enabled | Maintained simulator launcher; body work is available only through declared provider capabilities |
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
- normal natural-language cognition goes through model-authored typed meaning;
  Goal Interpretation owns WHAT, Goal Association owns canonical Goal continuity,
  and Fast/Deep Planner owns HOW plus every user-facing Communicative Activity;
  the Host validates, schedules, and realizes those Activities without becoming
  a second response author;
- simulation exemptions never authorize hardware;
- physical execution stays default-off and Soridormi-owned;
- implementation, automated verification, target validation, and release
  readiness are reported separately.

## Repository

| Path | Responsibility |
|---|---|
| `orchestrator/` | Host audio, interruption, conversation state, and Trusted Capability Runtime |
| `agent/app/cognitive_core/goal_interpreter/` | Goal Interpretation implementation: provider-neutral Responsibility meaning only |
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
