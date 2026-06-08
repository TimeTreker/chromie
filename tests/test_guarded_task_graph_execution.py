from __future__ import annotations

import unittest
from typing import Any

from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ConfirmationPolicy,
    ExecutionPolicy,
    FailurePolicy,
    MonitoringPolicy,
    ToolCapability,
    TransportSpec,
)
from agent.app.task_graph.async_executor import TaskGraphExecutionProofs
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.service import TaskGraphService
from agent.app.tool_invocation import McpStreamableHttpInvoker


def _registry():
    bundle = CapabilityBundle(
        source="guarded-test",
        agents=[
            AgentManifest(
                agent_id="remote.control",
                transport=TransportSpec(
                    kind="mcp_streamable_http",
                    url="http://remote:8000/mcp",
                ),
                tools=[
                    ToolCapability(
                        name="remote.write",
                        agent_id="remote.control",
                        safety_class="low_risk_action",
                        effects=["write"],
                        confirmation=ConfirmationPolicy(required=True),
                        execution=ExecutionPolicy(side_effect_free=False),
                    ),
                    ToolCapability(
                        name="remote.monitor",
                        agent_id="remote.control",
                        safety_class="safety_critical",
                        effects=["safety_control"],
                    ),
                    ToolCapability(
                        name="remote.move",
                        agent_id="remote.control",
                        safety_class="physical_motion",
                        effects=["physical_motion"],
                        confirmation=ConfirmationPolicy(required=True),
                        monitoring=MonitoringPolicy(requires_safety_monitor=True),
                        execution=ExecutionPolicy(side_effect_free=False),
                        default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                    ),
                ],
            )
        ],
    )
    return build_chromie_registry([bundle])


def _confirmed_write_graph() -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": "confirmed-write",
            "created_by": "user",
            "nodes": [
                {
                    "id": "confirm",
                    "tool": "chromie.ask_confirmation",
                    "type": "confirmation",
                    "args": {"question": "Write the value?"},
                },
                {
                    "id": "write",
                    "tool": "remote.write",
                    "type": "action",
                    "depends_on": ["confirm"],
                    "args": {"value": "approved"},
                },
            ],
        }
    )


def _physical_graph() -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": "physical-motion",
            "created_by": "user",
            "nodes": [
                {
                    "id": "confirm",
                    "tool": "chromie.ask_confirmation",
                    "type": "confirmation",
                    "args": {"question": "Move now?"},
                },
                {
                    "id": "monitor",
                    "tool": "remote.monitor",
                    "type": "monitor",
                    "during": ["move"],
                },
                {
                    "id": "move",
                    "tool": "remote.move",
                    "type": "action",
                    "depends_on": ["confirm"],
                    "args": {"distance_m": 0.1},
                },
            ],
        }
    )


class GuardedTaskGraphExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_low_risk_side_effect_executes(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append(tool)
            return {"structuredContent": {"written": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
        )

        trace = await service.execute_guarded(
            _confirmed_write_graph(),
            TaskGraphExecutionProofs(confirmed_node_ids={"confirm"}),
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(calls, ["remote.write"])
        self.assertTrue(trace.result_map()["confirm"].output["confirmed"])

    async def test_missing_confirmation_rejects_before_remote_call(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"written": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
        )

        with self.assertRaisesRegex(ValueError, "node-bound confirmation proof"):
            await service.execute_guarded(
                _confirmed_write_graph(),
                TaskGraphExecutionProofs(),
            )

        self.assertEqual(calls, 0)

    async def test_physical_motion_runs_only_after_monitor_activation(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            return {"structuredContent": {"completed": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )

        trace = await service.execute_guarded(
            _physical_graph(),
            TaskGraphExecutionProofs(confirmed_node_ids={"confirm"}),
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(calls, ["remote.monitor", "remote.move"])

    async def test_inactive_monitor_blocks_physical_motion(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append(tool)
            return {"structuredContent": {"active": False}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )

        trace = await service.execute_guarded(
            _physical_graph(),
            TaskGraphExecutionProofs(confirmed_node_ids={"confirm"}),
        )

        self.assertEqual(trace.status, "failed")
        self.assertEqual(calls, ["remote.monitor"])
        self.assertIn("active safety monitor", trace.result_map()["move"].error or "")

    async def test_physical_motion_has_separate_enable_gate(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"active": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=False,
        )

        with self.assertRaisesRegex(ValueError, "physical TaskGraph execution is disabled"):
            await service.execute_guarded(
                _physical_graph(),
                TaskGraphExecutionProofs(confirmed_node_ids={"confirm"}),
            )

        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
