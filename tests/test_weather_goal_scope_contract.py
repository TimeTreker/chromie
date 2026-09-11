from __future__ import annotations

import pytest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver
from agent.app.goal_association_contract import GoalSegmentationModelOutput
from agent.app import goal_association_prompt as ga_prompt
from agent.app import planner_prompt
from tests.cognitive_work_test_support import cognitive_work_request
from tests.test_goal_association_pr2 import FakeOllama, binding, create_goals, goal, resource_responsibility
from tests.test_fast_planner_pr3 import execute_step, execute_outcome, exact_satisfaction, multi_goal_plan
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest


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
    assert "night" in scope["supported_temporal_scopes"]
    assert "annual" in scope["unsupported_temporal_scopes"]
    assert scope["scope_mismatch_policy"] == "clarify_or_unavailable_never_narrow"
    assert "person or object is present" in tool.llm_hints["when_not_to_use"]
    assert "direct visual or auditory observation" in tool.llm_hints["when_not_to_use"]
    assert tool.input_schema["properties"]["period"]["enum"] == [
        "day",
        "morning",
        "afternoon",
        "evening",
        "night",
    ]
    assert tool.output_schema["properties"]["forecast_period"]["properties"]["scope"]["enum"] == [
        "morning",
        "afternoon",
        "evening",
        "night",
    ]
    assert "forecast_period" in tool.output_schema["required"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["information", "speech"])
async def test_weather_goal_to_planner_preserves_information_and_temporal_scope(mode):
    request = CognitiveWorkRequest(
        sid="weather-contract", text="Check tomorrow morning's Chongqing weather.",
        language="en-US", interpretation_confidence=1.0,
        responsibilities=[{
            "local_ref": "r1", "outcome": "Acquire and explain tomorrow morning's Chongqing weather.",
            "output_mode": "information", "confidence": 1.0,
            "bindings": {"location": "Chongqing", "date": "tomorrow", "period": "morning"},
        }],
    )
    association_model = FakeOllama(create_goals(goal(
        request.responsibilities[0].outcome, mode,
        resource=resource_responsibility(
            kind="information", description="Chongqing weather", quantity="",
            source_status="provider_resolved", attributes=[
                binding("location", "location", "Chongqing"),
                binding("date", "date", "tomorrow"),
                binding("period", "day_part", "morning"),
            ],
        ),
    )))
    resolution = await GoalAssociationResolver(association_model).resolve(request)
    if mode == "speech":
        assert resolution.resolution_status != "resolved"
        assert not resolution.new_goals
        return
    assert resolution.resolution_status == "resolved"
    assert len(association_model.prompts) == 1
    canonical = resolution.new_goals[0]
    assert canonical.metadata["output_mode"] == "information"
    assert canonical.source_responsibility_refs == ["r1"]
    goal_id = canonical.goal_id
    arguments = {"location": "Chongqing", "date": "tomorrow", "period": "morning"}
    planner_model = FakeOllama(multi_goal_plan(
        disposition="execute", coverage="complete", goal_summary=canonical.description,
        steps=[execute_step("weather", "chromie.weather.lookup", arguments, [goal_id], "Acquire the forecast.")],
        goal_outcomes={goal_id: execute_outcome(goal_id, ["weather"], "Acquire before explaining.")},
        goal_satisfaction=exact_satisfaction([goal_id]),
    ))
    tool = next(t for a in chromie_capability_bundle().agents for t in a.tools if t.name == "chromie.weather.lookup")

    class WeatherCatalog:
        async def prompt_entries(self, **kwargs):
            return [CatalogCapability(
                capability_id=tool.name, agent_id="chromie.weather", description=tool.description,
                input_schema=tool.input_schema, output_schema=tool.output_schema,
                available=True, interaction_executable=True, hints=tool.llm_hints,
            )]

    request.context["goal_association_resolution"] = resolution.model_dump(mode="json")
    plan = await FastPlannerResolver(planner_model, WeatherCatalog()).resolve(request)
    assert plan.disposition == "execute", plan.metadata
    assert len(planner_model.prompts) == 1
    assert plan.steps[0].args == arguments
    assert plan.steps[0].source_goal_ids == [goal_id]
    assert not plan.response_text


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
    goal_prompt = ga_prompt.build_prompt(
        request,
        [],
        output_type=GoalSegmentationModelOutput,
    )
    fast_prompt = planner_prompt.fast_plan_prompt(
        request,
        [],
        response_schema={},
    )
    deep_prompt = planner_prompt.deep_plan_prompt(
        request,
        [],
        response_schema={},
        expected_goal_ids=["goal-weather"],
    )

    assert "Never narrow broader temporal scope" in goal_prompt
    assert "Never silently narrow a goal" in fast_prompt
    assert "Never silently narrow a canonical goal" in deep_prompt
    assert "Capability domains are not interchangeable" in fast_prompt
    assert "Capability domains are not interchangeable" in deep_prompt
    assert "must never rewrite the Goal" in fast_prompt
    assert "never rewrites the canonical Goal or silently narrows its scope" in deep_prompt
    assert "do not emit separate parameter_resolutions for them" in fast_prompt
    assert "do not emit separate parameter_resolutions for them" in deep_prompt
