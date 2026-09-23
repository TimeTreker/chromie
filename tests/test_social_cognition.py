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
    assert "never remove this independent interaction duty" in prompt
    assert "produce at least one brief truthful acknowledgement" in prompt
    assert "planner never grants or withholds your communication authority" in prompt
    assert "do not explain a communication or silence decision by saying planner authorized" in prompt


def test_fresh_addressed_task_cannot_silently_disappear_while_work_runs_in_parallel():
    from agent.app.social_cognition import validate_social_cognition_output
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput

    responsibility = CognitiveResponsibilityProposal(
        local_ref="r1", outcome="nod six times", output_mode="body_action", confidence=1.0,
    )
    current = SocialCognitionRequest(
        request_id="sc-parallel-ack", trigger="interpretation", source_refs=["turn:1"],
        responsibilities=[responsibility],
        source_turn={"turn_id": "turn:1", "original_text": "nod your head 6 times please"},
        context={
            "work_decision_pending": True,
            "interaction_context": {"already_spoken": [], "pending_speech": []},
        },
    )
    schema = social_cognition_response_schema(current, [])
    silence = {"disposition": "silence", "activities": [], "reason_summary": "Wait for Planner."}
    assert list(Draft202012Validator(schema).iter_errors(silence))
    with pytest.raises(ValueError, match="requires acknowledgement"):
        validate_social_cognition_output(SocialCognitionOutput.model_validate(silence), current, [])

    acknowledgement = response(
        text="Okay.",
        function="acknowledge",
        truth_stage="pre_evidence",
        progress_kind="acknowledge_work",
        source_goal_ids=[],
        source_responsibility_refs=["r1"],
    )
    Draft202012Validator(schema).validate(acknowledgement)

    duplicate = current.model_copy(deep=True, update={
        "context": {
            **current.context,
            "interaction_context": {
                "already_spoken": [],
                "pending_speech": [{"text": "Okay."}],
            },
        },
    })
    duplicate_schema = social_cognition_response_schema(duplicate, [])
    Draft202012Validator(duplicate_schema).validate(silence)


def test_social_auxiliary_anchor_is_mechanical_parent_linkage() -> None:
    from agent.app.social_cognition import _materialize_communicative_auxiliary_anchors
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput

    raw = response(
        text="Hi!",
        function="acknowledge",
        source_goal_ids=[],
        auxiliary_activities=[{
            "auxiliary_activity_id": "wave-1",
            "capability_id": "test.wave",
            "anchor_kind": "plan_step",
            "anchor_id": "wrong-parent",
            "args": {},
        }],
    )

    materialized = _materialize_communicative_auxiliary_anchors(raw)

    auxiliary = materialized["activities"][0]["auxiliary_activities"][0]
    assert auxiliary["anchor_kind"] == "communicative_act"
    assert auxiliary["anchor_id"] == materialized["activities"][0]["activity_id"]
    # The semantic expression choice itself is unchanged and the DTO now accepts it.
    assert auxiliary["capability_id"] == "test.wave"
    SocialCognitionOutput.model_validate(materialized)


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


def test_terminal_work_failure_result_need_cannot_choose_silence():
    from shared.chromie_contracts.plan import SocialCommunicationNeed

    need = SocialCommunicationNeed(
        need_id="need:failure", owner="runtime", kind="result",
        source_goal_ids=["goal:1"], reference_id="work_failure:turn:planner",
        facts={"status": "failed", "known_cause": "The proposed actions were inconsistent.", "required_result_update": True},
        delivery_phase="immediate",
    )
    current = request(
        communication_needs=[need],
        context={
            "work": [{"id": "work:1", "status": "failed"}],
            "active_goal_snapshots": [{"goal_id": "goal:1", "status": "active"}],
            "work_failure": {
                "status": "failed",
                "known_cause": "The proposed actions were inconsistent.",
            },
        },
    )
    schema = social_cognition_response_schema(current, [])
    assert "silence" not in schema["properties"]["disposition"]["enum"]
    assert schema["properties"]["need_outcomes"]["properties"][need.need_id]["const"] == "covered"


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
    primary_source = model.calls[0][0].split("\nRequired output contract JSON:\n", 1)[0]
    deep_source = deep.calls[0][0].split("\nRequired output contract JSON:\n", 1)[0]
    assert primary_source == deep_source
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
    fresh_id = "fresh"
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
    fresh_contract = schema["$defs"]["SocialCommunicativeAct"]["oneOf"][0]["properties"]["activity_id"]
    assert fresh_contract["maxLength"] == 24
    assert fresh_contract["not"]["enum"] == ["existing"]
    assert "maxItems" not in schema["properties"]["activities"]
    for contract in (schema, {"$defs": schema["$defs"], "oneOf": schema["oneOf"]}):
        validator = Draft202012Validator(contract)
        assert validator.is_valid(response(activity_id="existing", text=words))
        assert not validator.is_valid(response(activity_id="existing", text="Different words."))
        assert validator.is_valid(response(activity_id="fresh", text="Different words."))
        repeated = response()
        repeated["activities"] = [
            response(activity_id=f"fresh-{index}", text=words)["activities"][0]
            for index in range(12)
        ]
        assert validator.is_valid(repeated)


