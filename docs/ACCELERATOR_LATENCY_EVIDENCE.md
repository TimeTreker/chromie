# Accelerator Telemetry and Latency Evidence Gates

## Status

Implemented and automatically verified at Level A. This work completes the
Chromie-side Runtime Observability implementation. It does not create target
GPU, simulator, microphone, speaker, or physical-robot evidence by itself.
Operators must still retain real traces from the claimed environment before a
release latency gate can be enabled.

## Purpose

This work closes the remaining implementation gaps after resource, recovery,
and trace-retention coverage:

- collect accelerator telemetry without blocking the realtime event loop;
- derive reproducible latency distributions from retained Runtime Trace events;
- compare candidate evidence with a retained baseline under an explicit gate
  policy; and
- refuse release claims when evidence class, environment, sample count, or
  source revision is not qualified.

The trace schema remains architecture-independent. Accelerator measurements are
ordinary `resource_sample` items, and latency reports are derived artifacts.

## Non-blocking accelerator telemetry

The shared sampler is:

```text
shared/chromie_runtime/accelerator_telemetry.py
```

It declares the stable module identity:

```text
module = chromie.runtime.accelerator
kind   = resource_sample
name   = accelerator_resource_sample
```

Collection occurs in a worker thread behind a bounded timeout. The event loop
never calls `nvidia-smi` directly. Results are cached so session finalization can
attach the last truthful observation without launching a subprocess.

The initial provider uses the stable no-units NVIDIA CSV query and records only
bounded operational facts, including:

```text
accelerator_device_count
accelerator_gpu_utilization_max_percent
accelerator_gpu_utilization_mean_percent
accelerator_memory_utilization_max_percent
accelerator_memory_used_total_bytes
accelerator_memory_total_bytes
accelerator_memory_used_percent
accelerator_temperature_max_c
accelerator_power_total_w
```

Per-device records may also include index, UUID, model name, utilization,
memory, temperature, and power. Unsupported fields are omitted rather than
invented.

An unavailable provider is represented by bounded facts such as:

```text
available = false
provider_status = executable_not_found | timeout | no_devices | exit_<code>
```

Raw stderr is not copied into Runtime Trace attributes.

## Sampling modes

```bash
CHROMIE_RUNTIME_TRACE_ACCELERATOR_SAMPLING=off
CHROMIE_RUNTIME_TRACE_ACCELERATOR_PROVIDER=auto
CHROMIE_RUNTIME_TRACE_ACCELERATOR_TIMEOUT_MS=1000
CHROMIE_RUNTIME_TRACE_ACCELERATOR_MIN_INTERVAL_S=5
```

Supported sampling modes:

- `off`: no accelerator collection;
- `session`: collect at session boundaries and retain the latest cached sample;
- `periodic`: also refresh through the existing session idle sweeper.

The provider values are:

- `auto`: select the supported built-in provider;
- `nvidia_smi`: explicitly request the NVIDIA provider;
- `off`: disable provider access independently of sampling mode.

The minimum interval prevents multiple simultaneous sessions from launching
redundant provider commands.

## Retained latency report

The command-line tool is:

```text
scripts/runtime_trace_latency.py
```

It consumes immutable `trace.json` and `trace-summary.json` payloads from one or
more Runtime Event roots. It does not inspect an active trace checkpoint as
release evidence.

Example simulator report:

```bash
python scripts/runtime_trace_latency.py summarize \
  --source .chromie/runtime-events \
  --evidence-class simulator \
  --environment rtx5090-mujoco \
  --label post-change \
  --output .chromie/latency/post-change.json
```

The report records:

- evidence class and environment label;
- Chromie revision and worktree cleanliness;
- source trace count and deterministic source digest;
- complete versus abandoned state counts;
- Runtime Trace coverage counts;
- total-duration and first-user-observable distributions;
- module inclusive, exclusive, maximum, item-count, and error distributions;
- bounded numeric resource distributions; and
- per-trace correlation references.

Distributions include count, mean, minimum, p50, p90, p95, p99, and maximum.
Abandoned traces are excluded by default and can be included explicitly for
reliability analysis.

## Interaction-response latency slices

This section defines the remaining instrumentation and qualification
requirements for grounded-response latency. Direct/Fast/Deep path
classification and Deep invocation reasons are implemented. TTS request,
first-PCM, and playback timing exists in retained session evidence, but a
correlated first-valid-speech-commitment trace boundary is still missing; these
slices cannot support an end-to-end latency claim until that boundary and the
model/repair timings below are retained together.

Response-latency qualification must keep semantically different request classes
separate:

- direct non-effectful conversation, classified as a direct path with no
  planner invocation or planner-tier value;
- complete bounded capability work, with a terminal Fast plan;
- uncertain, complex, or dependency-heavy work, and work whose safety/resource
  reasoning requires the wider planning boundary, with a recorded Deep Planner
  reason.

For each class, retained traces must distinguish:

- admitted input to the first complete, schema-valid, Host-authorized speech
  commitment;
- speech commitment to `tts_request_start`;
- TTS request to first PCM chunk;
- first PCM chunk to `first_audio_playback`;
- total `first_user_observable_latency_ms`;
- Goal Association, Fast/Deep Planner, Planner communication validation, execution
  start, terminal evidence, and final playback timing where applicable;
- model queue/evaluation time and contract-repair count and duration;
- request purpose, queue wait, resident model/resource state, and any compute
  priority or pre-emption decision without treating that decision as Goal
  cancellation.

`tts_stream_start` is a transport event, not proof of audible output. Once the
required instrumentation is implemented, a trace that lacks the applicable
commitment, PCM, playback, planner-path, or repair events is incomplete for the
corresponding latency claim. Compare warm and cold p50 and p95 only within the
same request class and declared environment. Goal omission, unsafe execution,
ungrounded speech, critical LLM/schema integrity failure, service failure, or
unsafe idle is a hard failure; it cannot be averaged into a latency pass.

Concurrency qualification compares the maintained single-request setting with
at most one bounded two-request candidate per hardware profile under shared
LLM/TTS load. It must show that user-observable response and TTS work are not
starved by deliberative or optional background work, and must retain the current
setting when p95 latency, hard-failure rate, or recovery worsens. These are
measured scheduling requirements, not fixed realtime/deliberative/background
model slots.

Thresholds must come from a retained representative baseline and an explicitly
reviewed policy. This document does not invent a universal first-response
budget, and automated or simulator traces cannot support a target-audio claim.

## Foreground-priority inference runtime candidate qualification

Chromie's semantic architecture remains one mind even when several model transactions are
logically concurrent. Central LLM inference is a limited compute resource, so the runtime
must protect foreground interaction from deliberative/background contention rather than
serve every role fairly. Scheduling is operational only: it may carry compute class,
provider/instance binding, queue priority, context/output budget, preemptibility, cache
policy, or resource reservation, but it may not own Responsibility, Goal, Capability,
Plan semantics, response wording, or truth.

