# Chromie Latest Handoff

Audience: coding agent reviewing or delivering the qualified Goal Association
candidate on `codex/ga-prompt-qualification-paused-20260901`.

Owner: project owner. Current source, tests, retained artifacts,
`DEVELOPMENT_CHECKPOINT.md`, and Issue #34 win over chat history.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `codex/ga-prompt-qualification-paused-20260901`
- Upstream: `origin/codex/ga-prompt-qualification-paused-20260901`
- Pre-delivery baseline:
  `ec34652f29f7957182b0104cc1fa57a3d0050cf3`
- Expected resume revision: the latest normal delivery commit containing this file
  and `DEVELOPMENT_CHECKPOINT.md` on the branch and upstream above.
- Delivery files: `agent/app/goal_association_contract.py`,
  `agent/app/goal_association_prompt.py`,
  `agent/app/goal_association_schema.py`,
  `tests/test_goal_association_pr2.py`, this file, and
  `DEVELOPMENT_CHECKPOINT.md`.
- No merge, rebase, force-push, runtime configuration change, or deployment is part
  of this delivery.
- The local `main` line and this branch are divergent; do not transfer the GA-green
  claim without integration and a fresh revision-bound rerun.
- Remote sibling `origin/codex/ga-prompt-qualification-1500` was not changed.
- Active Issue: [#34](https://github.com/TimeTreker/chromie/issues/34).

## Current truth

The exact current branch candidate is qualified at the same-model offline Codex
surrogate level: 1,500/1,500 strict, zero repair, recovery, timeout, or process
failure. The owner explicitly corrected the task away from Qwen/Ollama as the
quality authority. Old Qwen evidence remains historical only.

GA remains the sole Goal identity/continuity authority:

```text
user turn + GI Responsibilities + bounded candidates/context
  -> exact GA prompt + dynamic Schema
  -> one target-blind Codex primary result
  -> optional one mechanical malformed-DTO repair
  -> DTO / resolver / Host fail-closed validation
  -> hidden Responsibility-map adjudication
```

Do not add a confirmation, critic, scorer, or semantic repair call. Do not move
continuity, replacement, resource, referent, or Responsibility ownership to the
Host.

## Implemented correction

- `reason_summary` is non-authoritative and emitted after the structured semantic
  result; collections/decision own the decision.
- Request-bound Goal branches begin with source identity, output mode, and resource
  discriminator rather than a Qwen-specific payload-first order.
- Existing replacement/coexistence/polarity, relationship precedence,
  description provenance, overlap rejection, and conservation rules remain.
- `media_playback` branches require an explicit operation from the valid non-`none`
  set, closing the dynamic-Schema/DTO mismatch that caused one mechanical repair.

## Retained evidence

All paths are ignored and machine-local; Git does not transport them.

- Baseline:
  `.chromie/benchmarks/goal-association/20260902T-codex-current-branch-baseline/`
  — 1,500/1,500 strict, zero repair/failure.
- Iteration 1 focused:
  `.chromie/benchmarks/goal-association/20260902T-codex-iteration-01-focused/`
  — 6/6 strict.
- Iteration 1 full:
  `.chromie/benchmarks/goal-association/20260902T-codex-iteration-01-full/`
  — 1,498 hard / 1,497 strict; two capacity failures and one media repair.
- Iteration 2 focused:
  `.chromie/benchmarks/goal-association/20260902T-codex-iteration-02-focused/`
  — 3/3 strict, including the repaired media case and both capacity cases.
- Final iteration 2 full:
  `.chromie/benchmarks/goal-association/20260902T-codex-iteration-02-full/`
  — **1,500/1,500 strict**, zero repair/recovery/timeout/process failure.

Final identities:

```text
provider: codex
model: gpt-5.6-sol
reasoning effort: high
Codex CLI: 0.148.0-alpha.9
production-files sha256: aedd5ea9322c3f7d7aa277f15ea0b5ae00451e91d8e1ba835ebaf2e87803b5a4
prompt identity index sha256: 6455efe3d42fa2baea2d6ca3077b9ff3147c3b204f4ae4559376e49541c03ec7
corpus sha256: e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0
```

## Validation ledger

```text
python -m pytest -q \
  tests/test_scoped_referent_contract.py \
  tests/test_goal_association_pr2.py \
  tests/test_goal_association_contract_module.py \
  tests/test_media_provider_contract.py \
  benchmarks/tests/test_goal_association_daily_life_dataset.py
# 114 passed

python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class planner_goal_semantic_quality \
  --ability-class robust_intent_understanding \
  --ability-class human_like_cognitive_continuity \
  --ability-class multi_goal_daily_life \
  --ability-class natural_uncertainty_handling --no-write
# 28 passed, 0 failed

python scripts/check_repository_policies.py
# 15 rule families passed, 0 reviewed exceptions

./scripts/run_tests.sh
# exit 0; 138 pytest, 2,050 unittest, 20 legacy Agent tests passed

python scripts/check_docs.py
# 102 Markdown files passed after this handoff rewrite
```

## Review commands

```bash
git status --short --branch
git diff --check HEAD^ HEAD
git diff HEAD^ HEAD -- \
  agent/app/goal_association_contract.py \
  agent/app/goal_association_prompt.py \
  agent/app/goal_association_schema.py \
  tests/test_goal_association_pr2.py \
  DEVELOPMENT_CHECKPOINT.md HANDOFF.md

jq . \
  .chromie/benchmarks/goal-association/20260902T-codex-iteration-02-full/adjudication-summary.json

python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

## Resume state and claim boundary

Two of the owner-authorized maximum 10 Codex-led iterations were used. The stop
condition is met; do not continue tuning without new failing evidence.

The 1,500-case corpus is assistant-authored, has no independent semantic review,
and does not contain non-empty discourse-referent or `interpretation_unresolved`
examples. Deterministic referent/unresolved tests and 28 relevant Level-A cases
pass, but independent review or a broader frozen corpus is required for a broader
whole-role or training-readiness claim.

This handoff establishes only same-model offline Codex qualification for the exact
current branch candidate. It establishes no Qwen/Ollama quality, deployed service,
divergent-main, independent-review, Fast/Deep Planner, voice, simulator, hardware,
safety, release, or physical-robot evidence.
