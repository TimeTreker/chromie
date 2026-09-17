from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from agent.app.social_cognition import SocialCognitionResolver, social_cognition_response_schema
from agent.app.capabilities.validator import validate_args_for_schema
from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialCommunicativeAct
from tests.test_situational_cognition import goal_free_observation


class Model:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return copy.deepcopy(self.output)


class Catalog:
    async def prompt_entries(self, **kwargs):
        return []


@pytest.mark.parametrize("trigger", ["interpretation", "goal_state", "work_state", "evidence", "situation"])
@pytest.mark.parametrize("memory_field", ["memory_candidates", "self_memory_candidates"])
def test_native_memory_proposals_require_situation_authority(trigger, memory_field):
    from tests.test_situational_cognition import request_for

    current = request_for(goal_free_observation())
    if trigger != "situation":
        current = current.model_copy(update={"trigger": trigger, "source_turn": {"turn_id": "source"}})
    schema = social_cognition_response_schema(current, [])
    proposal = {"text": "A shared event.", "source_refs": current.source_refs,
                "subject_refs": ["person:dad"]}
    if memory_field == "self_memory_candidates":
        proposal.update(kind="self_concern", subject_refs=["self:chromie"])
    raw = {"disposition": "silence", "activities": [], "reason_summary": "No interruption needed.",
           memory_field: [proposal]}
    for contract in (schema, {"$defs": schema["$defs"], "oneOf": schema["oneOf"]}):
        assert (not list(Draft202012Validator(contract).iter_errors(raw))) == (trigger == "situation")


@pytest.mark.parametrize("need_count", [0, 1, 3])
@pytest.mark.parametrize("deep", [False, True])
def test_native_decision_states_preserve_pending_needs_and_unresolved_cognition(need_count, deep):
    from shared.chromie_contracts.social_cognition import SocialCommunicationNeed

    needs = [SocialCommunicationNeed(need_id=f"need:{i}", owner="planner", kind="answer",
        reference_id="plan:1", source_goal_ids=["goal:1"]) for i in range(need_count)]
    current = request(communication_needs=needs)
    schema = social_cognition_response_schema(current, [], deep=deep)
    # Exercise complete native alternatives without relying on if/then support.
    native = {"$defs": schema["$defs"], "oneOf": schema["oneOf"]}
    for state in ("communicate", "silence", "deliberate"):
        for coverage in ("covered", "pending", "empty"):
            raw = response(addressed_need_ids=[need.need_id for need in needs])
            raw.update(disposition=state,
                activities=raw["activities"] if state == "communicate" else [],
                need_outcomes={} if coverage == "empty" else {need.need_id: coverage for need in needs})
            expected = (not deep and (not need_count or coverage == "empty")) if state == "deliberate" else (
                not need_count or (coverage != "empty" and (state == "communicate" or coverage == "pending")))
            for contract in (schema, native):
                assert (not list(Draft202012Validator(contract).iter_errors(raw))) == expected, (state, coverage)
    # No unresolved decision may author memory, even when it has no needs.
    unresolved = {"disposition": "deliberate", "activities": [], "reason_summary": "Unresolved.",
                  "need_outcomes": {}, "memory_candidates": [{}]}
    assert list(Draft202012Validator(native).iter_errors(unresolved))


@pytest.mark.parametrize("phase", ["pre_action", "final"])
def test_native_act_alternatives_preserve_upstream_delivery_order(phase):
    from shared.chromie_contracts.social_cognition import SocialCommunicationNeed

    current = request(communication_needs=[SocialCommunicationNeed(
        need_id="ordered", owner="planner", kind="answer", reference_id="plan:1",
        source_goal_ids=["goal:1"], delivery_phase=phase,
    )])
    schema = social_cognition_response_schema(current, [])
    valid = response(function="respond", delivery_phase=phase, addressed_need_ids=["ordered"])
    valid["need_outcomes"] = {"ordered": "covered"}
    Draft202012Validator(schema).validate(valid)
    # Test the concrete native alternatives independently of if/then support.
    for actual in ("immediate", "pre_action", "final"):
        act = copy.deepcopy(valid["activities"][0])
        act["delivery_phase"] = actual
        accepted = []
        for branch in schema["$defs"]["SocialCommunicativeAct"]["oneOf"]:
            native = copy.deepcopy(branch)
            native.pop("allOf", None)
            native["$defs"] = schema["$defs"]
            accepted.append(not list(Draft202012Validator(native).iter_errors(act)))
        assert any(accepted) == (actual == phase)
        # Unbound optional communication does not inherit the Need's barrier.
        act["addressed_need_ids"] = []
        optional = {**valid, "activities": [act], "need_outcomes": {"ordered": "pending"}}
        Draft202012Validator(schema).validate(optional)


def request(**changes):
    return SocialCognitionRequest(
        request_id="sc-test", trigger="work_state", source_refs=["work:1"],
        goal_ids=["goal:1"], context={"work": [{"id": "work:1", "status": "running"}],
                                     "active_goal_snapshots": [{"goal_id": "goal:1", "status": "active"}]},
    ).model_copy(update=changes)


def response(**changes):
    act = {"activity_id": "sc-act", "text": "还在进行中。", "function": "inform",
           "truth_stage": "context_grounded", "source_goal_ids": ["goal:1"]}
    act.update(changes)
    return {"disposition": "communicate", "activities": [act], "reason_summary": "Meaningful progress."}


@pytest.mark.parametrize("state", ["queued", "playing", "completed", "interrupted", "failed"])
def test_delivery_projection_preserves_social_facts_without_mutating_trusted_request(state):
    from agent.app.social_cognition import social_cognition_prompt

    ledger = {"events": [{"status": state, "text": "A grounded update.",
                         "metadata": {"communicative_activity_ids": ["act:1"]}}]}
    plan = {
        "plan_id": "plan:walk", "planner_tier": "fast", "disposition": "execute",
        "coverage": "complete", "goal_ids": ["goal:1"], "goal_summary": "Walk left.",
        "steps": [{"step_id": "walk", "capability_id": "soridormi.walk_velocity",
                   "source_goal_ids": ["goal:1"], "args": {"yaw_radps": 0.4, "duration_s": 2},
                   "timing": "sequential", "step_purpose": "achieve_effect",
                   "reason_summary": "Carry out the requested walk."}],
        "parameter_resolutions": [{"step_id": "walk", "parameter": "yaw_radps",
                                   "strategy": "intent", "value": 0.4}],
        "selected_agent_skills": [{"skill_id": "locomotion"}],
    }
    current = request(context={"interaction_context": ledger,
                               "active_goal_snapshots": [{"goal_id": "goal:1", "status": "active"}],
                               "other_evidence": {"status": "unknown", "value": "retain exactly"},
                               "canonical_plan_resolution": plan})
    before = current.model_dump(mode="json")
    digest = current.snapshot_digest()
    prompt = social_cognition_prompt(current, [], num_ctx=8192)
    packet = json.loads(prompt.split("Trusted interaction snapshot:\n", 1)[1])
    assert next(iter(packet)) == "interaction_context"
    opportunity_text = prompt.split("Immediate interaction opportunity:\n", 1)[1].split("\nTrusted interaction snapshot:\n", 1)[0]
    assert json.loads(opportunity_text)["kind"] == "trusted_state_change"
    projected = packet["request"]
    assert "interaction_context" not in projected["context"]
    assert packet["interaction_context"] == ledger
    assert projected["context"]["other_evidence"] == {"status": "unknown", "value": "retain exactly"}
    social_plan = projected["context"]["canonical_plan_resolution"]
    assert social_plan["plan_id"] == "plan:walk"
    assert social_plan["goal_summary"] == "Walk left."
    assert social_plan["steps"] == [{"step_id": "walk", "source_goal_ids": ["goal:1"],
                                      "timing": "sequential", "step_purpose": "achieve_effect",
                                      "reason_summary": "Carry out the requested walk."}]
    rendered = json.dumps(social_plan, ensure_ascii=False)
    assert "soridormi.walk_velocity" not in rendered
    assert "yaw_radps" not in rendered
    assert "parameter_resolutions" not in social_plan
    assert "selected_agent_skills" not in social_plan
    assert current.model_dump(mode="json") == before
    assert current.snapshot_digest() == digest


