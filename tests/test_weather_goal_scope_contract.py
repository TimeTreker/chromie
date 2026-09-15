from __future__ import annotations

import json

import pytest

from agent.app.cognitive_core.goal_interpreter.model_interpreter import OllamaGoalInterpreter, _source_tokens
from agent.app.cognitive_core.goal_interpreter.schema import GoalInterpretationRequest

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
@pytest.mark.parametrize("explicit_provenance", [False, True])
@pytest.mark.parametrize("separate_query_scope,separate_location", [(True, True), (False, True), (False, False)])
async def test_weather_goal_to_planner_preserves_information_and_temporal_scope(mode, explicit_provenance, separate_query_scope, separate_location):
    request = CognitiveWorkRequest(
        sid="weather-contract", text="Check tomorrow morning's Chongqing weather.",
        language="en-US", interpretation_confidence=1.0,
        responsibilities=[{
            "local_ref": "r1", "outcome": "Acquire and explain tomorrow morning's Chongqing weather.",
            "output_mode": "information", "confidence": 1.0,
            "bindings": {**({"location": "Chongqing"} if separate_location else {}), **(
                {"date": "tomorrow", "period": "morning"} if separate_query_scope else {}
            )},
        }],
    )
    if not separate_query_scope:
        # Exercise the actual GI Host handoff before GA: time is retained in the
        # complete query, without manufacturing provider date/period bindings.
        source = GoalInterpretationRequest(text=request.text)
        schema = OllamaGoalInterpreter._goal_interpretation_response_schema(
            new_relationship_only=True, admitted_turn=request.text,
        )
        primary = {"confidence": 1.0, "responsibilities": [{
            "local_ref": "r1", "outcome": request.responsibilities[0].outcome,
            "output_mode": "information", "binding_items": ({"location": "Chongqing"} if separate_location else {}),
            "confidence": 1.0, "source_evidence": {
                "source_start_token_ref": "t0",
                "source_end_token_ref": _source_tokens(request.text)[-2]["ref"],
            },
        }], "coordination": [], "unresolved": []}
        interpreted = OllamaGoalInterpreter._validate_interpretation_content(
            source, json.dumps(primary), response_schema=schema,
        )
        request = request.model_copy(update={"responsibilities": interpreted.responsibilities})
    association_model = FakeOllama(create_goals(goal(
        request.responsibilities[0].outcome, mode,
        resource=resource_responsibility(
            kind="information", description="Chongqing weather", quantity="",
            source_status="provider_resolved", attributes=[
                *([binding("location", "location", "Chongqing")] if separate_location else []),
                *([binding("date", "date", "tomorrow"),
                   binding("period", "day_part", "morning")] if separate_query_scope else []),
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
    assert canonical.description == request.responsibilities[0].outcome
    goal_id = canonical.goal_id
    arguments = {"location": "Chongqing", "date": "tomorrow", "period": "morning"}
    planner_model = FakeOllama(multi_goal_plan(
        disposition="execute", coverage="complete", goal_summary=canonical.description,
        steps=[execute_step("weather", "chromie.weather.lookup", arguments, [goal_id], "Acquire the forecast.")],
        goal_outcomes={goal_id: execute_outcome(goal_id, ["weather"], "Acquire before explaining.")},
        goal_satisfaction=exact_satisfaction([goal_id]),
        parameter_resolutions=([{"step_id": "weather", "parameter": "location",
            "strategy": "user_supplied", "value": "Chongqing", "confidence": 1.0,
            "source_goal_ids": [goal_id]}] if explicit_provenance else []),
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
    for prompt in (fast_prompt, deep_prompt):
        assert "Compare annual weather." in prompt
        assert "Preserve exact advertised semantic scope" in prompt
        assert "never reinterpret or repair WHAT" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("text,outcome,location,bindings,accepted", [
    ("What is the weather today in Chongqing?", "what the weather is today in Chongqing", "Chongqing", {}, True),
    ("明天重庆天气怎么样？", "明天重庆天气怎么样", "重庆", {}, True),
    ("What is the weather in Paris?", "what the weather is in Chongqing", "Chongqing", {}, False),
    ("Check Chongqing weather and Beijing time.", "determine Beijing time", "Chongqing", {}, False),
    ("Check Chongqing weather.", "check Chongqing weather", "Chong", {}, False),
    ("Compare Beijing and Chongqing weather.", "compare Beijing and Chongqing weather", "Beijing", {"location": "Chongqing"}, False),
])
async def test_fast_query_literal_arguments_require_own_intent_and_original_source(text, outcome, location, bindings, accepted):
    # Exercise the production pre-GA boundary, where required inputs formerly
    # needed a duplicate same-name GI binding even for exact source literals.
    from tests.test_fast_planner_pr3 import WeatherCatalog, FastPlannerResolver as StreamingResolver

    request = CognitiveWorkRequest(text=text, responsibilities=[{
        "local_ref": "r1", "outcome": outcome, "output_mode": "information",
        "confidence": 1.0, "bindings": bindings,
    }], context={"user_turn_envelope": {
        "turn_id": "source-literal-test", "original_input": {"text": "  " + text + "\n"},
    }})
    from tests.test_fast_planner_pr3 import FakeOllama as StreamingFakeOllama
    candidate = StreamingFakeOllama({
        "disposition": "execute", "coverage": "complete",
        "covered_responsibility_refs": ["r1"], "activities": [{
            "activity_id": "query", "role": "capability",
            "capability_id": "chromie.weather.lookup", "args": {"location": location},
            "source_responsibility_refs": ["r1"], "timing": "sequential",
        }], "continuations": [], "confidence": 1.0, "unresolved": [],
        "reason_summary": "Acquire the requested information.",
    })
    advance = await StreamingResolver(candidate, WeatherCatalog()).resolve_advance(request)
    assert (advance.disposition == "execute") is accepted, advance.metadata
    if accepted:
        assert advance.activities[0].args["location"] == location
    else:
        assert advance.disposition == "unavailable"
        assert not advance.activities
    assert len(candidate.prompts) == 1


@pytest.mark.parametrize("value", [3, True, "3", "3 seconds", "0.2 m/s", {}, ["重庆"]])
def test_literal_intent_provenance_cannot_replace_typed_measurement_evidence(value):
    from agent.app.planner_grounding import literal_intent_argument

    source = "Use " + str(value)
    assert not literal_intent_argument(value, outcome=source, source_text=source)


@pytest.mark.parametrize("source,description,source_id,bound_location,accepted", [
    ("Check Chongqing weather.", "Check Chongqing weather.", "g1", None, True),
    ("Check Beijing weather.", "Check Chongqing weather.", "g1", None, False),
    ("Check Chongqing weather.", "Check Beijing weather.", "g1", None, False),
    ("Check Chongqing weather.", "Check Chongqing weather.", "g2", None, False),
    ("Compare Chongqing and Beijing weather.", "Compare Chongqing and Beijing weather.", "g1", "Beijing", False),
])
def test_canonical_literal_provenance_preserves_goal_ownership_and_explicit_bindings(source, description, source_id, bound_location, accepted):
    from agent.app.planner_model_contract import PlannerModelOutput
    from agent.app.planner_validation import validate_user_supplied_parameter_provenance

    output = PlannerModelOutput.model_validate(multi_goal_plan(
        disposition="execute", coverage="complete", goal_summary=description,
        steps=[execute_step("query", "chromie.weather.lookup", {"location": "Chongqing"}, ["g1"], "Acquire information.")],
        goal_outcomes={"g1": execute_outcome("g1", ["query"], "Acquire information.")},
        goal_satisfaction=exact_satisfaction(["g1"]),
        parameter_resolutions=[{"step_id": "query", "parameter": "location", "strategy": "user_supplied",
            "value": "Chongqing", "confidence": 1.0, "source_goal_ids": [source_id]}],
    ))
    bindings = ({"location": {"name": "location", "entity_type": "location", "value": bound_location}} if bound_location else {})
    goals = [{"goal_id": name, "description": description, "source_text": source, "object": {"bindings": bindings}}
             for name in ["g1", "g2"]]
    if accepted:
        validate_user_supplied_parameter_provenance(output, authoritative_goals=goals)
    else:
        with pytest.raises(ValueError, match="not present in authoritative"):
            validate_user_supplied_parameter_provenance(output, authoritative_goals=goals)
