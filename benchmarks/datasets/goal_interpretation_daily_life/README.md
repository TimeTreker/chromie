# Goal Interpretation Daily-Life Dataset

Audience: Chromie maintainers evaluating or reviewing the isolated Goal
Interpretation (GI) authority. The checked-in scenario JSON files are the
authoritative dataset assets; this directory does not ship a scenario generator.

This dataset is separate from `daily_conversation` because it tests the current
primary GI model contract directly: atomic Responsibilities, sparse typed
bindings, output modes, coordination, genuine unresolved meaning, and exact
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

The retained coverage includes every one of the 25 normal model-facing binding
dimensions, all ten concrete GI output modes, and the `new`, `continue`,
`modify`, `clarify`, `cancel`, and `resume` relationship paths. There are 306
context-bearing scenarios and 102 cases with genuine unresolved meaning.

## Validation

Run the complete static audit with:

```bash
python benchmarks/datasets/goal_interpretation_daily_life/validate.py
```

The audit discovers every file, checks declared coverage and split isolation,
rejects exact input duplication, and validates each reference against the
dynamic current GI response schema. All 1,496 references must also pass the
production Host validator. In particular, a one-phrase elliptical clarification
such as “Tomorrow afternoon.” remains a valid whole-turn binding only for one
`relationship=clarify` Responsibility targeting one supplied Goal with an open,
blocking `ask_user` information gap. The same whole-turn binding remains invalid
without that exact bounded context, so the transport-echo guard still catches
opaque or collapsed requests.

These checks prove mechanical compatibility and internal consistency, not
independent semantic correctness or live-model performance.
