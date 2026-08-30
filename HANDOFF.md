# Chromie Latest Handoff

Audience: a coding agent or operator resuming current semantic-authority and target-evidence closure.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; source, tests, retained evidence, and the checkpoint win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Pre-delivery branch/base: `main` at `f5a49c6b0a48358566805a73dc58e311958143d2`
- Expected resume revision: latest `origin/main` commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Delivery scope: all project changes listed below are committed together; retained
  evidence under ignored `.chromie/` paths remains local operational evidence
- Active delivery line: canonical local gate, current-revision live proof, then default
  target-evidence closure; do not add unrelated features or architecture

## Current architecture

```text
Gateway -> GI WHAT/Responsibilities
              ├── Fast Planner stream -> immutable PresentationCommit -> terminal Plan
              └── Goal Association -> canonical Goal continuity
                         ↓
       canonical validation / confirmation / Capability Runtime
                         ↓
           correlated Evidence -> scoped Planner re-entry
```

One semantic authority owns each result. GI, GA, and Planner primary outputs contain
their complete grounding/coverage evidence. Trusted code validates mechanics and fails
closed. Do not restore semantic reviewers, Host resegmentation, same-owner repair chains,
raw-token TTS, or Work before terminal Plan + GA binding + canonical validation.

## Worktree changes

- Six cognitive-runtime scenario fixtures now set the intended communicative
  `delivery_phase` after that field became authoritative; the old implicit immediate
  default had made existing ordering/confirmation cases stale.
- `tests/test_semantic_task_continuity.py` now asserts the live WHAT-only prompt contract
  instead of an incidental superseded sentence.
- The project delivery-handoff skill is indexed in `docs/README.md` and `CONTRIBUTING.md`;
  the checkpoint was compacted within the repository line budget.
- `env/profiles/rtx4090_laptop.env` assigns all LLM selectors, Agent Skill selection,
  and CosyVoice compact-model identity to `qwen3.5:4b`. `release/model-lock.json`, profile
  tests, `HARDWARE_PROFILES.md`, `docs/CONFIGURATION.md`, and `docs/STATUS.md` match.
- The profile retains one resident Ollama model. `OLLAMA_NUM_PARALLEL=1` is deliberate:
  Ollama 0.32.14 logs `qwen35` parallel requests as unsupported and starts `n_seq_max=1`
  even when configured for two.
- `GoalDrivenRuntimeCoordinator` now always gathers its concurrent Goal Association task
  during fail-closed cleanup, including a task already terminal. The regression verifies
  that simultaneous GA/Fast failure produces no unhandled asyncio task exception.
- The GI primary schema/prompt now agree on omitted fresh-turn Goal relationship fields;
  source provenance identifies the user and Chromie, short context-free location values
  are decoder-closed to exact source surfaces, and the Deep mechanical location constraint
  addresses wire `binding_items`.
- `scripts/qualify_vllm_provider.py` adds retained, no-HTTP-deadline vLLM transport and
  primary-GI qualification without changing the deployed provider or profile.

No environment variable, architecture term, compatibility path, or current document was
added. The only new repository surfaces are the isolated qualification script and its test;
production profile/provider ownership remains unchanged by the vLLM work.

## vLLM qualification on this laptop

The pinned runtime was `vllm/vllm-openai:v0.24.0` at image digest
`sha256:251eba5cc7c12fed0b75da22a9240e582b1c9e39f6fbc064f86781b963bd814f`.
Every provider run used two sequences, prefix caching, explicit non-thinking mode where
supported, no HTTP/WebSocket deadline, and normal explicit cancellation. vLLM rejects
JSON Schema `uniqueItems`; the qualification adapter removed only that decoder hint and
then ran Chromie's canonical Host validator.

| Candidate / pinned revision | Primary GI | Measured text weights / budget | Judgment |
|---|---:|---:|---|
| `RedHatAI/Qwen3.5-4B-quantized.w4a16` / `7a613872...` | 1/5 | 4.48 GiB / 55% | Transport passes; semantics fail |
| `RedHatAI/Qwen3.5-9B-quantized.w4a16` / `a398088c...` | 2/5 | 9.48 GiB / 80% | Best semantics tested, still fails |
| `RedHatAI/gemma-3-12b-it-quantized.w4a16` / `700b3cfd...` | 0/5 | 7.84 GiB / 80% | Compact-JSON server setting fixes whitespace nontermination; semantics fail |
| `Qwen/Qwen3-8B-AWQ` / `4da05a8e...` | 1/5 | 5.71 GiB / 60% | Fits resource envelope; semantics fail |

