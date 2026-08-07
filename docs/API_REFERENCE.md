# API and Protocol Reference

This document describes interfaces implemented in this repository. Soridormi
is a separate deployment; only its checked-in capability contract is summarized
here. Current revision and verification status are maintained in
[STATUS.md](STATUS.md).

## Cognitive Core turn-interpretation API — Agent port 8092

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/cognitive-gateway/attention-review` | Return only bounded addressedness admission evidence for one inactive turn; it cannot author route, intent, capability, action, plan, or response. |
| `POST` | `/cognitive-core/interpret` | Interpret one admitted `CoreTurnRequest` containing an immutable `UserTurnEnvelope` and digest-bound `GatewayContextSnapshot`. |

The Cognitive Gateway remains an embedded Host boundary and does not expose a
separate semantic-routing service. It owns input normalization, protective
reflexes, attention review, bounded context assembly, and turn admission. The
Goal-Driven Cognitive Core owns ordinary meaning, goal interpretation, task
continuity proposals, capability intent, planning handoff, and response intent.

`POST /cognitive-gateway/attention-review` accepts only normalized turn identity,
text, language, and bounded host engagement evidence. Suppression is limited to
high-confidence inactive ambient speech. An internally contradictory
`addressed=false` result with a directed or unclear speech act receives one
schema-constrained model repair; direct, unresolved unclear, malformed,
unavailable, or failed review admits the turn.

`POST /cognitive-core/interpret` accepts only a schema-valid admitted
`CoreTurnRequest`. Bare text, a suppressed envelope, mismatched context identity,
or a context digest mismatch is rejected before Goal Interpretation. The result
is a `CoreInterpretationResult` bound to the turn and a SHA-256 digest of its
internal `RouteDecision` compatibility projection. It is advisory cognitive
evidence and does not authorize side effects. The Orchestrator still
validates schemas, authorization, confirmation, resource conflicts, commitment,
and trusted execution evidence before any effectful request runs.

A successful interpretation returns HTTP `200` with `CoreInterpretationResult`.
When a non-empty admitted turn cannot be interpreted after the bounded model
path, the endpoint returns HTTP `503` with
`CoreInterpretationUnavailable`. That result carries turn identity and a typed
failure reason but no invented route, intent, action, or compatibility
projection. Callers must surface or handle that unavailable result; they must
not reinterpret it as generic chat.

The implementation may use fast and review models, but it must reason from
meaning, context, active goals, and capability descriptions. Production code
must not use phrase tables, regular-expression intent routing, scenario IDs, or
fixed input-to-action mappings.

## Agent HTTP API — port 8092

FastAPI also exposes its generated OpenAPI UI at `/docs` while the service is
running.

### Runtime and capability inspection

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return model/runtime state, loaded capability sources, feature gates, scheduler counters, and the legacy CapabilityAgent emergency gate. |
| `GET` | `/semantic-authority` | Return the machine-readable single-authority route matrix and current Agent emergency-fallback gate. |
| `GET` | `/agents` | List specialized agents and ownership notes. |
| `POST` | `/cognitive-gateway/attention-review` | Focused pre-Core admission review; returns addressedness evidence only and fails open. |
| `POST` | `/cognitive-core/interpret` | Envelope-first ordinary semantic Goal Interpretation inside the Core. |
| `GET` | `/agent-skills` | Return bounded owner-approved Agent Skill metadata summaries and configured package provenance only; no Skill body or projection text. |
| `POST` | `/agent-skills/select` | Let the declared responsible Agent role make a typed model-authored no/one/multi-Skill decision from bounded approved summaries; this endpoint does not load projections, mutate Plans, or execute Capabilities. |
| `POST` | `/agent-skills/disclose` | Load only exact projections from a validated selection under digest and prompt-budget checks; it does not mutate Plans or execute Capabilities. |
| `GET` | `/capabilities` | Return the active merged static capability registry and manifest sources. |
| `GET` | `/capabilities/catalog` | Return the shared catalog, including last-known live named capabilities and refresh status. |
| `POST` | `/capabilities/search` | Rank relevant capabilities for Goal Interpretation and normal InteractionRuntime. |
| `GET` | `/capabilities/llm-context?language=en&text=...` | Return concise full-catalog or query-specific LLM context. |
| `POST` | `/goal-association` | Resolve continuity-before-creation and independent Goal segmentation for the unified runtime; the endpoint itself does not mutate host state. |
| `POST` | `/fast-plan` | Produce a complete common-catalog `CanonicalPlan` or terminal Deep Planner escalation. |
| `POST` | `/deep-plan` | Produce a terminal full-catalog `CanonicalPlan`, including bounded same-tier revision. |
| `POST` | `/compose-response-plan` | Bind goal-scoped speech and optional auxiliary attention to an immutable terminal plan. |
| `POST` | `/tools/execute` | Execute one exact planner-selected, explicitly interaction-executable safe read-only local capability and return structured evidence only. |
| `POST` | `/tool-result/interpret` | Select exact grounded facts from complete tool evidence and synthesize a concise spoken answer. |

`GET /agent-skills` reports the passive read-only cognitive-content registry.
The maintained repository root is mounted read-only and contains the approved
`chromie.grounded-external-information` and `chromie.weather-information`
packages. Startup validates safe YAML, explicit
`authority=agent_method_only`, explicit `execution_authority=none`, owner
approval, semantic version, deterministic package digest, projection paths,
duplicate IDs, parent references, inheritance cycles, and normalized
`applicable_routes`. The endpoint exposes only immutable bounded summaries. The
two packages expose projections for all five maintained Agent roles; the
weather package declares the grounded method as its parent and remains passive
despite referencing required/optional Capabilities.

`POST /agent-skills/select` accepts the responsible Agent projection name, the
current user text, bounded Goal context, optional bounded context summaries, and
an optional explicit candidate-ID set. The Host performs only structural
discovery: it filters by declared projection, validates explicit IDs, sorts and
caps the candidate summaries, then lets the configured model author an explicit
`no_skill` or ordered one/multi-Skill decision. The closed output is validated
against the exact disclosed IDs, versions, projection, Goal IDs, confidence,
and registry digest. One invalid result may receive one same-boundary repair;
model or contract failure returns an optional no-Skill resolution rather than
fabricating method provenance. No `SKILL.md` or projection text is loaded, no
Canonical Plan is changed, and no Capability is registered, authorized, or
executed. Before disclosure, a non-empty package-owned `applicable_routes`
list removes that package from the candidate set when the current structured
route does not match; an empty list remains unrestricted. This is a structural
applicability boundary, not Host semantic selection. `/health` reports whether
this independent selection boundary is enabled plus its model and candidate
limits.

Catalog entries include `prompt_tier=common|rare`, plus
`prompt_tier_locked`, `prompt_tier_source`, and `prompt_tier_reason`. The
Goal Interpretation uses unlocked `common` entries for the fast compact Qwen prompt as
`common_ability_catalog`; deepthinking may use the full catalog. Safety-locked
entries remain visible in the full catalog but are excluded from the fast
common prompt even when an experience overlay requests `common`. The initial
preset is data in `capabilities/prompt_tiers.json`, not a Python skill list.
`chromie.speak` remains common and interaction-executable for legacy/native
`InteractionResponse` compatibility, but the Goal-driven Fast and Deep Planner
schemas exclude it as response transport. A mixed conversational/body turn uses
a goal-scoped `respond` outcome plus executable body steps; the Response
Composer owns the speech plan. Search scores are relevance signals for catalog
inspection endpoints, not Goal Interpretation execution authorization.

`POST /agent-skills/disclose` accepts a previously validated selection and loads
only its exact matching role projections. The Loader rechecks package content,
applies per-projection/aggregate/count budgets, omits rather than truncates
oversized content, and returns typed failures plus a disclosure digest. The five
maintained model endpoints perform this selection/disclosure automatically;
caller-supplied disclosure context is removed before trusted injection.

### Conversation and interaction

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/run` | Established `AgentRequest -> AgentResult` compatibility path. CapabilityAgent semantic planning is emergency-only; exact Goal Interpretation actions are adapter input. |
| `POST` | `/interaction` | Return a natively accumulated and strictly revalidated shared `InteractionResponse`; exact Goal Interpretation actions are materialized without LLM reinterpretation, and the legacy CapabilityAgent planner requires explicit emergency authority. |
| `POST` | `/task-continuity` | Return a validated `SemanticTaskOperationSet` proposal for the current utterance and active-task snapshot. |
| `POST` | `/agent-skills/select` | Return a typed optional method selection authored for the declared Agent role from bounded approved summaries. |
| `POST` | `/agent-skills/disclose` | Return exact bounded role projections from one validated selection without Plan mutation or execution. |
| `POST` | `/compose-response-plan` | Compose goal-scoped speech and optional auxiliary social attention around an immutable terminal `CanonicalPlan`. |
| `POST` | `/tools/execute` | Trusted execution boundary for exact local safe-read capability requests already selected by the Goal-driven planner. |
| `POST` | `/tool-result/interpret` | Interpret complete bounded tool evidence for the user request without exposing the raw payload. |

