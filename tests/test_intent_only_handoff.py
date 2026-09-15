"""Owner-authorized intent/realization boundary, including the reported episode."""
import json
import copy

import pytest
from jsonschema import Draft202012Validator

from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _source_tokens,
)
from agent.app.cognitive_core.goal_interpreter.schema import GoalInterpretationRequest
from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver
from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.plan import FastPlannerStreamFailure, FastPlannerStreamTerminal


EPISODES = [
    "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left",
    "以0.2的速度向前走10秒，然后点头两次，再向左转",
    "Walk for ten seconds while singing, then look at me",
    "一边向前走一边唱歌，然后看着我",
    "Will it rain in Chongqing tomorrow morning?",
    "重庆明天早上会下雨吗？",
]


def intent_result(text, output_mode="body_action"):
    tokens = _source_tokens(text)
    return {
        "confidence": 1.0,
        "responsibilities": [{
            "local_ref": "r1", "outcome": text, "confidence": 1.0, "output_mode": output_mode,
            "source_evidence": {
                "source_start_token_ref": tokens[0]["ref"],
                "source_end_token_ref": tokens[-1]["ref"],
            },
        }],
        "unresolved": [],
    }


@pytest.mark.parametrize("text", EPISODES)
def test_complete_intent_needs_no_capability_fields(text):
    request = GoalInterpretationRequest(text=text)
    schema = OllamaGoalInterpreter._goal_interpretation_response_schema(admitted_turn=text)
    result = intent_result(text, "information" if text in EPISODES[-2:] else "body_action")
    Draft202012Validator(schema).validate(result)
    decision = OllamaGoalInterpreter._validate_interpretation_content(
        request, json.dumps(result), response_schema=schema,
    )
    assert decision.responsibilities[0].outcome == text
    assert not decision.responsibilities[0].bindings
    assert not decision.unresolved


@pytest.mark.parametrize("name,value", [
    ("binding_items", {"duration": "10 seconds"}),
    ("bindings", {"direction": "ahead"}),
    ("capability_id", "test.walk"),
    ("relationship", "new"),
    ("target_goal_ids", []),
])
def test_gi_rejects_downstream_authorship(name, value):
    text = EPISODES[0]
    result = intent_result(text)
    result["responsibilities"][0][name] = value
    with pytest.raises(ValueError):
        OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text=text), json.dumps(result),
        )


class Catalog:
    def __init__(self, entries):
        self.entries = entries

    async def prompt_entries(self, *, scope, refresh=False):
        return [item for item in self.entries if scope != "common" or item.prompt_tier == "common"]


class Model:
    def __init__(self, replies):
        self.replies = list(replies)
        self.packets = []

    async def generate_stream(self, prompt, **kwargs):
        self.packets.append((str(prompt), kwargs))
        yield json.dumps(self.replies.pop(0))

    async def generate(self, prompt, **kwargs):
        self.packets.append((str(prompt), kwargs))
        return self.replies.pop(0)


def request_for(text):
    decision = OllamaGoalInterpreter._validate_interpretation_content(
        GoalInterpretationRequest(text=text), json.dumps(intent_result(text)),
    )
    return CognitiveWorkRequest(sid="intent-handoff", text=text,
        responsibilities=decision.responsibilities, interpretation_confidence=1.0)


def capability(name, properties, *, tier="common"):
    return CatalogCapability(
        capability_id="test." + name, agent_id="test", description=name,
        input_schema={"type": "object", "properties": properties,
                      "required": list(properties), "additionalProperties": False},
        interaction_executable=True, prompt_tier=tier, can_run_parallel=False,
        effects=["physical_motion"], hints={"semantic_type":"body_action"},
        parallel_metadata_declared=True,
    )


def work(activities):
    return {"disposition": "execute", "coverage": "complete",
        "covered_responsibility_refs": ["r1"], "activities": activities,
        "continuations": [], "confidence": 1.0, "unresolved": [],
        "reason_summary": "Complete requested activities in source order."}


def activity(name, args, sources):
    return {"role": "capability", "activity_id": name, "capability_id": "test." + name,
        "args": args, "argument_sources": sources, "timing": "sequential",
        "source_responsibility_refs": ["r1"]}


