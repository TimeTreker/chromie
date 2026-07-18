# API and Protocol Reference

This document describes interfaces implemented in this repository. Soridormi
is a separate deployment; only its checked-in capability contract is summarized
here. Current revision and verification status are maintained in
[STATUS.md](STATUS.md).

## Router HTTP API — port 8091

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return Router mode, model, Ollama URL, and rule-order state. |
| `GET` | `/routes` | List route names, routing stages, active mode, and known Agent names. |
| `POST` | `/route` | Convert text and session context into a validated `RouteDecision`. |

`POST /route` accepts `sid`, `text`, optional `language`, and a free-form
`context` object. Route names are `chat`, `deep_thought`, `robot_action`,
`tool`, `memory`, `clarify`, `interrupt`, and `ignore`.

Interrupt and ignore decisions are normalized deterministically: they do not
require the Agent and they do not speak. For other input, Router queries the
Agent-owned shared capability catalog snapshot, sends bounded context and the
unlocked common ability catalog to the quick intent Router model when enabled,
and delegates low-confidence or explicitly complex quick routes to
`deep_thought`. Normal robot, tool, memory, conversation, and deep-thought
intent is not selected by phrase rules.
Per-query catalog search matches are not part of the fast Router decision
surface.

Router also attaches staged task metadata:

- `routes`: optional preferred multi-route items for one utterance; each item
  has its own `route`, `intent`, `confidence`, `lane`, `context_profile`,
  optional `requires_mind`, optional `direct_to_tts`, and optional `text`,
  `skill_id`, `args`, or `actions`;
- `metadata.route_items`: JSON mirror of `routes[]` for older callers and
  trace tools;
- `metadata.route_stage_outputs`: one entry per route stage that contributed or
  passed, each with legacy proposed `tasks`/`actions` and shared
  `task_proposals`;
- `metadata.desired_abilities`: optional non-executable ability proposals when
  the Router understands a broad human-like ability that is not safely
  represented by the current common executable catalog;
- `metadata.task_list`: the legacy merged priority/stage ordered task list;
- `metadata.task_proposals`: the preferred shared-schema merged task proposal
  list, including `state=missing_ability` entries derived from desired
  abilities;
- `metadata.route_merge`: the concise merge ledger, including merge strategy,
  final route/intent/source, selected stage, proposal count, task count,
  task-proposal count, and task source stages.

For conversation continuity, the quick Router model may also attach advisory
task-lifecycle metadata:

- `metadata.task_relation`: `new_task`, `continue_task`, `modify_task`,
  `close_task`, `side_conversation`, or `clarify_task`;
- `metadata.target_task_id`: the task context the utterance appears to refer
  to, when known from bounded context;
- `metadata.task_context_patch`: compact fields such as goal, task type,
  important claims, entities, constraints, pending questions, status, and
  persistence policy.

This metadata is advisory planning state. Concrete skill execution still uses
validated `RouteDecision.actions`, Agent-selected `InteractionResponse.skills`,
and Skill Runtime/provider authorization. When the quick Router model can
represent a mixed utterance, `RouteDecision.routes[]` is the preferred
multi-route surface. Route-item lanes include `immediate_speech`,
`conversation`, `post_turn`, `deepthought`, `skill_runtime`, `tool`,
`deterministic_control`, and `none`. Context profiles include `none`,
`fast_minimal`, `session_compact`, `capability_safety`, and `full_mind`.
Only short safe chat items may set `direct_to_tts=true`, but that compatibility
marker alone cannot schedule audio. Playback additionally requires the
default-off Router-generated FastSpeech gate and its validated structured
contract, or an independent trusted host response-plan/cache path, while other
items continue through Agent, memory, deepthought, tool, or Skill Runtime
policy.

Both a top-level `RouteDecision` and an individual `RouteItem` may include
`fast_speech`. A bare string or partial object remains parseable for wire
compatibility, and top-level `fast_speech.text` may still populate the
compatibility `speak_first` field. Neither form is playback authority. Dynamic
Router-authored playback is default-off behind
`ORCH_ROUTER_GENERATED_FAST_SPEECH_ENABLED=0`; when explicitly enabled it still
requires a structured object with safe `text`, an allowed process `purpose`, a
non-terminal `commitment`, and `must_not_claim_completion=true`. It must not
claim a result, memory write, physical execution, or final answer. Contract
markers such as `thinking` or `checking_only` are not spoken as literal text.
Validated `metadata.response_plan` immediate speech and startup-cached host cues
are separate trusted paths and do not require this compatibility gate.

