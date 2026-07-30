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
| What retained trace artifacts can the CLI inspect? | `docs/TRACE_SCHEMA.md` |
| How do Runtime Trace, Runtime Events, Episodes, and Scenario Candidates relate? | `docs/RUNTIME_OBSERVABILITY_ARCHITECTURE.md` |
| What common contract must runtime trace items obey? | `docs/RUNTIME_TRACE.md` |
| How should a module add trace instrumentation? | `docs/RUNTIME_TRACE_INSTRUMENTATION.md` |
| How are accelerator observations, retained latency reports, and regression gates produced? | `docs/ACCELERATOR_LATENCY_EVIDENCE.md` |
| What contract and evidence govern TTS backend selection? | `docs/TTS_PROVIDER_EVALUATION.md` |
| What validation supports a claim? | `docs/ACCEPTANCE.md` and `docs/USER_OUTCOME_ACCEPTANCE.md` |
| What cognitive principles govern goals, continuity, planning, and execution? | `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` |
| How do Agents, Agent Skills, Plans, and Capabilities differ? | `docs/AGENT_SKILLS_ARCHITECTURE.md` |
| What is the Agent Skills implementation issue and delivery order? | `docs/AGENT_SKILLS_IMPLEMENTATION_PLAN.md` |
| How is the goal-driven runtime enabled, observed, evidenced, and rolled back? | `docs/COGNITIVE_RUNTIME_ROLLOUT.md` |
| How is the active Gateway/Core migration qualified against live services and MuJoCo? | `docs/COGNITIVE_GATEWAY_CORE_QUALIFICATION.md` |
| What is the implementation contract for terminal Fast Planner multi-goal planning? | `docs/FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md` |
| Which component owns semantic planning for each entrypoint? | `docs/SEMANTIC_AUTHORITY.md` |
| What development process is required for interaction behavior? | `docs/SCENARIO_DRIVEN_DEVELOPMENT.md` |
| What architecture organizes module, integration, E2E, stress, and regression evaluation? | `docs/CHROMIE_BENCHMARK_SUITE.md` |
| What staged work builds that benchmark architecture? | `docs/CHROMIE_BENCHMARK_IMPLEMENTATION_PLAN.md` |
| Which engineering-sustainability Issues are accepted, ordered, deferred, or rejected? | `docs/REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md` |
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
| How is behavior testing reconstructed around general abilities? | `docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md` |
| How are semantic goals preserved and revised across turns? | `docs/SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md` |
| How are references such as “那边” scoped and how may verified prior results be retrieved? | `docs/DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md` |
| How do I operate the current simulator workflow? | `docs/USER_MANUAL.md` |
| Where should a new collaborator resume? | `docs/HANDOFF.md` |
| How are development artifacts packaged? | `docs/RELEASE.md` |
| What changed? | `CHANGELOG.md` |

README files should describe their component. They should not carry global
milestone histories or duplicate complete setup and acceptance procedures.

## Start here

