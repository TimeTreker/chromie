# Chromie Development Checkpoint

Status: Issue #35 Goal-driven Fast/Deep Planner single-authority correction,
coverage design, and Deep same-model offline qualification are complete in the
current delivery tree. Fast's final prompt repair passes its focused regression,
but a full current-source rerun is blocked by remote provider integrity.
Independent semantic review and deployed `qwen3.5:4b` qualification remain open;
no retained Planner scenario is approved for SFT/QLoRA training.

Updated: 2026-09-04

Delivery branch: `main`

Pre-delivery base: `origin/main` at
`bc278c9f71239a173f098fa9d6599f03f2b4fdd5`.

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
  `b5da6e022886effd3b9618384e48914775e7a742b19cbe584f9c1826227eb669`.
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
| Fast v24 full rerun | 115/204 attempted: 23 outputs and 92 provider timeouts at 180 s before the run was stopped | Incomplete provider-integrity failure; no semantic verdict |
| Deep v15 | 40/40 process, Schema, Host, and hidden target-region passes; 20 English/20 Chinese, 24 primary/16 re-entry | Same-model offline Codex surrogate only |
| Deep v15 post-hoc review | 40/40 semantic passes | Same-model and non-independent |
| Relevant General Ability Level A | 46/46 across eight Planner-related ability classes | Source-level Level A only |
| Repository policy / ownership / docs | 15 rule families, 0 exceptions; ownership pass; 102 Markdown files pass | Static/source consistency only |
| Canonical local gate | Final result recorded in `HANDOFF.md` | Local automated evidence only |

- Fast v21 predecessor: `.chromie/benchmarks/fast-planner/20260904T-fast-v21-qualified-full/`.
- Fast v22 current focused proof: `.chromie/benchmarks/fast-planner/20260904T-fast-v22-focused-unspecified-plan/`.
- Current Fast production-files SHA-256: `0c07329afc04855a609dceac6452e95191759d26e5113c06c0244d8362c36398`;
  tracked-diff SHA-256: `4daf8377d1c1ccf631d0278ca8b844a7fa43edfeadd81119807cbbaf096b4c26`.
- Incomplete Fast v24: `.chromie/benchmarks/fast-planner/20260904T-fast-v24-qualified-full/`.
- Deep v15: `.chromie/benchmarks/deep-planner/20260904T-deep-v15-qualified-full/`;
  production-files SHA-256: `482b22aea8cb3eadf4bb2fbb25e6dda2f219d061e57513850286c18d6a34d495`.

Never promote v12/v14/v16/v23/v24. V17/v19 exposed corpus defects; v21 is a
complete diagnostic predecessor, not proof for the final prompt and corpus.

## Model, serving, and training decision

The RTX 4090 Laptop vLLM probe established strict JSON, SSE streaming, two-short-
sequence overlap, cancellation isolation, and post-cancel health. It did not
establish semantic fitness: the unchanged five-case screen scored Qwen3.5-4B
1/5 and Qwen3.5-9B 2/5, and two long streams slowed TTS first audio by 2.37×.
Ollama `qwen3.5:4b` also exposes only one sequence slot in the current profile.

Therefore vLLM remains a serving candidate, not a semantic remedy. QLoRA/SFT is
not yet authorized by evidence: all retained cases are explicitly training-
ineligible and lack independent semantic review. The next training decision
requires independently reviewed examples plus failures reproduced on the exact
deployed target model/transport; otherwise the label set can teach corpus or
reviewer defects.

## Resume point

1. When the remote provider is healthy, rerun all 204 Fast cases from scratch in
   one immutable batch on the final prompt/corpus; then obtain independent human
   or separate-model semantic review of Fast 204 and Deep 40.
2. Run the frozen corpora through the exact deployed `qwen3.5:4b` transaction on
   the chosen serving transport. Bind model digest, decoder, runtime profile,
   source revision, and provider concurrency.
3. Cluster target-model failures by earliest shared boundary. Only then decide
   prompt/schema changes versus a reviewed QLoRA dataset and vLLM deployment.
4. Rebuild the current revision and retain the complete live voice cohort plus
   exactly one debug bundle. Physical microphone/speaker and robot proof remain
   supervised evidence gaps.

## Claim boundary

This delivery closes the reproduced watchdog defect, Planner single-authority
source defects, coverage-designed offline corpora, Deep same-model offline
qualification, and the focused Fast prompt defect. Full final-source Fast
qualification remains open because the provider failed during v24. This does not
qualify deployed Qwen/Ollama/vLLM, independent semantic truth, SFT data, live
voice, simulator, target hardware, physical safety, release readiness, or
customer-visible behavior.
