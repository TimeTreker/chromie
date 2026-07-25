from pathlib import Path


def test_orchestrator_uses_agent_owned_cognitive_core() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "orchestrator/orchestrator.py").read_text(encoding="utf-8")
    assert "RouterClient" not in source
    assert "router_client.route" not in source
    assert "agent_client.interpret_turn" in source
    assert "gateway.for_core_review" in source


def test_gateway_is_not_named_compatibility_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "orchestrator/runtime/cognitive_gateway.py").read_text(encoding="utf-8")
    assert "class CognitiveGateway" in source
    assert "GatewayCoreCompatibilityAdapter" not in source
    assert "compatibility_router.attention_review" not in source
