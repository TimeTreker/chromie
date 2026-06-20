from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agent.app.capabilities.loader import build_configured_registry
from agent.app.capabilities.probe import CapabilityProbeResult
from agent.app.soridormi_acceptance import (
    build_soridormi_task_agent_graph,
    default_soridormi_task_goal,
    build_soridormi_guarded_graph,
    require_soridormi_runtime_status,
    run_soridormi_guarded_dry_run_acceptance,
    run_soridormi_planning_acceptance,
    run_soridormi_runtime_cancellation_acceptance,
    run_soridormi_runtime_preflight,
    run_soridormi_task_agent_acceptance,
    soridormi_task_agent_graph_id,
)
from agent.app.tool_invocation import McpStreamableHttpInvoker


class SoridormiAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def _registry(self):
        manifest = (
            Path(__file__).resolve().parents[1]
            / "capabilities"
            / "soridormi.json"
        )
        with patch.dict(
            "os.environ",
            {"SORIDORMI_MCP_URL": "http://soridormi:8000/mcp"},
        ):
            return build_configured_registry([str(manifest)]).registry

    async def test_acceptance_probes_then_runs_status_and_planning(self) -> None:
        registry = self._registry()
        calls: list[tuple[str, dict[str, Any]]] = []

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append((tool, args))
            if tool == "soridormi.robot.get_status":
                return {"structuredContent": {"mode": "sim", "safe": True}}
            return {
                "structuredContent": {
                    "plan_id": "acceptance-plan",
                    "summary": "No-motion plan ready.",
                }
            }

        commands = [{"vx": 0.0, "vy": 0.0, "yaw": 0.0, "duration_s": 0.05}]
        trace = await run_soridormi_planning_acceptance(
            registry,
            commands=commands,
            invoker=McpStreamableHttpInvoker(registry, call=call),
            probe=probe,
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(
            calls,
            [
                ("soridormi.robot.get_status", {}),
                ("soridormi.motion.create_plan", {"commands": commands}),
            ],
        )

    async def test_acceptance_stops_when_probe_fails(self) -> None:
        registry = self._registry()
        calls = 0

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={"required.tool": {}},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            nonlocal calls
            calls += 1
            return {}

        with self.assertRaisesRegex(ValueError, "capability probe failed"):
            await run_soridormi_planning_acceptance(
                registry,
                commands=[],
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )

        self.assertEqual(calls, 0)

    async def test_acceptance_requires_planning_contract_fields(self) -> None:
        registry = self._registry()

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            if tool == "soridormi.robot.get_status":
                return {"structuredContent": {"safe": True}}
            return {"structuredContent": {"plan_id": "missing-summary"}}

        with self.assertRaisesRegex(RuntimeError, "missing required fields"):
            await run_soridormi_planning_acceptance(
                registry,
                commands=[
                    {
                        "vx": 0.0,
                        "vy": 0.0,
                        "yaw": 0.0,
                        "duration_s": 0.05,
                    }
                ],
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )

    async def test_task_agent_bridge_acceptance_previews_submits_and_monitors(
        self,
    ) -> None:
        registry = self._registry()
        calls: list[tuple[str, dict[str, Any]]] = []
        expected_ref = (
            f"chromie:{soridormi_task_agent_graph_id(default_soridormi_task_goal())}:submit"
        )

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append((tool, args))
            if tool == "soridormi.task.get_capabilities":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_capabilities.v1",
                        "mode": "sim",
                        "backend": "runtime",
                        "safe_idle": True,
                        "task_api_no_motion": True,
                        "ready_subsystems": ["task_registry"],
                        "task_types": [
                            {
                                "task_type": "perform_gesture",
                                "status": "dry_run_ready",
                            }
                        ],
                    }
                }
            if tool == "soridormi.task.preview":
                return {
                    "structuredContent": {
                        "preview_id": "preview-1",
                        "task_type": args["task_type"],
                        "accepted": True,
                        "status": "accepted",
                        "phase": "accepted",
                        "terminal": True,
                        "safe_idle": True,
                        "no_motion": True,
                        "persistent": False,
                        "would_record_task_on_submit": True,
                    }
                }
            if tool == "soridormi.task.submit":
                return {
                    "structuredContent": {
                        "task_id": "soridormi-task-1",
                        "client_task_ref": args["client_task_ref"],
                        "task_type": args["task_type"],
                        "accepted": True,
                        "status": "completed",
                        "phase": "completed",
                        "terminal": True,
                        "safe_idle": True,
                        "no_motion": True,
                        "deadline_at": 100.0,
                        "expired": False,
                    }
                }
            if tool == "soridormi.task.events":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_events.v1",
                        "task_id": "soridormi-task-1",
                        "client_task_ref": expected_ref,
                        "status": "completed",
                        "phase": "completed",
                        "terminal": True,
                        "safe_idle": True,
                        "deadline_at": 100.0,
                        "expired": False,
                        "events": [
                            {
                                "sequence": 1,
                                "kind": "task_completed",
                                "message": "No-motion task contract completed.",
                            }
                        ],
                        "returned_count": 1,
                        "latest_sequence": 1,
                        "next_after_sequence": 1,
                        "has_more": False,
                        "poll_recommendation": {"action": "stop_polling"},
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool}")

        trace = await run_soridormi_task_agent_acceptance(
            registry,
            goal=default_soridormi_task_goal(),
            invoker=McpStreamableHttpInvoker(registry, call=call),
            probe=probe,
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(
            [tool for tool, _ in calls],
            [
                "soridormi.task.get_capabilities",
                "soridormi.task.preview",
                "soridormi.task.submit",
                "soridormi.task.events",
            ],
        )
        self.assertEqual(
            calls[2][1]["client_task_ref"],
            expected_ref,
        )
        self.assertEqual(trace.result_map()["submit"].output["status"], "completed")

    async def test_task_agent_bridge_acceptance_requires_no_motion_api(
        self,
    ) -> None:
        registry = self._registry()
        calls: list[str] = []

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            if tool == "soridormi.task.get_capabilities":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_capabilities.v1",
                        "task_api_no_motion": False,
                        "task_types": [{"task_type": "perform_gesture"}],
                    }
                }
            if tool == "soridormi.task.preview":
                return {
                    "structuredContent": {
                        "preview_id": "preview-1",
                        "task_type": args["task_type"],
                        "accepted": True,
                        "status": "accepted",
                        "phase": "accepted",
                        "terminal": True,
                        "safe_idle": True,
                        "no_motion": True,
                        "persistent": False,
                        "would_record_task_on_submit": True,
                    }
                }
            if tool == "soridormi.task.submit":
                return {
                    "structuredContent": {
                        "task_id": "soridormi-task-1",
                        "client_task_ref": args["client_task_ref"],
                        "task_type": args["task_type"],
                        "accepted": True,
                        "status": "completed",
                        "phase": "completed",
                        "terminal": True,
                        "safe_idle": True,
                        "no_motion": True,
                        "deadline_at": 100.0,
                        "expired": False,
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool}")

        with self.assertRaisesRegex(RuntimeError, "task_api_no_motion=true"):
            await run_soridormi_task_agent_acceptance(
                registry,
                goal=default_soridormi_task_goal(),
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )
        self.assertEqual(calls, ["soridormi.task.get_capabilities"])

    async def test_task_agent_bridge_acceptance_requires_task_types_before_submit(
        self,
    ) -> None:
        registry = self._registry()
        calls: list[str] = []

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            if tool == "soridormi.task.get_capabilities":
                return {
                    "structuredContent": {
                        "schema_version": "soridormi.task_capabilities.v1",
                        "task_api_no_motion": True,
                        "task_types": [],
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool}")

        with self.assertRaisesRegex(RuntimeError, "missing task_types"):
            await run_soridormi_task_agent_acceptance(
                registry,
                goal=default_soridormi_task_goal(),
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )
        self.assertEqual(calls, ["soridormi.task.get_capabilities"])

    def test_task_agent_bridge_graph_uses_task_contract_tools(self) -> None:
        graph = build_soridormi_task_agent_graph(default_soridormi_task_goal())

        self.assertEqual(
            [node.tool for node in graph.nodes],
            [
                "soridormi.task.get_capabilities",
                "soridormi.task.preview",
                "soridormi.task.submit",
                "soridormi.task.events",
            ],
        )
        self.assertEqual(
            graph.graph_id,
            soridormi_task_agent_graph_id(default_soridormi_task_goal()),
        )

    async def test_runtime_preflight_requires_runtime_backend_and_ready_state(
        self,
    ) -> None:
        registry = self._registry()

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            self.assertEqual(tool, "soridormi.robot.get_status")
            return {
                "structuredContent": {
                    "backend": "runtime",
                    "mode": "sim",
                    "emergency_stop": False,
                    "robot_time": 12.5,
                }
            }

        report = await run_soridormi_runtime_preflight(
            registry,
            invoker=McpStreamableHttpInvoker(registry, call=call),
            probe=probe,
        )

        self.assertEqual(report.endpoint, "http://soridormi:8000/mcp")
        self.assertEqual(report.backend, "runtime")
        self.assertEqual(report.mode, "sim")
        self.assertFalse(report.emergency_stop)

    async def test_runtime_preflight_rejects_dry_run_endpoint(self) -> None:
        registry = self._registry()

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            return {
                "structuredContent": {
                    "backend": "local_tool_dry_run",
                    "mode": "sim",
                    "emergency_stop": False,
                }
            }

        with self.assertRaisesRegex(RuntimeError, "expected 'runtime'"):
            await run_soridormi_runtime_preflight(
                registry,
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )

    async def test_runtime_preflight_rejects_active_emergency_stop(self) -> None:
        registry = self._registry()

        async def probe(_registry):
            return [
                CapabilityProbeResult(
                    url="http://soridormi:8000/mcp",
                    expected_schemas={},
                    advertised_schemas={},
                )
            ]

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            return {
                "structuredContent": {
                    "backend": "runtime",
                    "mode": "sim",
                    "emergency_stop": True,
                }
            }

        with self.assertRaisesRegex(RuntimeError, "emergency_stop=false"):
            await run_soridormi_runtime_preflight(
                registry,
                invoker=McpStreamableHttpInvoker(registry, call=call),
                probe=probe,
            )

    def test_runtime_status_guard_rejects_missing_identity(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "backend is 'missing'"):
            require_soridormi_runtime_status(
                {"mode": "sim", "emergency_stop": False}
            )

    async def test_guarded_dry_run_executes_and_verifies_stop_fallback(self) -> None:
        registry = self._registry()
        calls: list[tuple[str, dict[str, Any]]] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append((tool, args))
            if tool == "soridormi.safety.monitor_motion":
                return {"structuredContent": {"ok": True, "event": None}}
            if tool == "soridormi.motion.execute_plan":
                if args["plan_id"] == "accepted-plan":
                    return {
                        "structuredContent": {
                            "completed": True,
                            "dry_run_only": True,
                        }
                    }
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "plan not found"}],
                }
            return {"structuredContent": {"stopped": True}}

        guarded, failure, emergency, status = (
            await run_soridormi_guarded_dry_run_acceptance(
                registry,
                plan_id="accepted-plan",
                invoker=McpStreamableHttpInvoker(registry, call=call),
            )
        )

        self.assertEqual(guarded.status, "success")
        self.assertEqual(failure.status, "failed")
        self.assertEqual(failure.result_map()["stop"].status, "success")
        self.assertIsNone(emergency)
        self.assertIsNone(status)
        self.assertEqual(
            [tool for tool, _ in calls],
            [
                "soridormi.safety.monitor_motion",
                "soridormi.motion.execute_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.motion.execute_plan",
                "soridormi.motion.stop",
            ],
        )

    async def test_guarded_dry_run_can_verify_emergency_stop_state(self) -> None:
        registry = self._registry()
        emergency_active = False

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            nonlocal emergency_active
            if tool == "soridormi.safety.monitor_motion":
                return {"structuredContent": {"ok": True, "event": None}}
            if tool == "soridormi.motion.execute_plan":
                if args["plan_id"] == "accepted-plan":
                    return {
                        "structuredContent": {
                            "completed": True,
                            "dry_run_only": True,
                        }
                    }
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "plan not found"}],
                }
            if tool == "soridormi.safety.emergency_stop":
                emergency_active = True
                return {"structuredContent": {"stopped": True}}
            if tool == "soridormi.robot.get_status":
                return {
                    "structuredContent": {
                        "emergency_stop": emergency_active,
                    }
                }
            return {"structuredContent": {"stopped": True}}

        _, _, emergency, status = (
            await run_soridormi_guarded_dry_run_acceptance(
                registry,
                plan_id="accepted-plan",
                invoker=McpStreamableHttpInvoker(registry, call=call),
                exercise_emergency_stop=True,
            )
        )

        self.assertEqual(emergency, {"stopped": True})
        self.assertEqual(status, {"emergency_stop": True})

    async def test_runtime_cancellation_uses_emergency_fallback_and_checks_state(
        self,
    ) -> None:
        registry = self._registry()
        calls: list[str] = []
        emergency_active = False
        emergency_applied = asyncio.Event()

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            nonlocal emergency_active
            calls.append(tool)
            if tool == "soridormi.safety.monitor_motion":
                return {"structuredContent": {"active": True}}
            if tool == "soridormi.motion.execute_plan":
                await emergency_applied.wait()
                return {"structuredContent": {"completed": False}}
            if tool == "soridormi.safety.emergency_stop":
                emergency_active = True
                emergency_applied.set()
                return {"structuredContent": {"stopped": True}}
            if tool == "soridormi.robot.get_status":
                return {
                    "structuredContent": {
                        "emergency_stop": emergency_active,
                    }
                }
            raise AssertionError(f"unexpected tool call: {tool}")

        trace, status = await run_soridormi_runtime_cancellation_acceptance(
            registry,
            plan_id="long-running-plan",
            invoker=McpStreamableHttpInvoker(registry, call=call),
            cancel_after_s=0,
        )

        self.assertEqual(trace.status, "cancelled")
        self.assertEqual(trace.result_map()["execute"].status, "cancelled")
        self.assertEqual(trace.result_map()["emergency"].status, "success")
        self.assertEqual(status, {"emergency_stop": True})
        self.assertEqual(
            calls,
            [
                "soridormi.safety.monitor_motion",
                "soridormi.motion.execute_plan",
                "soridormi.safety.emergency_stop",
                "soridormi.robot.get_status",
            ],
        )

    async def test_runtime_cancellation_rejects_completed_operation(self) -> None:
        registry = self._registry()

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            if tool == "soridormi.safety.monitor_motion":
                return {"structuredContent": {"active": True}}
            if tool == "soridormi.motion.execute_plan":
                return {"structuredContent": {"completed": True}}
            raise AssertionError(f"unexpected tool call: {tool}")

        with self.assertRaisesRegex(RuntimeError, "completed before cancellation"):
            await run_soridormi_runtime_cancellation_acceptance(
                registry,
                plan_id="short-plan",
                invoker=McpStreamableHttpInvoker(registry, call=call),
                cancel_after_s=0,
            )

    def test_guarded_graph_declares_normal_and_emergency_recovery(self) -> None:
        graph = build_soridormi_guarded_graph("plan-1")
        execute = graph.node_map()["execute"]

        self.assertEqual(execute.on_failure.target, "stop")
        self.assertEqual(execute.on_timeout.target, "stop")
        self.assertEqual(execute.on_event["safety_event"].target, "emergency")


if __name__ == "__main__":
    unittest.main()