def test_social_authority_does_not_confuse_high_level_work_with_raw_motor_control():
    from agent.app.social_cognition import SOCIAL_COGNITION_AUTHORITY_PROMPT

    prompt = SOCIAL_COGNITION_AUTHORITY_PROMPT.lower()
    assert "high-level requested work such as walking, turning" in prompt
    assert "is not raw motor control" in prompt
    assert "must never be declared unavailable or unsafe" in prompt


def test_fresh_turn_prompt_frontloads_social_opportunity_without_duplicate_source_or_empty_needs():
    from agent.app.social_cognition import social_cognition_prompt
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal

    current = SocialCognitionRequest(
        request_id="sc-fresh", trigger="interpretation", source_refs=["turn:1"],
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1", outcome="turn left", confidence=1.0, output_mode="other",
            source_evidence={"source_start_token_ref": "t0", "source_end_token_ref": "t1"},
        )],
        source_turn={
            "schema_version": 1, "turn_id": "turn:1", "language": "en-US",
            "original_text": "turn left", "original_text_sha256": "a" * 64,
            "authority": "read_only_source_provenance",
        },
        context={
            "user_turn_envelope": {"large": "trusted transport copy"},
            "user_turn_schema_version": 1,
            "work_decision_pending": True,
            "interaction_context": {"already_spoken": [], "pending_speech": []},
        },
    )
    prompt = social_cognition_prompt(current, [], num_ctx=8192)
    packet = json.loads(prompt.split("Trusted interaction snapshot:\n", 1)[1])
    opportunity = json.loads(
        prompt.split("Immediate interaction opportunity:\n", 1)[1].split("\nTrusted interaction snapshot:\n", 1)[0]
    )
    assert opportunity == {
        "fresh_addressed_turn": True,
        "kind": "fresh_addressed_turn",
        "reply_already_pending_or_delivered": False,
        "work_decision_pending": True,
    }
    projected = packet["request"]
    assert "communication_needs" not in projected
    assert "user_turn_envelope" not in projected["context"]
    assert "user_turn_schema_version" not in projected["context"]
    assert projected["source_turn"]["original_text"] == "turn left"
    assert current.context["user_turn_envelope"] == {"large": "trusted transport copy"}


def test_social_authority_treats_fresh_task_request_as_interaction_not_silence_by_default():
    from agent.app.social_cognition import SOCIAL_COGNITION_AUTHORITY_PROMPT

    prompt = SOCIAL_COGNITION_AUTHORITY_PROMPT.lower()
    assert "fresh addressed turn is itself an interaction opportunity" in prompt
    assert "task-oriented content, physical work, or absence of a planner communication need" in prompt
    assert "are never by themselves reasons for silence" in prompt
    assert "acknowledging receipt is itself useful interaction" in prompt
    assert "do not relabel the absence of task-oriented speech as 'no useful social change'" in prompt
    assert "reason_summary must cite a separate supplied situational fact" in prompt
    assert "planner never grants or withholds your communication authority" in prompt
    assert "do not explain a communication or silence decision by saying planner authorized" in prompt



@pytest.mark.asyncio
async def test_shared_goal_state_is_read_only_input_and_complete_decision_is_one_call():
    current = request()
    before = current.model_dump()
    model = Model(response())
    deep = Model({})
    result = await SocialCognitionResolver(model, Catalog(), deep_model=deep).resolve(current)
    assert result.activities[0].text == "还在进行中。"
    assert result.snapshot_digest == current.snapshot_digest()
    assert result.semantic_owner == "social_cognition"
    assert result.model_call_count == len(model.calls) == 1
    assert deep.calls == []
    assert current.model_dump() == before
    assert "active_goal_snapshots" in model.calls[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 8])
async def test_repeated_words_keep_distinct_act_identity_without_a_single_act_cap(count):
    current = request(context={"history": [{"role": "user", "text": f"Say hello {count} times."}]})
    raw = {"disposition": "communicate", "reason_summary": "The person explicitly requested repetition.",
        "activities": [response(activity_id=f"hello:{index}", text="Hello.")["activities"][0]
                       for index in range(count)]}
    model = Model(raw)
    result = await SocialCognitionResolver(model, Catalog()).resolve(current)
    assert [act.text for act in result.activities] == ["Hello."] * count
    assert len({act.activity_id for act in result.activities}) == count
    assert len(model.calls) == 1

    # A repeated identity is an invalid complete result even when words match.
    # It must never become partial delivery or a second semantic model call.
    raw["activities"][1]["activity_id"] = raw["activities"][0]["activity_id"]
    repeated = Model(raw)
    deeper = Model(response())
    with pytest.raises(ValueError, match="Activity IDs must be unique"):
        await SocialCognitionResolver(repeated, Catalog(), deep_model=deeper).resolve(current)
    assert len(repeated.calls) == 1 and deeper.calls == []


@pytest.mark.asyncio
async def test_environment_can_initiate_without_gi_or_fake_goal():
    observation = goal_free_observation()
    current = SocialCognitionRequest(
        request_id="arrival", trigger="situation", source_refs=observation.source_refs,
        situation=observation.projection, context={"active_goal_snapshots": []},
    )
    model = Model(response(source_goal_ids=[], text="欢迎回来。"))
    result = await SocialCognitionResolver(model, Catalog()).resolve(current)
    assert result.activities[0].text == "欢迎回来。"
    assert current.responsibilities == []
    assert current.source_turn == {}
    assert result.activities[0].source_goal_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("source_goal_ids", ["foreign"]), ("evidence_refs", ["invented"]),
    ("source_responsibility_refs", ["invented"]), ("addressed_need_ids", ["invented"]),
])
async def test_unknown_provenance_fails_before_resolution_without_retry(field, value):
    model = Model(response(**{field: value}))
    with pytest.raises(ValueError):
        await SocialCognitionResolver(model, Catalog()).resolve(request())
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_no_capability_catalog_cannot_produce_gesture():
    model = Model(response(auxiliary_activities=[{
        "auxiliary_activity_id": "nod", "capability_id": "soridormi.nod",
        "anchor_kind": "communicative_act", "anchor_id": "sc-act", "args": {},
    }]))
    with pytest.raises(ValueError):
        await SocialCognitionResolver(model, Catalog()).resolve(request())