@pytest.mark.asyncio
async def test_compound_intent_becomes_three_grounded_activities_and_one_goal():
    request = request_for(EPISODES[0])
    entries = [
        capability("walk", {"speed": {"type": "number"}, "duration_s": {"type": "number"}}),
        capability("nod", {"count": {"type": "integer"}}),
        capability("turn", {"direction": {"type": "string"}}),
    ]
    activities = [
        activity("walk", {"speed": .2, "duration_s": 10}, {"speed": "0.2 speed", "duration_s": "10 seconds"}),
        activity("nod", {"count": 2}, {"count": "twice"}),
        activity("turn", {"direction": "left"}, {"direction": "left"}),
    ]
    frames = [frame async for frame in FastPlannerResolver(Model([work(activities)]), Catalog(entries)).stream_advance(request)]
    assert isinstance(frames[0], FastPlannerStreamTerminal)
    ga = Model([{"new_goals": [{"source_responsibility_refs": ["r1"], "related_goal_ids": [], "supersedes_goal_ids": []}],
                 "referent_updates": [], "resolved_references": [], "confidence": 1.0, "reason_summary": "New intent."}])
    association = await GoalAssociationResolver(ga).resolve(request)
    assert len(association.new_goals) == 1
    assert association.new_goals[0].description == EPISODES[0]
    assert association.new_goals[0].metadata["output_mode"] == "body_action"
    plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(
        advance=frames[0].advance, association=association, user_text=request.text,
    )
    assert [step.capability_id for step in plan.steps] == ["test.walk", "test.nod", "test.turn"]
    assert all(step.timing == "sequential" for step in plan.steps)
    assert [item.source_quote for item in plan.parameter_resolutions] == ["0.2 speed", "10 seconds", "twice", "left"]
    assert all(item.source_goal_ids == [association.new_goals[0].goal_id] for item in plan.parameter_resolutions)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "unknown_id", "second_lookup", "mixed_plan", "invented_quote"])
async def test_indexed_capability_lookup_precedes_one_complete_plan(fault):
    request = request_for("turn left by 45 degrees")
    entry = capability("turn", {"rotation_degrees": {"type": "number", "maximum": 90}}, tier="rare")
    lookup = {"requested_capability_ids": ["test.turn"]}
    final = work([activity("turn", {"rotation_degrees": 45}, {"rotation_degrees": "45 degrees"})])
    if fault == "unknown_id":
        lookup["requested_capability_ids"] = ["test.missing"]
    elif fault == "second_lookup":
        final = copy.deepcopy(lookup)
    elif fault == "mixed_plan":
        lookup.update(final)
    elif fault == "invented_quote":
        final["activities"][0]["argument_sources"]["rotation_degrees"] = "180 degrees"
    model = Model([lookup, final])
    frames = [frame async for frame in FastPlannerResolver(model, Catalog([entry])).stream_advance(request)]
    assert "test.turn" in model.packets[0][0]
    assert "rotation_degrees" not in model.packets[0][0]
    if fault:
        assert isinstance(frames[0], FastPlannerStreamFailure)
    else:
        assert isinstance(frames[0], FastPlannerStreamTerminal)
        assert len(model.packets) == 2
        assert "rotation_degrees" in model.packets[1][0]
        assert request.text in model.packets[1][0]
        assert frames[0].advance.metadata["semantic_result_call_count"] == 1
    assert len(model.packets) <= 2


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["nod your head twice", "点头两次"])
async def test_body_intent_cannot_be_completed_by_a_zero_work_response(text):
    reply = work([{"role": "complete_response", "activity_id": "reply",
                   "source_responsibility_refs": ["r1"], "timing": "parallel",
                   "rationale": "The response completes the task."}])
    reply["disposition"] = "respond"
    model = Model([reply])
    frames = [frame async for frame in FastPlannerResolver(model, Catalog([])).stream_advance(request_for(text))]
    assert len(frames) == 1
    assert isinstance(frames[0], FastPlannerStreamFailure)
    assert len(model.packets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name,value", [
    ("output_mode", "speech"), ("bindings", []), ("resource_kind", "physical_object"),
    ("resource_responsibility", {}), ("description", "Only reply"),
])
async def test_ga_cannot_reauthor_intent_or_execution_fields(name, value):
    candidate = {"source_responsibility_refs": ["r1"], "related_goal_ids": [],
                 "supersedes_goal_ids": [], name: value}
    model = Model([{"decision": "create_goals", "new_goals": [candidate],
                   "referent_updates": [], "resolved_references": [],
                   "confidence": 1.0, "reason_summary": "A new goal."}])
    result = await GoalAssociationResolver(model).resolve(request_for("nod your head twice"))
    assert result.resolution_status == "fail_closed"
    assert not result.new_goals
    assert len(model.packets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "foreign_quote", "wrong_instant", "missing_zone", "invalid_date", "missing_clock"])
