from __future__ import annotations

import asyncio

import pytest

from agent.app.cognitive_activation import CognitiveActivationResolver
from shared.chromie_contracts.cognitive_activation import (
    CognitiveActivationContext,
    CognitiveActivationDecision,
)
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal


class Model:
    def __init__(self, output):
        self.output = output
        self.calls = 0
        self.kwargs = None

    async def generate(self, prompt, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return self.output


def planner_request() -> CognitiveActivationContext:
    responsibility = CognitiveResponsibilityProposal(
        local_ref="r1",
        outcome="Check the weather.",
        output_mode="information",
        continuity_scope="goal",
        confidence=1.0,
    )
    return CognitiveActivationContext(
        request_id="activation:evidence-1",
        trigger="execution_outcome",
        allowed_authorities=["planner"],
        goal_ids=["goal-weather"],
        responsibility_refs=["r1"],
        source_refs=["evidence-1"],
        responsibilities=[responsibility],
        state={"existing_work_activities": []},
    )


def test_activation_model_can_request_exact_existing_authority() -> None:
    request = planner_request()
    model = Model({
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh Evidence changes remaining Work reasoning.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the current Goal.",
    })
    result = asyncio.run(CognitiveActivationResolver(model).resolve(request))
    assert [item.authority for item in result.cognitive_requests] == ["planner"]
    assert model.calls == 1
    schema = model.kwargs["response_format"]
    selection = schema["$defs"]["CognitiveActivationSelection"]
    assert selection["properties"]["authority"]["enum"] == ["planner"]
    assert selection["properties"]["goal_ids"]["items"]["enum"] == ["goal-weather"]


def test_activation_model_can_choose_no_further_cognition() -> None:
    result = asyncio.run(CognitiveActivationResolver(Model({
        "cognitive_requests": [],
        "confidence": 0.9,
        "reason_summary": "The trusted state change needs no further cognition.",
    })).resolve(planner_request()))
    assert result.cognitive_requests == []


def test_activation_decision_cannot_widen_scope_or_authority() -> None:
    request = planner_request()
    with pytest.raises(ValueError, match="unavailable authority"):
        CognitiveActivationDecision(
            cognitive_requests=[{
                "authority": "social_cognition",
                "goal_ids": ["goal-weather"],
                "responsibility_refs": ["r1"],
                "source_refs": ["evidence-1"],
            }],
            confidence=1.0,
            reason_summary="bad",
        ).validate_request(request)
    with pytest.raises(ValueError, match="widened Goal scope"):
        CognitiveActivationDecision(
            cognitive_requests=[{
                "authority": "planner",
                "goal_ids": ["goal-other"],
                "responsibility_refs": ["r1"],
                "source_refs": ["evidence-1"],
            }],
            confidence=1.0,
            reason_summary="bad",
        ).validate_request(request)


def test_cognitive_activation_endpoint_is_exposed() -> None:
    from agent.app.main import app

    assert "/cognitive-activation" in {route.path for route in app.routes}
