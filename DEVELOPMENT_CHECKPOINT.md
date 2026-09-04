# Chromie Development Checkpoint

Status: Issue #35 Goal-driven Fast/Deep Planner single-authority correction,
coverage design, and fixed-Codex offline qualification are complete through the current Fast corpus. Codex
`gpt-5.6-sol` was the candidate Planner; no local/deployed model was invoked.
After one prompt repair, 204/204 mechanical checks pass; same-model semantic
review reports 201 pass, one partial, and two fail, all remaining findings at
model inference. Independent review and training approval remain open.

Updated: 2026-09-04; delivery branch: `main`

Current evaluated revision: `04dd76fcb2c59f452bcd09cd2d6b5336e8e5b740`
(`origin/main`, 0 ahead/0 behind before the current uncommitted qualification
patch).

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35).

## User-visible defect and actual workflow

The retained bundle is
`.chromie/debug/debug_bundle_20260902_221509/`. For the admitted voice turn
`你好。`, the model-authored semantic work was not the first wrong boundary.

```text
admitted voice turn
  -> Goal Interpretation: one greeting Responsibility (correct)
  -> Goal Association and Fast Planner start concurrently (correct invariant)
       GA completes at 5903.1 ms
       Fast emits a valid presentation commit at 7958.7 ms
  -> outer cognitive-runtime watchdog fires at 9055.1 ms
  -> in-flight workflow is cancelled before terminal Plan/response projection
  -> generic failure speech: 咦，刚才没接上。你再跟我说一遍嘛。
  -> later turns contend for the single qwen35 Ollama slot and GI returns ReadTimeout
```

| Boundary | Owner and material input | Actual output | Expected output | Verdict |
|---|---|---|---|---|
| Voice admission / GI | Gateway + GI; `你好。` | Addressed greeting; one speech Responsibility | Same | Correct |
| GA | Goal Association; same immutable GI result | Valid greeting Goal at 5903.1 ms | Canonical Goal without delaying Fast launch | Correct |
| Fast presentation | Planner; GI result and common catalog, launched with GA | Valid presentation commit at 7958.7 ms | Continue the same invocation to terminal Plan | Correct but interrupted downstream |
| Runtime watchdog | Host cognitive runtime; concurrent GA/Fast workflow | Cancelled the legal workflow at 9055.1 ms | Development watchdog must cover the legal workflow; latency is measured separately | **Earliest wrong boundary** |
| Failure projection | Host failure path | Generic reconnect wording | Preserve a truthful typed failure only after the workflow actually fails | Downstream symptom |
| Subsequent GI calls | One-slot Ollama `qwen3.5:4b` | `ReadTimeout` under retained contention | Bounded provider completion or typed availability failure | Contributing condition |

The fix preserves concurrent GA/Fast launch. It separates development workflow
watchdogs from latency targets: Agent GA/Fast are 60 s, Deep 120 s; Host GA/Fast
are 65 s, Deep 125 s; the outer cognitive runtime is 300 s. These values prevent
the watchdog from relabelling a legal workflow as model failure. They do not turn
slow interaction into a pass; latency remains a separate measured acceptance axis
and can be tightened only from retained deployed evidence.

## Planner authority correction

- Fast and Deep are passes of one Planner HOW authority. Each produces its full
  semantic result in one primary invocation.
- Forbidden Fast/Deep same-tier semantic repair, revision, critic, and
  qualification calls are removed. Deep receives authoritative Goals/context,
  not a Fast candidate or validator feedback.
- Host validation is fail-closed and mechanical. It no longer restores or
  rewrites wording, steps, arguments, timing, Goal coverage, satisfaction, IDs,
  or candidate semantics.
- Deep sees the complete bounded Capability catalog. It does not confuse a
  missing composite provider with missing available component capabilities.
- Fast schema/prompt contracts now require complete information-gap ownership,
  exact catalog/default/confirmation semantics, and one two-frame streaming
  transaction. Deep prompt contracts cover minimum satisfaction, conditional
  read-before-effect composition, retryability evidence strength, and
  cancellation semantics.
- Numeric grounding uses authoritative typed Goal bindings rather than mining
  arbitrary prose or ISO date fragments.

## Coverage-designed corpora

The stale 1,500-case Fast cross-product was replaced because its count did not
establish Planner ability coverage and much of its input no longer matched the
current GA DTO. The maintained corpus is design-traced:

- Fast/shared: 204 cases = 17 Planner capacities × 3 controlled daily-life
  situation families × supported/boundary contrast × English/Chinese.
- Runtime entries: 72 canonical primary, 80 canonical re-entry, 52 streaming
  advance; 102 cases per language; 51 contrast sets.
- Splits: 120 train-candidate, 44 validation, 40 frozen-test. Every case remains
  `training_eligible=false` and `independent_semantic_review=false`.
- Fast scenario-tree SHA-256:
  `2650948b9027071c948bb75481d203104923b4aff2bfc33750288d350679c2d8`.
- Deep: 40 independent extension cases spanning primary and re-entry semantics;
  scenario-tree SHA-256:
  `a0c79e38cf4055b7021a4dcc1cbd0a2caec915872174d41e9c2bf153a4a7406a`.

This matrix demonstrates the named Planner capacities and controlled contrasts;
it is not a claim of exhaustive daily life, statistical model reliability, live
service behavior, or training-data approval.

