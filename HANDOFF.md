# Chromie Latest Handoff

## 2026-09-09 active handoff — RTX 4090 Laptop SGLang resource boundary

This section is the active continuation and supersedes the historical handoff below. Resume from
repository `TimeTreker/chromie`, branch `main`, base
`7f9d1c019b5be97c664a3a26d88ae00f1376b459` plus the checkpoint patch that contains this text.

### What is already settled

- Keep the Goal-driven single-authority architecture. GI owns WHAT; Planner owns HOW; GA owns Goal
  continuity; runtime/provider owns effect truth; provider scheduling owns only operational compute.
- Keep Ollama as the maintained production/control path. SGLang is still a candidate provider.
- RTX 5090 provider evidence already proved priority/preemption, presentation lease, interruption
  revocation, reacquisition for replacement TTS, and Deep continuity with protocol 5.
- The RTX 5090 SGLang Qwen3.5-9B production-shaped GI semantic cohort passed only 1/16. Treat that
  model-role promotion as rejected; the correct Host fail-closed validators must not be weakened.
- Do not infer semantic quality from the RTX 4090 Laptop Qwen3.5-4B run described below. It is a
  resource canary only.

### RTX 4090 Laptop measured state

The operator switched to the 16 GB RTX 4090 Laptop and kept CosyVoice on the same GPU. The first
TTS restart loop was a container-network proxy error, not CUDA: the host shell exported
`127.0.0.1:7897`, which addresses the container itself. Using
`host.docker.internal:7897` made CosyVoice healthy with zero restarts. The qualification compose in
this patch now exposes the same proxy/offline contract permanently.

With TTS resident, exact SGLang canary identity:

```text
image: lmsysorg/sglang:v0.5.19-cu129
model: Qwen/Qwen3.5-4B
revision: 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
served name: chromie-qwen35-4b-sglang
weights: HF safetensors, BF16, unquantized
context_length: 32768
max_running_requests: 2
max_mamba_cache_size: 10
```

Measured sequence:

```text
mem_fraction_static=.70
  weight load: 8.62 GB
  result: fail before KV pool; SGLang minimum viable fraction > .826

mem_fraction_static=.90, default prefill graph
  Mamba ~= .53 GB
  KV = 5,091 tokens
  result: fail during prefill CUDA-graph capture OOM

mem_fraction_static=.90, prefill graph disabled
  decode graphs remain for bs=1,2
  SGLang healthy + TTS healthy
  KV = 5,091 tokens
  total GPU ~= 15.9 / 16.4 GiB

same run + --language-only
  multimodal loading still initialized
  0.10 GB multimodal sizing reservation remained
  weights stayed 8.62 GB
  KV stayed exactly 5,091 tokens
  result: no useful memory gain; do not retain this flag
```

The Numba `inkling` warning (`Numba needs NumPy 2.4 or less; got 2.5`) is an ignored optional
multimodal-processor import warning, not the current blocker. Do not downgrade NumPy merely to
silence it.

### Current decision / do-not-do list

The laptop proves **physical co-residency, not a deployable cognitive topology**. 5,091 tokens is
below the maintained GI 16K request and far below other 32K roles.

Do not:

- run protocol-5 and call it product evidence with this 5K pool;
- reduce `max_running_requests` to 1 and thereby remove the foreground-vs-Deep objective;
- shrink semantic contracts, source provenance, or Host validators to fit VRAM;
- add model-specific semantic repair;
- promote Qwen3.5-4B or Qwen3.5-9B in model lock / Agent profiles from these results;
- keep `--language-only` as a supposed memory optimization;
- copy `.90` or disabled prefill graphs blindly to a future quantized model—the new artifact must
  be resized from its own measured pre-load/weight/pool facts.

### Exact next work

The next comparison target is a **quantized SGLang-served model/artifact** appropriate to the
16 GB shared-GPU laptop. Hold these requirements fixed:

```text
CosyVoice resident and healthy
two simultaneous model requests
priority/preemption enabled
32K target context topology (GI must at least clear 16K)
typed non-thinking / structured-output transport
exact source model + revision + quantization + runtime identity retained
```