Qwen3.5-4B provider/TTS evidence retained at
`.chromie/acceptance/model-qualification/vllm-qwen35-4b-w4a16-warm-20260829T2136Z/provider-contract.json`:
two streams really overlapped, cancellation did not kill the survivor, total GPU peaked at
14,953 MiB, and generated-but-unplayed TTS first-audio latency slowed 2.37x (total 1.97x)
under two long decode streams. The schema-aligned model screens are retained at:

```text
.chromie/acceptance/model-qualification/vllm-qwen35-4b-w4a16-gi-harness-fixed-20260829T2200Z
.chromie/acceptance/model-qualification/vllm-qwen35-9b-w4a16-schema-aligned-20260829T2208Z.json
.chromie/acceptance/model-qualification/vllm-gemma3-12b-w4a16-compact-json-20260829T2228Z.json
.chromie/acceptance/model-qualification/vllm-qwen3-8b-awq-20260829T2242Z.json
```

This qualifies the vLLM transport candidate, not a production model, Agent workflow,
audible voice, simulator, target, or physical robot. No provider/profile integration was
made. The temporary vLLM container and failed model caches were removed; `chromie-llm`,
`chromie-tts`, `chromie-asr`, and `chromie-agent` were restored healthy.

## Recommended-model follow-up

The same current-checkout five-case primary-GI screen was run through Ollama 0.32.14
with `httpx` deadlines disabled. TTS was stopped only while measuring isolated GPU
residency, then restored healthy. This is direct provider/GI evidence, not the complete
Agent workflow.

| Candidate / digest | Primary GI | GPU used without TTS | Judgment |
|---|---:|---:|---|
| `ministral-3:14b` / `4760c35a...` | 2/5 | 10,451 MiB | Semantic control; not qualified |
| `ministral-3:8b` / `1922accd...` | 1/5 | 7,515 MiB | Semantic control; not qualified |
| `gemma4:e4b` / `c6eb396d...` | 1/5 | 4,991 MiB | Semantic control; not qualified |
| `gemma4:12b` / `4eb23ef1...` | 2/5 | 8,727 MiB | Semantic control; not qualified |
| `gpt-oss:20b` / `17052f91...` | 0/5 with `think:false`; 3/5 diagnostic with `think:low` | 12,951 MiB | Promising semantics, but reasoning cannot be disabled and TTS has no residency headroom |

Retained evidence:

```text
.chromie/acceptance/model-qualification/ollama-recommended-gi-screen-20260829T231656Z.json
.chromie/acceptance/model-qualification/gpt-oss-20b-low-reasoning-diagnostic-20260829T232100Z.json
```

The non-thinking GPT-OSS requests generated tokens but returned empty `message.content`.
Ollama's current official contract states that GPT-OSS accepts only `low`, `medium`, or
`high` thinking levels and that its trace cannot be fully disabled. The low-reasoning run
therefore bypassed Chromie's non-thinking response guard only for diagnosis; it must not
be treated as qualification or precedent for changing semantic authority. It still
misclassified `今晚` and dropped the explicit 10-second duration.

### Prompt/schema correction and second sweep

The earliest shared semantic boundary was decoder salience, not transport: the primary
schema gave `unresolved[]` no semantic description and weakly contrasted `time`,
`time_scope`, `duration`, `threshold`, `subtype`, `entity`, and `recipient`; the long
prompt stated atomicity but did not execute decomposition/binding coverage as its final
decision order. The correction strengthens those existing descriptions and final
preflight only. It adds no call, classifier, route, compatibility path, or semantic owner.

| Revised-contract candidate | Primary GI | Measured residency | Judgment |
|---|---:|---:|---|
| `qwen3.5:4b` baseline | 2/5 | not remeasured | Filler, temporal scope, compound coverage failed |
| `qwen3.5:4b` best observed | 3/5 | 9,273/16,376 MiB with TTS | Filler fixed in that run; temporal scope and compound duration/atomicity still fail |
| `qwen3.5:4b` fresh final rerun | 2/5 | 9,275/16,376 MiB with TTS | The 3/5 result is not repeatable qualification |
| `qwen3.5:9b` | 2/5 | existing cache | Larger same-family model does not fix shared classes |
| `ministral-3:14b` | 3/5 | existing cache | Same temporal and compound classes fail |
| `gemma4:12b` | 2/5 | existing cache | Additional source-span/duration failures |
| `granite4:tiny-h` | 0/5 | existing cache | Output-mode and provenance failures |
| `qwen3:14b` / `bdbd181c...` | 2/5 | 14,823/16,376 MiB with TTS | Semantics fail and only 1,553 MiB remains; no two-sequence headroom |

Every run used the same current source/schema and `httpx` with no deadline. The compact
prompt experiment regressed to 1/5 and was discarded; the front-loaded duplicate kernel
also failed to improve repeatability and was removed. Retained final evidence:

```text
.chromie/acceptance/model-qualification/ollama-qwen35-4b-semantic-baseline-20260829T235203Z.json
.chromie/acceptance/model-qualification/ollama-qwen35-4b-semantic-final-20260830T001802Z.json
.chromie/acceptance/model-qualification/ollama-qwen3-14b-semantic-preflight-v1-20260830T001400Z.json
.chromie/acceptance/model-qualification/ollama-qwen3.5-4b-object-binding-primary-restored-20260830T020000Z.json
```

### Discarded typed-binding wire experiment

A same-call prototype replaced the model-facing sparse `binding_items` object with a
typed dimension/value array, mechanically lowered unique facts into the unchanged
canonical `bindings` object, and closed short fresh-turn string spellings to exact source
surfaces. It added no semantic call, classifier, or repair. Ministral-3-14B initially
scored 5/5 mechanically, but manual review found an elapsed-duration unit misclassified
as `time_scope`. Decoder-visible uniqueness was not honored by Ollama; focused reruns
emitted duplicate `duration` facts and correctly failed Host validation. An unseen
eight-case holdout scored 6/8 mechanically and only about 4/8 under manual semantic
review because of duplicate duration, missed referent ambiguity, a truncated predicate,
and invented direction facts. Qwen3.5-4B scored 2/5 on the wire; Ministral-8B 1/5,
Qwen3.5-9B 3/5, Gemma4-12B 3/5, and Gemma4-26B 3/5. The wire change was therefore
discarded rather than imposed on production.

Retained evidence includes:

```text
.chromie/acceptance/model-qualification/ollama-ministral-3-14b-typed-binding-primary-current-20260830T010000Z.json
.chromie/acceptance/model-qualification/ollama-ministral-3-14b-typed-binding-primary-current-parallel_gaze_blink-focused-20260830T013000Z.json
.chromie/acceptance/model-qualification/ollama-ministral-3-14b-typed-binding-primary-current-holdout-20260830T013000Z.json
.chromie/acceptance/model-qualification/ollama-qwen3.5-4b-typed-binding-primary-current-20260830T010000Z.json
```

Production remains `qwen3.5:4b`. The failed Qwen3-14B cache was removed after retaining
its full digest, outputs, and resource sample. All services were healthy and the
production model was resident again at handoff.

The larger pasted candidates were screened out before download: Qwen3.8-27B,
Qwen3.5-35B-A3B, Muse-Glimmer-30B, and Gemma-4-26B class weights leave no safe 16 GB
resident budget beside KV cache and approximately 4.7 GB TTS. Ling-3.0-tiny is compact
enough, but its official deployment currently requires a vendor vLLM/SGLang path rather
than the maintained stable runtime; the official Ollama path is an unreleased Apple-MLX
branch. Do not add that runtime fork until the primary prompt/eval contract is frozen.
The failed 13 GB GPT-OSS cache was removed to restore disk headroom; its digest/evidence
are retained and it can be re-pulled explicitly.

## RTX 4090 Laptop facts

- GPU: RTX 4090 Laptop, 16,376 MiB.
- Runtime: Ollama 0.32.14, `qwen3.5:4b` Q4_K_M digest
  `2a654d98e...`, one 32,768-token runner.
- Observed model allocation: about 3.80 GB runner allocation / 4.62 GB process use.
- CosyVoice used about 4.68 GB; the pair fit with about 6.3 GB free.
- Direct probe: sequential two-request wall time 1.961 s; concurrent submission wall time
  1.487 s, with the second response completing after the first. This is queue overlap,
  not two inference sequences.
- Generated runtime fingerprint:
  `e22218e621afabbe51338c944674560cb8ad8c784871fe3e19e891435c520155`.
- Never edit `.env.runtime`; regenerate it through the profile scripts.

## Deployment provenance correction

The first all-Qwen cohort found a stale `chromie-agent` image. Its deployed
`/fast-advance` endpoint returned the older untagged single object, while the checkout
owns the current NDJSON stream. That run is retained at
`.chromie/acceptance/general-ability/qwen35-all-roles-20260829T1323Z/live-text` with one
bundle `/home/chromie/Downloads/chromie_debug_bundle_20260829_213258.tar.gz`; it is
deployment-mismatch diagnostics only.

`chromie-agent` was rebuilt and recreated. Checkout/container SHA-256 values then matched:

```text
agent/app/main.py                 72aa06612ff4c371ee53588a4cecc8c648855062da764ca4e2d92b5599b528ec
agent/app/fast_planner.py         693e1f3e335fecd88baac14adfd0e6f7a088be8c635aac34f494be8f70c517c3
shared/chromie_contracts/plan.py  abd809b1d5bd1360e261cedcd604103495119d1008a09f03847aa44619459371
```

The rebuilt image ID was
`sha256:30b8abf7d1f8fcdd8078f908dfda35b4b72ba92dc2e317feac19d42759686882`.
All four Chromie services were healthy during the current-source cohort.

