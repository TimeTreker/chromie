# Chromie Development Checkpoint

Status: customer-configurable Stable Mind is integrated into `main`; the Fast
Planner 1,000-scenario corpus is complete and digest-frozen, while its first
target-blind baseline remains deliberately incomplete. Fast/Deep qualification
and current-revision target evidence remain open.

Updated: 2026-09-02

Pre-delivery baseline: `origin/main` at
`a10eab83379353c1e51862d319ec3decedea668a`.

Expected resume revision: latest `origin/main` commit containing this checkpoint
and `HANDOFF.md`.

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35).

Current focus: preserve Chromie's Goal-driven single-authority architecture while
qualifying Fast Planner first and Deep Planner second. Stable Mind personalization
supplies bounded durable context only; it does not move semantic authority out of
Goal Interpretation, Goal Association, Planner, Runtime, or Evidence owners.

## Integrated scope

- `codex/customer-mind-personalization` is integrated. Its bounded Stable Mind
  personalization reuses the existing `MindProfile` authority: a deterministic
  customer-derived profile may alter only reviewed identity presentation,
  worldview, household values, and social style; factory safety, consent,
  privacy, truthfulness, embodiment, evidence, and current-intent facts remain
  protected.
- Host and Agent select the same validated active profile when no explicit
  profile path is set. Fast Planner, Deep Planner, and Reflection receive one
  bounded Stable Mind projection. `scripts/configure_chromie_mind.py` remains
  preview-first; `--apply` is atomic and recoverable, and `--reset` creates a
  timestamped backup.
- No new semantic authority, model call, Runtime switch, environment variable,
  compatibility path, or product profile is introduced. The Stable Mind feature
  remains source-level only; no customer authentication/UI, deployed model,
  service-restart, voice, simulator, or hardware claim exists.
- `refactor/complexity-cleanup-round2` was already an ancestor of the
  pre-delivery `origin/main` tip, so no duplicate merge was made.

## Current qualification boundary

The Fast Planner corpus remains 1,000 independent bilingual scenarios in 100
ten-member contrast sets, with tree SHA-256
`8b5133b32e85eebd3587f2a63fff394cd02094b798ac8948d7ca9e350175579b`.
The previous baseline was intentionally stopped after 349 complete calls and
must not be resumed or adjudicated. It establishes no prompt-quality, deployed,
voice, simulator, hardware, safety, or release result.

The existing GA mixed-decision DTO gap remains separate from Issue #35. Do not
add a reviewer, semantic repair call, or new authority to address it.

## Evidence ledger

| Evidence | Observed result | Limit |
|---|---|---|
| Stable Mind branch focused tests | `28 passed in 0.51s` before its original delivery | Historical branch-local source evidence only |
| Stable Mind branch canonical gates | Policy, full test suite, and docs gate passed before its original delivery | Historical branch-local evidence only |
| Integrated merge validation | `python scripts/check_repository_policies.py` passed; `./scripts/run_tests.sh` exited 0 with all checks passed | Automated source/document evidence on the staged merge tree only |
| Fast Planner baseline | 349 complete retained calls; cohort interrupted at owner request | Incomplete; do not resume/adjudicate |
| Live/deployed/voice/simulator/hardware evidence | Not run for this integration | No such claim exists |

## Ordered resume work

1. Pull the latest `main`, read this checkpoint, `HANDOFF.md`, Issue #35, and
   the frozen Fast Planner corpus README/manifest.
2. Run a fresh immutable 1,000-case Fast target-blind cohort; do not reuse the
   interrupted run or change source, prompt, Schema, model, or corpus during it.
3. Adjudicate every result through the production parser/DTO/Host boundary,
   inspect semantic facts, and cluster failures by earliest shared boundary.
4. Make at most one minimal evidenced correction, prove it on a focused case,
   then rerun the complete cohort and the applicable General Ability and
   canonical gates. Qualify Deep separately, then rerun both Planner cohorts.
5. Before a customer-visible Stable Mind feature claim, qualify an active profile
   through an authenticated setup surface, exact deployed model, and real service
   restart, retaining the factory/customer digests and runtime identity.

## Claim boundary

This merge integrates source and tests only. It does not qualify Stable Mind
personalization, Fast/Deep Planner behavior, a deployed service/model, voice,
simulator, target hardware, physical safety, or release readiness.
