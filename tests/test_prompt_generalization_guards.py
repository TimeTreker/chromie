from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_goal_interpretation_prompt_uses_general_rules_not_casebook_literals() -> None:
    prompt = _text(
        "agent/app/cognitive_core/goal_interpreter/prompts/goal_interpreter_system.txt"
    )
    for literal in (
        "Chinese `边…边…`",
        "Chinese `重庆`",
        "never `Chongqing`",
        "`外面`",
        "green tea",
        "the second one",
        "add ice to it",
        "Did event P occur?",
        "Is action Z safe under condition C?",
        "'tonight'",
    ):
        assert literal not in prompt
    assert "coordination grammar in any language" in prompt.casefold()
    assert "verbatim contiguous span" in prompt
    assert "Preserve interrogative polarity" in prompt


def test_deep_goal_interpretation_atomicity_rule_is_language_independent() -> None:
    source = _text("agent/app/cognitive_core/goal_interpreter/model_interpreter.py")
    assert "Chinese 边…边…" not in source
    assert "coordination" in source
    assert "grammar in any language" in source


def test_goal_association_prompt_does_not_embed_weather_or_tonight_templates() -> None:
    source = _text("agent/app/goal_association.py")
    for literal in (
        "Chinese 边…边…",
        "checking weather and judging whether it is hot",
        "precipitation plus whether the returned",
        "Normalize tonight",
        "Natural 'tonight'",
        "time=tonight",
        "tonight uses one constraint",
    ):
        assert literal not in source
    assert "Coordination grammar in any language" in source
    assert "Information acquisition and a requested interpretation of that same evidence" in source


def test_fast_planner_truth_prompt_preserves_epistemic_strength_without_phrase_table() -> None:
    source = _text("agent/app/fast_planner.py")
    for literal in (
        "所以会下雨",
        "可能会下雨",
        "a 76% chance of rain",
        "rain or showers",
        "it will rain",
    ):
        assert literal not in source
    assert "Preserve uncertainty and qualification exactly" in source
    assert "strengthens probability" in source


def test_weather_capability_prompt_metadata_has_no_place_phrase_table() -> None:
    source = _text("agent/app/capabilities/local.py")
    start = source.index('name="chromie.weather.lookup"')
    end = source.index('name="chromie.external_information.retrieve"', start)
    weather_block = source[start:end]
    for literal in ("重庆", "河南省内乡县", "Chongqing", "Neixiang County"):
        assert literal not in weather_block
    assert "Canonical place binding resolved in the Goal" in weather_block


def test_concrete_cases_remain_as_regression_evidence_outside_production_prompts() -> None:
    gi_tests = _text("tests/test_goal_interpreter_llm_prompt.py")
    fast_tests = _text("tests/test_fast_planner_pr3.py")
    ga_tests = _text("tests/test_goal_association_pr2.py")
    assert "边走边唱歌" in gi_tests
    assert "今天晚上重庆热不热" in gi_tests
    assert "76%" in fast_tests
    assert "所以会下雨" in fast_tests
    assert "tonight" in ga_tests
