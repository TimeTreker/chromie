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
Mypy, documentation, 1,662 primary tests, and 20 legacy Agent tests pass. The
strict narrow verifier is implemented, but the active Issue **Retain a
Current-Revision Live Voice Loop** still needs one clean supervised bundle. No
current-revision live or broader target-evidence claim is closed.

## What to do now

- commit and push the implemented `current-revision-live-voice` profile;
- from that exact clean revision, run `voice_acceptance.py --mode supervised
  --cases speech-only --start-services` and provide the real microphone input
  plus audible-output verdict;
- verify the retained directory with `verify_voice_evidence.py --profile
  current-revision-live-voice --require-clean`;
- close the Issue only when the machine-readable narrow claim reports
  `eligible=true`; it must remain `release_qualified=false` and make no
  Soridormi, simulator, or robot claim.

After that, initialize a fresh closure root and collect the default Gateway/Core,
Agent Skill/weather, Social Attention, paired MuJoCo, active cancellation, and
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
