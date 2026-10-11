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
    assert {"soridormi.acquire_and_deliver_resource", "soridormi.walk_forward", "soridormi.look_at_person",
            "soridormi.hug_gesture"} <= ids
    assert not ids & {"soridormi.nod_yes", "soridormi.wave_hand", "soridormi.blink_eyes", "chromie.weather.lookup"}


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
    from tests.test_cognitive_runtime_pr7 import (
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


def test_full_turn_without_reviewed_capability_never_calls_value_judgment():
    client, result = walk_turn(RuntimeError("must not be called"), reviewed=frozenset({"soridormi.hug_gesture"}))
    assert result.status == "applied" and "value_judgment" not in client.calls
    (walk,) = result.interaction_response.capabilities
    assert not walk.requires_confirmation and "value_withheld" not in walk.metadata
