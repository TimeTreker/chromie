# User Meaning Interpretation Daily-Life Dataset

Audience: UMI reference authors and qualification reviewers. Checked-in JSON,
source inputs, contrast membership and manifest remain the dataset assets.

## Inventory and current compatibility

The retained inventory contains 1,496 scenarios: 374 four-case contrast sets,
17 ordinary-life categories, 748 cases per language. Splits are 896
`train_candidate`, 220 `validation`, 380 `frozen_test`; a contrast set stays within
one split. Every case remains `training_eligible=false` pending independent review.

This is a frozen reference inventory, not a qualified production-model corpus.
The 2026-10-04 current-contract reconciliation removes retired initial
`social_cognition` requests: Runtime already owns that standing invocation. It adds
the existing body-effect family to 850 body-action references and their semantic
expectations (730 task physical effects, 120 social expressions). All 1,496
references now pass the current dynamic Schema and Host validator.

The retained admitted text, complete meaning, context, source ranges, actors,
referents, quantities, order, contrast membership and splits are unchanged. Original
files and per-file before/after digests are retained under
`.chromie/acceptance/contract-fixture-repair-20261004T084054Z/`; the manifest binds the
new scenario-tree digest. This is a mechanical reference migration, not candidate
inference or independent semantic review.

UMI preserves complete contextual WHAT, requested result type, uncertainty and
exact current-turn source evidence. Planner owns parameter extraction, Capability
selection and Work; SC owns wording. The live `bindings` surface conflicts with
Charter principle 30 and is an open design/source finding in the
[project audit](../../../ARCHITECTURE_AUDIT.md), not an approved dataset extension.

## Validation and migration

```bash
python benchmarks/datasets/goal_interpretation_daily_life/validate.py
```

Validation must expose incompatibilities; it must not rewrite targets or routing
choices to obtain a pass. Preserve admitted text, bounded context, 374 contrast
sets and split isolation while reviewing migration. Frozen-test target changes
require owner review and new bound digests; compare Schema, DTO and Host separately.

Counts, actors, referents, units, place/time scope and relations remain semantic
review targets. Neither a reference label nor deterministic compatibility proves
native inference, independent semantic correctness, training readiness, service
behavior, voice, simulator or robot performance. Follow the
[qualification method](../../../docs/LLM_PROMPT_QUALIFICATION_METHOD.md) before
candidate optimization or promotion. The migration does not authorize changing UMI's
production prompt or `bindings` ownership.
