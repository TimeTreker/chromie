from __future__ import annotations

from agent.app.planner_fast_validation import _drop_redundant_unbound_schema_default
from agent.app.planner_prompt import EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT


def test_exact_unbound_optional_schema_default_is_removed_from_model_authored_args() -> None:
    args = {
        "direction": "left",
        "turn_rate_radps": 0.12,
        "duration_s": 2.0,
        "count": 1,
    }

    for parameter, schema in (
        ("turn_rate_radps", {"type": "number", "default": 0.12}),
        ("duration_s", {"type": "number", "default": 2.0}),
        ("count", {"type": "integer", "default": 1}),
    ):
        assert _drop_redundant_unbound_schema_default(
            args,
            parameter=parameter,
            parameter_schema=schema,
            required_inputs={"direction"},
        )

    assert args == {"direction": "left"}


def test_nondefault_unbound_optional_value_remains_for_fail_closed_rejection() -> None:
    args = {"direction": "left", "turn_rate_radps": 0.01}

    assert not _drop_redundant_unbound_schema_default(
        args,
        parameter="turn_rate_radps",
        parameter_schema={"type": "number", "default": 0.12},
        required_inputs={"direction"},
    )
    assert args == {"direction": "left", "turn_rate_radps": 0.01}


def test_required_input_is_never_removed_even_when_schema_has_a_default() -> None:
    args = {"direction": "left"}

    assert not _drop_redundant_unbound_schema_default(
        args,
        parameter="direction",
        parameter_schema={"type": "string", "enum": ["left", "right"], "default": "left"},
        required_inputs={"direction"},
    )
    assert args == {"direction": "left"}


def test_planner_prompt_assigns_schema_defaults_to_trusted_runtime_not_model_work() -> None:
    prompt = EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT.lower()

    assert "omit every optional input" in prompt
    assert "even when its schema declares a default" in prompt
    assert "do not copy, choose, modify or restate schema defaults" in prompt
    assert "trusted runtime/provider realization applies declared defaults" in prompt
    assert "use their declared schema_default" not in prompt
