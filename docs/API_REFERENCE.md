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
Agent-owned shared capability catalog, sends bounded context and candidates to
the quick intent Router model when enabled, and delegates low-confidence or
explicitly complex quick routes to `deep_thought`. Normal robot, tool, memory,
conversation, and deep-thought intent is not selected by phrase rules.
`RouteDecision.candidate_capabilities` preserves the ranked evidence for the
native interaction path.

Router also attaches staged task metadata:

- `metadata.route_stage_outputs`: one entry per route stage that contributed or
  passed, each with proposed `tasks` and `actions`;
- `metadata.task_list`: the merged priority/stage ordered task list.

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
and Skill Runtime/provider authorization.
The host Orchestrator owns the final task context write, persistence policy,
confirmation, cancellation, and safety state.

The Router exposes three conceptual stages:

| Stage | Routes | LLM use |
|---|---|---|
| `emergency_filter` | `interrupt`, `ignore` | Never |
| `quick_intent` | `chat`, `deep_thought`, `robot_action`, `tool`, `memory`, `clarify` | Optional when Router mode is `hybrid` or `llm_only` |
| `deep_thought` | `deep_thought` | Handled by Agent after routing |

## Agent HTTP API — port 8092

FastAPI also exposes its generated OpenAPI UI at `/docs` while the service is
running.

### Runtime and capability inspection

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return model/runtime state, loaded capability sources, feature gates, and scheduler counters. |
| `GET` | `/agents` | List specialized agents and ownership notes. |
| `GET` | `/capabilities` | Return the active merged static capability registry and manifest sources. |
| `GET` | `/capabilities/catalog` | Return the shared catalog, including last-known live named skills and refresh status. |
| `POST` | `/capabilities/search` | Rank relevant capabilities for Router and normal InteractionRuntime. |
| `GET` | `/capabilities/llm-context?language=en&text=...` | Return concise full-catalog or query-specific LLM context. |

### Conversation and interaction

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/run` | Established `AgentRequest -> AgentResult` compatibility path. |
| `POST` | `/interaction` | Return a natively accumulated and strictly revalidated shared `InteractionResponse`; explicit adapter rollback remains configurable. |

Both endpoints currently accept the same request shape:

- `sid`
- `text`
- `route_decision`
- optional `language`
- `context`
- `history`

`InteractionResponse` can contain speech items and named skill requests. Shared
contracts reject unknown fields and recursively reject low-level motor, joint,
torque, and actuator fields. Native mode is the Agent default. The response
metadata includes `interaction_output_mode` (`native`, `legacy-adapter`, or
`legacy-fallback`) for operator diagnostics. When `AGENT_EXPRESSIVE_BODY_CUES`
allows it, chat-only speech may include a parallel expressive skill such as
`soridormi.express_attention`; confirmation and simulator/physical safety gates
still apply. Body and tool requests are routed through the model-assisted
Router, capability catalog, Agent capability planner, schemas, and Skill
Runtime validation rather than hidden phrase parsers. Plain walking requests
use a normal safe forward speed of `0.18 m/s`;
requested forward speeds above Soridormi's current runtime limit of `0.20 m/s`
are normalized back to the normal speed and surfaced through `speak_first`.
Requests to sing while walking are represented as a `speak_first` utterance plus
the walking skill, so the same motion safety normalization still applies. When
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
active. The current supported backend and mode are `faster_whisper` and
`final`. The pong reports `backend`, `mode`, `model`, `model_revision`, and
`max_concurrent_transcriptions`.

## TTS WebSocket protocol — port 5000

Supported JSON text messages:

| Request type | Result |
|---|---|
| `health` or `ping` | `pong` with sample rate, GPU-layer setting, generation limits, and available speakers. |
| `list_speakers` | `speakers` with speaker IDs. |
| `create_speaker` | `speaker_created` or `error`; the WAV path must remain inside `SPEAKER_DIR`. |
| `synthesize_stream` | `start`, binary PCM16 chunks, then `end`; or `error`. |

A synthesis request includes `text`, optional `speaker_id`, and optional
`request_id`. The `start` message declares `sample_rate`, `format=pcm_s16le`,
and `channels=1`.

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
