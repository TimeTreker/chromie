# Runtime Observability Architecture

## Implementation status

The default-off Runtime Trace foundation is implemented across the goal-driven
cognitive/model path and detached voice-session path. Current coverage includes
VAD/ASR, action execution/providers, TTS/playback, first audible and optional
provider-reported first-motion milestones, bounded CPU/memory/queue/event-loop
resource observations, idle abandonment, active-trace checkpoint recovery,
late-bound artifact correlation, and configurable latency/sampling retention.
Cognitive-integrity incidents attach active trace scenes when available.
Optional accelerator telemetry and retained-trace latency report/gate tooling
are implemented. Representative simulator/hardware evidence and approved
environment-specific thresholds remain open and cannot be inferred from the
implementation alone.

## Purpose

Runtime Observability is Chromie's architecture for understanding what happened,
when it happened, how long it took, and which evidence should enter the external
data loop. It is a cross-cutting runtime capability rather than a fixed pipeline
profiler.

The architecture must remain valid when Chromie adds, removes, renames, or
reorders modules. The observability schema therefore describes generic runtime
work and relationships. It does not contain fixed fields such as
`router_latency_ms`, `fast_planner_latency_ms`, or `tts_latency_ms`.

Runtime Observability supports:

- end-to-end and user-observable latency analysis;
- critical-path and parallelism analysis;
- incident diagnosis and root-cause investigation;
- performance-regression detection;
- resource and queue-pressure analysis;
- correlation with semantic experience episodes;
- scenario mining and model/runtime iteration; and
- retained evidence for acceptance and release claims.

It does not replace business logging, semantic planning, Runtime Events,
Experience Episodes, or the external data loop.

## Architectural components

```text
Runtime modules
    │
    │ emit generic trace items
    ▼
Runtime Trace
    │
    │ freezes raw evidence and derived summary
    ▼
Runtime Event package
    │
    │ local durable capture and trigger notification
    ▼
External Data Loop
    │
    │ merge, resource governance, upload, retention
    ▼
Offline and cloud analysis
    ├── latency and critical-path analysis
    ├── incident diagnosis
    ├── episode correlation
    └── scenario-candidate derivation
```

Four artifacts have different responsibilities:

| Artifact | Primary question |
|---|---|
| Runtime Trace | What work happened, in what topology, and how long did it take? |
| Runtime Event | What immutable evidence package should enter the data loop? |
| Experience Episode | What happened semantically across the interaction history? |
| Scenario Candidate | How might retained evidence become a reviewed regression or training case? |

These artifacts are correlated by identifiers. They must not be collapsed into
one unbounded payload or allowed to overwrite one another.

## Design principles

### Architecture-independent schema

Trace producers declare their own stable module identity and emit generic items.
The trace schema does not enumerate Router, Planner, ASR, TTS, robot control, or
any other current component.

The completed trace reveals the real architecture that participated in that
interaction.

### Module-owned identity

Each instrumented class or module declares stable metadata such as:

```python
TRACE_MODULE = TraceModule(
    name="agent.fast_planner",
    component_type="planner",
    implementation="FastPlannerResolver",
    schema_version=1,
)
```

The tracing framework does not maintain a central list of known modules.
Consumers must preserve unknown component types and item kinds.

### Framework-owned mechanics

Modules emit observations through the shared tracing API. They do not write
files, generate trace IDs, calculate durations, invoke the data loop, or parse
trace environment variables independently.

The framework owns:

- trace, item, and parent identity;
- wall-clock correlation and monotonic duration measurement;
- async context propagation;
- bounded attributes and privacy policy;
- buffering and finalization;
- immutable trace snapshots and summaries; and
- Runtime Event integration.

### Evidence before interpretation

The raw completed trace is evidence. Critical-path, exclusive-time, aggregate,
and latency summaries are derived and reproducible.

Analysis must not discard the raw trace merely because a summary exists.

### Operational independence

Tracing must not become an execution authority or a required cloud dependency.
Failure to upload, summarize, or emit an optional normal-path trace event must
not authorize, alter, or silently retry robot behavior.

Critical incident evidence follows the stricter failure-capture policy defined
by [Cognitive Integrity Events](COGNITIVE_INTEGRITY_EVENTS.md).

## Identity and correlation

The architecture distinguishes these scopes:

```text
conversation/session
└── interaction/trace
    └── trace item/span
```

The common identifiers are:

| Identifier | Meaning |
|---|---|
| `session_id` | A longer-lived runtime or conversation session |
| `conversation_id` | Semantic conversation continuity identity |
| `interaction_id` | One user interaction or routed turn |
| `trace_id` | One execution trace, normally aligned with an interaction |
| `item_id` | One timed or instantaneous trace item |
| `parent_item_id` | Structural parent for nested work |
| `event_id` | One immutable Runtime Event package |
| `episode_id` | One retained semantic episode snapshot |
| `scenario_id` | One derived scenario-candidate identity |

