# Documentation Index and Governance

This index defines where each kind of project information belongs. Keeping one
owner for each fact is the main defense against documentation drift.

## Authority order

1. [Current Implementation Status](STATUS.md) — what exists, what is tested,
   what has target evidence, and what is release ready.
2. [Roadmap](../ROADMAP.md) — milestone intent and exit criteria.
3. [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) — exact resume point
   for the current repository revision.
4. [Operations Runbook](../CHROMIE_RUNBOOK.md) — commands and recovery steps.
5. [Configuration Reference](CONFIGURATION.md) and
   [API Reference](API_REFERENCE.md) — deployed interfaces.
6. Component documents — local ownership and implementation boundaries.
7. Decision documents — rationale and historical design constraints.

When two documents disagree, update the lower-authority document. Do not hide a
status mismatch by changing only the README.

## Start here

- [Project README](../README.md)
- [Current Implementation Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Chinese Project Guide](PROJECT_GUIDE.zh-CN.md)
- [Operations Runbook](../CHROMIE_RUNBOOK.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [Release and Packaging](RELEASE.md)
- [Tracked Release Assets](../release/README.md)
- [v0.1.0-alpha.1 Candidate Notes](../release/v0.1.0-alpha.1.md)

## Architecture and runtime

- [Engineering Context](../LLM_CONTEXT.md)
- [Agent](../agent/README.md)
- [Router](../router/README.md)
- [Orchestrator](../orchestrator/README.md)
- [ASR](../asr/README.md)
- [TTS](../tts/README.md)
- [Shared Packages](../shared/README.md)
- [Legacy Hardware Daemon](../hardware/README.md)
- [Hardware Profiles](../HARDWARE_PROFILES.md)

## Interaction, capabilities, and execution

- [Interaction Agent and Skill Runtime](interaction_agent_skill_runtime.md)
- [Capability Registry](agent_capability_registry.md)
- [External Capability Manifests](../capabilities/README.md)
- [TaskGraph Planning and Guarded Execution](agent_task_graph.md)
- [TaskGraph Concurrency Decision](task_graph_concurrency_decision.md)
- [Conversation State](conversation_state.md)

## Interfaces and operations

- [API Reference](API_REFERENCE.md)
- [Configuration Reference](CONFIGURATION.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
- [Release and Packaging](RELEASE.md)

## Project governance

- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)
- [Support](../SUPPORT.md)
- [Changelog](../CHANGELOG.md)
- [Release asset policy](../release/README.md)
- [v0.1.0-alpha.1 candidate notes](../release/v0.1.0-alpha.1.md)
- [Coding-agent guidance](../CLAUDE.md)

## Documentation update rules

A change must update documentation in the same pull request when it changes any
of the following:

- an API endpoint, WebSocket message, shared contract, or capability schema;
- an environment variable, default, feature gate, startup command, or evidence
  location;
- a runtime ownership boundary or safety invariant;
- a milestone status, target-evidence claim, or release-readiness claim;
- a supported hardware profile or deployment mode.

Use the four-axis status vocabulary from `STATUS.md`. “Implemented” must never
be used as a synonym for “validated on target” or “release ready.”

Run the documentation checker before submitting changes:

```bash
python scripts/check_docs.py
```

The normal test command also runs the checker:

```bash
./scripts/run_tests.sh
```

## Snapshot metadata

For status-bearing documents, include the verified repository revision and date
or link to `STATUS.md`. Historical decisions should state that they are not the
current status authority.