The interaction, goal-association, and task-continuity endpoints accept the same request shape:

- `sid`
- `text`
- `route_decision`
- optional `language`
- `context`
- `history`

`POST /fast-plan` is available only when `AGENT_FAST_PLANNER_ENABLED=1` and Agent LLM use is enabled. It returns the shared `CanonicalPlan` contract. Ollama itself receives an exact flat semantic DTO schema; the host adds `schema_version`, `plan_id`, `planner_tier`, and the authoritative Goal Association IDs after model validation. The Fast Planner may return a complete simple response, a complete direct common-capability plan, or an escalation. Partial or uncertain coverage is contractually required to contain zero executable steps. The endpoint never executes by itself; the host uses it inside unified `report_only` observation or authoritative `apply`, where the trusted runtime revalidates every terminal plan.

Executable identity is canonicalized as `capability_id` in new planner schemas,
Canonical Plan steps, Interaction Capability requests/results/traces, and
execution evidence. Declared compatibility readers accept historical
`skill_id`, normalize it immediately, and reject a payload containing
contradictory dual fields. New serializers do not emit executable `skill_id`.
The existing `skills` collection name in `InteractionResponse` is a bounded
transport compatibility surface; each contained request is a canonical
`CapabilityRequest`.

Planner responses also expose `CanonicalPlan.selected_agent_skills`. Each item is
a content-free provenance record containing the exact selection/disclosure IDs,
selecting planner role, Agent Skill ID/version, package/projection/disclosure
digests, explicit relevant Goal IDs, rationale, and confidence. Fast Plans may
contain only Fast Planner provenance. Deep Plans preserve ordered Fast Planner
provenance from the advisory Plan and append Deep Planner provenance. This field
is included in Plan fingerprints and replay serialization but is ignored by
Capability authorization and execution.

