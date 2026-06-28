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
