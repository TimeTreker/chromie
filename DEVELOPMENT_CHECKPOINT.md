# Chromie Development Checkpoint

Status: vLLM transport is qualified on RTX 4090 Laptop; production promotion is blocked by model semantics or authority compatibility
Updated: 2026-08-30
Pre-delivery baseline: `main` at `f5a49c6b0a48358566805a73dc58e311958143d2`
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

## Current worktree

- The stale scenario fixtures now declare explicit communicative `delivery_phase` values;
  the stale prompt-literal test protects the live WHAT contract instead of old wording.
- The new delivery-handoff skill is indexed and owned; checkpoint length remains within
  the repository documentation budget.
- RTX 4090 Laptop assigns every LLM selector to `qwen3.5:4b`, one resident model, GI
  16K/512, and downstream 32K stage contracts.
- Ollama 0.32.14 logs that `qwen35` does not support parallel requests and starts
  `n_seq_max=1` even with `OLLAMA_NUM_PARALLEL=2`. The profile truthfully declares
  `OLLAMA_NUM_PARALLEL=1`; two provider sequence slots are not available.
- CognitiveRuntime cleanup now gathers a concurrent Goal Association task even when it
  already finished. This contains its exception when Fast Planner fails at the same time
  and prevents `Task exception was never retrieved` without changing semantic authority.
- The current GI prompt now matches its fresh-turn schema, and immutable source provenance
  explicitly identifies user -> Chromie. Short fresh turns with no continuity context close
  location spelling to exact source surfaces in the primary schema; continuity turns retain
  context plus fail-closed Host validation. The Deep mechanical constraint now targets the
  model-facing `binding_items` field rather than the removed legacy wire name.
- `scripts/qualify_vllm_provider.py` is a no-deadline qualification probe for identity,
  strict JSON, SSE streaming, two-sequence overlap, cancellation isolation, GPU/TTS
  contention, and the current primary GI contract. It removes only vLLM-unsupported
  `uniqueItems` decoder hints and retains canonical Host revalidation.
- A no-HTTP-deadline Ollama follow-up screened four cached recommended controls plus
  `gpt-oss:20b`. GPT-OSS fit only with TTS stopped, cannot disable its reasoning trace,
  and reached 3/5 only in a non-production `think: low` diagnostic; no model was promoted.
- The current GI prompt/schema now gives `unresolved[]` and the easily-confused binding
  dimensions explicit decoder-visible contracts, and runs decomposition/binding coverage
  as the final preflight. This keeps one primary semantic call and adds no Host classifier.
  Production Qwen3.5-4B reached 3/5 once but a fresh same-source rerun scored 2/5;
  weather temporal scope and compound duration/atomicity remain unstable hard failures.
  A typed-array wire prototype was discarded after manual and holdout review.

## Root-cause workflow

| Boundary | Actual current-source episode | Expected | Judgment |
|---|---|---|---|
| Gateway/GI | Admitted text reached one Qwen GI call; 18/48 timed out, 16/48 returned mechanically invalid provenance/authority/structure, 14/48 were accepted low-confidence outputs | One valid complete Responsibility result or typed fail-closed outcome | Model/provider blocker; validators correct |
| GI fan-out | Each accepted result started GA and Fast concurrently | Both authorities make progress under their stage budgets | Architecture correct; provider has only one sequence slot |
| Ollama/Qwen | One request ran while the other queued; Fast timed out in all 14 accepted-GI cases | Concurrent GA/Fast inference | Resource-profile blocker |
| Fast transport | Current Agent emitted a typed `fast_planner_stream:timeout` failure | Typed pre/post-commit failure | Correct after rebuild |
| Runtime cleanup | A GA task that failed just before Fast was done and therefore was not canceled or gathered | Every child task is joined on exit | Earliest software defect; fixed |
| Capability/Provider | No plan reached canonical dispatch | No effect after hard failure | Correct fail-closed containment |
| vLLM transport | v0.24.0 served two overlapping sequences, isolated cancellation, strict structured output, and remained healthy | Preserve concurrent/cancel/schema contracts | Qualified in isolated provider evidence |
| Primary GI models | Revised object-wire Qwen3.5-4B observed 3/5 once and 2/5 on the fresh final rerun. A typed-array/source-closed prototype gave Ministral-3-14B mechanical 5/5, but manual review found false temporal typing; focused reruns duplicated duration and an unseen holdout was 6/8 mechanical, about 4/8 after manual review. Ministral-8B 1/5, Qwen3.5-9B 3/5, Gemma4-12B 3/5, and Gemma4-26B 3/5 on that experimental wire | Stable 5/5 plus manual review and current non-thinking authority contract before workflow/profile promotion | Model-facing array experiment discarded; no screened model is semantically qualified |

Initiating condition: all roles share one Qwen3.5 runner. Root model/resource causes are
GI contract weakness and Ollama's one sequence slot. The downstream user-visible symptom
is bounded failure speech with no Work. The separate software cause of the asyncio warning
was cleanup joining only non-terminal tasks; gathering every terminal state restores task
ownership without changing any model decision.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Final canonical local gate | repository/static/docs gates passed; 122 benchmark cases; 2,026 main tests; 20 legacy Agent tests | Automated source evidence |
| Focused changed runtime file | 67/67 passed | Cleanup/concurrency regression only |
| Level A composable + multi-Goal | 15/15 passed | Deterministic Level A only |
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

1. Preserve the green canonical local gate; the current run passed all required checks.
2. Do not rerun or append to the retained current-source cohort and do not collect another
   bundle for it.
3. Treat all-Qwen target qualification as blocked, not passed. Do not weaken validators,
   add a semantic repair/reviewer, or inflate timeouts around a single provider slot.
4. Do not promote a production provider yet. The revised prompt reached 3/5 once but the
   fresh final Qwen3.5-4B run returned to 2/5; the same weather temporal-scope and compound
   duration/atomicity classes still fail across larger models. The next semantic
   change must improve primary-result binding coverage generally; do not add phrase rules,
   a reviewer/repair call, or reasoning-only authority without explicit owner authorization.
5. Retain `qwen3.5:4b` for all deployed roles until a model passes the primary screen and
   the complete current workflow. After a material deployment/model change, rebuild
   `chromie-agent`, verify deployed
   source hashes, capture a fresh identity, then run one complete directory-discovered
   cohort and collect exactly one post-cohort bundle.

## Claim boundary

This remains development-only. Local tests and C-preview evidence do not qualify audible
voice, microphone, simulator execution, target robot behavior, or release readiness.
