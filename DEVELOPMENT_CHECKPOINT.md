# Chromie Development Checkpoint

Status: GI prompt and 1,496-case corpus are mechanically validated; production model/prompt qualification remains open
Updated: 2026-08-30
Pre-delivery baseline: `main` at `c55ce694f46ade547844c1ebceebea8a0342b2c9`
Expected resume revision: the latest `origin/main` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md), [Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), [Acceptance](docs/ACCEPTANCE.md),
and [Latest Handoff](HANDOFF.md). Source, tests, and retained executable evidence win.

## Active delivery line

Keep the current Goal-driven single-authority path intact:

```text
admitted turn -> GI WHAT/Responsibilities -> concurrent GA + Fast Planner
  -> immutable presentation commit + terminal Plan -> canonical validation
  -> confirmation/Work -> Runtime Evidence -> scoped Planner re-entry
```

- One semantic authority produces its complete primary result. Do not restore semantic
  reviewers, Host resegmentation, or same-owner repair calls.
- GI owns current-turn WHAT; GA owns Goal identity/continuity; Planner owns HOW and exact
  Communicative/Capability Activities.
- Raw model tokens never reach TTS. Goal Work waits for the terminal Planner result,
  GA binding, and canonical validation.
- Keep validation fail-closed and keep stop/cancel/emergency deterministic.

## Current delivery scope

- The production GI system prompt is now a 10,225-character provider-neutral decision
  procedure covering all 25 model-facing binding dimensions, atomic decomposition,
  complete acquire-and-deliver outcomes, cross-clause collection, output modes,
  coordination, uncertainty, source perspective, decoder-safe key order, and minimal
  predicate evidence. It contains no candidate-model or reported-case literals.
- `build_system_prompt()` conditionally projects Goal-continuity and accepted prior-
  assistant-utterance rules only when authoritative bounded Context exposes those schema
  surfaces. Primary, one mechanical DTO repair, and Deep GI use the same projection; no
  model call, semantic reviewer, or authority owner was added.
- A new frozen 15-case `goal_interpreter_primary_v1` manifest plus
  `qualify_goal_interpreter_model_potential.py` separates raw model semantic potential from
  production prompt/schema/Host compatibility and reports six dimensions independently.
- RTX 5090 diagnostic evidence remains model-potential only. Ministral-3-14B retained
  28/28 evaluable decomposition and output-mode passes across two repeats but only 16/28
  binding passes; Granite4.2-8B retained all 15 outcomes/modes but passed 3/15 bindings.
  Neither model, provider, nor runtime profile was promoted.
- The checked-in `goal_interpretation_daily_life` corpus contains 1,496 one-file bilingual
  daily-life scenarios in 374 four-case contrast sets, with whole-set train-candidate,
  validation, and frozen-test splits. It covers all 25 binding dimensions, all ten concrete
  output modes, continuity relationships, 306 context turns, and 102 genuine-unresolved
  cases. It ships no scenario generator.
- Every corpus reference passes its request-specific decoder schema and current Host
  validator. Review fields remain `independent_semantic_review=false` and
  `training_eligible=false`; this is mechanically checked candidate evidence, not model
  inference or training qualification.
- The Host whole-turn echo guard no longer rejects one atomic context-backed elliptical
  clarification such as `Tomorrow afternoon.`. The exception requires one Responsibility,
  `relationship=clarify`, exactly one supplied target Goal, and an unresolved blocking
  `ask_user` information gap. All other whole-turn echoes remain fail-closed.
- Repository profile truth remains unchanged. The current generated local runtime selects
  `rtx5090`, GI `gemma4:12b`, 32,768 context, and 2,048 output tokens; `.env.runtime` was
  inspected but not edited. Retained RTX 4090 all-Qwen evidence remains historical and
  unqualified. No provider integration or deployment was changed.

## Root-cause workflow

| Boundary | Actual current-source episode | Expected | Judgment |
|---|---|---|---|
| Dataset authoring | Assistant authored 1,496 exact inputs, semantic regions, wire references, and adversarial hypotheses | Reusable candidate corpus with explicit review limits | Correct candidate evidence; independent review still open |
| Dynamic schema | All 1,496 references were validated against each request-specific model-facing schema | Closed DTO shape for every retained reference | Correct |
| Host provenance/structure | Before the fix, 34 one-phrase clarification replies failed because their only new binding equaled the whole admitted turn | Context-backed binding must survive without weakening opaque-turn protection | Earliest current software defect; fixed |
| Host echo fix | Allows the whole-turn binding only for one exact clarify target with a blocking unresolved `ask_user` gap | Mechanical exception, no semantic retyping or repair | Correct; 1,496/1,496 Host accepted |
| Model-potential probe | Ministral and Granite preserved much of decomposition/modality but failed binding coverage | Select candidates without conflating raw semantics with production transaction | Diagnostic only; no promotion |
| Production workflow | The new prompt/corpus was not run through a deployed current-revision GI/GA/Planner workflow | Exact prompt + schema + decoder + model + profile qualification | Unproven and still blocked |