async def test_planner_owns_new_future_readiness_without_gi_time_fields(fault):
    from pathlib import Path
    from datetime import datetime
    due = "2099-09-04T19:00:00+08:00"
    text = "Nod twice at " + due
    request = request_for(text)
    ga = Model([{"decision": "create_goals", "new_goals": [{"source_responsibility_refs": ["r1"],
                "related_goal_ids": [], "supersedes_goal_ids": []}],
                "confidence": 1.0, "referent_updates": [], "resolved_references": [], "reason_summary": "New intent."}])
    association = await GoalAssociationResolver(ga).resolve(request)
    goal_id = association.new_goals[0].goal_id
    assert not association.new_goals[0].object.get("bindings")
    request.context["goal_association_resolution"] = association.model_dump(mode="json")
    raw = json.loads(Path("benchmarks/integration/scenarios/workflow-delayed.json").read_text())["model_steps"][2]["response"]
    raw = json.loads(json.dumps(raw).replace("${goal}", goal_id))
    condition = raw["time_conditions"][0]
    condition["source_quote"] = due
    condition["due_at_ms"] = int(datetime.fromisoformat(due).timestamp() * 1000)
    if fault == "foreign_quote":
        condition["source_quote"] = "at midnight"
    elif fault == "wrong_instant":
        condition["due_at_ms"] += 1000
    elif fault == "missing_zone":
        condition["source_quote"] = due[:19]
    elif fault == "invalid_date":
        condition["source_quote"] = "2099-02-30T19:00:00+08:00"
    elif fault == "missing_clock":
        condition["source_quote"] = "Nod twice"
    model = Model([raw])
    plan = await FastPlannerResolver(model, Catalog([])).resolve(request)
    assert not plan.steps
    assert len(model.packets) == 1
    if fault:
        assert plan.metadata.get("failure_class"), plan.model_dump()
    else:
        assert plan.disposition == "respond", plan.model_dump()
        assert not plan.metadata.get("failure_class"), plan.model_dump()
        assert plan.time_conditions[0].source_quote == due
        assert plan.goal_outcomes[0].satisfaction.unmet_goal_ids == [goal_id]
        Draft202012Validator(model.packets[0][1]["response_format"]).validate(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("available,locked", [(False, False), (True, True)])
async def test_index_visibility_does_not_authorize_unavailable_or_locked_work(available, locked):
    entry = capability("turn", {"rotation_degrees": {"type": "number"}}, tier="rare")
    entry = entry.model_copy(update={"available": available, "prompt_tier_locked": locked})
    final = work([activity("turn", {"rotation_degrees": 45}, {"rotation_degrees": "45 degrees"})])
    model = Model([{"requested_capability_ids": ["test.turn"]}, final])
    frames = [frame async for frame in FastPlannerResolver(model, Catalog([entry])).stream_advance(
        request_for("turn left by 45 degrees"))]
    assert len(frames) == 1 and isinstance(frames[0], FastPlannerStreamFailure)
    assert len(model.packets) == 2


@pytest.mark.asyncio
async def test_canonical_fast_lookup_retains_original_intent_and_one_semantic_result():
    from tests.test_fast_planner_pr3 import execute_step, execute_outcome, exact_satisfaction, multi_goal_plan
    request = request_for("turn left by 45 degrees")
    request.context["goal_association_resolution"] = {"new_goals": [{
        "goal_id": "g", "description": request.text, "metadata": {"output_mode": "body_action"},
        "source_responsibility_refs": ["r1"],
    }]}
    entry = capability("turn", {"rotation_degrees": {"type": "number"}}, tier="rare")
    raw = multi_goal_plan(disposition="execute", coverage="complete", goal_summary=request.text,
        steps=[execute_step("turn", "test.turn", {"rotation_degrees":45}, ["g"], "Perform the requested turn.")],
        goal_outcomes={"g":execute_outcome("g",["turn"],"Execute the requested turn.")},
        goal_satisfaction=exact_satisfaction(["g"]), parameter_resolutions=[{
            "step_id":"turn","parameter":"rotation_degrees","value":45,"strategy":"semantic_realization",
            "source_goal_ids":["g"],"source_quote":"45 degrees","confidence":1.,"blocking":False,
            "rationale":"Realize the exact requested rotation."}])
    raw.update(time_conditions=[], cancel_activity_ids=[])
    lookup = {"requested_capability_ids": ["test.turn"]}
    model = Model([lookup,raw])
    plan = await FastPlannerResolver(model,Catalog([entry])).resolve(request)
    assert plan.disposition == "execute", plan.metadata
    assert len(model.packets) == 2
    for packet,reply in zip(model.packets,[lookup,raw],strict=True):
        Draft202012Validator(packet[1]["response_format"]).validate(reply)
        assert request.text in packet[0]
    assert "rotation_degrees" not in model.packets[0][0]
    assert "rotation_degrees" in model.packets[1][0]
    assert plan.metadata["capability_detail_lookups"] == 1
    assert plan.metadata["semantic_result_call_count"] == 1


@pytest.mark.parametrize("typed", [False, True])
def test_intent_update_preserves_or_rejects_retained_constraints_atomically(typed):
    from shared.chromie_contracts.semantic_task import SemanticGoal, semantic_goal_fingerprint, apply_goal_meaning_update
    goal = SemanticGoal(goal_id="g",description="Nod twice",source_text="Nod twice",success_criteria=["Nod twice"],
        metadata={"output_mode":"body_action"},
        object={"bindings":{"count":{"entity_type":"count","value":2}}} if typed else {})
    before = goal.model_dump()
    update = {"base_goal_fingerprint":semantic_goal_fingerprint(goal),"replace_requirement_indices":[0],
        "source_turn_id":"correction", "source_responsibilities":intent_result("Nod three times")["responsibilities"],
        "binding_changes":[]}
    if typed:
        with pytest.raises(ValueError,match="explicitly sourced replacement"):
            apply_goal_meaning_update(goal,update)
    else:
        updated = apply_goal_meaning_update(goal,update)
        assert updated.description == "Nod three times" and updated.version == goal.version + 1
    assert goal.model_dump() == before


@pytest.mark.parametrize("foreign", [False, True])
def test_fast_quote_binding_includes_exact_retained_goal_owner(foreign):
    from shared.chromie_contracts.goal import GoalAssociationResolution
    from shared.chromie_contracts.plan import FastPlannerAdvance
    association = GoalAssociationResolution(turn_id="t",resolution_status="resolved",confidence=1.,
        associations=[{"association_id":"a","relationship":"continue","source_responsibility_refs":["r1"],
                       "target_goal_ids":["retained"],"confidence":1.}])
    advance = FastPlannerAdvance(turn_id="t",**work([activity("nod",{"count":2},{"count":"twice"})]))
    kwargs = dict(advance=advance,association=association,user_text="Nod twice",
        retained_goals=[{"goal_id":"retained","goal":{
            "goal_id":"other" if foreign else "retained","description":"Nod twice"}}])
    if foreign:
        with pytest.raises(ValueError,match="no exact canonical Goal owner"):
            GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(**kwargs)
    else:
        plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(**kwargs)
        assert plan.parameter_resolutions[0].source_goal_ids == ["retained"]


def test_intent_only_numeric_activity_requires_provenance_at_decoder():
    from agent.app.planner_schema import fast_streaming_advance_response_schema
    request = request_for("walk for ten seconds")
    catalog = capability("walk", {"duration_s":{"type":"number"}})
    schema = fast_streaming_advance_response_schema(["r1"],responsibilities=request.responsibilities,
        capabilities=[catalog.model_dump(mode="json")])
    raw = work([activity("walk",{"duration_s":10},{"duration_s":"ten seconds"})])
    validator = Draft202012Validator(schema)
    validator.validate(raw)
    del raw['activities'][0]['argument_sources']
    assert list(validator.iter_errors(raw))


def test_optional_numeric_arguments_expose_sources_without_requiring_defaults():
    from agent.app.planner_schema import fast_streaming_advance_response_schema
    from agent.app.planner_fast_validation import validate_fast_advance_output
    from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput
    request = request_for("walk for ten seconds")
    catalog = capability("walk", {"duration_s":{"type":"number", "default":2}})
    catalog.input_schema["required"] = []
    capabilities = [catalog.model_dump(mode="json")]
    schema = fast_streaming_advance_response_schema(["r1"], responsibilities=request.responsibilities,
        capabilities=capabilities)
    validator = Draft202012Validator(schema)
    raw = work([activity("walk", {"duration_s":10}, {"duration_s":"ten seconds"})])
    validator.validate(raw)
    validate_fast_advance_output(FastPlannerAdvanceModelOutput.model_validate(raw), request=request,
        responsibilities=request.responsibilities, capabilities=capabilities)
    del raw["activities"][0]["argument_sources"]
    assert list(validator.iter_errors(raw))
    raw["activities"][0]["argument_sources"] = {}
    with pytest.raises(ValueError, match="unbound required Capability input"):
        validate_fast_advance_output(FastPlannerAdvanceModelOutput.model_validate(raw), request=request,
            responsibilities=request.responsibilities, capabilities=capabilities)
    # Omitting an optional input still permits the provider's authoritative default.
    raw["activities"][0]["args"] = {}
    validator.validate(raw)
    validate_fast_advance_output(FastPlannerAdvanceModelOutput.model_validate(raw), request=request,
        responsibilities=request.responsibilities, capabilities=capabilities)