## Current-source live evidence

The complete must-pass cohort is retained at:

```text
.chromie/acceptance/general-ability/qwen35-all-roles-current-20260829T133621Z/live-text
```

- runtime identity: `2ab46a7cb42053391fe9fc0acbef77bc8d562bc3e9f6fd30c70f7f9becbeee91`
- dirty source-tree digest: `428c51bb87cffe96d42f3f20f324eccfa0ec44a64c3f99e8cfbb7d50d4186c42`
- result: 0/50 must-pass; core 15 and challenge 8 correctly gated off
- evidence level: diagnostic C-preview; headless/preview-only, no body execution
- exactly one post-cohort bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20260829_214253.tar.gz`

Mutually exclusive earliest failure counts covering all 50 cases:

| Earliest boundary | Count |
|---|---:|
| GI provider `ReadTimeout` | 18 |
| GI invalid exact location provenance | 8 |
| GI dropped/rewrote explicit numeric binding | 5 |
| GI independent Responsibility spans overlap | 2 |
| GI invented duration provenance | 1 |
| Typed Fast stream timeout after accepted GI | 14 |
| Preview-only deterministic reflex limitation | 2 |

All 14 retained accepted GI results were low confidence (13 at 0.5, one at 0.75);
10/14 retained one or two unresolved strings. No Capability reached canonical dispatch.
There was no OOM, runner eviction, service crash, emergency, unsafe-idle event, TTS claim,
simulator execution claim, microphone claim, or physical robot claim.

## Concurrent-failure defect workflow

Representative accepted-GI episodes followed this path:

| Module/owner | Authoritative input | Actual output | Expected output | Boundary |
|---|---|---|---|---|
| Gateway + GI | admitted turn and closed token table | accepted low-confidence Responsibilities | complete grounded WHAT or typed rejection | mechanically accepted; semantic quality weak |
| Host fan-out | immutable GI result | started GA and Fast concurrently | concurrent independent authority calls | correct |
| Ollama/Qwen | two requests, one sequence slot | one ran while the other queued; stage deadlines expired | two usable results within budgets | first target blocker |
| Agent Fast stream | provider timeout | typed `FastPlannerStreamFailure` | typed terminal failure | correct after rebuild |
| Host cleanup | terminal Fast failure plus GA child task | canceled/gathered only when GA was still running; a just-finished failing task was not retrieved | own every spawned task through exit | first software defect; fixed |
| Capability Runtime | no canonical Plan | no dispatch | no dispatch | correct containment |

Initiating trigger: all roles share one Qwen runner. Model/resource root causes are GI
contract weakness and the provider's single sequence slot. Downstream symptoms are bounded
failure speech and no Work. A contributing software cause produced only the asyncio warning:
cleanup checked `not task.done()` before both cancel and gather. It now conditionally
cancels but unconditionally gathers. This changes task lifecycle I/O only; it does not
reinterpret GA, select Work, retry semantics, or shift any authority.

## Automated evidence

Final canonical evidence:

```text
python scripts/check_repository_policies.py
passed

./scripts/run_tests.sh
122 benchmark cases; 2,026 main tests; 20 legacy Agent tests; passed

python scripts/check_docs.py
97 Markdown files; passed

python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class composable_action_planning \
  --ability-class multi_goal_daily_life --no-write
15/15 passed, Level A
```

Cleanup-focused evidence:

```text
python -m unittest tests.test_cognitive_runtime_pr7
67/67 passed
```

Do not convert Level A or C-preview evidence into live robot behavior.

## Resume commands

Reproduce the final canonical gates before another delivery claim:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Do not rerun or append to the current-source cohort and do not collect another bundle for
it. The next qualification run requires a material model/runtime/profile change, a rebuilt
current Agent image, deployed-source hash verification, and a fresh runtime identity.

The current all-Qwen choice remains in the profile as requested, but it is not qualified.
Do not hide the blockers with longer deadlines, sequentializing the architecture, weaker
validators, Host semantic repair, or another same-authority model call. The next model
topology change should start by freezing the current five-case screen into a broader
prompt/eval contract, then compare only models that can satisfy the non-thinking primary
authority and coexist with TTS. A reasoning-only model or vendor runtime fork requires an
explicit owner architecture/runtime decision before integration.

Typical safe deployment inspection:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  ./scripts/compose.sh build chromie-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  ./scripts/compose.sh up -d --no-deps --force-recreate chromie-agent
docker compose ps chromie-agent
docker exec chromie-agent sha256sum \
  /app/app/main.py /app/app/fast_planner.py /app/chromie_contracts/plan.py
```

## Claim boundary

This remains development-only. The all-Qwen profile is retained configuration, not a
semantic-quality, latency, audio, simulator, hardware, deployment, or release claim.