`POST /deep-plan` is available when `AGENT_DEEP_PLANNER_ENABLED=1`. It receives the original turn, active-goal context, Goal Association advisory, Fast Planner escalation, and the full capability catalog. It returns the same `CanonicalPlan` contract with `planner_tier=deep`. Deep planning is terminal: it may execute, respond, clarify, report unavailable, or refuse, but cannot return to Fast Planner. Complete multi-goal model output uses `goal_outcomes` as an exact object keyed once by every authoritative Goal ID; the host materializes the canonical outcome list in authoritative order. Per-goal and aggregate satisfaction are prospective plan-adequacy assessments, not execution evidence. A supplied low per-goal score remains authoritative; runtime validation does not invent a missing duplicate per-goal score when the exact keyed outcomes and aggregate judgment already establish coverage. `spoken_response` Goals must use a response outcome containing the requested authored content and cannot own executable transport steps. Parallel timing is accepted only from provider catalog entries that explicitly declare compatible parallel safety and resources. Otherwise the planner must fail closed or author a typed `safe_adjustment`/`alternative`; `plan_relation` and `user_confirmation_required` enforce user confirmation before the host transfers that judgment to canonical metadata. Deterministic validation feedback may trigger at most `AGENT_DEEP_PLANNER_MAX_REPLANS` same-tier revisions.

