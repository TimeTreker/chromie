# Project Handoff

Last updated: 2026-07-31

This file is a concise resume aid. Current claims belong to
[Current Status](STATUS.md), delivery order belongs to
[Roadmap](../ROADMAP.md), and exact commands belong to
[Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

## Current resume point

Chromie has one Goal-driven semantic authority:

```text
Cognitive Gateway admission
  -> Goal Association
  -> model-authored Agent Skill selection
  -> Fast or terminal Deep Planner
  -> Canonical Plan
  -> Trusted Capability Runtime
  -> exact evidence reconciliation
  -> final response and TTS
```

The Host owns deterministic protective controls, validation, authorization,
scheduling, cancellation, evidence, and lifecycle coordination. Soridormi owns
backend selection, embodied feasibility, collision safety, stop, and recovery.

The canonical local gate is restored: repository policy, test ownership, Ruff,
Mypy, documentation, and the full canonical test suites pass. The strict narrow
verifier is implemented. This PC has no microphone, so physical target
validation is deferred without a claim. The active Issue is **Close
Current-Revision Target Evidence** using the non-physical default profile.

## What to do now

- keep the failed `20260731T110834Z` attempt as diagnostic-only: Python 3.11.15
  and services were ready, but no microphone input existed;
- retain the old `20260731T121727Z` root as diagnostic-only; its ambient and
  grounded-weather failures were corrected in rebuilt-Agent dirty-source
  headless diagnostics, not qualifying evidence;
- after the correction is committed, initialize a fresh
  `source_bound_development` closure and collect Gateway/Core, Agent
  Skill/weather, Social Attention, paired MuJoCo, active cancellation, and
  second-machine LAN evidence.

## Work after evidence closure

Continue one semantic Issue at a time:

- audit and narrow broad runtime exception boundaries;
- decompose `VoiceAssistant` around seams demonstrated by retained traces;
- consolidate direct environment parsing into typed profile-owned settings;
- expand Mypy through complete contract and runtime boundaries;
- merge duplicated documentation and vocabulary;
- rerun the same source-bound evidence profile after simplification.

The detailed scope and exit criteria are in
[Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).

## Required gates

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/check_docs.py
./scripts/run_tests.sh
```

## Start a fresh evidence closure

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT=".chromie/acceptance/target-evidence/${RUN_ID}"

python scripts/run_target_evidence_closure.py init \
  --profile source_bound_development \
  --reviewer "$USER" \
  --evidence-root "$EVIDENCE_ROOT"
```

Follow [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md) for collection,
human review, attachment, status, and finalization commands.
