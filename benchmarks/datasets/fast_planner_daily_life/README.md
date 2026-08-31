# Fast Planner Daily-Life Qualification Work Area

Audience: Fast Planner prompt, workflow, contract, and architecture reviewers and
qualification operators. Each JSON file below
`scenarios/<split>/<category>/` is one independently reviewable scenario. This
README records an incomplete authoring checkpoint; it is not production behavior
policy and does not yet describe a frozen qualification corpus.

[Issue #35](https://github.com/TimeTreker/chromie/issues/35) owns this work. The
intended corpus remains 1,000 production-shaped cases arranged as 100 bilingual
contrast sets. The tracked checkpoint contains only the first 10 model-authored
`streaming_advance` direct-conversation cases: five controlled family/home
conditions paired in English and Chinese. It is not frozen, digest-bound,
baseline-executed, adjudicated, or qualified.

The intended coverage is:

- streaming direct conversation, one common Capability, multiple Goals,
  parameter grounding, and boundary handling;
- canonical single- and multi-Goal plans;
- retained/provisional Work reconciliation;
- terminal-result and cancellation Evidence re-entry;
- Situation-revision and time-condition re-entry.

The existing scenario `input` contains an accepted `CognitiveWorkRequest` plus a
catalog fixture reference. Targets declare an acceptable semantic region rather
than one brittle response. When the corpus is complete, candidate packets must
contain only the exact rendered production prompts and dynamic response Schema;
targets, rubrics, categories, splits, and expected results must remain excluded.

`qualification.py`, `validate.py`, and `catalogs/common_v1.json` are unfinished
harness scaffolding. They must not be cited as working validation because the
required frozen `dataset.json` manifest and remaining scenario files do not yet
exist. After model authoring, review, per-file materialization, and manifest freeze,
the intended execution sequence is:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification prepare \
  --label baseline \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
python -m benchmarks.datasets.fast_planner_daily_life.qualification run \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
python -m benchmarks.datasets.fast_planner_daily_life.qualification adjudicate \
  --output-dir .chromie/benchmarks/fast-planner/RUN_ID
```

The planned run uses one `gpt-5.6-sol` Codex invocation per scenario, reasoning
effort `high`, no candidate retry, and primary-result Host adjudication with Fast
same-tier repair disabled. Codex CLI is not the deployed Ollama transport. Even
after completion, this would be same-model, offline, non-independent evidence and
could not establish deployed service, voice, simulator, hardware, release, or
independent semantic-review claims.

The tracked 10 cases were authored in one retained `gpt-5.6-sol` call and remain
`training_eligible=false`. Additional retained model-call envelopes are local,
ignored, unreviewed authoring material and do not transfer with Git. No script may
generate scenario semantics; mechanical tooling may only retain model-authored
output, split accepted envelopes unchanged into reviewable source files, validate
contracts, and execute qualification.
