from __future__ import annotations

import json
from typing import Any


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _bounded_scalar(value: Any, max_chars: int) -> str:
    text = str(value)
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _encode(text[:mid])
        if len(candidate) <= max_chars:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best or "null"


def bounded_json(value: Any, max_chars: int) -> str:
    """Return valid bounded JSON without slicing a serialized structure.

    Prompt projections may omit complete top-level fields or list items when the
    budget is exhausted. They never return half of a JSON string/object/array.
    Callers remain responsible for choosing semantically useful field/item order.
    """

    max_chars = max(4, int(max_chars))
    text = _encode(value)
    if len(text) <= max_chars:
        return text

    if isinstance(value, list):
        kept: list[Any] = []
        for item in value:
            candidate = [*kept, item]
            if len(_encode(candidate)) > max_chars:
                break
            kept.append(item)
        return _encode(kept)

    if isinstance(value, tuple):
        return bounded_json(list(value), max_chars)

    if isinstance(value, dict):
        kept: dict[str, Any] = {}
        for key in value:
            candidate = {**kept, str(key): value[key]}
            if len(_encode(candidate)) > max_chars:
                continue
            kept[str(key)] = value[key]
        return _encode(kept)

    return _bounded_scalar(value, max_chars)