First prove resource fit only. Do not run or optimize semantic prompts while the engine cannot
retain the required context. Once a quantized candidate retains a production-sized pool:

1. run one foreground-under-Deep provider canary;
2. run one protocol-5 presentation lease/revocation round-trip with TTS;
3. run the frozen production-shaped 16-case GI semantic cohort with the prompt/Schema/Host
   transaction unchanged;
4. only if semantic failures cluster narrowly at an evidenced prompt/profile boundary, optimize
   that owner and rerun focused + full cohorts;
5. only after GI qualification proceed to Fast/Deep Planner and real Agent/Host end-to-end work.

### Patch/application gate

This patch intentionally does **not** add a laptop SGLang Agent overlay. It only makes
qualification infrastructure reproducible and records the checkpoint.

After apply:

```bash
python3 scripts/runtime_configuration_inventory.py
python3 scripts/runtime_configuration_inventory.py --check

python3 -m pytest -q   tests/test_sglang_qualification_compose.py   tests/test_sglang_runtime_integration.py   tests/test_runtime_configuration_inventory.py

python3 scripts/check_repository_policies.py
python3 scripts/check_docs.py
git diff --check
```

Commit the regenerated `config/runtime_configuration_inventory.json` together with the patch
changes if the inventory generator modifies it.

## Historical handoff retained for provenance

Audience: the project owner or coding agent resuming the current Goal-driven
single-authority focus, deployed Planner qualification, and current-revision
evidence closure for Issue #35.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and working state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Pre-delivery base: `46b6fe90a36179e63da36f086ac2b04ed8e7b3c1`
  (`main == origin/main` before this continuation).
- Expected resume revision: the latest normal `main` commit containing this
  handoff and `DEVELOPMENT_CHECKPOINT.md` after the authorized fast-forward push.
- Delivery target: fast-forward `main` to `origin/main`, then verify the remote ref.
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35).
- 2026-09-06 transaction-fidelity continuation: A01–A06 are source-closed in the current worktree. The next evidence gate is a clean checkout with pinned dependencies running `./scripts/run_tests.sh` and recording the full pytest collection/pass counts before any model/profile promotion.
- Scope: deliver the transport, warm-up, scenario, test, status, checkpoint,
  and handoff changes listed below in one revision.

Changed paths:

```text
agent/app/clients/ollama_client.py
config/runtime_exception_boundaries.json
docs/CONFIGURATION.md
docs/STATUS.md
scripts/warm_ollama.sh
scenarios/general_ability/must_pass/speech_identity_latency/standalone_greeting_one_natural_reply.json
tests/test_general_ability_acceptance.py
tests/test_ollama_client.py
tests/test_runtime_reliability_stage4.py
DEVELOPMENT_CHECKPOINT.md
HANDOFF.md
```

## 2026-09-06 transaction-fidelity continuation

The archive audit found six implementation mismatches without changing the target authority architecture. The current worktree removes live GA semantic repair, makes terminal Fast limitations/refusals final unless canonical state materially changes, validates request-specific early speech before release, switches the main test tree to pytest collection and migrates stale hidden tests/scenarios, makes authoritative GI Responsibility projection lossless in both GA prompt paths, and reconciles completed GA commit truth into downstream error results.

Focused evidence retained in this work session: PR7 71 passed plus 2 subtests; A05/A06 focused 153 passed plus 2 subtests; migrated hidden-test focused set 94 passed plus 2 subtests; Level-A `multi_goal_daily_life` 10/10; one broad pytest partition 475 passed plus 50 subtests. Another broad partition exceeded this execution environment's command timeout, so this handoff does **not** claim a complete canonical gate. Run the pinned full gate on the destination checkout before delivery/promotion.

Next commands after applying the patch:

```bash
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
python scripts/general_ability_acceptance.py --mode level-a --ability-class multi_goal_daily_life --no-write
git diff --check
```

## What was reproduced

The exact live greeting did not fail because Goal Interpretation misunderstood
it. On the current RTX 4090 all-Qwen profile, the observed workflow changed as
successive earlier boundaries were repaired:

1. Exact microphone session `fe7a5819`: ASR produced `你好。`; GI returned a
   correct greeting speech Responsibility in about 1.94 s; GA and Fast both
   timed out near 60 s with no output. The session ended before playback.
2. Direct probes showed current Ollama 0.33.2 `/api/generate` with
   `think:false` emitted no bytes before timeout, even for a tiny request.
   `/api/chat` completed immediately, including structured JSON and streaming,
   with no thinking field. GI already used `/api/chat`; generic Agent semantic
   roles used `/api/generate`.
3. After the Agent `/api/chat` repair, a focused greeting still timed out because
   the resident Qwen runner was 16K while GA/Fast requested 32K. An identical
   direct 16K chat completed immediately. The old warm-up had used the broken
   endpoint and had not established production context residency.
4. After restarting Ollama and running the repaired `/api/chat` warm-up, the
   runner reported context length 32768 and direct 32K chat completed. The exact
   greeting then reached GI, GA, and Fast, exposing a repeatable Fast semantic
   failure.

```text
`你好。` -> GI: correct speech Responsibility (~5.50 s)
        -> GA: correct speech Goal (~6.08 s)          [concurrent]
        -> Fast: empty commit (~8.246 s), then        [concurrent]
                 clock Capability + `现在的时间是。`
        -> Host rejects invalid speech-to-clock Plan
        -> no natural greeting response
```

| Module/boundary | Authoritative input and actual output | Expected output | Judgment |
|---|---|---|---|
| Gateway | Exact explicit text; admitted | Admit usable addressed turn | Correct |
| GI | `你好。`; one greeting speech Responsibility | WHAT-only greeting meaning | Correct, slow |
| GA | Immutable GI result; one speech Goal | Exact Goal coverage | Correct, slow |
| Fast commit | Same GI/context; empty commit at ~8.246 s | Natural immediate greeting within 2 s | Late/incomplete |
| Fast terminal | Speech ref `r1`; clock Capability and time-preface text | Speech-only `complete_response`, no Capability | **Earliest remaining wrong semantic boundary** |
| Host validator | Invalid Plan rejected before execution | Validate without semantic rewrite | Correct containment |
| Capability/playback | Not launched as successful work | Launch only from a valid canonical Plan | Correctly absent |

The Fast transaction's printed schema already forbids Capability mapping for a
speech-only source Responsibility. This isolated case therefore does not show a
missing prompt rule and does not justify a greeting-specific patch.

## Unchanged deployed aggregate

The complete directory-discovered must-pass stage then ran once without source,
service, model, or warm-state changes:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
Result: 5/51 hard-passed; 46 hard-failed
Evidence: Level C-preview, dirty source, incomplete runtime identity
Semantic review: pending
```

| Non-overlapping primary result bucket | Cases | Representative evidence |
|---|---:|---|
| Passed | 5 | Three simple body requests, one filler request, one social response |
| Goal Interpretation | 5 | Binding/provenance or relationship/unresolved contract rejection |
| Goal Association | 2 | Structured-output validation failure |
| Fast Planner | 35 | Invalid JSON/DTO, invented fields/Capabilities, timing/resource conflicts, truncation, or missing communication |
| Deep Planner | 1 | Invalid Goal-outcome coverage |
| Preview evidence limitation | 3 | Deterministic reflex requires non-preview execution evidence |

This classification assigns each case once by its primary user-visible failure;
some concurrently running roles also failed. Of 39 retained Fast timings, zero
met the two-second GI-handoff-to-commit target: minimum 9.795 seconds, median
12.228 seconds, maximum 14.586 seconds. The aggregate greeting repeated the
clock-Capability error with GI at 2.676 seconds and Fast commit at 10.685
seconds. This broad distribution rejects the hypothesis that only the greeting
wording is defective.

## Latest supervised voice diagnosis

After that aggregate, the operator ran the dirty source through device
microphone and speaker mode. The latest bundle retains two current-session
turns and their raw model transactions:

```text
SID 97957fa9: `你好。`
  ASR 126.5 ms -> Gateway greeting/admit 2.416 s
  -> GI accepted one greeting speech Responsibility 8.552 s total
  -> GA created one greeting Goal 7.308 s [concurrent with Fast]
  -> Fast empty commit at 9.547 s; terminal result at 10.645 s
  -> raw Plan invented chromie.clock.local + `现在的时间是。`
  -> Host rejection -> fixed failure speech; session total 27.33 s

