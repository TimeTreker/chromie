# Chromie Latest Handoff

Audience: the project owner or coding agent resuming Issue #35 final Fast and
deployed-model qualification after the Planner authority and workflow-watchdog
delivery.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and delivery state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Pre-delivery base: `bc278c9f71239a173f098fa9d6599f03f2b4fdd5`
- `origin/main` was fetched on 2026-09-04 and matched that base (0 ahead/0 behind).
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35)
- Expected resume revision: latest normal `origin/main` commit containing this
  file and `DEVELOPMENT_CHECKPOINT.md`.

## Delivered behavior and root cause

The originating bundle is machine-local:
`.chromie/debug/debug_bundle_20260902_221509/`.

For `你好。`, GI correctly authored one greeting Responsibility. GA and Fast
started concurrently as designed; GA completed at 5903.1 ms and Fast emitted a
valid presentation commit at 7958.7 ms. The outer cognitive-runtime watchdog
cancelled the still-legal workflow at 9055.1 ms before terminal completion, and
the fallback spoke `咦，刚才没接上。你再跟我说一遍嘛。`. Later calls then hit GI
`ReadTimeout` while the single-slot Ollama Qwen runner remained contended.

The earliest wrong boundary was the outer workflow watchdog, not greeting
semantics. The delivery preserves concurrent GA/Fast startup and changes the
unqualified development watchdogs to cover the legal workflow:

```text
Agent GA/Fast: 60000 ms
Agent Deep: 120000 ms
Host GA/Fast: 65000 ms
Host Deep: 125000 ms
Outer cognitive runtime: 300000 ms
```

These are watchdogs, not latency objectives. Slow interaction still fails the
latency acceptance axis; do not tighten the watchdogs again without retained
workflow latency and cancellation-margin evidence. `.env.runtime` is generated
and was not edited.

## Planner authority now in source

```text
immutable GI result
  ├─ Goal Association (concurrent Goal continuity authority)
  └─ Fast Planner one primary HOW invocation
       ├─ validated presentation_commit
       └─ terminal_plan
            └─ Deep Planner only for genuinely deeper cognition,
               from authoritative Goals/context rather than a Fast candidate
```

Fast/Deep same-tier critic, repair, revision, and qualification calls are gone.
Host validation no longer repairs semantic fields. Deep receives the full
bounded capability catalog, and both Planner tiers must author complete Goal
outcomes, evidence interpretation, satisfaction, wording, Work, timing, and
confirmation semantics in their primary result. Keep deterministic stop/cancel/
emergency paths unchanged.

## Qualification artifacts

Artifacts under `.chromie/` are ignored and machine-local.

### Fast Planner

- Complete diagnostic predecessor:
  `.chromie/benchmarks/fast-planner/20260904T-fast-v21-qualified-full/`
- 204/204 successful processes, Schema accepted, Host accepted, and hidden
  target-region passed; 0 timeout/process failure; source/harness stable.
- Breakdown: English 102/102, Chinese 102/102; canonical primary 72/72,
  canonical re-entry 80/80, streaming advance 52/52.
- Predecessor production-files digest:
  `960141dc7e351d3a452a2f14b35fe99fd21e16669bf657230c1ffad7122aa114`
- Same-model review:
  `.chromie/benchmarks/fast-planner/20260904T-fast-v21-qualified-full/semantic-review-final-v2/`
  passed 201/204. The three failures correctly exposed two date-rotted
  resource-composition inputs and one genuine defect: unsupported praise of an
  unspecified plan.
- Current focused repair:
  `.chromie/benchmarks/fast-planner/20260904T-fast-v22-focused-unspecified-plan/`
  passed 1/1 process, Schema, Host, and hidden target-region checks after the
  prompt prohibited evaluating details that the source never supplied.
- Current production-files digest:
  `0c07329afc04855a609dceac6452e95191759d26e5113c06c0244d8362c36398`
- Current production tracked-diff digest:
  `4daf8377d1c1ccf631d0278ca8b844a7fa43edfeadd81119807cbbaf096b4c26`
- Current corpus tree digest:
  `b5da6e022886effd3b9618384e48914775e7a742b19cbe584f9c1826227eb669`