@pytest.mark.asyncio
async def test_raw_schema_rejects_nested_identity_violation_before_dto_or_retry():
    current = request(context={"interaction_context": {"already_spoken": [{
        "text": "Old words.", "metadata": {"communicative_activity_ids": ["old"]},
    }]}})
    # This is a valid free-standing DTO. The request-specific Schema prevents
    # reusing a delivered identity with different wording while leaving fresh IDs open.
    raw = response(activity_id="old", text="New words.")
    model = Model(raw)
    with pytest.raises(ValueError, match="raw Schema rejected"):
        await SocialCognitionResolver(model, Catalog()).resolve(current)
    assert len(model.calls) == 1


@pytest.mark.parametrize("identity,accepted", [
    ("", False), ("a", True), ("existing", False), ("existing2", True),
    ("x" * 23, True), ("x" * 24, False), ("x" * 23 + "y", True),
    ("y" * 24, True), ("y" * 25, False),
    ("failure_acknowledgement_001", False), ("existing" + "0" * 30, False),
])
def test_native_fresh_identity_pattern_enforces_length_without_decoder_length_keywords(identity, accepted):
    import re

    retained = ["existing", "x" * 24, "retained" * 8]
    current = request(context={"interaction_context": {"already_spoken": [{
        "text": "Old words.", "metadata": {"communicative_activity_ids": retained},
    }]}})
    schema = social_cognition_response_schema(current, [])
    fresh = schema["$defs"]["SocialCommunicativeAct"]["oneOf"][0]["properties"]["activity_id"]
    # The native decoder honors the regex but can ignore sibling min/maxLength.
    # Its accepted language must still exclude empty, long and reserved new IDs.
    assert bool(re.fullmatch(fresh["pattern"], identity)) is accepted
    assert Draft202012Validator(schema).is_valid(response(
        activity_id=retained[-1], text="Old words.",
    ))


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
@pytest.mark.parametrize("state", ["committed", "completed", "cancelled"])
@pytest.mark.parametrize("path", ["optional", "required"])
async def test_state_social_refreshes_continuity_after_previous_speech(state, path):
    from orchestrator.runtime.capability_runtime import CapabilityRegistry, CapabilityRuntime
    from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    prior_speech = asyncio.Event()
    previous = asyncio.create_task(prior_speech.wait())
    ledger = InteractionLedger()
    original = {"history": [{"sid": "earlier", "role": "user", "text": "Hello"}],
                "active_goal_snapshots": [{"goal_id": "goal:1", "work_status": "planning"}],
                "active_task_snapshots": [{"task_id": "task:1", "status": "planning"}],
                "user_turn_envelope": {"turn_id": "turn"}}
    live = copy.deepcopy(original)
    requests, expression_contexts, refreshes = [], [], []

    def refresh(sid):
        refreshes.append(sid)
        return live

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            requests.append(request)
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                need_outcomes={need.need_id: "pending" for need in request.communication_needs},
                disposition="silence", activities=[], reason_summary="No additional speech needed.", model_call_count=1,
            )

    async def build_response(**kwargs):
        expression_contexts.append(kwargs["context"])
        assert kwargs["plan"] == plan
        return SimpleNamespace()

    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(),
        adapter=SimpleNamespace(
            interaction_runtime=SimpleNamespace(runtime=CapabilityRuntime(CapabilityRegistry())),
            build_social_cognition_response=build_response,
        ),
        policy=CognitiveRuntimePolicy(mode="apply"), context_refresh=refresh, interaction_ledger=ledger,
    )
    coordinator.schedule_social_expression = lambda *args, context, **kwargs: expression_contexts.append(context)
    coordinator._social_turns["sid"] = ("previous", previous, "turn" if path == "optional" else "sid")
    coordinator._social_dispatches["previous"] = "previous-delivery"
    plan = CanonicalPlan(plan_id="plan", planner_tier="fast", disposition="execute", coverage="complete",
        goal_ids=["goal:1"], steps=[{"step_id": "nod", "capability_id": "soridormi.nod_yes", "source_goal_ids": ["goal:1"]}],
        goal_outcomes=[{"goal_id": "goal:1", "disposition": "execute", "coverage": "complete", "step_ids": ["nod"]}],
        communication_needs=[{"need_id": "progress", "owner": "planner", "kind": "answer", "reference_id": "plan", "source_goal_ids": ["goal:1"]}])
    work = CognitiveWorkRequest(sid="sid", text="Nod once", context=copy.deepcopy(original), history=original["history"],
        responsibilities=[{"local_ref": "r1", "outcome": "Nod once", "output_mode": "body_action", "confidence": 1.0}])
    pending = (
        coordinator.start_state_interaction(None, work_request=work, turn_id="turn", plan=plan)
        if path == "optional" else asyncio.create_task(coordinator.resolve_plan_interaction(
            None, plan=plan, work_request=work, session_id="sid", language="en", context=copy.deepcopy(original),
        ))
    )
    try:
        await asyncio.sleep(0)
        assert not requests and not refreshes
        # The authoritative owners advance while the previous same-turn speech holds SC.
        live["active_goal_snapshots"] = [{"goal_id": "goal:1", "work_status": "executing" if state == "committed" else state}]
        live["active_task_snapshots"] = [] if state != "committed" else [{"task_id": "task:1", "status": "executing"}]
        live["recent_goal_snapshots"] = [{"goal_id": "goal:1", "work_status": state}]
        live["history"] += [{"sid": "sid", "role": "user", "text": "Nod once"},
                            {"sid": "later", "role": "user", "text": "Future turn"}]
        ledger.append(session_id="sid", owner="trusted_capability_runtime" if state == "committed" else "execution_closure", domain="activity",
            event_type="activity_" + state, state=state, subject_id="nod", event_id="event:" + state,
            turn_id="turn", interaction_id="work", goal_ids=["goal:1"], canonical_plan_id="plan", capability_id="soridormi.nod_yes",
            evidence_refs=["execution:" + state] if state != "committed" else [])
        prior_speech.set()
        await asyncio.wait_for(pending, 1)
        assert len(requests) == 1
        packet = requests[0]
        assert packet.context["active_goal_snapshots"] == live["active_goal_snapshots"]
        assert packet.context["active_task_snapshots"] == live["active_task_snapshots"]
        assert packet.context["recent_goal_snapshots"] == live["recent_goal_snapshots"]
        assert packet.context["interaction_context"]["activity"][-1]["state"] == state
        assert "runtime_admission" not in packet.context
        assert packet.context["history"] == original["history"]
        assert packet.responsibilities == work.responsibilities
        assert packet.source_refs == [plan.plan_id] and packet.goal_ids == plan.goal_ids
        assert packet.context["canonical_plan_resolution"] == plan.prompt_projection()
        assert expression_contexts == [packet.context]
        assert refreshes == ["sid"]
        assert work.context == original
    finally:
        prior_speech.set()
        coordinator._social_dispatches.pop("previous", None)
        await coordinator.cancel_social_interaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["same_work", "cancelled_work", "other_work", "interpretation"])
