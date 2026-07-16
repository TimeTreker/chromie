from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import patch

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
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.grants import ConfirmationGrantStore
from agent.app.task_graph.service import (
    TaskGraphConfirmationGrantRequest,
    TaskGraphService,
)
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
                    ToolCapability(
                        name="remote.stop",
                        agent_id="remote.control",
                        safety_class="safety_critical",
                        effects=["safety_control"],
                    ),
                    ToolCapability(
                        name="remote.emergency_stop",
                        agent_id="remote.control",
                        safety_class="safety_critical",
                        effects=["safety_control"],
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
                    "on_failure": {"strategy": "goto", "target": "emergency"},
                },
                {
                    "id": "emergency",
                    "tool": "remote.emergency_stop",
                    "type": "safety",
                },
            ],
        }
    )


class GuardedTaskGraphExecutionTests(unittest.IsolatedAsyncioTestCase):
    def _grant(self, service: TaskGraphService, graph: TaskGraph) -> str:
        return service.issue_confirmation_grant(
            TaskGraphConfirmationGrantRequest(
                graph=graph,
                confirmed_node_ids={"confirm"},
            )
        ).confirmation_grant

    async def test_disabled_guarded_execution_cannot_issue_grant(self) -> None:
        service = TaskGraphService(_registry())
        with self.assertRaisesRegex(RuntimeError, "guarded TaskGraph execution is disabled"):
            service.issue_confirmation_grant(
                TaskGraphConfirmationGrantRequest(
                    graph=_confirmed_write_graph(),
                    confirmed_node_ids={"confirm"},
                )
            )

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

        graph = _confirmed_write_graph()
        trace = await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(trace.status, "success")
        self.assertEqual(calls, ["remote.write"])
        self.assertTrue(trace.result_map()["confirm"].output["confirmed"])

    async def test_independent_guarded_non_physical_nodes_can_overlap(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"structuredContent": {"written": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "parallel-guarded-write",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "confirm",
                        "tool": "chromie.ask_confirmation",
                        "type": "confirmation",
                        "args": {"question": "Write both values?"},
                    },
                    {
                        "id": "write-a",
                        "tool": "remote.write",
                        "type": "action",
                        "depends_on": ["confirm"],
                    },
                    {
                        "id": "write-b",
                        "tool": "remote.write",
                        "type": "action",
                        "depends_on": ["confirm"],
                    },
                ],
            }
        )

        trace = await service.execute_guarded(
            graph,
            self._grant(service, graph),
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(peak, 2)
        self.assertEqual(
            [result.node_id for result in trace.node_results],
            ["confirm", "write-a", "write-b"],
        )

    async def test_parallel_flag_keeps_physical_nodes_sequential(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            return {"structuredContent": {"completed": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
            enable_parallel_execution=True,
            max_concurrency=4,
        )
        graph = _physical_graph()

        trace = await service.execute_guarded(
            graph,
            self._grant(service, graph),
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(peak, 1)

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
            graph = _confirmed_write_graph()
            grant = service.issue_confirmation_grant(
                TaskGraphConfirmationGrantRequest(graph=graph)
            ).confirmation_grant
            await service.execute_guarded(graph, grant)

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

        graph = _physical_graph()
        trace = await service.execute_guarded(graph, self._grant(service, graph))

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

        graph = _physical_graph()
        trace = await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(trace.status, "failed")
        self.assertEqual(calls, ["remote.monitor", "remote.emergency_stop"])
        self.assertIn("active safety monitor", trace.result_map()["move"].error or "")
        self.assertEqual(trace.result_map()["emergency"].status, "success")
        self.assertTrue(any(event.type == "emergency_fallback" for event in trace.events))

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
            graph = _physical_graph()
            await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(calls, 0)

    async def test_confirmation_grant_is_single_use_and_graph_bound(self) -> None:
        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            return {"structuredContent": {"written": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = _confirmed_write_graph()
        grant = self._grant(service, graph)

        await service.execute_guarded(graph, grant)
        with self.assertRaisesRegex(ValueError, "invalid or already used"):
            await service.execute_guarded(graph, grant)

        other_graph = graph.model_copy(update={"graph_id": "different"}, deep=True)
        other_grant = self._grant(service, graph)
        with self.assertRaisesRegex(ValueError, "does not match"):
            await service.execute_guarded(other_graph, other_grant)

    async def test_cancellation_cancels_inflight_motion_and_runs_emergency_stop(self) -> None:
        calls: list[str] = []
        motion_started = asyncio.Event()
        emergency_applied = asyncio.Event()
        motion_transport_cancelled = False

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal motion_transport_cancelled
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                motion_started.set()
                try:
                    await emergency_applied.wait()
                except asyncio.CancelledError:
                    motion_transport_cancelled = True
                    raise
                return {"structuredContent": {"completed": False}}
            if tool == "remote.emergency_stop":
                emergency_applied.set()
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        graph = _physical_graph()
        execution = asyncio.create_task(
            service.execute_guarded(graph, self._grant(service, graph))
        )
        await asyncio.wait_for(motion_started.wait(), timeout=1.0)

        cancellation = service.cancel_execution(graph.graph_id)
        trace = await asyncio.wait_for(execution, timeout=1.0)

        self.assertTrue(cancellation.cancellation_requested)
        self.assertEqual(trace.status, "cancelled")
        self.assertEqual(calls, ["remote.monitor", "remote.move", "remote.emergency_stop"])
        self.assertEqual(trace.result_map()["move"].status, "cancelled")
        self.assertEqual(trace.result_map()["emergency"].status, "success")
        self.assertFalse(motion_transport_cancelled)
        self.assertFalse(service.cancel_execution(graph.graph_id).cancellation_requested)

    async def test_physical_failure_runs_emergency_stop(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "motor controller fault"}],
                }
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        graph = _physical_graph()

        trace = await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(trace.status, "failed")
        self.assertEqual(calls, ["remote.monitor", "remote.move", "remote.emergency_stop"])
        self.assertEqual(trace.result_map()["move"].status, "failed_fatal")
        self.assertEqual(trace.result_map()["emergency"].status, "success")

    async def test_emergency_fallback_retries_transient_transport_failure(self) -> None:
        emergency_attempts = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ):
            nonlocal emergency_attempts
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "motion fault"}],
                }
            if tool == "remote.emergency_stop":
                emergency_attempts += 1
                if emergency_attempts == 1:
                    raise ConnectionError("transient transport reset")
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        registry.get_tool("remote.emergency_stop").execution.idempotent = True
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        graph = _physical_graph()

        trace = await service.execute_guarded(
            graph,
            self._grant(service, graph),
        )

        self.assertEqual(trace.result_map()["emergency"].status, "success")
        self.assertEqual(trace.result_map()["emergency"].attempts, 2)

    async def test_normal_failure_uses_stop_with_emergency_path_declared(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "motion fault"}],
                }
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        payload = _physical_graph().model_dump(mode="json")
        move = next(node for node in payload["nodes"] if node["id"] == "move")
        move["on_failure"] = {"strategy": "goto", "target": "stop"}
        move["on_event"] = {
            "safety_event": {"strategy": "goto", "target": "emergency"}
        }
        payload["nodes"].append(
            {
                "id": "stop",
                "tool": "remote.stop",
                "type": "safety",
            }
        )
        graph = TaskGraph.model_validate(payload)

        trace = await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(trace.status, "failed")
        self.assertEqual(calls, ["remote.monitor", "remote.move", "remote.stop"])
        self.assertEqual(trace.result_map()["stop"].status, "success")
        self.assertNotIn("emergency", trace.result_map())
        self.assertTrue(any(event.type == "stop_fallback" for event in trace.events))

    async def test_timeout_uses_on_timeout_stop(self) -> None:
        calls: list[str] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                raise TimeoutError("motion timed out")
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        payload = _physical_graph().model_dump(mode="json")
        move = next(node for node in payload["nodes"] if node["id"] == "move")
        move["on_timeout"] = {"strategy": "goto", "target": "stop"}
        payload["nodes"].append(
            {
                "id": "stop",
                "tool": "remote.stop",
                "type": "safety",
            }
        )
        graph = TaskGraph.model_validate(payload)

        trace = await service.execute_guarded(graph, self._grant(service, graph))

        self.assertEqual(trace.status, "failed")
        self.assertEqual(calls, ["remote.monitor", "remote.move", "remote.stop"])
        self.assertEqual(trace.result_map()["move"].status, "timeout")
        self.assertEqual(trace.result_map()["stop"].status, "success")
        self.assertNotIn("emergency", trace.result_map())

    async def test_cancellation_uses_emergency_path_not_normal_stop(self) -> None:
        calls: list[str] = []
        motion_started = asyncio.Event()
        emergency_applied = asyncio.Event()

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float):
            calls.append(tool)
            if tool == "remote.monitor":
                return {"structuredContent": {"active": True}}
            if tool == "remote.move":
                motion_started.set()
                await emergency_applied.wait()
                return {"structuredContent": {"completed": False}}
            if tool == "remote.emergency_stop":
                emergency_applied.set()
            return {"structuredContent": {"stopped": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            guarded_invoker=McpStreamableHttpInvoker(registry, call=call),
            allow_physical_motion=True,
        )
        payload = _physical_graph().model_dump(mode="json")
        payload["graph_id"] = "physical-cancel-with-stop"
        move = next(node for node in payload["nodes"] if node["id"] == "move")
        move["on_failure"] = {"strategy": "goto", "target": "stop"}
        move["on_event"] = {
            "safety_event": {"strategy": "goto", "target": "emergency"}
        }
        payload["nodes"].append(
            {
                "id": "stop",
                "tool": "remote.stop",
                "type": "safety",
            }
        )
        graph = TaskGraph.model_validate(payload)
        execution = asyncio.create_task(
            service.execute_guarded(graph, self._grant(service, graph))
        )
        await asyncio.wait_for(motion_started.wait(), timeout=1.0)

        service.cancel_execution(graph.graph_id)
        trace = await asyncio.wait_for(execution, timeout=1.0)

        self.assertEqual(trace.status, "cancelled")
        self.assertEqual(
            calls,
            ["remote.monitor", "remote.move", "remote.emergency_stop"],
        )
        self.assertNotIn("stop", trace.result_map())
        self.assertEqual(trace.result_map()["emergency"].status, "success")

    def test_confirmation_grant_expires(self) -> None:
        store = ConfirmationGrantStore()
        graph = _confirmed_write_graph()
        with patch(
            "agent.app.task_graph.grants.time.time",
            side_effect=[100.0, 102.0],
        ):
            token, _ = store.issue(graph, {"confirm"}, ttl_s=1)
            with self.assertRaisesRegex(ValueError, "expired"):
                store.consume(token, graph)


if __name__ == "__main__":
    unittest.main()
