from __future__ import annotations

from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver, GoalSegmentationModelOutput
from tests.cognitive_work_test_support import cognitive_work_request


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
    assert "afternoon" in scope["supported_temporal_scopes"]
    assert "evening" in scope["supported_temporal_scopes"]
    assert "tonight" in scope["supported_temporal_scopes"]
    assert "annual" in scope["unsupported_temporal_scopes"]
    assert scope["scope_mismatch_policy"] == "clarify_or_unavailable_never_narrow"
    assert tool.input_schema["properties"]["period"]["enum"] == [
        "day",
        "morning",
        "afternoon",
        "evening",
        "tonight",
    ]
    assert tool.output_schema["properties"]["forecast_period"]["properties"]["scope"]["enum"] == [
        "morning",
        "afternoon",
        "evening",
        "tonight",
    ]
    assert "forecast_period" in tool.output_schema["required"]


def test_safe_read_step_uses_model_owned_specific_language() -> None:
    bundle = chromie_capability_bundle()
    tool = next(
        tool
        for agent in bundle.agents
        for tool in agent.tools
        if tool.name == "chromie.weather.lookup"
    )
    assert "pre_execution_acknowledgement" not in tool.llm_hints
    assert "pre_execution_speech_guidance" in tool.llm_hints


def test_goal_and_planner_prompts_forbid_scope_narrowing() -> None:
    request = cognitive_work_request(
        sid="scope-contract",
        text="Compare annual weather.",
        language="en-US",
        context={
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": "goal-weather",
                        "description": "Compare annual weather.",
                        "bindings": [],
                    }
                ],
            },
            "fast_plan_resolution": {
                "disposition": "escalate",
                "coverage": "uncertain",
                "steps": [],
            },
        },
    )
    goal_prompt = GoalAssociationResolver(object())._build_prompt(
        request,
        [],
        output_type=GoalSegmentationModelOutput,
    )
    fast_prompt = FastPlannerResolver(object(), object())._prompt(
        request,
        [],
        response_schema={},
    )
    deep_prompt = DeepPlannerResolver(object(), object())._prompt(
        request,
        [],
        feedback=[],
        response_schema={},
        expected_goal_ids=["goal-weather"],
    )

    assert "Never silently rewrite annual" in goal_prompt
    assert "Never silently narrow a goal" in fast_prompt
    assert "Never silently narrow a canonical goal" in deep_prompt
    assert "calendar-date argument does not cover a finer day-part" in fast_prompt
    assert "calendar-date argument does not cover a finer day-part" in deep_prompt
    assert "canonical value morning, afternoon, evening, or tonight" in goal_prompt
    assert "do not emit separate location or date parameter_resolutions" in fast_prompt
    assert "do not emit separate location or date parameter_resolutions" in deep_prompt