async def test_pending_state_social_result_rechecks_actual_work(change):
    from orchestrator.runtime.capability_runtime import CapabilityRegistry, CapabilityRuntime, MockCapabilityProvider
    from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.interaction import InteractionResponse
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_capability_runtime import _body_definition

    started = {name: asyncio.Event() for name in ("work", "other")}
    release = {name: asyncio.Event() for name in started}

    class Provider(MockCapabilityProvider):
        async def execute(self, request, definition, context):
            started[request.request_id].set()
            await release[request.request_id].wait()
            return await super().execute(request, definition, context)

    registry = CapabilityRegistry()
    registry.register(_body_definition(exclusive_group=None))
    runtime = CapabilityRuntime(registry)
    runtime.register_provider(Provider("mock.body"))
    receipts = {}
    for name, goal, turn in (("work", "goal:1", "turn"), ("other", "goal:2", "other-turn")):
        receipts[name] = await runtime.submit(InteractionResponse(
            interaction_id=name, capabilities=[{
                "request_id": name, "capability_id": "soridormi.nod_yes", "timing": "parallel",
                "metadata": {"source_goal_ids": [goal], "turn_id": turn, "canonical_plan_id": name},
            }],
        ))
    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), 1)
    deciding, answer = asyncio.Event(), asyncio.Event()
    calls, delivered = [], []

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            calls.append(request)
            deciding.set()
            await answer.wait()
            return SocialCognitionResolution(
                **response(text="你好。" if change == "interpretation" else "动作还在进行中。",
                           source_goal_ids=request.goal_ids),
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
            )

    class Delivery:
        async def submit_response(self, packet, **kwargs):
            delivered.append(packet)
            return packet

        async def wait_dispatch(self, dispatch):
            return SimpleNamespace(status="completed")

        async def record_social_delivery(self, *args, **kwargs):
            return True

    delivery = Delivery()
    delivery.runtime = runtime
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(interaction_runtime=delivery),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    plan = CanonicalPlan(
        plan_id="work", planner_tier="fast", disposition="execute", coverage="complete",
        goal_ids=["goal:1"], steps=[{
            "step_id": "nod", "capability_id": "soridormi.nod_yes", "source_goal_ids": ["goal:1"],
        }], goal_outcomes=[{
            "goal_id": "goal:1", "disposition": "execute", "coverage": "complete", "step_ids": ["nod"],
        }],
    )
    work = CognitiveWorkRequest(sid="sid", text="你好，点一下头", responsibilities=[{
        "local_ref": "r1", "outcome": "greet", "output_mode": "speech", "confidence": 1.0,
    }])
    pending = coordinator.start_state_interaction(
        None, work_request=work, turn_id="turn", plan=None if change == "interpretation" else plan,
    )
    try:
        await asyncio.wait_for(deciding.wait(), 1)
        finished = "other" if change == "other_work" else "work"
        if change == "cancelled_work":
            await runtime.cancel_interaction("work")
        else:
            release[finished].set()
        await runtime.wait_terminal(receipts.pop(finished))
        answer.set()
        result = await asyncio.wait_for(pending, 1)
        assert len(calls) == 1
        stale = change in {"same_work", "cancelled_work"}
        assert (result is None) == stale
        assert bool(delivered) == (not stale)
    finally:
        answer.set()
        for event in release.values():
            event.set()
        await asyncio.gather(*(runtime.wait_terminal(receipt) for receipt in receipts.values()))
        await coordinator.cancel_social_interaction()


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
    from orchestrator.runtime.session import SessionTracker

    sc_started = asyncio.Event()
    release_sc = asyncio.Event()
    sessions = SessionTracker(resource_sampling_mode="off")
    sid = sessions.create()
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
        policy=CognitiveRuntimePolicy(mode="apply"), goal_state_apply=lambda *args, **kwargs: [],
        social_task_tracker=sessions.track_social_task)
    core, envelope = admitted_core("眨一次眼", sid=sid, language="zh-CN", responsibilities=[{
        "local_ref": "r1", "outcome": "Blink once", "bindings": {"count": 1}, "output_mode": "body_action", "confidence": 1,
    }])
    try:
        result = await asyncio.wait_for(coordinator.resolve(None, text="眨一次眼", sid=sid,
            core_interpretation=core, turn_envelope=envelope, context={}, history=[], language="zh-CN"), 2)
        assert result.status == "applied", result.fallback_reason
        assert result.interaction_response.speech == []
        assert len(result.interaction_response.capabilities) == 1
        assert result.interaction_response.capabilities[0].args == {"count": 1}
        assert not release_sc.is_set()
        assert any(not task.done() for task in coordinator._auxiliary_execution_tasks)
        sessions.state[sid]["llm_done"] = True
        sessions.maybe_done(sid)
        assert not sessions.state[sid]["done_logged"]
    finally:
        release_sc.set()
        await asyncio.gather(*tuple(coordinator._auxiliary_execution_tasks), return_exceptions=True)
    assert sessions.state[sid]["pending_social_tasks"] == 0
    assert sessions.state[sid]["done_logged"]


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