For ordered listed-skill work inside a robot-action route item,
`RouteDecision.actions` may still contain an ordered list of skill proposals.
The fast Router receives `common_ability_catalog` and `common_ability_ids` as
the small-model executable menu.
Each action uses an exact `capability_id` from that common menu,
schema-shaped `args`, optional `sequence`, and optional `timing`, plus a
0.0-1.0 `confidence` for that specific skill choice and arguments. Speech that
belongs inside a physical task is represented as the `chromie.speak` skill with
`args.text`, not as unstructured final text. If any required compound action is
below the Router confidence threshold, or if the fast Router selects a
rare/full-catalog skill outside `common_ability_ids`, the Router delegates the
whole plan to `deep_thought` rather than executing only the high-confidence or
rare subset. The delegated
`RouteDecision.metadata` includes
`quick_router_review_request` with the quick actions, legacy task list, shared
task proposals, and `execution_state=not_committed` so deepthinking can
`accept`, `revise`, or `supersede` the quick plan.
If the quick Router understands an unsupported body/social/manipulation goal,
it must not put that goal in `RouteDecision.actions`. It should delegate or
clarify and may record `metadata.desired_abilities[]` with `ability_id`,
`intent`, `status=missing_ability`, `confidence`, and `reason`.
The host Orchestrator owns the final task context write, persistence policy,
confirmation, cancellation, and safety state.

The Router exposes four conceptual stages plus deterministic validation:

| Stage | Routes | LLM use |
|---|---|---|
| `emergency_filter` | `interrupt`, `ignore` | Never |
| `post_interrupt_review` | `chat`, `deep_thought`, `robot_action`, `tool`, `memory`, `clarify`, `interrupt`, `ignore` | Optional after an interrupt has already been applied |
| `quick_intent` | `chat`, `deep_thought`, `robot_action`, `tool`, `memory`, `clarify` | Optional when Router mode is `hybrid` or `llm_only` |
| `route_validation` | `chat`, `deep_thought`, `robot_action`, `tool`, `memory`, `clarify` | Never |
| `deep_thought` | `deep_thought` | Handled by Agent after routing |

## Agent HTTP API — port 8092

FastAPI also exposes its generated OpenAPI UI at `/docs` while the service is
running.

### Runtime and capability inspection

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return model/runtime state, loaded capability sources, feature gates, scheduler counters, and the legacy CapabilityAgent emergency gate. |
| `GET` | `/semantic-authority` | Return the machine-readable single-authority route matrix and current Agent emergency-fallback gate. |
| `GET` | `/agents` | List specialized agents and ownership notes. |
| `GET` | `/capabilities` | Return the active merged static capability registry and manifest sources. |
| `GET` | `/capabilities/catalog` | Return the shared catalog, including last-known live named skills and refresh status. |
| `POST` | `/capabilities/search` | Rank relevant capabilities for Router and normal InteractionRuntime. |
| `GET` | `/capabilities/llm-context?language=en&text=...` | Return concise full-catalog or query-specific LLM context. |
| `POST` | `/goal-association` | Resolve continuity-before-creation and independent Goal segmentation for the unified runtime; the endpoint itself does not mutate host state. |
| `POST` | `/fast-plan` | Produce a complete common-catalog `CanonicalPlan` or terminal Deep Planner escalation. |
| `POST` | `/deep-plan` | Produce a terminal full-catalog `CanonicalPlan`, including bounded same-tier revision. |
| `POST` | `/compose-response-plan` | Bind goal-scoped speech and optional auxiliary attention to an immutable terminal plan. |

Catalog entries include `prompt_tier=common|rare`, plus
`prompt_tier_locked`, `prompt_tier_source`, and `prompt_tier_reason`. The
Router uses unlocked `common` entries for the fast compact Qwen prompt as
`common_ability_catalog`; deepthinking may use the full catalog. Safety-locked
entries remain visible in the full catalog but are excluded from the fast
common prompt even when an experience overlay requests `common`. The initial
preset is data in `capabilities/prompt_tiers.json`, not a Python skill list.
`chromie.speak` remains common and interaction-executable for legacy/native
`InteractionResponse` compatibility, but the Goal-driven Fast and Deep Planner
schemas exclude it as response transport. A mixed conversational/body turn uses
a goal-scoped `respond` outcome plus executable body steps; the Response
Composer owns the speech plan. Search scores are relevance signals for catalog
inspection endpoints, not Router execution authorization.

