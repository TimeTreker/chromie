# Fast Planner Daily-Life Qualification Corpus

Audience: Fast Planner prompt, workflow, contract, and architecture reviewers and
qualification operators. Each JSON file below
`scenarios/<split>/<category>/` is one independently reviewable scenario. This is
offline qualification input, not production behavior policy.

[Issue #35](https://github.com/TimeTreker/chromie/issues/35) owns this work. The
manifest-bound corpus contains 1,500 production-shaped cases arranged as 150
bilingual contrast sets. Each set crosses five controlled conditions with
`en-US`/`zh-CN` pairs and remains wholly inside one split. Coverage is balanced:
750 cases per language, 500 per runtime variant, 100 per ability class, and
1,000/250/250 cases in `train_candidate`/`validation`/`frozen_test`.

The 15 ability classes cover:

- streaming direct conversation, one common Capability, multiple Goals,
  parameter grounding, and boundary handling;
- canonical single- and multi-Goal plans;
- retained/provisional Work reconciliation;
- terminal-result and cancellation Evidence re-entry;
- Situation-revision and time-condition re-entry.

The ten daily-life domains are family/home, work/study, school/learning,
shopping/errands, travel/navigation, health/wellbeing, entertainment/media,
friends/communication, pets/garden, and personal organization.

Each scenario `input` contains an accepted `CognitiveWorkRequest` plus a
catalog fixture reference. Targets declare an acceptable semantic region rather
than one brittle response. Candidate packets contain only the exact rendered
production prompts and dynamic response Schema; targets, rubrics, categories,
splits, and expected results remain excluded.

`qualification.py` and `validate.py` directory-discover every scenario, enforce
the frozen coverage and review contract, reconstruct the exact production prompt
and runtime-variant dynamic Schema, and verify that targets remain outside the
candidate transaction. Validate the manifest and scenario-tree digest with:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate
python -m pytest -q benchmarks/tests/test_fast_planner_daily_life_dataset.py
```

After owner semantic review, the immutable target-blind baseline sequence is:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification prepare \
  --label baseline \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
python -m benchmarks.datasets.fast_planner_daily_life.qualification run \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
python -m benchmarks.datasets.fast_planner_daily_life.qualification adjudicate \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
```

The planned baseline uses one `gpt-5.6-sol` Codex invocation per scenario, reasoning
effort `high`, no candidate retry, and primary-result Host adjudication with Fast
same-tier repair disabled. Codex CLI is not the deployed Ollama transport. Even
after execution, this would be same-model, offline, non-independent evidence and
could not establish deployed service, voice, simulator, hardware, release, or
independent semantic-review claims.

The scenario semantics were directly authored by retained `gpt-5.6-sol`
high-reasoning calls. Mechanical tooling assigned coverage cells, retained prompts,
outputs and execution ledgers, rejected incomplete/malformed complete outputs,
split accepted JSONL into reviewable files, advanced review metadata after
validation, and computed the manifest digest; it did not generate scenario
semantics. Local ignored authoring evidence under
`.chromie/benchmarks/fast-planner/llm-authoring-v2/` does not transfer with Git.

Every case remains `independent_semantic_review=false` and
`training_eligible=false`. The `train_candidate` split is a partition name, not
training approval. No immutable baseline or adjudication has been run, so this
corpus does not yet qualify the Fast Planner prompt, model, contract, workflow,
architecture, or behavior.
