# Documentation Index and Governance

Chromie documentation is organized by ownership. A fact should have one
authoritative home and other documents should link to it rather than repeat it.

## Authority order

1. [Project Charter](PROJECT_CHARTER.md) - stable mission, ownership, principles,
   and non-goals.
2. [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md) -
   root-cause rules for natural, grounded robot behavior and valid interaction
   evidence.
3. [Current Status](STATUS.md) - implementation, automated verification, target
   validation, and release readiness.
4. [Roadmap](../ROADMAP.md) - milestone order and exit criteria.
5. [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) - short resume point.
6. [Operations Runbook](../CHROMIE_RUNBOOK.md) - commands and recovery.
7. [Configuration](CONFIGURATION.md), [API](API_REFERENCE.md), and
   [Acceptance](ACCEPTANCE.md) - interface and evidence details.
8. Component documents - local implementation boundaries.
9. Decision documents - rationale for an established design.

When documents disagree, correct the lower-authority document.

## Document ownership

| Question | Owner |
|---|---|
| What is Chromie trying to become? | `docs/PROJECT_CHARTER.md` |
| What exists and what evidence is retained? | `docs/STATUS.md` |
| What milestone is next and what closes it? | `ROADMAP.md` |
| Where should development resume? | `DEVELOPMENT_CHECKPOINT.md` |
| How do I install, run, inspect, or recover it? | `CHROMIE_RUNBOOK.md` |
| What does an environment variable mean? | `docs/CONFIGURATION.md` |
| What endpoints and contracts exist? | `docs/API_REFERENCE.md` |
| What retained trace artifacts can the CLI inspect? | `docs/TRACE_SCHEMA.md` |
| What validation supports a claim? | `docs/ACCEPTANCE.md` |
| What keeps visible robot behavior natural and grounded? | `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md` |
| How is behavior testing reconstructed around general abilities? | `docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md` |
| How do I operate the current simulator workflow? | `docs/USER_MANUAL.md` |
| Where should a new collaborator resume? | `docs/HANDOFF.md` |
| What can be published and supported? | `docs/RELEASE.md` |
| What changed? | `CHANGELOG.md` |

README files should describe their component. They should not carry global
milestone histories or duplicate complete setup and acceptance procedures.

## Start here

- [Project README](../README.md)
- [Chinese Guide](PROJECT_GUIDE.zh-CN.md)
- [Project Charter](PROJECT_CHARTER.md)
- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [Current Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [User Manual](USER_MANUAL.md)
- [Project Handoff](HANDOFF.md)

## Architecture and runtime

- [Agent](../agent/README.md)
- [Orchestrator](../orchestrator/README.md)
- [Router](../router/README.md)
- [ASR](../asr/README.md)
- [TTS](../tts/README.md)
- [Shared Packages](../shared/README.md)
- [Capability Manifests](../capabilities/README.md)
- [Legacy Hardware Daemon](../hardware/README.md)
- [Hardware Profiles](../HARDWARE_PROFILES.md)

## Interaction and execution

- [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md)
- [Interaction Agent and Skill Runtime](interaction_agent_skill_runtime.md)
- [Chromie High-Level Ability Registry](chromie_ability_registry.md)
- [Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md)
- [Chromie Mind, Principles, and Experience](chromie_mind.md)
- [Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md)
- [Experience-To-Ability Learning](EXPERIENCE_TO_ABILITY_LEARNING.md)
- [Memory Extraction and Prompt Context](MEMORY_EXTRACTION.md)
- [Agent Capability Registry](agent_capability_registry.md)
- [Adding Agent and Tool Capabilities](ADDING_AGENT_CAPABILITIES.md)
- [Model-Assisted Routing Guardrails](MODEL_ASSISTED_ROUTING_GUARDRAILS.md)
- [Catalog-Aware Router Tiers](CATALOG_AWARE_ROUTER_TIERS.md)
- [Quick Router Task Planning](QUICK_ROUTER_TASK_PLANNING.md)
- [Orchestrator Task Proposal Merge](ORCHESTRATOR_TASK_PROPOSAL_MERGE.md)
- [TaskGraph](agent_task_graph.md)
- [Trace Schema](TRACE_SCHEMA.md)
- [Chromie/Soridormi Task-Agent Plan](CHROMIE_SORIDORMI_TASK_AGENT_IMPLEMENTATION_PLAN.md)
- [Chromie/Soridormi Proposal Boundary Plan](CHROMIE_SORIDORMI_PROPOSAL_BOUNDARY_PLAN.md)
- [Developer Usability Tools Plan](DEVELOPER_USABILITY_TOOLS.md)
- [ASR Backend Migration Plan](ASR_BACKEND_MIGRATION.md)
- [TaskGraph Concurrency Decision](task_graph_concurrency_decision.md)
- [Conversation State](conversation_state.md)

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
- [0.0.1 Release Notes](../release/0.0.1.md)

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
