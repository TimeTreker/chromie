from __future__ import annotations

from typing import Any


def normalize_whitespace(value: Any) -> Any:
    """Collapse internal whitespace for string contract fields.

    Non-string values are returned unchanged so the helper is safe for
    Pydantic ``mode=before`` validators that still need type validation to run.
    """

    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value
