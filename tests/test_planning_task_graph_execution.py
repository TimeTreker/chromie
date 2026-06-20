from __future__ import annotations

import asyncio
import unittest
from typing import Any

from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ExecutionPolicy,
    FailurePolicy,
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
                                name="soridormi.task.get_capabilities",
                                agent_id="soridormi.task",
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                            ToolCapability(
                                name="soridormi.task.preview",
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

        validation = service.validate(graph)
        self.assertEqual(validation.errors, [])
        self.assertEqual(validation.warnings, [])

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
        self.assertEqual(trace.outcome_summary, "TaskGraph completed successfully.")
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

    async def test_soridormi_task_contract_graph_previews_submits_and_monitors(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            calls.append((tool, args))
            if tool == "soridormi.task.get_capabilities":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_capabilities.v1",
                        "task_api_no_motion": True,
                        "task_types": {
                            "deliver_object": {
                                "status": "blocked",
                                "blocked_subsystems": ["manipulation", "handoff"],
                            }
                        },
                    }
                }
            if tool == "soridormi.task.preview":
                return {
                    "structuredContent": {
                        "preview_id": "preview-1",
                        "task_type": args["task_type"],
                        "accepted": True,
                        "status": "accepted",
                        "phase": "previewed",
                        "terminal": True,
                        "safe_idle": True,
                        "no_motion": True,
                        "blocked_subsystems": ["manipulation", "handoff"],
                        "recommended_next_actions": [
                            {
                                "action": "report_blocked_capability",
                                "reason_code": "missing_manipulation_pipeline",
                            }
                        ],
                    }
                }
            if tool == "soridormi.task.submit":
                return {
                    "structuredContent": {
                        "task_id": "soridormi-task-2",
                        "client_task_ref": args["client_task_ref"],
                        "task_type": args["task_type"],
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
                        "task_id": "soridormi-task-2",
                        "client_task_ref": "chromie:delivery-request:submit",
                        "status": "completed",
                        "phase": "completed",
                        "terminal": True,
                        "safe_idle": True,
                        "events": [
                            {
                                "sequence": 1,
                                "kind": "task_completed",
                                "message": "Contract-only task completed with no motion.",
                            }
                        ],
                        "returned_count": 1,
                        "latest_sequence": 1,
                        "next_after_sequence": 1,
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
        task_payload = {
            "task_type": "deliver_object",
            "summary": "Bring water from the kitchen.",
            "parameters": {"object": "water", "source": "kitchen"},
        }
        graph = TaskGraph.model_validate(
            {
                "graph_id": "delivery-request",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "capabilities",
                        "tool": "soridormi.task.get_capabilities",
                        "type": "query",
                    },
                    {
                        "id": "preview",
                        "tool": "soridormi.task.preview",
                        "type": "plan",
                        "depends_on": ["capabilities"],
                        "args": task_payload,
                    },
                    {
                        "id": "submit",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "depends_on": ["preview"],
                        "args": task_payload,
                    },
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(trace.status, "success")
        self.assertEqual(trace.outcome_summary, "TaskGraph completed successfully.")
        self.assertEqual(
            [tool for tool, _ in calls],
            [
                "soridormi.task.get_capabilities",
                "soridormi.task.preview",
                "soridormi.task.submit",
                "soridormi.task.events",
            ],
        )
        submit_args = calls[2][1]
        self.assertEqual(submit_args["client_task_ref"], "chromie:delivery-request:submit")
        submit_result = trace.result_map()["submit"]
        self.assertEqual(submit_result.output["status"], "completed")
        self.assertEqual(
            submit_result.output["monitoring"]["events"][0]["kind"],
            "task_completed",
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
                    "blocked_subsystems": ["navigation", "localization"],
                    "recommended_next_actions": [
                        {
                            "action": "report_blocked_capability",
                            "reason_code": "missing_navigation_pipeline",
                        }
                    ],
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
        self.assertIn(
            "TaskGraph aborted: node go (soridormi.task.submit) failed",
            trace.outcome_summary,
        )
        self.assertIn("reason_code=missing_navigation_pipeline", trace.outcome_summary)
        self.assertIn(
            "blocked_subsystems=navigation,localization",
            trace.outcome_summary,
        )
        self.assertIn(
            "recommended_next_actions=report_blocked_capability(missing_navigation_pipeline)",
            trace.outcome_summary,
        )
        self.assertEqual(calls, ["soridormi.task.submit"])
        result = trace.result_map()["go"]
        self.assertEqual(result.status, "failed_fatal")
        error = result.error or ""
        self.assertIn("missing_navigation_pipeline", error)
        self.assertIn("blocked_subsystems=navigation,localization", error)
        self.assertIn(
            "recommended_next_actions=report_blocked_capability(missing_navigation_pipeline)",
            error,
        )

    async def test_soridormi_task_refusal_can_activate_trace_only_report(self) -> None:
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
                    "blocked_subsystems": ["navigation", "localization"],
                }
            }

        registry = _soridormi_task_registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "blocked-nav-report",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "go",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "args": {"task_type": "navigate_to_location"},
                        "on_failure": FailurePolicy(
                            strategy="goto",
                            target="report",
                        ).model_dump(mode="json"),
                    },
                    {
                        "id": "report",
                        "tool": "chromie.report",
                        "type": "report",
                        "args": {
                            "message": {
                                "$ref": "go.error",
                            }
                        },
                    },
                ],
            }
        )

        trace = await service.execute_planning(graph)

        self.assertEqual(calls, ["soridormi.task.submit"])
        self.assertEqual(trace.status, "failed")
        result_map = trace.result_map()
        self.assertEqual(result_map["go"].status, "failed_fatal")
        self.assertEqual(result_map["report"].status, "success")
        self.assertIn(
            "Soridormi task did not complete successfully",
            result_map["report"].output["message"],
        )
        self.assertIn(
            "missing_navigation_pipeline",
            result_map["report"].output["message"],
        )
        self.assertEqual(
            result_map["report"].output["delivery"],
            "trace_only",
        )
        self.assertEqual(
            result_map["report"].output["reported"],
            True,
        )
        self.assertIn("missing_navigation_pipeline", trace.outcome_summary)

    async def test_planning_execution_still_rejects_speak_nodes(self) -> None:
        registry = _soridormi_task_registry()
        service = TaskGraphService(
            registry,
            planning_invoker=McpStreamableHttpInvoker(
                registry,
                call=lambda *args: None,
            ),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "speak-rejected",
                "created_by": "system",
                "nodes": [
                    {
                        "id": "speak",
                        "tool": "chromie.speak",
                        "type": "report",
                        "args": {"text": "I cannot do that yet."},
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "chromie.speak"):
            await service.execute_planning(graph)


if __name__ == "__main__":
    unittest.main()
