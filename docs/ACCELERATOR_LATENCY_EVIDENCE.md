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
