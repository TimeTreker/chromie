from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def enum_key(value: str) -> str:
    normalized = re.sub(r"[_-]+", " ", (value or "").strip().casefold())
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def enum_joined_key(value: str) -> str:
    return enum_key(value).replace(" ", "")


def normalize_enum_string(value: str, allowed: list[Any]) -> str:
    enum_values = [item for item in allowed if isinstance(item, str)]
    if not enum_values:
        return value
    exact = {item: item for item in enum_values}
    if value in exact:
        return value
    by_key = {enum_key(item): item for item in enum_values}
    by_joined = {enum_joined_key(item): item for item in enum_values}
    key = enum_key(value)
    joined = key.replace(" ", "")
    if key in by_key:
        return by_key[key]
    if joined in by_joined:
        return by_joined[joined]
    if key.endswith("ly") and key[:-2] in by_key:
        return by_key[key[:-2]]

    aliases = {
        "quickly": ("quick", "fast_limited"),
        "rapidly": ("quick", "fast_limited"),
        "swiftly": ("quick", "fast_limited"),
        "fast": ("quick", "fast_limited"),
        "faster": ("quick", "fast_limited"),
        "slowly": ("slow",),
        "normal speed": ("normal",),
        "normally": ("normal",),
        "medium speed": ("medium",),
    }
    for alias in aliases.get(key, ()):
        alias_key = enum_key(alias)
        alias_joined = enum_joined_key(alias)
        if alias_key in by_key:
            return by_key[alias_key]
        if alias_joined in by_joined:
            return by_joined[alias_joined]
    return value


def normalize_value_for_schema(value: Any, schema: dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return value
    enum_values = schema.get("enum")
    if isinstance(value, str) and isinstance(enum_values, list):
        return normalize_enum_string(value, enum_values)

    schema_type = schema.get("type")
    if isinstance(value, dict) and (
        schema_type == "object" or isinstance(schema.get("properties"), dict)
    ):
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return value
        normalized = dict(value)
        for key, item_schema in properties.items():
            if key in normalized and isinstance(item_schema, dict):
                normalized[key] = normalize_value_for_schema(
                    normalized[key],
                    item_schema,
                )
        return normalized
    if isinstance(value, list) and (
        schema_type == "array" or isinstance(schema.get("items"), dict)
    ):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [normalize_value_for_schema(item, item_schema) for item in value]
    return value


def normalize_args_for_schema(
    args: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    normalized = normalize_value_for_schema(dict(args), schema)
    if not isinstance(normalized, dict):
        return dict(args), False
    return normalized, normalized != args


def validate_value_for_schema(value: Any, schema: dict[str, Any], *, path: str) -> list[str]:
    if not schema:
        return []
    errors: list[str] = []
    schema_type = schema.get("type")
    allowed_types = schema_type if isinstance(schema_type, list) else [schema_type] if schema_type else []
    if allowed_types and not any(_matches_type(value, item) for item in allowed_types):
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
                errors.extend(validate_value_for_schema(item, child_schema, path=f"{path}.{key}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path} has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path} has more than {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_value_for_schema(item, item_schema, path=f"{path}[{index}]"))
    return errors


def validate_args_for_schema(args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    return validate_value_for_schema(args, schema, path="args")


def _matches_type(value: Any, schema_type: str) -> bool:
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
