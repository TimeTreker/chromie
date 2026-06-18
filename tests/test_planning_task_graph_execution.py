from __future__ import annotations

import asyncio
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
    return build_chromie_registry(
        [
            CapabilityBundle(
                source="planning-test",
                agents=[
                    AgentManifest(
                        agent_id="remote",
                        transport=TransportSpec(
                            kind="mcp_streamable_http",
                            url="http://remote:8000/mcp",
                        ),
                        tools=[
                            ToolCapability(
                                name="remote.status",
                                agent_id="remote",
                                safety_class="safe_read",
                            ),
                            ToolCapability(
                                name="remote.create_plan",
                                agent_id="remote",
                                safety_class="planning_only",
                                execution=ExecutionPolicy(side_effect_free=False),
                            ),
                            ToolCapability(
                                name="remote.move",
                                agent_id="remote",
                                safety_class="physical_motion",
                            ),
                        ],
                    )
                ],
            )
        ]
    )


def _soridormi_task_registry():
    return build_chromie_registry(
        [
            CapabilityBundle(
                source="soridormi-task-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.task",
                        transport=TransportSpec(
                            kind="mcp_streamable_http",
                            url="http://soridormi:8000/mcp",
                        ),
                        tools=[
                            ToolCapability(
                                name="soridormi.task.submit",
                                agent_id="soridormi.task",
                                safety_class="planning_only",
                                effects=[
                                    "planning_only",
                                    "embodied_task_request",
                                    "no_motion_contract",
                                ],
                                execution=ExecutionPolicy(side_effect_free=False),
                            ),
                            ToolCapability(
                                name="soridormi.task.events",
                                agent_id="soridormi.task",
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                        ],
                    )
                ],
            )
        ]
    )


class PlanningTaskGraphExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_stateful_non_physical_plan_creation(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "planning",
                "created_by": "system",
                "nodes": [
                    {"id": "status", "tool": "remote.status", "type": "query"},
                    {
                        "id": "plan",
                        "tool": "remote.create_plan",
                        "type": "plan",
                        "depends_on": ["status"],
                    },
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(trace.status, "success")
        self.assertEqual(calls, ["remote.status", "remote.create_plan"])

    async def test_rejects_physical_tool_before_any_call(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            nonlocal calls
            calls += 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "unsafe-planning",
                "created_by": "system",
                "nodes": [{"id": "move", "tool": "remote.move"}],
            }
        )

        with self.assertRaisesRegex(ValueError, "rejected unsafe nodes"):
            await service.execute_planning(graph)
        self.assertEqual(calls, 0)

    async def test_rejects_planning_tool_with_physical_effect(self) -> None:
        registry = _registry()
        registry.get_tool("remote.create_plan").effects = ["physical_motion"]
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(
                registry,
                call=lambda *args: None,
            ),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "inconsistent-planning",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "plan",
                        "tool": "remote.create_plan",
                        "type": "plan",
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "physical_motion"):
            await service.execute_planning(graph)

    async def test_independent_planning_nodes_can_overlap(self) -> None:
        active = 0
        peak = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "parallel-planning",
                "created_by": "system",
                "nodes": [
                    {"id": "plan-a", "tool": "remote.create_plan", "type": "plan"},
                    {"id": "plan-b", "tool": "remote.create_plan", "type": "plan"},
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(trace.status, "success")
        self.assertEqual(peak, 2)

    async def test_soridormi_task_submit_adds_client_ref_and_monitors_events(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            calls.append((tool, args))
            if tool == "soridormi.task.submit":
                return {
                    "structuredContent": {
                        "task_id": "soridormi-task-1",
                        "client_task_ref": args["client_task_ref"],
                        "accepted": True,
                        "status": "accepted",
                        "phase": "planning",
                        "terminal": False,
                        "safe_idle": True,
                        "no_motion": True,
                    }
                }
            if tool == "soridormi.task.events":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_events.v1",
                        "task_id": "soridormi-task-1",
                        "client_task_ref": "chromie:water-run:body-task",
                        "status": "completed",
                        "phase": "completed",
                        "terminal": True,
                        "safe_idle": True,
                        "deadline_at": 0.0,
                        "expired": False,
                        "events": [],
                        "returned_count": 0,
                        "latest_sequence": 4,
                        "next_after_sequence": 4,
                        "has_more": False,
                        "poll_recommendation": {"action": "stop_polling"},
                    }
                }
            raise AssertionError(f"unexpected tool {tool}")

        registry = _soridormi_task_registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "water-run",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "body-task",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "args": {
                            "task_type": "navigate_to_location",
                            "parameters": {"destination": "kitchen"},
                        },
                    }
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(trace.status, "success")
        self.assertEqual(
            calls,
            [
                (
                    "soridormi.task.submit",
                    {
                        "task_type": "navigate_to_location",
                        "parameters": {"destination": "kitchen"},
                        "client_task_ref": "chromie:water-run:body-task",
                    },
                ),
                (
                    "soridormi.task.events",
                    {"task_id": "soridormi-task-1", "after_sequence": 0},
                ),
            ],
        )
        result = trace.result_map()["body-task"]
        self.assertEqual(result.output["status"], "completed")
        self.assertEqual(
            result.output["monitoring"]["schema_version"],
            "soridormi.task_events.v1",
        )

    async def test_soridormi_task_refusal_fails_the_graph_node(self) -> None:
        calls: list[str] = []

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            calls.append(tool)
            return {
                "structuredContent": {
                    "task_id": "soridormi-task-1",
                    "client_task_ref": args["client_task_ref"],
                    "accepted": False,
                    "status": "refused",
                    "phase": "refused",
                    "terminal": True,
                    "safe_idle": True,
                    "reason_code": "missing_navigation_pipeline",
                    "reason": "navigate_to_location is declared but not executable yet.",
                }
            }

        registry = _soridormi_task_registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "blocked-nav",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "go",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "args": {"task_type": "navigate_to_location"},
                    }
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(trace.status, "aborted")
        self.assertEqual(calls, ["soridormi.task.submit"])
        result = trace.result_map()["go"]
        self.assertEqual(result.status, "failed_fatal")
        self.assertIn("missing_navigation_pipeline", result.error or "")


if __name__ == "__main__":
    unittest.main()