`agent/app/inference_compute.py` defines only relative provider-neutral classes:
`REALTIME`, `INTERACTIVE`, `CONTINUITY`, `DELIBERATIVE`, and `BACKGROUND`. Their ordinal
rank is not a raw provider priority. Exact provider values and preemption thresholds are
qualification knobs retained with evidence rather than prompt or semantic-DTO constants.
Existing Ollama transactions record the class for observability without sending unsupported
priority fields.

The topology decision is evidence-driven:

```text
Level 1: one candidate engine with foreground priority/preemption
  pass -> keep one engine
  fail -> Level 2: separate foreground and deliberative engines
  fail -> Level 3: physical compute isolation
```

A single engine can improve time-sharing, batching, cache reuse, chunked prefill, and
preemption, but it does not create a second GPU or another semantic brain.

### Isolated SGLang candidate

`docker-compose.sglang-qualification.yml` is separate from production `docker-compose.yml`.
It does not replace `chromie-llm` or change Agent dependencies. It enables SGLang request
priority scheduling, fails a priority-bearing request closed if priority scheduling is not
enabled, keeps the base queue policy explicitly `fcfs`, and exposes configurable
preemption/chunked-prefill/memory knobs. With priority scheduling enabled, SGLang orders the
`fcfs` waiting queue by request priority first and arrival time second; the queue policy and
request-priority mechanism are therefore intentionally separate controls.

Use a pinned image and retain the exact identity in evidence:

```bash
export SGLANG_IMAGE='<pinned-sglang-image-or-image@sha256:digest>'
export SGLANG_MODEL='<exact-huggingface-model-id>'
export SGLANG_MODEL_REVISION='<exact-model-commit>'
export SGLANG_SERVED_MODEL_NAME='chromie-sglang-candidate'
export SGLANG_HF_CACHE_DIR="$HOME/.cache/huggingface"
export SGLANG_CONTEXT_LENGTH=32768

# Qualification starting values, not architecture constants:
export SGLANG_DEFAULT_PRIORITY_VALUE=0
export SGLANG_PRIORITY_PREEMPTION_THRESHOLD=10
export SGLANG_CHUNKED_PREFILL_SIZE=2048
export SGLANG_SCHEDULE_CONSERVATIVENESS=1.0
# This single-user contention probe needs one Deep + one foreground request.
export SGLANG_MAX_RUNNING_REQUESTS=2
# Qwen3.5 uses the default extra-buffer hybrid-state strategy: 5 state slots/request.
export SGLANG_MAX_MAMBA_CACHE_SIZE=10
export SGLANG_MEM_FRACTION_STATIC=0.80

docker compose -f docker-compose.sglang-qualification.yml up -d \
  chromie-llm-sglang-qualification
```

These are qualification starting values, not architecture constants or production defaults.
On the retained RTX 5090 + Qwen3.5-9B + CosyVoice3 path, two failed probes established a bounded
shared-GPU window rather than an arbitrary tuning preference: starting SGLang first at
`mem_fraction_static=0.70` let SGLang become ready but the later TTS warm synthesis failed during
cuFFT initialization; warming TTS first and then starting SGLang at `0.60` failed even earlier
because SGLang 0.5.19 computes its non-static slack from the GPU memory available before model
load. With TTS already resident, that setting reserved more slack than remained after the 17.6 GB
Qwen weights, and the hybrid Mamba/KV budget became negative.

For the foreground-under-Deep experiment, Chromie needs only two simultaneous model requests.
Pinning `max_running_requests=2` prevents irrelevant multi-user concurrency from consuming runtime
state, while `max_mamba_cache_size=10` matches Qwen3.5's observed/default five hybrid-state slots
per request and preserves the existing FP32 SSM state dtype. The `0.80` memory fraction is the next
measured candidate because, with TTS pre-warmed, it retains materially more runtime slack than an
exclusive-GPU setup while leaving enough static budget for weights plus the two-request state/KV
pools. It is not accepted until the exact contention workload completes with TTS alive.

### 2026-09-09 contract repair and responsiveness comparison

The owner requested fixing non-model engineering defects first; model inference quality is
separate future optimization/LoRA work. Migration is judged by foreground interaction latency
and no additional degradation, not by requiring all model roles to become perfect.

Baseline revision: `759b5e062cd43ac2cb919e4ca587a682ca673eee`. The paired 24-case GI runs and
three-trial responsiveness series froze the same worktree digest:
`fc0d5a0b425f759af72c34fa2bfda0eb1555dbc38e5e1992940331eb63227cb9`.
Artifacts: `.chromie/acceptance/sglang-contract-comparison-20260909/`.

**Confirmed non-model defects and repairs:**

| Actual episode / boundary owner | Input → actual output → required output | Diagnosis and repair |
| --- | --- | --- |
| GI schema builder | Prompt requires lexicographic keys; schema placed duration before direction → SGLang grammar rejects direction then duration → decoder must admit the instructed order | `contract_or_schema`: sort binding properties after adding optional context fields, in Fast and Deep. Decoder proof rejects the old order and accepts the fixed order; no meaning, authority or allowed value changed. |
| Primary-screen oracle | Canonical unit-bearing scalar `30度` → oracle demanded 30; unfamiliar name → unconditional ambiguity; minimal source span → not scored | `scenario_or_oracle`: v2 owns separate scenario files, validates references through Schema/Host, preserves units/pronouns, contrasts ambiguity, and checks spans. Historic v1 stays unchanged. |
| Primary-screen result retention | Valid JSON with a length stop, or a mechanically passing result → incomplete termination could pass / passing raw text omitted | `context_or_harness`: require normal stop and retain raw text for both verdicts. Unalignable dimensions are unscored, not false passes. |
| SGLang cache sizing | Default auto-sized shared cache with resident TTS → later CosyVoice allocation OOM → retain speech headroom | `runtime_or_provider`: maintained Compose now exposes positive `SGLANG_MAX_TOTAL_TOKENS`, default 32768, instead of relying on an ignored private override. Exact AWQ profile proved two simultaneous 16K inputs and speech coexistence. |

The schema-order repair alone changed the historical 16-case mechanical result from 2 to
3 passes; remaining raw semantic errors persisted. This is not evidence that the schema
repair resolves all model errors. The source regression covers both depth variants and
context-dependent bindings; compiled decoder evidence is in `decoder-order-proof.json`.

The v2 coverage is 16 retained regressions plus eight minimal contrasts, 15 Chinese and nine
English, six semantic groups, all in `frozen_test`, `training_eligible=false`. It deliberately
omits broad Goal lifecycle/continuity and all-role deployment coverage. The inference corpus
snapshot tree is `b434ce62a0b7a55eb08c1a7b1af0d9da1090c6691cccc2d29af31bc264c80c67`.
Post-batch rubric review additionally accepts “give” as a transfer synonym and source-entailed
“forward” as direction, while keeping measured distance verbatim. Final checked-in tree:
`7b233a6647f20c7c453e6606f70cfeae47f6a592067e8c5c93735d17f2b156b5`.
Original reports are unchanged; separate `post-batch-rubric-review.json` records the review,
which changes neither aggregate pass count. No reference was supplied to model inference.

