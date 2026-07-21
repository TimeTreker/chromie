# Runtime Trace Contract

## Status

This document is the normative contract for Chromie's Runtime Trace subsystem.
The initial implementation exists in
`shared/chromie_runtime/runtime_trace.py` and currently instruments the
goal-driven cognitive/model path with partial coverage. Execution, audio, TTS,
provider/resource observations, user-observable milestones, session lifecycle
recovery, and retained live latency evidence remain open.

## Trace envelope

A Runtime Trace is one correlated execution timeline:

```json
{
  "schema_version": 1,
  "trace_id": "trace_...",
  "state": "complete",
  "started_at": "2026-07-19T12:00:00.000000+00:00",
  "finished_at": "2026-07-19T12:00:02.840000+00:00",
  "duration_ms": 2840.0,
  "correlations": {
    "session_id": "session_...",
    "conversation_id": "conversation_...",
    "interaction_id": "interaction_...",
    "turn_index": 4
  },
  "collection": {
    "mode": "basic",
    "coverage": "partial",
    "sampling_reason": "latency_threshold_exceeded"
  },
  "items": []
}
```

Valid lifecycle states are initially:

```text
active
finishing
complete
abandoned
```

Only `complete` and `abandoned` traces are immutable retained snapshots.

## Module descriptor

Every producer declares its own module identity:

```json
{
  "name": "agent.fast_planner",
  "component_type": "planner",
  "implementation": "FastPlannerResolver",
  "schema_version": 1,
  "version": "optional implementation version"
}
```

Requirements:

- `name` is stable, globally namespaced, and low-cardinality;
- `component_type` is descriptive and open-ended;
- `implementation` identifies the class, function, service, or runtime adapter;
- `schema_version` versions the module metadata contract, not every code change;
- unknown fields and component types must be preserved by consumers.

Module descriptors must not include user IDs, request IDs, prompt text, exception
messages, or other per-invocation values.

## Trace item contract

Every item uses the same common envelope:

```json
{
  "trace_id": "trace_...",
  "item_id": "item_...",
  "parent_item_id": "item_parent_or_null",
  "name": "fast_planner.resolve",
  "kind": "operation",
  "module": {
    "name": "agent.fast_planner",
    "component_type": "planner",
    "implementation": "FastPlannerResolver",
    "schema_version": 1
  },
  "operation": "resolve",
  "status": "ok",
  "started_at": "2026-07-19T12:00:00.100000+00:00",
  "finished_at": "2026-07-19T12:00:00.430000+00:00",
  "duration_ms": 330.0,
  "attributes": {
    "goal_count": 2,
    "repair_attempted": false
  },
  "links": []
}
```

Required common fields are identity, module, operation, status, and timing or
milestone time. Component-specific facts belong in bounded `attributes`.

## Item kinds

Initial examples include:

```text
session
interaction
operation
model_call
tool_call
queue_wait
execution
user_observable
resource_sample
event
```

This is not a closed enumeration. Unknown kinds remain valid and must be stored,
transported, and displayed generically.

## Status

Initial item statuses are:

```text
unset
ok
error
cancelled
timeout
abandoned
```

The common status is operational. Semantic outcomes such as `respond`,
`execute`, `blocked`, or `needs_information` belong in component attributes or
existing domain contracts.

## Timing rules

The tracer records:

- a wall-clock timestamp for cross-process and event correlation; and
- a monotonic timestamp internally for duration calculation.

`duration_ms` must be derived from the monotonic clock. Wall-clock subtraction
must not be the sole duration source because system time can move.

Instantaneous milestones have one timestamp and a duration of zero or omit
`finished_at` according to the eventual implementation schema.

## Hierarchy and links

`parent_item_id` represents structural nesting. Context propagation should make
nested module calls form a natural tree without manually passing IDs.

Parallel and non-parent dependencies can be represented through links:

```json
{
  "relationship": "follows_from",
  "item_id": "item_goal_association"
}
```

Initial relationship names may include:

```text
follows_from
caused_by
scheduled_by
observes
```

Unknown relationships must remain valid.

## Attributes

Attributes are JSON-serializable, bounded, and policy-controlled.

Good basic attributes:

```text
goal_count
candidate_count
queue_depth
prompt_token_count
completion_token_count
skill_count
cold_start
repair_attempted
```

Sensitive or high-volume data such as prompts, transcripts, model output,
images, audio, stack traces, or arbitrary request objects must not be inserted
as normal attributes. They belong in explicitly governed evidence attachments or
incident payloads.

Attribute keys should be stable and low-cardinality. Values that create one key
or module identity per user, request, or error message are forbidden.

## Error capture

A span should automatically record bounded error classification when it exits
with an exception:

```json
{
  "status": "error",
  "error": {
    "type": "PlannerContractError",
    "classification": "contract_invalid"
  }
}
```

Raw stack traces and exception messages are debug or incident evidence governed
by explicit policy. Trace instrumentation must not swallow or replace the
original exception.

## Collection modes

### Off

Optional spans are not collected. Mandatory incident or safety evidence may
still be retained.

### Basic

Basic mode records:

- module and operation identity;
- hierarchy and links;
- start, finish, duration, and status;
- bounded counters;
- user-observable milestones; and
- minimal collection metadata.

### Debug

Debug mode may additionally record explicitly approved:

- validation and repair classifications;
- candidate and decision summaries;
- model usage and completion diagnostics;
- queue and resource snapshots; and
- sanitized request or response summaries.

Debug mode is not permission to serialize arbitrary objects or bypass privacy
policy.

## Finalization and summary

Finalization freezes `trace.json` and derives `trace-summary.json`.

The summary may contain:

```json
{
  "schema_version": 1,
  "trace_id": "trace_...",
  "status": "complete",
  "total_duration_ms": 2840.0,
  "item_count": 17,
  "critical_path_item_ids": [],
  "largest_items": [],
  "module_aggregates": [],
  "first_user_observable_latency_ms": 1310.0,
  "coverage": "partial"
}
```

Derived analysis should distinguish:

- inclusive duration: an item plus nested work;
- exclusive duration: time attributable to the item outside child spans;
- critical-path duration;
- queue wait versus processing time;
- sequential versus overlapping work; and
- user-observable versus backend completion latency.

For overlapping children, exclusive time cannot be calculated by simply
subtracting the sum of child durations. The analyzer must operate on interval
unions and dependency topology.

## Runtime Event integration

The raw trace and summary may be declared as Runtime Event payload files:

```text
trace.json
trace-summary.json
```

A normal trace event should use a stable event type such as:

```text
chromie.interaction_trace
```

Critical incidents should include or reference the correlated trace rather than
emitting an unrelated duplicate trace with ambiguous ownership.

The Runtime Event ready directory remains the source of truth for data-loop
capture. A trigger receipt does not mean cloud upload succeeded.

## Compatibility and evolution

Adding a new module, item kind, link relationship, or bounded attribute does not
require changing the common schema version.

A schema-version change is required when the meaning or required structure of
the common trace envelope changes incompatibly.

Consumers must:

- tolerate unknown fields, kinds, component types, and relationships;
- preserve raw evidence when generating summaries;
- avoid assuming a fixed Chromie pipeline; and
- report partial instrumentation coverage honestly.
