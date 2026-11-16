# Chromie Handoff

Volatile operational snapshot. The stable resume boundary is in the
[checkpoint](DEVELOPMENT_CHECKPOINT.md); the four-axis state and ordered open
work are in [STATUS](docs/STATUS.md).

## Current snapshot — offline scripts feature delivery

- Checkout: `/tmp/chromie-finetuning-delivery-20261116` (temporary; clone the
  remote branch for a durable checkout). Branch: `codex/offline-gemma4-finetuning`.
  Baseline/latest main observed before edits:
  `55f5587d4ca8034fdefb24e53d632df5790b7dba`. Expected resume revision is the
  latest feature-branch commit containing all three delivery owners.
- Owner authorized feature-branch commit/push only. No main update, real model
  training, service restart, deployment or model promotion is part of this delivery.
- Runtime identity: not inspected in this delivery. Source profile remains RTX
  5090 / SGLang, shared `chromie-gemma4-12b`, pinned HF Gemma4 Unified revision;
  current runtime sources, prompts, profiles and Compose are unchanged. Prior
  live evidence remains bound to main's recorded revisions and is not requalified.
- Active live repair Issue and all existing target/voice blockers remain in the
  checkpoint and Status. Do not run the historical optimization loop or deploy
  this branch merely because offline script tests pass.

## Retained evidence and claim boundary

The preceding implementation session's durable local root is
`/home/chromie/Documents/Codex/2026-11-14/referenced-chatgpt-conversation-this-is-an/`.
Its `outputs/verification.json` binds all 23 delivered source file hashes.
`work/canonical-gate.log` records pytest 4,141 passed, 6 skipped, 1,002 subtests,
172 benchmark passes and 20 legacy Agent passes (2026-11-14).
`work/level-a.log` records 45/45; `work/workflow-reference.log` records 6,000
frozen workflow cases with source unchanged, no external candidate calls and
`model_ability_evaluated=false`. `work/cpu-smoke.log` is random tiny CPU evidence,
not real 12B training. Evidence artifacts under
`work/chromie/.chromie/finetuning/level-a-gate/` and `workflow-reference/`
remain private/ignored. These paths are local, not guaranteed after moving hosts.

Current delivery checks (2026-11-16): `python -m pytest -q tests/test_finetuning.py`
passed 29 tests; repository policies (15 families, no exceptions), docs,
configuration inventory (399 keys), Ruff and test ownership passed. CLI help,
`git diff --check` and runtime-source/profile/prompt/Compose byte comparison to
baseline passed. All 23 implementation files match the retained verification
hashes. The prior full gate is retained evidence, not claimed as rerun on this
branch. No GPU or physical evidence is inferred from it.

Inherited live identities, private historical paths and operational commands are
available in the [baseline Handoff](https://github.com/TimeTreker/chromie/blob/55f5587d4ca8034fdefb24e53d632df5790b7dba/HANDOFF.md).
They require re-verification before any live work.

## Resume and verify (no model training)

```bash
git clone --branch codex/offline-gemma4-finetuning --single-branch https://github.com/TimeTreker/chromie.git chromie-finetuning
cd chromie-finetuning
python -m scripts.finetuning --help
python -m pytest -q tests/test_finetuning.py
python scripts/check_repository_policies.py
python scripts/check_docs.py
# Full local gate when needed; does not train the target model:
./scripts/run_tests.sh
```

Full export, review, offline environment, training, paired evaluation and rollback
commands are owned by [the component guide](scripts/finetuning/README.md).
Training remains deferred by the owner. Native baseline/candidate testing,
all shared-model role regressions, narrow supervised voice proof and default
target-evidence closure remain mandatory before any future promotion.