Actual complete GI workflow for every case:

```text
immutable turn/context → production prompt + sorted dynamic Schema → provider call
  → production parser / deterministic Host
      ├─ rejected primary → explicit unavailable; no semantic retry
      ├─ accepted and unresolved → one fresh source-only Deep call → Host
      └─ accepted and resolved → final GI decision
  → offline schema and semantic rubric review; no GA/Planner/robot execution
```

Both providers received identical primary messages, ordered compatible schema, temperature
and output budget (`paired-packet-audit.json`). SGLang made 24 calls; Ollama made 32,
including eight real unresolved-triggered Deep calls. Confidence alone does not trigger Deep.
SGLang's two deictic cases incorrectly emitted no unresolved meaning, so Deep was not invoked.
All 48 case results were retained and reviewed, including mechanical passes. Correct Host
rejection of translated durations remains intact; other structurally valid wrong meanings
remain model-output findings, not secretly repaired Host results.

Mechanical scores are 2/24 SGLang and 4/24 Ollama. They are diagnostic, not complete semantic
correctness scores. Some nominal passes contain extra/misbound fields (e.g. entity=nod or
addressee=me), so manual findings remain visible. There are concrete cross-deployment changes:
SGLang loses speech modality/sequence for nod-then-hello where Ollama retained them; SGLang
better preserves decomposition in some compound requests where Ollama merges effects.
Thus this is not a monotonic no-degradation replacement. Do not attribute these differences
specifically to SGLang scheduling: quantized artifacts differ, and backend-versus-quantization
numerical causality has not been isolated. No further prompt tuning was performed.

Responsiveness series, three observations per deployment; report medians and ranges, not
release percentiles. These are synthetic foreground requests under active Deep, not full
production GI/Planner payloads or microphone-to-speaker latency:

| Measurement | SGLang AWQ | Maintained Ollama Q4_K_M |
| --- | --- | --- |
| Fast GI first delta | 91.294 ms (49.384–99.433) | 27,473.888 ms (23,220.009–29,466.147) |
| Fast Planner first delta | 85.856 ms (49.872–88.760) | 64.209 ms (63.804–77.632), after Deep finishes |
| Complete foreground window | 279.363 ms (201.700–285.325) | 27,686.594 ms (23,414.119–29,654.988) |
| TTS first audio under tested workload | 3,530.734 ms (2,865.601–4,266.149) | 6,493.102 ms (4,557.640–7,112.504) |

SGLang retained Deep through both presentation leases and resumed it in 3/3 trials; Fast
completed before Deep in 3/3 versus 0/3 for Ollama's one-slot maintained profile. SGLang
replacement TTS first audio was 4,125.545 ms median (4,009.098–5,220.764). Ollama has no
matching pause/revocation primitive in this control, so no paired interruption claim is made.
Audio was generated but not played. The improvement is queue responsiveness, not every module
running faster. Agent end-to-end, actual audible interruption and physical evidence remain open.

