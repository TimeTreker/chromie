# Documentation Index and Governance

Chromie documentation is organized by ownership. A fact should have one
authoritative home and other documents should link to it rather than repeat it.

## Authority order

The machine-readable ownership map and archive rules are defined in [Documentation Authority](DOCUMENTATION_AUTHORITY.md).

1. [Project Charter](PROJECT_CHARTER.md) - stable mission, ownership, principles,
   and non-goals.
2. [Cognitive Gateway](COGNITIVE_GATEWAY.md) - authoritative target boundary
   for interaction input, protective reflexes, attention review, context
   assembly, and turn admission.
3. [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md) - executable manager-owned
   turn lifecycle from admission through delegation, outcome reconciliation,
   and final response.
4. [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) -
   cognitive constitution for goal continuity, multi-goal planning, validation, and interaction.
5. [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md) -
   Agent, Agent Skill, Plan, Capability, discovery, and authority boundaries.
6. [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md) -
   root-cause rules for natural, grounded robot behavior and valid interaction
   evidence.
7. [Current Status](STATUS.md) - implementation, automated verification, target
   validation, and release readiness.
8. [Roadmap](../ROADMAP.md) - milestone order and exit criteria.
9. [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) - short resume point.
10. [Operations Runbook](../CHROMIE_RUNBOOK.md) - commands and recovery.
11. [Configuration](CONFIGURATION.md), [API](API_REFERENCE.md), and
   [Acceptance](ACCEPTANCE.md) - interface and evidence details.
12. Component documents - local implementation boundaries.
13. Decision documents - rationale for an established design.

When documents disagree, correct the lower-authority document.

## Document ownership