- [Project README](../README.md)
- [Chinese Guide](PROJECT_GUIDE.zh-CN.md)
- [Project Charter](PROJECT_CHARTER.md)
- [Documentation Authority](DOCUMENTATION_AUTHORITY.md)
- [Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md)
- [Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md)
- [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md)
- [VoiceAssistant Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md)
- [Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md)
- [Static Analysis Ratchets](STATIC_ANALYSIS.md)
- [Runtime Observability Architecture](RUNTIME_OBSERVABILITY_ARCHITECTURE.md)
- [Runtime Trace Contract](RUNTIME_TRACE.md)
- [Accelerator Telemetry and Latency Evidence Gates](ACCELERATOR_LATENCY_EVIDENCE.md)
- [TTS Provider Contract and Evaluation](TTS_PROVIDER_EVALUATION.md)
- [Tool Result Interpretation](TOOL_RESULT_INTERPRETATION.md)
- [Built-In TTS Voice Catalog](../assets/tts/voices/README.md)
- [Owner-Editable Mind Profile](../config/mind/README.md)
- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
- [Benchmark Suite](../benchmarks/README.md)
- [Stress Benchmark Workloads](../benchmarks/stress/README.md)
- [Benchmark E2E Adapter Contract](../benchmarks/e2e/README.md)
- [Reviewed Social Attention Dataset](../benchmarks/datasets/social_attention/README.md)
- [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Agent Skills Implementation Plan](AGENT_SKILLS_IMPLEMENTATION_PLAN.md)
- [Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md)
- [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
- [Fast Planner Multi-Goal Contract Path](FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md)
- [Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md)
- [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md)
- [Chromie Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md)
- [Chromie Benchmark Implementation Plan](CHROMIE_BENCHMARK_IMPLEMENTATION_PLAN.md)
- [Benchmark Scenario Migration and Continuous Review](BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md)
- [Maintained Scenario Migration](../benchmarks/scenarios/README.md)
- [Continuous Scenario Mining and Review](../benchmarks/mining/README.md)
- [End-to-End Benchmark Execution](E2E_BENCHMARK_EXECUTION.md)
- [Social Attention Baseline Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md)
- [Stress and Behavior-Distribution Evaluation](STRESS_BENCHMARK_EVALUATION.md)
- [Test Suite Maintenance](TEST_SUITE_MAINTENANCE.md)
- [Test Ownership](TEST_OWNERSHIP.md)
- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [User-Outcome Acceptance Framework](USER_OUTCOME_ACCEPTANCE.md)
- [Social Attention Behavior Domain](SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md)
- [Current Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [User Manual](USER_MANUAL.md)
- [Project Handoff](HANDOFF.md)

## Architecture and runtime

- [Runtime Observability Architecture](RUNTIME_OBSERVABILITY_ARCHITECTURE.md)
- [Runtime Trace Contract](RUNTIME_TRACE.md)
- [Runtime Trace Instrumentation Guide](RUNTIME_TRACE_INSTRUMENTATION.md)
- [Session, Execution, and Audio Runtime Trace](SESSION_EXECUTION_AUDIO_TRACE.md)
- [Input, Action, and Idle Trace Coverage](INPUT_ACTION_IDLE_TRACE.md)
- [Resource, Recovery, and Trace Retention](RESOURCE_RECOVERY_TRACE_RETENTION.md)
- [Accelerator Telemetry and Latency Evidence Gates](ACCELERATOR_LATENCY_EVIDENCE.md)
- [Runtime Event Architecture](RUNTIME_EVENT_ARCHITECTURE.md)
- [Cognitive Integrity Events](COGNITIVE_INTEGRITY_EVENTS.md)
- [Scenario Candidate Data Loop](SCENARIO_CANDIDATE_DATA_LOOP.md)
- [Cognitive Gateway](COGNITIVE_GATEWAY.md)
- [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md)
- [Benchmark Suite](../benchmarks/README.md)
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
- [Benchmark Suite](../benchmarks/README.md)
- [Stress Benchmark Workloads](../benchmarks/stress/README.md)
- [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)
- [Agent Skills Implementation Plan](AGENT_SKILLS_IMPLEMENTATION_PLAN.md)
- [Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md)
- [Fast Planner Multi-Goal Contract Path](FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md)
- [Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md)
- [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md)
- [Chromie Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md)
- [Chromie Benchmark Implementation Plan](CHROMIE_BENCHMARK_IMPLEMENTATION_PLAN.md)
- [Benchmark Scenario Migration and Continuous Review](BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md)
- [Maintained Scenario Migration](../benchmarks/scenarios/README.md)
- [Continuous Scenario Mining and Review](../benchmarks/mining/README.md)
- [Test Suite Maintenance](TEST_SUITE_MAINTENANCE.md)
- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md)
- [User-Outcome Acceptance Framework](USER_OUTCOME_ACCEPTANCE.md)
- [Social Attention Behavior Domain](SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md)
- [Interaction Agent and Skill Runtime](interaction_agent_skill_runtime.md)
- [Chromie High-Level Ability Registry](chromie_ability_registry.md)
- [Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md)
- [Chromie Mind, Principles, and Experience](chromie_mind.md)
- [Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md)
- [Experience-To-Ability Learning](EXPERIENCE_TO_ABILITY_LEARNING.md)
- [Memory Extraction and Prompt Context](MEMORY_EXTRACTION.md)
- [Agent Capability Registry](agent_capability_registry.md)
- [Adding Agent and Tool Capabilities](ADDING_AGENT_CAPABILITIES.md)
- [Model-Assisted Cognitive Guardrails](MODEL_ASSISTED_COGNITIVE_GUARDRAILS.md)
- [Catalog-Aware Goal Interpretation Tiers](CATALOG_AWARE_GOAL_INTERPRETATION.md)
- [Fast Goal Interpreter Task Planning](FAST_COGNITIVE_PLANNING.md)
- [Orchestrator Task Proposal Merge](ORCHESTRATOR_TASK_PROPOSAL_MERGE.md)
- [Semantic Task Continuity and Situational Planning](SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md)
- [TaskGraph](agent_task_graph.md)
- [Trace Schema](TRACE_SCHEMA.md)
- [Chromie/Soridormi Task-Agent Plan](CHROMIE_SORIDORMI_TASK_AGENT_IMPLEMENTATION_PLAN.md)
- [Chromie/Soridormi Proposal Boundary Plan](CHROMIE_SORIDORMI_PROPOSAL_BOUNDARY_PLAN.md)
- [Developer Usability Tools Plan](DEVELOPER_USABILITY_TOOLS.md)
- [SenseVoice ASR](SENSEVOICE_ASR.md)
- [TaskGraph Concurrency Decision](task_graph_concurrency_decision.md)
- [Conversation State](conversation_state.md)
- [Scoped Discourse Referents and Verified Tool Memory](DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md)

## Operations and release

- [Bilingual OuteTTS Speaker Guide](../CHROMIE_BILINGUAL_SPEAKER_GUIDE.md)
- [Deployment](DEPLOYMENT.md)
- [Voice-to-MuJoCo Quick Start (Chinese)](VOICE_MUJOCO_QUICKSTART.zh-CN.md)
- [User Manual](USER_MANUAL.md)
- [Project Handoff](HANDOFF.md)
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


## Historical archives

These files preserve detailed narrative and are not current authority:

- [Changelog Archive — through 2026-07-30](../CHANGELOG_ARCHIVE_2026-07-30.md)
- [Development Checkpoint Archive — 2026-07-30](../DEVELOPMENT_CHECKPOINT_ARCHIVE_2026-07-30.md)
- [Implementation Status Archive — 2026-07-30](STATUS_ARCHIVE_2026-07-30.md)
