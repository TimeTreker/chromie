# Chromie Benchmark Suite

This directory contains evaluation infrastructure, not production behavior policy.
Thinking remains in the LLM. Benchmark code may discover scenarios, validate
contracts and provenance, aggregate evidence, and report coverage. It must not
add phrase tables, regular-expression intent rules, scenario-ID branches, or
fixed input-to-action mappings.

## Repository layout

- `benchmark.schema.json`: versioned generated-inventory contract.
- `manifests/suites.json`: authoritative source classification and taxonomy.
- `inventory/core.py`: deterministic discovery, validation, and coverage report.
- `modules/`, `integration/`, `e2e/`, `stress/`, `regression/`, `datasets/`:
  reserved homes for later benchmark phases; existing scenarios remain in place.
- `reports/`: generated local reports. Generated JSON should not be committed
  unless a release process explicitly retains it as evidence.

## Commands

Validate the repository inventory without writing generated files:

```bash
python -m benchmarks.inventory.core --check
```

Generate the inventory and coverage report locally:

```bash
python -m benchmarks.inventory.core
```

Run focused tests:

```bash
pytest -q benchmarks/tests/test_inventory.py
```

The inventory is deterministic: source rules and paths are sorted, IDs are
stable, and output contains no timestamps. A duplicate ID, unknown taxonomy
value, missing required source, malformed JSON, or broken source reference fails
closed with exit status `2`.

Run the maintained comprehensive source, benchmark, service, bilingual
closed-loop, GPU-contention, and evidence-collection workflow with:

```bash
./scripts/qualification/run_comprehensive_test.sh
```

The shell entrypoint is orchestration only. It does not own scenario content or
semantic truth. Existing fixture/contract checks remain deterministic, and
pending qualitative cases are packaged for retained LLM or human review. The
runner records its own digest and the tested Git revision in the archive.

Compare a clean known-good archive with a candidate using the maintained
revision-bound comparator:

```bash
python -m benchmarks.regression compare \
  --baseline ~/Downloads/chromie-baseline.tar.gz \
  --candidate ~/Downloads/chromie-candidate.tar.gz \
  --output benchmarks/reports/regression-comparison.json
```

The comparator verifies retained artifact indexes, compares deterministic checks
before semantic verdicts, reports missing scenarios/evidence, and measures
latency/audio regressions. Exit status `1` means a regression was found; exit
status `2` means the evidence could not be validated. Cohort mismatches are
reported as inconclusive rather than silently treated as equivalent.

Replay one retained live workflow case without rerunning the full suite:

```bash
python -m benchmarks.regression replay \
  --archive ~/Downloads/chromie-candidate.tar.gz \
  --scenario en_session_memory_recall \
  --output-dir .chromie/replay/en_session_memory_recall \
  --start-services
```

For a multi-turn failure, `benchmarks.regression minimize` uses structural
delta-debugging. Its default oracle is the exact mechanical failure boundary. A
semantic failure requires an explicit `--oracle-command` that reads replay JSON
from stdin and returns `{"failure_reproduced": true|false}`. The minimizer never
uses phrases or keywords to decide meaning.

Run the maintained controlled provider-fault matrix through the real Ollama
client boundary:

```bash
python -m benchmarks.faults run \
  --manifest benchmarks/manifests/fault_injection_v1.json \
  --output benchmarks/reports/fault-injection.json \
  --repeat 3
```

Repeat any qualification command and retain every stdout/stderr stream:

```bash
python -m benchmarks.faults repeat \
  --count 5 \
  --timeout 7200 \
  --output-dir .chromie/repeats/comprehensive \
  -- ./scripts/qualification/run_comprehensive_test.sh --strict-exit
```

Reports distinguish `consistent_pass`, `consistent_fail`, `intermittent`, and
`infrastructure_timeout`; one successful run never hides intermittent failure.

Create a separate upload-safe copy without modifying raw evidence:

```bash
python -m benchmarks.evidence sanitize \
  --input ~/Downloads/chromie-comprehensive-REV-RUN.tar.gz \
  --output ~/Downloads/chromie-comprehensive-REV-RUN-sanitized.tar.gz
```