| Question | Owner |
|---|---|
| What is Chromie trying to become? | `docs/PROJECT_CHARTER.md` |
| What admits interaction input before semantic cognition? | `docs/COGNITIVE_GATEWAY.md` |
| What lifecycle carries one admitted turn through execution evidence and a final response? | `docs/COGNITIVE_TURN_LOOP.md` |
| What exists and what evidence is retained? | `docs/STATUS.md` |
| What milestone is next and what closes it? | `ROADMAP.md` |
| Where should development resume? | `DEVELOPMENT_CHECKPOINT.md` |
| How do I install, run, inspect, or recover it? | `CHROMIE_RUNBOOK.md` |
| What does an environment variable mean? | `docs/CONFIGURATION.md` |
| What endpoints and contracts exist? | `docs/API_REFERENCE.md` |
| What retained trace artifacts can the CLI inspect? | `docs/RUNTIME_OBSERVABILITY.md` |
| How do Runtime Trace, Runtime Events, Episodes, and Scenario Candidates relate? | `docs/RUNTIME_OBSERVABILITY.md` |
| What common contract must runtime trace items obey? | `docs/RUNTIME_OBSERVABILITY.md` |
| How should a module add trace instrumentation? | `docs/RUNTIME_OBSERVABILITY_OPERATIONS.md` |
| How are accelerator observations, retained latency reports, and regression gates produced? | `docs/ACCELERATOR_LATENCY_EVIDENCE.md` |
| What contract and evidence govern TTS backend selection? | `docs/TTS_PROVIDER_EVALUATION.md` |
| What validation supports a claim? | `docs/ACCEPTANCE.md` and `docs/USER_OUTCOME_ACCEPTANCE.md` |
| What cognitive principles govern goals, continuity, planning, and execution? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` |
| How do Agents, Agent Skills, Plans, and Capabilities differ? | `docs/AGENT_SKILLS_ARCHITECTURE.md` |
| Where is current Agent Skill delivery work tracked? | `ROADMAP.md` and `docs/STATUS.md` |
| How is the goal-driven runtime enabled, observed, evidenced, and rolled back? | `docs/COGNITIVE_RUNTIME_ROLLOUT.md` |
| How is the active Gateway/Core migration qualified against live services and MuJoCo? | `docs/COGNITIVE_GATEWAY_CORE_QUALIFICATION.md` |
| What governs terminal Fast Planner multi-goal planning? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` and `docs/API_REFERENCE.md` |
| Which component owns semantic planning for each entrypoint? | `docs/SEMANTIC_AUTHORITY.md` |
| What development process is required for interaction behavior? | `docs/SCENARIO_DRIVEN_DEVELOPMENT.md` |
| What causal explanation and evidence must accompany every defect fix? | `CONTRIBUTING.md`, grounded in `docs/PROJECT_CHARTER.md`; interaction-specific detail lives in `docs/SCENARIO_DRIVEN_DEVELOPMENT.md` |
| What architecture organizes module, integration, E2E, stress, and regression evaluation? | `docs/CHROMIE_BENCHMARK_SUITE.md` |
| Which tests use exact fixture truth and which require reviewed semantic judgment? | `docs/CHROMIE_BENCHMARK_SUITE.md` Section 7.3 |
| Where is remaining benchmark delivery work tracked? | `ROADMAP.md` |
| Which structural simplification and evidence work remains? | `ROADMAP.md` |
| How are maintained runtime failures classified and made explicit? | `docs/RUNTIME_FAILURE_PATHS.md` |
| Which stable source, architecture, Agent Skill, contract, and local deployment rules are executable? | `docs/REPOSITORY_ENGINEERING_POLICIES.md` |
| Which Python static-analysis ratchets are active? | `docs/STATIC_ANALYSIS.md` |
| How are maintained scenarios migrated and episode candidates reviewed? | `docs/BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md` |
| How are stress workloads and behavior distributions executed and compared? | `docs/STRESS_BENCHMARK_EVALUATION.md` |
| How are semantic scenarios executed at distinct E2E evidence levels? | `docs/E2E_BENCHMARK_EXECUTION.md` |
| Where is the reviewed Social Attention benchmark dataset? | `benchmarks/datasets/social_attention/README.md` |
| How is the automated suite kept free of stale wrappers and duplicate coverage? | `docs/TEST_SUITE_MAINTENANCE.md` |
| Which facts belong to behavior, architecture-policy, or generated-artifact tests? | `docs/TEST_OWNERSHIP.md` |
| What keeps visible robot behavior natural and grounded? | `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md` |
| How are embodiment-independent, personality-driven language and body cues planned? | `docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md` |
| How do Social Attention, Speaking, Activity, and Soridormi body lanes coordinate concurrently? | `docs/EXECUTION_LANES_AND_COORDINATION.md` |
| How is behavior testing reconstructed around general abilities? | `docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md` |
| How are semantic goals preserved and revised across turns? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` |
| How are references such as “那边” scoped and how may verified prior results be retrieved? | `docs/DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md` |
| How do I operate the current simulator workflow? | `docs/USER_MANUAL.md` |
| Where should a new collaborator resume? | `DEVELOPMENT_CHECKPOINT.md` |
| How are development artifacts packaged? | `docs/RELEASE.md` |
| What changed? | `CHANGELOG.md` |

README files should describe their component. They should not carry global
milestone histories or duplicate complete setup and acceptance procedures.

## Core reading path

A new collaborator should not need the complete reference catalog. Read these
in order:

- [Project README](../README.md)
- [Chinese Guide](PROJECT_GUIDE.zh-CN.md)
- [Project Charter](PROJECT_CHARTER.md)
- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [Current Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Execution Lanes and Coordination](EXECUTION_LANES_AND_COORDINATION.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md)
- [Operations Runbook](../CHROMIE_RUNBOOK.md)
- [Documentation Authority](DOCUMENTATION_AUTHORITY.md)

Use the catalog below only for the component or evidence boundary being
changed. Listing a document here does not by itself justify keeping it; the
queued documentation-surface Issue will require a real component, operator, or
mechanical-contract owner.

## Architecture and runtime

- [Runtime Observability Contract](RUNTIME_OBSERVABILITY.md)
- [Runtime Observability Operations](RUNTIME_OBSERVABILITY_OPERATIONS.md)

- [Accelerator Telemetry and Latency Evidence Gates](ACCELERATOR_LATENCY_EVIDENCE.md)
- [Cognitive Integrity Events](COGNITIVE_INTEGRITY_EVENTS.md)
- [Chromie Data Loop: Interaction Evidence and Scenario Candidates](SCENARIO_CANDIDATE_DATA_LOOP.md)
- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Benchmark Suite](../benchmarks/README.md)
- [Benchmark E2E Adapter Contract](../benchmarks/e2e/README.md)
- [Reviewed Social Attention Dataset](../benchmarks/datasets/social_attention/README.md)
- [Stress Benchmark Workloads](../benchmarks/stress/README.md)
- [Stress and Behavior-Distribution Evaluation](STRESS_BENCHMARK_EVALUATION.md)
- [Agent](../agent/README.md)
- [Orchestrator](../orchestrator/README.md)
- [ASR](../asr/README.md)
- [TTS](../tts/README.md)
- [TTS Provider Contract and Evaluation](TTS_PROVIDER_EVALUATION.md)
- [Tool Result Interpretation](TOOL_RESULT_INTERPRETATION.md)
- [Shared Packages](../shared/README.md)
- [Capability Manifests](../capabilities/README.md)
- [Agent Skill Packages](../agent-skills/README.md)
- [Grounded External Information Skill](../agent-skills/grounded-external-information/SKILL.md)
  - [Goal Association projection](../agent-skills/grounded-external-information/projections/goal_association.md)
  - [Fast Planner projection](../agent-skills/grounded-external-information/projections/fast_planner.md)
  - [Deep Planner projection](../agent-skills/grounded-external-information/projections/deep_planner.md)
  - [Response Composer projection](../agent-skills/grounded-external-information/projections/response_composer.md)
  - [Tool Result Interpreter projection](../agent-skills/grounded-external-information/projections/tool_result_interpreter.md)
- [Weather Information Skill](../agent-skills/weather-information/SKILL.md)
  - [Goal Association projection](../agent-skills/weather-information/projections/goal_association.md)
  - [Fast Planner projection](../agent-skills/weather-information/projections/fast_planner.md)
  - [Deep Planner projection](../agent-skills/weather-information/projections/deep_planner.md)
  - [Response Composer projection](../agent-skills/weather-information/projections/response_composer.md)
  - [Tool Result Interpreter projection](../agent-skills/weather-information/projections/tool_result_interpreter.md)
- [Legacy Hardware Daemon](../hardware/README.md)
- [Hardware Profiles](../HARDWARE_PROFILES.md)

## Interaction and execution

- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
- [Benchmark Suite](../benchmarks/README.md)
- [Stress Benchmark Workloads](../benchmarks/stress/README.md)
- [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md)
- [Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md)
- [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md)
- [Chromie Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md)
- [Benchmark Scenario Migration and Continuous Review](BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md)
- [Maintained Scenario Migration](../benchmarks/scenarios/README.md)
- [Continuous Scenario Mining and Review](../benchmarks/mining/README.md)
- [End-to-End Benchmark Execution](E2E_BENCHMARK_EXECUTION.md)
- [Test Suite Maintenance](TEST_SUITE_MAINTENANCE.md)
- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md)
- [User-Outcome Acceptance Framework](USER_OUTCOME_ACCEPTANCE.md)
- [Social Attention Behavior Domain](SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md)
- [Execution Lanes and Coordination](EXECUTION_LANES_AND_COORDINATION.md)
- [Social Attention Baseline Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md)
- [Chromie High-Level Ability Registry](chromie_ability_registry.md)
- [Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md)
- [Chromie Mind, Principles, and Experience](chromie_mind.md)
- [Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md)
- [Experience-To-Ability Learning](EXPERIENCE_TO_ABILITY_LEARNING.md)
- [Memory Extraction and Prompt Context](MEMORY_EXTRACTION.md)
- [Adding Agent and Tool Capabilities](ADDING_AGENT_CAPABILITIES.md)
- [TaskGraph](agent_task_graph.md)
- [Trace Schema](RUNTIME_OBSERVABILITY.md)
- [SenseVoice ASR](SENSEVOICE_ASR.md)
- [TaskGraph Concurrency Decision](task_graph_concurrency_decision.md)
- [Conversation State](conversation_state.md)
- [Scoped Discourse Referents and Verified Tool Memory](DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md)

## Operations and release

- [Bilingual OuteTTS Speaker Guide](../CHROMIE_BILINGUAL_SPEAKER_GUIDE.md)
- [Built-In TTS Voice Catalog](../assets/tts/voices/README.md)
- [Owner-Editable Mind Profile](../config/mind/README.md)
- [Deployment](DEPLOYMENT.md)
- [Voice-to-MuJoCo Quick Start (Chinese)](VOICE_MUJOCO_QUICKSTART.zh-CN.md)
- [User Manual](USER_MANUAL.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [Operations Runbook](../CHROMIE_RUNBOOK.md)
- [Configuration Reference](CONFIGURATION.md)
- [API Reference](API_REFERENCE.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [Behavior Scenario Fixtures](../scenarios/README.md)
- [Reference Robot Commissioning Checklist](ROBOT_COMMISSIONING.md)
- [Reference Robot Candidate Files](../commissioning/README.md)
- [Release and Packaging](RELEASE.md)
- [Release Assets](../release/README.md)
- [Development Scope](../release/development.md)

## Governance

- [Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md)
- [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md)
- [VoiceAssistant Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md)
- [Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md)
- [Static Analysis Ratchets](STATIC_ANALYSIS.md)
- [Test Ownership](TEST_OWNERSHIP.md)
- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)
- [Support](../SUPPORT.md)
- [Changelog](../CHANGELOG.md)
- [Coding Agent Guidance](../AGENTS.md)

## Update rules

Update the owning document in the same patch when changing:

- mission, ownership, or safety boundaries;
- milestone scope or exit criteria;
- implementation or evidence status;
- an API, schema, environment variable, default, or feature gate;
- setup, validation, recovery, support, or release behavior.

Use the four-axis vocabulary from `STATUS.md`. Do not use “done” to collapse
implementation, automated verification, target validation, and release
readiness.

Run:

```bash
python scripts/check_docs.py
./scripts/run_tests.sh
```

- [Resource Acquisition and Delivery](RESOURCE_ACQUISITION_AND_DELIVERY.md): provider-neutral physical and information resource Goals, peer Provider contracts, and completion evidence.
