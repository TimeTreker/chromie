# Chromie Agent

`chromie-agent` is Chromie's containerized reasoning, compatibility-response,
structured-interaction, capability-registry, and TaskGraph service. It listens
on port `8092` by default.

For the authoritative project status, see [`../docs/STATUS.md`](../docs/STATUS.md).
For the complete HTTP surface, see
[`../docs/API_REFERENCE.md`](../docs/API_REFERENCE.md).

## Current implementation boundary

The Agent:

- accepts text, routing decisions, and bounded context;
- returns the established `AgentResult` contract from `POST /run`;
- returns the strict `InteractionResponse` contract from `POST /interaction`;
- loads and validates trusted external capability manifests at startup;
- plans, validates, simulates, and—behind explicit gates—executes TaskGraphs;
- never opens the microphone, plays audio, or controls robot hardware directly.

The host Orchestrator owns realtime audio, conversation state, interruption, and
the trusted Skill Runtime. Soridormi owns embodied planning, execution policy,
resource exclusivity, cancellation, emergency behavior, and hardware
commissioning.

`POST /interaction` now uses `InteractionRuntime` by default. Specialized agents
write through a native accumulator that creates `InteractionSpeech` and
`SkillRequest` objects as the pipeline runs; the endpoint does not convert a
final `AgentResult`. The serialized result is validated again against the strict
shared contract before it is returned.

`AgentResultInteractionAdapter` remains available for rollback through
`AGENT_INTERACTION_OUTPUT_MODE=legacy-adapter`. Native validation fallback is
separate and default-off; enable it only with
`AGENT_NATIVE_INTERACTION_FALLBACK=1`.

## Specialized agents

| Agent | Current behavior |
|---|---|
| `conversation_agent` | Produces short conversational speech with Ollama or deterministic fallback behavior. |
| `speaker_agent` | Normalizes wording, brevity, and speaking style. It never plays audio. |
| `robot_pose_controller_agent` | Produces legacy high-level pose/head/gesture action proposals. |
| `motion_planner_agent` | Produces legacy high-level movement proposals. |
| `safety_agent` | Rejects or clamps unsafe legacy action proposals. |
| `tool_agent` | Produces a validated TaskGraph when LLM TaskGraph planning is enabled; otherwise emits a compatibility `tool.*` action that this repository does not automatically execute. |
| `memory_agent` | Produces memory updates and compatibility `memory.store` actions. Chromie's current conversation state is process-local and not a durable memory store. |
| `vision_agent` | Produces a compatibility `vision.query` proposal. No vision executor is included in this repository. |

## HTTP API

Core endpoints:

- `GET /health`
- `GET /agents`
- `GET /capabilities`
- `GET /capabilities/llm-context?language=en`
- `POST /run`
- `POST /interaction`

TaskGraph endpoints:

- `POST /task-graphs/validate`
- `POST /task-graphs/dry-run`
- `POST /task-graphs/execute-read-only`
- `POST /task-graphs/execute-planning`
- `POST /task-graphs/confirmation-grants`
- `POST /task-graphs/execute-guarded`
- `POST /task-graphs/{graph_id}/cancel`
- `GET /task-graphs/{graph_id}/trace`
- `GET /task-graphs/scheduler/status`

Guarded execution, confirmation grants, and cancellation require
`Authorization: Bearer <AGENT_TASK_GRAPH_EXECUTION_TOKEN>`. Dry-run, trace, and
scheduler diagnostics require `AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN`; a blank
diagnostics token falls back to the execution token, and both blank disables
those diagnostic endpoints with HTTP 503. Validation and capability inspection
remain available without that bearer token, so deploy the service only on a
trusted network boundary.

## Feature gates

Risk-bearing behavior is default-off.

