from __future__ import annotations

import json

import pytest

from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter, _source_tokens
from agent.app.cognitive_core.user_meaning_interpreter.schema import UserMeaningInterpretationRequest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver
from agent.app.goal_association_contract import GoalSegmentationModelOutput
from agent.app import goal_association_prompt as ga_prompt
from agent.app import planner_prompt
from tests.cognitive_work_test_support import cognitive_work_request
from tests.test_goal_association_pr2 import FakeOllama, create_goals, intent_goal
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
    derivation = tool.llm_hints["argument_derivation"]["location_context"]
    assert derivation["source_argument"] == "location"
    assert derivation["require_exact_source_value"] is True
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
@pytest.mark.parametrize("mode_override", [None, "speech"])
@pytest.mark.parametrize("foreign_quote", [False, True])
@pytest.mark.parametrize("text,location,date,period", [
    ("Check tomorrow morning's Chongqing weather.", "Chongqing", "tomorrow", "morning"),
    ("查一下明天早上重庆的天气。", "重庆", "tomorrow", "morning"),
])
async def test_weather_goal_to_planner_preserves_information_and_temporal_scope(
    mode_override, foreign_quote, text, location, date, period,
):
    source = UserMeaningInterpretationRequest(text=text)
    schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(admitted_turn=text)
    primary = {"confidence": 1.0, "responsibilities": [{
        "local_ref": "r1", "outcome": text, "output_mode": "information", "confidence": 1.0,
        "continuity_scope": "goal",
        "source_evidence": {"source_start_token_ref": "t0",
            "source_end_token_ref": _source_tokens(text)[-1]["ref"]},
    }], "cognitive_requests": [
        {"authority": "goal_association", "responsibility_refs": ["r1"],
         "reason_summary": "Check canonical continuity."},
        {"authority": "social_cognition", "responsibility_refs": ["r1"],
         "reason_summary": "Consider interaction."},
        {"authority": "planner", "responsibility_refs": ["r1"],
         "reason_summary": "Meaning is ready for HOW."},
    ], "meaning_uncertainties": []}
    interpreted = OllamaUserMeaningInterpreter._validate_interpretation_content(
        source, json.dumps(primary), response_schema=schema,
    )
    request = CognitiveWorkRequest(sid="weather-contract", text=text,
        responsibilities=interpreted.responsibilities, interpretation_confidence=1.0)
    assert not request.responsibilities[0].bindings
    ga_wire = intent_goal(text, "information")
    if mode_override:
        ga_wire["output_mode"] = mode_override
    association_model = FakeOllama(create_goals(ga_wire))
    resolution = await GoalAssociationResolver(association_model).resolve(request)
    assert len(association_model.prompts) == 1
    if mode_override:
        assert resolution.resolution_status == "fail_closed"
        assert not resolution.new_goals
        return
    assert resolution.resolution_status == "resolved"
    canonical = resolution.new_goals[0]
    assert canonical.metadata["output_mode"] == "information"
    assert canonical.source_responsibility_refs == ["r1"]
    assert canonical.description == text
    assert not canonical.object.get("bindings")
    goal_id = canonical.goal_id
    arguments = {"location": location, "date": date, "period": period}
    planner_model = FakeOllama(multi_goal_plan(
        disposition="execute", coverage="complete", goal_summary=text,
        steps=[execute_step("weather", "chromie.weather.lookup", arguments, [goal_id], "Acquire the forecast.")],
        goal_outcomes={goal_id: execute_outcome(goal_id, ["weather"], "Acquire before explaining.")},
        goal_satisfaction=exact_satisfaction([goal_id]),
        parameter_resolutions=[{"step_id": "weather", "parameter": name,
            "strategy": "semantic_realization", "value": value, "confidence": 1.0,
            "source_quote": "Check next year's Paris weather." if foreign_quote else text,
            "source_goal_ids": [goal_id]} for name, value in arguments.items()],
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
    assert len(planner_model.prompts) == 1
    if foreign_quote:
        assert plan.disposition == "escalate"
        assert not plan.steps
    else:
        assert plan.disposition == "execute", plan.metadata
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

    assert "Host supplies descriptions and IDs" in goal_prompt
    for prompt in (fast_prompt, deep_prompt):
        assert "Compare annual weather." in prompt
        assert "Preserve exact advertised semantic scope" in prompt
        assert "never reinterpret or repair WHAT" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("text,outcome,location,bindings,accepted", [
    ("What is the weather today in Chongqing?", "what the weather is today in Chongqing", "Chongqing", {}, True),
    ("明天重庆天气怎么样？", "明天重庆天气怎么样", "重庆", {}, True),
    ("Can you help me check the weather today in chongqing?", "Provide the current weather conditions for Chongqing as of today.", "chongqing", {}, True),
    ("What is the weather in Paris?", "what the weather is in Chongqing", "Chongqing", {}, False),
    ("Check Chongqing weather and Beijing time.", "determine Beijing time", "Chongqing", {}, False),
    ("Check Chongqing weather.", "check Chongqing weather", "Chong", {}, False),
    ("Compare Beijing and Chongqing weather.", "compare Beijing and Chongqing weather", "Beijing", {"location": "Chongqing"}, False),
])
async def test_fast_query_literal_arguments_require_own_intent_and_original_source(text, outcome, location, bindings, accepted):
    # Exercise the production pre-GA boundary, where required inputs formerly
    # needed a duplicate same-name UMI binding even for exact source literals.
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


@pytest.mark.asyncio
@pytest.mark.parametrize("location_context,accepted", [
    ({"locality": "重庆", "country": "中国"}, True),
    ({"locality": "成都", "country": "中国"}, False),
])
async def test_weather_location_context_derives_from_grounded_location(
    location_context, accepted,
):
    from tests.test_fast_planner_pr3 import WeatherCatalog, FastPlannerResolver as StreamingResolver
    from tests.test_fast_planner_pr3 import FakeOllama as StreamingFakeOllama

    text = "重庆今天天气怎么样？"
    request = CognitiveWorkRequest(
        text=text,
        responsibilities=[{
            "local_ref": "r1", "outcome": text, "output_mode": "information",
            "confidence": 1.0, "bindings": {},
            "source_evidence": {
                "source_start_token_ref": "t0",
                "source_end_token_ref": _source_tokens(text)[-1]["ref"],
            },
        }],
        context={"user_turn_envelope": {
            "turn_id": "weather-location-context",
            "original_input": {"text": text},
        }},
    )
    candidate = StreamingFakeOllama({
        "disposition": "execute", "coverage": "complete",
        "covered_responsibility_refs": ["r1"], "activities": [{
            "activity_id": "query", "role": "capability",
            "capability_id": "chromie.weather.lookup",
            "args": {"location": "重庆", "location_context": location_context},
            "argument_sources": {
                "location": {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t1",
                }
            },
            "source_responsibility_refs": ["r1"], "timing": "sequential",
        }], "continuations": [], "confidence": 1.0, "unresolved": [],
        "reason_summary": "Acquire the requested information.",
    })
    catalog = WeatherCatalog()
    weather = next(item for item in catalog.items if item.capability_id == "chromie.weather.lookup")
    input_schema = json.loads(json.dumps(weather.input_schema, ensure_ascii=False))
    input_schema["properties"]["location_context"] = {
        "type": "object",
        "properties": {
            "locality": {"type": "string"},
            "country": {"type": "string"},
        },
        "additionalProperties": False,
    }
    hints = json.loads(json.dumps(weather.hints, ensure_ascii=False))
    hints["argument_derivation"] = {
        "location_context": {
            "source_argument": "location",
            "require_exact_source_value": True,
        }
    }
    catalog.items = [
        item.model_copy(update={"input_schema": input_schema, "hints": hints})
        if item.capability_id == "chromie.weather.lookup" else item
        for item in catalog.items
    ]
    advance = await StreamingResolver(candidate, catalog).resolve_advance(request)
    assert (advance.disposition == "execute") is accepted, advance.metadata
    if accepted:
        assert advance.activities[0].args["location_context"] == location_context
    else:
        assert advance.disposition == "unavailable"
        assert not advance.activities


@pytest.mark.parametrize("value", [3, True, "3", "3 seconds", "0.2 m/s", {}, ["重庆"]])
def test_literal_intent_provenance_cannot_replace_typed_measurement_evidence(value):
    from agent.app.planner_grounding import literal_intent_argument

    source = "Use " + str(value)
    assert not literal_intent_argument(value, outcome=source, source_text=source)


def test_literal_intent_provenance_tolerates_only_authoritative_ascii_case_drift():
    from agent.app.planner_grounding import literal_intent_argument

    outcome = "Provide the current weather conditions for Chongqing as of today."
    source = "Can you help me check the weather today in chongqing?"
    assert literal_intent_argument("chongqing", outcome=outcome, source_text=source)
    assert literal_intent_argument("Chongqing", outcome=outcome, source_text=source)
    assert not literal_intent_argument("CHONGQING", outcome=outcome, source_text=source)


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


@pytest.mark.asyncio
async def test_fast_weather_collapses_duplicate_read_after_default_cleanup() -> None:
    from tests.test_fast_planner_pr3 import (
        FakeOllama as StreamingFakeOllama,
        FastPlannerResolver as StreamingResolver,
    )

    tool = next(
        tool
        for agent in chromie_capability_bundle().agents
        for tool in agent.tools
        if tool.name == "chromie.weather.lookup"
    )

    class QualifiedWeatherCatalog:
        async def prompt_entries(self, **kwargs):
            del kwargs
            return [CatalogCapability(
                capability_id=tool.name,
                agent_id="chromie.weather",
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                available=True,
                interaction_executable=True,
                hints=tool.llm_hints,
                idempotent=tool.execution.idempotent,
                side_effect_free=tool.execution.side_effect_free,
            )]

    request = CognitiveWorkRequest(
        sid="weather-deduplicate-default",
        text="what's the weather today in chongqing?",
        language="en-US",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "the weather today in chongqing",
            "bindings": {"location": "chongqing", "time_reference": "today"},
            "output_mode": "information",
            "continuity_scope": "goal",
            "confidence": 1.0,
        }],
        interpretation_confidence=1.0,
    )
    raw = {
        "disposition": "execute",
        "coverage": "complete",
        "covered_responsibility_refs": ["r1"],
        "activities": [
            {
                "activity_id": "weather-explicit-default",
                "role": "capability",
                "capability_id": "chromie.weather.lookup",
                "args": {"location": "chongqing", "date": "today", "period": "day"},
                "timing": "sequential",
                "source_responsibility_refs": ["r1"],
            },
            {
                "activity_id": "weather-implicit-default",
                "role": "capability",
                "capability_id": "chromie.weather.lookup",
                "args": {"location": "chongqing"},
                "timing": "sequential",
                "source_responsibility_refs": ["r1"],
            },
        ],
        "continuations": [],
        "confidence": 1.0,
        "unresolved": [],
        "reason_summary": "Acquire the same weather evidence once.",
    }

    advance = await StreamingResolver(
        StreamingFakeOllama(raw), QualifiedWeatherCatalog()
    ).resolve_advance(request)

    assert advance.disposition == "execute", advance.metadata
    assert [(item.activity_id, item.args) for item in advance.activities] == [
        ("weather-explicit-default", {"location": "chongqing", "date": "today"})
    ]
    repairs = advance.metadata["mechanical_duplicate_activity_collapses"]
    assert len(repairs) == 1
    assert repairs[0]["removed_activity_id"] == "weather-implicit-default"
