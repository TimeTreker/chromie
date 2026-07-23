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
