from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agent.app.capabilities.loader import build_configured_registry
from agent.app.capabilities.probe import CapabilityProbeResult
from agent.app.soridormi_acceptance import run_soridormi_planning_acceptance
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


if __name__ == "__main__":
    unittest.main()