SID 17c7c47a: Chongqing rain request
  ASR 199.3 ms -> Gateway request/admit 626.1 ms
  -> raw GI output translated exact source `重庆` to `Chongqing`
  -> provenance rejection at 11.572 s; GA/Planner/weather not invoked
  -> same fixed failure speech; session total 18.16 s
```

Both model calls completed with `done_reason=stop`; neither was a timeout,
truncation, HTTP failure, or TTS failure. The GI prompt explicitly requires the
source-language location surface, and the Fast contract requires ordinary
speech to use `complete_response`; the raw Qwen outputs violated those existing
rules. The earliest wrong boundaries are therefore deployed-model inference in
GI and Fast. Deterministic Host validation correctly contained each invalid
result. Its shared failure utterance makes distinct upstream faults sound
identical but is not their cause.

The same model slot alternated 16K GI and 32K Fast requests. Provider records
showed load durations of 3.80 s for greeting GI, 3.87 s for greeting Fast, and
7.81 s for weather GI. This is a measured latency contributor; the exact
internal Ollama eviction/reload mechanism was not independently proven. The
failed greeting Goal also remained active when the weather turn began; whether
failed planning should retain that Goal is an open recovery-state question,
not an authorized change in this delivery.

## Implemented repair

- `OllamaClient.generate_complete()` and `generate_stream()` use `/api/chat`,
  send system/user messages separately, consume `message.content`, and enforce
  non-thinking output. Existing test-fixture response shapes remain accepted at
  the decoder boundary.
- `scripts/warm_ollama.sh` uses the same `/api/chat` path as production.
- `docs/CONFIGURATION.md` owns the updated transport/warm-up statement.
- A discovered must-pass `speech_identity_latency` case now covers exact
  `你好。`, no Capability, one speech Goal/outcome, a Fast communicative act, no
  Fast contract failure, and the existing warm latency budgets.
- The runtime-exception-boundary body hash changed; its reviewed classification
  remains `narrow_reraise`.
- No prompt, Schema, DTO, model, profile, semantic authority, retry, execution
  policy, configuration key, architecture term, or current document was added.

## Why the previous optimization did not fix hello

The Fast v33 and Deep v15 work fixed Codex `gpt-5.6-sol` as the candidate and
measured the prompt + schema + decoder + Host transaction offline. It never used
the local/deployed Qwen model as a Planner proxy. Those strong mechanical and
non-independent same-model results are useful contract evidence, but they are
not evidence that the RTX 4090 `qwen3.5:4b` can follow the transaction.

The target profile uses one Qwen model for every semantic role and
`OLLAMA_NUM_PARALLEL=1`. That serializes the GA/Fast work the architecture starts
concurrently, while the new case proves this Qwen Fast result is also
semantically invalid. The new current run hard-passed only 5/51 must-pass cases;
prior all-Qwen evidence had retained 0/50. The root project gap is qualification of the real
deployable model/resource profile, not absence of a hardcoded greeting rule.

Verdict after the frozen aggregate: **NO PROMPT CHANGE RECOMMENDED**. The next
comparison target is the complete deployable model/resource transaction.

## Retained evidence

Pre-change voice workflow:

```text
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.json
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.md
```

Pre-change bundle:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_212025.tar.gz
SHA-256: 390186fa3f9ffd22d87b429b0454289bd4ebe9a88eeb2b2c0a1dc1edce40145b
```

Post-repair formal greeting:

```text
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/
Result: 0/1, score 40, hard failure
Evidence level: C-preview, private, live text
Workflow SID: 65f84c93
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/01-must_pass-speech_identity_latency-standalone_greeting_one_natural_reply/session-workflows/20260904T14094030079-65f84c93.json
```

Post-change bundle, collected once after the formal case:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_221033.tar.gz
SHA-256: 386c50d9bd1844dead9a2e12da71705535c8da74054ea12c5d37dc8841c2660b
```

Unchanged must-pass aggregate and its one post-run bundle:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
/home/chromie/Downloads/chromie_debug_bundle_20260904_230315.tar.gz
SHA-256: e26db4bbaee0bfa9de7374d7ec81564e78a72e77993963e59b5150fde4907f4a
```

