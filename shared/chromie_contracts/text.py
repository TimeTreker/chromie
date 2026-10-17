from __future__ import annotations

from typing import Any, overload


@overload
def normalize_whitespace(value: str) -> str: ...


@overload
def normalize_whitespace(value: Any) -> Any: ...


def normalize_whitespace(value: Any) -> Any:
    """Collapse internal whitespace for string contract fields.

    Non-string values are returned unchanged so the helper is safe for
    Pydantic ``mode=before`` validators that still need type validation to run.
    """

    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def normalize_unique_text_list(value: Any) -> list[str]:
    """Return whitespace-normalized, nonempty, first-seen-unique strings.

    ``None`` is an empty list and a single string is a one-item list; any other
    non-list value is rejected.
    """

    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list or string")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