@pytest.mark.asyncio
async def test_silence_keeps_upstream_obligations_intact():
    current = request()
    model = Model({"disposition": "silence", "activities": [], "reason_summary": "Already pending."})
    result = await SocialCognitionResolver(model, Catalog()).resolve(current)
    assert result.activities == []
    assert current.goal_ids == ["goal:1"]
    assert current.context["work"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_only_unresolved_source_can_deepen_once_without_candidate_review():
    model = Model({"disposition": "deliberate", "activities": [], "reason_summary": "Need deeper reasoning."})
    deep = Model(response())
    result = await SocialCognitionResolver(model, Catalog(), deep_model=deep).resolve(request())
    assert result.model_call_count == 2
    assert model.calls[0][0] == deep.calls[0][0]
    assert "Need deeper reasoning." not in deep.calls[0][0]
    assert deep.calls[0][1]["response_format"]["properties"]["disposition"]["enum"] == ["communicate", "silence"]


@pytest.mark.asyncio
async def test_deeper_recursion_and_missing_deeper_model_fail_closed():
    unresolved = {"disposition": "deliberate", "activities": [], "reason_summary": "Unresolved."}
    for deep in (None, Model(unresolved)):
        model = Model(unresolved)
        with pytest.raises(ValueError):
            await SocialCognitionResolver(model, Catalog(), deep_model=deep).resolve(request())
        assert len(model.calls) == 1
        if deep:
            assert len(deep.calls) == 1


@pytest.mark.asyncio
async def test_snapshot_cannot_change_during_catalog_await():
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingCatalog:
        async def prompt_entries(self, **kwargs):
            entered.set()
            await release.wait()
            return []

    current = request()
    original_digest = current.snapshot_digest()
    model = Model(response())
    task = asyncio.create_task(SocialCognitionResolver(model, WaitingCatalog()).resolve(current))
    await entered.wait()
    current.context["work"][0]["status"] = "completed"
    release.set()
    result = await task
    assert result.snapshot_digest == original_digest
    assert '"status":"running"' in model.calls[0][0]


@pytest.mark.asyncio
async def test_nonverbal_act_has_real_anchor_and_never_fabricates_speech():
    class BodyCatalog:
        async def prompt_entries(self, **kwargs):
            return [SimpleNamespace(
                capability_id="soridormi.nod", description="Optional nod", available=True,
                interaction_executable=True, behavior_domains=["social_attention"],
                requires_confirmation=False, can_run_parallel=True, parallel_metadata_declared=True,
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            )]

    model = Model(response(text="", function="nonverbal", auxiliary_activities=[{
        "auxiliary_activity_id": "nod", "capability_id": "soridormi.nod", "args": {},
        "anchor_kind": "communicative_act", "anchor_id": "sc-act",
    }]))
    result = await SocialCognitionResolver(model, BodyCatalog()).resolve(request())
    assert result.activities[0].text == ""
    assert result.activities[0].auxiliary_activities[0].anchor_id == "sc-act"
    with pytest.raises(ValueError):
        SocialCommunicativeAct.model_validate(response(text="", function="nonverbal")["activities"][0])



@pytest.mark.parametrize("function,text,expression,valid", [
    ("nonverbal", "", False, False), ("nonverbal", "", True, True),
    ("nonverbal", "Hello", True, False), ("respond", "Hello", False, True),
    ("respond", "Hello", True, True), ("respond", "", True, False),
])
def test_decoder_preserves_verbal_and_embodied_expression_contract(function, text, expression, valid):
    schema = social_cognition_response_schema(request(), [{
        "capability_id": "soridormi.nod", "input_schema": {"type": "object"},
    }])
    raw = response(text=text, function=function)
    if expression:
        raw["activities"][0]["auxiliary_activities"] = [{
            "auxiliary_activity_id": "nod", "capability_id": "soridormi.nod", "args": {},
            "anchor_kind": "communicative_act", "anchor_id": "sc-act",
        }]
    assert (not list(Draft202012Validator(schema).iter_errors(raw))) is valid


def test_work_mutation_is_unrepresentable_in_social_output():
    schema = social_cognition_response_schema(request(), [])
    raw = response()
    raw["steps"] = [{"capability_id": "soridormi.walk", "args": {}}]
    assert validate_args_for_schema(raw, schema)


def test_work_plan_can_retain_an_unfulfilled_communication_need_without_words():
    from shared.chromie_contracts.plan import CanonicalPlan

    raw = {
        "plan_id": "plan:chat", "planner_tier": "fast", "disposition": "respond",
        "coverage": "complete", "goal_ids": ["goal:chat"],
        "goal_outcomes": [{"goal_id": "goal:chat", "disposition": "respond", "coverage": "complete"}],
        "communication_needs": [{"need_id": "answer:chat", "owner": "planner", "kind": "answer",
                                 "source_goal_ids": ["goal:chat"], "reference_id": "plan:chat"}],
    }
    plan = CanonicalPlan.model_validate(raw)
    assert plan.response_text == "" and plan.communicative_acts == [] and plan.steps == []
    assert plan.executable_goal_ids() == []
    assert plan.communication_needs[0].source_goal_ids == ["goal:chat"]
    for changes in ({"reference_id": "another-plan"}, {"source_goal_ids": ["foreign-goal"]}, {"owner": "runtime"}):
        invalid = copy.deepcopy(raw)
        invalid["communication_needs"][0].update(changes)
        with pytest.raises(ValueError):
            CanonicalPlan.model_validate(invalid)


@pytest.mark.parametrize("context", [
    {"raw": {"motor_commands": [1]}},
    {"interaction_context": None},
    {"interaction_context": {"already_spoken": "not a record array"}},
    {"interaction_context": {"already_spoken": [{"metadata": {"communicative_activity_ids": "not-an-array"}}]}},
])
def test_untrusted_context_shape_cannot_reach_cognition(context):
    with pytest.raises(ValueError):
        SocialCognitionRequest.model_validate({**request().model_dump(), "context": context})


def test_expression_identity_cannot_be_reused_under_two_communicative_anchors():
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput

    activities = []
    for act_id in ("first", "second"):
        activities.append(response(activity_id=act_id, auxiliary_activities=[{
            "auxiliary_activity_id": "same-expression", "capability_id": "soridormi.nod",
            "args": {}, "anchor_kind": "communicative_act", "anchor_id": act_id,
        }])["activities"][0])
    with pytest.raises(ValueError, match="unique across"):
        SocialCognitionOutput.model_validate({
            "disposition": "communicate", "activities": activities, "reason_summary": "Two distinct acts.",
        })


def test_silence_and_repair_have_distinct_schema_contracts():
    current = request(context={"interaction_context": {"already_spoken": [{
        "text": "Previously delivered.", "metadata": {"communicative_activity_ids": ["earlier"]},
    }]}})
    schema = social_cognition_response_schema(current, [])
    fresh_id = schema["$defs"]["SocialCommunicativeAct"]["oneOf"][0]["properties"]["activity_id"]["enum"][0]
    assert Draft202012Validator(schema).is_valid({
        "disposition": "silence", "activities": [], "reason_summary": "No new interaction need.",
    })
    # The retained native failure encoded silence as a placeholder repair.
    assert not Draft202012Validator(schema).is_valid(response(text="...", function="repair"))
    assert not Draft202012Validator(schema).is_valid(response(repair_of_activity_ids=["earlier"]))
    assert Draft202012Validator(schema).is_valid(response(
        activity_id=fresh_id, text="A correction.", function="repair", repair_of_activity_ids=["earlier"],
    ))


@pytest.mark.parametrize("ledger_key", ["events", "already_spoken", "pending_speech"])
@pytest.mark.parametrize("words", ["The task is complete.", "事情已经完成了。"])
def test_native_identity_choices_preserve_reuse_and_explicit_repetition(ledger_key, words):
    current = request(context={"interaction_context": {ledger_key: [{
        "text": words, "metadata": {"communicative_activity_ids": ["existing"]},
    }]}})
    schema = social_cognition_response_schema(current, [])
    fresh_ids = schema["$defs"]["SocialCommunicativeAct"]["oneOf"][0]["properties"]["activity_id"]["enum"]
    assert len(fresh_ids) == schema["properties"]["activities"]["maxItems"]
    assert "existing" not in fresh_ids and len(set(fresh_ids)) == len(fresh_ids)
    for contract in (schema, {"$defs": schema["$defs"], "oneOf": schema["oneOf"]}):
        validator = Draft202012Validator(contract)
        assert validator.is_valid(response(activity_id="existing", text=words))
        assert not validator.is_valid(response(activity_id="existing", text="Different words."))
        assert validator.is_valid(response(activity_id=fresh_ids[0], text="Different words."))
        repeated = response()
        repeated["activities"] = [response(activity_id=identity, text=words)["activities"][0]
                                  for identity in fresh_ids]
        assert validator.is_valid(repeated)


@pytest.mark.asyncio
async def test_raw_schema_rejects_nested_identity_violation_before_dto_or_retry():
    current = request(context={"interaction_context": {"already_spoken": [{
        "text": "Old words.", "metadata": {"communicative_activity_ids": ["old"]},
    }]}})
    # This is a valid free-standing DTO. The request-specific Schema excludes
    # an unoffered fresh ID, while preserving all fresh message meanings.
    raw = response(activity_id="unoffered", text="New words.")
    model = Model(raw)
    with pytest.raises(ValueError, match="raw Schema rejected"):
        await SocialCognitionResolver(model, Catalog()).resolve(current)
    assert len(model.calls) == 1


def test_sglang_preserves_social_need_contract_through_decoder_intersections():
    from agent.app.clients.sglang_protocol import build_sglang_chat_payload
    from agent.app.inference_compute import CognitionComputeClass
    from shared.chromie_contracts.social_cognition import SocialCommunicationNeed

    current = request(communication_needs=[SocialCommunicationNeed(
        need_id="answer:1", owner="runtime", kind="result", source_goal_ids=["goal:1"], reference_id="work:1",
    )])
    schema = social_cognition_response_schema(current, [])
    payload = build_sglang_chat_payload(
        model="test", messages=[], compute_class=CognitionComputeClass.REALTIME,
        options={}, response_format=schema, stream=False, priority_step=100,
    )
    wire = payload["response_format"]["json_schema"]["schema"]
    valid = response(addressed_need_ids=["answer:1"])
    valid["need_outcomes"] = {"answer:1": "covered"}
    Draft202012Validator(wire).validate(valid)
    invalid = {**valid, "disposition": "silence", "activities": []}
    assert list(Draft202012Validator(wire).iter_errors(invalid))
    assert payload["priority"] == 500
    assert validate_args_for_schema({"speech": "invented envelope"}, wire)


@pytest.mark.asyncio
async def test_host_rejects_obsolete_state_without_delivery_or_work_mutation():
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator, CognitiveRuntimePolicy

    revision = [1]

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            result = await SocialCognitionResolver(Model(response()), Catalog()).resolve(request)
            revision[0] = 2
            return result

    runtime = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(), policy=CognitiveRuntimePolicy(mode="apply"),
    )
    result = await runtime.resolve_social_interaction(
        None, request=request(), session_id="person-session", snapshot_is_current=lambda: revision[0] == 1,
    )
    assert result is None
    assert revision[0] == 2


