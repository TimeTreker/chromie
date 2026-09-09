# Chromie Development Checkpoint

## Current continuation — SGLang/Gemma deployed; behavior contracts remain open

Active Issue #35; pre-delivery base `67d2b2f867064d59c21c075a8ad0108abc3250da` on `main`.
Expected resume revision: the latest delivery commit containing this checkpoint and handoff.
RTX 5090 auto-detection now selects shared Google Gemma4-12B online FP8 on SGLang,
served as `chromie-gemma4-12b`: 65536 context/shared cache tokens, two request slots,
priority preemption, 0.125 sliding/full cache ratio, and Host speech leases.
ASR SenseVoice int8 and TTS CosyVoice3 0.5B remain specialized. Laptop unchanged.
Normal launcher startup passed, including unplayed zh/en/mixed TTS warmups. All four
services remain healthy; no host Orchestrator/microphone or physical effects were run.

Build owner `llm/sglang/Dockerfile` pins the upstream image and repairs the reproduced
missing `lm_head_is_tied` constructor field. `docker-compose.sglang.yml` overrides the
existing `chromie-llm` owner; the obsolete Qwen validation overlay was removed. SGLang
rejects colons in served aliases, so the profile uses the new alias for the same weights.
Provider-aware startup, health, diagnostics and provenance validation are implemented.
No prompt/Schema/semantic-authority changes. Inventory remains 381 environment keys.

Evidence root `.chromie/acceptance/sglang-gemma12b-migration-20260909/`.
Read `migration-report.md`, then `behavior-review.json` and `reviewed-cases/`.
The real 23,919,549,408-byte checkpoint SHA256 was verified (`model-verified.json`).
Real weights occupy 13.68 GiB; KV allocation is 3.50 GiB. No dummy-weight timing claim.
Provider protocol passed. Saturated two-slot preemption passed 3/3 (foreground first
output 74.69–77.90 ms). Speech pause/resume/revocation/recovery passed 3/3 with generated,
unplayed audio. Actual GI median was 4.35 s; short canaries are not full-workflow latency.

The immutable 51-case preview completed: four mechanical passes, zero fully qualified
transactions. Terminal buckets: 37 GA Schema/DTO, seven Fast contract, one GI duration,
two preview-reflex limitations, four mechanical passes rejected by review. Nod2/blink1
planned correct actions but GA lost count bindings; B. merely echoed; capability inventory
was not answered. No Fast input-budget failures. Earlier shared-Gemma 0/51 was Ollama Q4,
not SGLang; FP8/64K versus Q4/32K is not a controlled backend-only comparison.
All 49 raw GI results passed Schema; all 96 raw GA results violated submitted Schema.
Offline proof: pinned XGrammar permits the exact invalid GA output through unsupported
multi-option allOf; installed LLGuidance rejects contains constraints. These are retained
integration gaps, not proof of intrinsic Gemma incapacity. Host binding conservation after
GA repair also remains open. Preserve SGLang selection; do not silently weaken contracts.

Canonical gate passed 2303 tests/268 subtests, 140 benchmark and 20 legacy tests; Level A
45/45. Later final logs bind diagnostic/documentation consistency checks separately.
Runtime identity: `runtime-identity.json`; complete raw calls: `raw-calls.jsonl` (194).
Exactly one post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_141505.tar.gz`.
Owner authorized commit/push of this migration, followed by GA root-cause repair.
Physical voice and default target closure remain open.

## Revision and retained baseline

Active Issue #35, `main` at `67d2b2f867064d59c21c075a8ad0108abc3250da`.
This delivery contains the owner-selected shared Gemma4-12B reasoning profile;
The Goal-driven single-authority architecture remains: GI owns WHAT, GA continuity,
Planner HOW, and Host/runtime effects. No prompt or Schema
change is part of this migration. Laptop configuration remains unchanged.

Before migration, shared Gemma Q4 on **Ollama** completed all 51 preview cases with zero
passes: 30 GI overlaps, four duplicate refs, five duration provenance failures, eight
Fast request-budget failures, two invalid Fast plans and two preview-only limitations.
All 49 completed GI outputs passed JSON Schema; that is not semantic correctness.
Evidence: `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/comparison-report.md`,
`shared-gemma-review.json`, and `reviewed-cases/` retain inputs and raw calls.
One post-cohort bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260909_121448.tar.gz`.

Earlier SGLang Qwen versus maintained Ollama was a different-model comparison, not
matched Gemma evidence. Three synthetic trials showed GI median first output 37 ms
versus 19403 ms; model/precision/topology confound backend causality. Its only mechanical
preview pass was rejected: unresolved GI meaning and lost GA bindings reached executable
Fast work (head-shake case `c70cf61a`). Preview prevented actual dispatch.
Evidence: `.chromie/acceptance/sglang-switch-rtx5090-20260909/`, including
`comparison-review.json`, `test-utterances-and-results.md`, identities and trial summaries.
Neither preview supplies physical microphone, speaker or robot evidence.

## Preserved engineering work and open boundaries

HEAD already contains the GI binding-schema ordering repair, version-2 24-case frozen
primary-screen corpus and strict raw-output/termination retention. The 1496-reference
GI audit passed. Prior laptop comparison and module I/O details remain in
[HANDOFF.md](HANDOFF.md) and [accelerator evidence](docs/ACCELERATOR_LATENCY_EVIDENCE.md).
Historical instructions to restore Ollama are superseded by the owner's SGLang selection.

The former BF16 allocation failure is addressed by the current online-FP8 deployment
configuration, verified with the real-weight checks above. A single matched norm
tensor did not establish full Ollama/Hugging Face weight equivalence; current FP8 versus
previous Q4 timings must not be presented as a controlled backend-only benchmark.

GI conservation, unresolved-meaning commitment, GA binding preservation and Planner
contract failures remain separate semantic work. Current-revision physical voice proof
and default target-evidence closure remain open. Do not repair semantics with host
rewriting, a second judging model call, or reinterpret validation errors as success.

## Resume checks

The download and deployment are complete; no download/startup pipeline remains active.
Next repair the reproduced GA dynamic-Schema/Host conservation boundary, including the
single mechanical-repair result, before interpreting downstream passes as qualified.
Keep Gemma and SGLang fixed, prove rejection of retained invalid outputs, then rerun the
focused and full immutable cohort. Do not add semantic rewriting or another model judge.
Retain actual voice proof separately; the current evidence is headless text/provider work.

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
git diff --check
```
