from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT = (
    ROOT
    / "agent"
    / "app"
    / "cognitive_core"
    / "goal_interpreter"
    / "prompts"
    / "goal_interpreter_system.txt"
)


def test_goal_interpreter_preserves_same_turn_material_context() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "current-turn material context belongs to the same responsibility" in prompt
    assert "declarative, descriptive or locative clause" in prompt
    assert "requested object/resource" in prompt
    assert "source or location" in prompt
    assert "recipient/target" in prompt
    assert "without converting it into bindings or execution parameters" in prompt


def test_goal_interpreter_source_span_covers_material_clauses_not_only_command() -> None:
    prompt = PROMPT.read_text(encoding="utf-8").casefold()

    assert "source_evidence span must cover every current-turn material clause" in prompt
    assert "never cite only the final command/question clause" in prompt
    assert "determines what, where, which, whom or under what" in prompt
    assert "semantic conservation, not a capability rule" in prompt
