from __future__ import annotations

from shared.chromie_contracts.json_schema import json_schema_validation_errors
from shared.chromie_contracts.text import normalize_whitespace


def test_normalize_whitespace_collapses_string_and_preserves_non_string() -> None:
    assert normalize_whitespace("  hello   chromie \n ") == "hello chromie"
    marker = {"value": 1}
    assert normalize_whitespace(marker) is marker
    assert normalize_whitespace(None) is None


def test_json_schema_validation_preserves_boolean_integer_boundary() -> None:
    assert json_schema_validation_errors(3, {"type": "integer"}, path="value") == []
    assert json_schema_validation_errors(True, {"type": "integer"}, path="value") == [
        "value expected ['integer'], got bool"
    ]


def test_json_schema_validation_checks_nested_contracts() -> None:
    schema = {
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string", "minLength": 2},
            }
        },
    }
    assert json_schema_validation_errors(
        {"items": ["x"], "extra": True}, schema, path="args"
    ) == [
        "args has unknown fields: ['extra']",
        "args.items has fewer than 2 items",
        "args.items[0] is shorter than 2",
    ]


def test_json_schema_validation_can_preserve_local_tool_array_policy() -> None:
    schema = {"type": "array", "minItems": 2, "items": {"type": "integer"}}
    assert json_schema_validation_errors(
        [1], schema, path="args", validate_array_bounds=False
    ) == []