### Conversation and interaction

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/run` | Established `AgentRequest -> AgentResult` compatibility path. CapabilityAgent semantic planning is emergency-only; exact Router actions are adapter input. |
| `POST` | `/interaction` | Return a natively accumulated and strictly revalidated shared `InteractionResponse`; exact Router actions are materialized without LLM reinterpretation, and the legacy CapabilityAgent planner requires explicit emergency authority. |
| `POST` | `/task-continuity` | Return a validated `SemanticTaskOperationSet` proposal for the current utterance and active-task snapshot. |
| `POST` | `/compose-response-plan` | Compose goal-scoped speech and optional auxiliary social attention around an immutable terminal `CanonicalPlan`. |

The interaction, goal-association, and task-continuity endpoints accept the same request shape:

- `sid`
- `text`
- `route_decision`
- optional `language`
- `context`
- `history`

`POST /fast-plan` is available only when `AGENT_FAST_PLANNER_ENABLED=1` and Agent LLM use is enabled. It returns the shared `CanonicalPlan` contract. Ollama itself receives an exact flat semantic DTO schema; the host adds `schema_version`, `plan_id`, `planner_tier`, and the authoritative Goal Association IDs after model validation. The Fast Planner may return a complete simple response, a complete direct common-capability plan, or an escalation. Partial or uncertain coverage is contractually required to contain zero executable steps. The endpoint never executes by itself; the host uses it inside unified `report_only` observation or authoritative `apply`, where the trusted runtime revalidates every terminal plan.

`POST /deep-plan` is available when `AGENT_DEEP_PLANNER_ENABLED=1`. It receives the original turn, active-goal context, Goal Association advisory, Fast Planner escalation, and the full capability catalog. It returns the same `CanonicalPlan` contract with `planner_tier=deep`. Deep planning is terminal: it may execute, respond, clarify, report unavailable, or refuse, but cannot return to Fast Planner. Complete multi-goal model output uses `goal_outcomes` as an exact object keyed once by every authoritative Goal ID; the host materializes the canonical outcome list in authoritative order. Per-goal and aggregate satisfaction are prospective plan-adequacy assessments, not execution evidence. Typed `plan_relation` and `user_confirmation_required` fields enforce confirmation for safe adjustments and alternatives before the host transfers those judgments to canonical metadata. Deterministic validation feedback may trigger at most `AGENT_DEEP_PLANNER_MAX_REPLANS` same-tier revisions.

`POST /compose-response-plan` is available when `AGENT_RESPONSE_COMPOSER_ENABLED=1`. It requires a terminal `CanonicalPlan` in request context and returns `ResponseCompositionResolution`. Ollama receives the exact `ResponseComposerModelOutput` schema: a `ResponsePlan`, optional `SocialAttentionPlan`, confidence, and rationale, with response-stage Goal IDs constrained to the immutable plan. The host constructs composition identity, embeds the immutable plan and its SHA-256 fingerprint, requires every plan goal to be covered by response stages, and forbids pre-execution completion claims. One invalid schema result may receive a bounded same-stage repair using the original JSON and exact validation errors; a second invalid result fails closed. Social attention is independently validated against exact capability IDs, schemas, target evidence, confirmation policy, and primary-plan resource conflicts; invalid optional behavior is dropped without changing speech or task planning. The unified host invokes this stage in both observation and authoritative apply; composition failure fails closed after authority acquisition.

`POST /goal-association` is available only when
`AGENT_GOAL_ASSOCIATION_ENABLED=1` and Agent LLM use is enabled. It applies
continuity before creation: each semantic responsibility may associate with
existing active goals, become an independent new goal, or produce one natural
clarification when the reference is ambiguous. Existing goal IDs must be copied
from the supplied active-goal snapshots; unknown or below-threshold associations
are rejected. The endpoint itself does not mutate task state, authorize side
effects, alter Router output, or execute plans. The unified host uses its result
in `report_only` observation or authoritative `apply`, and only the host may
atomically commit the validated association.

`POST /task-continuity` is available only when
`AGENT_TASK_CONTINUITY_ENABLED=1` and Agent LLM use is enabled. It treats the
Router decision as advisory context, replaces model-provided operation IDs with
stable request-bound IDs, rejects below-threshold or unknown-task operations,
and may return an immediate `ResponsePlan`. It never applies task changes,
authorizes side effects, or claims execution. The host decides whether to call
it in `off`, `report_only`, or `apply` mode and remains the authority for task
versions, confirmation validity, commitment, scheduling, and evidence.

The host context now includes compact prompt-memory fields:
`session_memory.memory_summary`, `session_memory.extracted_memory`, and
top-level `extracted_memory`. These are process-local session/task memory
summaries, not durable user-profile memory and not authorization for side
effects. Quick Router prompts sanitize raw `history` and `conversation` fields
from their bounded context payload and rely on these compact memory fields
instead.
For explicit `memory` routes, `memory_agent` emits an `extracted_memory`
`memory_updates` entry with a scoped compact statement plus the legacy
`user_statement` compatibility entry. The Orchestrator consumes only the
refined entry into prompt-facing session memory.

`InteractionResponse` can contain speech items and named skill requests. Shared
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
and a bounded latency budget. Installation calibration is only a fallback when
live target evidence is absent. Concrete user-requested actions remain primary
CanonicalPlan goals and cannot be replaced by auxiliary expression. Body and tool requests are routed through the model-assisted
Router, capability catalog, Agent capability planner, schemas, and Skill
Runtime validation rather than hidden phrase parsers. Plain walking requests
use a normal safe forward speed of `0.18 m/s`;
requested forward speeds above Soridormi's current runtime limit of `0.20 m/s`
are normalized back to the normal speed and surfaced through `speak_first`.
Requests to sing or joke while walking may be represented as a `chromie.speak`
skill plus the walking skill, so the same motion safety normalization still
applies. When
native speech metadata includes `wait_for_playback_start=true`, the host speech
provider completes that speech request only after playback has started or the
configured wait times out; this lets the following sequential body skill begin
with audible speech instead of merely queued TTS.

### TaskGraph validation and execution

| Method | Path | Gate or authorization | Purpose |
|---|---|---|---|
| `POST` | `/task-graphs/validate` | Always available | Validate graph structure and active capability policy. |
| `POST` | `/task-graphs/dry-run` | Diagnostics bearer token | Produce a deterministic trace without remote calls. |
| `POST` | `/task-graphs/execute-read-only` | `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1` | Execute preflight-approved side-effect-free work. |
| `POST` | `/task-graphs/execute-planning` | `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1` | Execute safe reads and stateful `planning_only` tools. |
| `POST` | `/task-graphs/confirmation-grants` | Guarded execution enabled plus bearer token | Issue a short-lived, single-use grant bound to a graph and confirmation nodes. |
| `POST` | `/task-graphs/execute-guarded` | Guarded execution enabled plus bearer token | Execute authorized side effects; physical motion also requires its separate gate and monitor proofs. |
| `POST` | `/task-graphs/{graph_id}/cancel` | Guarded execution bearer token | Request cancellation of an active graph. |
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

TaskGraph execution responses return an `ExecutionTrace`. Its `summary` remains
the planner-provided task summary, while `outcome_summary` is generated
deterministically from node results. Failed Soridormi task nodes preserve
`reason_code`, `blocked_subsystems`, and `recommended_next_actions` in that
summary so user-facing report/speech code does not need to infer the refusal.
Planning execution can run `chromie.report` as a trace-only local report node;
it does not play audio. `chromie.speak` remains rejected from planning
execution and should be emitted through `InteractionResponse`/Skill Runtime when
audible playback is required.
When native `POST /interaction` emits `chromie.task_graph.execute`, the host
Skill Runtime can route that request to `POST /task-graphs/execute-planning`.
The Agent-side planning execution flag still controls whether the graph runs;
disabled planning execution returns a safe failure instead of falling back to
raw control or guarded execution. Failed, aborted, or cancelled graph traces are
reported back as non-completed skill results so `after_skills` speech is not
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

## TTS WebSocket protocol — port 5000

Supported JSON text messages:

| Request type | Result |
|---|---|
| `health` or `ping` | `pong` with sample rate, GPU-layer setting, resolved/actual DAC device, generation profile, recent performance summary, worker state, and available speakers. |
| `list_speakers` | `speakers` with speaker IDs. |
| `create_speaker` | `speaker_created` or `error`; the WAV path must remain inside `SPEAKER_DIR`. |
| `synthesize_stream` | `start`, binary PCM16 chunks, then `end`; or `error`. |

A synthesis request includes `text`, optional `speaker_id`, and optional
`request_id`. The `start` message declares `sample_rate`, `format=pcm_s16le`,
`channels=1`, codec device, quantization, context size, and generation limit.
The terminal `end` message includes audio duration plus model-generation, DAC
decode, PCM conversion, worker round-trip, queue delay, total time, and
real-time-factor fields. Older clients may ignore these additive fields.

Each OuteTTS/llama.cpp model worker runs in a restartable child process. The
common/default configuration uses one worker; high-memory GPU profiles may start
more than one worker for bounded parallel synthesis. If an active synthesis is
cancelled because its client disconnects, the owning child is terminated and
re-created. Health responses report worker count, per-worker liveness, restart
count, and cancellation mode.

The host Orchestrator may split one logical speech response into multiple
ordered `synthesize_stream` requests. This lowers time-to-first-audio and lets
later chunks generate while earlier chunks are played, while preserving audible
order at the playback layer.

## Soridormi contract snapshot

`capabilities/soridormi.json` contains 20 tools grouped under six external
agents:

- robot status, mode, and battery reads;
- motion plan creation, execution, stop, and cancellation;
- named-skill catalog, plan creation, and execution;
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
