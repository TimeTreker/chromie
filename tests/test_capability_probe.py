from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
    TransportSpec,
)
from agent.app.capabilities.probe import (
    _collect_tool_pages,
    _schema_satisfies_contract,
    probe_mcp_capabilities,
)
from agent.app.probe_capabilities import _run as run_probe_cli


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="probe-test",
                agents=[
                    AgentManifest(
                        agent_id="remote.robot",
                        transport=TransportSpec(
                            kind="mcp_streamable_http",
                            url="http://robot:8000/mcp",
                        ),
                        tools=[
                            ToolCapability(
                                name="remote.status",
                                agent_id="remote.robot",
                            ),
                            ToolCapability(
                                name="remote.plan",
                                agent_id="remote.robot",
                                safety_class="planning_only",
                            ),
                        ],
                    )
                ],
            )
        ]
    )


class CapabilityProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_accepts_endpoint_with_all_manifest_tools(self) -> None:
        async def list_tools(
            url: str,
            timeout_s: float,
        ) -> dict[str, dict]:
            self.assertEqual(url, "http://robot:8000/mcp")
            self.assertEqual(timeout_s, 3.0)
            return {
                "remote.status": {},
                "remote.plan": {},
                "remote.diagnostics": {},
            }

        [result] = await probe_mcp_capabilities(
            _registry(),
            timeout_s=3.0,
            list_tools=list_tools,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.missing_tools, frozenset())
        self.assertEqual(result.extra_tools, frozenset({"remote.diagnostics"}))

    async def test_probe_reports_manifest_tools_missing_from_server(self) -> None:
        async def list_tools(url: str, timeout_s: float) -> dict[str, dict]:
            return {"remote.status": {}}

        [result] = await probe_mcp_capabilities(
            _registry(),
            list_tools=list_tools,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.missing_tools, frozenset({"remote.plan"}))

    async def test_probe_can_exclude_tools_by_effect(self) -> None:
        registry = _registry()
        registry.get_tool("remote.plan").effects = ["test_control"]

        async def list_tools(url: str, timeout_s: float) -> dict[str, dict]:
            return {"remote.status": {}}

        [result] = await probe_mcp_capabilities(
            registry,
            list_tools=list_tools,
            excluded_effects=frozenset({"test_control"}),
        )

        self.assertTrue(result.ok)
        self.assertEqual(set(result.expected_schemas), {"remote.status"})

    async def test_probe_reports_server_schema_weaker_than_manifest(self) -> None:
        registry = _registry()
        registry.get_tool("remote.plan").input_schema = {
            "type": "object",
            "properties": {
                "distance": {
                    "type": "number",
                    "maximum": 1,
                }
            },
        }

        async def list_tools(url: str, timeout_s: float) -> dict[str, dict]:
            return {
                "remote.status": {},
                "remote.plan": {
                    "type": "object",
                    "properties": {
                        "distance": {
                            "type": "number",
                        }
                    },
                },
            }

        [result] = await probe_mcp_capabilities(
            registry,
            list_tools=list_tools,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.schema_mismatches, frozenset({"remote.plan"}))


    async def test_probe_cli_reports_connection_errors_without_traceback(self) -> None:
        with patch.dict(os.environ, {"SORIDORMI_MCP_URL": "http://127.0.0.1:1/mcp"}):
            rc = await run_probe_cli(
                ["capabilities/soridormi.json"],
                timeout_s=0.01,
                excluded_effects=frozenset({"test_control"}),
            )

        self.assertEqual(rc, 1)

    async def test_probe_requires_an_mcp_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "no MCP Streamable HTTP endpoints"):
            await probe_mcp_capabilities(CapabilityRegistry())

    async def test_collect_tool_pages_follows_next_cursor(self) -> None:
        calls: list[str | None] = []

        async def list_page(cursor: str | None):
            calls.append(cursor)
            if cursor is None:
                return {"remote.status": {}}, "page-2"
            return {"remote.plan": {}}, None

        schemas = await _collect_tool_pages(list_page)

        self.assertEqual(calls, [None, "page-2"])
        self.assertEqual(set(schemas), {"remote.status", "remote.plan"})

    async def test_collect_tool_pages_rejects_repeated_cursor(self) -> None:
        async def list_page(cursor: str | None):
            return {}, "same-cursor"

        with self.assertRaisesRegex(ValueError, "repeated pagination cursor"):
            await _collect_tool_pages(list_page)

    def test_schema_comparison_handles_unordered_constraints(self) -> None:
        expected = {
            "type": "object",
            "required": ["vx", "duration_s"],
            "properties": {
                "vx": {"type": "number", "minimum": -0.2, "maximum": 0.2},
            },
        }
        actual = {
            "type": "object",
            "required": ["duration_s", "vx"],
            "properties": {
                "vx": {"type": "number", "minimum": -0.2, "maximum": 0.2},
            },
        }

        self.assertTrue(_schema_satisfies_contract(actual, expected))


    def test_schema_comparison_allows_unadvertised_optional_property_when_extras_allowed(self) -> None:
        expected = {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "chromie_intent": {
                    "type": "object",
                    "properties": {
                        "execution_mode": {"type": "string", "const": "proposed"},
                    },
                    "required": ["execution_mode"],
                },
            },
            "required": ["skill_id"],
        }
        actual = {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
            },
            "required": ["skill_id"],
        }

        self.assertTrue(_schema_satisfies_contract(actual, expected))

    def test_schema_comparison_rejects_unadvertised_optional_property_when_extras_forbidden(self) -> None:
        expected = {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "chromie_intent": {"type": "object"},
            },
            "required": ["skill_id"],
        }
        actual = {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
            },
            "required": ["skill_id"],
            "additionalProperties": False,
        }

        self.assertFalse(_schema_satisfies_contract(actual, expected))

    async def test_probe_reports_optional_schema_warning_without_failing(self) -> None:
        registry = _registry()
        registry.get_tool("remote.plan").input_schema = {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "chromie_intent": {"type": "object"},
            },
            "required": ["skill_id"],
        }

        async def list_tools(url: str, timeout_s: float) -> dict[str, dict]:
            return {
                "remote.status": {},
                "remote.plan": {
                    "type": "object",
                    "properties": {
                        "skill_id": {"type": "string"},
                    },
                    "required": ["skill_id"],
                },
            }

        [result] = await probe_mcp_capabilities(
            registry,
            list_tools=list_tools,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.schema_mismatches, frozenset())
        self.assertIn("remote.plan", result.schema_warnings)
        self.assertIn("chromie_intent", result.schema_warnings["remote.plan"][0])

    def test_schema_comparison_rejects_incompatible_stricter_constraints(self) -> None:
        expected = {
            "type": "object",
            "required": ["vx"],
            "properties": {
                "vx": {"type": "number", "maximum": 0.2},
            },
        }
        actual = {
            "type": "object",
            "required": ["vx", "mode"],
            "properties": {
                "vx": {"type": "number", "maximum": 0.1},
            },
        }

        self.assertFalse(_schema_satisfies_contract(actual, expected))


if __name__ == "__main__":
    unittest.main()