- Current full-rerun blocker:
  `.chromie/benchmarks/fast-planner/20260904T-fast-v24-qualified-full/`
  attempted 115/204 cases before stop: 23 completed and 92 timed out at 180 s
  with no output. Logs contain request timeouts, WebSocket/TLS disconnects, and
  MCP initialization failures. This is an incomplete provider-integrity batch,
  not a semantic result.

Do not promote v12/v14/v16/v23/v24. V17 and v19 exposed date-rotted corpus
inputs. V21 is a complete predecessor; it is not a full final-prompt result.

### Deep Planner

- Final full cohort:
  `.chromie/benchmarks/deep-planner/20260904T-deep-v15-qualified-full/`
- 40/40 process/Schema/Host/target-region passes; English 20/20, Chinese 20/20;
  primary 24/24, re-entry 16/16; 0 timeout/process failure.
- Same-model post-hoc semantic review: 40/40 pass.
- Production-files digest:
  `482b22aea8cb3eadf4bb2fbb25e6dda2f219d061e57513850286c18d6a34d495`
- Production tracked-diff digest:
  `6ef07ee85f764599d06c5b2ba2adfc7cad5adb1da395edead37f709a4e2ea63f`
- Corpus tree digest:
  `a0c79e38cf4055b7021a4dcc1cbd0a2caec915872174d41e9c2bf153a4a7406a`

Both semantic reviews use `gpt-5.6-sol`, the same model family as candidate
generation. They are non-independent. Every scenario remains
`training_eligible=false` and `independent_semantic_review=false`.

## Coverage contract

Fast contains 204 design-derived cases: 17 Planner capacities, three distinct
daily-life families per capacity, supported/boundary contrasts, and English/
Chinese pairs. The 51 contrast sets cover 15 daily-life families and three
runtime entry shapes. Deep adds 40 separate cases for complex composition,
evidence/cancellation semantics, and primary/re-entry behavior.

This is stronger logical coverage than the replaced 1,500-case cross-product,
whose apparent size was dominated by repeated labels and stale DTOs. It is not
exhaustive-world or statistical reliability evidence. See
`benchmarks/datasets/fast_planner_daily_life/README.md`.

## Local validation

```text
Fast corpus validation: 204/204
Deep corpus validation: 40/40
Planner-related General Ability Level A: 46/46
Repository policy: 15 rule families, 0 reviewed exceptions
Test ownership: passed
Docs: 102 Markdown files passed after final handoff refresh
Canonical local gate: 140 pytest, 2055 unittest, and 20 legacy Agent tests passed;
all policy, ownership, Ruff, Mypy, configuration, and documentation stages passed
```

Do not translate Level A or same-model offline evidence into deployed service,
voice, simulator, GPU, target-hardware, or physical-robot claims.

## Serving and QLoRA decision

The vLLM isolation probe passed strict JSON, SSE, short-request concurrency,
cancellation isolation, and health recovery. Semantic screens did not: Qwen3.5-
4B scored 1/5 and Qwen3.5-9B 2/5; two long streams also slowed TTS first audio
2.37×. Current Ollama Qwen exposes one sequence slot and cannot realize GA/Fast
inference overlap.

Do not begin SFT yet. The next legitimate sequence is:

1. independently review the 204 Fast and 40 Deep cases and correct any labels;
2. run them target-blind through the exact deployed Qwen3.5-4B + decoder +
   transport profile;
3. cluster failures by earliest boundary;
4. only then form an approved train/validation/frozen split for QLoRA and compare
   the tuned checkpoint against the untouched frozen holdout;
5. qualify vLLM separately as transport and under GA/Fast plus TTS contention.

## Resume commands

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate
python -m benchmarks.datasets.fast_planner_daily_life.deep_qualification validate
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Then start a new immutable output directory for the exact deployed target-model
cohort. Never resume or patch an old batch, change source between cases, average
a hard failure into a pass, or approve training data from same-model review.

## Claim boundary

This handoff records source correction, Deep same-model offline qualification,
and focused Fast repair evidence. Full current-source Fast qualification remains
open behind the recorded provider failure. It does not qualify deployed Qwen/
Ollama/vLLM, independent semantics, QLoRA data, live voice, simulator, GPU
coexistence, target hardware, physical safety, release readiness, or customer-
visible behavior.
