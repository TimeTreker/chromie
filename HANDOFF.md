# Chromie Latest Handoff

Audience: coding agent resuming Issue #35 Fast/Deep Planner prompt qualification.

Owner: project owner. Replace this volatile snapshot when the checkpoint advances.
Current source, tests, retained evidence, `DEVELOPMENT_CHECKPOINT.md`, and Issue #35
win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `codex/ga-prompt-qualification-1500`
- Upstream: `origin/codex/ga-prompt-qualification-1500`
- Pre-delivery base: `ac83e4677d67014f3d547823d9568abf95c09834`
- Expected resume revision: latest upstream commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35)
- Delivery scope: incomplete Fast Planner LLM-authored scenario checkpoint and
  unfinished qualification harness scaffolding; no production Planner change

The worktree is expected to remain dirty after delivery because the project owner's
unrelated architecture-diagram work in `README.md` and `docs/assets/` is deliberately
excluded from this commit. Do not discard, stage, or rewrite those paths.

## Tracked checkpoint

`benchmarks/datasets/fast_planner_daily_life/` contains:

- 10 separate scenario JSON files under
  `scenarios/train_candidate/stream_direct_conversation/`;
- five paired `en-US`/`zh-CN` family/home conditions authored by retained call
  `fp-author-001` using `gpt-5.6-sol`, high reasoning;
- `catalogs/common_v1.json`;
- incomplete `qualification.py` and `validate.py` harness scaffolding;
- a README that explicitly marks the corpus as incomplete; and
- no `dataset.json`, frozen digest, complete-corpus test, baseline inference, or
  adjudication summary.

`benchmarks/README.md` and `docs/README.md` index the in-progress work area. No
production file under `agent/`, `orchestrator/`, `shared/`, profiles, or runtime
configuration changed.

## Retained local authoring material

These ignored paths do not transfer with the Git push:

```text
.chromie/benchmarks/fast-planner/llm-authoring-v1/
.chromie/benchmarks/fast-planner/llm-authoring-v1/fp-author-001-envelope.json
.chromie/benchmarks/fast-planner/llm-authoring-v1/authoring-calls/
.chromie/benchmarks/fast-planner/llm-authoring-v1/authoring-logs/
```

Observed at handoff:

- 78 additional completed output envelopes and 78 corresponding logs exist for
  calls `fp-author-002` through `fp-author-078`, plus `fp-author-080`;
- calls `fp-author-079` and `fp-author-081` through `fp-author-087` were running
  when the exact authoring process group was terminated;
- the remaining assigned calls had not started;
- the interrupted process did not write `authoring-executions.json`; and
- none of those envelopes has been accepted as tracked corpus or qualification
  evidence.

Discarded script-generated material is retained only as provenance that must not be
reintroduced or cited:

```text
.chromie/benchmarks/fast-planner/discarded-script-generated-corpus-20260831T092909Z/
.chromie/benchmarks/fast-planner/20260831T092450Z_fp_daily_v1_discarded_no_inference_harness-path/
.chromie/benchmarks/fast-planner/20260831T092621Z_fp_daily_v1_discarded_no_inference_codex-schema-mismatch/
.chromie/benchmarks/fast-planner/20260831T092909Z_fp_daily_v1_discarded_partial_freeze_script_corpus/
```

## Actual workflow state

```text
authority/workflow audit
  -> intended 100 bilingual contrast sets / 1,000 scenarios
  -> one accepted 10-scenario LLM-authored probe tracked
  -> 78 additional LLM envelopes retained but unreviewed
  -> authoring interrupted and stopped
  -> corpus freeze NOT reached
  -> immutable Fast baseline NOT run
  -> failure diagnosis / optimization NOT started
  -> Deep qualification NOT started
```

The harness is intended to reconstruct the real production prompt and dynamic
Schema, prepare target-blind packets, invoke one declared Codex call per scenario,
and replay raw output through the Fast parser and Host validator with same-tier
semantic repair disabled. That intended behavior is untested on this checkpoint.

## Validation ledger

No tests or gates were run on the final tracked tree because the owner explicitly
requested immediate commit/push without testing.

Earlier in the work, before the owner rejected script-generated scenarios, the now-
discarded corpus produced these observations:

```text
python -m pytest -q benchmarks/tests/test_fast_planner_daily_life_dataset.py
3 passed in 50.06s
```

A direct `pytest -q` invocation of that test failed during import because it did not
use the repository's module invocation. Both observations apply only to removed,
script-generated material and provide no evidence for the final model-authored
checkpoint.

Not run on the final tree:

```text
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
git diff --check
```

The current work must therefore be treated as untested and unqualified.

## Cross-machine resume

```bash
git fetch origin codex/ga-prompt-qualification-1500
git switch codex/ga-prompt-qualification-1500
git pull --ff-only
```

The ignored LLM envelopes are available only on the originating machine. On that
machine, resume from `.chromie/benchmarks/fast-planner/llm-authoring-v1/`; on another
machine, re-author missing scenario sets through new retained LLM calls. Do not
replace LLM authorship with a scenario generator.

After completing and freezing the corpus, run the validator, focused corpus test,
immutable baseline, adjudication, applicable General Ability class, and canonical
gates before changing the Planner prompt or making any qualification claim. If a
case exposes a global identity/worldview/value or semantic-authority change, retain
the blocker and obtain explicit owner authorization first.

## Claim boundary

This handoff records a partial authoring checkpoint only. It does not qualify or
optimize Fast/Deep Planner workflow, contract, architecture, prompt, context, Schema,
Host validation, model quality, or robot behavior. It establishes no deployed,
voice, simulator, hardware, safety, release, or independent-review evidence.