SGLang retains the pinned AWQ/image identity from the resource continuation below. Ollama is
0.33.2, image digest `sha256:020e4134285e2ef4d8fd801234176de3b4faadc992a3eb06c8e66a2f9d4c4ba2`,
model `qwen3.5:4b` digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`,
GGUF Q4_K_M, one request slot, q8_0 KV. Its series command recorded CUDA as unknown;
subsequent process-map evidence binds the actually loaded `libcudart.so.13.0.96` in
`ollama-loaded-cuda.txt`. This supplemental observation does not rewrite original metadata.

Bundles: `/home/chromie/Downloads/chromie_debug_bundle_20260909_060924.tar.gz` (order-fix
cohort), `..._061242.tar.gz` (SGLang v2), `..._061915.tar.gz` (Ollama v2), and
`..._062218.tar.gz` (completed responsiveness series). Full paths are in each artifact log.

Delivery changes no maintained provider/model default and adds no semantic repair. Ollama
remains selected because the current whole-deployment candidate has additional behavior
regressions, not because all existing model deficiencies must first be solved. SGLang stays
available as a bounded candidate for the owner's later model work. Qualification-only
`SGLANG_*` inputs grow 14→15; maintained runtime inventory stays 381 keys, four modes,
one public boolean, zero aliases. No new current document or architectural term was added.

### 2026-09-09 quantized laptop continuation

Source baseline: `759b5e062cd43ac2cb919e4ca587a682ca673eee`; only the checkpoint
consolidation was tracked during runtime trials. Private evidence directory:
`.chromie/acceptance/sglang-laptop-quantized-20260909/`.

The initial canonical gate failed because the checkpoint contained 246 lines against its
reviewed 160-line limit. Consolidating superseded checkpoint history into the existing handoff
restored the gate without changing behavior or weakening the check: 2,298 pytest tests,
262 subtests, and 20 legacy Agent tests passed, with two warnings. All pinned test dependency
versions matched; `source-validation.json` and `source-gate-after-checkpoint.log` retain the
exact tested worktree scope. Focused provider/configuration tests passed 19 tests and four
subtests. This is Level A source evidence, not a clean committed revision or target closure.

Resource experiments preserved two requests, 32K per-request context, priority/preemption,
and resident CosyVoice. FP8 used the existing pinned upstream Qwen3.5-4B checkpoint; AWQ used
`cyankiwi/Qwen3.5-4B-AWQ-4bit` revision `ef85d23bebaba87b3c4672ba11c449c79dbdb23e`.
The latter is compressed-tensors W4A16, symmetric group size 32, with BF16 activations/KV;
its upstream source revision is unpublished/unknown. The 4,040,461,440-byte weights matched
SHA-256 `902477edf53bc6768bd1f212dd1866856fd5a0627def06887780c95900ffb013`.
SGLang image digest is
`lmsysorg/sglang@sha256:59e11312666e1c5c155210ea335589b91daa0d70848521b390b93b1b1e8fb0ef`
(version 0.5.19, CUDA 12.9.2). No remote model code was enabled.

| Profile at static fraction .80 | Weights | Shared KV tokens | Observed result |
| --- | --- | --- | --- |
| Online FP8, prefill graphs | 5.93 GB | 58,917 | Provider pass; TTS warmup OOM |
| Online FP8, prefill disabled | 5.93 GB | 32,768 | Provider pass; TTS warmup OOM |
| AWQ, prefill disabled | 3.90 GB | 65,536 | Two simultaneous 32,000-token inputs plus 64 outputs each succeeded; provider pass; TTS warmup OOM |

The actual failure workflow is the same in these three trials:

| Boundary / owner | Authoritative input and actual output | Expected / downstream result |
| --- | --- | --- |
| SGLang resource sizing | Resident TTS, configured cache/request budget; engine starts and allocates cache | Correct startup, insufficient proof of transient voice headroom |
| Provider harness | Structured output, streams, concurrent/cancel/foreground workload; pass | Inference contract satisfied for this synthetic workload |
| Protocol-5 harness | Opens TTS warmup websocket before Deep or any lease | Correct ordering; first audio required before progressing |
| CosyVoice GPU allocation | Warmup synthesis with SGLang resident; 20 MiB allocation fails, free memory only 6.31 / 22.31 / 10.31 MiB respectively | First failed execution boundary; worker fails instead of producing audio |
| Harness containment | Receives worker error; records qualification failure | Correct fail-closed; Deep, lease/revocation and GI cohort not invoked |

The root resource problem is insufficient shared-GPU transient headroom; an idle healthy
container and an allocated KV pool do not prove speech coexistence. No evidence supports
changing semantic prompts, validators, or lease ordering for these failures. Stop SGLang
and successfully synthesize TTS before the next sizing trial. The next AWQ trial caps the
shared cache at 32,768 tokens, freeing 1 GB without changing cognitive authority. This
reduces simultaneous full-context capacity and must be qualified as such.

Failure bundles (one per stopped failed trial), retained outside Git:

- `/home/chromie/Downloads/chromie_debug_bundle_20260909_012302.tar.gz` (FP8 first).
- `/home/chromie/Downloads/chromie_debug_bundle_20260909_012719.tar.gz` (FP8 32K).
- `/home/chromie/Downloads/chromie_debug_bundle_20260909_014054.tar.gz` (AWQ 64K).

These are automated real-GPU/service observations. No microphone, audible playback,
physical robot, repeated latency distribution, or Agent end-to-end proof is claimed.

The AWQ 32K shared-cache trial subsequently passed two simultaneous 16,000-token inputs
with 64 generated tokens each, the full provider canary, and one protocol-5 round-trip.
The same artifact/image used `max_running_requests=2`, Mamba slots 10, fraction .80,
32K context, and disabled prefill graphs. It supports the demonstrated two 16K requests;
two simultaneous full 32K contexts are not claimed. The memory-budget change alters only
SGLang allocation, leaving more transient room for CosyVoice; it does not move semantic authority.

`protocol5-awq32.json` retains first-audio baseline 2,722.82 ms, interruption speech
2,864.89 ms, replacement speech 3,763.01 ms; synthetic Fast GI/Planner TTFTs were
58.47/57.96 ms and interruption-to-GI-first-delta 59.24 ms. Deep stayed active before
both pauses, emitted zero content deltas during each held lease, and resumed afterward.
This is one sample, not P95/P99, production lease policy, real interruption, or audible playback.

The frozen primary GI screen then completed all 16 cases on the unchanged runtime and
worktree hash `b41f1d680d954871b8c3d0953817606cee215affa594f50a39913a8dfdee7263`.
Manifest SHA-256:
`f13c1c14e73bcb1c64092bbf1e959b21cac870b907a9c63ec13b00c8c290bbfe`.
Mechanical result: **2/16 pass, 14/16 fail**. All requests returned HTTP 200 and stopped
without output truncation. Actual prompts were roughly 3.4–3.9K tokens; the separate
capacity probe supplies the larger-context evidence. All request/response pairs, including
passes, are retained in `gi-transactions/`; `gi-adjudication.json` reviews every case.

| GI workflow boundary / owner | Observed contract and output | Judgment |
| --- | --- | --- |
| Canonical payload builder | Exact immutable utterance, token refs, empty bounded context, WHAT prompt/schema; temperature 0, thinking off, 512 output tokens | No expected answers supplied to model; required binding rules present |
| SGLang primary invocation | One complete JSON response per case; missing/mistyped dimensions, translated provenance, wrong modality and lost coordination | Earliest observed semantic failure is the primary transaction output; prompt/template/quantization/model causality not isolated |
| Canonical Host validator | Rejects two translated duration cases; accepts other structurally valid DTOs | Correct duration containment; acceptance does not establish all semantic grounding |
| Frozen oracle | Reports 12 additional failures and two passes | Incomplete oracle; manual review required |
| Downstream authorities | Deep, GA, Planner, Agent/Host execution not invoked by this primary-only screen | No complete semantic-transaction or robot behavior claim |

Failures cluster around typed binding coverage/grounding, modality/coordination, and
referent interpretation. Reject this artifact for GI promotion under the unchanged transaction.
Do not infer that quantization caused these errors without a controlled contrast. No prompt,
Schema, DTO, Host semantic repair, or maintained model profile was changed.

Manual review additionally found that mechanical pass `filler_blink_twice` cites trailing
particle `吧` (t12), contrary to the minimal-source-span contract. The threshold oracle expects
numeric 30 where the canonical unit-preserving contract requires `30度`; the unfamiliar-name
oracle demands unresolved unconditionally although unfamiliarity alone is not ambiguity.
Both failing cases have independent defects, so neither observation rescues this candidate.
These oracle gaps must be reconciled and frozen as a new cohort before another optimization;
do not silently edit or retrospectively rescore this run. Uniform confidence .5 is retained as diagnostic output. Production GI delegates only on
unresolved meaning; confidence alone does not trigger Deep.

One bundle was collected after the complete semantic cohort:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_014915.tar.gz`.
Next work is canonical oracle reconciliation and complete semantic transaction qualification,
then repeated resource/lease proof and Agent end-to-end qualification on a qualified candidate.
Ollama remains the maintained control. Current-target evidence closure remains open.

### RTX 4090 Laptop shared-GPU sizing checkpoint

The 2026-09-09 RTX 4090 Laptop probe keeps scheduler/runtime qualification separate from semantic
model promotion. `Qwen/Qwen3.5-4B` revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` was used only as a SGLang resource canary. The
maintained Agent profile remains Ollama `qwen3.5:4b`, and neither the HF BF16 4B canary nor the
earlier HF BF16 9B canary is qualified as a Chromie semantic-role model.

The first failure was not CUDA-related: CosyVoice inherited a host-shell proxy at
`127.0.0.1:7897`, which resolves to the container itself. Once the TTS container used
`host.docker.internal:7897`, the pinned CosyVoice snapshot downloaded and the worker became healthy
with zero restarts. Qualification Compose therefore propagates the same optional proxy/offline
contract as the maintained model services and maps `host.docker.internal` to the Docker host
gateway. A fully cached operator may instead set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`.

With CosyVoice warm and resident, the laptop exposed about 10.45 GB free to SGLang before Qwen
weight load. The BF16 Qwen3.5-4B weights consumed 8.62 GB and left 1.83 GB. The measured sizing
sequence was:

```text
mem_fraction_static=0.70
  -> weight load succeeds
  -> SGLang rejects KV allocation
  -> provider-calculated minimum viable fraction > 0.826

mem_fraction_static=0.90, default prefill CUDA graph
  -> Mamba cache ~= 0.53 GB
  -> BF16 KV cache = 5,091 tokens
  -> prefill CUDA-graph capture exhausts the remaining GPU memory

mem_fraction_static=0.90, prefill CUDA graph disabled
  -> decode CUDA graphs remain enabled for batch sizes 1 and 2
  -> SGLang and CosyVoice both become healthy
  -> final max_total_num_tokens = 5,091
  -> observed total GPU use ~= 15.9 / 16.4 GiB
```

`--language-only` was also measured as an isolated follow-up and did not reclaim a useful context
budget in SGLang v0.5.19 for this Qwen3.5 path: multimodal loading still initialized, the 0.10 GB
multimodal post-sizing reservation remained, weight memory stayed 8.62 GB, and the final KV pool
remained exactly 5,091 tokens. Do not retain that flag as a Chromie optimization.

This proves physical SGLang + CosyVoice co-residency on the 16 GB laptop, but **does not qualify
the topology for Chromie cognition**. The maintained laptop GI request budget is 16K and other
semantic roles retain 32K request budgets; 5,091 tokens cannot represent that deployment. Do not
trade away the two-request concurrency requirement merely to make the canary fit, because
foreground progress while Deep remains active is the reason for evaluating SGLang.

The next laptop gate is therefore a quantized SGLang-served model/artifact comparison. Hold the
semantic contracts, `max_running_requests=2`, resident TTS, priority semantics, and target context
topology fixed while changing only the exact model artifact/runtime quantization. Resource fit must
be proven before running semantic-role promotion. Only after a candidate has a production-sized
context pool should the frozen GI semantic cohort and then protocol-5 contention/lease/revocation
be used as promotion evidence.

For resource reproduction on the measured BF16 canary, the relevant operator values are:

```bash
export SGLANG_MEM_FRACTION_STATIC=0.90
export SGLANG_MAX_RUNNING_REQUESTS=2
export SGLANG_MAX_MAMBA_CACHE_SIZE=10
export SGLANG_CONTEXT_LENGTH=32768
export SGLANG_CUDA_GRAPH_BACKEND_PREFILL=disabled
```

These values are retained evidence for that exact BF16 canary only. They are not defaults for a
future quantized candidate.

### Candidate-provider contention harness

`scripts/qualify_inference_provider.py` replaces the old vLLM-named transport probe because
the maintained contract is an OpenAI-compatible candidate-provider contract, not a vLLM
semantic contract. It supports `sglang` and `vllm` candidate qualification plus an `ollama`
contention-only deployed control, records provider-specific priority semantics, and includes a
mandatory `foreground_under_deliberative_load` phase:

```text
optional TTS warm/baseline
  -> start long DELIBERATIVE stream with context pressure
  -> wait until it is actively decoding
  -> inject INTERACTIVE Fast-GI canary
  -> while Deep remains active, inject INTERACTIVE Fast-Planner canary
  -> optionally synthesize TTS in the same contention window
  -> require foreground completion before Deep finishes
  -> require Deep to complete cleanly afterwards
```

The harness retains TTFT, elapsed time, maximum inter-delta pause, GPU samples, TTS timing,
provider/model/runtime identity, scheduler settings, and the qualification-only priority
mapping. SGLang's default convention is translated as larger numeric values first; vLLM's
priority convention is translated as smaller numeric values first. These raw numbers are
evidence knobs only and never become semantic configuration.

The contention transaction has three explicit operational model routes: `fast_gi`,
`fast_planner`, and `deliberative`. All three inherit the required base `--model` identity by
default. A deployed topology may override any route only by supplying its model name, exact
revision, and exact artifact record together. This is compute/deployment evidence only; it does
not create separate semantic authorities or personalities. The resolved topology is retained in
`workload_config.model_topology`, so a repeated series cannot silently mix one-model and
multi-model samples.

The synthetic contention workload freezes non-thinking behavior at the provider wire boundary
instead of letting model-family defaults change the canary. Ollama receives its supported
`reasoning_effort=none` for every routed model, matching production `think:false`; this matters
for Gemma as well as Qwen because a short canary must not spend its output budget only on hidden
reasoning and then appear to have produced no content. SGLang and vLLM Qwen3-family routes receive
`chat_template_kwargs.enable_thinking=false`; non-Qwen candidate controls remain provider/model
specific until separately qualified. Reasoning control is retained per transaction route under
`workload_config.reasoning_control`, so samples with different models or reasoning behavior cannot
be combined into one latency distribution.

Every retained provider sample carries an explicit base `model_artifact` operator record plus
the artifact identity of every overridden contention route. Each artifact declares at least
`source_model_id`, `weight_format`, and `quantization`. This is required because a shared model
name is not enough to prove a scheduler-isolated comparison: a GGUF Q4 checkpoint and an HF
BF16 safetensors checkpoint have different memory footprints and compute cost even when both
descend from the same base model. The evidence also hashes the current tracked diff plus all
untracked non-ignored source files. Repeated samples therefore cannot be summarized across a
clean/dirty transition or across two different dirty worktrees that happen to share the same
Git commit.

### Presentation compute-lease probe

The foreground-priority canary answers only whether one LLM request can progress while another
LLM request is deliberating. It does not make an independent CUDA process such as CosyVoice
visible to the SGLang request scheduler. If the foreground LLM path passes but TTS first-audio
latency degrades materially while Deep remains active, qualify the provider's generation-pause
primitive before proposing Agent integration.

For SGLang, `--presentation-lease-mode in_place` changes only the contention transaction after
the Fast-Planner canary has produced its synthetic PresentationCommit boundary:

```text
Deep actively decoding
  -> Fast GI completes under INTERACTIVE priority
  -> Fast Planner completes under INTERACTIVE priority
  -> POST /pause_generation {"mode":"in_place"}
  -> allow already-buffered SSE delivery to settle
  -> synthesize TTS while SGLang inference is quiescent
  -> require zero new Deep content deltas during TTS
  -> POST /continue_generation {"torch_empty_cache":false}
  -> require a new Deep content delta and normal terminal completion
```

This is intentionally an **engine-level qualification primitive**, not the final Chromie
resource-arbitration architecture. `in_place` preserves the running request and its KV state, but
SGLang pauses inference for the engine rather than granting a per-request lease. Production must
still define how a new user input can revoke or supersede a speech lease, and must not make the
LLM provider the semantic owner of presentation policy.

The harness records pause/continue latency, Deep delta counts across the held lease,
resume-to-next-delta latency, TTS baseline and lease timing, and final Deep completion. It does
**not** invent a new TTS slowdown threshold: the result is retained as evidence and must later be
judged with Chromie's existing interaction-latency contract and real
GI -> Planner -> typed `PresentationCommit` -> TTS -> playback evidence.

