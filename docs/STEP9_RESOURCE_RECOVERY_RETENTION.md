# Step 9: Resource, Recovery, and Trace Retention

## Status

Implemented behind the existing default-off Runtime Trace policy.

Step 9 extends the architecture-independent trace foundation with four
operational capabilities:

- generic process, host-memory, queue, and event-loop resource samples;
- atomic active-trace checkpoints and process-restart recovery;
- configurable latency-threshold and deterministic-sampling retention policy;
- late-bound correlation between session, cognitive, interaction, and episode
  artifacts.

This step does not claim GPU telemetry, fleet analytics, or retained hardware
latency qualification.

## Resource samples

Resource observations use the normal Trace Item contract:

```text
module = chromie.runtime.resources
kind   = resource_sample
name   = runtime_resource_sample
```

The sampler uses standard-library and Linux procfs sources only. Depending on
platform availability, a sample may contain:

```text
process_cpu_time_ms
process_cpu_percent_one_core
process_rss_bytes
process_virtual_memory_bytes
process_thread_count
process_open_fd_count
system_memory_total_bytes
system_memory_available_bytes
system_memory_used_percent
system_load_1m
system_load_5m
system_load_15m
event_loop_lag_ms
playback_queue_depth
mic_queue_depth
active_synthesis_tasks
```

Missing metrics are omitted rather than estimated. The sampler does not invoke
`nvidia-smi`, network services, or another model from the realtime path.

Collection modes are:

```text
off
session
periodic
```

`session` samples start and finish boundaries. `periodic` additionally samples
active traces from the existing Orchestrator session sweeper.

## Active-trace checkpoints

When `CHROMIE_RUNTIME_TRACE_CHECKPOINT_DIR` is configured, active session traces
are atomically checkpointed under:

```text
<checkpoint-root>/active/<trace_id>.json
```

A checkpoint contains the latest raw trace and reproducible summary. It is
recovery evidence, not a completed trace and not a cloud-upload receipt.

Normal finalization removes the active checkpoint. On process startup, stale
active checkpoints are recovered as abandoned traces with:

```text
recovery_reason = process_restart
recovered_from_checkpoint = true
checkpoint_recovered = true
```

If Runtime Event emission is enabled, recovery produces a
`chromie.interaction_trace` package with subtype
`voice_session_restart_recovery`. The original checkpoint is then moved under
`recovered/`. Invalid checkpoint files move under `corrupt/` and are never
silently treated as valid evidence.

Recovery preserves the duration observed at the latest durable checkpoint. It
does not fabricate timing for the unobserved interval between the final
checkpoint and process restart.

## Retention policy

`CHROMIE_RUNTIME_TRACE_EMIT_EVENTS` remains the master gate for normal trace
Runtime Events. When enabled, final traces are selected in this order:

1. abandoned traces, when always-retain is enabled;
2. first-user-observable latency threshold breaches;
3. total latency threshold breaches;
4. deterministic trace-ID sampling;
5. no event when none of the above selects the trace.

The decision is recorded as:

```json
{
  "emit": true,
  "reason": "first_user_observable_latency_threshold",
  "severity": "warning"
}
```

Deterministic sampling hashes `trace_id`, so repeated analysis of the same trace
identity produces the same decision. Thresholds override a zero normal sampling
rate.

Critical cognitive-integrity incidents continue to attach their active trace
scene independently of normal-path sampling.

## Correlation

A voice-session trace starts with `session_id`. As information becomes
available, the same active trace may be enriched with:

```text
conversation_id
cognitive_trace_id
interaction_id
episode_id
```

The trace schema does not require all identifiers at creation time. Correlation
updates are bounded and stop once the trace is finalized.

This lets offline analysis join:

```text
voice-session trace
+ cognitive interaction trace
+ experience episode
+ incident or scenario candidate
```

without merging their distinct evidence contracts inside the realtime runtime.

## Configuration

```bash
CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING=off
CHROMIE_RUNTIME_TRACE_CHECKPOINT_DIR=.chromie/runtime-trace-checkpoints
CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE=1.0
CHROMIE_RUNTIME_TRACE_EVENT_MIN_TOTAL_MS=0
CHROMIE_RUNTIME_TRACE_EVENT_MIN_FIRST_OBSERVABLE_MS=0
CHROMIE_RUNTIME_TRACE_EVENT_ALWAYS_EMIT_ABANDONED=1
```

The defaults preserve previous behavior: tracing and event emission remain off
unless explicitly enabled, and configured event emission retains all traces
unless operators reduce the sample rate or set thresholds.

## Follow-on status

[Step 10](STEP10_ACCELERATOR_LATENCY_EVIDENCE.md) implements non-blocking
accelerator telemetry plus retained latency distributions and evidence-qualified
regression gates. Provider-independent first-motion truth still belongs to the
body telemetry source, and cloud-side clustering/fleet analytics remain future
data-loop work.
