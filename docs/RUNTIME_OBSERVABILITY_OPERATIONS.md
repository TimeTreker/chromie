# Runtime Observability Operations

Status: current instrumentation, latency, resource, recovery, and retention
procedure. The data model and authority boundary are owned by
[Runtime Observability Contract](RUNTIME_OBSERVABILITY.md).

## Instrumentation pattern

Declare one stable module descriptor near the implementation boundary:

```python
TRACE_MODULE = TraceModule(
    name="orchestrator.cognitive_runtime",
    component_type="cognitive_runtime",
    implementation="GoalDrivenRuntimeCoordinator",
    schema_version=1,
)
```

Continue from the request context and instrument the owned operation:

```python
scope = runtime_tracer.continue_from_context(context)
async with scope:
    async with runtime_tracer.span(
        module=TRACE_MODULE,
        operation="resolve",
        attributes={"lane": lane},
    ) as span:
        result = await resolve()
        span.set_attribute("status", result.status)
scope.finish(state="complete")
```

Use a milestone for an observed point in time rather than wrapping an artificial
span around it. Let the framework assign IDs and timestamps.

## Context propagation

Pass the request context through the normal typed call. When work moves to a
new task, copy the bounded carrier through that context. Detached observability
or evidence tasks should use the parent scope or an explicit link.

Do not pass mutable span objects across service boundaries. Do not place the
complete trace in prompts, capability arguments, or provider requests.

## Disabled overhead

Code must remain correct when trace mode is `off`. Avoid building expensive
attribute payloads before checking whether the scope is enabled. Do not add
extra model calls, provider calls, serialization, or synchronization solely to
produce trace detail.

## Attribute rules

Good attributes are compact and diagnostic:

- route/lane and model name;
- prompt/input/output sizes and token counts;
- timeout and queue duration;
- capability/provider IDs and typed status;
- goal/task/evidence correlation;
- failure class/domain and retryability;
- playback generation/order and cancellation reason;
- resource sample reference.

Do not retain full prompts, unrestricted dialogue, raw audio, model contexts,
private reasoning, credentials, bearer tokens, or large tool payloads.

## Errors and cancellation

Set the span error status when an owned boundary fails. Preserve the existing
classified failure object when available. Cancellation is recorded as
cancellation, not converted to an exception success path. If cleanup fails,
record that as separate evidence without erasing the original cause.

## Instrument boundaries, not every line

High-value boundaries include:

- VAD utterance start/end and ASR send/final;
- Gateway admission and Core interpretation;
- Goal Association, Fast/Deep planning, and Planner response projection;
- TTS request, first PCM, audible playback start/end;
- capability/provider request start, Provider start, progress, terminal result,
  cancellation, and safe idle;
- outcome reconciliation and user-facing result delivery;
- checkpoint, recovery, and trace finalization.

Nested modules should instrument their own work. A parent should not duplicate
child timings as if they were separate operations.

## User-observable latency milestones

Latency evidence must distinguish:

1. admitted user input;
2. first complete valid speech commitment;
3. `tts_request_start`;
4. first provider PCM received;
5. first audible playback;
6. plan readiness;
7. provider/effect start;
8. terminal evidence;
9. final audible playback completion.

A WebSocket connection or provider stream-start event is not audible playback.
A generated text stage is not delivered speech until playback begins.

Warm/cold reports should retain request class, hardware/runtime profile, model
identity, queueing, contract-repair count, and hard failures. Report p50/p95 only
for a reviewed comparable scenario set.

## Session, execution, and audio trace

The Orchestrator owns the detached session trace that follows one admitted turn
through cognition, skill runtime, outcome reconciliation, and speech delivery.
Preserve the same `session_id` and trace carrier across queued synthesis and
playback tasks.

Speech evidence should include stage, purpose, commitment state, generation,
order, and actual playback-start status. Scheduled or synthesized speech that
never begins playback must remain `not_delivered`.

Capability evidence should preserve request ID, `capability_id`, source Goal
IDs, confirmation state, Provider start, result status, and cancellation scope.
A later ordinary turn does not by itself erase an independent Goal's terminal
result obligation.

## Input, action, and idle coverage

### VAD and ASR

Record audio duration, RMS, sample format, ASR send duration, final transcript
size, and unusable/ignored disposition. Raw audio is not part of the normal
trace payload. Device identity may be recorded as a bounded stable label.

### Actions

Record trusted capability preparation, Provider dispatch, Provider start,
progress/terminal evidence, cancellation, post-status, and safe idle. Do not
claim physical execution from a dry run or simulation-only backend.

### Idle and closure

Record deterministic session completion, pending task counts, queued/played/
failed speech counts, and cleanup. Idle sweep or shutdown must finalize or
abandon active traces explicitly.

## Resource and accelerator samples

Resource samples are timestamped observations correlated to a trace or runtime
window. Current collectors may include CPU, memory, GPU memory/utilization,
model residency, and queue state. Samples should remain bounded and should not
block user-observable work.

Accelerator telemetry is context for latency and failure analysis. It is not
proof that a model or provider produced a correct semantic result.

## Checkpoints and restart recovery

Configure a checkpoint directory only on a trusted local filesystem. Writes are
atomic. Recovery should validate schema and source identity before continuing a
trace. Incompatible or stale active checkpoints are finalized as abandoned or
quarantined; they are never silently treated as completed evidence.

Checkpoint retention should be shorter than retained completed evidence unless
a supervised investigation requires otherwise. Cleanup must avoid deleting an
active checkpoint still owned by a running process.

## Runtime Event retention

Runtime Event roots contain `.staging/` and `ready/` packages. Consumers read
only complete packages under `ready/`. Optional trigger files reference the
completed manifest and payload root.

The producer owns event classification and payload construction. The data loop
owns deduplication, aggregation, storage/bandwidth policy, and external delivery.
A failed optional trigger does not mutate the original runtime outcome.

## Configuration

Primary trace settings:

- `CHROMIE_RUNTIME_TRACE_MODE=off|basic|debug`;
- `CHROMIE_RUNTIME_TRACE_MODULES`;
- `CHROMIE_RUNTIME_TRACE_DEBUG_MODULES`;
- `CHROMIE_RUNTIME_TRACE_MAX_ITEMS`;
- `CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTES`;
- `CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTE_CHARS`;
- `CHROMIE_RUNTIME_TRACE_EMIT_EVENTS`;
- `CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE`;
- `CHROMIE_RUNTIME_TRACE_EVENT_MIN_TOTAL_MS`;
- `CHROMIE_RUNTIME_TRACE_EVENT_MIN_FIRST_OBSERVABLE_MS`;
- `CHROMIE_RUNTIME_TRACE_EVENT_ALWAYS_EMIT_ABANDONED`;
- `CHROMIE_RUNTIME_TRACE_COVERAGE`;
- `CHROMIE_RUNTIME_EVENT_ROOT`;
- `CHROMIE_DATA_LOOP_TRIGGER_ROOT`.

Orchestrator session logs and cognitive evidence have their own typed settings.
Those outputs may reference a trace; they do not replace the shared trace
contract.

## Review checklist

Before merging instrumentation:

- module identity is stable and low-cardinality;
- the owning boundary, not a caller, records the work;
- context propagation preserves trace and request IDs;
- disabled mode does not change behavior;
- attributes are bounded and contain no secrets/private reasoning;
- cancellation and hard failure remain distinguishable;
- user-observable milestones use the correct physical meaning;
- child work is not double-counted;
- optional evidence failure cannot authorize unsafe execution;
- focused trace, interruption, latency, and retention tests pass.
