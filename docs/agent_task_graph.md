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
declare an `on_failure` target that is a registered emergency-stop safety node.

An authorized caller can cancel an active graph:

```text
POST /task-graphs/{graph_id}/cancel
Authorization: Bearer <long-random-secret>
```

Cancellation propagates to the task awaiting the MCP call. If physical
execution has started, Chromie invokes the declared emergency-stop fallback and
records a cancelled trace.

This is supervised operator attestation, not yet Chromie's end-user voice
confirmation workflow.