Run the bounded probe only after the ordinary foreground-under-Deep SGLang canary has passed and
TTS is warm/resident:

```bash
python scripts/qualify_inference_provider.py \
  --provider sglang \
  --provider-version "$SGLANG_VERSION" \
  --runtime-image "$SGLANG_RUNTIME_IMAGE" \
  --base-url http://127.0.0.1:30000/v1 \
  --model "$SGLANG_SERVED_MODEL_NAME" \
  --model-revision "$SGLANG_MODEL_REVISION" \
  --model-artifact-json '{"source_model_id":"Qwen/Qwen3.5-9B","weight_format":"safetensors","quantization":"none","dtype":"bfloat16"}' \
  --cuda-runtime "$SGLANG_CUDA_RUNTIME" \
  --scheduler-config-json '{"schedule_policy":"fcfs","enable_priority_scheduling":true,"disable_priority_preemption":false,"default_priority_value":0,"priority_scheduling_preemption_threshold":10,"chunked_prefill_size":2048,"schedule_conservativeness":1.0,"mem_fraction_static":0.80,"max_running_requests":2,"max_mamba_cache_size":10,"context_length":32768,"max_total_num_tokens_observed":38717}' \
  --contention-only \
  --presentation-lease-mode in_place \
  --deliberative-context-repeat 800 \
  --deliberative-max-tokens 2048 \
  --tts-url ws://127.0.0.1:5000 \
  --tts-speaker chromie_mixed \
  --output .chromie/acceptance/inference-runtime/sglang-presentation-lease.json
```

The workload identity advances to contention protocol version 3 only when this lease mode is
enabled. Repeated-series summarization therefore cannot silently combine ordinary contention
samples with presentation-lease samples.

### Presentation-lease revocation / synthetic user-interruption probe

A stable presentation lease is still insufficient for production because `in_place` pauses the
whole SGLang engine. A new user input that arrives while speech is being synthesized must be able
to revoke that lease before it asks Fast GI for new foreground cognition. The provider must not
turn "speech is active" into "the mind cannot hear anything new."

`--presentation-lease-revocation-probe` extends the bounded provider canary only; it does not
claim microphone detection, playback interruption, or Agent policy. The correct round-trip is:

```text
Deep actively decoding
  -> Fast GI + Fast Planner complete
  -> pause_generation(mode=in_place)
  -> start TTS while Deep is quiescent
  -> first TTS audio arrives (synthetic interruption trigger)
  -> close the old TTS websocket to cancel synthesis
  -> continue_generation(torch_empty_cache=false)
  -> immediately inject a new Fast-GI canary
  -> run a new Fast-Planner canary to the next synthetic PresentationCommit
  -> pause_generation(mode=in_place) again
  -> synthesize the replacement response while Deep is quiescent
  -> require zero Deep deltas during that recovery TTS
  -> continue_generation(torch_empty_cache=false) again
  -> require Deep to resume and finish normally
```

The first-audio trigger is intentionally conservative: it proves revocation after speech has
actually become presentable, not merely while TTS is queued. WebSocket close is already the
qualified TTS request-cancellation boundary. Any native drain that continues after close remains
visible: the replacement synthesis begins immediately after the new PresentationCommit, so its
queue wait includes any still-held TTS singleton/cancellation lock. The harness does not insert an
artificial cancellation sleep.

The first retained protocol-4 RTX 5090 revocation series established 20/20 fast revocation and
Deep continuity, but it also exposed an invalid recovery ordering in the canary itself: after the
interrupted GI completed, the harness let Deep run to saturation and only then asked TTS to prove
recovery. Fast interruption stayed excellent (about 56 ms worst-case trigger-to-GI-first-delta),
but post-interruption TTS recovery became bimodal: about 2.09 s P50 versus about 13.9 s P95/P99.
That path reintroduced the same cross-process contention that the presentation lease exists to
prevent. CosyVoice's worker also uses a three-second bounded cancellation drain before falling back
to terminate-and-reload, so starving that drain can turn a barge-in into a cold-worker tail.
Protocol 4 is therefore diagnostic evidence, not the final revocation transaction.

The corrected round-trip records interrupted GI and Planner latency, TTS close latency,
interruption-trigger-to-GI-first-delta and Planner-finish latency, second-lease pause/continue and
resume latency, Deep delta counts during recovery TTS, and recovery TTS queue/native-first-audio
timing. Revocation samples now use contention protocol version 5 so protocol-4 diagnostics cannot
be silently mixed with the corrected transaction.

### Candidate runtime integration gate

The retained RTX 5090 protocol-5 round-trip series closes the synthetic provider-compute phase:
20/20 samples passed; original and interrupted foreground work completed before Deep in every
trial; both presentation leases held Deep at zero new content deltas during TTS and Deep resumed
afterward in every trial. Observed P99s were about 41.7 ms Fast-GI TTFT, 40.6 ms Fast-Planner
TTFT, 54.6 ms interruption-trigger-to-new-GI-first-delta, 307.1 ms interruption-trigger-to-new
Planner completion, 2.95 ms reacquire-pause, 4.71 ms reacquire-continue, and 3.79 ms
resume-to-next-Deep-delta. Replacement TTS no longer showed the invalid protocol-4 ~14 s tail:
its P99 first audio was about 2.86 s, split into about 825 ms worker queue wait and about 2.15 s
native first audio.

Source may therefore expose an **opt-in candidate runtime integration** without promoting it to
the default deployment. `AGENT_LLM_PROVIDER=sglang` selects an SGLang transport at the Agent
composition root and translates existing provider-neutral compute classes into the already
qualified priority wire field. Ollama remains the default and is not deleted. The Host separately
owns the presentation-compute lease around real Vocal delivery; Planner owns wording/HOW and the
provider merely executes pause/resume resource commands. A newly admitted foreground input revokes
an active engine pause before its routed GI transaction begins.

This source integration is **not** model/role promotion evidence. The provider canaries used one
Qwen3.5-9B served model to isolate scheduler behavior, while the maintained RTX 5090 Ollama profile
still uses its declared Gemma/Qwen role topology. Candidate Agent runs must explicitly select the
served model for each role and then pass the real GI/Planner semantic gates plus
GI -> Planner -> typed PresentationCommit -> TTS -> playback/interruption end-to-end evidence.

Run only after the full presentation-lease series is stable:

```bash
python scripts/qualify_inference_provider.py \
  --provider sglang \
  --provider-version "$SGLANG_VERSION" \
  --runtime-image "$SGLANG_RUNTIME_IMAGE" \
  --base-url http://127.0.0.1:30000/v1 \
  --model "$SGLANG_SERVED_MODEL_NAME" \
  --model-revision "$SGLANG_MODEL_REVISION" \
  --model-artifact-json '{"source_model_id":"Qwen/Qwen3.5-9B","weight_format":"safetensors","quantization":"none","dtype":"bfloat16"}' \
  --cuda-runtime "$SGLANG_CUDA_RUNTIME" \
  --scheduler-config-json '{"schedule_policy":"fcfs","enable_priority_scheduling":true,"disable_priority_preemption":false,"default_priority_value":0,"priority_scheduling_preemption_threshold":10,"chunked_prefill_size":2048,"schedule_conservativeness":1.0,"mem_fraction_static":0.80,"max_running_requests":2,"max_mamba_cache_size":10,"context_length":32768,"max_total_num_tokens_observed":38717}' \
  --contention-only \
  --presentation-lease-mode in_place \
  --presentation-lease-revocation-probe \
  --deliberative-context-repeat 800 \
  --deliberative-max-tokens 2048 \
  --tts-url ws://127.0.0.1:5000 \
  --tts-speaker chromie_mixed \
  --output .chromie/acceptance/inference-runtime/sglang-presentation-lease-revocation.json
```

This remains an engine-level primitive. A production design still needs an explicit Chromie-owned
lease/revocation policy, actual speech/playback cancellation, and a real user-input path. Provider
control APIs can execute the resource decision; they do not own the semantic decision to listen,
speak, interrupt, or continue.

Example SGLang run with the default CosyVoice service:

```bash
python scripts/qualify_inference_provider.py \
  --provider sglang \
  --provider-version '<exact-sglang-version>' \
  --runtime-image "$SGLANG_IMAGE" \
  --model "$SGLANG_SERVED_MODEL_NAME" \
  --model-revision "$SGLANG_MODEL_REVISION" \
  --model-artifact-json '{"source_model_id":"Qwen/Qwen3.5-4B","weight_format":"safetensors","quantization":"none","dtype":"bfloat16"}' \
  --cuda-runtime '<exact-cuda-runtime>' \
  --scheduler-config-json '{"schedule_policy":"fcfs","priority_scheduling":true,"default_priority_value":0,"priority_preemption_threshold":10,"chunked_prefill_size":2048,"schedule_conservativeness":1.0,"max_running_requests":2,"max_mamba_cache_size":10,"mem_fraction_static":0.80}' \
  --tts-url ws://127.0.0.1:5000 \
  --goal-interpreter-probe \
  --output .chromie/acceptance/inference-runtime/sglang-provider.json
```

### Isolated vLLM control candidate

`docker-compose.vllm-qualification.yml` provides the same isolated deployment shape for the vLLM
control candidate. It remains separate from production Ollama and from the SGLang service, pins
image/model/revision inputs, uses vLLM `priority` scheduling (lower numeric values first), enables
chunked prefill, and exposes the batched-token and GPU-memory reservation knobs used by the
qualification.

```bash
export VLLM_IMAGE='<pinned-vllm-image-or-image@sha256:digest>'
export VLLM_MODEL='<exact-huggingface-model-id>'
export VLLM_MODEL_REVISION='<exact-model-commit>'
export VLLM_SERVED_MODEL_NAME='chromie-vllm-candidate'
export VLLM_HF_CACHE_DIR="$HOME/.cache/huggingface"
export VLLM_CONTEXT_LENGTH=32768
export VLLM_MAX_NUM_BATCHED_TOKENS=2048
export VLLM_GPU_MEMORY_UTILIZATION=0.70

docker compose -f docker-compose.vllm-qualification.yml up -d \
  chromie-llm-vllm-qualification
```

Then run `scripts/qualify_inference_provider.py --provider vllm` with the exact version/image/model
identity and the matching scheduler operator record. The old `scripts/qualify_vllm_provider.py`
filename is intentionally removed instead of retained as a compatibility wrapper because it
encoded a provider-specific owner for what is now a provider-neutral qualification contract.

### Deployed Ollama saturated-deliberation control

Provider promotion requires a same-workload control from the deployed Ollama runtime. Ollama is
**not** treated as if it exposed Chromie's request-priority control: the harness sends no
`priority` field for `--provider ollama`, records every compute-class mapping value as `null`, and
labels the provider priority semantics `unsupported_control_no_priority_sent`. The control uses
`--contention-only` so unsupported candidate-only structured-output/overlap gates cannot prevent
the foreground-under-deep-load timing slice from being retained. A control can therefore retain
`status=control_observed` when foreground work waits for Deep; that observation is the baseline,
not a candidate-provider pass.

Run the control against the already deployed model topology, with TTS alive. A single-model
profile needs only the base model identity. A multi-model profile must override the exact routes
that differ from the base. For example, the maintained RTX 5090 profile currently routes Fast GI
and deliberative cognition through `gemma4:12b`, while Fast Planner uses `qwen3.5:9b`:

```bash
python scripts/qualify_inference_provider.py \
  --provider ollama \
  --provider-version '<exact-ollama-version>' \
  --runtime-image "$OLLAMA_IMAGE" \
  --model gemma4:12b \
  --model-revision '<exact-gemma4:12b-ollama-digest>' \
  --model-artifact-json '<exact-gemma4:12b-artifact-json>' \
  --fast-planner-model qwen3.5:9b \
  --fast-planner-model-revision '<exact-qwen3.5:9b-ollama-digest>' \
  --fast-planner-model-artifact-json '<exact-qwen3.5:9b-artifact-json>' \
  --cuda-runtime '<exact-container-cuda-runtime>' \
  --scheduler-config-json '<exact-observed-ollama-runtime-settings-json>' \
  --contention-only \
  --tts-url ws://127.0.0.1:5000 \
  --output .chromie/acceptance/inference-runtime/ollama-provider-control.json
```

The base identity therefore applies to both `fast_gi` and `deliberative`; only Fast Planner is
overridden. This matters because the first foreground transaction can contend with Deep on the
same Gemma runner before the later Planner transaction reaches the already-resident Qwen runner.
Do not collapse those two stages into one generic "foreground model" in evidence.

The same frozen transaction topology should be retained when comparing deployed outcomes. A
single-model SGLang/vLLM Level-1 scheduler experiment answers a different question and may use one
model for all three routes. Their full provider-contract runs remain separate evidence. Do not
compare a warm Ollama control against a cold candidate or change model/context/TTS conditions and
call the result a scheduler-only comparison.

### Repeated contention distributions

One contention run is a retained sample, not P95/P99 evidence. Repeat the exact same contention
configuration into a provider-specific directory, then summarize those immutable samples with
`scripts/summarize_inference_provider_evidence.py`. The summary reuses Chromie's maintained latency
distribution implementation and refuses to combine samples whose provider/model revision/runtime
image/CUDA/accelerator/source revision/scheduler operator record/workload configuration differ.
It reports p50/p90/p95/p99 for Fast-GI TTFT, Fast-Planner TTFT, the complete foreground window,
Deep timing, TTS timing, peak VRAM, and GPU utilization. It does not invent a promotion threshold.