Not every producer has every identifier. Producers include all identifiers they
truthfully know and never invent false correlations.

## Lifecycle

A normal interaction follows this lifecycle:

```text
trace created
    ↓
modules append items and milestones
    ↓
interaction completes or fails
    ↓
trace freezes
    ↓
summary is derived
    ↓
trace may be attached to an incident or emitted as an interaction-trace event
    ↓
data-loop trigger is produced when configured
```

A session may contain many interaction traces. Session lifecycle events can
summarize the set of traces, but session completion is not guaranteed. A process
restart, power loss, or crash may leave a session abandoned. Recovery tooling
must be able to finalize such a session as incomplete without rewriting its
existing trace evidence.

## Collection modes

Runtime Trace defines three initial modes:

| Mode | Behavior |
|---|---|
| `off` | No optional trace collection. Mandatory safety and incident evidence may still be retained. |
| `basic` | Low-overhead identity, timing, hierarchy, status, counters, and user-observable milestones. |
| `debug` | Basic data plus explicitly allowed bounded diagnostic attributes and resource context. |

The tracing framework resolves global and per-module policy. Business modules do
not directly interpret environment variables or create their own debug file
formats.

Normal-path full traces may be sampled. Critical incidents and configured
latency-threshold breaches may request complete traces. The external data loop
owns upload, retention, compression, bandwidth, and storage policy.

## User-observable latency

Backend stage duration is not sufficient to describe robot responsiveness.
Traces should record milestones when available, including:

```text
input_started
input_finished
asr_final
first_acknowledgement_audio
first_final_audio
execution_dispatched
execution_acknowledged
first_observable_motion
execution_completed
interaction_completed
```

These are generic milestone names, not required pipeline stages. Different
products or modules may emit additional user-observable milestones under the
same item contract.

The analyzer may derive metrics such as:

- input-finished to first observable response;
- input-finished to first audio;
- input-finished to first motion;
- input-finished to task completion; and
- total interaction duration.

## Resource context

Timing evidence may be correlated with bounded resource observations such as:

- CPU and memory pressure;
- GPU utilization and memory;
- model warm/cold state;
- event-loop lag;
- inference or execution queue depth;
- network timing;
- audio backlog; and
- controller acknowledgement latency.

Resource collection is optional and policy-controlled. High-frequency metrics
belong in a dedicated telemetry system or attachment, not in unbounded trace-item
attributes.

## Relationship to Runtime Events

Runtime Trace records execution flow. Runtime Events provide durable packaging
and data-loop notification.

A completed trace can be represented as:

```text
trace.json
trace-summary.json
```

These files may be included in:

- `chromie.cognitive_integrity_failure`;
- a future execution or safety incident;
- `chromie.interaction_trace`; or
- a future session-summary event.

Runtime Event packaging rules are defined in
[Runtime Event Architecture](RUNTIME_EVENT_ARCHITECTURE.md).

## Relationship to episodes and scenarios

Experience Episodes preserve semantic history. Runtime Trace preserves execution
topology and timing. Incident packages preserve failure-boundary evidence.

Offline analysis can correlate:

```text
Episode + Runtime Trace + Incident
    ↓
root-cause and latency analysis
    ↓
Scenario Candidate
```

Scenario candidates remain derived artifacts under mandatory human review. See
[Scenario Candidate Data Loop](SCENARIO_CANDIDATE_DATA_LOOP.md).

## Implementation sequence

The intended implementation sequence is:

1. define the shared Runtime Trace contracts and lifecycle;
2. add context propagation and sync/async span APIs;
3. instrument the goal-driven cognitive path and model calls;
4. instrument execution, audio, TTS, and provider boundaries incrementally;
5. derive summaries from the observed topology;
6. attach trace evidence to critical incidents;
7. optionally emit sampled normal interaction-trace events; and
8. add session-level summaries and abandoned-session recovery.

Instrumentation coverage is incremental. A partially instrumented trace remains
valid and must state its coverage honestly.

## Authority and safety boundary

Runtime Observability may observe and report runtime behavior. It may not:

- invent planner semantics;
- authorize capabilities or physical execution;
- alter model output;
- hide a failure behind a successful trace summary;
- claim cloud upload from a local trigger receipt; or
- automatically promote evidence into regression or training datasets.

The Host remains responsible for deterministic validation and safety policy.
The external data loop remains responsible for transport and resource
governance. Human review remains required for scenario promotion.
