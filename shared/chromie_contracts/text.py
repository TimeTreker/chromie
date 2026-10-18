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


def compact_text(value: str, *, limit: int) -> str:
    """Collapse whitespace and cut to ``limit`` characters, marking a cut with ``...``."""

    text = " ".join((value or "").strip().split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def require_identifier(value: str) -> str:
    """Strip an identifier field and reject a blank one."""

    value = (value or "").strip()
    if not value:
        raise ValueError("identifier must not be empty")
    return value


def split_comma_separated(raw: str | None) -> list[str]:
    """Split a comma-separated setting into its nonblank, stripped items."""

    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]