@pytest.mark.asyncio
async def test_host_realizes_exact_words_with_no_work_or_goal_completion_permission():
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator, CognitiveRuntimePolicy

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return await SocialCognitionResolver(Model(response()), Catalog()).resolve(request)

    runtime = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(), policy=CognitiveRuntimePolicy(mode="apply"),
    )
    result = await runtime.resolve_social_interaction(
        None, request=request(), session_id="person-session", snapshot_is_current=lambda: True,
    )
    assert result is not None
    decision, interaction = result
    assert interaction.speech[0].text == decision.activities[0].text
    assert interaction.speech[0].metadata["wording_owner"] == "social_cognition"
    assert interaction.speech[0].metadata["goal_completion_authority"] is False
    assert interaction.capabilities == []


@pytest.mark.asyncio
async def test_situation_speech_retains_correlation_through_actual_delivery_ledger():
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator, CognitiveRuntimePolicy
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle

    observation = goal_free_observation(audience_refs=["person:dad"])
    current = SocialCognitionRequest(
        request_id=observation.observation_id, trigger="situation", source_refs=observation.source_refs,
        situation=observation.projection,
    )

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return await SocialCognitionResolver(
                Model(response(text="欢迎回来。", source_goal_ids=[])), Catalog(),
            ).resolve(request)

    ledger = InteractionLedger()
    runtime = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(), policy=CognitiveRuntimePolicy(mode="apply"),
        interaction_ledger=ledger,
    )
    resolved = await runtime.resolve_social_interaction(
        None, request=current, session_id="sid", snapshot_is_current=lambda: True,
    )
    assert resolved is not None
    speech = resolved[1].speech[0]
    lifecycle = PlaybackDeliveryLifecycle(interaction_event_sink=ledger.record_playback_event)
    lifecycle.register_turn_speech_event(
        session_id="sid", turn_id=current.request_id, generation=1, orders=[1],
        normalized_text=speech.text, stage="social_cognition", purpose=speech.metadata["speech_act"],
        communicative_activity_ids=speech.metadata["communicative_activity_ids"],
        situation_signature=speech.metadata["situation_signature"], subject_refs=speech.metadata["subject_refs"],
    )
    lifecycle.update_turn_speech_event_for_playback(
        generation=1, order=1, session_id="sid", started=True, reason="playback_start",
    )
    assert ledger.context("sid").already_spoken == []
    lifecycle.complete_turn_speech_order(generation=1, order=1, session_id="sid", completed=True, reason="completed")
    delivered = ledger.context("sid").already_spoken[0]
    assert delivered["text"] == speech.text
    assert delivered["metadata"]["situation_signature"] == observation.projection.interpretation_signature()
    assert delivered["metadata"]["subject_refs"] == ["person:dad"]
    assert delivered["metadata"]["communicative_activity_ids"] == ["sc-act"]


