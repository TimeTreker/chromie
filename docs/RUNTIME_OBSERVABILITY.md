# Runtime Observability Contract

Status: current architecture and data-contract authority for Runtime Trace and
Runtime Event evidence. Operational instrumentation and retention procedures are
owned by [Runtime Observability Operations](RUNTIME_OBSERVABILITY_OPERATIONS.md).

## Purpose

Chromie records how a request moved through the runtime without turning
observability into a second semantic authority. Producers describe their own
module identity and emit generic spans, milestones, attributes, errors, and
correlation IDs. The shared runtime framework owns identifiers, clocks, context
propagation, bounded serialization, finalization, summaries, checkpoints, and
optional durable Runtime Event packages.

Traces are evidence. They do not decide user intent, select capabilities,
authorize effects, reinterpret results, or establish safety.

## Owned packages

The current implementation is in `shared/chromie_runtime/`:

- `runtime_trace.py` — trace policy, module identity, spans, milestones,
  checkpoints, snapshots, summaries, context carriers, and event packaging;
- `runtime_events.py` — immutable local event packages and data-loop trigger
  files;
- `cognitive_integrity_events.py` — typed integrity/failure evidence emitted at
  cognitive boundaries;
- `resource_sampling.py` and `accelerator_telemetry.py` — bounded resource
  context;
- `latency_evidence.py` — reviewed latency evidence extraction;
- `scenario_candidates.py` — derivation of reviewable scenario candidates;
- `scheduling.py` and `llm_diagnostics.py` — shared scheduling and inference
  diagnostics used by trace producers.

The Host integration is in
`orchestrator/runtime/interaction_session_evidence.py`: it owns the typed
interaction-Session capture Policy Provider, immutable policy snapshot,
Session-lifecycle collection, and restart recovery. The shared Runtime Event
package remains transport/fact-layer infrastructure and does not own that
domain trigger.

No component may create a parallel trace schema for convenience. Component
logs may remain human-readable, but retained structured evidence must use these
shared contracts.

## Design principles

### Architecture-independent schema

Trace mechanics describe work in generic terms. A module declares what it is;
the framework does not need a registry of every cognitive or provider stage.
This lets new modules enter the trace without extending a central ontology.

### Module-owned identity

Each instrumented module declares a stable `TraceModule`:

```python
TraceModule(
    name="agent.goal_association",
    component_type="goal_association",
    implementation="GoalAssociationResolver",
    schema_version=1,
)
```

`name`, `component_type`, and `implementation` are low-cardinality identifiers.
Per-request values belong in invocation attributes, not module identity.

### Framework-owned mechanics

The shared tracer owns:

- `trace_id`, item IDs, timestamps, monotonic durations, and ordering;
- parent/child relationships and cross-trace links;
- async context propagation;
- bounded attribute normalization;
- cancellation/error capture;
- active, finishing, complete, and abandoned lifecycle states;
- checkpoint persistence and recovery metadata;
- trace summaries and Runtime Event retention decisions.

### Evidence before interpretation

A trace stores observed lifecycle facts and producer-declared classifications.
Later evaluation may derive latency reports or scenario candidates, but the
original evidence remains available and correlated.

### Operational independence

Trace collection can be disabled, sampled, or retained without changing the
semantic or execution result. Failure to persist optional trace evidence must
not silently become permission to continue unsafe work.

## Identity and correlation

### Trace identity

Every trace has a stable `trace_id`. Every item has its own item ID, module
descriptor, kind, operation name, status, start/end timestamps, and duration.
Items may include a parent ID and explicit links to related traces or items.

### Request correlation

When available, producers should attach existing typed identifiers rather than
inventing substitutes:

- `session_id` and conversation ID;
- `turn_id`;
- Goal and task IDs;
- interaction and request IDs;
- `capability_id` and provider request ID;
- confirmation and cancellation IDs;
- evidence and outcome IDs;
- runtime profile and source revision identity.

A correlation field connects evidence; it never transfers semantic or safety
authority.

### Context carrier

The tracer propagates a bounded carrier under `_chromie_runtime_trace` and may
attach a bounded fragment under `_runtime_trace_fragment`. Callers should pass
the existing request context through normal typed boundaries. They must not
copy private tracer internals or serialize in-memory span objects.

## Trace envelope

The current trace schema version is `1`. A snapshot contains:

- trace identity and lifecycle state;
- collection mode and coverage;
- start/end wall-clock timestamps and monotonic duration;
- bounded trace-level attributes and correlations;
- ordered items;
- optional links and recovery information;
- a separately versioned summary.

A trace reference is the compact form used by other evidence records. It
contains the trace ID, lifecycle state, collection mode/coverage, item count,
total duration, and first user-observable latency when known.

## Trace items

### Kinds

The shared tracer supports generic work items rather than project-specific
classes. Current producers use spans for operations and milestones for observed
points in time. Checkpoints and summary references are trace-level records.

### Status

Items begin active. They finish successfully, with error, or through
cancellation. The trace itself becomes:

- `active` while work can still append evidence;
- `finishing` during deterministic closure;
- `complete` after normal finalization;
- `abandoned` when work cannot close normally or recovery explicitly abandons
  it.

Cancellation must not be rewritten as success, and an abandoned trace must
remain distinguishable from an ordinary error response.

### Timing

Wall-clock timestamps use UTC ISO-8601. Durations use monotonic clocks.
Producers should not calculate competing elapsed times when the tracer already
owns the operation boundary.

### Attributes

Attributes must be bounded, JSON-safe, and useful for diagnosis or evaluation.
Use compact typed facts such as route, model, queue depth, token counts,
provider status, failure class, or lifecycle reason. Avoid full prompts,
unbounded tool results, audio bytes, private reasoning, secrets, and high-cardinality
object dumps.

