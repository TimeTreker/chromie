from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orchestrator.orchestrator import VoiceAssistant


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
        playback_generation=0,
        get_http_session=get_http_session,
        _outcome_response_is_stale=lambda **_kwargs: False,
    )
    return host, runtime


def test_completed_resource_handover_becomes_optional_social_completion_need() -> None:
    host, runtime = _host()
    result = asyncio.run(VoiceAssistant._optional_completed_resource_social_response(host,
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

    assert result == "social-response"
    assert runtime.request is not None
    assert runtime.request.trigger == "evidence"
    assert runtime.request.evidence_refs == ["evidence-water"]
    assert len(runtime.request.communication_needs) == 1
    need = runtime.request.communication_needs[0]
    assert need.owner == "runtime"
    assert need.kind == "result"
    assert need.delivery_phase == "final"
    assert need.facts == {
        "status": "completed",
        "result_kind": "resource_delivery_handover",
        "optional_completion_update": True,
    }


def test_non_resource_completion_does_not_create_handover_social_need() -> None:
    host, runtime = _host()
    result = asyncio.run(VoiceAssistant._optional_completed_resource_social_response(host,
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
