from __future__ import annotations

from typing import Any

try:
    from chromie_contracts.json_schema import json_schema_validation_errors
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.json_schema import json_schema_validation_errors

def normalize_args_for_schema(
    args: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Preserve model-authored arguments for exact schema validation.

    The function remains as the shared adapter boundary for callers, but it
    never translates natural-language aliases into enum values. Invalid model
    output must take the existing repair or clarification path.
    """

    del schema
    return dict(args), False


def validate_value_for_schema(value: Any, schema: dict[str, Any], *, path: str) -> list[str]:
    return json_schema_validation_errors(value, schema, path=path)

def validate_args_for_schema(args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    return validate_value_for_schema(args, schema, path="args")
