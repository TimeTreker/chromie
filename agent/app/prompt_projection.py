from __future__ import annotations

import json
from typing import Any


class RequiredPromptProjectionError(ValueError):
    """A required input cannot fit; no candidate decision may be attempted."""

    def __init__(self, *, label: str, chars: int, max_chars: int) -> None:
        super().__init__(
            f"{label} exceeds required prompt projection budget: "
            f"chars={chars} max_chars={max_chars}"
        )
        self.label = label
        self.chars = chars
        self.max_chars = max_chars

    def metadata(self) -> dict[str, Any]:
        return {
            "failure_class": "required_context_over_budget",
            "failure_domain": "prompt_projection",
            "architecture_attribution": "prompt_projection",
            "retryable": False,
            "execution_allowed": False,
            "attempt_count": 0,
            "error_type": type(self).__name__,
            "error": str(self),
            "projection_label": self.label,
            "projection_chars": self.chars,
            "projection_max_chars": self.max_chars,
        }


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



def required_json(value: Any, max_chars: int, *, label: str) -> str:
    """Return one required prompt projection losslessly or fail explicitly.

    Use this for authoritative transaction inputs whose omission would change the
    model's decision surface. Optional/background prompt context may still use
    ``bounded_json``.
    """

    max_chars = max(4, int(max_chars))
    text = _encode(value)
    if len(text) > max_chars:
        raise RequiredPromptProjectionError(
            label=label, chars=len(text), max_chars=max_chars
        )
    return text

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
