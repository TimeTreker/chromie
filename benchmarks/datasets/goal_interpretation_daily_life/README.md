# User Meaning Interpretation Daily-Life Dataset

Audience: UMI reference authors and qualification reviewers. Checked-in JSON,
source inputs, contrast membership and manifest remain the dataset assets.

## Inventory and current compatibility

The retained inventory contains 1,496 scenarios: 374 four-case contrast sets,
17 ordinary-life categories, 748 cases per language. Splits are 896
`train_candidate`, 220 `validation`, 380 `frozen_test`; a contrast set stays within
one split. Every case remains `training_eligible=false` pending independent review.

This is a frozen reference inventory, not a qualified production-model corpus.
Under the owner-authorized WHAT-only contract, the current wire migration removes
`output_mode`, `body_effect_family` and `continuity_scope` from references and their
obsolete classification expectations. It retains explicit `value_review`, source
ranges, complete outcomes, every input/context, intent-detail oracle, contrast and
split. Cognitive activation retains its authority/source refs without advisory HOW.
The old classification distribution is retained in the migration evidence rather
than required from UMI. Dynamic Schema/Host validation is rerun after migration.

Before-bytes, per-file SHA256 and invariant checks for all 1,496 scenarios are under
`.chromie/acceptance/meaning-coverage-repair-20261112/daily-life-wire-migration/`;
`dataset.json` binds the new tree digest. This is explicit reference maintenance,
not candidate inference or independent semantic review.

UMI preserves complete contextual WHAT, uncertainty, Value-review requirement and
exact current-turn source evidence. Planner owns HOW, parameter extraction,
Capability selection and Work; SC owns communication. Fresh UMI output forbids
execution/output/lifetime categories and `bindings`, including an empty object.
Retained canonical Goal constraints stay read-only context. Native complete meaning
and activation coverage still require qualification.

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
