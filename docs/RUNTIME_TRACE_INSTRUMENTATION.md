# Runtime Trace Instrumentation Guide

## Purpose

This guide defines how Chromie modules participate in Runtime Trace through the
shared `runtime_tracer` implementation. It applies to classes, module-level
functions, service adapters, model clients, audio components, and execution
providers. The initial cognitive/model instrumentation is implemented; later
modules should follow the same contract rather than creating a second profiler.

The authoritative schema is [Runtime Trace Contract](RUNTIME_TRACE.md). The
system-level rationale is
[Runtime Observability Architecture](RUNTIME_OBSERVABILITY_ARCHITECTURE.md).

## Declare stable module identity

A class can declare:

```python
TRACE_MODULE = TraceModule(
    name="agent.fast_planner",
    component_type="planner",
    implementation="FastPlannerResolver",
    schema_version=1,
)
```

A module-level function can use:

```python
TRACE_MODULE = TraceModule(
    name="runtime.capability_validator",
    component_type="validator",
    implementation="validate_canonical_plan",
    schema_version=1,
)
```

Choose names that remain useful across refactors and deployments. Do not include
request values, user identity, model output, or process-local object identity.

## Instrument operations through the shared tracer

Synchronous operation:

```python
with runtime_tracer.span(
    module=TRACE_MODULE,
    operation="validate",
    attributes={"step_count": len(plan.steps)},
) as span:
    result = validate_canonical_plan(plan)
    span.set_attribute("result_status", result.status)
```

Asynchronous operation:

```python
async with runtime_tracer.span(
    module=self.TRACE_MODULE,
    operation="resolve",
    attributes={"goal_count": len(goals)},
) as span:
    result = await self._resolve(goals)
    span.set_attribute("selected_step_count", len(result.plan.steps))
```

A milestone uses the shared marker API:

```python
runtime_tracer.mark(
    module=TRACE_MODULE,
    name="first_observable_motion",
    kind="user_observable",
)
```

The shared API is implemented in `shared/chromie_runtime/runtime_trace.py`.
Modules should import `TraceModule` and the process-local `runtime_tracer`
singleton rather than create competing wrappers or persistence paths.

## Context propagation

The active trace and parent item should be propagated with `contextvars` or an
equivalent async-safe mechanism.

For example:

```text
fast_planner.resolve
└── ollama.generate
```

The Ollama client declares and emits its own item. Fast Planner does not need to
know the child's item ID or serialize the model client's timing.

Parallel child tasks inherit the correct parent context at task creation. The
trace analyzer uses time intervals and links to reconstruct parallelism.

## Let the framework resolve policy

Do not write module logic such as:

```python
if os.getenv("DEBUG_TRACE"):
    write_json(...)
```

Instead, emit through `runtime_tracer.span(...)` and let the shared policy decide
whether the span is active. When metadata is expensive to compute, check the
returned span's `enabled` property after entering it before producing debug-only
attributes.

The framework owns global and per-module configuration, sampling, privacy,
attribute limits, and Runtime Event emission.

## Keep disabled overhead small

When tracing is off:

- no evidence files should be written;
- expensive metadata hooks should not run;
- large objects should not be serialized;
- network or model calls must never be made for tracing; and
- business behavior must remain unchanged.

Module metadata hooks must be cheap and side-effect free.

## Separate module metadata and invocation attributes

Stable identity:

```json
{
  "name": "agent.ollama",
  "component_type": "model_client",
  "implementation": "OllamaClient",
  "schema_version": 1
}
```

Invocation attributes:

```json
{
  "purpose": "fast_planner",
  "model": "qwen...",
  "prompt_token_count": 1200,
  "completion_token_count": 320,
  "done_reason": "stop",
  "cold_start": false
}
```

Do not create a new module identity per model, request, user, capability, or
exception.

## Attribute rules

Attributes should be:

- JSON serializable;
- bounded in number and size;
- stable in naming;
- useful for filtering or analysis;
- safe under the active privacy policy; and
- inexpensive to compute at the selected trace mode.

Prefer counts, classifications, IDs already permitted for diagnostics, booleans,
and durations.

Avoid:

- full prompts or transcripts;
- raw model output;
- arbitrary dataclass or Pydantic dumps;
- audio, image, or binary data;
- secrets and access tokens;
- high-cardinality keys;
- unbounded lists; and
- duplicated child-module timing.

Large evidence belongs in separately declared Runtime Event payload files.

## Errors and cancellation

Let the tracing context manager observe exceptions and cancellation, set the
item status, and re-raise unchanged.

Modules may add a stable classification before re-raising:

```python
span.set_attribute("failure_class", "contract_invalid")
raise
```

Do not convert a failure to success because tracing or event capture failed.
Tracing errors should be isolated according to the framework's policy, while
mandatory incident capture retains its fail-closed evidence guarantees.

## Instrument boundaries, not every line

High-value boundaries include:

- external service or model calls;
- queue entry and dequeue;
- validation and repair attempts;
- execution dispatch, acknowledgement, first effect, and completion;
- audio input completion and first playback;
- lifecycle transitions; and
- meaningful parallel work.

Avoid tiny spans around trivial pure functions. Excessive item counts increase
runtime overhead and make critical-path analysis harder.

## Do not double-count child work

A parent item should measure its operation naturally. It should not manually add
the reported durations of child modules as attributes.

The analyzer derives inclusive and exclusive time from the trace topology:

```text
planner.resolve        800 ms inclusive
└── ollama.generate    700 ms inclusive

planner exclusive      100 ms
```

Manual aggregation risks double-counting and divergence from raw evidence.

## User-observable milestones

Components closest to observable effects should emit the milestone:

- the playback component emits first audible output;
- the execution provider emits acknowledgement and first observable motion;
- the interaction coordinator emits final interaction completion.

A higher-level coordinator should not estimate a lower-level effect when the
owning component can report it directly.

## Review checklist

Before merging new instrumentation, verify:

1. The module identity is stable and low-cardinality.
2. The operation boundary is meaningful.
3. Disabled tracing has negligible overhead and no behavior change.
4. Attributes are bounded and privacy-safe.
5. Child-module work is not manually duplicated.
6. Errors and cancellation still propagate correctly.
7. Unknown kinds or attributes are not required by downstream correctness.
8. The instrumentation does not authorize or alter semantic behavior.
9. Tests cover timing lifecycle, error status, and context propagation where
   applicable.
10. Documentation is updated when the common contract or configuration changes.
