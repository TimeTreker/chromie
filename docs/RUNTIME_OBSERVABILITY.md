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
Later evaluation may derive latency reports or scenario candidates, but while a
record is retained its content remains immutable and correlated. Immutability is not
a requirement for indefinite retention: privacy/retention policy may expire or delete
records. Consumers must therefore distinguish `no retained evidence` from a qualified
negative historical fact unless collection and retention coverage is known complete.

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

### Ollama prompt-prefix evidence

Issue [#17](https://github.com/TimeTreker/chromie/issues/17) defines the
observability contract and dependent Issue
[#18](https://github.com/TimeTreker/chromie/issues/18) owns its implementation.
The `llm_prefix_probe_start` event now retains both the legacy raw request proxy
and declared stable-layer evidence; `llm_prefix_probe_finish` correlates the
provider timing response.

The runtime integration must retain two deliberately different evidence
classes:

- declared-layer evidence records layer 0 through 3 character and UTF-8 byte
  counts and SHA-256 digests, plus whether the same model and prompt family
  previously declared the same stable prefix;
- provider completion evidence records Ollama's `prompt_eval_count`,
  `prompt_eval_duration`, `load_duration`, `eval_count`, `eval_duration`, and
  `total_duration` when Ollama returns them.

The existing raw system-plus-prompt character windows remain a source-request
proxy. Neither an exact declared-layer digest nor a raw common-character prefix
is a provider-confirmed cache hit because Ollama applies a model template and
tokenization after Chromie's request boundary. Logs must use wording such as
`stable_prefix_repeat` or `reuse_candidate`, never `cache_hit`, unless a future
provider supplies direct cache-hit evidence.

`reuse_candidate=true` requires an exact declared stable-prefix repeat and an
exact `request_contract_digest` repeat for the same model and prompt family.
The request-contract digest covers structured format and generation options but
does not pretend those out-of-band bytes are prompt tokens. Ollama's returned
`prompt_eval_count` is the only token count retained by this boundary and covers
the complete rendered input, not only the stable layers.

Prompt text is not added to retained attributes. Digests, bounded counts,
model and artifact identity, Ollama version, prompt family, call correlation,
structured format/options identity, runner residency, and timing are
sufficient. A valid benchmark compares repeated requests for the same resident
model and exact stable prefix, retains the changed volatile suffix, and reports
model load time separately. It also includes deliberately changed stable
projections and cold-runner controls. Cross-model calls, unloaded runners, cold
starts, and raw prefix similarity must not be averaged into a KV-reuse claim.

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

When cognitive evidence is enabled, the same Session owner also writes one
JSON workflow fact layer and one human-readable Markdown flow when each SID
becomes complete or abandoned. These reports retain monotonic start/finish
timing plus the already-owned input DTO, output DTO, status, diagnostics, and
attempt number for ASR, Gateway attention, Goal Interpretation, Goal
Association and state commit, Fast/Deep Planning, canonical-plan validation or
rejection, Response Composition, runtime adaptation, fallback speech, and the
Trusted Capability Runtime. The existing runtime event timeline adds TTS,
playback, and provider-result observations. A canonical-plan rejection records
that dispatch was blocked. Provider start is derived only from Trusted Capability
Runtime trace events and is scoped separately to requested Work, ordinary speech
delivery (`chromie.speak`), and the aggregate runtime. Fallback speech therefore
never counts as evidence that the requested capability reached its provider.

Reports are stored beside the configured cognitive evidence file under
`session-workflows/` and retain existing session, conversation, turn, and trace
correlations. Each completed SID also refreshes a conversation-correlated
rolling JSON/Markdown view, so a failure and the user's later follow-up remain
inspectable in one ordered flow without inventing a second conversation
boundary. `ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT` governs raw conversational
text in both report formats; when disabled, textual values and runtime log
messages are replaced by length and digest evidence. The files remain private
runtime evidence and are not safe to publish without review. Report capture is
best-effort, does not infer semantics, and cannot authorize or alter execution.

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
