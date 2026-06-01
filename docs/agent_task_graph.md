# Chromie TaskGraph and dry-run executor

Chromie owns the global LLM router. Soridormi and other subsystems only expose
capability manifests. This layer lets Chromie validate an LLM-proposed DAG before
any MCP tool call can execute.

## Scope

This patch adds only schema, validation, and deterministic dry-run tracing:

- `TaskGraph` / `TaskNode`
- `$ref` argument references such as `make_plan.output.plan_id`
- `GraphValidator` against the global `CapabilityRegistry`
- physical-motion checks for confirmation and safety monitor coverage
- fallback target validation
- blocked-node propagation
- `DagDryRunExecutor` for trace development without calling real MCP servers

It does not start MCP transports, call real tools, or move Soridormi.

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

The first executor was intentionally dry-run only. Chromie now also has a
transport-neutral `ToolInvoker` interface:

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
