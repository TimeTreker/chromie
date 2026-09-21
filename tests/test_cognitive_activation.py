from __future__ import annotations

import asyncio

import pytest
from jsonschema import Draft202012Validator

from agent.app.cognitive_activation import CognitiveActivationResolver
from orchestrator.runtime.cognitive_activation import _compact_activation_state
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
    assert selection["required"] == [
        "authority", "goal_ids", "responsibility_refs", "source_refs", "reason_summary",
    ]
    assert selection["properties"]["goal_ids"]["const"] == ["goal-weather"]
    assert selection["properties"]["responsibility_refs"]["const"] == ["r1"]
    assert selection["properties"]["source_refs"]["const"] == ["evidence-1"]


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


def test_activation_prompt_treats_fresh_information_evidence_as_remaining_obligation() -> None:
    request = planner_request().model_copy(update={
        "state": {
            "trusted_state_change": {
                "trusted_terminal_evidence": [{
                    "evidence_id": "evidence-1",
                    "tool_id": "chromie.weather.lookup",
                    "status": "completed",
                    "data": {"temperature_c": 25, "forecast": "x" * 10000},
                }]
            }
        }
    })
    model = Model({
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh information Evidence requires result reasoning.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should establish the remaining answer obligation.",
    })
    asyncio.run(CognitiveActivationResolver(model).resolve(request))
    assert "acquisition completion is not the same" in model.kwargs["system"]
    assert "delivering the requested information" in model.kwargs["system"]


def test_compact_activation_state_drops_large_owner_envelopes_but_retains_lifecycle() -> None:
    compact = _compact_activation_state({
        "goal_association": {
            "resolution_status": "resolved",
            "reason_summary": "x" * 20000,
            "new_goals": [{
                "goal_id": "goal-weather",
                "description": "Check weather",
                "source_responsibility_refs": ["r1"],
                "metadata": {"huge": "x" * 20000},
            }],
        },
        "canonical_plan": {
            "plan_id": "plan-weather", "disposition": "execute",
            "coverage": "complete", "goal_ids": ["goal-weather"],
            "goal_satisfaction": {"status": "partial", "score": 0.5,
                                  "unmet_requirements": ["Deliver the acquired information."]},
            "response_text": "x" * 20000,
            "steps": [{"step_id": "lookup", "capability_id": "chromie.weather.lookup",
                       "source_goal_ids": ["goal-weather"], "step_purpose": "acquire_information",
                       "args": {"huge": "x" * 20000}}],
        },
        "existing_work_activities": [{
            "activity_id": "lookup", "capability_id": "chromie.weather.lookup",
            "status": "completed", "provider_blob": "x" * 20000,
        }],
        "trusted_state_change": {
            "trusted_execution_outcome": {
                "outcome_id": "outcome-1", "aggregate_status": "completed",
                "goal_outcomes": [{"goal_id": "goal-weather", "status": "completed",
                                   "acquisition_step_ids": ["lookup"],
                                   "planned_satisfaction": {"status": "partial", "score": 0.5,
                                                            "unmet_requirements": ["Deliver the acquired information."]},
                                   "evidence_ids": ["evidence-1"], "huge": "x" * 20000}],
            },
            "trusted_terminal_evidence": [{
                "evidence_id": "evidence-1", "tool_id": "chromie.weather.lookup",
                "status": "completed", "data": {"huge": "x" * 20000},
            }],
        },
    })
    import json
    encoded = json.dumps(compact, ensure_ascii=False)
    assert len(encoded) < 5000
    assert "response_text" not in encoded
    assert "provider_blob" not in encoded
    assert '"aggregate_status": "completed"' in encoded
    assert '"evidence_id": "evidence-1"' in encoded
    assert compact["canonical_plan"]["steps"][0]["step_purpose"] == "acquire_information"
    assert compact["canonical_plan"]["goal_satisfaction"]["status"] == "partial"
    outcome = compact["trusted_state_change"]["trusted_execution_outcome"]["goal_outcomes"][0]
    assert outcome["acquisition_step_ids"] == ["lookup"]
    assert outcome["planned_satisfaction"]["unmet_requirements"] == ["Deliver the acquired information."]


def test_activation_decoder_requires_exact_trusted_scope_fields() -> None:
    request = planner_request()
    schema = CognitiveActivationResolver.response_schema(request)
    validator = Draft202012Validator(schema)
    omitted_scope = {
        "cognitive_requests": [{
            "authority": "planner",
            "reason_summary": "Fresh Evidence requires Planner continuation.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the open information Goal.",
    }
    assert not validator.is_valid(omitted_scope)
    exact = {
        "cognitive_requests": [{
            "authority": "planner",
            "goal_ids": ["goal-weather"],
            "responsibility_refs": ["r1"],
            "source_refs": ["evidence-1"],
            "reason_summary": "Fresh Evidence requires Planner continuation.",
        }],
        "confidence": 1.0,
        "reason_summary": "Planner should reconsider the open information Goal.",
    }
    assert validator.is_valid(exact)