## Retained qualification evidence

| Evidence | Observed result | Qualification limit |
|---|---|---|
| Fast v21 predecessor | 204/204 process, Schema, Host, and hidden target-region passes; its post-hoc review passed 201/204 and exposed two date-rotted corpus inputs plus one unspecified-plan characterization defect | Same-model offline Codex surrogate on the immediately prior prompt/corpus |
| Fast v22 focused repair | 1/1 process, Schema, Host, and hidden target-region pass for the unspecified-plan defect | Current prompt; focused same-model evidence only |
| Fast v26 diagnostic | 204/204 processes and Schemas; 203 Host/target passes. The sole rejection showed a Chinese source `杭州` paired with invalid synthetic GI binding `Hangzhou` | Complete diagnostic on the pre-repair corpus; earliest wrong boundary was corpus input, not Planner |
| Fast v27 focused corpus repair | 1/1 process, Schema, Host, and hidden target-region pass with source-faithful `杭州` | Focused same-model evidence; Planner source unchanged |
| Fast v29 pre-change full rerun | 204/204 process, Schema, Host, and hidden target-region passes; post-hoc review 199 pass, 2 partial, 3 fail | Corrected corpus and pre-change prompt; diagnostic same-model evidence |
| Fast v32 focused prompt repair | 1/1 process, Schema, Host, target-region, and manual semantic pass; supportive wording no longer invents user history, prior effort, or future success | Fixed `gpt-5.6-sol` candidate; focused same-model evidence |
| Fast v33 current full rerun | 204/204 process, Schema, Host, and hidden target-region passes; 102/102 English, 102/102 Chinese; 72/72 primary, 80/80 re-entry, 52/52 streaming | Current corpus and prompt; fixed Codex candidate; zero timeout and no disallowed semantic repair |
| Fast v33 post-hoc review | 201 pass, 1 partial, 2 fail across 51 contrast sets; all three findings are model inference against existing concise-rationale, exact-date, or Runtime-authorization contracts | Same-model and non-independent; not a full semantic qualification |
| Deep v15 | 40/40 process, Schema, Host, and hidden target-region passes; 20 English/20 Chinese, 24 primary/16 re-entry | Same-model offline Codex surrogate only |
| Deep v15 post-hoc review | 40/40 semantic passes | Same-model and non-independent |
| Relevant General Ability Level A | 46/46 across eight Planner-related ability classes | Source-level Level A only |
| Repository policy / ownership / docs | 15 rule families, 0 exceptions; ownership pass; 102 Markdown files pass | Static/source consistency only |
| Canonical local gate | Final result recorded in `HANDOFF.md` | Local automated evidence only |

- Current Fast production-files SHA-256: `c751adc530dd06241d7b86ec857e465f0aada1911875b01982c21bcc5057279f`;
  prompt SHA-256: `14aa76efe559674234d91512b61e604f49e2e64aa5b985e328fe46a6b1b13d1f`.
- Fast v33 current full proof:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v33-qualified-full/`;
  root adjudication: `semantic-review-codex-v1/root-adjudication.json`.
- Deep v15: `.chromie/benchmarks/deep-planner/20260904T-deep-v15-qualified-full/`;
  production-files SHA-256: `482b22aea8cb3eadf4bb2fbb25e6dda2f219d061e57513850286c18d6a34d495`.

Never promote v12/v14/v16/v23/v24/v25/v28/v31. V17/v19/v26 exposed corpus
defects; v21 and v29 are complete diagnostic predecessors, not proof for the
current prompt. V31 was intentionally not run because prompt rendering exposed
the rule in only one Fast branch before candidate inference.

## Candidate-model and training boundary

The candidate Planner is fixed as Codex `gpt-5.6-sol`; only its surrounding
semantic transaction is in scope. Calls were target-blind, one per case, high
reasoning, without retry. Separate same-model review is non-independent.

Historical Qwen/Ollama/vLLM evidence remains context only and was not invoked,
extended, or used as a proxy in this work. QLoRA/SFT remains unauthorized: all
retained cases are training-ineligible and lack independent semantic review.

## Resume point

1. Obtain independent human or separately authorized model review of Fast v33
   and Deep v15. Do not treat same-model review as semantic truth or training
   approval.
2. Preserve the fixed Codex candidate if Planner qualification continues. For
   each retained failure, change Prompt/context/Schema/DTO/Host/corpus only when
   evidence identifies that surface as the earliest wrong boundary; do not tune,
   compare, or proxy the candidate with a local model.
3. Do not add redundant prompt clauses or semantic Host keyword repair for the
   three v33 findings: their governing contracts are already explicit. Retain
   them as fixed-model inference variance and as independent-review probes.
4. Rebuild the current revision and retain the complete live voice cohort plus
   exactly one debug bundle. Physical microphone/speaker and robot proof remain
   supervised evidence gaps.

## Claim boundary

This working tree closes the reproduced watchdog defect, Planner
single-authority source defects, coverage-designed offline corpora, Deep
same-model offline qualification, the supportive-speech Fast prompt gap, and
current-corpus Fast mechanical qualification with a fixed Codex candidate. It
does not establish independent semantic truth, statistical model reliability,
SFT data, deployed/local-model behavior, live voice, simulator, target hardware,
physical safety, release readiness, or customer-visible behavior.
