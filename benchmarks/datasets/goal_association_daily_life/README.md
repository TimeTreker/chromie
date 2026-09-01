# Goal Association Daily-Life Corpus

Audience: GA prompt/contract reviewers and qualification operators. Each JSON file
below `scenarios/<split>/<category>/` is an independently reviewable authoritative
scenario, while `dataset.json` owns aggregate coverage. This document is operational
guidance only. An existing product document cannot own the corpus because benchmark
coverage, split isolation, asset identity, and review provenance are executable
qualification facts rather than runtime behavior policy.

Issue [#34](https://github.com/TimeTreker/chromie/issues/34) owns this work. The
corpus contains exactly 1,500 cases: 100 bilingual daily-life semantic seeds, each
expanded into the same 15-member Goal-continuity contrast set. Unlike the GI corpus,
every case supplies a production-shaped `CognitiveWorkRequest` containing accepted GI
Responsibilities and bounded existing/recent Goal state.

The corpus covers new creation, continue, modify, clarification answers, confirm,
reject, cancel, pause, resume, terminal reference, replacement, unrelated new work,
merge, split, and a deliberately retained mixed association-plus-creation contract
regression family. Its historical category name retains the origin of the defect, but
the owner-authorized candidate-aware contract now requires those cases to emit existing-
Goal associations and independent new Goals together in one primary result.

Validate the complete directory-discovered corpus with:

```bash
python benchmarks/datasets/goal_association_daily_life/validate.py
```

The validator discovers all 1,500 separate scenario files, reconstructs each production
decoder Schema, checks the accepted reference DTO through the real
`GoalAssociationResolver`, verifies Responsibility conservation and contrast membership,
and binds the complete sorted scenario tree to the manifest digest. All 1,500 references,
including the 100 mixed continuity-plus-creation cases, must pass the exact dynamic
Schema, model DTO, resolver conservation checks, and canonical Host DTO.

All scenarios remain `training_eligible=false` and lack independent semantic review.
Mechanical validity does not qualify the prompt, a deployed model, service behavior,
voice, simulator, target robot, or release.

To qualify the GA prompt with Codex as a same-model offline surrogate, freeze one
target-blind batch and keep source unchanged until adjudication completes:

```bash
python -m benchmarks.datasets.goal_association_daily_life.qualification prepare \
  --label baseline \
  --model gpt-5.6-sol \
  --reasoning-effort high \
  --output-dir .chromie/benchmarks/goal-association/RUN_ID
python -m benchmarks.datasets.goal_association_daily_life.qualification run \
  --concurrency 8 \
  --output-dir .chromie/benchmarks/goal-association/RUN_ID
python -m benchmarks.datasets.goal_association_daily_life.qualification adjudicate \
  --output-dir .chromie/benchmarks/goal-association/RUN_ID
```

Each candidate receives only the exact rendered production system/user prompt and
dynamic Schema. The harness retains one raw primary output per scenario, invokes the
single production mechanical repair only when the resolver requests it, then checks
the accepted output through Schema, DTO, resolver/Host conservation, and the hidden
Responsibility-map oracle. This is same-model, non-independent offline evidence; it
does not qualify the deployed Ollama transport or production model profile.