@pytest.mark.parametrize("meaning_uncertainties", [[], [{
    "local_ref": "u1",
    "kind": "referent",
    "description": "which person the user means",
    "responsibility_refs": ["say"],
}]])
def test_initial_sc_cannot_complete_a_task_before_work_establishes_its_need(meaning_uncertainties):
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    current = SocialCognitionRequest(request_id="initial", trigger="interpretation", source_refs=["turn"],
        source_turn={"original_text": "先眨眼再说你好"}, meaning_uncertainties=meaning_uncertainties,
        responsibilities=[CognitiveResponsibilityProposal(local_ref="say", outcome="Say hello after blinking",
            output_mode="speech", bindings={"after": ["blink"]}, confidence=0.8)])
    result = SocialCognitionResolution(request_id=current.request_id, snapshot_digest=current.snapshot_digest(),
        model_call_count=1, disposition="communicate", reason_summary="Premature task answer.", activities=[{
            "activity_id": "too-early", "text": "你好", "function": "respond", "truth_stage": "context_grounded", "source_responsibility_refs": ["say"]}])
    with pytest.raises(ValueError, match="unestablished"):
        result.validate_request(current)


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["interrupt", "new_turn", "same_turn", "same_turn_interrupt"])
async def test_pending_social_playback_is_cancelled_only_on_interrupt_or_replacement(transition):
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
            return SimpleNamespace(status="completed")

        async def cancel_interaction(self, interaction_id):
            cancelled.append(interaction_id)

        async def record_social_delivery(self, *args, **kwargs):
            delivered.append(args)
            return True

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
    if transition.startswith("same_turn"):
        second = coordinator.start_state_interaction(
            None, work_request=work, turn_id="first", trigger="work_state", source_refs=["plan"],
        )
        for _ in range(5):
            await asyncio.sleep(0)
        assert not first.done() and not second.done()
        assert cancelled == [] and delivered == []
        if transition == "same_turn_interrupt":
            await coordinator.cancel_social_interaction()
            await asyncio.gather(first, second, return_exceptions=True)
            assert cancelled and delivered == []
            assert coordinator._social_dispatches == {}
            return
        held.set()
        await asyncio.gather(first, second)
        assert len(delivered) == 2 and cancelled == []
        assert coordinator._social_dispatches == {}
        return
    if transition == "new_turn":
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
    complete = await runtime.record_social_delivery(response, execution, session_id="sid")
    assert complete is playback_completed
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


