from __future__ import annotations

import unittest
from typing import Any

from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ExecutionPolicy,
    ToolCapability,
    TransportSpec,
)
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.service import TaskGraphService
from agent.app.tool_invocation import McpStreamableHttpInvoker


def _registry():
    bundle = CapabilityBundle(
        source="remote-test",
        agents=[
            AgentManifest(
                agent_id="remote",
                transport=TransportSpec(kind="mcp_streamable_http", url="http://remote:8000/mcp"),
                tools=[
                    ToolCapability(
                        name="remote.lookup",
                        agent_id="remote",
                        safety_class="safe_read",
                        effects=["read_only"],
                    ),
                    ToolCapability(
                        name="remote.plan",
                        agent_id="remote",
                        safety_class="planning_only",
                        effects=["planning_only"],
                    ),
                    ToolCapability(
                        name="remote.write",
                        agent_id="remote",
                        safety_class="low_risk_action",
                        effects=["write"],
                        execution=ExecutionPolicy(side_effect_free=False),
                    ),
                ],
            )
        ],
    )
    return build_chromie_registry([bundle])


class ReadOnlyTaskGraphExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_executes_read_only_graph_and_resolves_refs(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append((tool, args))
            if tool == "remote.lookup":
                return {"structuredContent": {"value": "result-1"}}
            return {"structuredContent": {"plan": f"use {args['input']}"}}

        service = TaskGraphService(
            _registry(),
            read_only_invoker=McpStreamableHttpInvoker(_registry(), call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "read-only-success",
                "created_by": "user",
                "nodes": [
                    {"id": "lookup", "tool": "remote.lookup", "type": "query"},
                    {
                        "id": "plan",
                        "tool": "remote.plan",
                        "type": "plan",
                        "depends_on": ["lookup"],
                        "args": {"input": {"$ref": "lookup.output.value"}},
                    },
                ],
            }
        )

        trace = await service.execute_read_only(graph)

        self.assertEqual(trace.status, "success")
        self.assertEqual(calls[1], ("remote.plan", {"input": "result-1"}))
        self.assertEqual(service.get_trace(graph.graph_id).status, "success")

    async def test_rejects_entire_graph_before_calling_any_side_effect(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "read-only-rejected",
                "created_by": "user",
                "nodes": [
                    {"id": "lookup", "tool": "remote.lookup", "type": "query"},
                    {
                        "id": "write",
                        "tool": "remote.write",
                        "type": "action",
                        "depends_on": ["lookup"],
                    },
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "non-read-only nodes"):
            await service.execute_read_only(graph)

        self.assertEqual(calls, 0)
        self.assertIsNone(service.get_trace(graph.graph_id))

    async def test_disabled_execution_fails_without_invocation(self) -> None:
        graph = TaskGraph.model_validate(
            {
                "graph_id": "disabled",
                "created_by": "user",
                "nodes": [{"id": "lookup", "tool": "remote.lookup", "type": "query"}],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            await TaskGraphService(_registry()).execute_read_only(graph)


if __name__ == "__main__":
    unittest.main()
