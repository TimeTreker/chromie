from __future__ import annotations

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
