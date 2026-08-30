# Chromie Development Checkpoint

Status: selected fixed-v4 GI prompt passes the complete 1,496-case offline diagnostic; exact production provider/model qualification remains open
Updated: 2026-08-31
Pre-delivery baseline: `main` at `ae250dd8ae40a01f58eb415b3f6e84e7bceed553`
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

- The selected fixed-v4 GI system prompt and request-specific schema descriptions now agree
  that directly supplied Arabic-digit duration, speed, distance, threshold, quantity, and
  magnitude values are JSON numbers when no conversion is required. The prior prompt/schema
  contradiction was the earliest shared boundary behind the largest residual cluster.
- Existing role and mode owners are clearer without adding terms or calls: `recipient` is
  the actual receiver of transferred/communicated content, a named third party asked a
  supplied question is `speech` with `addressee`, a question Chromie must answer from unknown
  truth is `information`, and ordinary breathing remains `body_action` unless an audible
  nonverbal sound is explicitly requested.
- A separate circumstance, correction, replacement, or binding-only clause may provide a
  final binding without automatically widening the positive predicate's source evidence.
  An anaphoric continuation that only adds duration/extent remains one Responsibility.
- Dynamic schema descriptions carry the same numeric, role, output-mode, proposition,
  preference, subtype, and evidence-span distinctions. No Host semantic resegmentation,
  phrase rule, compatibility path, runtime flag, provider integration, or semantic owner was
  added. GI still authors one complete primary result; the retained post-hoc evaluator never
  participates in production inference or repair.
- The complete 1,496-case directory-discovered corpus was run on one fixed-v4 source/prompt
  identity using isolated `gpt-5.6-sol`/high Codex calls. All 1,496 calls completed; generated
  schema and current production Host validation passed 1,496/1,496; mechanical reference
  equality was 789/1,496 versus the 461-case baseline.
- A single same-model post-hoc semantic self-audit judged 1,355/1,496 v4 candidates valid,
  141 invalid, and recommended no further prompt change. It judged only 1,078 assistant
  references valid and produced inconsistent count/schema judgments, so it is diagnostic,
  non-independent, and ineligible for training or production promotion.
- A broader fixed-v5 wording experiment completed the same full run but regressed to 761
  mechanical and 1,338 self-adjudicated semantic passes. It was rejected; the prompt and
  implementation/test patch were restored exactly to v4 before final gates.
- `docs/STATUS.md` now records this evidence and its limits. Repository runtime/profile truth
  is otherwise unchanged; no model, provider, profile, service, deployment, audio, simulator,
  or robot behavior was promoted.

## Root-cause workflow

| Boundary | Actual fixed-v4 episode | Expected | Judgment |
|---|---|---|---|
| Target-blind prepare | Parsed scenario identity/input/context and retained request packets without `target`, `reference_wire_output`, or `semantic_expectations` markers | Inference cannot see labels | Correct; 0 marker files |
| GI payload builder | Exact fixed-v4 system/user bodies plus each request-specific schema | One complete WHAT contract per case | Correct; prompt SHA retained |
| Codex transport | Wrapped both production message bodies and schema in one read-only Codex envelope; 8 independent workers | One raw result per case | 1,496/1,496 completed; role/strict-decoder fidelity remains unproven |
| Raw evidence store | Retained raw JSON and stdout/stderr before grading | Immutable evidence before attribution | Correct; all manifest/state/request/raw hashes matched |
| Schema/Host boundary | Validated each raw result with generated schema and production Host mechanics | Hard failures cannot be averaged | 1,496/1,496; no hard failure |
| Mechanical oracle | Compared candidate to assistant-authored references | Narrow difference signal only | 789 exact; reference defects remain common |
| Post-hoc self-audit | Examined frozen candidates after inference; never repaired or re-called GI | Diagnostic attribution only | 1,355 valid; non-independent and internally inconsistent |
| Version selection | Compared complete v4 and v5 cohorts | Reject net regression | v4 selected; v5 reverted |

