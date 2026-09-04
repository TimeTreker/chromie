# Chromie Latest Handoff

Audience: the project owner or coding agent resuming Issue #35 independent
semantic review or surrounding-transaction optimization after fixed-Codex Fast
Planner qualification.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and delivery state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Current evaluated revision: `04dd76fcb2c59f452bcd09cd2d6b5336e8e5b740`
  (`origin/main`, 0 ahead/0 behind before the current uncommitted qualification
  patch)
- Pre-delivery base: `bc278c9f71239a173f098fa9d6599f03f2b4fdd5`
- `origin/main` was fetched on 2026-09-04 and matched the current evaluated
  revision (0 ahead/0 behind before the current uncommitted qualification patch).
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
- Pre-supportive-repair production-files digest:
  `0c07329afc04855a609dceac6452e95191759d26e5113c06c0244d8362c36398`
- Current corpus tree digest:
  `2650948b9027071c948bb75481d203104923b4aff2bfc33750288d350679c2d8`
- Historical full-rerun blocker:
  `.chromie/benchmarks/fast-planner/20260904T-fast-v24-qualified-full/`
  attempted 115/204 cases before stop: 23 completed and 92 timed out at 180 s
  with no output. Logs contain request timeouts, WebSocket/TLS disconnects, and
  MCP initialization failures. This is an incomplete provider-integrity batch,
  not a semantic result.
- Incomplete v25 diagnostic:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v25-qualified-full/`
  attempted 97/204: 67 outputs and 30 provider timeouts.
- Complete v26 diagnostic on the pre-repair corpus:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v26-qualified-full/`
  completed 204/204 processes and Schemas but passed Host/target checks 203/204.
  The sole rejection paired directly supplied Chinese `杭州` with an invalid
  synthetic GI binding `Hangzhou`; the Planner emitted the source-faithful value,
  so the earliest wrong boundary was corpus input rather than Planner.
- Focused current-corpus proof:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v27-focused-zh-location-binding/`
  passed 1/1 process, Schema, Host, and hidden target-region checks after the
  binding was corrected to `杭州`.
- Incomplete v28 rerun:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v28-qualified-full/`
  attempted 67/204: 59 outputs and 8 provider timeouts.
- Pre-change current-corpus mechanical proof:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v29-qualified-full/`
  passed 204/204 process, Schema, Host, and hidden target-region checks with
  source/harness stable and zero timeout. Breakdown: English 102/102, Chinese
  102/102; canonical primary 72/72, canonical re-entry 80/80, streaming advance
  52/52. Corrected post-hoc review v3 completed 51/51 contrast sets and reported
  199 pass, 2 partial, and 3 fail. Manual review identified one stable prompt
  gap: supportive speech could invent unprovided effort/history.
- Focused current prompt proof:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v32-focused-supportive-grounding/`
  passed 1/1 process, Schema, Host, hidden target-region, and manual semantic
  checks. The target-blind response was supportive without inventing prior
  effort, familiarity, circumstance, or likely success.
- Final current prompt proof:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v33-qualified-full/`
  passed 204/204 process, Schema, Host, and hidden target-region checks with zero
  timeout and no disallowed semantic repair. Breakdown: English 102/102, Chinese
  102/102; canonical primary 72/72, canonical re-entry 80/80, streaming advance
  52/52.
- V33 post-hoc semantic review:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v33-qualified-full/semantic-review-codex-v1/`
  completed 51/51 contrast sets with 201 pass, 1 partial, and 2 fail. Root
  adjudication retained all three findings as model inference: repeated internal
  escalation rationale (non-hard), a user-facing exact date reduced to
  unanchored `that morning` (hard), and Planner wording that claimed it would
  `authorize` a blink despite Runtime owning authorization (hard). Each governing
  rule is already explicit, so no additional Prompt/Schema/DTO/Host repair is
  recommended.
- Current production-files digest:
  `c751adc530dd06241d7b86ec857e465f0aada1911875b01982c21bcc5057279f`;
  `agent/app/planner_prompt.py` digest:
  `14aa76efe559674234d91512b61e604f49e2e64aa5b985e328fe46a6b1b13d1f`.
- Candidate generation and review used fixed Codex `gpt-5.6-sol`. No local or
  deployed Qwen/Ollama/vLLM model was invoked, evaluated, tuned, or used as a
  proxy.

Do not promote v12/v14/v16/v23/v24/v25/v28/v31. V17, v19, and v26 exposed
corpus defects. V21 and v29 are complete diagnostic predecessors. V31 was not
run: prompt rendering exposed that the first edit reached only one Fast branch,
and the projection was corrected before candidate inference.

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

Fast and Deep candidate/review calls use fixed `gpt-5.6-sol`. Their separate
post-hoc reviews are same-model and non-independent. Every scenario remains
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

## Candidate-model boundary

This work fixes Codex `gpt-5.6-sol` as the candidate Planner and optimizes only
the surrounding semantic transaction. Model comparison, weight tuning, local
Qwen/Ollama/vLLM inference, and local-model proxy evaluation are outside the
authorized scope. Historical serving/model notes remain context only.

Do not begin SFT. The legitimate next sequence is:

1. independently review Fast v33 and Deep v15 and correct any scenario/oracle
   defects;
2. preserve Codex as the candidate for any continued Planner qualification;
3. cluster retained failures by earliest boundary and change only an evidenced
   Prompt/context/Schema/DTO/Host/corpus owner;
4. retain already-contracted model-inference failures without keyword repair,
   semantic Host rewriting, same-stage retry, or a second model authority.

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

Then obtain independent semantic review of Fast v33 and Deep v15. If another
fixed-Codex Planner cohort is justified, use a new immutable output directory.
Never resume or patch an old batch, change source between cases, average a hard
failure into a pass, invoke a local model as proxy, or approve training data from
same-model review.

## Claim boundary

This handoff records source correction, Deep same-model offline qualification,
the corpus-binding correction, the supportive-speech Fast prompt repair, and
204/204 current-corpus Fast mechanical qualification with fixed Codex. It does
not establish independent semantics, statistical reliability, SFT/QLoRA data,
deployed/local-model behavior, live voice, simulator, GPU coexistence, target
hardware, physical safety, release readiness, or customer-visible behavior.