@pytest.mark.parametrize('stage,kind,schema_valid,dto_valid', [
    ('pre_evidence', None, False, False),
    ('pre_evidence', 'acknowledge_work', True, True),
    # Generic DTO permits a context-grounded acknowledgement, but the dynamic
    # interpretation-ingress schema now rejects it for non-speech task Work.
    ('context_grounded', None, False, True),
    ('context_grounded', 'acknowledge_work', False, False),
])
def test_decoder_enforces_the_existing_progress_kind_contract(stage, kind, schema_valid, dto_valid):
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    current = request(trigger='interpretation', source_turn={'original_text': 'Please check the forecast.'},
                      responsibilities=[CognitiveResponsibilityProposal(local_ref='r1', outcome='check forecast',
                          output_mode='information', confidence=1)])
    raw = response(function='acknowledge', truth_stage=stage, source_responsibility_refs=['r1'])
    if kind is not None:
        raw['activities'][0]['progress_kind'] = kind
    schema = social_cognition_response_schema(current, [])
    assert Draft202012Validator(schema).is_valid(raw) is schema_valid
    if dto_valid:
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
@pytest.mark.parametrize("primary", ["none", "same", "same_compatible", "conflicting", "compatible"])
async def test_independent_sc_result_reaches_runtime_expression_queue(spoken, primary):
    from orchestrator.runtime.capability_runtime import CapabilityRegistry, CapabilityRuntime
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator,
    )
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_planner_auxiliary_activity_contract import _Runtime, _definition

    class Runtime(_Runtime):
        def __init__(self, definitions):
            super().__init__(definitions)
            self.runtime = CapabilityRuntime(CapabilityRegistry())

        async def record_social_delivery(self, *args, **kwargs):
            return True

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return SocialCognitionResolution(
                **response(text="我听到了。" if spoken else "",
                           function="acknowledge" if spoken else "nonverbal",
                           source_goal_ids=[], auxiliary_activities=[{
                    "auxiliary_activity_id": "blink", "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 3}, "anchor_kind": "communicative_act", "anchor_id": "sc-act",
                    "reason_summary": "An independently intended social acknowledgement, not task fulfillment.",
                }]), request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
                model_call_count=1,
            )

    social_definition = _definition()
    if primary == "same_compatible":
        social_definition = social_definition.model_copy(update={
            "exclusive_group": None, "metadata": {
                **social_definition.metadata, "resource_claims": [],
            },
        })
    definitions = [social_definition]
    plan = None
    if primary != "none":
        capability_id = "soridormi.blink_eyes" if primary.startswith("same") else "test.primary.motion"
        if not primary.startswith("same"):
            definition = _definition(capability_id)
            if primary == "compatible":
                definition = definition.model_copy(update={
                    "exclusive_group": "other", "metadata": {
                        **definition.metadata, "resource_claims": ["other"],
                    },
                })
            definitions.append(definition)
        plan = CanonicalPlan(
            plan_id="primary-work", planner_tier="fast", disposition="execute", coverage="complete",
            goal_ids=["goal:1"], steps=[{
                "step_id": "primary", "capability_id": capability_id, "args": {"count": 2},
                "source_goal_ids": ["goal:1"],
            }], goal_outcomes=[{
                "goal_id": "goal:1", "disposition": "execute", "coverage": "complete", "step_ids": ["primary"],
            }],
        )
    original_plan = plan.model_dump() if plan else None
    provider = Runtime(definitions)
    tracked_tasks = []
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=CanonicalPlanRuntimeAdapter(provider),
        policy=CognitiveRuntimePolicy(mode="apply"),
        social_task_tracker=lambda sid, task: tracked_tasks.append((sid, task)),
    )
    work = CognitiveWorkRequest(sid="sid", text="眨两下眼睛", responsibilities=[{
        "local_ref": "r1", "outcome": "眨两下眼睛", "output_mode": "body_action", "confidence": 1.0,
    }], context={
        "user_turn_envelope": {"turn_id": "turn-user", "original_input": {"text": "眨两下眼睛"}},
    })
    task = coordinator.start_state_interaction(None, work_request=work, turn_id="turn-user", plan=plan)
    _, packet = await task
    await asyncio.gather(*list(coordinator._auxiliary_execution_tasks))
    assert ("sid", task) in tracked_tasks
    assert all(sid == "sid" for sid, _ in tracked_tasks)
    assert (plan.model_dump() if plan else None) == original_plan
    submitted = [item for response, _ in provider.executed for item in response.capabilities]
    blocked = primary in {"same", "conflicting"}
    assert len(submitted) == (0 if blocked else 1)
    if blocked:
        assert packet.metadata["social_expression_admission"]["reasons"] == ["resource_conflict:soridormi.blink_eyes"]
    else:
        assert submitted[0].capability_id == "soridormi.blink_eyes"
        assert submitted[0].args == {"count": 3}
        assert submitted[0].metadata["turn_id"] == "turn-user"
        assert submitted[0].metadata["source_goal_ids"] == []
    speeches = [item for response, _ in provider.executed for item in response.speech]
    assert len(speeches) == int(spoken)
    if spoken:
        assert speeches[0].metadata["turn_id"] == "turn-user"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "provider", "playback"])
async def test_session_joins_social_delivery_and_retains_failed_completion(failure):
    from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator
    from orchestrator.runtime.session import SessionTracker
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    tracker = SessionTracker(resource_sampling_mode="off")
    sid = tracker.create()
    admitted, release = asyncio.Event(), asyncio.Event()

    class Runtime:
        async def submit_response(self, packet, **kwargs):
            admitted.set()
            return packet

        async def wait_dispatch(self, dispatch):
            await release.wait()
            return SimpleNamespace(status="failed" if failure == "provider" else "completed")

        async def record_social_delivery(self, *args, **kwargs):
            return failure != "playback"

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return SocialCognitionResolution(
                **response(source_goal_ids=[]), request_id=request.request_id,
                snapshot_digest=request.snapshot_digest(), model_call_count=1,
            )

    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=SimpleNamespace(interaction_runtime=Runtime()),
        policy=CognitiveRuntimePolicy(mode="apply"), social_task_tracker=tracker.track_social_task,
    )
    work = CognitiveWorkRequest(sid=sid, text="你好", responsibilities=[{
        "local_ref": "r1", "outcome": "greet", "output_mode": "speech", "confidence": 1.0,
    }])
    task = coordinator.start_state_interaction(None, work_request=work, turn_id="turn")
    await asyncio.wait_for(admitted.wait(), 1)
    tracker.state[sid]["llm_done"] = True
    tracker.maybe_done(sid)
    assert not tracker.state[sid]["done_logged"]
    release.set()
    result, = await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    state = tracker.state[sid]
    assert state["done_logged"] and state["pending_social_tasks"] == 0
    assert bool(state["social_task_failures"]) is bool(failure)
    assert isinstance(result, RuntimeError) is bool(failure)
    assert state["workflow_report"]["termination_state"] == ("failed" if failure else "complete")
    assert coordinator._social_dispatches == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["planner_contract", "planner_exception", "social", "playback", "interrupt"])