The initiating condition was the full bilingual corpus exposing repeated binding/type and
evidence-span disagreements. The confirmed root cause was a contradiction and ambiguity in
the primary model-facing prompt/schema contract; the downstream mechanical oracle amplified
symptoms because many assistant references were also defective. The v4 fix changes only the
primary GI contract presented to the existing semantic authority. Schema/Host validation,
GA, Planner, Capability Runtime, live services, and robot execution were not invoked to
reinterpret or repair these offline cases.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Final canonical local gate | repository/static/docs gates passed; 2,045 main tests; 20 legacy Agent tests | Automated source evidence on dirty pre-delivery tree |
| Daily-life GI corpus validator | 1,496 schema passes; 1,496 Host passes; zero known Host gaps | Reference/corpus mechanics only; not live model inference |
| Focused GI prompt tests | 68 passed plus 10 subtests | Prompt/schema regression only |
| Level A robust intent + Planner/Goal semantics | 12/12 passed; `.chromie/acceptance/general-ability/20260830T161609Z-level-a/` | Deterministic Level A only |
| Fixed-v4 target-blind Codex cohort | 1,496/1,496 calls; 789 mechanical; 1,496 schema/Host; 1,355 same-model semantic self-passes | Codex text envelope, not exact production roles/decoder; reviewer non-independent |
| Fixed-v5 rejection cohort | 1,496/1,496 calls; 761 mechanical; 1,338 semantic self-passes; one unstable prompt-gap judgment | Rejected experiment; source restored to v4 |
| Assistant-reference prompt audit | 16/16 schema, Host, and six-dimension passes | One strong assistant reference; no external model/provider call |
| RTX 5090 model-potential probe | Ministral-3-14B 8/30 whole trials over two repeats; Granite4.2-8B 1/15; dimension details retained | Simplified wire, dirty checkout, isolated model evidence only |
| RTX profile/provider probe | RTX 4090 Laptop 16,376 MiB; one Qwen3.5 32K runner; CosyVoice and Qwen fit; configured parallel 2 still created `n_seq_max=1` | Resource evidence, not semantics |
| Current-source live-text must-pass cohort | 0/50; core 15 and challenge 8 gated off | Diagnostic C-preview; no execution/audio/hardware claim |
| vLLM 0.24.0 / Qwen3.5-4B provider contract | strict JSON, SSE, real two-sequence overlap, cancellation isolation passed; peak 14,953 MiB with TTS | TTS first-audio slowed 2.37x under two long decode streams; no playback claim |
| Isolated primary-GI model screen | Qwen3.5-4B 1/5, Qwen3.5-9B 2/5, Gemma-3-12B 0/5, Qwen3-8B 1/5 | Provider transport passed; no candidate is semantically qualified |
| Recommended Ollama follow-up | Ministral-3-14B 2/5, Ministral-3-8B 1/5, Gemma4-e4B 1/5, Gemma4-12B 2/5; GPT-OSS `think:false` 0/5 empty content, `think:low` diagnostic 3/5 | No HTTP deadline; isolated GI only. GPT-OSS used 12,951/16,376 MiB without TTS and cannot disable reasoning |
| Revised prompt/model screen | Object wire: Qwen3.5-4B best 3/5, fresh final 2/5 at 9,275 MiB with TTS. Discarded typed wire: Ministral-14B 5/5 mechanical but manual failure and 6/8 unseen holdout mechanical/about 4/8 manual; all other cached candidates <=3/5 | No HTTP deadline; direct GI only. No candidate passed manual review and no model/profile was promoted |

Retained selected/rejected offline evidence (local ignored artifacts):

- selected: `.chromie/acceptance/model-qualification/codex-gi-reference-full-fixed-v4/`
- selected report: `.chromie/acceptance/model-qualification/codex-gi-reference-full-fixed-v4/ANALYSIS.zh-CN.md`
- rejected experiment: `.chromie/acceptance/model-qualification/codex-gi-reference-full-fixed-v5/`
- v4 qualification identity: `chromie.codex_gi_reference_full.fixed_v4`
- model/effort: `gpt-5.6-sol`, `high`; production options are metadata only
- prompt SHA-256: `2d0ce9814d3b8e882b925800225b152aaf0f0f3c6b5f838a5d9e7196eebb62ad`
- pre-status-update v4 worktree diff SHA-256:
  `bf365f0a2e251f548a1953ab1f2e4abc95a9606004119b14e76821a59543f3a9`

Historical deployed current-source cohort remains unchanged:

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

1. Preserve the green canonical local gate, the selected fixed-v4 prompt identity, and the
   1,496/1,496 schema/Host corpus result. Do not reintroduce rejected v5 wording merely to
   match a stochastic self-review judgment.
2. Keep every corpus split non-training: independent semantic review and frozen execution
   remain required before promoting any scenario to training evidence.
3. The next qualification step is an exact deployed provider/model/strict-decoder run bound
   to a committed revision and runtime identity. Keep prompt, schema, decoder, model,
   parameters, latency, and failure attribution separate; the Codex envelope cannot close
   that claim.
4. Seek independent semantic review before changing training eligibility or treating 1,355
   as truth. Correct evaluator/reference defects in their owning evidence, not by tuning the
   production prompt to a reviewer.
5. Preserve the narrow clarification exception and its negative regressions. Do not expand
   it into substring semantics, phrase rules, Host resegmentation, or a semantic repair call.
6. Do not rerun or append to the retained all-Qwen current-source cohort. After a material
   deployment/model change, rebuild `chromie-agent`, verify source hashes, capture a fresh
   identity, run one complete directory-discovered cohort, and retain exactly one bundle.

## Claim boundary

This remains development-only. Local tests and C-preview evidence do not qualify audible
voice, microphone, simulator execution, target robot behavior, or release readiness.
