# Chromie Latest Handoff

Audience: coding agent resuming the unqualified Goal Association model-role
candidate after the owner-authorized 10-iteration limit.

Owner: project owner. Replace this volatile snapshot when the checkpoint advances.
Current source, tests, retained artifacts, `DEVELOPMENT_CHECKPOINT.md`, and the
active Issue win over chat history.

## Repository and delivery state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `codex/ga-prompt-qualification-paused-20260901`
- Intended upstream: `origin/codex/ga-prompt-qualification-paused-20260901`
- Pre-delivery base: `5cb6977ab176044d99b1ae9007eca259c6da8377`
- Expected resume revision: the latest normal delivery commit containing this file
  and `DEVELOPMENT_CHECKPOINT.md`.
- Remote sibling `origin/codex/ga-prompt-qualification-1500` remains at `0f525f3a`.
  It was not merged, rebased, rewritten, or force-pushed.
- Active Issue: [#34](https://github.com/TimeTreker/chromie/issues/34). Issue #35
  Fast/Deep Planner qualification remains paused because GA is not qualified.

## Current truth

The configured `qwen3.5:4b` GA role is not good enough. The final exact-provider
focused gate scored 5/9 strict after 10 total semantic iterations. A local 9B
comparison scored 4/9 and was not configured or deployed. No final current-source
1,500-case cohort was run because the focused prerequisite failed.

The retained candidate keeps GA as the only Goal-identity/continuity authority:

```text
user turn + GI Responsibilities + bounded Goal candidates
  -> production GA prompt + dynamic Schema
  -> one target-blind primary Ollama result
  -> optional one mechanical malformed-DTO repair
  -> DTO / resolver / Host fail-closed validation
  -> hidden Responsibility-map adjudication
```

Do not add a confirmation, critic, scorer, or semantic repair call. Do not move
replacement, resource, or Responsibility ownership to the Host.

## Implemented candidate scope

- DTO and dynamic Schema reject overlap between `related_goal_ids` and
  `supersedes_goal_ids` before Host materialization.
- Prompt distinguishes explicit replacement, positive coexistence, independent new
  work, relationship precedence, and new-Goal description provenance.
- Top-level continuity evidence is bounded and generated before the collections;
  Goal branch fields use the focused mechanically stable order. These remain
  unqualified production candidates.
- The frozen runner supports both Codex surrogate and exact Ollama modes, binds
  model/version/digest/options, uses production `OllamaClient`, retains raw output
  and execution records, and rechecks source/harness/model stability.
- Frozen Schema JSON now preserves production object-key order. Canonical hashing
  remains order-insensitive, while constrained decoding receives production order.
- Existing tests cover overlap rejection, prompt invariants, Schema order,
  production options, order-preserving freezing, and Ollama transport.

No runtime configuration or deployed model was changed.

## Failure workflow

| Boundary | Actual result | Required result | State |
|---|---|---|---|
| GI Responsibility | Correct `new`/empty-target versus targeted relationship evidence | Preserve local-ref ownership | Correct |
| Primary GA model | Sometimes states correct rationale, then emits both association and new Goal, supersedes retained work, or treats blinking as a physical resource | Exactly one owner per ref; body action remains non-resource; replace only with direct source evidence | Earliest remaining failure |
| Schema / DTO | Rejects duplicate ownership, overlap, wrong resource branch, and malformed fields | Fail closed without semantic reinterpretation | Correct containment |
| Resolver / Host | Commits complete conserved output or fails closed | No downstream repair | Correct containment |

## Retained local evidence

All paths below are ignored and machine-local; Git does not transport them.

### Same-model offline qualification

`.chromie/benchmarks/goal-association/20260902T-relationship-precedence-full/`

- 1,500/1,500 strict, zero repair/timeout.
- This remains Codex-surrogate evidence only and does not qualify Ollama.

### Interrupted and invalid exact-provider baselines

- `.chromie/benchmarks/goal-association/20260902T-qwen35-4b-deployed-baseline/`
  stopped at 1,275/1,500 when the task was interrupted. It is incomplete and must
  never be resumed or reported as a cohort result.
- `.chromie/benchmarks/goal-association/20260902T-qwen35-4b-deployed-baseline-rerun/`
  completed 1,500 calls and initially appeared to score 1,184 hard / 1,170 strict,
  with 22 repairs, 15 Host recoveries, and four truncations. It is not an exact
  production-Schema claim because the runner had sorted frozen Schema keys before
  sending them to constrained decoding.

### Exact-order diagnosis and final focused gates

- `.chromie/benchmarks/goal-association/20260902T-qwen35-4b-iteration8-focused9-exact-order/`
  — exact production order; 3/9 hard, five repairs, one primary truncation.
- `.chromie/benchmarks/goal-association/20260902T-qwen35-4b-iteration9-focused9/`
  — final configured-model candidate; 5/9 strict, zero repair/timeout, stable
  source/harness/model.
- `.chromie/benchmarks/goal-association/20260902T-qwen35-9b-iteration10-focused9/`
  — 9B comparison only; 4/9 strict, one repair, stable source/harness/model.

Configured model identity:

```text
Ollama 0.32.14
qwen3.5:4b, 4.7B Q4_K_M
digest 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
num_ctx=32768 num_predict=2048 temperature=0 top_p=0.9
```

Comparison identity:

```text
qwen3.5:9b, 9.7B Q4_K_M
digest 6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7
```

Frozen corpus digest:
`e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`.

## Validation ledger

Observed on the delivery candidate:

```text
python -m pytest -q \
  tests/test_goal_association_pr2.py \
  tests/test_goal_association_contract_module.py \
  benchmarks/tests/test_goal_association_daily_life_dataset.py
# 94 passed

python scripts/check_repository_policies.py
# 15 rule families passed, 0 reviewed exceptions

./scripts/run_tests.sh
# exit 0; 138 pytest, 2,050 unittest, and 20 legacy Agent tests passed after
# policy, ownership, static-analysis, configuration, structure, documentation,
# and scenario checks

python scripts/check_docs.py
# 102 Markdown files passed
```

These green repository gates establish code/document consistency only. They do not
override the failed exact-model semantic qualification gate.

## Resume commands

Inspect the delivered state:

```bash
git fetch origin
git switch codex/ga-prompt-qualification-paused-20260901
git status --short --branch
git log -1 --oneline --decorate
git diff --check HEAD^ HEAD
```

Review the final configured-model evidence:

```bash
jq . \
  .chromie/benchmarks/goal-association/20260902T-qwen35-4b-iteration9-focused9/adjudication-summary.json

find \
  .chromie/benchmarks/goal-association/20260902T-qwen35-4b-iteration9-focused9/adjudication \
  -type f -name '*.json' -print0 \
  | xargs -0 jq -c 'select(.hard_pass == false) | {scenario_id,host,schema,target_region}'
```

After owner authorization for a new iteration budget, prepare a fresh immutable
focused batch rather than editing an existing evidence directory:

```bash
python benchmarks/datasets/goal_association_daily_life/qualification.py prepare \
  --output-dir .chromie/benchmarks/goal-association/<new-label> \
  --label <new-label> \
  --provider ollama \
  --model qwen3.5:4b \
  --ollama-url http://127.0.0.1:11434 \
  --num-ctx 32768 \
  --num-predict 2048 \
  --timeout-ms 120000 \
  --only-case ga_daily_v1_07_00_supersede_existing \
  --only-case ga_daily_v1_07_01_supersede_existing \
  --only-case ga_daily_v1_07_02_supersede_existing \
  --only-case ga_daily_v1_07_00_unrelated_new_goal \
  --only-case ga_daily_v1_07_01_unrelated_new_goal \
  --only-case ga_daily_v1_07_02_unrelated_new_goal \
  --only-case ga_daily_v1_07_00_mixed_continue_and_new_contract_gap \
  --only-case ga_daily_v1_07_01_mixed_continue_and_new_contract_gap \
  --only-case ga_daily_v1_07_02_mixed_continue_and_new_contract_gap

python benchmarks/datasets/goal_association_daily_life/qualification.py run \
  --output-dir .chromie/benchmarks/goal-association/<new-label> \
  --concurrency 1 \
  --timeout-s 140

python benchmarks/datasets/goal_association_daily_life/qualification.py adjudicate \
  --output-dir .chromie/benchmarks/goal-association/<new-label>
```

Require 9/9 strict with no repair, recovery, timeout, or truncation before running
the affected full categories and then a fresh complete 1,500-case cohort.

## Claim boundary

This handoff records an unqualified GA production candidate and exact local Ollama
evidence. It establishes no full-corpus deployed-model qualification, independent
semantic review, Fast/Deep Planner quality, training eligibility, service, voice,
simulator, hardware, safety, release, or physical-robot evidence.