@pytest.mark.asyncio
async def test_social_expression_uses_existing_trusted_runtime_without_goal_work():
    from tests.test_planner_auxiliary_activity_contract import _Runtime, _definition
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    raw = response(auxiliary_activities=[{
        "auxiliary_activity_id": "blink", "capability_id": "soridormi.blink_eyes", "args": {"count": 1},
        "anchor_kind": "communicative_act", "anchor_id": "sc-act",
    }])
    decision = SocialCognitionResolution(
        **raw, request_id="sc-test", snapshot_digest=request().snapshot_digest(), model_call_count=1,
    )
    provider = _Runtime([_definition()])
    adapter = CanonicalPlanRuntimeAdapter(provider)
    result = await adapter.execute_auxiliary_activities(
        social_cognition=decision, session_id="session", turn_id="sc-test",
        interaction=InteractionResponse(speech=[InteractionSpeech(id="spoken", text=decision.activities[0].text,
            metadata={"communicative_activity_ids": ["sc-act"]})]), context={},
    )
    assert result["materialized_count"] == 1
    executed = provider.executed[0][0].capabilities[0]
    assert executed.args == {"count": 1}
    assert executed.metadata["source"] == "social_cognition_auxiliary_activity"
    assert executed.metadata["source_goal_ids"] == []
    assert executed.metadata["execution_role"] == "social_decoration"
    # Repeated dispatch of the same immutable expression is suppressed.
    repeated = await adapter.execute_auxiliary_activities(
        social_cognition=decision, session_id="session", turn_id="sc-test",
        interaction=InteractionResponse(speech=[InteractionSpeech(id="spoken", text=decision.activities[0].text,
            metadata={"communicative_activity_ids": ["sc-act"]})]), context={},
    )
    assert repeated["materialized_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("covered", [True, False])
async def test_sc_words_bind_to_work_without_changing_its_identity_or_completing_progress(covered):
    from tests.test_cognitive_runtime_pr7 import FakeRuntime
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.plan import CanonicalPlan, canonical_plan_fingerprint
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    plan = CanonicalPlan(
        plan_id="plan:chat", planner_tier="fast", disposition="respond", coverage="complete",
        goal_ids=["goal:1"], goal_outcomes=[{"goal_id": "goal:1", "disposition": "respond", "coverage": "complete"}],
        communication_needs=[{"need_id": "answer:1", "owner": "planner", "kind": "answer",
                              "source_goal_ids": ["goal:1"], "reference_id": "plan:chat"}],
    )
    current = request(source_refs=[plan.plan_id], communication_needs=plan.communication_needs,
                      context={"canonical_plan_resolution": plan.prompt_projection()})
    result = SocialCognitionResolution(
        **{**response(addressed_need_ids=["answer:1"] if covered else []),
           "need_outcomes": {"answer:1": "covered" if covered else "pending"}},
        request_id=current.request_id, snapshot_digest=current.snapshot_digest(), model_call_count=1,
    )
    before = plan.model_dump()
    fingerprint = canonical_plan_fingerprint(plan)
    interaction = await CanonicalPlanRuntimeAdapter(FakeRuntime()).build_social_cognition_response(
        plan=plan, request=current, resolution=result, session_id="sid", language="zh-CN",
    )
    assert plan.model_dump() == before
    assert interaction.metadata["canonical_plan_fingerprint"] == fingerprint
    assert interaction.speech[0].text == result.activities[0].text
    assert interaction.speech[0].metadata["wording_owner"] == "social_cognition"
    assert interaction.speech[0].metadata["communication_completion_goal_ids"] == (["goal:1"] if covered else [])
    assert interaction.metadata["pending_communication_need_ids"] == ([] if covered else ["answer:1"])


@pytest.mark.asyncio
async def test_optional_sc_progress_does_not_create_a_physical_work_playback_barrier():
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, walk_definition
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    plan = CanonicalPlan(
        plan_id="plan:walk", planner_tier="fast", disposition="execute", coverage="complete",
        goal_ids=["goal:1"], steps=[{"step_id": "walk", "capability_id": "soridormi.walk_forward",
                                   "source_goal_ids": ["goal:1"], "args": {"duration_s": 1}, "timing": "sequential"}],
    )
    current = request(source_refs=[plan.plan_id], context={"canonical_plan_resolution": plan.prompt_projection()})
    result = SocialCognitionResolution(
        **response(), request_id=current.request_id, snapshot_digest=current.snapshot_digest(), model_call_count=1,
    )
    interaction = await CanonicalPlanRuntimeAdapter(FakeRuntime([walk_definition()])).build_social_cognition_response(
        plan=plan, request=current, resolution=result, session_id="sid", language="zh-CN",
    )
    assert len(interaction.capabilities) == 1
    assert interaction.speech[0].timing == "parallel"
    assert interaction.speech[0].metadata["playback_start_required_for_effects"] is False
    assert interaction.speech[0].metadata["communication_completion_goal_ids"] == []


def test_delivery_receipt_preserves_communication_need_and_responsibility_bindings():
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle

    ledger = InteractionLedger()
    lifecycle = PlaybackDeliveryLifecycle(interaction_event_sink=ledger.record_playback_event)
    fields = dict(session_id="sid", turn_id="turn", normalized_text="Answer.",
                  stage="social_cognition", purpose="respond", communicative_activity_ids=["answer-act"],
                  addressed_need_ids=["answer-need"], source_responsibility_refs=["r1"], wording_owner="social_cognition")
    lifecycle.register_turn_speech_event(**fields, generation=1, orders=[1])
    assert ledger.context("sid").already_spoken == []
    lifecycle.complete_turn_speech_order(generation=1, order=1, session_id="sid", completed=True, reason="completed")
    receipt = ledger.context("sid").already_spoken[0]["metadata"]
    assert receipt["addressed_need_ids"] == ["answer-need"]
    assert receipt["source_responsibility_refs"] == ["r1"]
    assert receipt["wording_owner"] == "social_cognition"
    with pytest.raises(ValueError, match="communication binding"):
        lifecycle.register_turn_speech_event(**{**fields, "addressed_need_ids": ["unrelated"]}, generation=2, orders=[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["completion", "need", "commitment", "question", "ordering"])
async def test_sc_projection_rejects_relabeling_exact_speech_as_other_authority(mutation):
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.planner_response import PlannerResponseProjection
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_cognitive_runtime_pr7 import FakeRuntime

    plan = CanonicalPlan(
        plan_id="plan", planner_tier="fast", disposition="respond", coverage="complete", goal_ids=["goal:1"],
        goal_outcomes=[{"goal_id": "goal:1", "disposition": "respond", "coverage": "complete"}],
        communication_needs=[{"need_id": "answer", "owner": "planner", "kind": "answer", "reference_id": "plan", "source_goal_ids": ["goal:1"]}],
    )
    current = request(source_refs=[plan.plan_id], communication_needs=plan.communication_needs,
                      context={"canonical_plan_resolution": plan.prompt_projection()})
    result = SocialCognitionResolution(
        **{**response(), "need_outcomes": {"answer": "pending"}}, request_id=current.request_id,
        snapshot_digest=current.snapshot_digest(), model_call_count=1,
    )
    adapter = CanonicalPlanRuntimeAdapter(FakeRuntime())
    async def capture(**kwargs):
        return kwargs["planner_response"]
    adapter.build_response = capture
    projection = await adapter.build_social_cognition_response(plan=plan, request=current, resolution=result, session_id="sid", language="en")
    payload = projection.model_dump()
    stage = payload["response_plan"]["activities"][0]
    if mutation == "completion":
        stage["metadata"]["communication_completion_goal_ids"] = ["goal:1"]
    elif mutation == "need":
        stage["metadata"]["addressed_need_ids"] = ["answer"]
    elif mutation == "commitment":
        stage["commitment_state"] = "completed"
        stage["must_not_claim_completion"] = False
    elif mutation == "question":
        stage["speech_act"] = "ask_confirmation"
    else:
        stage["metadata"]["required_before_work"] = True
    with pytest.raises(ValueError, match="SC projection changed"):
        PlannerResponseProjection.model_validate(payload)


@pytest.mark.asyncio
async def test_slow_sc_does_not_hold_validated_body_work_after_gi():
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, blink_definition, body_goal_association, admitted_core
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from shared.chromie_contracts.plan import FastPlannerAdvance, FastPlannerStreamTerminal
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    sc_started = asyncio.Event()
    release_sc = asyncio.Event()
    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            sc_started.set()
            await release_sc.wait()
            return SocialCognitionResolution(request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="silence", activities=[], reason_summary="No useful acknowledgement now.", model_call_count=1)
        async def resolve_goal_association(self, session, **kwargs):
            return body_goal_association()
        async def stream_fast_advance(self, session, *, request, **kwargs):
            await sc_started.wait()
            advance = FastPlannerAdvance(turn_id=request.sid, disposition="execute", coverage="complete",
                covered_responsibility_refs=["r1"], confidence=1, activities=[{
                    "role": "capability", "activity_id": "blink", "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1}, "timing": "sequential", "source_responsibility_refs": ["r1"],
                }])
            yield FastPlannerStreamTerminal(turn_id=request.sid, advance=advance)
    coordinator = GoalDrivenRuntimeCoordinator(agent_client=Agent(),
        adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([blink_definition()])),
        policy=CognitiveRuntimePolicy(mode="apply"), goal_state_apply=lambda *args, **kwargs: [])
    core, envelope = admitted_core("眨一次眼", sid="sc-work", language="zh-CN", responsibilities=[{
        "local_ref": "r1", "outcome": "Blink once", "bindings": {"count": 1}, "output_mode": "body_action", "confidence": 1,
    }])
    try:
        result = await asyncio.wait_for(coordinator.resolve(None, text="眨一次眼", sid="sc-work",
            core_interpretation=core, turn_envelope=envelope, context={}, history=[], language="zh-CN"), 2)
        assert result.status == "applied", result.fallback_reason
        assert result.interaction_response.speech == []
        assert len(result.interaction_response.capabilities) == 1
        assert result.interaction_response.capabilities[0].args == {"count": 1}
        assert not release_sc.is_set()
        assert any(not task.done() for task in coordinator._auxiliary_execution_tasks)
    finally:
        release_sc.set()
        await asyncio.gather(*tuple(coordinator._auxiliary_execution_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_normal_greeting_work_establishes_need_and_sc_authors_the_reply():
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, new_goal_association, admitted_core
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from shared.chromie_contracts.plan import FastPlannerAdvance, FastPlannerStreamTerminal
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    requests = []
    history = [{"role": "user", "text": "Canonical recent turn"}]
    source_context = {"history": history, "memory_summary": "Only available memory",
        "conversation": {"history": [{"text": "Stale aggregate"}],
                         "session_memory": {"memory_summary": "Owned memory"}},
        "trusted_terminal_evidence": [{"evidence_id": "retained-fact"}]}
    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            requests.append(request)
            assert "conversation" not in request.context
            assert request.context["history"] == history
            assert request.context["session_memory"] == {"memory_summary": "Owned memory"}
            assert request.context["trusted_terminal_evidence"] == [{"evidence_id": "retained-fact"}]
            if request.trigger == "interpretation":
                return SocialCognitionResolution(request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                    disposition="silence", activities=[], reason_summary="An answer can follow without filler.", model_call_count=1)
            need = request.communication_needs[0]
            return SocialCognitionResolution(request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate", reason_summary="Return the greeting.", model_call_count=1,
                need_outcomes={need.need_id: "covered"}, activities=[{
                    "activity_id": "sc-greeting", "text": "你好呀。", "function": "respond", "truth_stage": "context_grounded",
                    "source_goal_ids": need.source_goal_ids, "source_responsibility_refs": need.source_responsibility_refs,
                    "addressed_need_ids": [need.need_id], "delivery_phase": need.delivery_phase,
                }])
        async def resolve_goal_association(self, session, **kwargs):
            return new_goal_association()
        async def stream_fast_advance(self, session, *, request, **kwargs):
            advance = FastPlannerAdvance(turn_id=request.sid, disposition="respond", coverage="complete",
                covered_responsibility_refs=["r1"], confidence=1, activities=[{
                    "role": "complete_response", "activity_id": "greeting", "rationale": "Ordinary greeting is supported by current context.",
                    "source_responsibility_refs": ["r1"], "timing": "parallel",
                }])
            yield FastPlannerStreamTerminal(turn_id=request.sid, advance=advance)
    coordinator = GoalDrivenRuntimeCoordinator(agent_client=Agent(), adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
        policy=CognitiveRuntimePolicy(mode="apply"), goal_state_apply=lambda *args, **kwargs: [])
    core, envelope = admitted_core("你好", sid="sc-greeting", language="zh-CN", responsibilities=[{
        "local_ref": "r1", "outcome": "Return greeting", "bindings": {}, "output_mode": "speech", "confidence": 1,
    }])
    result = await coordinator.resolve(None, text="你好", sid="sc-greeting", core_interpretation=core,
        turn_envelope=envelope, context=source_context, history=[], language="zh-CN")
    assert result.status == "applied", result.fallback_reason
    assert result.terminal_plan.response_text == ""
    assert result.terminal_plan.communicative_acts == []
    assert result.terminal_plan.communication_needs[0].kind == "answer"
    assert result.interaction_response.speech[0].text == "你好呀。"
    assert result.interaction_response.speech[0].metadata["wording_owner"] == "social_cognition"
    assert len([item for item in requests if item.trigger == "work_state"]) == 1
    assert "conversation" in source_context
    await asyncio.gather(*tuple(coordinator._auxiliary_execution_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_ordered_sc_answer_stays_between_work_steps_and_waits_for_delivery():
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, blink_definition
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    plan = CanonicalPlan(plan_id="ordered-work", planner_tier="deep", disposition="mixed", coverage="complete",
        goal_ids=["first", "say", "last"], steps=[
            {"step_id": "first-step", "capability_id": "soridormi.blink_eyes", "args": {"count": 1}, "source_goal_ids": ["first"]},
            {"step_id": "last-step", "capability_id": "soridormi.blink_eyes", "args": {"count": 2}, "source_goal_ids": ["last"]},
        ], goal_outcomes=[
            {"goal_id": "first", "disposition": "execute", "coverage": "complete", "step_ids": ["first-step"]},
            {"goal_id": "say", "disposition": "respond", "coverage": "complete"},
            {"goal_id": "last", "disposition": "execute", "coverage": "complete", "step_ids": ["last-step"]},
        ], communication_needs=[{"need_id": "middle-answer", "owner": "planner", "kind": "answer",
            "reference_id": "ordered-work", "source_goal_ids": ["say"], "before_step_ids": ["last-step"], "after_step_ids": ["first-step"]}])
    current = request(source_refs=[plan.plan_id], goal_ids=plan.goal_ids, communication_needs=plan.communication_needs,
                      context={"canonical_plan_resolution": plan.prompt_projection()})
    result = SocialCognitionResolution(request_id=current.request_id, snapshot_digest=current.snapshot_digest(),
        model_call_count=1, disposition="communicate", reason_summary="Fulfill the ordered answer.",
        need_outcomes={"middle-answer": "covered"}, activities=[{"activity_id": "middle-act", "text": "你好。",
            "function": "respond", "truth_stage": "context_grounded", "source_goal_ids": ["say"], "addressed_need_ids": ["middle-answer"]}])
    runtime = FakeRuntime([blink_definition()])
    response = await CanonicalPlanRuntimeAdapter(runtime).build_social_cognition_response(
        plan=plan, request=current, resolution=result, session_id="ordered", language="zh-CN")
    scheduled = runtime.runtime._scheduled_requests(response)
    assert [item.capability_id for item in scheduled] == ["soridormi.blink_eyes", "chromie.speak", "soridormi.blink_eyes"]
    assert scheduled[0].args == {"count": 1}
    assert scheduled[-1].args == {"count": 2}
    assert scheduled[1].timing == "sequential"
    assert scheduled[1].args["metadata"]["wait_for_voice_release"] is True
    assert scheduled[1].args["metadata"]["communication_completion_goal_ids"] == ["say"]


@pytest.mark.parametrize("unresolved", [[], ["which person the user means"]])
def test_initial_sc_cannot_complete_a_task_before_work_establishes_its_need(unresolved):
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    current = SocialCognitionRequest(request_id="initial", trigger="interpretation", source_refs=["turn"],
        source_turn={"original_text": "先眨眼再说你好"}, interpretation_unresolved=unresolved,
        responsibilities=[CognitiveResponsibilityProposal(local_ref="say", outcome="Say hello after blinking",
            output_mode="speech", bindings={"after": ["blink"]}, confidence=0.8)])
    result = SocialCognitionResolution(request_id=current.request_id, snapshot_digest=current.snapshot_digest(),
        model_call_count=1, disposition="communicate", reason_summary="Premature task answer.", activities=[{
            "activity_id": "too-early", "text": "你好", "function": "respond", "truth_stage": "context_grounded", "source_responsibility_refs": ["say"]}])
    with pytest.raises(ValueError, match="unestablished"):
        result.validate_request(current)


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_turn", [False, True])
async def test_pending_social_playback_is_cancelled_on_interrupt_or_replacement(replace_turn):
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator, CognitiveRuntimePolicy
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    admitted = asyncio.Event()
    held = asyncio.Event()
    cancelled = []
    delivered = []

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                disposition="communicate", reason_summary="A brief acknowledgement is useful.",
                model_call_count=1, activities=[{
                    "activity_id": request.request_id + ":ack", "text": "我明白了。",
                    "function": "acknowledge", "truth_stage": "context_grounded",
                }],
            )

    class Runtime:
        async def submit_response(self, response, **kwargs):
            admitted.set()
            return response

        async def wait_dispatch(self, dispatch):
            await held.wait()

        async def cancel_interaction(self, interaction_id):
            cancelled.append(interaction_id)

        async def record_social_delivery(self, *args, **kwargs):
            delivered.append(args)

    runtime = Runtime()
    runtime.runtime = runtime
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(interaction_runtime=runtime),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    coordinator.schedule_social_expression = lambda *args, **kwargs: None
    work = CognitiveWorkRequest(sid="sid", text="帮我看看", responsibilities=[{"local_ref": "r1", "outcome": "Check the requested item", "confidence": 1.0}], context={}, history=[])
    first = coordinator.start_state_interaction(None, work_request=work, turn_id="first")
    await asyncio.wait_for(admitted.wait(), 1)
    if replace_turn:
        second = coordinator.start_state_interaction(None, work_request=work, turn_id="second")
        for _ in range(20):
            if cancelled:
                break
            await asyncio.sleep(0)
        assert cancelled
        await coordinator.cancel_social_interaction()
        await asyncio.gather(second, return_exceptions=True)
    else:
        await coordinator.cancel_social_interaction()
    await asyncio.gather(first, return_exceptions=True)
    assert cancelled
    assert delivered == []
    assert coordinator._social_dispatches == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("playback_completed", [False, True])
async def test_social_dialogue_history_requires_completed_playback(playback_completed):
    from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
    from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
    recorded = []

    async def waiter(session_id, output):
        assert session_id == "sid"
        return playback_completed

    runtime = InteractionRuntimeCoordinator(
        lambda *args, **kwargs: None, speech_delivery_waiter=waiter,
        communicative_delivery_recorder=lambda *args: recorded.append(args),
    )
    response = InteractionResponse(interaction_id="interaction", speech=[InteractionSpeech(
        id="utterance", text="已经查到了。", metadata={
            "wording_owner": "social_cognition", "source_goal_ids": ["goal"],
            "evidence_refs": ["evidence"], "addressed_need_ids": ["need"],
            "communicative_activity_ids": ["act"],
        },
    )])
    execution = SimpleNamespace(results=[SimpleNamespace(
        request_id="utterance", capability_id="chromie.speak", status="completed", output={},
    )])
    await runtime.record_social_delivery(response, execution, session_id="sid")
    assert bool(recorded) is playback_completed
    if recorded:
        assert recorded[0][1] == "已经查到了。"
        assert recorded[0][2]["source_goal_ids"] == ["goal"]
        assert recorded[0][2]["evidence_refs"] == ["evidence"]
        assert recorded[0][2]["playback_completed"] is True


@pytest.mark.parametrize("disposition", ["unavailable", "refused"])
def test_terminal_fast_limitation_establishes_exact_result_need(disposition):
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator
    from shared.chromie_contracts.plan import FastPlannerAdvance
    from tests.test_cognitive_runtime_pr7 import new_goal_association
    advance = FastPlannerAdvance(
        turn_id="turn", disposition=disposition, coverage="uncertain",
        covered_responsibility_refs=["r1"], confidence=1.0,
        unresolved=["The required provider is unavailable."],
        reason_summary="The supplied provider contract cannot support the request.",
    )
    plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(
        advance=advance, association=new_goal_association(), user_text="Check it.",
    )
    assert plan.steps == []
    assert plan.response_text == ""
    assert len(plan.communication_needs) == 1
    need = plan.communication_needs[0]
    assert need.kind == "result"
    assert need.source_goal_ids == ["goal-1"]
    assert need.source_responsibility_refs == ["r1"]
    assert need.reference_id == plan.plan_id
    assert need.facts["disposition"] == disposition


@pytest.mark.parametrize('stage,kind,valid', [
    ('pre_evidence', None, False), ('pre_evidence', 'acknowledge_work', True),
    ('context_grounded', None, True), ('context_grounded', 'acknowledge_work', False),
])
def test_decoder_enforces_the_existing_progress_kind_contract(stage, kind, valid):
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    current = request(trigger='interpretation', source_turn={'original_text': 'Please check the forecast.'},
                      responsibilities=[CognitiveResponsibilityProposal(local_ref='r1', outcome='check forecast',
                          output_mode='information', confidence=1)])
    raw = response(function='acknowledge', truth_stage=stage, source_responsibility_refs=['r1'])
    if kind is not None:
        raw['activities'][0]['progress_kind'] = kind
    schema = social_cognition_response_schema(current, [])
    assert Draft202012Validator(schema).is_valid(raw) is valid
    if valid:
        SocialCommunicativeAct.model_validate(raw['activities'][0])
    else:
        with pytest.raises(ValueError):
            SocialCommunicativeAct.model_validate(raw['activities'][0])


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_initial_social_failure_and_cancellation_are_retained_in_workflow(cancelled):
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator, CognitiveRuntimePolicy
    rows = []
    class Agent:
        async def resolve_social_cognition(self, *args, **kwargs):
            if cancelled:
                raise asyncio.CancelledError()
            raise RuntimeError('Social Cognition output contract rejected')
    runtime = GoalDrivenRuntimeCoordinator(agent_client=Agent(), adapter=SimpleNamespace(),
        policy=CognitiveRuntimePolicy(mode='apply'), workflow_stage_sink=lambda sid, **row: rows.append((sid, row)))
    with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
        await runtime.resolve_social_interaction(None, request=request(), session_id='sc-failed', snapshot_is_current=lambda: True)
    assert len(rows) == 1
    sid, row = rows[0]
    assert sid == 'sc-failed'
    assert row['stage'] == 'social_cognition'
    assert row['status'] == ('cancelled' if cancelled else 'failed')
    assert row['metadata']['trigger'] == 'work_state'
    assert row['errors']
    assert row['output_payload'] is None


@pytest.mark.asyncio
async def test_social_route_reports_invalid_output_as_contract_error(monkeypatch):
    from agent.app import main
    from fastapi import HTTPException
    class InvalidResolver:
        async def resolve(self, request):
            raise ValueError('prospective communication requires its semantic progress kind')
    monkeypatch.setattr(main, 'social_cognition_resolver', InvalidResolver())
    with pytest.raises(HTTPException) as raised:
        await main.resolve_social_cognition(request())
    assert raised.value.status_code == 422
    assert 'progress kind' in raised.value.detail


@pytest.mark.asyncio
async def test_social_route_preserves_typed_budget_failure_without_unhandled_server_error(monkeypatch):
    from agent.app import main
    from agent.app.clients.sglang_client import SGLangGenerationError
    from fastapi import HTTPException

    class UnavailableResolver:
        async def resolve(self, request):
            raise SGLangGenerationError("actual context overflow", failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget", architecture_attribution="sglang", retryable=False)

    monkeypatch.setattr(main, "social_cognition_resolver", UnavailableResolver())
    with pytest.raises(HTTPException) as raised:
        await main.resolve_social_cognition(request())
    assert raised.value.status_code == 503
    assert raised.value.detail["failure_class"] == "prompt_budget_exceeded"
    assert raised.value.detail["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("spoken", [False, True])
async def test_independent_sc_result_reaches_runtime_expression_queue(spoken):
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator,
    )
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_planner_auxiliary_activity_contract import _Runtime, _definition

    class Runtime(_Runtime):
        async def record_social_delivery(self, *args, **kwargs):
            pass

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return SocialCognitionResolution(
                **response(text="我听到了。" if spoken else "",
                           function="acknowledge" if spoken else "nonverbal",
                           source_goal_ids=[], auxiliary_activities=[{
                    "auxiliary_activity_id": "blink", "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1}, "anchor_kind": "communicative_act", "anchor_id": "sc-act",
                }]), request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                model_call_count=1,
            )

    provider = Runtime([_definition()])
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=CanonicalPlanRuntimeAdapter(provider),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    work = CognitiveWorkRequest(sid="sid", text="你好", responsibilities=[{
        "local_ref": "r1", "outcome": "greet the user", "output_mode": "speech", "confidence": 1.0,
    }], context={
        "user_turn_envelope": {"turn_id": "turn-user", "original_input": {"text": "你好"}},
    })
    task = coordinator.start_state_interaction(None, work_request=work, turn_id="turn-user")
    await task
    await asyncio.gather(*list(coordinator._auxiliary_execution_tasks))
    submitted = [item for response, _ in provider.executed for item in response.capabilities]
    assert len(submitted) == 1
    assert submitted[0].capability_id == "soridormi.blink_eyes"
    assert submitted[0].args == {"count": 1}
    assert submitted[0].metadata["turn_id"] == "turn-user"
    assert submitted[0].metadata["source_goal_ids"] == []
    speeches = [item for response, _ in provider.executed for item in response.speech]
    assert len(speeches) == int(spoken)
    if spoken:
        assert speeches[0].metadata["turn_id"] == "turn-user"


@pytest.mark.asyncio
async def test_sc_delivery_remains_visible_after_canonical_goal_binding():
    from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle

    current = request(goal_ids=[], source_turn={"turn_id": "turn-user"})
    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return await SocialCognitionResolver(Model(response(source_goal_ids=[])), Catalog()).resolve(request)

    ledger = InteractionLedger()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(), policy=CognitiveRuntimePolicy(mode="apply"),
        interaction_ledger=ledger,
    )
    _, response_packet = await coordinator.resolve_social_interaction(
        None, request=current, session_id="sid", snapshot_is_current=lambda: True,
    )
    speech = response_packet.speech[0]
    delivery = PlaybackDeliveryLifecycle(interaction_event_sink=ledger.record_playback_event)
    delivery.register_turn_speech_event(
        session_id="sid", turn_id=speech.metadata["turn_id"], generation=1, orders=[1],
        normalized_text=speech.text, stage="social_cognition", purpose="acknowledge",
        communicative_activity_ids=speech.metadata["communicative_activity_ids"],
    )
    scoped = lambda: ledger.context("sid", goal_ids=["canonical-goal"], turn_id="turn-user")
    assert scoped().already_spoken == []
    delivery.complete_turn_speech_order(generation=1, order=1, session_id="sid", completed=True, reason="completed")
    assert [row["text"] for row in scoped().already_spoken] == [speech.text]


@pytest.mark.asyncio
@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
async def test_sc_expression_uses_real_runtime_queue_and_completion_ledger(fresh, terminal_status):
    from orchestrator.runtime.capability_runtime import MockCapabilityProvider
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator,
    )
    from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_planner_auxiliary_activity_contract import _definition

    ledger = InteractionLedger()
    runtime = InteractionRuntimeCoordinator(lambda _: {"scheduled": True}, interaction_ledger=ledger)
    entered, release = asyncio.Event(), asyncio.Event()
    class Provider(MockCapabilityProvider):
        async def execute(self, request, definition, context):
            entered.set()
            await release.wait()
            result = await super().execute(request, definition, context)
            return result.model_copy(update={"status": terminal_status})
    provider = Provider("test.social")
    runtime.registry.register(_definition("test.social.blink").model_copy(update={
        "provider_id": provider.provider_id, "output_schema": {"type": "object"},
    }))
    runtime.runtime.register_provider(provider)
    current = request(goal_ids=[], source_turn={"turn_id": "turn-user"})
    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return SocialCognitionResolution(
                **response(text="", function="nonverbal", source_goal_ids=[], auxiliary_activities=[{
                    "auxiliary_activity_id": "blink", "capability_id": "test.social.blink", "args": {"count": 1},
                    "anchor_kind": "communicative_act", "anchor_id": "sc-act",
                }]), request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
            )
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=CanonicalPlanRuntimeAdapter(runtime),
        policy=CognitiveRuntimePolicy(mode="apply"), interaction_ledger=ledger,
    )
    resolved = await coordinator.resolve_social_interaction(
        None, request=current, session_id="sid", snapshot_is_current=lambda: fresh,
    )
    if not fresh:
        assert resolved is None
        assert provider.calls == []
        return
    _, packet = resolved
    dispatch = await runtime.submit_response(packet, session_id="sid")
    tasks = [asyncio.create_task(runtime.wait_dispatch(dispatch))]
    if fresh:
        await asyncio.wait_for(entered.wait(), 1)
        pending = ledger.context("sid", goal_ids=["later-goal"], turn_id="turn-user")
        assert any(row["event_type"] == "social_decoration_committed" for row in pending.social_decorations)
        assert not any(row["event_type"] == "social_decoration_completed" for row in pending.social_decorations)
        release.set()
    await asyncio.gather(*tasks)
    assert len(provider.calls) == int(fresh)
    assert not packet.speech
    if fresh:
        assert provider.calls[0].metadata["turn_id"] == "turn-user"
        assert provider.calls[0].metadata["source_goal_ids"] == []
        events = ledger.events("sid")
        assert any(event.event_type == "social_decoration_" + terminal_status for event in events)
        assert not any(event.event_type == "speech_playback_completed" for event in events)

@pytest.mark.asyncio
async def test_optional_provider_loss_does_not_suppress_anchored_speech():
    from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech, CapabilityRequest
    spoken = []
    async def speak(args):
        spoken.append(args["text"])
        return {"scheduled": True}
    ledger = InteractionLedger()
    runtime = InteractionRuntimeCoordinator(speak, interaction_ledger=ledger)
    packet = InteractionResponse(interaction_id="provider-loss", speech=[InteractionSpeech(text="Hello.",
        metadata={"coordination_id": "anchor", "lane_start_policy": "prepared_start"})],
        capabilities=[CapabilityRequest(request_id="blink", capability_id="soridormi.blink_eyes", timing="parallel",
            metadata={"coordination_id": "anchor", "lane_start_policy": "prepared_start",
                "source": "social_cognition_auxiliary_activity", "semantic_owner": "social_cognition",
                "execution_role": "social_decoration", "auxiliary_plan_activity": True, "source_goal_ids": []})],
        metadata={"social_expression_materialized": True, "turn_id": "turn", "session_id": "sid"})
    dispatch = await runtime.submit_response(packet, session_id="sid")
    result = await runtime.wait_dispatch(dispatch)
    assert spoken == ["Hello."]
    assert result.status == "completed"
    assert dispatch.runtime_response.capabilities == []
    assert dispatch.runtime_response.metadata["social_expression_admission_failures"][0]["reason_code"] == "social_expression_unavailable"
    assert any(event.event_type == "social_decoration_failed" for event in ledger.events("sid"))


@pytest.mark.parametrize("kind", ["input", "confirmation"])
@pytest.mark.parametrize("phase", [None, "immediate", "pre_action", "final"])
def test_native_question_need_requires_question_function_without_forcing_optional_speech(kind, phase):
    from shared.chromie_contracts.plan import SocialCommunicationNeed
    current = request(communication_needs=[SocialCommunicationNeed(
        need_id="question", owner="planner", kind=kind, reference_id="plan:1",
        source_goal_ids=["goal:1"], delivery_phase=phase)])
    schema = social_cognition_response_schema(current, [])
    valid = response(function="ask", delivery_phase=phase or "immediate", addressed_need_ids=["question"])
    valid["need_outcomes"] = {"question": "covered"}
    Draft202012Validator(schema).validate(valid)
    for function in ("ask", "respond", "inform"):
        act = {**valid["activities"][0], "function": function}
        accepted = []
        for branch in schema["$defs"]["SocialCommunicativeAct"]["oneOf"]:
            native = copy.deepcopy(branch); native.pop("allOf", None); native["$defs"] = schema["$defs"]
            accepted.append(Draft202012Validator(native).is_valid(act))
        assert any(accepted) == (function == "ask")
        # Optional communication remains a separate decision with no false coverage.
        act["addressed_need_ids"] = []
        Draft202012Validator(schema).validate({**valid, "activities": [act], "need_outcomes": {"question": "pending"}})


def test_social_model_context_compacts_redundant_mind_without_losing_social_self() -> None:
    from agent.app.social_cognition import _social_model_context
    from shared.chromie_contracts.mind import default_mind_profile

    mind = default_mind_profile().prompt_context(max_chars=5000)
    context = {"mind": mind}
    projected = _social_model_context(context)["mind"]

    assert projected["owner_approved"] is True
    assert projected["identity"]["name"] == "Chromie"
    assert "smart" in projected["personality_expression"]["core_traits"]
    assert projected["worldview"]
    assert projected["household_values"]
    assert projected["social_interaction_style"] == mind["social_interaction_style"]
    assert projected["long_term_goals"] == mind["long_term_goals"]
    assert projected["deliberation_policy"] == mind["deliberation_policy"]
    assert projected["experience_tuning_policy"] == mind["experience_tuning_policy"]
    assert "prompt_summary" not in projected
    assert "reflex_policy" not in projected
    assert "internal_components" not in projected.get("self_model", {})
    assert len(json.dumps(projected, ensure_ascii=False)) < len(
        json.dumps(mind, ensure_ascii=False)
    ) * 0.75