async def test_planner_failure_joins_independent_social_delivery_without_hiding_failure(failure):
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator,
    )
    from shared.chromie_contracts.plan import FastPlannerStreamFailure
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    from tests.test_cognitive_runtime_pr7 import FakeRuntime, admitted_core, body_goal_association

    social_started, planner_failed, release_social = asyncio.Event(), asyncio.Event(), asyncio.Event()
    submitted, cancelled = [], []

    class Agent:
        async def resolve_social_cognition(self, session, *, request, **kwargs):
            social_started.set()
            try:
                await release_social.wait()
            except asyncio.CancelledError:
                cancelled.append(request.request_id)
                raise
            if failure == "social":
                raise OSError("SC service failed")
            if request.context.get("work_failure"):
                failure_context = request.context["work_failure"]
                expected_reason = (
                    "planner transport failed"
                    if failure == "planner_exception"
                    else "Direction source missing."
                )
                assert failure_context["known_cause"] == expected_reason
                assert len(request.communication_needs) == 1
                need = request.communication_needs[0]
                assert need.owner == "runtime" and need.kind == "result"
                assert need.facts["known_cause"] == expected_reason
                assert need.facts["required_result_update"] is True
                return SocialCognitionResolution(
                    request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                    disposition="communicate", reason_summary="The requested Work failed before completion.",
                    activities=[{"activity_id": "work-failed", "text": f"I couldn't complete that turn because {expected_reason}",
                                 "function": "inform", "truth_stage": "context_grounded",
                                 "source_responsibility_refs": ["turn"],
                                 "addressed_need_ids": [need.need_id],
                                 "delivery_phase": "immediate"}],
                    need_outcomes={need.need_id: "covered"},
                )
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                disposition="communicate", reason_summary="The greeting is independent of the turn action.",
                activities=[{"activity_id": "greet", "text": "Hello!", "function": "respond",
                             "truth_stage": "context_grounded", "source_responsibility_refs": ["hello"]}],
            )

        async def resolve_goal_association(self, *args, **kwargs):
            return body_goal_association(source_ref="turn").model_copy(
                update={"non_goal_responsibility_refs": ["hello"]},
            )

        async def stream_fast_advance(self, session, *, request, **kwargs):
            await social_started.wait()
            planner_failed.set()
            if failure == "planner_exception":
                raise RuntimeError("planner transport failed")
            yield FastPlannerStreamFailure(
                turn_id=request.sid, failure_stage="before_commit",
                failure_class="fast_stream_contract_invalid", failure_domain="model_contract",
                reason="Direction source missing.", retryable=False,
            )

    class Runtime(FakeRuntime):
        async def submit_response(self, packet, **kwargs):
            submitted.append(packet)
            return packet

        async def record_social_delivery(self, *args, **kwargs):
            return failure != "playback"

    runtime = Runtime()
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=Agent(), adapter=CanonicalPlanRuntimeAdapter(runtime),
        policy=CognitiveRuntimePolicy(mode="apply"),
    )
    core, envelope = admitted_core("Hello, then turn left.", sid="mixed", language="en-US", responsibilities=[
        {"local_ref": "hello", "outcome": "Respond to the greeting", "output_mode": "speech", "continuity_scope": "turn", "confidence": 1},
        {"local_ref": "turn", "outcome": "Turn left", "output_mode": "body_action", "continuity_scope": "goal", "confidence": 1},
    ], cognitive_requests=[
        {"authority": "social_cognition", "responsibility_refs": ["hello", "turn"], "reason_summary": "Own interaction for the complete admitted turn."},
        {"authority": "planner", "responsibility_refs": ["turn"], "reason_summary": "Plan the requested turn."},
    ])
    task = asyncio.create_task(coordinator.resolve(
        None, text=envelope.original_input.text, sid="mixed", language="en-US",
        context={}, history=[], core_interpretation=core, turn_envelope=envelope,
    ))
    try:
        await asyncio.wait_for(planner_failed.wait(), 1)
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done(), "Work failure must not terminate pending independent communication"
        assert not cancelled
        if failure == "interrupt":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled and not submitted
            return
        release_social.set()
        result = await asyncio.wait_for(task, 1)
        assert result.status == "error"
        assert result.metadata["failure_class"] == (
            "RuntimeError" if failure == "planner_exception" else "fast_stream_contract_invalid"
        )
        assert not cancelled
        assert all(not packet.capabilities for packet in submitted)
        if failure in {"social", "playback"}:
            assert result.interaction_response is None
            assert any(item.get("stage") == "social_cognition" for item in result.metadata["stage_diagnostics"])
        else:
            assert len(submitted) == 2
            assert submitted[0].speech[0].text == "Hello!"
            expected_reason = (
                "planner transport failed"
                if failure == "planner_exception"
                else "Direction source missing."
            )
            assert expected_reason in result.interaction_response.speech[0].text
            assert result.interaction_response.metadata["presentation_already_dispatched"] is True
    finally:
        release_social.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await coordinator.cancel_social_interaction()


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
async def test_social_terminal_ledger_has_one_writer_through_cognitive_closure():
    from orchestrator.orchestrator import VoiceAssistant
    from orchestrator.runtime.capability_runtime import MockCapabilityProvider
    from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
    from orchestrator.runtime.interaction_ledger import InteractionLedger
    from shared.chromie_contracts.interaction import CapabilityRequest, InteractionResponse
    from tests.test_planner_auxiliary_activity_contract import _definition

    class CountingLedger(InteractionLedger):
        def __init__(self):
            super().__init__()
            self.social_result_calls = 0

        def record_social_results(self, **kwargs):
            self.social_result_calls += 1
            return super().record_social_results(**kwargs)

    ledger = CountingLedger()
    runtime = InteractionRuntimeCoordinator(
        lambda _: {"scheduled": True},
        interaction_ledger=ledger,
    )
    provider = MockCapabilityProvider("test.social")
    runtime.registry.register(
        _definition("test.social.blink").model_copy(
            update={
                "provider_id": provider.provider_id,
                "output_schema": {"type": "object"},
            }
        )
    )
    runtime.runtime.register_provider(provider)
    packet = InteractionResponse(
        interaction_id="single-social-ledger-writer",
        capabilities=[CapabilityRequest(
            request_id="blink",
            capability_id="test.social.blink",
            args={"count": 1},
            timing="parallel",
            metadata={
                "source": "social_cognition_auxiliary_activity",
                "semantic_owner": "social_cognition",
                "execution_role": "social_decoration",
                "auxiliary_plan_activity": True,
                "source_goal_ids": [],
            },
        )],
        metadata={
            "social_expression_materialized": True,
            "turn_id": "turn-social-ledger",
            "session_id": "sid-social-ledger",
        },
    )
    dispatch = await runtime.submit_response(packet, session_id="sid-social-ledger")
    execution = await runtime.wait_dispatch(dispatch)
    assert ledger.social_result_calls == 1

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.interaction_runtime = runtime
    assistant.session_log = lambda *args, **kwargs: None
    status = await assistant._close_cognitive_execution(
        response=dispatch.source_response,
        execution=execution,
        session_id="sid-social-ledger",
        generation=0,
        provider_status=None,
    )
    assert status == "not_applicable"
    assert ledger.social_result_calls == 1


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


