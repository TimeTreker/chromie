# Chromie TaskGraph and dry-run executor

Chromie owns the global LLM router. Soridormi and other subsystems only expose
capability manifests. This layer lets Chromie validate an LLM-proposed DAG before
any MCP tool call can execute.

## Scope

The task graph layer provides:

- `TaskGraph` / `TaskNode`
- `$ref` argument references such as `make_plan.output.plan_id`
- `GraphValidator` against the global `CapabilityRegistry`
- physical-motion checks for confirmation and safety monitor coverage
- fallback target validation
- blocked-node propagation
- `DagDryRunExecutor` for trace development without calling real MCP servers
- `DagToolExecutor` with a transport-neutral `ToolInvoker`
- Agent API endpoints for validation, dry-run execution, and trace lookup

Chromie ships an MCP Streamable HTTP transport behind `ToolInvoker`. Real
robot execution remains behind registered capabilities, confirmation grants,
monitor gating, emergency fallbacks, and the existing hardware boundary.

This layer completed **M4 - TaskGraph production integration**. Real external
deployment and acceptance are tracked as M5 in the [project roadmap](../ROADMAP.md).

The accepted concurrency direction is to extend these executors and share
scheduling/reliability semantics with Skill Runtime, not to add a separate DAG
runner. See [TaskGraph concurrency and shared scheduling
decision](task_graph_concurrency_decision.md).

## Agent API

Validate a graph without executing it:

```text
POST /task-graphs/validate
```

Dry-run a graph and retain its latest trace in Agent memory:

```text
POST /task-graphs/dry-run
GET /task-graphs/{graph_id}/trace
```

The dry-run endpoint never calls a real MCP server or hardware device. Invalid
graphs return HTTP 422 and are not stored as execution traces.

## Agent planning path

With `AGENT_ENABLE_TASK_GRAPH_PLANNING=1`, requests routed to `tool_agent` may
produce a validated graph in `AgentResult.task_graphs`. Conversation and robot
action routes keep their existing deterministic paths.

The planner exposes only registered LLM-visible capabilities, filters request
context to an allowlist, replaces model-provided graph IDs, and validates the
result before returning it. These graphs are plans, not executable actions.

## Example physical-motion graph

A safe short-motion graph should include:

1. read robot status
2. create Soridormi motion plan
3. ask Chromie-side confirmation
4. run Soridormi safety monitor during execution
5. execute Soridormi motion plan
6. report result through Chromie

Execution node arguments may reference earlier outputs:

```json
{
  "id": "execute_motion",
  "tool": "soridormi.motion.execute_plan",
  "depends_on": ["confirm"],
  "args": {
    "plan_id": {"$ref": "make_plan.output.plan_id"}
  }
}
```

## CLI

Validate a graph:

```bash
PYTHONPATH=agent python -m app.task_graph_demo graph.json \
  --manifest /tmp/soridormi_capabilities.json
```

Dry-run it:

```bash
PYTHONPATH=agent python -m app.task_graph_demo graph.json \
  --manifest /tmp/soridormi_capabilities.json \
  --dry-run
```

Decline confirmation in dry-run:

```bash
PYTHONPATH=agent python -m app.task_graph_demo graph.json \
  --manifest /tmp/soridormi_capabilities.json \
  --dry-run \
  --no-auto-confirm
```

## Tool invocation bridge

Chromie also has a transport-neutral `ToolInvoker` interface:

```python
from app.task_graph import DagToolExecutor
from app.tool_invocation import FunctionToolInvoker
```

`DagToolExecutor` uses the same `TaskGraph`, `GraphValidator`, `$ref` handling,
fallback logic, and trace format as the dry-run executor, but delegates each tool
call to a registered invoker. The invoker can be an in-process test registry, a
local Chromie tool adapter, a Soridormi CLI adapter, or a future MCP client.

The boundary is:

```text
TaskGraph node -> resolved args -> ToolInvoker.invoke(tool_name, args) -> ToolCallOutcome -> NodeResult
```

This keeps LLM/DAG planning independent from the transport. Real MCP should wrap
the same `ToolInvoker` protocol rather than changing the DAG schema.

## MCP Streamable HTTP adapter

`McpStreamableHttpInvoker` uses the official MCP Python SDK and the URL declared
by each agent manifest's `TransportSpec`. It normalizes MCP structured content,
text content, tool errors, transport errors, and timeouts into
`ToolCallOutcome`.

Invocation is policy-gated independently from graph validation:

- restricted tools are always rejected
- low-risk side effects require explicit side-effect authorization
- physical motion additionally requires confirmation and an active safety monitor
- safety-critical controls require explicit safety-control authorization

The adapter is not yet connected to automatic TaskGraph execution. Planned
graphs remain observable artifacts until the execution coordinator supplies
these proofs.

## Read-only execution coordinator

Set `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1` to enable:

```text
POST /task-graphs/execute-read-only
```

The coordinator validates and preflights the entire graph before the first MCP
call. Every node must be `safe_read` or `planning_only` and declare
`side_effect_free=true`. If any node fails that policy, no node is invoked.

This endpoint is disabled by default. It does not accept confirmation or safety
proofs and therefore cannot execute speech output, writes, safety controls, or
physical motion.

## Planning execution coordinator

Some planning tools create server-side plan IDs and therefore correctly declare
`side_effect_free=false` even though they cannot move hardware. Enable these
with:

```env
AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1
```

```text
POST /task-graphs/execute-planning
```

This coordinator accepts `safe_read` nodes only when they are side-effect-free,
and accepts `planning_only` nodes such as
`soridormi.motion.create_plan`. It rejects low-risk actions, safety controls,
restricted tools, and physical motion before the first MCP call.

## Parallel read and planning execution

Independent read-only and planning nodes can use the shared bounded scheduler:

```env
AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION=1
AGENT_TASK_GRAPH_MAX_CONCURRENCY=4
```

The feature is disabled by default. When disabled, the service selects the
existing sequential executor behavior before invoking any node.

When enabled:

- only dependency-ready nodes overlap;
- the configured limit bounds active work across concurrent read/planning
  graphs in the Agent process;
- `can_run_parallel=false` excludes all other work while that capability runs;
- matching `exclusive_group` values serialize across graph executions;
- node results and result trace events are recorded in deterministic node-ID
  order, regardless of completion order;
- node/capability timeouts and node retry/backoff remain active.
- failure policies can skip, provide defaults, activate validated fallback
  nodes, or abort and cancel still-running siblings;
- cancellation retains a partial trace and affects only the requested graph.

Guarded execution may use the same flag for independent non-physical
`safe_read`, `planning_only`, and `low_risk_action` nodes. Confirmation nodes,
monitors, safety controls, and all physical-motion nodes remain sequential.
Disabling the flag affects subsequent executions; an in-flight graph is never
replayed through the sequential executor.

Scheduler diagnostics are available from:

```text
GET /health
GET /task-graphs/scheduler/status
```

They report the configured mode and limit, active/waiting work, serial claims,
and active graph IDs. Trace events include deterministic `sequence` and
`stable_order` presentation metadata.

## Supervised guarded execution

Guarded side effects require an operator-configured bearer token:

```env
AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=1
AGENT_TASK_GRAPH_EXECUTION_TOKEN=<long-random-secret>
```

The operator first exchanges the exact graph and confirmed node IDs for a
short-lived grant:

```text
POST /task-graphs/confirmation-grants
Authorization: Bearer <long-random-secret>
```

The returned opaque grant is single-use, expires within at most five minutes,
and is bound to a hash of the exact graph. The caller then submits:

```text
POST /task-graphs/execute-guarded
Authorization: Bearer <long-random-secret>
```

with `confirmation_grant` beside the graph. Confirmed IDs must name actual
confirmation nodes, and tools that require confirmation must depend on them.
The coordinator represents confirmed nodes locally; it does not invoke
`chromie.ask_confirmation` as an MCP tool.

Physical motion has a second, independent deployment gate:

```env
AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=1
```

A monitor node covering the physical node must successfully return `ok: true`
or `active: true` before motion is invoked. The MCP invoker then independently
checks confirmation and monitor context again. Every physical node must also
declare an `on_failure` target that is a registered stop safety node and an
emergency-stop target through `on_failure` or `on_event`. Ordinary failures use
the stop fallback; cancellation and emergency paths use emergency stop.

An authorized caller can cancel an active graph:

```text
POST /task-graphs/{graph_id}/cancel
Authorization: Bearer <long-random-secret>
```

Cancellation marks the physical node cancelled while preserving the in-flight
MCP request long enough for the declared emergency-stop fallback to preempt it.
Chromie then drains the original request as cleanup and records the cancelled
trace. The live acceptance hook observes the actual MCP `tools/call` dispatch
boundary, so it does not confuse client-session setup with in-flight motion.

This is supervised operator attestation, not yet Chromie's end-user voice
confirmation workflow.
