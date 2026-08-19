from agent.app.main import app
from orchestrator.clients.agent_client import AgentClient
from shared.chromie_contracts.core_interpretation import CoreInterpretationUnavailable


def test_goal_interpreter_is_owned_by_agent_core() -> None:
    paths = {route.path for route in app.routes}
    assert "/cognitive-core/interpret" in paths
    assert "/cognitive-gateway/attention-review" in paths


def test_orchestrator_agent_client_exposes_core_interpretation() -> None:
    assert callable(getattr(AgentClient, "interpret_turn", None))
    assert callable(getattr(AgentClient, "review_attention", None))


def test_core_unavailability_reason_is_bounded_without_secondary_failure() -> None:
    unavailable = CoreInterpretationUnavailable(
        turn_id="turn-1",
        session_id="session-1",
        failure_class="goal_interpreter_unavailable",
        reason="validation failure " * 100,
    )

    assert len(unavailable.reason) == 500
    assert unavailable.reason.startswith("validation failure")
