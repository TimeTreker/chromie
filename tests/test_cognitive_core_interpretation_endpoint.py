from agent.app.main import app
from orchestrator.clients.agent_client import AgentClient


def test_goal_interpreter_is_owned_by_agent_core() -> None:
    paths = {route.path for route in app.routes}
    assert "/cognitive-core/interpret" in paths
    assert "/cognitive-gateway/attention-review" in paths


def test_orchestrator_agent_client_exposes_core_interpretation() -> None:
    assert callable(getattr(AgentClient, "interpret_turn", None))
    assert callable(getattr(AgentClient, "review_attention", None))
