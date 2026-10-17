from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime import planner_reentry_host


class _Runtime:
    interaction_ledger = None

    def __init__(self) -> None:
        self.request = None

    async def resolve_social_interaction(self, _session, *, request, **_kwargs):
        self.request = request
        return object(), "social-response"


def _host():
    runtime = _Runtime()

    async def get_http_session():
        return object()

    host = SimpleNamespace(
        cognitive_runtime=runtime,
        playback_delivery=SimpleNamespace(playback_generation=0),
        get_http_session=get_http_session,
        _outcome_response_is_stale=lambda **_kwargs: False,
    )
    return host, runtime


def _handover_request(host):
    return asyncio.run(planner_reentry_host.optional_completed_resource_social_response(host,
        source_response=SimpleNamespace(metadata={
            "user_turn_envelope": {
                "turn_id": "turn-water",
                "normalized_input": {"text": "Bring me some water."},
            }
        }),
        bundle=SimpleNamespace(aggregate_status="completed"),
        plan=SimpleNamespace(
            plan_id="plan-water",
            steps=[SimpleNamespace(step_id="deliver-water")],
        ),
        session_id="sid-water",
        language="en-US",
        user_request="Bring me some water.",
        evidence_refs=["evidence-water"],
        goal_ids=["goal-water"],
        selected_execution_evidence=[SimpleNamespace(
            status="completed",
            capability_id="soridormi.acquire_and_deliver_resource",
        )],
    ))


def test_completed_resource_handover_becomes_optional_social_completion_need() -> None:
    host, runtime = _host()
    result = _handover_request(host)

    assert result == "social-response"
    assert runtime.request is not None
    assert runtime.request.trigger == "evidence"
    assert runtime.request.evidence_refs == ["evidence-water"]
    assert len(runtime.request.communication_needs) == 1
    need = runtime.request.communication_needs[0]
    assert need.owner == "runtime"
    assert need.kind == "result"
    assert need.delivery_phase == "immediate"
    assert need.after_step_ids == ["deliver-water"]
    assert need.facts == {
        "status": "completed",
        "result_kind": "resource_delivery_handover",
        "optional_completion_update": True,
    }


def test_non_resource_completion_does_not_create_handover_social_need() -> None:
    host, runtime = _host()
    result = asyncio.run(planner_reentry_host.optional_completed_resource_social_response(host,
        source_response=SimpleNamespace(metadata={}),
        bundle=SimpleNamespace(aggregate_status="completed"),
        plan=SimpleNamespace(plan_id="plan-other", steps=[]),
        session_id="sid-water",
        language="en-US",
        user_request="Blink.",
        evidence_refs=["evidence-other"],
        goal_ids=["goal-other"],
        selected_execution_evidence=[SimpleNamespace(
            status="completed",
            capability_id="soridormi.blink_eyes",
        )],
    ))

    assert result is None
    assert runtime.request is None


def test_handover_words_bound_to_the_need_reach_the_person() -> None:
    """Live 2026-10-15: SC's "给你。" kept the need's phase and the transport rejected it."""
    from orchestrator.runtime.response_plan import build_social_interaction_response
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution

    host, runtime = _host()
    _handover_request(host)
    request = runtime.request
    need = request.communication_needs[0]
    result = SocialCognitionResolution(
        request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
        disposition="communicate", model_call_count=1,
        reason_summary="A brief close after the completed handover.",
        need_outcomes={need.need_id: "covered"},
        activities=[{"activity_id": "handover", "text": "Here you are.", "function": "respond",
                     "truth_stage": "context_grounded", "delivery_phase": need.delivery_phase,
                     "source_goal_ids": request.goal_ids, "evidence_refs": request.evidence_refs,
                     "addressed_need_ids": [need.need_id]}],
    )

    response = build_social_interaction_response(
        request, result, session_id="sid-water", interaction_context=None,
    )

    assert [item.text for item in response.speech] == ["Here you are."]