`POST /compose-response-plan` is available when `AGENT_RESPONSE_COMPOSER_ENABLED=1`. It requires a terminal `CanonicalPlan` in request context and returns `ResponseCompositionResolution`. Ollama receives the exact `ResponseComposerModelOutput` schema: a `ResponsePlan`, optional `SocialAttentionPlan`, confidence, and rationale, with response-stage Goal IDs constrained to the immutable plan. The host constructs composition identity, embeds the immutable plan and its SHA-256 fingerprint, requires every plan goal to be covered by response stages, and forbids pre-execution completion claims. One invalid schema result may receive a bounded same-stage repair using the original JSON and exact validation errors; a second invalid result fails closed. Social attention is independently validated against exact capability IDs, schemas, target evidence, confirmation policy, and primary-plan resource conflicts; invalid optional behavior is dropped without changing speech or task planning. The unified host invokes this stage in both observation and authoritative apply; composition failure fails closed after authority acquisition.

`POST /tools/execute` is a trusted provider boundary, not a semantic router. It accepts an exact `capability_id` and schema-valid arguments already produced by the Goal-driven planner. The Agent rejects unknown, unavailable, non-local, side-effecting, confirmation-gated, or non-`safe_read` capabilities and returns structured output without composing user speech. The Trusted Capability Runtime (legacy code name: Skill Runtime) remains responsible for provider registration, input validation, timing, cancellation, and correlated execution evidence. The first maintained binding is `chromie.weather.lookup`; additional local tools require an explicit manifest declaration and trusted provider binding rather than phrase rules.

`POST /tool-result/interpret` is available when `AGENT_TOOL_RESULT_INTERPRETER_ENABLED=1`. It accepts the original user request plus one or more complete bounded `ToolResultEvidence` objects. The model returns a direct, summary, or detailed spoken response and exact evidence-ID/JSON-Pointer fact references. Trusted validation rejects stale or collection-valued references, unsupported numeric claims, internal identifiers, raw-payload narration, and speech outside the selected budgets. The full tool result remains in the execution bundle or Agent metadata; only the validated synthesis is spoken.

`POST /goal-association` is available only when
`AGENT_GOAL_ASSOCIATION_ENABLED=1` and Agent LLM use is enabled. It applies
continuity before creation: each semantic responsibility may associate with
existing active goals, become an independent new goal, or produce one natural
clarification when the reference is ambiguous. Existing goal IDs must be copied
from the supplied active-goal snapshots; unknown or below-threshold associations
are rejected. Every new Goal also declares five typed completion facts.
`responsibility_kind` is `executable_action`, `spoken_response`,
`capability_dependent`, or `other`; `execution_lane` is `speaking`, `activity`,
or `none`; `output_mode` distinguishes ordinary speech, expressive speech,
recitation, singing, humming, nonverbal vocalization, body action, media
playback, capability work, or other; `provider_required` says whether an
exact registered Capability Provider beyond ordinary authored speech delivery
must return completion evidence; and `media_operation` is one exact persistent
playback operation for `media_playback` or `none` for every other output mode.
The live decoder schema requires all five fields, while retained legacy DTOs
receive only a bounded compatibility mapping.
Mode-specific vocal output remains Speaking but requires provider evidence; a
generic `respond` outcome or ordinary TTS cannot close it. The eventual spoken
delivery of a capability result remains part of that capability-dependent Goal
rather than becoming a duplicate response Goal. The endpoint itself does not mutate task state,
authorize side effects, alter Cognitive Core interpretation output, or execute plans. The unified host uses its result
in `report_only` observation or authoritative `apply`, and only the host may
atomically commit the validated association.