Latest supervised device-mode diagnosis (supersedes the preliminary `231903`
collection for these two turns):

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_232045.tar.gz
SHA-256: 4c8644003dad8f013999f98133bd2493aca52ae5af3a28e6d7cb0515cef3e959
Workflow: session-workflows/20260904T15174264392-97957fa9.json
Workflow: session-workflows/20260904T15191722733-17c7c47a.json
Source: 46b6fe90a36179e63da36f086ac2b04ed8e7b3c1 plus the listed dirty patch
Runtime: Ollama 0.33.2; all roles qwen3.5:4b; GI num_ctx=16384;
Fast num_ctx=32768; think=false; chat/chat_stream transport
```

Do not treat two earlier invocation-error directories as model evidence:
`qwen-chat-transport-must-pass-aggregate-20260904` rejected an unsupported
runtime-identity schema before inference, and
`qwen-chat-transport-must-pass-aggregate-rerun-20260904` used the MCP server
root rather than `/mcp` and received HTTP 404 preflight failures. No debug
bundle was collected for either invalid attempt.

The formal run used a dirty source tree and recorded incomplete runtime identity.
The latest device-mode trace is supervised diagnostic microphone/speaker
evidence, not a formal acceptance run. Neither artifact is clean
committed-revision, simulator, robot, safety, or release evidence.

## Validation

- Focused transport/runtime/scenario suite: 65 passed.
- Repository policy: 15 rule families, zero exceptions.
- Test ownership: passed.
- Canonical `./scripts/run_tests.sh`: passed, including 140 pytest, 2058
  unittest, and 20 legacy Agent tests.
- Unchanged current deployed must-pass aggregate: 5/51 hard-passed; 46
  hard-failed; semantic review pending.
- Latest device-mode diagnosis: two admitted turns, two distinct model-semantic
  failures, both correctly contained and rendered as the same fixed failure
  speech. No post-diagnosis source repair or acceptance rerun was performed.

## Runtime state and exact resume commands

At delivery review, the Host launcher and `python -m orchestrator.orchestrator`
were still running. The four main Compose services (`chromie-agent`,
`chromie-llm`, ASR, and TTS) were healthy, but Ollama `/api/ps` reported no
resident model. The latest retained voice run had also reached
`soridormi-runtime-mcp` and MuJoCo startup checks. Do not infer warm model state
or other service health from the still-running Host process.

Inspect first:

```bash
git status --short --branch
git diff --check
docker compose ps
curl -fsS http://127.0.0.1:11434/api/ps
```

If the Agent image or Ollama process has changed, restore the tested transport
and context state before evidence collection:

```bash
docker compose build chromie-agent
docker compose up -d chromie-agent
docker compose restart chromie-llm
./scripts/warm_ollama.sh qwen3.5:4b
```

Start the Host in the repository root when supervised voice use is intended:

```bash
CHROMIE_OPERATOR_MODE=voice_mujoco ./scripts/start_orchestrator.sh
```

Do not tune the single greeting next. Use the retained 5/51 aggregate to compare
the smallest deployable model/resource-profile change while keeping the frozen
cases and one-authority contracts fixed. Reproduce the dominant Fast failures,
then check the GI, GA, and Deep buckets. Rerun the complete cohort after the
chosen change before broader claims.

Repository-only revalidation:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

## Claim boundary

This delivery repairs the observed Agent endpoint mismatch and the warm-up
context mismatch. Tests verify those source contracts. The formal and later
device-mode cases prove the greeting reaches GI, GA, and Fast and that Host
validation rejects the invalid Plan; the weather turn proves GI can separately
violate explicit source-language provenance. The aggregate proves the current
all-Qwen profile is broadly unqualified—5/51 hard passes, with no retained Fast
timing meeting target—but does not qualify a replacement or normal physical
voice behavior. Clean committed-revision provenance, semantic review,
robot/sim behavior, safety, and release readiness remain open.
