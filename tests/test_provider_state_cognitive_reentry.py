from __future__ import annotations

from orchestrator.runtime.planner_reentry import (
    meaningful_provider_state,
    provider_state_relevance,
)
from shared.chromie_contracts.interaction import InteractionResponse


def _response() -> InteractionResponse:
    return InteractionResponse(
        interaction_id="interaction-provider-state",
        metadata={
            "canonical_plan_id": "plan-current",
            "canonical_plan_fingerprint": "a" * 64,
        },
    )


def _binding(**updates):
    value = {
        "goal_id": "goal-1",
        "found": True,
        "responsibility_status": "open",
        "canonical_plan_id": "plan-current",
        "canonical_plan_fingerprint": "a" * 64,
        "request_ids": ["request-1"],
    }
    value.update(updates)
    return value


def test_meaningful_provider_state_ignores_running_heartbeats_and_percent_churn():
    assert meaningful_provider_state({"status": "running", "percent": 10}) == {}
    assert meaningful_provider_state({"status": "running", "percent": 90}) == {}
    assert meaningful_provider_state(
        {"status": "running", "member_status": {"left": "running", "right": "running"}}
    ) == {}


def test_meaningful_provider_state_keeps_blocked_waiting_and_degraded_transitions():
    assert meaningful_provider_state(
        {
            "status": "blocked",
            "blocked": True,
            "waiting_for": "door_open",
            "percent": 41,
        }
    ) == {
        "status": "blocked",
        "waiting_for": "door_open",
        "blocked": True,
    }
    assert meaningful_provider_state(
        {
            "status": "running",
            "member_status": {"left": "running", "right": "degraded"},
        }
    ) == {"member_status": {"right": "degraded"}}


def test_provider_state_reentry_requires_current_open_goal_plan_and_request_binding():
    response = _response()
    assert provider_state_relevance(
        source_response=response,
        request_id="request-1",
        source_goal_ids=["goal-1"],
        goal_bindings=[_binding()],
    ) == (True, "current")

    assert provider_state_relevance(
        source_response=response,
        request_id="request-1",
        source_goal_ids=["goal-1"],
        goal_bindings=[_binding(responsibility_status="completed")],
    ) == (False, "goal_responsibility_terminal")

    assert provider_state_relevance(
        source_response=response,
        request_id="request-1",
        source_goal_ids=["goal-1"],
        goal_bindings=[_binding(canonical_plan_id="plan-new")],
    ) == (False, "canonical_plan_superseded")

    assert provider_state_relevance(
        source_response=response,
        request_id="request-old",
        source_goal_ids=["goal-1"],
        goal_bindings=[_binding()],
    ) == (False, "request_binding_superseded")


def test_meaningful_provider_state_preserves_phase_change_even_when_status_is_running():
    assert meaningful_provider_state(
        {"status": "running", "phase": "waiting_for_grasp", "percent": 50}
    ) == {"phase": "waiting_for_grasp"}