The configured policy bounds item count, attribute count, and individual
attribute size. Truncation is evidence policy, not a semantic transformation.

### Error capture

Errors record exception type, bounded message, cancellation state, and any
producer-owned failure classification already available. Sensitive payloads and
full private tracebacks are not required in retained runtime events.

## Collection modes

`CHROMIE_RUNTIME_TRACE_MODE` supports:

- `off` — no trace items; disabled overhead remains minimal;
- `basic` — lifecycle spans and high-value milestones;
- `debug` — additional bounded diagnostic attributes for reviewed modules.

`CHROMIE_RUNTIME_TRACE_MODULES` may allowlist module names.
`CHROMIE_RUNTIME_TRACE_DEBUG_MODULES` may opt selected modules into debug detail
while the global mode is basic.

Collection mode must not alter planning, execution, cancellation, or response
composition.

## Lifecycle and finalization

A trace begins at the first owning boundary and follows the request across
async tasks through the context carrier. Detached work must continue from the
existing trace or start a clearly linked trace; it must not silently create an
unrelated evidence chain.

Finalization is idempotent. The framework closes active items, determines the
trace state, calculates summaries, applies retention policy, and optionally
persists a Runtime Event. A late producer cannot reopen a complete trace.

The summary includes item counts, status counts, total duration, slowest work,
first user-observable latency, and other bounded derived measures. Summary data
never replaces the item evidence from which it was derived.

## Checkpoint and recovery contract

Long-running or restart-sensitive traces may persist an active checkpoint. A
checkpoint contains the bounded trace snapshot, schema version, write time, and
recovery identity. Atomic replacement prevents a partial file from being
accepted as a valid checkpoint.

Recovery may continue a compatible active trace, finalize it as abandoned, or
record that the checkpoint is invalid. It may not invent missing successful
work. Completed trace retention and active-checkpoint retention are separate
policies.

## Runtime Event packages

A Runtime Event is an immutable local evidence package produced by a component.
`persist_runtime_event()` writes payload JSON files and independently named
binary/path artifacts plus an `event.json` manifest through a staging directory,
syncs them, and atomically moves the package to the ready directory. Every
inventory entry records an artifact ID, content type, size, and SHA-256 digest.
Retry with the same deterministic event identity returns the committed package
instead of producing a second effective result.

The manifest includes:

- schema version and `event_id`;
- event type, subtype, severity, and occurrence time;
- producer identity;
- deterministic fingerprint;
- correlations and bounded attributes;
- derivation metadata;
- payload inventory and capture status.

When a data-loop trigger root is configured, the producer writes a small trigger
record only after the package is complete. The external data loop owns merging,
deduplication, bandwidth/storage governance, retention, and cloud delivery.

A Runtime Event is not a live command bus. It does not authorize execution or
replace direct typed runtime contracts.

## Interaction-Session evidence

`chromie.interaction_session_capture` is an independently controlled Data Loop
policy, not a global observability or Data Loop switch. The Session owner
resolves one typed, versioned policy snapshot at SID start and finalizes it as
complete or abandoned. Restart recovery seals only artifacts that exist and
marks requested missing evidence explicitly; it never fabricates an Episode or
successful trace. Logical evidence demand remains distinct from physical
capture, so a compatible immutable artifact may be reused without merging its
purpose, retention, or provenance.

The fact-layer event keeps its manifest, input PCM16, RuntimeTrace, trace
summary, and Episode as separate artifacts. Runtime/profile identity, policy
digest, activation ID, SID, lifecycle timestamps, artifact digests, and
missing/partial state make later evaluation auditable. Evaluators and scenario
miners remain downstream and never run on the realtime collection path. Chromie
uses Nozdormu v1.x as its current architecture baseline; CP-2026-001/v2 ideas
inform the replaceable provider boundary but remain proposed. The policy,
privacy, and candidate-provenance contract is owned by
[Chromie Data Loop](SCENARIO_CANDIDATE_DATA_LOOP.md).

## Trace-to-event retention

Trace policy may retain:

- every event;
- deterministic samples;
- traces above total-latency or first-observable-latency thresholds;
- abandoned traces regardless of sampling.

Retention decisions are recorded with a reason. A trace can remain available
in process or as a checkpoint without being emitted as a Runtime Event.

## Cognitive Integrity events

Cognitive boundaries may emit typed integrity evidence for contract failures,
unresolved authority, repair exhaustion, or runtime rejection. The event records
what failed and at which boundary. It does not decide the fallback itself.
Fallback and fail-closed behavior remain owned by the existing cognitive/runtime
contracts.

## Episodes and scenario candidates

Episodes summarize user-visible turns and outcomes. Runtime traces explain how
those turns were processed. Scenario candidates may reference both, but they
must preserve source IDs and derivation metadata. A mined candidate is review
input, not a new accepted behavior contract.

## Compatibility and evolution

Schema changes require an explicit version increment and bounded readers for
retained older evidence. Producers may add optional bounded attributes without
creating a new schema version. Renaming identity fields, changing lifecycle
meaning, or changing required manifest fields requires a reviewed migration.

## Safety and authority boundary

Runtime observability must never:

- infer intent from trace shape;
- authorize a capability or provider;
- weaken confirmation or cancellation;
- reinterpret user-facing evidence;
- claim physical success from simulation;
- expose private reasoning, credentials, or unrestricted payloads;
- turn Runtime Events into an effectful control plane.

The Cognitive Core remains semantic authority, the Host validates and executes,
and Soridormi remains physical safety and embodiment authority.
