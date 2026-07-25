from pathlib import Path


def test_goal_interpreter_is_owned_by_agent_core() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "agent/app/cognitive_core/goal_interpreter/engine.py").is_file()
    main = (root / "agent/app/main.py").read_text(encoding="utf-8")
    assert '/cognitive-core/interpret' in main
    assert 'interpret_cognitive_turn' in main


def test_orchestrator_agent_client_exposes_core_interpretation() -> None:
    root = Path(__file__).resolve().parents[1]
    client = (root / "orchestrator/clients/agent_client.py").read_text(encoding="utf-8")
    assert 'async def interpret_turn' in client
    assert '/cognitive-core/interpret' in client
