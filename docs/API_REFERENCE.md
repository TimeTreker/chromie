# API and Protocol Reference

This document describes interfaces implemented in this repository. Soridormi
is a separate deployment; only its checked-in capability contract is summarized
here. Current revision and verification status are maintained in
[STATUS.md](STATUS.md).

## Router HTTP API — port 8091

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return Router mode, model, Ollama URL, and rule-order state. |
| `GET` | `/routes` | List route names and known Agent names. |
| `POST` | `/route` | Convert text and session context into a validated `RouteDecision`. |

`POST /route` accepts `sid`, `text`, optional `language`, and a free-form
`context` object. Route names are `chat`, `robot_action`, `tool`, `memory`,
`clarify`, `interrupt`, and `ignore`.

Interrupt and ignore decisions are normalized deterministically: they do not
require the Agent and they do not speak. For other input, Router queries the
Agent-owned shared capability catalog before optional legacy rules or LLM
routing. `RouteDecision.candidate_capabilities` preserves the ranked evidence
for the native interaction path.

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
`legacy-fallback`) for operator diagnostics.

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
  `{"type":"pong","service":"asr"}`.
- Binary PCM16 mono audio at `ASR_SAMPLE_RATE` -> one JSON final result:
  `{"type":"final","text":"...","duration":<seconds>}`.

Failures return `{"type":"error","message":"..."}`. The host Orchestrator
performs VAD and sends complete utterance audio; this service does not stream
partial transcripts. Blocking faster-whisper inference and segment consumption
run in a bounded executor, so health/ping handling remains responsive while a
transcription is active. The pong reports `max_concurrent_transcriptions`.

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

The process has one mutable OuteTTS/llama.cpp model worker in a restartable child
process. Generation is serialized internally even when multiple WebSocket tasks
are present. If an active synthesis is cancelled because its client disconnects,
the child is terminated and re-created; stale native generation cannot continue
holding the only model slot. Health responses report worker liveness, restart
count, and cancellation mode.

## Soridormi contract snapshot

`capabilities/soridormi.json` contains 12 tools grouped under four external
agents:

- robot status, mode, and battery reads;
- motion plan creation, execution, stop, and cancellation;
- named-skill catalog, plan creation, and execution;
- motion monitoring and emergency stop.

The live endpoint URL is supplied by `${SORIDORMI_MCP_URL}`. Probe the endpoint
against the manifest before enabling execution; the checked-in JSON is not proof
that the currently running server has the same schema.
