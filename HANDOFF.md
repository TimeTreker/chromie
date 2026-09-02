# Chromie Latest Handoff

Audience: coding agent resuming Issue #35 Fast/Deep Planner qualification or
reviewing the Goal Association integration on `main`.

Owner: project owner. Current source, tests, retained artifacts,
`DEVELOPMENT_CHECKPOINT.md`, and the active Issue win over chat history.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `main`
- Pre-delivery base: `origin/main` at
  `7605466bfe61aba1fbee70df1676d2005136a9e5`
- Merged branch: `codex/ga-prompt-qualification-paused-20260901`
- Expected resume revision: latest normal merge commit on `origin/main`
  containing this handoff and `DEVELOPMENT_CHECKPOINT.md`
- Completed delivery Issue: [#34](https://github.com/TimeTreker/chromie/issues/34),
  to be closed only after the merge push succeeds
- Next active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35)
- Post-push branch disposition: delete the merged feature branch locally and
  remotely after verifying `origin/main`

## Current truth

This `main` merge integrates the GA prompt/Schema/DTO/Host correction and both
frozen qualification corpora. A fresh integrated Codex cohort scored
1,500/1,500 strict with zero repair, recovery, timeout, or process failure. GA
remains the sole Goal identity/continuity authority:

```text
user turn + GI Responsibilities + bounded candidates/context
  -> exact GA prompt + dynamic Schema
  -> one target-blind primary result
  -> optional one mechanical malformed-DTO repair
  -> DTO / resolver / Host fail-closed validation
  -> hidden Responsibility-map adjudication
```

Do not add a confirmation, critic, scorer, or semantic repair call. Do not move
continuity, replacement, resource, referent, or Responsibility ownership to the
Host.

The owner explicitly corrected the qualification away from Qwen/Ollama as the
quality authority. The final source-branch Codex `gpt-5.6-sol` high-reasoning
cohort scored 1,500/1,500 strict with zero repair, recovery, timeout, or process
failure. Two of the allowed 10 Codex-led iterations were used; further GA tuning
requires new failing evidence.

## Integrated correction

- `reason_summary` is compact, non-authoritative, and emitted after the
  structured semantic result.
- Goal branches begin with source identity, output mode, and resource
  discriminator rather than a model-specific payload-first order.
- Replacement/coexistence/polarity, relationship precedence, description
  provenance, overlap rejection, and conservation rules remain intact.
- `media_playback` requires an explicit operation from the valid non-`none` set,
  closing the dynamic-Schema/DTO mismatch.
- The frozen GA 1,500-case and Fast Planner 1,000-case corpora, qualification
  runners, method/skill alignment, and focused tests are part of this merge.
- Stable Mind personalization from the pre-merge `main` line remains bounded
  and source-level; no active customer profile is created.

## Retained GA evidence

All artifact paths are ignored and machine-local; Git does not transport them.

- Final source-branch run:
  `.chromie/benchmarks/goal-association/20260902T-codex-iteration-02-full/`
  — 1,500/1,500 strict, zero repair/recovery/timeout/process failure.
- Final integrated run:
  `.chromie/benchmarks/goal-association/20260902T-main-integration-full/`
  — 1,500/1,500 strict, zero repair/recovery/timeout/process failure; source
  and harness stable.
- Production-files SHA-256:
  `aedd5ea9322c3f7d7aa277f15ea0b5ae00451e91d8e1ba835ebaf2e87803b5a4`
- Prompt identity index SHA-256:
  `6455efe3d42fa2baea2d6ca3077b9ff3147c3b204f4ae4559376e49541c03ec7`
- Corpus SHA-256:
  `e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`
- Provider/model: Codex / `gpt-5.6-sol`, high reasoning; Codex CLI
  `0.148.0-alpha.9`.

The corpus is assistant-authored, has no independent semantic review, and has
no non-empty discourse-referent or `interpretation_unresolved` cases.
Deterministic module tests cover those boundaries, but broader qualification
requires an independently reviewed corpus revision.

## Integrated validation ledger

```text
Integrated Codex target-blind cohort: 1,500/1,500 strict; 0 repairs,
0 recovery calls, 0 timeouts, 0 process failures; source/harness stable
Focused GA/referent/media/corpus tests: 114/114 passed
Relevant General Ability Level A: 28/28 passed
Repository policies: 15 rule families passed, 0 reviewed exceptions
Canonical local gate: exit 0; 138 pytest, 2,053 unittest, and 20 legacy
Agent tests passed, including policy, ownership, Ruff, Mypy, configuration,
documentation, scenario, and repository-structure checks
Final docs gate: 102 Markdown files passed
```

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
one earliest-boundary cluster before editing. The historical 349-call Fast run
was interrupted and must not be resumed or adjudicated.

## Claim boundary

This handoff records the integrated source delivery. GA qualification is
same-model offline Codex evidence, not deployed or independent semantic truth.
No Fast/Deep Planner, customer-visible Stable Mind, deployed service/model,
voice, simulator, target hardware, safety, release, or physical-robot claim is
established.
