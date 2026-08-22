from __future__ import annotations

from typing import Any


def json_schema_type_matches(value: Any, schema_type: str) -> bool:
    """Return whether ``value`` matches the bounded JSON-Schema type subset."""

    if schema_type == "null":
        return value is None
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def json_schema_validation_errors(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str,
    validate_array_bounds: bool = True,
) -> list[str]:
    """Validate Chromie's intentionally bounded JSON-Schema subset.

    The helper owns mechanism only.  Callers remain free to return the error
    list or fail closed on the first error.  ``validate_array_bounds`` keeps
    the legacy local-tool contract unchanged while removing its duplicated
    validator implementation.
    """

    if not schema:
        return []

    errors: list[str] = []
    schema_type = schema.get("type")
    allowed_types = (
        schema_type
        if isinstance(schema_type, list)
        else [schema_type]
        if schema_type
        else []
    )
    if allowed_types and not any(
        json_schema_type_matches(value, item) for item in allowed_types
    ):
        return [f"{path} expected {allowed_types}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {schema['enum']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path} exceeds maximum {schema['maximum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path} is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path} is longer than {schema['maxLength']}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path} is missing required field {required!r}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                errors.append(f"{path} has unknown fields: {unknown}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(
                    json_schema_validation_errors(
                        item,
                        child_schema,
                        path=f"{path}.{key}",
                        validate_array_bounds=validate_array_bounds,
                    )
                )

    if isinstance(value, list):
        if validate_array_bounds:
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path} has fewer than {schema['minItems']} items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(f"{path} has more than {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    json_schema_validation_errors(
                        item,
                        item_schema,
                        path=f"{path}[{index}]",
                        validate_array_bounds=validate_array_bounds,
                    )
                )

    return errors
