"""Value Judgment: whether Chromie should act, never how (owner amendment 2026-10-10)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent.app.value_judgment import VALUE_JUDGMENT_SYSTEM_PROMPT, ValueJudgmentResolver
from orchestrator.runtime.capability_runtime import CapabilityRegistry, CapabilityRuntime
from orchestrator.runtime.cognitive_runtime import apply_value_judgment
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.value_judgment import (
    VALUE_REVIEW_RELATIVE_PATH,
    ValueJudgmentModelOutput,
    ValueJudgmentResult,
    load_value_review_capability_ids,
)
from tests.capability_runtime_test_support import submit_and_wait_terminal
from tests.test_capability_runtime import MockCapabilityProvider, _body_definition
from tests.voice_assistant_test_support import bare_voice_assistant

ROOT = Path(__file__).resolve().parents[1]


class Model:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def generate(self, prompt, **kwargs):
        self.calls.append((str(prompt), kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def work_request(text="Take the neighbor's package from their doorstep, and don't tell them.", mind=True):
    context = {"mind": default_mind_profile().model_dump(mode="json")} if mind else {}
    context["situation"] = {"interpretations": [
        {"epistemic_status": "established", "value": "bottle of water, 2 meters in front of Chromie"},
        {"epistemic_status": "proposed", "value": "unconfirmed object"},
    ]}
    return CognitiveWorkRequest(sid="vj", text=text, language="en-US", interpretation_confidence=1.0,
        responsibilities=[CognitiveResponsibilityProposal(local_ref="r1", outcome="bring the neighbor's package",
            output_mode="body_action", confidence=1.0)], context=context)


def judgment(decision, concern="others_property", affected="another_adult"):
    return {"affected": affected, "concern": concern, "decision": decision,
            "reason": "Taking someone else's package in secret is not right."}


def test_resolver_judges_from_the_full_stable_mind_and_turn_facts():
    model = Model(judgment("decline", "deception"))
    result = asyncio.run(ValueJudgmentResolver(model).resolve(work_request()))
    assert result.status == "judged" and result.judgment.decision == "decline"
    assert not result.permits_effects
    prompt, kwargs = model.calls[0]
    assert kwargs["system"] == VALUE_JUDGMENT_SYSTEM_PROMPT
    assert kwargs["prompt_family"] == "value_judgment.primary"
    for principle in ("respect_others_property", "respect_privacy", "act_lawfully_and_honestly"):
        assert principle in prompt
    facts = json.loads(prompt.split("Current request facts JSON:\n", 1)[1].split("\n\n", 1)[0])
    assert facts["person_said"].startswith("Take the neighbor's package")
    assert facts["chromie_perceives"] == ["bottle of water, 2 meters in front of Chromie"]
    assert list(kwargs["response_format"]["properties"]) == ["affected", "concern", "decision", "reason"]


@pytest.mark.parametrize("reply,mind", [
    ({"decision": "proceed"}, True),                       # incomplete verdict
    ({**judgment("maybe")}, True),                         # unknown decision
    (RuntimeError("model down"), True),                    # service failure
    (judgment("proceed", "none", "nobody_else"), False),   # no owner-approved Stable Mind
])
def test_resolver_fails_closed(reply, mind):
    result = asyncio.run(ValueJudgmentResolver(Model(reply)).resolve(work_request(mind=mind)))
    assert result.status == "failed" and result.judgment is None
    assert not result.permits_effects


def plan_with(*capability_ids):
    return CanonicalPlan(plan_id="vj-plan", planner_tier="fast", disposition="execute", coverage="complete",
        confidence=1.0, goal_ids=["g"], goal_summary="Do the requested Work.",
        steps=[{"step_id": f"s{index}", "capability_id": cid, "args": {}, "timing": "sequential",
                "source_goal_ids": ["g"]} for index, cid in enumerate(capability_ids)],
        goal_outcomes=[{"goal_id": "g", "disposition": "execute", "coverage": "complete",
                        "step_ids": [f"s{index}" for index in range(len(capability_ids))]}])


@pytest.mark.parametrize("result,expected", [
    (ValueJudgmentResult(status="judged", judgment=ValueJudgmentModelOutput(**judgment("proceed", "none", "nobody_else"))), {}),
    (ValueJudgmentResult(status="judged", judgment=ValueJudgmentModelOutput(**judgment("ask", "others_property", "owner_unknown"))),
     {"value_confirmation_required": True}),
    (ValueJudgmentResult(status="judged", judgment=ValueJudgmentModelOutput(**judgment("decline"))), {"value_withheld": True}),
    (ValueJudgmentResult(status="failed", failure_class="value_judgment_unavailable"), {"value_withheld": True}),
])
def test_verdict_permits_questions_or_withholds_only_reviewed_effects(result, expected):
    plan = apply_value_judgment(plan_with("soridormi.acquire_and_deliver_resource", "soridormi.nod_yes"),
                                {"soridormi.acquire_and_deliver_resource"}, result)
    reviewed, gesture = plan.steps
    assert {key: reviewed.metadata[key] for key in ("value_confirmation_required", "value_withheld")
            if key in reviewed.metadata} == expected
    assert reviewed.metadata["value_judgment"]["decision"] == (result.judgment.decision if result.judgment else "decline")
    assert "value_judgment" not in gesture.metadata
    assert plan.metadata["value_judgment"]["reviewed_capability_ids"] == ["soridormi.acquire_and_deliver_resource"]
    assert [step.capability_id for step in plan.steps] == ["soridormi.acquire_and_deliver_resource", "soridormi.nod_yes"]


def test_owner_review_list_covers_objects_walking_and_people_not_gestures():
    ids = load_value_review_capability_ids(ROOT / VALUE_REVIEW_RELATIVE_PATH)
    assert {"soridormi.acquire_and_deliver_resource", "soridormi.walk_forward", "soridormi.hug_gesture"} <= ids
    # Gaze is an expressive gesture, which the Charter keeps off the review list.
    assert not ids & {"soridormi.nod_yes", "soridormi.wave_hand", "soridormi.blink_eyes", "soridormi.look_at_person",
                      "chromie.weather.lookup"}


def test_withheld_effect_is_refused_before_any_provider_starts():
    async def run():
        registry = CapabilityRegistry()
        registry.register(_body_definition())
        provider = MockCapabilityProvider("mock.body")
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(provider)
        verdict = {"decision": "decline", "reason": "Taking someone else's package in secret is not right."}
        response = InteractionResponse(interaction_id="vj-refuse", capabilities=[{
            "request_id": "withheld", "capability_id": "soridormi.nod_yes",
            "metadata": {"value_withheld": True, "value_judgment": verdict}}])
        terminal = await submit_and_wait_terminal(runtime, response)
        return provider, terminal
    provider, terminal = asyncio.run(run())
    assert provider.calls == []
    (result,) = terminal.results
    assert result.status == "refused" and result.reason_code == "value_judgment_declined"
    assert result.message == "Taking someone else's package in secret is not right."
    assert result.output["value_judgment"]["decision"] == "decline"


def walk_turn(verdict, reviewed=frozenset({"soridormi.walk_forward"})):
    """One full apply-mode turn whose Plan walks; the scripted Agent returns the given verdict."""
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator)
    from tests.cognitive_runtime_test_support import (
        FakeRuntime, ScriptedClient, admitted_core, body_goal_association, walk_definition)

    class Client(ScriptedClient):
        value_requests: list = []

        async def resolve_value_judgment(self, session, *, request, **kwargs):
            self.calls.append("value_judgment")
            self.value_requests.append(request)
            if isinstance(verdict, Exception):
                raise verdict
            return verdict

    walk = CanonicalPlan(plan_id="plan-walk", planner_tier="fast", disposition="execute", coverage="complete",
        confidence=0.95, goal_ids=["goal-1"], goal_summary="walk forward", response_text="OK, walking forward.",
        steps=[{"step_id": "walk", "capability_id": "soridormi.walk_forward", "args": {"duration_s": 3.0},
                "timing": "sequential", "source_goal_ids": ["goal-1"]}],
        goal_satisfaction={"score": 1.0, "status": "exact", "satisfied_goal_ids": ["goal-1"]})
    client = Client(association=body_goal_association(), fast_plans=[walk])
    client.value_requests = []
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=client, adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([walk_definition()])),
        policy=CognitiveRuntimePolicy(mode="apply", value_review_capability_ids=reviewed))
    core, envelope = admitted_core("Walk forward.", sid="sid-vj", language="en-US", responsibilities=None)
    result = asyncio.run(coordinator.resolve(object(), text="Walk forward.", sid="sid-vj", core_interpretation=core,
        context={"history": [], "active_goal_snapshots": [], "mind": default_mind_profile().prompt_context()},
        history=[], language="en-US", turn_envelope=envelope))
    return client, result


def judged(decision, concern="none", affected="nobody_else"):
    return ValueJudgmentResult(status="judged", judgment=ValueJudgmentModelOutput(
        affected=affected, concern=concern, decision=decision, reason="Walking here could bump into the child."))


@pytest.mark.parametrize("verdict,confirm,withheld", [
    (judged("proceed"), False, False),
    (judged("ask", "harm_risk", "child"), True, False),
    (judged("decline", "harm_risk", "child"), False, True),
    (RuntimeError("agent down"), False, True),
])
def test_full_turn_value_verdict_gates_only_the_reviewed_effect(verdict, confirm, withheld):
    client, result = walk_turn(verdict)
    assert result.status == "applied"
    assert client.calls.count("value_judgment") == 1
    (request,) = client.value_requests
    assert request.context["mind"]["owner_approved"] is True
    (walk,) = result.interaction_response.capabilities
    assert walk.capability_id == "soridormi.walk_forward"
    assert walk.requires_confirmation is confirm
    assert bool(walk.metadata.get("value_withheld")) is withheld
    needs = result.terminal_plan.communication_needs
    confirmation = [need for need in needs if need.kind == "confirmation"]
    assert bool(confirmation) is confirm
    if confirm:
        assert confirmation[0].facts["value_question"]["concern"] == "harm_risk"
    declined = [need for need in needs if need.owner == "runtime" and need.kind == "result"]
    assert bool(declined) is withheld
    if withheld:
        assert declined[0].facts["withheld_capability_ids"] == ["soridormi.walk_forward"]
        assert declined[0].facts["value_declined"]["decision"] == "decline"
    # Live 2026-10-11 (h_ask_phone_zh): the annotated Plan must archive as the Planner's artifact.
    from orchestrator.runtime.cognitive_runtime import CognitiveEvidenceRecorder
    packets = CognitiveEvidenceRecorder.semantic_artifact_packets(result, sid="sid-vj")
    (plan_packet,) = [packet for packet in packets if packet.ref.artifact_kind == "planner_plan"]
    assert "value_judgment" not in plan_packet.payload["metadata"]
    assert all(need["owner"] != "runtime" for need in plan_packet.payload["communication_needs"])


def test_full_turn_without_reviewed_capability_never_calls_value_judgment():
    client, result = walk_turn(RuntimeError("must not be called"), reviewed=frozenset({"soridormi.hug_gesture"}))
    assert result.status == "applied" and "value_judgment" not in client.calls
    (walk,) = result.interaction_response.capabilities
    assert not walk.requires_confirmation and "value_withheld" not in walk.metadata


def test_withheld_effect_never_joins_a_provider_local_body_group():
    # Live 2026-10-11 (h_no_coworker_lunch_en): a declined delivery ran inside the compiled
    # Soridormi body group, which bypassed the single-request pre-start refusal.
    from tests.test_execution_lanes import _GroupedBodyProvider, _definition

    async def run():
        registry = CapabilityRegistry()
        for capability_id, group in (("soridormi.deliver", "hands"), ("soridormi.blink", "eyes"),
                                     ("soridormi.attend", "head")):
            registry.register(_definition(capability_id, group=group, resources=[group]))
        provider = _GroupedBodyProvider()
        runtime = CapabilityRuntime(registry, max_concurrency=3)
        runtime.register_provider(provider)
        verdict = {"decision": "decline", "reason": "That lunch belongs to someone else."}
        response = InteractionResponse(interaction_id="vj-group", capabilities=[
            {"request_id": "deliver", "capability_id": "soridormi.deliver", "timing": "parallel",
             "metadata": {"value_withheld": True, "value_judgment": verdict}},
            {"request_id": "blink", "capability_id": "soridormi.blink", "timing": "parallel"},
            {"request_id": "attend", "capability_id": "soridormi.attend", "timing": "parallel"},
        ])
        return provider, await submit_and_wait_terminal(runtime, response)

    provider, terminal = asyncio.run(run())
    assert provider.group_calls == [["blink", "attend"]]
    assert "deliver" not in [request.request_id for request in provider.calls]
    by_id = {result.request_id: result for result in terminal.results}
    assert by_id["deliver"].status == "refused" and by_id["deliver"].reason_code == "value_judgment_declined"
    assert by_id["blink"].status == by_id["attend"].status == "completed"


def speech_turn(verdict, *, value_review=True):
    """Turn-local speech UMI marked value_review (owner choice B, 2026-10-12)."""
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator)
    from tests.cognitive_runtime_test_support import FakeRuntime, ScriptedClient, admitted_core, body_goal_association

    class Client(ScriptedClient):
        async def resolve_value_judgment(self, session, *, request, **kwargs):
            self.calls.append("value_judgment")
            self.value_requests.append(request)
            if isinstance(verdict, Exception):
                raise verdict
            return verdict

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            # A compliant SC: says every need except an answer Value Judgment withheld.
            withheld = {need.need_id for need in request.communication_needs if need.facts.get("value_withheld")}
            resolution = await super().resolve_social_cognition(session, request=request.model_copy(update={
                "communication_needs": [need for need in request.communication_needs if need.need_id not in withheld]}),
                **kwargs)
            return resolution.model_copy(update={"request_id": request.request_id,
                "snapshot_digest": request.snapshot_digest(),
                "need_outcomes": {**resolution.need_outcomes, **{key: "pending" for key in withheld}}})

    text = "When the teacher comes, tell her I was doing homework the whole time."
    answer = CanonicalPlan(plan_id="plan-say", planner_tier="fast", disposition="respond", coverage="complete",
        confidence=0.95, goal_ids=["goal-1"], goal_summary="answer the request", steps=[],
        goal_outcomes=[{"goal_id": "goal-1", "disposition": "respond", "coverage": "complete"}],
        communication_needs=[{"need_id": "need-answer", "owner": "planner", "kind": "answer",
                              "source_goal_ids": ["goal-1"], "reference_id": "plan-say",
                              "facts": {"goal_id": "goal-1", "disposition": "respond"}}],
        goal_satisfaction={"score": 1.0, "status": "exact", "satisfied_goal_ids": ["goal-1"]})
    client = Client(association=body_goal_association(), fast_plans=[answer])
    client.value_requests = []
    coordinator = GoalDrivenRuntimeCoordinator(
        agent_client=client, adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([])),
        policy=CognitiveRuntimePolicy(mode="apply"))
    core, envelope = admitted_core(text, sid="sid-say", language="en-US", responsibilities=[{
        "local_ref": "r1", "outcome": text, "output_mode": "speech", "continuity_scope": "turn",
        "value_review": value_review, "confidence": 1.0}])
    result = asyncio.run(coordinator.resolve(object(), text=text, sid="sid-say", core_interpretation=core,
        context={"history": [], "active_goal_snapshots": [], "mind": default_mind_profile().prompt_context()},
        history=[], language="en-US", turn_envelope=envelope))
    return client, result


def test_value_review_speech_requests_the_planner_before_any_answer():
    from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator

    flagged = CognitiveWorkRequest(sid="vj", text="Tell my teacher I was ill.", language="en-US",
        interpretation_confidence=1.0, responsibilities=[CognitiveResponsibilityProposal(
            local_ref="r1", outcome="tell the teacher I was ill", output_mode="speech",
            continuity_scope="turn", value_review=True, confidence=1.0)])
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(flagged, "planner") == ["r1"]
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(flagged, "goal_association") == ["r1"]
    plain = flagged.model_copy(update={"responsibilities": [
        flagged.responsibilities[0].model_copy(update={"value_review": False})]})
    assert GoalDrivenRuntimeCoordinator._cognitive_request_responsibility_refs(plain, "planner") == []
    with pytest.raises(ValueError, match="speech Responsibility only"):
        CognitiveResponsibilityProposal(local_ref="r1", outcome="limp", output_mode="body_action",
                                        body_effect_family="task_physical_effect", value_review=True)


@pytest.mark.parametrize("verdict,withheld,extra_kind", [
    (judged("proceed"), False, None),
    (judged("ask", "deception", "another_adult"), True, "input"),
    (judged("decline", "deception", "another_adult"), True, "result"),
    (RuntimeError("agent down"), True, "result"),
])
def test_value_review_speech_is_judged_before_social_cognition_says_it(verdict, withheld, extra_kind):
    client, result = speech_turn(verdict)
    assert result.status == "applied", result.fallback_reason
    assert client.calls.count("value_judgment") == 1
    plan = result.terminal_plan
    (answer,) = [need for need in plan.communication_needs if need.kind == "answer"]
    assert bool(answer.facts.get("value_withheld")) is withheld
    runtime_needs = [need for need in plan.communication_needs if need.owner == "runtime"]
    assert [need.kind for need in runtime_needs] == ([extra_kind] if extra_kind else [])
    if extra_kind:
        facts = runtime_needs[0].facts
        assert facts["withheld_answer_need_ids"] == [answer.need_id]
        assert ("value_question" if extra_kind == "input" else "value_declined") in facts
        assert plan.metadata["value_judgment"]["withheld_answer_goal_ids"] == ["goal-1"]
    from orchestrator.runtime.cognitive_runtime import CognitiveEvidenceRecorder
    packets = CognitiveEvidenceRecorder.semantic_artifact_packets(result, sid="sid-say")
    (plan_packet,) = [packet for packet in packets if packet.ref.artifact_kind == "planner_plan"]
    assert all("value_withheld" not in need["facts"] and "value_judgment" not in need["facts"]
               for need in plan_packet.payload["communication_needs"])


def test_unmarked_speech_never_calls_value_judgment():
    client, result = speech_turn(RuntimeError("must not be called"), value_review=False)
    assert "value_judgment" not in client.calls


@pytest.mark.parametrize("decision,expected", [("decline", "value_declined"), ("ask", "clarify"), ("proceed", "respond")])
def test_withheld_answer_sets_its_goal_outcome(decision, expected):
    from orchestrator.runtime.conversation_state import ConversationStateManager

    plan = {"goal_outcomes": [{"goal_id": "goal-1", "disposition": "respond"}, {"goal_id": "goal-2", "disposition": "respond"}],
            "metadata": {"value_judgment": {"decision": decision, "withheld_answer_goal_ids": ["goal-1"]}}}
    outcomes = ConversationStateManager._canonical_goal_outcomes({"canonical_plan": plan})
    assert outcomes["goal-1"]["disposition"] == expected
    assert outcomes["goal-2"]["disposition"] == "respond"


def test_value_declined_goal_ends_like_a_limitation_without_a_semantic_version_bump():
    """Live 2026-10-12 (vs_teacher_homework_zh): marking the declined Goal refused changed its
    semantic version before dispatch, so the decline was dropped as a stale submission."""
    from orchestrator.runtime.conversation_state import ConversationStateManager

    manager = ConversationStateManager(base_conversation_id="vj-goal")
    manager._task_contexts.append({"task_id": "goal-1", "status": "planning", "goal_version": 1})
    before = manager._semantic_goal_from_context(manager._task_contexts[-1]).model_dump(mode="json")
    manager._record_nonexecuting_goal_outcomes({"goal-1": {"goal_id": "goal-1", "disposition": "value_declined"}})
    context = manager._task_contexts[-1]
    assert (context["status"], context["commitment_state"], context["plan_status"]) == ("refused", "failed", "value_declined")
    assert manager._semantic_goal_from_context(context).model_dump(mode="json") == before


def reentry_walk(verdict, *, judged_plan=None, planner_metadata=None, reviewed=frozenset({"soridormi.walk_forward"})):
    """Evidence re-entry whose new Plan adds a walk ("if it's sunny, walk to the window")."""
    from types import SimpleNamespace

    from orchestrator.orchestrator import VoiceAssistant
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator)
    from tests.cognitive_runtime_test_support import FakeRuntime, walk_definition
    from tests.cognitive_work_test_support import PlannerActivationFixture, social_fixture_resolution

    walk = CanonicalPlan(plan_id="plan-reentry-walk", planner_tier="fast", disposition="execute", coverage="complete",
        confidence=0.95, goal_ids=["goal-1"], goal_summary="walk to the window",
        steps=[{"step_id": "walk", "capability_id": "soridormi.walk_forward", "args": {"duration_s": 3.0},
                "timing": "sequential", "source_goal_ids": ["goal-1"], "metadata": dict(planner_metadata or {})}],
        goal_outcomes=[{"goal_id": "goal-1", "disposition": "execute", "coverage": "complete", "step_ids": ["walk"]}],
        goal_satisfaction={"score": 1.0, "status": "exact", "satisfied_goal_ids": ["goal-1"]})
    source = judged_plan or CanonicalPlan(plan_id="plan-weather", planner_tier="fast", disposition="execute",
        coverage="complete", confidence=0.95, goal_ids=["goal-1"], goal_summary="check the weather",
        steps=[{"step_id": "weather", "capability_id": "chromie.weather.lookup", "args": {},
                "timing": "sequential", "source_goal_ids": ["goal-1"]}],
        goal_outcomes=[{"goal_id": "goal-1", "disposition": "execute", "coverage": "complete", "step_ids": ["weather"]}])

    class Client(PlannerActivationFixture):
        def __init__(self):
            self.calls = []

        async def resolve_fast_plan(self, _session, *, request, timeout_ms):
            return walk

        async def resolve_value_judgment(self, session, *, request, **kwargs):
            self.calls.append("value_judgment")
            if isinstance(verdict, Exception):
                raise verdict
            return verdict

        async def resolve_social_cognition(self, session, *, request, **kwargs):
            return social_fixture_resolution(request, "OK.")

    class Adapter(CanonicalPlanRuntimeAdapter):
        async def build_social_cognition_response(self, **_kwargs):
            return InteractionResponse(interaction_id="reentry-walk", status="ok")

    assistant = bare_voice_assistant()
    assistant.agent_client = Client()
    assistant.cognitive_runtime_policy = SimpleNamespace(fast_planner_timeout_ms=3000, deliberative_timeout_ms=6000)
    assistant.cognitive_runtime = GoalDrivenRuntimeCoordinator(
        agent_client=assistant.agent_client, adapter=Adapter(FakeRuntime([walk_definition()])),
        policy=CognitiveRuntimePolicy(mode="apply", value_review_capability_ids=reviewed))
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.build_context = lambda _sid: {"history": [], "mind": default_mind_profile().prompt_context()}
    assistant._cognitive_core_authority_context = lambda context, **_kwargs: context

    async def get_session():
        return object()

    assistant.get_http_session = get_session
    response = asyncio.run(assistant._planner_state_reentry_response(
        source_response=None, canonical_plan=source, user_request="If it's sunny, walk to the window.",
        language="en-US", goal_ids=["goal-1"], evidence_goal_ids=["goal-1"], evidence_refs=["evidence-sunny"],
        session_id=None, phase="capability_result_reentry",
        context_updates={"trusted_terminal_evidence": [{"evidence_id": "evidence-sunny", "status": "completed"}]},
        fast_workflow_stage="fast_planner_evidence_reentry", response_source="fast_planner_evidence_reentry",
        responsibilities_override=[CognitiveResponsibilityProposal(local_ref="r1",
            outcome="walk to the window if it is sunny", output_mode="stateful_effect", confidence=1.0)]))
    assert response is not None
    return assistant.agent_client, CanonicalPlan.model_validate(response.metadata["planner_reentry_plan"])


@pytest.mark.parametrize("verdict,confirm,withheld", [
    (judged("proceed"), False, False),
    (judged("ask", "harm_risk", "child"), True, False),
    (judged("decline", "harm_risk", "child"), False, True),
    (RuntimeError("agent down"), False, True),
])
def test_reentry_plan_adding_a_reviewed_capability_is_judged_before_it_starts(verdict, confirm, withheld):
    client, plan = reentry_walk(verdict)
    assert client.calls == ["value_judgment"]
    (walk,) = plan.steps
    assert bool(walk.metadata.get("value_confirmation_required")) is confirm
    assert bool(walk.metadata.get("value_withheld")) is withheld
    assert plan.metadata["value_judgment"]["reviewed_capability_ids"] == ["soridormi.walk_forward"]
    kinds = [need.kind for need in plan.communication_needs if need.owner == "runtime"]
    assert kinds == (["confirmation"] if confirm else ["result"] if withheld else [])
    if confirm:
        (need,) = [need for need in plan.communication_needs if need.kind == "confirmation"]
        assert need.facts["value_question"]["concern"] == "harm_risk"


def test_reentry_reuses_a_verdict_given_earlier_in_the_same_turn():
    earlier = apply_value_judgment(plan_with("soridormi.walk_forward"), {"soridormi.walk_forward"},
                                   judged("decline", "harm_risk", "child"))
    client, plan = reentry_walk(RuntimeError("must not be called"), judged_plan=earlier)
    assert client.calls == []
    (walk,) = plan.steps
    assert walk.metadata["value_withheld"] is True
    assert walk.metadata["value_judgment"]["decision"] == "decline"


def test_reentry_without_a_reviewed_capability_never_calls_value_judgment():
    client, plan = reentry_walk(RuntimeError("must not be called"), reviewed=frozenset({"soridormi.hug_gesture"}))
    assert client.calls == []
    assert "value_judgment" not in plan.steps[0].metadata


def test_planner_authored_verdict_on_a_reentry_plan_is_not_a_verdict():
    client, plan = reentry_walk(judged("decline", "harm_risk", "child"),
                                planner_metadata={"value_judgment": {"decision": "proceed"}})
    assert client.calls == ["value_judgment"]
    assert plan.steps[0].metadata["value_withheld"] is True


def test_turn_record_reuses_a_verdict_and_judges_only_new_reviewed_capabilities():
    from orchestrator.runtime.cognitive_runtime import (
        CanonicalPlanRuntimeAdapter, CognitiveRuntimePolicy, GoalDrivenRuntimeCoordinator)
    from tests.cognitive_runtime_test_support import FakeRuntime

    verdicts = [judged("proceed"), judged("decline", "consent", "another_adult")]
    requests = []

    class Client:
        async def resolve_value_judgment(self, session, *, request, **kwargs):
            requests.append(request)
            return verdicts[len(requests) - 1]

    coordinator = GoalDrivenRuntimeCoordinator(agent_client=Client(), adapter=CanonicalPlanRuntimeAdapter(FakeRuntime([])),
        policy=CognitiveRuntimePolicy(mode="apply", value_review_capability_ids=frozenset(
            {"soridormi.walk_forward", "soridormi.hug_gesture"})))

    def gate(plan):
        return asyncio.run(coordinator.apply_value_judgment_gate(object(), sid="sid", text="t", plan=plan,
            work_request=work_request(), goal_ids_by_responsibility={}, turn_id="turn-1"))

    first = gate(plan_with("soridormi.walk_forward"))
    assert len(requests) == 1 and first.steps[0].metadata["value_judgment"]["decision"] == "proceed"
    again = gate(plan_with("soridormi.walk_forward"))
    assert len(requests) == 1 and again.steps[0].metadata["value_judgment"]["decision"] == "proceed"
    mixed = gate(plan_with("soridormi.walk_forward", "soridormi.hug_gesture"))
    assert len(requests) == 2
    walk, hug = mixed.steps
    assert walk.metadata["value_judgment"]["decision"] == "proceed" and "value_withheld" not in walk.metadata
    assert hug.metadata["value_withheld"] is True
    assert mixed.metadata["value_judgment"]["decision"] == "decline"
    assert mixed.metadata["value_judgment"]["reviewed_capability_ids"] == [
        "soridormi.hug_gesture", "soridormi.walk_forward"]
    (declined,) = [need for need in mixed.communication_needs if need.owner == "runtime"]
    assert declined.facts["withheld_capability_ids"] == ["soridormi.hug_gesture"]
