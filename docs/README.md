# Documentation Index and Governance

Chromie documentation is organized by ownership. A fact should have one
authoritative home and other documents should link to it rather than repeat it.

## Authority order

The authority list, its precedence order and the archive rules are owned by
[Documentation Authority](DOCUMENTATION_AUTHORITY.md), which mirrors the
machine-readable `config/documentation_authority.json`. Component documents and
decision documents rank below every listed authority. When documents disagree,
correct the lower-authority document.

## Document ownership

| Question | Owner |
|---|---|
| What is Chromie trying to become? | `docs/PROJECT_CHARTER.md` |
| What owns ordinary communication in the accepted target? | [Social Cognition in the Project Charter](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14); [migration lifecycle](COGNITIVE_TURN_LOOP.md#social-cognition-lifecycle) and [implementation status](STATUS.md#social-cognition-migration) |
| What admits interaction input before semantic cognition? | `docs/COGNITIVE_GATEWAY.md` |
| What lifecycle carries one admitted turn through execution evidence and a final response? | `docs/COGNITIVE_TURN_LOOP.md` |
| What exists and what evidence is retained? | `docs/STATUS.md` |
| What delivery line is next and what closes it? | `ROADMAP.md` |
| What is the active Issue and where should development resume? | `DEVELOPMENT_CHECKPOINT.md` |
| What exact commands, runtime identities, and private evidence paths resume the current checkpoint? | `HANDOFF.md` |
| How do I install, run, inspect, or recover it? | `CHROMIE_RUNBOOK.md` |
| What does an environment variable mean? | `docs/CONFIGURATION.md` |
| What endpoints and contracts exist? | `docs/API_REFERENCE.md` |
| What trace artifacts exist, how do Runtime Trace, Events, Episodes and Scenario Candidates relate, and what contract must trace items obey? | `docs/RUNTIME_OBSERVABILITY.md` |
| How should a module add trace instrumentation? | `docs/RUNTIME_OBSERVABILITY_OPERATIONS.md` |
| How are accelerator observations, retained latency reports, and regression gates produced? | `docs/ACCELERATOR_LATENCY_EVIDENCE.md` |
| How is foreground-priority LLM runtime contention qualified without changing semantic authority? | `docs/ACCELERATOR_LATENCY_EVIDENCE.md` |
| What contract and evidence govern TTS backend selection? | `docs/TTS_PROVIDER_EVALUATION.md` |
| What validation supports a claim? | `docs/ACCEPTANCE.md` and `docs/USER_OUTCOME_ACCEPTANCE.md` |
| What cognitive principles govern goals, continuity, planning, and execution? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` |
| How do Agents, Agent Skills, Plans, and Capabilities differ? | `docs/AGENT_SKILLS_ARCHITECTURE.md` |
| Where is current Agent Skill delivery work tracked? | `ROADMAP.md` and `docs/STATUS.md` |
| How is the goal-driven runtime enabled, observed, evidenced, and rolled back? | `docs/COGNITIVE_RUNTIME_ROLLOUT.md` |
| How is the active Gateway/Core migration qualified against live services and MuJoCo? | `docs/COGNITIVE_GATEWAY_CORE_QUALIFICATION.md` |
| What governs multi-goal Planner Work? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md`, `docs/WORK_DAG.md` and `docs/API_REFERENCE.md` |
| Which component owns semantic planning for each entrypoint? | `docs/SEMANTIC_AUTHORITY.md` |
| What development process is required for interaction behavior? | `docs/SCENARIO_DRIVEN_DEVELOPMENT.md` |
| What method governs semantic model-role qualification and any evidenced prompt optimization? | `docs/LLM_PROMPT_QUALIFICATION_METHOD.md` |
| What causal explanation, prompt/output inspection, and LLM-versus-workflow attribution must accompany every defect fix? | `CONTRIBUTING.md`, grounded in `docs/PROJECT_CHARTER.md`; interaction-specific detail lives in `docs/SCENARIO_DRIVEN_DEVELOPMENT.md` |
| What architecture organizes module, integration, E2E, stress, and regression evaluation? | `docs/CHROMIE_BENCHMARK_SUITE.md` |
| Where is remaining benchmark, structural and evidence work tracked? | `ROADMAP.md` |
| How are maintained runtime failures classified and made explicit? | `docs/RUNTIME_FAILURE_PATHS.md` |
| Which stable source, architecture, Agent Skill, contract, and local deployment rules are executable? | `docs/REPOSITORY_ENGINEERING_POLICIES.md` |
| Which Python static-analysis ratchets are active? | `docs/STATIC_ANALYSIS.md` |
| How are maintained scenarios migrated and episode candidates reviewed? | `docs/BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md` |
| How are stress workloads and behavior distributions executed and compared? | `docs/STRESS_BENCHMARK_EVALUATION.md` |
| How are semantic scenarios executed at distinct E2E evidence levels? | `docs/E2E_BENCHMARK_EXECUTION.md` |
| Where is the reviewed Social Attention benchmark dataset? | `benchmarks/datasets/social_attention/README.md` |
| Where are the isolated daily-life User Meaning Interpretation candidate scenarios and their review boundary? | `benchmarks/datasets/goal_interpretation_daily_life/README.md` |
| Where are the daily-life Goal Association continuity scenarios and their contract-gap boundary? | `benchmarks/datasets/goal_association_daily_life/README.md` |
| Where are the bilingual Planner workflow, contract, architecture, and prompt qualification scenarios? | `benchmarks/datasets/fast_planner_daily_life/README.md` |
| How is the automated suite kept free of stale wrappers and duplicate coverage? | `docs/TEST_SUITE_MAINTENANCE.md` |
| Which facts belong to behavior, architecture-policy, or generated-artifact tests? | `docs/TEST_OWNERSHIP.md` |
| What keeps visible robot behavior natural and grounded? | `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md` |
| How are embodiment-independent, personality-driven language and body cues planned? | `docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md` |
| How do Vocal and Activity coordinate while SC-owned Social Attention decorates behavior? | `docs/EXECUTION_LANES_AND_COORDINATION.md` |
| How is behavior testing reconstructed around general abilities? | `docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md` |
| How are references such as “那边” scoped and how may verified prior results be retrieved? | `docs/DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md` |
| How do I operate the current simulator workflow? | `docs/USER_MANUAL.md` |
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
- [Latest Handoff](../HANDOFF.md)
- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md)
- [Operations Runbook](../CHROMIE_RUNBOOK.md)
- [Documentation Authority](DOCUMENTATION_AUTHORITY.md)

