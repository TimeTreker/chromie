from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.app.capabilities.local import chromie_capability_bundle
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter


def test_weather_capability_declares_bounded_temporal_scope() -> None:
    bundle = chromie_capability_bundle()
    tool = next(
        tool
        for agent in bundle.agents
        for tool in agent.tools
        if tool.name == "chromie.weather.lookup"
    )
    scope = tool.llm_hints["semantic_scope"]
    assert "today" in scope["supported_temporal_scopes"]
    assert "annual" in scope["unsupported_temporal_scopes"]
    assert scope["scope_mismatch_policy"] == "clarify_or_unavailable_never_narrow"


def test_safe_read_step_uses_model_owned_specific_language() -> None:
    step = SimpleNamespace(skill_id="chromie.weather.lookup", args={})
    definition = SimpleNamespace(
        metadata={
            "effects": ["read_only", "external_read", "weather_lookup"],
            "safety_class": "safe_read",
            "pre_execution_speech_guidance": (
                "Generate natural model-owned wording for the specific lookup."
            ),
        }
    )
    for language in ("zh-CN", "en-US"):
        with pytest.raises(
            ValueError,
            match="read-only pre-execution wording must come from Response Composer",
        ):
            CanonicalPlanRuntimeAdapter._authoritative_step_text(
                step,
                language=language,
                definition=definition,
            )
    assert "pre_execution_acknowledgement" not in definition.metadata
    assert "pre_execution_speech_guidance" in definition.metadata


def test_goal_and_planner_prompts_forbid_scope_narrowing() -> None:
    goal_source = open("agent/app/goal_association.py", encoding="utf-8").read()
    fast_source = open("agent/app/fast_planner.py", encoding="utf-8").read()
    deep_source = open("agent/app/deep_planner.py", encoding="utf-8").read()
    assert "Never silently rewrite annual" in goal_source
    assert "Never silently narrow a goal" in fast_source
    assert "Never silently narrow a canonical goal" in deep_source