`POST /task-continuity` is available only when
`AGENT_TASK_CONTINUITY_ENABLED=1` and Agent LLM use is enabled. It treats the
Goal Interpretation decision as advisory context, replaces model-provided operation IDs with
stable request-bound IDs, rejects below-threshold or unknown-task operations,
and may return an immediate `ResponsePlan`. It never applies task changes,
authorizes side effects, or claims execution. The host decides whether to call
it in `off`, `report_only`, or `apply` mode and remains the authority for task
versions, confirmation validity, commitment, scheduling, and evidence.

The host context now includes compact prompt-memory fields:
`session_memory.memory_summary`, `session_memory.extracted_memory`, and
top-level `extracted_memory`. These are process-local session/task memory
summaries, not durable user-profile memory and not authorization for side
effects. Fast Goal Interpretation prompts sanitize raw `history` and `conversation` fields
from their bounded context payload and rely on these compact memory fields
instead.
For explicit `memory` routes, Goal Interpretation must return a typed
`memory_update` proposal. `memory_agent` validates and applies that exact model
decision, emits an `extracted_memory` entry plus a bounded compatibility
`user_statement` derived from it, and clarifies when the proposal is missing.
It never infers memory semantics from raw text. The Orchestrator consumes only
the refined entry into prompt-facing session memory.

`InteractionResponse` can contain speech items and executable Capability requests; the `skills` container name remains a bounded compatibility surface. Shared
contracts reject unknown fields and recursively reject low-level motor, joint,
torque, and actuator fields. Native mode is the Agent default. The response
metadata includes `interaction_output_mode` (`native`, `legacy-adapter`, or
`legacy-fallback`) for operator diagnostics. When `AGENT_SOCIAL_ATTENTION_MODE` allows it, the runtime may attach an
advisory model-authored `social_attention_plan`. The plan identifies the
`social_attention` behavior domain, the `auxiliary_expression` role, a social
purpose, optional speech style/pacing adaptation, and zero or more model-selected
catalog behaviors. Response Composer coordinates the actual response text with
this plan; the native compatibility planner remains body-only. Applied skills
carry `metadata.source=social_attention_plan`,
`metadata.auxiliary_social_attention=true`, and purpose/function metadata; they
are excluded from user task proposals. Runtime validation checks exact catalog
membership, schemas, target evidence, resource conflicts, confirmation policy,
and a bounded latency budget. Target evidence is semantic only; installation calibration and body-specific
coordinates are never part of the Chromie planning contract. Concrete user-requested actions remain primary
CanonicalPlan goals and cannot be replaced by auxiliary expression. Body and tool requests are routed through the model-assisted
Goal Interpretation, capability catalog, Agent capability planner, schemas, and Trusted Capability
Runtime validation rather than hidden phrase parsers. Plain walking requests
use a normal safe forward speed of `0.18 m/s`;
requested forward speeds above Soridormi's current runtime limit of `0.20 m/s`
are normalized back to the normal speed and surfaced through `speak_first`.
Requests to joke, recite, or otherwise author speech while walking use a
`spoken_response` Goal coordinated with the walking step; `chromie.speak` is a
Response Composer transport and is never a planner step. A request to sing still
belongs to the Speaking lane, but it may be claimed as singing only when a
registered vocal-performance capability can provide that evidence. The planner
must otherwise report the limitation or propose an explicit alternative rather
than substituting a body action or ordinary TTS. The same motion safety
normalization still applies to the walking step. When
native speech metadata includes `wait_for_playback_start=true`, the host speech
provider completes that speech request only after playback has started or the
configured wait times out; this lets the following sequential body skill begin
with audible speech instead of merely queued TTS.

### Exact vocal-performance provider contract

