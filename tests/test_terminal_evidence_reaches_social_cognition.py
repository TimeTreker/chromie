"""Terminal Evidence reaches Social Cognition directly (owner decision 3).

SC is the interface between the user and Chromie. A result the person asked for must not
be dropped because Activation or the Planner chose no next Work, and the Planner
path must not cause a second SC communication for the same Evidence.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.response_plan import build_social_interaction_response
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from shared.chromie_contracts.tool_result import canonical_value_sha256
from tests.voice_assistant_test_support import bare_voice_assistant

GOAL = "goal-weather"
WEATHER = {"condition": "light rain", "temperature_c": 14}


def _plan(capability_id: str = "chromie.weather.lookup") -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="weather-plan", planner_tier="fast", disposition="execute",
        coverage="complete", confidence=0.95, goal_ids=[GOAL],
        steps=[CanonicalPlanStep(step_id="lookup", capability_id=capability_id,
                                 args={}, source_goal_ids=[GOAL])],
    )


def _bundle(plan: CanonicalPlan, *, status: str = "completed") -> ExecutionOutcomeBundle:
    data = WEATHER if status == "completed" else {}
    observation = ModelObservation(
        status="available", data=data, schema_validated=True,
        output_sha256=canonical_value_sha256(data), output_size_bytes=len(str(data)),
    ) if status == "completed" else None
    step = plan.steps[0]
    return ExecutionOutcomeBundle(
        outcome_id="outcome-weather", turn_id="turn-weather", interaction_id="weather",
        canonical_plan_id=plan.plan_id, canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
        canonical_goal_ids=[GOAL], aggregate_status=status,
        evidence=[ExecutionEvidence(
            evidence_id="weather-result", request_id="request-weather", step_id=step.step_id,
            capability_id=step.capability_id, source_goal_ids=[GOAL], status=status,
            reported_status=status, observation=observation,
            reason_code=None if status == "completed" else "provider_failed",
        )],
        goal_outcomes=[GoalExecutionOutcome(
            goal_id=GOAL, status=status, step_ids=[step.step_id], evidence_ids=["weather-result"],
            completed_step_ids=[step.step_id] if status == "completed" else [],
            unresolved_step_ids=[] if status == "completed" else [step.step_id],
            reason_codes=[] if status == "completed" else ["provider_failed"],
        )],
    )


def _source(output_mode: str = "information", text: str = "What's the weather?") -> InteractionResponse:
    return InteractionResponse(interaction_id="weather", status="ok", metadata={
        "language": "en-US",
        "user_turn_envelope": {"turn_id": "turn-weather",
                               "normalized_input": {"text": text, "language": "en-US"}},
        "user_meaning_interpretation": {"responsibilities": [{
            "local_ref": "r-weather", "outcome": text, "output_mode": output_mode,
            "confidence": 1.0}]},
        "goal_association": {"associations": [], "new_goals": [{
            "goal_id": GOAL, "source_responsibility_refs": ["r-weather"]}]},
    })


class _Runtime:
    interaction_ledger = None

    def __init__(self) -> None:
        self.requests: list = []

    async def resolve_social_interaction(self, _session, *, request, **_kwargs):
        self.requests.append(request)
        return object(), InteractionResponse(interaction_id="sc-result", status="ok")


def _assistant(planner_result):
    assistant = bare_voice_assistant()
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.cognitive_runtime = _Runtime()
    assistant.playback_delivery = SimpleNamespace(playback_generation=0)
    assistant.get_http_session = AsyncMock(return_value=object())
    assistant._outcome_response_is_stale = lambda **_kwargs: False
    assistant._planner_state_reentry_response = AsyncMock(return_value=planner_result)
    return assistant


def _run(assistant, plan, bundle, source):
    return asyncio.run(assistant._plan_evidence_bound_capability_result_response(
        source_response=source, bundle=bundle, plan=plan, session_id="session"))


def test_requested_answer_reaches_sc_when_planner_activation_chooses_none() -> None:
    plan = _plan()
    assistant = _assistant(None)

    response = _run(assistant, plan, _bundle(plan), _source())

    assert response is not None and response.interaction_id == "sc-result"
    assistant._planner_state_reentry_response.assert_awaited_once()
    [request] = assistant.cognitive_runtime.requests
    assert request.trigger == "evidence"
    assert request.goal_ids == [GOAL]
    assert request.evidence_refs == ["weather-result"]
    assert request.source_turn["turn_id"] == "turn-weather"
    assert [item.local_ref for item in request.responsibilities] == ["r-weather"]
    [need] = request.communication_needs
    assert (need.owner, need.kind) == ("runtime", "result")
    assert need.source_goal_ids == [GOAL]
    assert need.source_responsibility_refs == ["r-weather"]
    assert need.facts["status"] == "completed"
    assert need.facts["required_result_update"] is True
    assert need.after_step_ids == ["lookup"]
    [evidence] = request.context["trusted_terminal_evidence"]
    assert evidence["evidence_id"] == "weather-result"
    assert evidence["data"] == WEATHER


def test_planner_communication_is_the_only_sc_communication() -> None:
    plan = _plan()
    planner_response = InteractionResponse(interaction_id="planner-result", status="ok")
    assistant = _assistant(planner_response)

    response = _run(assistant, plan, _bundle(plan), _source())

    assert response is planner_response
    assert assistant.cognitive_runtime.requests == []


def test_terminal_evidence_without_requested_result_keeps_planner_ownership() -> None:
    plan = _plan("soridormi.blink_eyes")
    assistant = _assistant(None)

    response = _run(assistant, plan, _bundle(plan), _source("body_action", "Blink."))

    assert response is None
    assert assistant.cognitive_runtime.requests == []


def test_sc_owns_how_the_requested_result_is_said() -> None:
    plan = _plan()
    assistant = _assistant(None)
    _run(assistant, plan, _bundle(plan), _source())
    [request] = assistant.cognitive_runtime.requests
    need = request.communication_needs[0]
    result = SocialCognitionResolution(
        request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
        disposition="communicate", model_call_count=1,
        reason_summary="The person asked for the weather.",
        need_outcomes={need.need_id: "covered"},
        activities=[{"activity_id": "weather-answer", "text": "It's 14 degrees with light rain.",
                     "function": "respond", "truth_stage": "post_evidence",
                     "delivery_phase": need.delivery_phase, "source_goal_ids": [GOAL],
                     "source_responsibility_refs": ["r-weather"],
                     "evidence_refs": ["weather-result"], "addressed_need_ids": [need.need_id]}],
    )
    result.validate_request(request)

    response = build_social_interaction_response(
        request, result, session_id="session", interaction_context=None,
    )

    assert [item.text for item in response.speech] == ["It's 14 degrees with light rain."]


def test_failed_requested_result_cannot_be_silently_dropped_by_sc() -> None:
    plan = _plan()
    assistant = _assistant(None)
    _run(assistant, plan, _bundle(plan, status="failed"), _source())
    [request] = assistant.cognitive_runtime.requests
    need = request.communication_needs[0]
    assert need.facts["status"] == "failed"
    silence = SocialCognitionResolution(
        request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
        disposition="silence", model_call_count=1, reason_summary="Nothing to add.",
        need_outcomes={need.need_id: "pending"},
    )

    with pytest.raises(ValueError, match="terminal Work failure"):
        silence.validate_request(request)
