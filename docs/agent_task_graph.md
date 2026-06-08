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

Chromie does not currently ship an MCP transport in this layer. Real robot execution must remain behind registered safe tools and the existing hardware boundary.

This work is tracked as **M4 - TaskGraph production integration** in the
[project roadmap](../ROADMAP.md).

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
