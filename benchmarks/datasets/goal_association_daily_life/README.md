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

The owner-authorized intent-only migration keeps complete GI outcomes and the
existing expected result type as new Goal authority. GA's model output contains
source refs and continuity IDs; it no longer extracts capability/resource fields.
Input text, retained Goal snapshots, contrast sets and splits remain frozen.

Two hundred retained typed-state update references (100 modify and 100 clarification
answers) are explicit `accept_host_reject` cases. Their JSON/Schema/DTO remains valid,
but the transition must fail closed because new GI supplies no replacement typed
binding provenance. A complete source-backed replacement Goal is required; preserving
stale resource/parameter fields would be incorrect. Their original intended continuity
references stay visible as known contract limitations, not successful updates.

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
and binds the complete sorted scenario tree to the manifest digest. All 1,500
references pass exact Schema/DTO checks: 1,300 must be Host-accepted and 200 must
fail closed without a state transition. These include the 100 mixed continuity-plus-
creation cases. A rejection cannot be counted as successful user-goal fulfillment.

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

The `--provider ollama` variant uses the production client and frozen model digest
and generation options. Its `raw-outputs` files contain the client's parsed object
for Host replay; exact original provider text and request/response envelopes are
retained separately in each `call-logs` record, correlated by turn and attempt.
Adjudication reports raw JSON/Schema, completion, non-thinking and replay agreement
separately from normalized Host acceptance. A strict pass requires both; missing
historical provider records cannot establish raw validity. This direct provider
evidence still bypasses Agent HTTP, microphone, playback and robot execution.
