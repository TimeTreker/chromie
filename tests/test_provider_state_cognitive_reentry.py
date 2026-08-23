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


class _FreshDefinition:
    def __init__(self, capability_id: str, *, available: bool = True) -> None:
        self.capability_id = capability_id
        self.available = available
        self.provider_id = "soridormi.mcp"
        self.version = "1.0"
        self.unavailable_reason = None if available else "provider_reports_unavailable"


class _FreshRuntime:
    def __init__(self) -> None:
        self.refresh_calls = 0
        self.definitions = {
            "soridormi.walk_forward": _FreshDefinition("soridormi.walk_forward"),
            "soridormi.blink_eyes": _FreshDefinition(
                "soridormi.blink_eyes", available=False
            ),
        }

    async def refresh_soridormi_catalog(self, *, force: bool = True) -> None:
        assert force is True
        self.refresh_calls += 1

    def capability_definition(self, capability_id: str):
        if capability_id not in self.definitions:
            raise ValueError(capability_id)
        return self.definitions[capability_id]


class _RestoredState:
    def runtime_revalidation_candidates(self):
        return [
            {
                "goal_id": "goal-walk",
                "capability_ids": [
                    "soridormi.walk_forward",
                    "soridormi.blink_eyes",
                ],
            }
        ]


def test_restart_revalidation_uses_one_fresh_catalog_before_planner_reentry():
    import asyncio

    from orchestrator.orchestrator import VoiceAssistant

    host = VoiceAssistant.__new__(VoiceAssistant)
    host.conversation_state = _RestoredState()
    host.interaction_runtime = _FreshRuntime()
    host.session_log = lambda *_args, **_kwargs: None
    captured = []

    async def capture_reentry(*, candidate, provider_state):
        captured.append((candidate, provider_state))
        return True

    host._reenter_restored_goal_for_provider_state = capture_reentry
    asyncio.run(host._revalidate_restored_goals_from_provider_state())

    assert host.interaction_runtime.refresh_calls == 1
    assert len(captured) == 1
    states = {item["capability_id"]: item for item in captured[0][1]}
    assert states["soridormi.walk_forward"]["available"] is True
    assert states["soridormi.blink_eyes"]["available"] is False
    assert (
        states["soridormi.blink_eyes"]["unavailable_reason"]
        == "provider_reports_unavailable"
    )


def test_planner_reentry_stages_fresh_confirmation_instead_of_auto_dispatch():
    import asyncio

    from orchestrator.orchestrator import VoiceAssistant
    from shared.chromie_contracts.interaction import CapabilityRequest

    class _ConfirmationRuntime:
        async def confirmation_request_ids(self, _response):
            return {"request-walk"}

    class _NoRecordState:
        def record_interaction_response(self, *_args, **_kwargs):
            raise AssertionError("confirmation-gated Work must not be recorded as dispatched")

    host = VoiceAssistant.__new__(VoiceAssistant)
    host.interaction_runtime = _ConfirmationRuntime()
    host.conversation_state = _NoRecordState()
    host.session_log = lambda *_args, **_kwargs: None
    staged = []

    async def stage(response, session_id, *, language, reset_playback=True):
        staged.append((response.interaction_id, session_id, language, reset_playback))
        return True

    host._stage_interaction_confirmation = stage
    response = InteractionResponse(
        interaction_id="interaction-restored-confirm",
        capabilities=[
            CapabilityRequest(
                request_id="request-walk",
                capability_id="soridormi.walk_forward",
                args={},
                requires_confirmation=True,
            )
        ],
        metadata={"language": "en-US"},
    )
    result = asyncio.run(
        host._apply_planner_reentry_response(response, session_id=None)
    )

    assert result == "planner_reentry_confirmation_staged"
    assert staged == [
        (
            "interaction-restored-confirm",
            "interaction-restored-confirm",
            "en-US",
            False,
        )
    ]