Use `scripts/run_inference_contention_series.py` instead of manually copying a command N times.
The wrapper forwards one frozen `--contention-only` transaction, owns only the per-trial output
paths, verifies that Git revision plus worktree-state hash do not change between trials, and then
invokes the maintained summarizer. It refuses to mix semantic GI probes into the latency series.

```bash
python scripts/run_inference_contention_series.py \
  --trials 20 \
  --output-dir .chromie/acceptance/inference-runtime/sglang-contention \
  --summary-output .chromie/acceptance/inference-runtime/sglang-contention-summary.json \
  --label sglang-rtx4090-laptop \
  -- \
  --provider sglang \
  --provider-version '<exact-sglang-version>' \
  --runtime-image "$SGLANG_IMAGE" \
  --model "$SGLANG_SERVED_MODEL_NAME" \
  --model-revision "$SGLANG_MODEL_REVISION" \
  --model-artifact-json '{"source_model_id":"Qwen/Qwen3.5-4B","weight_format":"safetensors","quantization":"none","dtype":"bfloat16"}' \
  --cuda-runtime '<exact-cuda-runtime>' \
  --scheduler-config-json '{"schedule_policy":"fcfs","priority_scheduling":true,"default_priority_value":0,"priority_preemption_threshold":10,"chunked_prefill_size":2048,"schedule_conservativeness":1.0,"max_running_requests":2,"max_mamba_cache_size":10,"mem_fraction_static":0.80}' \
  --contention-only \
  --tts-url ws://127.0.0.1:5000
```

The sample count remains explicit in the report. Twenty samples are shown only as an operator
example; this document does not redefine the project's latency acceptance policy or claim that a
particular sample count is statistically sufficient for release. Use the same count and frozen
workload for each provider comparison.

### RTX 5090 deployed-topology boundary

The maintained `rtx5090` production profile is not a one-model scheduler experiment. It currently
uses `gemma4:12b` for Goal Interpretation, Goal Association, and Deep Planner, while
`qwen3.5:9b` owns Fast Planner and other latency-sensitive roles. Both models are intended to stay
resident beside TTS. The deployed Ollama control must therefore preserve at least the transaction
route relevant to the foreground-under-Deep experiment:

```text
Deep deliberative load    -> gemma4:12b
Fast GI canary            -> gemma4:12b
Fast Planner canary       -> qwen3.5:9b
TTS                       -> live shared-GPU service
```

This deployed-topology control measures the actual current outcome. It is not scheduler-isolated
because model artifacts, model sizes, and cross-runner GPU contention are part of the result.
Separately run SGLang and vLLM on the exact same HF model revision/artifact when the goal is to
isolate serving/runtime scheduling behavior. Only after those two evidence layers exist should a
production topology change be proposed.

### RTX 4090 Laptop comparison boundary

The maintained `rtx4090_laptop` profile uses Ollama `qwen3.5:4b`, which is a Q4_K_M GGUF
artifact, while the straightforward SGLang/vLLM candidate path uses the upstream
`Qwen/Qwen3.5-4B` safetensors checkpoint. Therefore use the laptop in two distinct layers:

1. **Scheduler/runtime candidate comparison:** SGLang versus vLLM on the exact same HF model
   revision, weight format, dtype, context, workload, TTS state, and sample count. Differences
   here can reasonably be attributed to the serving/runtime stack and its scheduling controls.
2. **Deployed outcome comparison:** compare the winning candidate with production Ollama under
   the same user-visible workload. Because the model artifact/quantization differs, this measures
   the whole deployed topology outcome and MUST NOT be reported as scheduler-only causality.

If an exact matched-weight artifact is later qualified across all runtimes, a stricter
scheduler-isolated three-provider comparison may be added. Do not weaken model quality merely to
force artifact symmetry; serving-runtime qualification and model-role qualification remain
separate decisions.

This phase is provider-level scheduling evidence. The Fast-GI/Fast-Planner strings are
canaries, not production semantic transactions, and
`chromie-presentation-commit-ready` is not a real `PresentationCommit`. A provider pass does
not prove Chromie interaction latency, semantic correctness, audible playback, simulator
behavior, or physical robot behavior. Production Ollama remains unchanged until same-revision
comparison and the actual Agent GI -> Fast Planner -> typed `PresentationCommit` -> TTS ->
playback path satisfy `INTERACTION-LATENCY-001`. The same saturated-deliberation control must
also be retained for Ollama before a cross-provider promotion claim is made.

## Evidence-based latency gate

The gate compares two retained reports:

```bash
python scripts/runtime_trace_latency.py gate \
  --baseline .chromie/latency/baseline.json \
  --candidate .chromie/latency/candidate.json \
  --policy env/validation/runtime_trace_latency_gate.json \
  --output .chromie/latency/gate-result.json
```

Exit status:

```text
0  pass
1  valid evidence but latency regression failed
2  invalid, disabled, or insufficient evidence
```

A policy may require:

- minimum baseline and candidate sample counts;
- the same evidence class;
- a specific evidence class such as `target`;
- the same named environment;
- clean baseline and candidate revisions; and
- explicit metric constraints.

Each metric gate may constrain:

```text
max_candidate_ms
max_regression_ms
max_regression_percent
```

All configured constraints must pass. The gate never converts automated or
simulator evidence into target evidence.

The repository supplies:

```text
env/validation/runtime_trace_latency_gate.example.json
```

It is deliberately disabled. Its example numbers are not release claims.
Operators must copy it to an active policy and enable it only after a retained,
representative baseline exists for the exact target environment.

## Evidence classes

Recommended labels are:

- `automated`: synthetic or unit-level traces;
- `simulator`: retained traces from the declared simulator environment;
- `target`: retained traces from the intended GPU, audio, and robot deployment;
- `production`: governed fleet evidence, when a deployment program exists.

A release policy should normally require `target` for target-latency claims.

## Data-loop relationship

Runtime Trace events remain the immutable evidence source:

```text
Runtime Trace event
        ↓
external Data Loop
        ↓
retained environment-specific evidence set
        ↓
latency report
        ↓
explicit gate policy
        ↓
pass / fail / invalid
```

The external Data Loop still owns transfer, merging, storage governance,
retention, and cloud delivery. The latency tool only reads retained local or
retrieved evidence packages.

## Remaining operational work

No additional Runtime Observability subsystem implementation slice is currently
planned in Chromie. Remaining work is evidence acquisition and product
operations:

- collect representative simulator and target trace sets;
- approve environment-specific gate thresholds from those baselines;
- retain listening, motion, and physical-device evidence where release claims
  require it; and
- build cloud-side clustering and fleet analytics in the future data-loop
  system.

Provider-independent physical-motion truth still belongs to the body/runtime
telemetry source. Chromie records it when that source reports a trustworthy
milestone; it does not infer motion from command acknowledgement.