This list matches `core_reading_path` in `config/documentation_authority.json`.
Use the catalog below only for the component or evidence boundary being
changed. Listing a document here does not by itself justify keeping it; a
specialized document needs a real component, operator, or mechanical-contract owner.

## Architecture and runtime

- [Runtime Observability Contract](RUNTIME_OBSERVABILITY.md)
- [Runtime Observability Operations](RUNTIME_OBSERVABILITY_OPERATIONS.md)
- [Accelerator Telemetry and Latency Evidence Gates](ACCELERATOR_LATENCY_EVIDENCE.md)
- [Cognitive Integrity Events](COGNITIVE_INTEGRITY_EVENTS.md)
- [Chromie Data Loop: Interaction Evidence and Scenario Candidates](SCENARIO_CANDIDATE_DATA_LOOP.md)
- [Benchmark Suite](../benchmarks/README.md)
- [Benchmark E2E Adapter Contract](../benchmarks/e2e/README.md)
- [Reviewed Social Attention Dataset](../benchmarks/datasets/social_attention/README.md)
- [User Meaning Interpretation Daily-Life Dataset](../benchmarks/datasets/goal_interpretation_daily_life/README.md)
- [Goal Association Daily-Life Dataset](../benchmarks/datasets/goal_association_daily_life/README.md)
- [Planner Daily-Life Qualification Work Area](../benchmarks/datasets/fast_planner_daily_life/README.md)
- [Stress Benchmark Workloads](../benchmarks/stress/README.md)
- [Stress and Behavior-Distribution Evaluation](STRESS_BENCHMARK_EVALUATION.md)
- [Agent](../agent/README.md)
- [Orchestrator](../orchestrator/README.md)
- [ASR](../asr/README.md)
- [TTS](../tts/README.md)
- [TTS Provider Contract and Evaluation](TTS_PROVIDER_EVALUATION.md)
- [Capability Result Evidence Re-entry](CAPABILITY_RESULT_EVIDENCE_REENTRY.md)
- [Shared Packages](../shared/README.md)
- [Capability Manifests](../capabilities/README.md)
- [Agent Skill Packages](../agent-skills/README.md)
- [Grounded External Information Skill](../agent-skills/grounded-external-information/SKILL.md)
  - [Planner projection](../agent-skills/grounded-external-information/projections/fast_planner.md)
- [Weather Information Skill](../agent-skills/weather-information/SKILL.md)
  - [Planner projection](../agent-skills/weather-information/projections/fast_planner.md)
- [Legacy Hardware Daemon](../hardware/README.md)
- [Hardware Profiles](../HARDWARE_PROFILES.md)

## Interaction and execution

- [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
- [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md)
- [Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md)
- [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md)
- [Semantic Model-Role Qualification and Prompt Optimization Method](LLM_PROMPT_QUALIFICATION_METHOD.md)
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
- [Chromie Mind, Principles, and Experience](CHROMIE_MIND.md)
- [Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md)
- [Experience-To-Ability Learning](EXPERIENCE_TO_ABILITY_LEARNING.md)
- [Memory Extraction and Prompt Context](MEMORY_EXTRACTION.md)
- [Adding Agent and Tool Capabilities](ADDING_AGENT_CAPABILITIES.md)
- [WorkDAG and DAGEngine](WORK_DAG.md)
- [SenseVoice ASR](SENSEVOICE_ASR.md)
- [Conversation State](CONVERSATION_STATE.md)
- [Resource Acquisition and Delivery](RESOURCE_ACQUISITION_AND_DELIVERY.md)
- [Scoped Discourse Referents and Verified Tool Memory](DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md)

## Operations and release

- [Bilingual OuteTTS Speaker Guide](../CHROMIE_BILINGUAL_SPEAKER_GUIDE.md)
- [Built-In TTS Voice Catalog](../assets/tts/voices/README.md)
- [Owner-Editable Mind Profile](../config/mind/README.md)
- [Deployment](DEPLOYMENT.md)
- [Voice-to-MuJoCo Quick Start (Chinese)](VOICE_MUJOCO_QUICKSTART.zh-CN.md)
- [User Manual](USER_MANUAL.md)
- [Configuration Reference](CONFIGURATION.md)
- [API Reference](API_REFERENCE.md)
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
- [Semantic Transaction Qualification Skill](../.agents/skills/qualify-chromie-semantic-transaction/SKILL.md): executable entrypoint for frozen-transaction qualification and evidenced owner repair
- [Chromie Delivery Handoff Skill](../.agents/skills/chromie-delivery-handoff/SKILL.md): Git delivery workflow for keeping the checkpoint and handoff truthful
- [Chromie Patch Git Commands Skill](../.agents/skills/chromie-patch-git-commands/SKILL.md): copy-ready review, commit, and push handoff commands

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
