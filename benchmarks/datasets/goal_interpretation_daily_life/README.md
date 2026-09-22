# User Meaning Interpretation Daily-Life Dataset

Audience: Chromie maintainers evaluating or reviewing the isolated User Meaning
Interpretation (UMI) authority. The checked-in scenario JSON files are the
authoritative dataset assets; this directory does not ship a scenario generator.

This dataset is separate from `daily_conversation` because it tests the current
primary GI model contract directly: complete natural-language intentions,
requested result types, genuine unresolved meaning, and exact
current-turn source evidence. It does not judge Planner behavior, Capability
selection, response wording, execution, voice, simulation, or robot behavior.

## Layout and scope

Every JSON file under `scenarios/` contains exactly one scenario. The 1,496
scenarios form 374 four-case contrast sets across 17 ordinary-life categories:
family and home, meals, routines, school, work, travel, shopping, wellbeing,
weather, friends, entertainment, household objects, movement, social support,
multi-turn continuity, uncertainty/correction, and pets/gardening.

The dataset is balanced between `zh-CN` and `en-US` (748 each) and divided by
whole contrast set:

- `train_candidate`: 896 scenarios
- `validation`: 220 scenarios
- `frozen_test`: 380 scenarios

A contrast set never crosses a split. The train-candidate label is only a data
partition name: every scenario has `training_eligible=false` until independent
semantic review promotes it. Frozen-test changes require owner review.

Each scenario contains:

- the immutable current turn and minimum bounded semantic context;
- one acceptable current-schema `reference_wire_output`;
- flexible semantic expectations for evaluating non-identical valid wording;
- machine-checkable invariants and named adversarial failure hypotheses;
- explicit review and evidence limitations.

The retained semantic review dimensions cover quantities, units, actors, referents,
place/time scope, requested result types, compound relations and continuity meaning.
These are **review targets**, not GI output fields. The owner-approved migration
keeps all source turns, context and contrast splits; full outcome text now carries
material details and relations. GA owns canonical relationships and Planner owns
parameter extraction, conversions and scheduling. The historical measurement
coverage labels in the manifest describe reviewed source details, not a typed GI
binding table. Native inference and independent semantic review remain separate.

## Validation

Run the complete static audit with:

```bash
python benchmarks/datasets/goal_interpretation_daily_life/validate.py
```

The audit discovers every file, checks declared coverage and split isolation,
rejects exact input duplication, and validates each reference against the
dynamic current GI response schema. All 1,496 references must also pass the
production Host validator. Host checks closed intent fields, exact source-token
references, order and non-overlap. It does not infer missing details, enforce a
fixed count of action fragments, or recover intent using phrase rules. Elliptical
replies must be understood from their supplied context in the primary GI result.

These checks prove mechanical compatibility and internal consistency, not
independent semantic correctness or live-model performance.

The September 22 reference migration preserves all admitted text, context,
outcomes, source spans, semantic detail expectations and contrast splits. References
now explicitly carry `continuity_scope`, typed `meaning_uncertainties` and
`cognitive_requests`. The 68 ambiguous-object/recipient cases retain their original
uncertainty descriptions and cite their sole Responsibility. Draft-only conversation
and repetition of already admitted speech use turn scope; separate recipient,
information, performance and effect outcomes retain Goal scope. Activation choices
are authored fixture data, never a Runtime routing rule or an inference-time repair.
The frozen-test changes remain subject to owner review; no independent semantic,
native-model or training promotion follows from current-Schema compatibility.
