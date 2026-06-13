from __future__ import annotations

import unittest
from typing import Any

from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ConfirmationPolicy,
    MonitoringPolicy,
    ToolCapability,
    TransportSpec,
)
from agent.app.tool_invocation import McpStreamableHttpInvoker, ToolInvocationContext


def _registry():
    bundle = CapabilityBundle(
        source="soridormi-test",
        agents=[
            AgentManifest(
                agent_id="soridormi.robot",
                transport=TransportSpec(kind="mcp_streamable_http", url="http://soridormi:8000/mcp"),
                tools=[
                    ToolCapability(
                        name="soridormi.robot.get_status",
                        agent_id="soridormi.robot",
                        safety_class="safe_read",
                        effects=["read_only"],
                    ),
                    ToolCapability(
                        name="soridormi.motion.execute_plan",
                        agent_id="soridormi.robot",
                        safety_class="physical_motion",
                        effects=["physical_motion"],
                        confirmation=ConfirmationPolicy(required=True),
                        monitoring=MonitoringPolicy(requires_safety_monitor=True),
                    ),
                    ToolCapability(
                        name="soridormi.safety.emergency_stop",
                        agent_id="soridormi.robot",
                        safety_class="safety_critical",
                        effects=["safety_control"],
                    ),
                    ToolCapability(
                        name="soridormi.raw_motor",
                        agent_id="soridormi.robot",
                        safety_class="restricted",
                    ),
                ],
            )
        ],
    )
    return build_chromie_registry([bundle])


class McpToolInvokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_started_callback_runs_at_dispatch(self) -> None:
        events: list[str] = []

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            events.append(f"call:{tool}")
            return {"structuredContent": {"standing": True}}

        invoker = McpStreamableHttpInvoker(
            _registry(),
            call=call,
            call_started=lambda tool: events.append(f"started:{tool}"),
        )

        outcome = await invoker.invoke("soridormi.robot.get_status", {})

        self.assertEqual(outcome.status, "success")
        self.assertEqual(
            events,
            [
                "started:soridormi.robot.get_status",
                "call:soridormi.robot.get_status",
            ],
        )

    async def test_safe_read_uses_manifest_transport_and_structured_content(self) -> None:
        calls: list[tuple[str, str, dict[str, Any], float]] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append((url, tool, args, timeout_s))
            return {"structuredContent": {"standing": True, "mode": "sim"}, "content": []}

        outcome = await McpStreamableHttpInvoker(_registry(), call=call).invoke(
            "soridormi.robot.get_status", {}
        )

        self.assertEqual(outcome.status, "success")
        self.assertEqual(outcome.output["mode"], "sim")
        self.assertEqual(calls[0][0], "http://soridormi:8000/mcp")

    async def test_physical_motion_requires_all_execution_proofs(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"completed": True}}

        invoker = McpStreamableHttpInvoker(_registry(), call=call)
        denied = await invoker.invoke(
            "soridormi.motion.execute_plan",
            {"plan_id": "plan-1"},
            context=ToolInvocationContext(allow_side_effects=True, confirmed=True),
        )
        allowed = await invoker.invoke(
            "soridormi.motion.execute_plan",
            {"plan_id": "plan-1"},
            context=ToolInvocationContext(
                allow_side_effects=True,
                confirmed=True,
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(denied.status, "failed_fatal")
        self.assertIn("safety monitor", denied.error or "")
        self.assertEqual(allowed.status, "success")
        self.assertEqual(calls, 1)

    async def test_restricted_and_safety_critical_tools_are_guarded(self) -> None:
        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": "{\"stopped\": true}"}]}

        invoker = McpStreamableHttpInvoker(_registry(), call=call)
        restricted = await invoker.invoke("soridormi.raw_motor", {})
        denied_stop = await invoker.invoke("soridormi.safety.emergency_stop", {})
        allowed_stop = await invoker.invoke(
            "soridormi.safety.emergency_stop",
            {},
            context=ToolInvocationContext(allow_safety_controls=True),
        )

        self.assertEqual(restricted.status, "failed_fatal")
        self.assertEqual(denied_stop.status, "failed_fatal")
        self.assertEqual(allowed_stop.output, {"stopped": True})

    async def test_mcp_tool_error_and_timeout_are_normalized(self) -> None:
        async def error_call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            return {"isError": True, "content": [{"type": "text", "text": "robot unavailable"}]}

        async def timeout_call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            raise TimeoutError("MCP deadline exceeded")

        error_outcome = await McpStreamableHttpInvoker(_registry(), call=error_call).invoke(
            "soridormi.robot.get_status", {}
        )
        timeout_outcome = await McpStreamableHttpInvoker(_registry(), call=timeout_call).invoke(
            "soridormi.robot.get_status", {}
        )

        self.assertEqual(error_outcome.status, "failed_fatal")
        self.assertEqual(error_outcome.error, "robot unavailable")
        self.assertEqual(timeout_outcome.status, "timeout")


if __name__ == "__main__":
    unittest.main()