| Variable | Default | Effect |
|---|---:|---|
| `AGENT_INTERACTION_OUTPUT_MODE` | `native` | Select `native` or explicit `legacy-adapter` output for `/interaction`. |
| `AGENT_NATIVE_INTERACTION_FALLBACK` | `0` | On native contract-validation failure, opt in to legacy adapter fallback instead of failing closed. |
| `AGENT_ENABLE_TASK_GRAPH_PLANNING` | `0` | Allow LLM-authored TaskGraph planning for tool routes. |
| `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION` | `0` | Enable side-effect-free read-only execution. |
| `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION` | `0` | Enable stateful `planning_only` execution. |
| `AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION` | `0` | Permit eligible independent nodes to use bounded parallel scheduling. |
| `AGENT_TASK_GRAPH_MAX_CONCURRENCY` | `4` | Process-local scheduler concurrency bound. |
| `AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN` | blank | Protect dry-run, trace, and scheduler endpoints; falls back to the execution token. |
| `AGENT_TASK_GRAPH_TRACE_MAX_ENTRIES` | `128` | Bound retained in-memory traces with LRU eviction. |
| `AGENT_TASK_GRAPH_TRACE_TTL_SEC` | `900` | Expire retained traces after this many seconds. |
| `AGENT_TASK_GRAPH_GRANT_MAX_ENTRIES` | `128` | Bound unconsumed in-memory confirmation grants. |
| `AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION` | `0` | Enable authorized guarded side effects. Requires an execution token. |
| `AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION` | `0` | Permit physical nodes after confirmation and active-monitor proof. Requires guarded execution. |

See [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md) for all settings.

## Capability manifests

`AGENT_CAPABILITY_MANIFESTS` is a comma-separated list of JSON files or
directories. The root Compose deployment mounts `./capabilities` read-only at
`/app/capabilities`.

Startup fails on missing files, malformed manifests, unresolved required
environment variables, duplicate capability identifiers, or incompatible
registry content. This is intentional: runtime policy must not silently diverge
from deployment configuration.

The checked-in Soridormi snapshot is materialized from Soridormi's authoritative
export and pinned to upstream commit
`4afb4bc6411db4a4194e97349d9466a62efd2f24`. See
[`../capabilities/README.md`](../capabilities/README.md).

## TaskGraph behavior

TaskGraph planning and execution are separate operations. A graph returned in
`AgentResult.task_graphs` is never automatically dispatched.

- Validation resolves every node against the active registry.
- Dry-run simulates policy and dependency behavior without remote MCP calls.
- Read-only execution accepts only eligible side-effect-free capabilities.
- Planning execution additionally accepts stateful `planning_only` capabilities.
- Guarded execution requires explicit authorization, graph-bound confirmation,
  and the capability's safety policy.
- Physical execution additionally requires an active covering monitor and an
  emergency fallback.
- Parallel execution is bounded and honors `can_run_parallel` and
  `exclusive_group`; physical work remains sequential.
- Traces and confirmation grants are retained in process memory only. Traces
  have configurable TTL/LRU bounds; grants have a configurable capacity and
  purge expired entries before issue/consume.

Detailed semantics are in
[`../docs/agent_task_graph.md`](../docs/agent_task_graph.md) and
[`../docs/task_graph_concurrency_decision.md`](../docs/task_graph_concurrency_decision.md).

## Soridormi verification

From the `agent` directory with development dependencies installed:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.probe_capabilities \
  --manifest ../capabilities/soridormi.json

SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.soridormi_acceptance \
  --manifest ../capabilities/soridormi.json
```

The probe checks the complete manifest by default. Acceptance workflows that
intentionally target a smaller surface may repeat `--exclude-effect EFFECT`;
M13 uses this only for the hidden `test_control` surface.

The Agent's direct Ollama client ignores ambient host proxy variables so
Compose-local model traffic cannot be redirected through an unreachable proxy.

The default acceptance uses safe status/planning behavior and does not authorize
physical motion. Additional guarded dry-run and runtime-cancellation modes are
documented in [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md).

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r agent/requirements.txt
PYTHONPATH=agent uvicorn app.main:app --host 0.0.0.0 --port 8092
```

The service can run with `AGENT_USE_LLM=0`; deterministic fallbacks remain
available for control-plane testing.

## Build the container

The Dockerfile requires the repository root as build context:

```bash
docker build -f agent/Dockerfile -t chromie-agent .
```

Normally start the complete service set through:

```bash
./scripts/start_services.sh
```

## Known limitations

- Native `/interaction` output and host request-bound confirmation are
  implemented; retained automatic and reviewed reference-host microphone
  evidence remain open.
- Tool, memory, and vision compatibility actions are proposals, not built-in executors.
- TaskGraph scheduler, grants, and traces are process-local rather than durable or distributed.
- Cross-process robot exclusivity is enforced by Soridormi, not by the Agent's local scheduler.
- Enabling physical execution is not equivalent to hardware commissioning or target acceptance.