def test_social_expression_cardinality_is_semantic_not_schema_policy() -> None:
    from agent.app.social_cognition import social_cognition_response_schema
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput, SocialCognitionRequest

    current = SocialCognitionRequest(
        request_id="sc-autonomous-expression",
        trigger="interpretation",
        source_refs=["turn:1"],
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1",
            outcome="Greet the person and answer their social question.",
            output_mode="speech",
            continuity_scope="turn",
            confidence=1.0,
        )],
        source_turn={"turn_id": "turn:1", "original_text": "Hello, how are you?"},
        context={"interaction_context": {"already_spoken": [], "pending_speech": []}},
    )
    candidates = [{
        "capability_id": "test.wave",
        "input_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
    }]

    schema = social_cognition_response_schema(current, candidates)
    assert "maxItems" not in schema["properties"]["activities"]
    contract = schema["$defs"]["SocialCommunicativeAct"]
    for branch in contract.get("oneOf", [contract]):
        assert "maxItems" not in branch["properties"]["auxiliary_activities"]

    # Cardinality is a semantic choice: more than the old 3-expression/8-act quotas
    # remains structurally legal when every item otherwise satisfies the contract.
    auxiliaries = [{
        "auxiliary_activity_id": f"wave-{index}",
        "capability_id": "test.wave",
        "args": {"count": 1},
        "anchor_kind": "communicative_act",
        "anchor_id": "sc-act",
    } for index in range(5)]
    rich = response(
        text="Hi!",
        function="respond",
        source_goal_ids=[],
        source_responsibility_refs=["r1"],
        auxiliary_activities=auxiliaries,
    )
    Draft202012Validator(schema).validate(rich)
    SocialCognitionOutput.model_validate(rich)


def test_social_authority_uses_semantic_stop_condition_not_action_quota() -> None:
    from agent.app.social_cognition import SOCIAL_COGNITION_AUTHORITY_PROMPT

    prompt = SOCIAL_COGNITION_AUTHORITY_PROMPT.lower()
    assert "there is no target number of expressions" in prompt
    assert "no requirement to use an available capability" in prompt
    assert "contributes distinct social meaning" in prompt
    assert "availability alone is never a reason to add one" in prompt
    assert "stop the decision as soon as the intended social response is complete" in prompt
    assert "do not create a sibling communicative act merely to enumerate another gesture" in prompt


def test_social_model_context_does_not_reinterpret_generic_dialogue_history() -> None:
    from agent.app.social_cognition import _social_model_context

    interaction = {
        "already_spoken": [],
        "pending_speech": [],
        "prior_delivered_speech": [{"turn_id": "old", "text": "Hi!"}],
    }
    projected = _social_model_context({
        "history": [
            {"role": "user", "text": "Hello, how are you?"},
            {"role": "assistant", "text": "Huh, that didn't go through."},
        ],
        "core_interpretation": {"responsibilities": [{"outcome": "old duplicate"}]},
        "interaction_context": interaction,
        "other_evidence": {"status": "retain"},
    })

    assert "history" not in projected
    assert "core_interpretation" not in projected
    assert projected["interaction_context"] == interaction
    assert projected["other_evidence"] == {"status": "retain"}


@pytest.mark.parametrize("core_turn", ["current", "older", ""])
def test_social_context_retains_current_umi_routing_without_widening_act_scope(core_turn):
    from agent.app.social_cognition import social_cognition_prompt, validate_social_cognition_output
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput

    greeting = CognitiveResponsibilityProposal(
        local_ref="greet", outcome="Greet the user", output_mode="speech",
        continuity_scope="turn", confidence=1,
    )
    body = CognitiveResponsibilityProposal(
        local_ref="turn", outcome="Turn left", output_mode="body_action", confidence=1,
    )
    core = {
        "authority": "user_meaning_interpretation", "turn_id": core_turn,
        "responsibilities": [greeting.model_dump(), body.model_dump()],
        "meaning_uncertainties": [],
        "cognitive_requests": [
            {"authority": "social_cognition", "responsibility_refs": ["greet"]},
            {"authority": "planner", "responsibility_refs": ["turn"]},
        ],
    }
    current = SocialCognitionRequest(
        request_id="sc-current", trigger="interpretation", source_refs=["current"],
        source_turn={"turn_id": "current", "original_text": "Hello, turn left."},
        responsibilities=[greeting], context={"core_interpretation": core},
    )
    before = current.model_dump(mode="json")
    prompt = social_cognition_prompt(current, [], num_ctx=8192)
    projected = json.loads(prompt.split("Trusted interaction snapshot:\n", 1)[1])["request"]
    if core_turn == "current":
        assert projected["context"]["core_interpretation"] == core
    else:
        assert "core_interpretation" not in projected["context"]
    assert [item["local_ref"] for item in projected["responsibilities"]] == ["greet"]
    assert current.model_dump(mode="json") == before

    # Read-only sibling meaning must not become SC fulfillment provenance.
    raw = response(text="Hello!", source_goal_ids=[], source_responsibility_refs=["turn"])
    assert not Draft202012Validator(social_cognition_response_schema(current, [])).is_valid(raw)
    with pytest.raises(ValueError):
        validate_social_cognition_output(SocialCognitionOutput.model_validate(raw), current, [])


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


