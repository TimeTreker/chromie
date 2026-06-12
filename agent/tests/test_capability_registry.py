from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.capabilities.loader import build_configured_registry, parse_manifest_paths
from app.capabilities.local import build_chromie_registry
from app.capabilities.models import AgentManifest, CapabilityBundle, ToolCapability


def test_chromie_registry_lists_local_speech_tools() -> None:
    registry = build_chromie_registry()
    names = {tool.name for tool in registry.tools_for_llm()}
    assert "chromie.speak" in names
    assert "chromie.ask_confirmation" in names
    assert "chromie.listen" in names


def test_registry_merges_external_soridormi_manifest() -> None:
    soridormi = CapabilityBundle(
        source="soridormi-test",
        agents=[
            AgentManifest(
                agent_id="soridormi.motion",
                tools=[
                    ToolCapability(
                        name="soridormi.motion.execute_plan",
                        agent_id="soridormi.motion",
                        description="Execute a validated Soridormi motion plan.",
                        effects=["physical_motion"],
                        safety_class="physical_motion",
                    )
                ],
            )
        ],
    )
    registry = build_chromie_registry([soridormi])
    assert registry.get_tool("soridormi.motion.execute_plan").safety_class == "physical_motion"


def test_checked_in_soridormi_manifest_preserves_safety_contract() -> None:
    manifest_path = Path(__file__).resolve().parents[2] / "capabilities" / "soridormi.json"
    with patch.dict(
        os.environ,
        {"SORIDORMI_MCP_URL": "http://soridormi:8000/mcp"},
    ):
        registry = build_configured_registry([str(manifest_path)]).registry

    execute = registry.get_tool("soridormi.motion.execute_plan")
    named_list = registry.get_tool("soridormi.skill.list")
    named_plan = registry.get_tool("soridormi.skill.create_plan")
    named_execute = registry.get_tool("soridormi.skill.execute_plan")
    emergency_stop = registry.get_tool("soridormi.safety.emergency_stop")
    assert execute.confirmation.required
    assert execute.monitoring.requires_safety_monitor
    assert execute.execution.side_effect_free is False
    assert emergency_stop.safety_class == "safety_critical"
    assert emergency_stop.llm_visible is True
    assert named_list.safety_class == "safe_read"
    assert named_plan.input_schema["required"] == ["skill_id"]
    assert named_execute.confirmation.required
    assert named_execute.monitoring.requires_safety_monitor


def test_restricted_tools_are_hidden_from_llm() -> None:
    bundle = CapabilityBundle(
        source="unsafe-test",
        agents=[
            AgentManifest(
                agent_id="unsafe",
                tools=[
                    ToolCapability(
                        name="unsafe.raw_motor",
                        agent_id="unsafe",
                        safety_class="restricted",
                        llm_visible=True,
                    )
                ],
            )
        ],
    )
    registry = build_chromie_registry([bundle])
    assert "unsafe.raw_motor" not in {tool.name for tool in registry.tools_for_llm()}


def test_llm_context_mentions_robot_safety_rules_in_chinese() -> None:
    context = build_chromie_registry().llm_context(language="zh")
    assert "不要生成或调用原始电机" in context
    assert "chromie.speak" in context


def test_configured_registry_loads_manifest_directory_and_reports_sources() -> None:
    with TemporaryDirectory() as temporary_directory:
        manifest = {
            "source": "external-test",
            "agents": [
                {
                    "agent_id": "external.status",
                    "tools": [
                        {
                            "name": "external.status.read",
                            "agent_id": "external.status",
                            "effects": ["read_only"],
                            "safety_class": "safe_read",
                        }
                    ],
                }
            ],
        }
        manifest_path = Path(temporary_directory) / "external.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        configured = build_configured_registry([temporary_directory])

        assert configured.sources == ["chromie", "external-test"]
        assert configured.manifest_files == [str(manifest_path)]
        assert configured.registry.get_tool("external.status.read").safety_class == "safe_read"


def test_configured_registry_rejects_missing_manifest_path() -> None:
    try:
        build_configured_registry(["/definitely/missing/chromie-capabilities.json"])
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing capability manifest path unexpectedly loaded")


def test_parse_manifest_paths_ignores_blank_entries() -> None:
    assert parse_manifest_paths(" one.json, ,two.json ") == ["one.json", "two.json"]


def test_configured_registry_expands_manifest_environment_variables() -> None:
    with TemporaryDirectory() as temporary_directory:
        manifest_path = Path(temporary_directory) / "external.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "external-test",
                    "agents": [
                        {
                            "agent_id": "external.status",
                            "transport": {
                                "kind": "mcp_streamable_http",
                                "url": "${EXTERNAL_MCP_URL}",
                            },
                            "tools": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"EXTERNAL_MCP_URL": "http://robot:8000/mcp"}):
            configured = build_configured_registry([str(manifest_path)])

        assert (
            configured.registry.get_agent("external.status").transport.url
            == "http://robot:8000/mcp"
        )


def test_configured_registry_rejects_missing_manifest_environment_variable() -> None:
    with TemporaryDirectory() as temporary_directory:
        manifest_path = Path(temporary_directory) / "external.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "external-test",
                    "agents": [
                        {
                            "agent_id": "external.status",
                            "transport": {
                                "kind": "mcp_streamable_http",
                                "url": "${MISSING_MCP_URL}",
                            },
                            "tools": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            try:
                build_configured_registry([str(manifest_path)])
            except ValueError as exc:
                assert "requires non-empty environment variable MISSING_MCP_URL" in str(exc)
            else:
                raise AssertionError("missing manifest environment variable unexpectedly loaded")


def test_configured_registry_rejects_empty_manifest_environment_variable() -> None:
    with TemporaryDirectory() as temporary_directory:
        manifest_path = Path(temporary_directory) / "external.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "external-test",
                    "agents": [
                        {
                            "agent_id": "external.status",
                            "transport": {
                                "kind": "mcp_streamable_http",
                                "url": "${EMPTY_MCP_URL}",
                            },
                            "tools": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"EMPTY_MCP_URL": ""}):
            try:
                build_configured_registry([str(manifest_path)])
            except ValueError as exc:
                assert "requires non-empty environment variable EMPTY_MCP_URL" in str(exc)
            else:
                raise AssertionError("empty manifest environment variable unexpectedly loaded")