Durable profile memory is excluded, credential-bearing keys and headers are
redacted, local identities are replaced, artifact hashes are rebuilt, and a
`sanitization-report.json` records every exclusion and redaction. Use
`--exclude-audio` when the reviewer does not need playback evidence. The raw
archive remains unchanged and must stay local unless explicitly approved.

## Classification policy

One source scenario appears once in the inventory and may carry multiple dataset
tags. Source files and legacy runners are not moved or replaced by inventory generation.
Language detection is descriptive metadata only. Acceptance scripts are indexed
as entrypoints until format adapters cover their internal cases.

## Common scenario contract

`contracts/scenario.schema.json` defines the normalized scenario boundary and
`contracts/result.schema.json` defines the retained execution-result envelope.
The contract keeps deterministic invariants, acceptable semantic outcomes,
auxiliary-behavior regions, qualitative review, and distribution observations as
separate fields. It does not require one exact model response.

`adapters/legacy_json.py` normalizes maintained JSON shapes in place. It preserves
declared IDs and legacy expectations, records source provenance, and derives a
stable content ID only when the source has no ID. Adapters do not execute a
scenario and do not interpret user phrases.

Every normalized case also declares or derives `oracle_policy`:

- `deterministic` for fixtures, schemas, exact tool arguments, lifecycle,
  evidence, signal, and transport truth;
- `semantic_review` for meaning and qualitative interaction judgment;
- `hybrid` when both authorities are required.