def test_interpretation_prompt_keeps_current_turn_foreground_and_hides_unbound_goal_memory():
    from agent.app.social_cognition import social_cognition_prompt
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal

    current = request(
        trigger="interpretation",
        source_refs=["turn:joke"],
        goal_ids=[],
        source_turn={"turn_id": "turn:joke", "original_text": "Tell me a joke."},
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1", outcome="tell a joke", output_mode="speech",
            continuity_scope="turn", confidence=1.0,
        )],
        context={
            "active_goal_snapshots": [{
                "goal_id": "goal-weather",
                "description": "Determine tomorrow's weather in Chongqing.",
            }],
            "working_goal_memory": [{
                "goal_id": "goal-weather",
                "description": "Determine tomorrow's weather in Chongqing.",
            }],
            "long_term_goal_memory": [{
                "goal_id": "goal-weather",
                "summary": "Tomorrow weather in Chongqing.",
            }],
            "work_decision_pending": False,
            "interaction_context": {
                "events": [], "already_spoken": [], "pending_speech": [],
                "prior_delivered_speech": [{
                    "turn_id": "old-weather-turn",
                    "text": "I said I would check the weather.",
                    "metadata": {"communicative_activity_ids": ["old-act"]},
                }],
            },
        },
    )
    prompt = social_cognition_prompt(current, [], num_ctx=8192)
    assert "tell a joke" in prompt
    assert "I said I would check the weather" in prompt
    assert "goal-weather" not in prompt
    assert "Determine tomorrow's weather in Chongqing" not in prompt
    assert "working_goal_memory" not in prompt
    assert "long_term_goal_memory" not in prompt


def test_interpretation_non_speech_task_cannot_inform_result_before_planner_or_evidence():
    from agent.app.social_cognition import validate_social_cognition_output
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.social_cognition import SocialCognitionOutput

    current = request(
        trigger="interpretation",
        source_refs=["turn:weather"],
        goal_ids=[],
        source_turn={"turn_id": "turn:weather", "original_text": "Will it rain tomorrow?"},
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1", outcome="determine whether it will rain tomorrow",
            output_mode="information", continuity_scope="goal", confidence=1.0,
        )],
        context={"work_decision_pending": True, "interaction_context": {
            "events": [], "already_spoken": [], "pending_speech": [], "prior_delivered_speech": [],
        }},
    )
    wrong = SocialCognitionOutput.model_validate({
        "disposition": "communicate",
        "activities": [{
            "activity_id": "weather-result",
            "text": "According to the latest forecast, it will rain.",
            "function": "inform",
            "truth_stage": "context_grounded",
            "source_responsibility_refs": ["r1"],
        }],
        "reason_summary": "Premature result.",
        "need_outcomes": {},
    })
    with pytest.raises(ValueError, match="task result cannot be communicated"):
        validate_social_cognition_output(wrong, current, [])

    acknowledgement = SocialCognitionOutput.model_validate({
        "disposition": "communicate",
        "activities": [{
            "activity_id": "weather-ack",
            "text": "I'll check that.",
            "function": "acknowledge",
            "truth_stage": "pre_evidence",
            "progress_kind": "check_information",
            "source_responsibility_refs": ["r1"],
        }],
        "reason_summary": "Acknowledge the request without claiming a result.",
        "need_outcomes": {},
    })
    validate_social_cognition_output(acknowledgement, current, [])


def test_interpretation_schema_rejects_non_speech_context_grounded_inform():
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal

    current = request(
        trigger="interpretation",
        source_refs=["turn:weather"],
        goal_ids=[],
        source_turn={"turn_id": "turn:weather", "original_text": "Will it rain tomorrow?"},
        responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1", outcome="determine whether it will rain tomorrow",
            output_mode="information", continuity_scope="goal", confidence=1.0,
        )],
        context={"work_decision_pending": True, "interaction_context": {
            "events": [], "already_spoken": [], "pending_speech": [], "prior_delivered_speech": [],
        }},
    )
    schema = social_cognition_response_schema(current, [])
    wrong = {
        "disposition": "communicate",
        "activities": [{
            "activity_id": "weather-result",
            "text": "According to the latest forecast, it will rain.",
            "function": "inform",
            "truth_stage": "context_grounded",
            "source_responsibility_refs": ["r1"],
            "source_goal_ids": [],
            "evidence_refs": [],
            "addressed_need_ids": [],
            "repair_of_activity_ids": [],
            "auxiliary_activities": [],
        }],
        "reason_summary": "Premature result.",
        "need_outcomes": {},
        "memory_candidates": [],
        "self_memory_candidates": [],
    }
    assert list(Draft202012Validator(schema).iter_errors(wrong))