`chromie.vocal.perform` is the single public Capability identity for qualified
provider-backed vocal performance. Backend identity is trusted runtime
metadata; it is not copied into semantic Goals and does not replace the public
Capability ID during proposal, validation, authorization, execution,
cancellation, or evidence collection.

The request schema requires authored `text` and one exact `mode` from
`speech`, `expressive_speech`, `recitation`, `singing`, `humming`, or
`nonverbal_vocalization`. A qualified provider declaration names its supported
modes, text/audio streaming support, request-cancellation support, timing-mark
types, sample formats and rates, concurrency limit, immutable software/model
provenance, and retained evidence for every advertised mode. The default Agent
catalog retains this contract as unavailable and advertises no supported modes;
only a declaration with mode-specific evidence makes it planner-visible.

The Trusted Capability Runtime rejects an unsupported requested mode with the
correlated `vocal_mode_unavailable` outcome before invoking the backend. A
completed result requires the delivered mode to equal the requested mode,
completed playback evidence, a declared sample format and rate, and no
undeclared timing marks. A mode mismatch or malformed delivery evidence fails
as `invalid_vocal_delivery_evidence`; it is never repaired into ordinary TTS or
another vocal mode. Cancellation retains the original request identity. These
results prove only the evidence level and artifacts recorded by the provider
declaration. Source-test evidence from a fake provider is not singing, speaker,
or physical-audio target evidence.

### Exact peer-media provider contract

Existing music, recordings, streams, and sound effects use seven stable public
Activity capabilities: `chromie.media.play`, `chromie.media.pause`,
`chromie.media.resume`, `chromie.media.seek`, `chromie.media.stop`,
`chromie.media.volume`, and `chromie.media.status`. Backend identity remains
trusted runtime metadata and never replaces these IDs in a Goal, Plan, request,
result, or retained trace. The default catalog keeps every operation visible but
unavailable until a qualified peer provider declares exact supported operations,
media kinds, persistent-state and progress support, request cancellation,
concurrency, mixer parameters, immutable provenance, and retained evidence for
every advertised operation.

`play` accepts only a provider-declared media kind plus a provider-neutral media
reference and optional start position or volume. Lifecycle controls require the
persistent `playback_id`; `seek` and `volume` add their exact value. Completed
results preserve the requested operation and public capability ID, playback
identity and state, bounded position/duration/volume, delivery evidence ID,
evidence level, and declared mixer policy. A different operation, incompatible
state, undeclared media kind, or malformed progress fails as
`invalid_media_lifecycle_evidence`; an unsupported input kind is rejected before
backend invocation.

Speech may overlap media only through an explicit `LaneCoordinationGroup`. The
Host then materializes the provider declaration's
`duck_media_during_speaking` gain, attack, and release values onto both the
Speaking item and media request without changing either Goal. Deterministic
`output_only`, `media_output`, and `current_interaction` scopes respectively
mean stop talking, stop media across retained interactions, and stop all work in
the foreground interaction. Their cancellation receipts retain exact selected
request identities and provider/dispatch failures; a receipt is not audible
silence or provider-safe-state proof.

### TaskGraph validation and execution

| Method | Path | Gate or authorization | Purpose |
|---|---|---|---|
| `POST` | `/task-graphs/validate` | Always available | Validate graph structure and active capability policy. |
| `POST` | `/task-graphs/dry-run` | Diagnostics bearer token | Produce a deterministic trace without remote calls. |
| `POST` | `/task-graphs/execute-read-only` | `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1` | Execute preflight-approved side-effect-free work. |
| `POST` | `/task-graphs/execute-planning` | `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1` | Execute safe reads and stateful `planning_only` tools. |
| `POST` | `/task-graphs/confirmation-grants` | Guarded execution enabled plus bearer token | Issue a short-lived, single-use grant bound to a graph and confirmation nodes. |
| `POST` | `/task-graphs/execute-guarded` | Guarded execution enabled plus bearer token | Execute authorized side effects; physical motion also requires its separate gate and monitor proofs. |
| `POST` | `/task-graphs/{graph_id}/cancel` | Guarded execution bearer token | Cancel an active graph or reserve a bounded cancel-before-start tombstone for a not-yet-arrived execute request. |
| `GET` | `/task-graphs/{graph_id}/trace` | Diagnostics bearer token | Return the latest non-expired in-memory retained trace. |
| `GET` | `/task-graphs/scheduler/status` | Diagnostics bearer token | Return scheduler mode, active/waiting counters, and active graph IDs. |