Existing deterministic runners remain authoritative. Semantic review is a
separate retained adjudication phase and cannot override a deterministic
failure. See
[hybrid oracle execution](../docs/CHROMIE_BENCHMARK_SUITE.md#73-hybrid-oracle-execution).

After generating the inventory, check all JSON scenario adapters with:

```bash
python -m benchmarks.adapters.normalize --check
```

Generate a local normalized view with:

```bash
python -m benchmarks.adapters.normalize
```

Generated normalized JSON belongs under `benchmarks/reports/` and is not an
authoritative source dataset.

## Module and integration runners

`runners/` executes normalized scenarios through an explicit executor boundary.
It does not import production services or infer expected behavior from user text.
Two modes are available:

- `replay`: evaluate retained observations deterministically;
- `live_model`: invoke an explicit adapter command over JSON stdin/stdout.

Machine evaluation is intentionally limited to declared boundaries: reported
invariants, explicit `primary_task_passed`, and exact forbidden-behavior labels.
Naturalness, empathy, style fit, and other semantic dimensions are returned as
`review` when no reviewed evaluator supplies a result. Missing required invariant
evidence fails closed.

Package pending semantic cases and their correlated artifacts:

```bash
python -m benchmarks.review package \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --report benchmarks/reports/run.json \
  --artifact-root .chromie/acceptance/run-id \
  --output-dir .chromie/review/run-id \
  --archive ~/Downloads/chromie-review-run-id.tar.gz
```

Run several independent API reviewers over the same evidence capsule:

```bash
cp benchmarks/manifests/semantic_reviewers.example.json \
  .chromie/semantic-reviewers.json
# Edit current model/base URL values, enable selected profiles, and export keys.

python -m benchmarks.review judge \
  --bundle .chromie/review/run-id \
  --reviewers .chromie/semantic-reviewers.json \
  --output-dir .chromie/review/run-id/judgments
```

The supported provider protocols are OpenAI Responses, Anthropic Messages, and
OpenAI-compatible Chat Completions. Each profile declares `model_family`; the
consensus threshold counts distinct families rather than reviewer aliases.
DeepSeek, Kimi/Moonshot, local gateways, or other compatible services use the
last form with their current documented base URL and model. No provider model
name is permanent repository truth.

Aggregate reviews produced manually or by separate systems:

```bash
python -m benchmarks.review aggregate \
  --reviews reviews-openai.json \
  --reviews reviews-claude.json \
  --reviews reviews-deepseek.json \
  --policy majority \
  --minimum-reviewers 3 \
  --minimum-model-families 3 \
  --output ensemble-reviews.json
```

Apply a retained individual, ensemble, or human review without weakening hard
gates:

```bash
python -m benchmarks.review apply \
  --report benchmarks/reports/run.json \
  --reviews ensemble-reviews.json \
  --output benchmarks/reports/run-reviewed.json
```

Run a module cohort from the generated inventory:

```bash
python -m benchmarks.modules.run \
  --inventory benchmarks/manifests/existing_scenarios.json \
  --mode replay \
  --replay-file /path/to/replay-observations.json \
  --output benchmarks/reports/module-replay.json
```

Run an integration cohort against an explicitly configured adapter:

```bash
python -m benchmarks.integration.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --mode live_model \
  --command "python scripts/my_benchmark_adapter.py" \
  --model local-model-name \
  --prompt-revision prompt-revision-id \
  --output benchmarks/reports/integration-live-model.json
```

The adapter receives one JSON request on stdin containing `scenario` and `run`,
and returns one observation object on stdout. This boundary allows later Cognitive Gateway,
Planner, Composer, and deployed-runtime adapters without coupling benchmark code
to one backend or adding benchmark-specific production branches.

## Runtime component adapters

`runtime_adapters/` connects the generic `live_model` runner to real Chromie
component boundaries without importing benchmark policy into production code.
Supported component profiles are:

- `cognitive_gateway`;
- `planner`;
- `mind_profile`;
- `capability_projection`;
- `social_attention`.

Each profile supports exactly one explicitly configured transport:

- an HTTP JSON endpoint through its `CHROMIE_BENCHMARK_*_URL` variable; or
- a Python callable using `module.path:function` through its
  `CHROMIE_BENCHMARK_*_CALLABLE` variable.

No deployment URL, port, backend identity, model, or prompt revision is embedded
in the manifest. The component receives the full normalized scenario and run
profile and must return a Benchmark execution observation. The adapter does not
infer expected behavior from user text and does not translate phrases into
skills.

Example using a deployed Cognitive Gateway adapter endpoint:

```bash
export CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_CALLABLE=my_harness.gateway:invoke
python -m benchmarks.modules.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --mode live_model \
  --command "python scripts/benchmark_runtime_adapter.py --component cognitive_gateway" \
  --model local-gateway-model \
  --prompt-revision cognitive-gateway-contract-v1 \
  --output benchmarks/reports/cognitive-gateway-live.json
```

Example using an in-process test harness callable:

```bash
export CHROMIE_BENCHMARK_SOCIAL_ATTENTION_CALLABLE=\
my_harness.social_attention:invoke
python scripts/benchmark_runtime_adapter.py --component social_attention
```

The callable or HTTP endpoint is an explicit test harness boundary. Production
modules remain unaware of scenario IDs and benchmark execution.


## Cognitive architecture terminology

The current ingress architecture is the **Cognitive Gateway**, which owns only
input normalization, protective reflex, attention review, context assembly, and
turn admission. Goal interpretation, planning, capability selection, and response
composition remain downstream in the Goal-Driven Cognitive Core.

The legacy `scenarios/goal_interpretation/` and `scenarios/cognitive_core_dialogue/` paths are retained
for source compatibility and historical comparison. Inventory classifies them as
`goal_interpretation` and `cognitive_core_dialogue` datasets; their directory names define
the current architecture. New benchmark component profiles must not reintroduce a
removed first-class Router boundary.

## Reviewed Social Attention dataset v1

`datasets/social_attention/cases.json` is the first comprehensive reviewed
behavior dataset. It contains 128 integration-layer cases across 16 cohorts,
with explicit coverage for style, mode, politeness, language, recent auxiliary
evidence, stillness, unavailable capabilities, safety conflicts, and historical
regressions.

The dataset is validated against `manifests/social_attention_v1.json`. Every case:

- expresses acceptable semantic behavior regions rather than one required gesture;
- keeps `none` as a valid auxiliary decision;
- separates deterministic invariants from qualitative review;
- uses backend-neutral `social_attention.*` capability labels;
- records LLM-generated/reviewed provenance without claiming release qualification;
- requires human approval and evidence before release qualification.

Validate it with:

```bash
python -m benchmarks.datasets.social_attention.validate --check
```

Generate its deterministic coverage report with:

```bash
python -m benchmarks.datasets.social_attention.validate
```

## Daily conversation semantic dataset v1

`datasets/daily_conversation/scenarios/` is the maintained Git-controlled
daily-life communication asset. It contains 166 Chromie-specific integration
scenarios across fifteen cohorts, with 83 Chinese and 83 English cases. Coverage
includes presence, family and home, school and learning,
routines, meals and wellbeing, emotional support, play and creativity,
identity and robotic-body truth, practical information and tools, communication
preferences, multi-turn continuity, uncertainty repair, friendships and peer
communication, shared-space etiquette, and casual conversation and curiosity.

These scenarios intentionally provide no canonical response strings. Each case
defines an acceptable semantic region, forbidden behavior, deterministic hard
boundaries, and dimensions for retained LLM or human adjudication. The source
records LLM authoring/review provenance and explicitly remains a dataset
candidate until independent review and execution evidence qualify a declared
model or release claim. Scenario content has no Runtime policy authority.

Focused source checks are:

```bash
python -m pytest -q benchmarks/tests/test_daily_conversation_dataset.py
python -m benchmarks.inventory.core --check
python -m benchmarks.adapters.normalize --check
```

Execute cases through the maintained safe live-text adapter and retain the real
outputs for semantic review:

```bash
export CHROMIE_DAILY_BENCHMARK_ARTIFACT_ROOT=.chromie/benchmarks/daily-conversation/run-id/artifacts
python scripts/run_daily_conversation_benchmark.py \
  --command "python scripts/daily_conversation_live_adapter.py" \
  --model candidate-model-id \
  --prompt-revision current-prompt-revision \
  --output-dir .chromie/benchmarks/daily-conversation/run-id
```

The live adapter receives each normalized scenario on standard input and uses
the maintained Host text path with cognitive-runtime apply, shared conversation
state for multi-turn cases, no speaker, and preview-only execution. It therefore
exercises routing, Goal Association, planning, and response composition without
executing proposed effects. It also verifies the quality-model identity exposed
by Agent health and that the fixed fast roles remain `qwen3:4b`. The runner writes
`normalized.json`, `run.json`, and `review/review-bundle.json`. Give that review
bundle to Codex or another declared LLM/human reviewer, fill the generated
`review-template.json`, and apply the retained semantic verdict with
`python -m benchmarks.review apply`. The reviewer judges the actual output
against the acceptable semantic region; it does not compare against a fixed
answer string. Every review must also distinguish scenario/oracle, prompt or
MindProfile, missing context, contract/schema, runtime/provider, and isolated
model-inference causes. One failed output never proves that the model is at
fault; when the retained prompt, raw output, validation error, and upstream
evidence cannot isolate the cause, attribution remains `unresolved`. `--id`,
`--cohort`, and `--language` support focused diagnostic runs, while the default
executes the complete dataset.

When diagnosing whether a failure comes from basic model semantics or from the
production prompt/DTO/coordinator surface, run the same cases through the
isolated semantic probe first:

```bash
export CHROMIE_DAILY_BENCHMARK_ARTIFACT_ROOT=.chromie/benchmarks/daily-conversation/probe-model/artifacts
python scripts/run_daily_conversation_benchmark.py \
  --command "python scripts/daily_conversation_semantic_probe_adapter.py" \
  --model candidate-model-id \
  --prompt-revision semantic-probe-v1 \
  --output-dir .chromie/benchmarks/daily-conversation/probe-model
```

The probe supplies the user episode, bounded `scenario_state`, registered
capability names, and Chromie's maintained identity/evidence rules through a
small structured contract. It explicitly excludes primary outcomes, forbidden
behavior labels, and review rubrics from the candidate prompt. This is a
diagnostic counterfactual, not integration or release evidence: a semantic-probe
pass followed by a live-adapter failure points toward the production context,
schema, workflow, or coordination boundary, while failure at both boundaries is
stronger model-inference evidence only after the fixture and prompt are judged
sufficient. Retain and semantically review both outputs; never convert a probe
score into a live robot claim.

To extend coverage, add exactly one scenario object per JSON file below
`datasets/daily_conversation/scenarios/<cohort>/`. Name the file after the last
segment of its scenario ID; for example,
`daily.v1.family_home.where_is_dad` belongs in
`scenarios/family_home/where_is_dad.json`. Dataset-wide provenance and coverage
live in `datasets/daily_conversation/dataset.json`, not in a scenario file.
The runner and inventory discover `**/*.json` recursively, so adding or
reorganizing scenario data never requires a Python change. Keep scenario IDs
unique and update the dataset and migration manifest counts when intentionally
changing the maintained cohort size.

## Goal Association daily-life corpus v1

`datasets/goal_association_daily_life/scenarios/` contains 1,500 independently
reviewable GA inputs, split evenly between Chinese and English. Every JSON file
supplies accepted GI Responsibilities together with bounded existing and recent
Goal state. The fifteen continuity families cover creation, association, Goal
lifecycle operations, replacement, merge/split decisions, and the deliberately
retained mixed association-plus-creation contract gap.

The corpus has no generator or combined scenario source: one scenario file is
the authoritative unit. `dataset.json` owns aggregate counts and the complete
scenario-tree digest. Reference decisions remain qualification oracles rather
than Runtime policy, all cases are ineligible for training, and the corpus does
not claim independent semantic review or deployed behavior evidence.

Validate the directory-discovered corpus and its real Host contracts with:

```bash
python benchmarks/datasets/goal_association_daily_life/validate.py
python -m pytest -q benchmarks/tests/test_goal_association_daily_life_dataset.py
```

See the corpus
[README](datasets/goal_association_daily_life/README.md) and
[Issue #34](https://github.com/TimeTreker/chromie/issues/34) for its ownership,
claim boundary, and retained prompt-qualification evidence.

## Fast Planner daily-life qualification corpus

`datasets/fast_planner_daily_life/scenarios/` contains 1,500 directly
model-authored, production-shaped Fast Planner cases in 150 bilingual contrast
sets. Coverage is balanced across streaming advance, canonical primary planning,
bounded re-entry, 15 ability classes, 10 daily-life domains, and English/Chinese.
The manifest owns aggregate counts and the complete scenario-tree digest.

The checked-in validator reconstructs the exact production prompt and dynamic
Schema for every case and enforces the target-blind transaction, review flags,
coverage matrix, Goal/Evidence/Work references, and frozen Capability fixture.
Every scenario is only a mechanically validated candidate: independent semantic
review, immutable baseline inference, and adjudication have not run. Do not cite
the corpus as prompt, contract, workflow, architecture, model, behavior, deployment,
or training qualification.

Validate it with:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate
python -m pytest -q benchmarks/tests/test_fast_planner_daily_life_dataset.py
```

See the corpus
[README](datasets/fast_planner_daily_life/README.md) and
[Issue #35](https://github.com/TimeTreker/chromie/issues/35). The tracked scenarios
and retained local authoring evidence remain same-model-authored, non-independent,
semantically unreviewed, and ineligible for training.


## End-to-end evidence profiles

`e2e/` runs the same normalized semantic scenario under an explicit evidence
profile. The maintained profiles distinguish replay, model-only, deployed text,
virtual audio, MuJoCo simulation, and supervised physical execution. Each
profile defines its allowed execution claims, required correlated evidence,
timing markers, supervision, safe-idle requirements, and human-approval status.

Validate the profile manifest with:

```bash
python -m benchmarks.e2e.validate --check
```

Run a cohort through a maintained first-party adapter boundary with:

```bash
export CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE=qualification_harness.live_service:invoke
python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --adapter live_service_text \
  --dataset social_attention \
  --effective-model fast_planner=<resolved-model> \
  --mind-profile <approved-profile-revision> \
  --social-style courteous \
  --social-attention-mode on \
  --style courteous \
  --mode on \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology cognitive-runtime-apply
```

Command adapters write correlated evidence incrementally. Timeout, process
failure, or malformed final output retains available partial evidence and
artifacts instead of hanging or silently discarding the trace. Automatic
reports never claim final release qualification. See
[`docs/E2E_BENCHMARK_EXECUTION.md`](../docs/E2E_BENCHMARK_EXECUTION.md).


## Social Attention baseline qualification

`manifests/social_attention_qualification_v1.json` defines the current
qualification identity and deterministic hard gates. E2E runs now retain
launcher-effective model topology, MindProfile, Social Interaction Style, apply
lanes, semantic authority, runtime topology, provider/hardware revisions, and
sample count. Optional Social Attention lifecycle evidence distinguishes proposal,
Host materialization, Provider acceptance/completion, and safe idle.

This is a logical behavior-domain track. Its adapter must exercise the ordinary
Fast/Deep Planner result and observe `auxiliary_activities[]`; it must not call or
emulate a separate Social Attention semantic endpoint. The benchmark `off`,
`report_only`, and `on` values are qualification conditions implemented by candidate
availability/execution observation, not product runtime switches.

Build a deterministic hard-gate report from retained E2E evidence with:

```bash
python -m benchmarks.social_attention \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --report benchmarks/reports/social-attention-live-service-off-courteous.json \
  --report benchmarks/reports/social-attention-live-service-off-custom.json \
  --report benchmarks/reports/social-attention-live-service-off-neutral.json \
  --report benchmarks/reports/social-attention-live-service-off-reserved.json \
  --report benchmarks/reports/social-attention-live-service-on-courteous.json \
  --report benchmarks/reports/social-attention-live-service-on-custom.json \
  --report benchmarks/reports/social-attention-live-service-on-neutral.json \
  --report benchmarks/reports/social-attention-live-service-on-reserved.json \
  --report benchmarks/reports/social-attention-live-service-report-only-custom.json \
  --report benchmarks/reports/social-attention-live-service-report-only-neutral.json \
  --report benchmarks/reports/social-attention-live-service-report-only-reserved.json \
  --output benchmarks/reports/social-attention-hard-gates.json
```

Each input report represents exactly one launcher-effective mode and one
owner-approved interaction style. The assembled report fails closed on missing
identity, scope drift, duplicate or missing scenario coverage, or required evidence
and always remains non-release-qualified. It checks explicit contracts only; it does not infer
naturalness, select a model winner, map phrases to actions, or create Runtime
behavior policy. See
[Social Attention Baseline Qualification](../docs/SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md).

## Stress and behavior-distribution evaluation

`stress/` repeats unchanged normalized scenarios under six versioned workloads:
long session, repetition/cooldown, interruption, concurrency, provider
degradation, and synthetic multi-user context isolation. Each workload reuses an
E2E evidence profile and declares sample count, sessions, concurrency,
seed, selectors, descriptive conditions, and observational dimensions.

Validate workloads with:

```bash
python -m benchmarks.stress.validate --check
```

Run one workload with:

```bash
python -m benchmarks.stress.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --workload long_session_social_attention \
  --command "python scripts/my_e2e_adapter.py" \
  --model local-model \
  --prompt-revision prompt-v1 \
  --mind-profile courteous
```

Compare compatible reports with:

```bash
python -m benchmarks.stress.compare \
  --input benchmarks/reports/model-a.json \
  --input benchmarks/reports/model-b.json
```

Reports include explicit denominators, evidence/status distributions, primary
task success, auxiliary and semantic behavior distributions, duplicate-cue
observations, invariant/forbidden-behavior families, latency p50/p95, session
drift, and 95% Wilson intervals. They do not define a target gesture frequency,
select a model winner, or carry Runtime policy authority. See
[`docs/STRESS_BENCHMARK_EVALUATION.md`](../docs/STRESS_BENCHMARK_EVALUATION.md).

## Maintained scenario migration

`manifests/scenario_migration_v1.json` is the authoritative classification for
all maintained scenario sources. Existing deterministic fixtures remain
referenced in place so stable IDs, Git provenance, general-ability metadata,
and evidence claims remain comparable. `manifests/suites.json` is a compatibility
redirect and no longer duplicates source rules.

Validate migration parity and run the file-backed suites with:

```bash
python -m benchmarks.scenarios check
python -m benchmarks.scenarios run --suite dialogue --no-write
```

Compatibility entrypoints and their criteria-based removal schedules are stored
in the migration manifest.

## Continuous scenario mining and review

`mining/` connects immutable episode-derived candidates to reviewed Benchmark
authoring. It indexes and clusters candidates, identifies related committed and
historical-regression cases, creates separate human review records bound to the
candidate fingerprint, emits controlled variation briefs, and promotes only an
approved candidate into the deterministic scenario tree.

```bash
python -m benchmarks.mining index --candidate-dir .chromie/scenario_candidates
python -m benchmarks.mining review candidate.json --decision approved \
  --reviewer owner-id --rationale "Reviewed regression boundary." \
  --output candidate.review.json
python -m benchmarks.mining promote candidate.json \
  --review candidate.review.json --id reviewed_regression_case
```

The mining workflow never commits changes, edits Prompts, changes personality or
Runtime policy, selects an action from a phrase, or grants release qualification.
See [Benchmark Scenario Migration and Continuous Review](../docs/BENCHMARK_SCENARIO_MIGRATION_AND_MINING.md).
