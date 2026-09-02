# Chromie Latest Handoff

Audience: coding agent resuming Issue #35 Fast/Deep Planner qualification or
reviewing the integrated Stable Mind source boundary.

Owner: project owner. This operational snapshot is subordinate to current
source, tests, `DEVELOPMENT_CHECKPOINT.md`, and the active Issue.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `main`
- Pre-delivery base: `origin/main` at
  `a10eab83379353c1e51862d319ec3decedea668a`
- Expected resume revision: latest `origin/main` commit containing this handoff
  and `DEVELOPMENT_CHECKPOINT.md`
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35)
- Delivery scope: merge `codex/customer-mind-personalization` into `main`,
  retain its bounded Stable Mind implementation and owned documentation, and
  refresh the exact next-session handoff. The already-integrated
  `refactor/complexity-cleanup-round2` branch required no code merge.

## Integrated Stable Mind boundary

```text
factory MindProfile
  + owner-confirmed bounded CustomerMindPersonalization
  -> deterministic complete derived profile
  -> strict recomputation/validation
  -> Host and Agent select one active profile
  -> bounded projection to Fast Planner, Deep Planner, and Reflection
```

Customer input is never raw prompt text and cannot override safety, privacy,
consent, truthfulness, embodiment, evidence, or the person's current explicit
intent. The configuration CLI previews by default; `--apply` uses atomic
replacement with private mode and backup, while `--reset` retains a recoverable
backup. No active customer profile was created by this merge.

The newly integrated files are the customer-profile contract/derivation,
Host/Agent selection, bounded model-role projection, preview/apply/reset CLI,
focused tests, and existing configuration/mind/status/user-manual owners.
No new model invocation, semantic authority, environment variable, Runtime
switch, compatibility path, provider, or hardware behavior was added.

## Fast Planner qualification state

`benchmarks/datasets/fast_planner_daily_life/` holds 1,000 separate bilingual
scenarios in 100 contrast sets. Its tree digest is
`8b5133b32e85eebd3587f2a63fff394cd02094b798ac8948d7ca9e350175579b`.
The prior immutable baseline in
`.chromie/benchmarks/fast-planner/20260901T053409Z_fp_daily_v1_codex_baseline/`
was stopped at owner request after 349 complete calls (with an interrupted 350th
envelope). It is incomplete: do not resume or adjudicate it, and do not claim
Fast Planner qualification from it.

## Validation ledger

Historical customer-branch results (not integrated-tree evidence):

```text
python -m pytest tests/test_mind_profile.py tests/test_cognitive_identity_context.py tests/test_configure_chromie_mind.py
28 passed in 0.51s
```

Canonical validation on the staged merge tree observed on 2026-09-02:

```text
python scripts/check_repository_policies.py
Repository engineering policies passed (15 rule families, 0 reviewed exceptions)

./scripts/run_tests.sh
exit 0; all checks passed, including policy, test ownership, Ruff, Mypy,
configuration, documentation, scenario, and repository-structure gates
```

This is automated source/document evidence on the staged merge tree; it does
not substitute for deployed, customer-visible, or target evidence.

No deployed Agent restart, exact provider/model check, household authentication,
voice, microphone, simulator, target hardware, physical safety, or release
evidence was collected for the Stable Mind integration.

## Cross-machine resume

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Then begin the Fast Planner target-blind cohort from a fresh output directory:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate

FP_RUN_DIR=.chromie/benchmarks/fast-planner/NEW_RUN_ID_fp_daily_v1_codex_baseline
python -m benchmarks.datasets.fast_planner_daily_life.qualification prepare \
  --label baseline-v1 --output-dir "$FP_RUN_DIR"
python -m benchmarks.datasets.fast_planner_daily_life.qualification run \
  --output-dir "$FP_RUN_DIR" --concurrency 16 --timeout-s 600
python -m benchmarks.datasets.fast_planner_daily_life.qualification adjudicate \
  --output-dir "$FP_RUN_DIR"
```

Keep the entire cohort source-stable. Inspect every adjudicated case and select
one earliest-boundary cluster before editing. For future customer-visible Stable
Mind work, use the same deterministic derivation/validation boundary and retain
authenticated owner confirmation plus deployed-model and service-restart evidence.

## Claim boundary

This is an integrated source delivery. It does not establish customer-visible
personalization, Planner prompt quality, deployment, model, voice, simulator,
hardware, safety, or release readiness.