Bearer format:

```text
Authorization: Bearer <AGENT_TASK_GRAPH_EXECUTION_TOKEN>
```

Dry-run, trace, and scheduler requests use
`AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN`. When that variable is blank, the Agent
falls back to `AGENT_TASK_GRAPH_EXECUTION_TOKEN`; when both are blank, the
diagnostic endpoints return 503. Invalid or missing credentials return 401.

`graph_id` is also the cancellation-path identity. It must contain 1–128
URL-path-safe letters, digits, periods, underscores, colons, or hyphens. If a
cancel request wins the transport race against execution registration, the
Agent retains a capacity- and TTL-bounded tombstone and returns a cancelled
trace when that graph arrives, without calling its provider. A graph with an
already-retained terminal trace returns `cancellation_requested=false`.
Read-only or planning execution retries with the same retained `graph_id`,
exact graph fingerprint, and execution lane return the retained trace without
invoking providers. Guarded retries must also present a fresh valid
graph-bound grant. Reusing the ID for different graph content or a different
successful execution lane is rejected until retention expires. Dry-run traces
are diagnostics only: they neither satisfy execution replay nor prevent a
later cancellation tombstone.

TaskGraph execution responses return an `ExecutionTrace`. Its `summary` remains
the planner-provided task summary, while `outcome_summary` is generated
deterministically from node results. Failed Soridormi task nodes preserve
`reason_code`, `blocked_subsystems`, and `recommended_next_actions` in that
summary so user-facing report/speech code does not need to infer the refusal.
Planning execution can run `chromie.report` as a trace-only local report node;
it does not play audio. `chromie.speak` remains rejected from planning
execution and should be emitted through `InteractionResponse`/Trusted Capability Runtime when
audible playback is required.
When native `POST /interaction` emits `chromie.task_graph.execute`, the host
Trusted Capability Runtime can route that request to `POST /task-graphs/execute-planning`.
The Agent-side planning execution flag still controls whether the graph runs;
disabled planning execution returns a safe failure instead of falling back to
raw control or guarded execution. Failed, aborted, or cancelled graph traces are
reported back as non-completed capability results so `after_skills` speech is not
played as if the task succeeded.
TaskGraph `$ref` arguments may read `<node>.output[.<field>]`, `<node>.error`,
or `<node>.status`; LLM-planned Soridormi task-submit nodes that omit a failure
fallback are normalized with a trace-only report fallback that reads
`<submit_node>.error`.

Traces and grants are process-memory state; they are not durable across Agent
restarts. Traces use configurable TTL/LRU retention (defaults: 900 seconds and
128 entries). Unconsumed grants are capped at 128 entries by default and expired
entries are purged before issue or consume.

## Hardware compatibility HTTP API — port 8095

This is the legacy mock-action daemon, not the Soridormi robot boundary.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return mock driver and robot state. |
| `GET` | `/state` | Return current mock robot state. |
| `POST` | `/actions` | Execute a namespaced compatibility action. |
| `GET` | `/actions/{action_id}` | Return an in-memory action result. |
| `POST` | `/emergency_stop` | Set mock emergency-stop state. |
| `POST` | `/reset_emergency_stop` | Clear mock emergency-stop state. |

The daemon rejects `unsafe.*` actions and actions that still require
confirmation. In this revision it always constructs `MockRobotDriver`; serial
configuration variables do not select a production backend.

## ASR WebSocket protocol — port 9001

The ASR service accepts WebSocket connections and two message forms:

- JSON text `{"type":"health"}` or `{"type":"ping"}` ->
  `{"type":"pong","service":"asr",...}` with backend, mode, model revision,
  and bounded-concurrency metadata.
- Binary PCM16 mono audio at `ASR_SAMPLE_RATE` -> one JSON final result:
  `{"type":"final","text":"...","duration":<seconds>}`.

Failures return `{"type":"error","message":"..."}`. The host Orchestrator
performs VAD and sends complete utterance audio; this service does not stream
partial transcripts. Blocking final-backend inference runs in a bounded
executor, so health/ping handling remains responsive while a transcription is
active. The current supported backend and mode are `sherpa_onnx` and `final`. The pong reports `backend`, `mode`, `model`, `model_revision`, and
`max_concurrent_transcriptions`.

## TTS WebSocket protocol — default port 5000

The maintained endpoint on port `5000` is Fun-CosyVoice3 0.5B. Explicit
alternatives use port `5001` for OuteTTS and port `5002` for Qwen3-TTS. All
three expose the same provider contract for health and synthesis.

Supported default-provider JSON messages:

| Request type | Result |
|---|---|
| `health` or `ping` | `pong` with provider contract/declaration, immutable model identity, sample rate, worker readiness, cancellation counters, and `speakers=["default"]`. |
| `list_speakers` | `speakers` with the installed cloned-reference identity. |
| `synthesize_stream` | `start`, binary PCM16 chunks, then `end`; or `error`. |

A synthesis request includes `text`, optional `speaker_id`, optional
`language_hint`, and optional `request_id`. The `start` message declares
`sample_rate`, `format=pcm_s16le`, `channels=1`, and a versioned `provider`
object. The terminal `end` repeats the provider declaration and includes audio
duration, comparable timing, and provider metadata.

The provider object includes contract version, provider ID, implementation,
software/model provenance and declared licenses, languages, rates, maximum
concurrency, native streaming, cancellation, speaker-profile, and voice-cloning
capabilities. These are capability declarations, not quality or legal approval.

The default CosyVoice provider consumes a host-installed authorized reference:

```bash
python scripts/tts_reference.py install \
  --source-wav /path/to/reference.wav \
  --transcript '录音中的逐字文本' \
  --license-id 'user-owned-recording'
```

It does not expose network `create_speaker`. The optional Oute fallback retains
that legacy operation on port `5001` for Oute v3 profiles; its success response
includes transcript-alignment and DAC acoustic-coverage diagnostics.

CosyVoice emits native streamed audio but currently accepts one complete text
request rather than incremental model tokens. Cancellation first attempts a
bounded drain while holding the singleton worker lock; if synchronous inference
does not finish, Chromie restarts the worker before accepting another request.
Health reports drain/restart evidence.

The host Orchestrator may split one logical speech response into multiple
ordered requests, resample provider output, serialize playback, and invalidate
late chunks after interruption. Startup-cached acknowledgements are bound to
provider/model/reference identity and pass duration plus ASR content gates
before playback.

## Soridormi contract snapshot

`capabilities/soridormi.json` contains 27 tools grouped under seven external
agents:

- robot status, mode, and battery reads;
- motion plan creation, execution, stop, and cancellation;
- named-skill catalog, plan creation, and execution;
- resource-aware body-activity capability discovery, compilation, execution,
  compatibility aliases, status, and cancellation;
- read-only Soridormi task capability readiness;
- no-motion embodied task preview with non-persistent `preview_id`;
- no-motion embodied task submit, status, events, cancellation, lifecycle phase
  reporting, skill-dry-run metadata, `skill_sequence` dry-run step metadata,
  embodied `plan_steps`/`blocked_subsystems`, and
  `recommended_next_actions`;
- motion monitoring and emergency stop.

The live endpoint URL is supplied by `${SORIDORMI_MCP_URL}`. Probe the endpoint
against the manifest before enabling execution; the checked-in JSON is not proof
that the currently running server has the same schema.