Initiating trigger for the 34-case defect was a valid short clarification answer whose only
new surface fact occupied the complete turn. The root cause was the Host echo guard treating
all non-speech whole-turn bindings as envelope copies without consulting already-validated
Goal relationship and pending-gap shape. The fix changes only that validator decision;
downstream GA/Planner/Runtime were not invoked in the reproduced failure and no authority
moved. Separately, weak binding accuracy remains a model/prompt/decoder qualification issue,
not evidence for weakening Host validation.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Final canonical local gate | repository/static/docs gates passed; 122 benchmark cases; 2,041 main tests; 20 legacy Agent tests | Automated source evidence on dirty pre-delivery tree |
| Daily-life GI corpus validator | 1,496 schema passes; 1,496 Host passes; zero known Host gaps | Reference/corpus mechanics only; not live model inference |
| Focused GI prompt/dataset tests | 67 passed plus 10 subtests | Prompt/schema/validator/corpus regression only |
| Level A robust intent + Planner/Goal semantics | 12/12 passed | Deterministic Level A only |
| Assistant-reference prompt audit | 16/16 schema, Host, and six-dimension passes | One strong assistant reference; no external model/provider call |
| RTX 5090 model-potential probe | Ministral-3-14B 8/30 whole trials over two repeats; Granite4.2-8B 1/15; dimension details retained | Simplified wire, dirty checkout, isolated model evidence only |
| RTX profile/provider probe | RTX 4090 Laptop 16,376 MiB; one Qwen3.5 32K runner; CosyVoice and Qwen fit; configured parallel 2 still created `n_seq_max=1` | Resource evidence, not semantics |
| Current-source live-text must-pass cohort | 0/50; core 15 and challenge 8 gated off | Diagnostic C-preview; no execution/audio/hardware claim |
| vLLM 0.24.0 / Qwen3.5-4B provider contract | strict JSON, SSE, real two-sequence overlap, cancellation isolation passed; peak 14,953 MiB with TTS | TTS first-audio slowed 2.37x under two long decode streams; no playback claim |
| Isolated primary-GI model screen | Qwen3.5-4B 1/5, Qwen3.5-9B 2/5, Gemma-3-12B 0/5, Qwen3-8B 1/5 | Provider transport passed; no candidate is semantically qualified |
| Recommended Ollama follow-up | Ministral-3-14B 2/5, Ministral-3-8B 1/5, Gemma4-e4B 1/5, Gemma4-12B 2/5; GPT-OSS `think:false` 0/5 empty content, `think:low` diagnostic 3/5 | No HTTP deadline; isolated GI only. GPT-OSS used 12,951/16,376 MiB without TTS and cannot disable reasoning |
| Revised prompt/model screen | Object wire: Qwen3.5-4B best 3/5, fresh final 2/5 at 9,275 MiB with TTS. Discarded typed wire: Ministral-14B 5/5 mechanical but manual failure and 6/8 unseen holdout mechanical/about 4/8 manual; all other cached candidates <=3/5 | No HTTP deadline; direct GI only. No candidate passed manual review and no model/profile was promoted |

Current cohort:

- evidence: `.chromie/acceptance/general-ability/qwen35-all-roles-current-20260829T133621Z/live-text`
- identity: `2ab46a7cb42053391fe9fc0acbef77bc8d562bc3e9f6fd30c70f7f9becbeee91`
- source tree: `428c51bb87cffe96d42f3f20f324eccfa0ec44a64c3f99e8cfbb7d50d4186c42`
- one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260829_214253.tar.gz`
- exclusive failures: 18 GI read timeouts; 8 invalid location provenance; 5 numeric
  binding loss/rewrite; 2 overlapping source spans; 1 invented duration; 14 typed Fast
  stream timeouts after accepted GI; 2 preview-only reflex limitations.
- all 14 accepted GI outputs were low confidence; 10 retained unresolved meaning.
- no Capability was dispatched; no simulator/audio/physical behavior was qualified.

The earlier `.chromie/acceptance/general-ability/qwen35-all-roles-20260829T1323Z/live-text`
cohort exposed a stale Agent image. Its pre-stream `/fast-advance` payload did not match
the checkout, so it is deployment-mismatch diagnostics only. The rebuilt Agent image
matches the current checkout file hashes and current failures use typed stream frames.

## Exact resume point

1. Preserve the green canonical local gate and the 1,496/1,496 schema/Host corpus result.
2. Keep every corpus split non-training: independent semantic review and frozen execution
   remain required before promoting any scenario to training evidence.
3. Run a blind exact-production-prompt evaluation over the corpus only through a callable,
   revision-bound model endpoint. Store raw output before grading and keep model, prompt,
   schema, decoder, parameters, repeats, latency, and failure attribution separate. The
   proposed Codex-strength 1,496-case self-evaluation was discussed but not run.
4. Treat Ministral/Granite model-potential results as candidate-selection diagnostics only.
   Do not attribute a combined transaction failure solely to model or prompt, and do not
   promote a production provider/profile until the exact production screen and complete
   workflow pass.
5. Preserve the narrow clarification exception and its negative regressions. Do not expand
   it into substring semantics, phrase rules, Host resegmentation, or a semantic repair call.
6. Do not rerun or append to the retained all-Qwen current-source cohort. After a material
   deployment/model change, rebuild `chromie-agent`, verify source hashes, capture a fresh
   identity, run one complete directory-discovered cohort, and retain exactly one bundle.

## Claim boundary

This remains development-only. Local tests and C-preview evidence do not qualify audible
voice, microphone, simulator execution, target robot behavior, or release readiness.
