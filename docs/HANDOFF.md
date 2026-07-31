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

The active Issue is **Restore Canonical Local Gate Reproducibility**. Direct
unittest discovery runs 1,654 tests but ends with 5 failures and 8 errors;
pinned Mypy reports 42 errors. No fresh full-suite automatic-verification claim
or current-revision target-evidence claim is closed.

## What to do now

- declare every imported test dependency, including `pytest`;
- make Router removal distinguish ignored bytecode from maintained source;
- isolate unit tests from generated runtime configuration;
- repair the existing Mypy scope without ignores or scope removal;
- require `INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh` to pass.

Then retain one narrow current-revision physical microphone-to-audible-response
bundle. After that, initialize a fresh closure root and collect the default
Gateway/Core, Agent Skill/weather, Social Attention, paired MuJoCo, active
cancellation, and second-machine LAN evidence.

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
