from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


_THINK_TAG_RE = re.compile(r"</?think\b[^>]*>", flags=re.IGNORECASE)
_EMPTY_THINK_BLOCK_RE = re.compile(
    r"<think\b[^>]*>\s*</think\s*>", flags=re.IGNORECASE
)
_CLOSING_THINK_RE = re.compile(r"</think\s*>", flags=re.IGNORECASE)
_REASONING_FIELDS = ("thinking", "reasoning", "reasoning_content")


class OllamaNonThinkingViolation(ValueError):
    """Provider output violated Chromie's global non-thinking boundary."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason)
        super().__init__(
            "Ollama returned thinking/reasoning output although think=false "
            f"({self.reason})"
        )


@dataclass(frozen=True)
class NonThinkingBoundaryResult:
    response: dict[str, Any]
    recovered: bool = False
    recovery: str | None = None


def _has_material_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _recover_structured_marker_glitch(text: str) -> tuple[str, str] | None:
    """Recover only a semantics-free Qwen/Ollama marker duplication glitch.

    With ``think=false`` some Qwen/Ollama combinations have returned the same
    schema-constrained JSON object twice with a bare ``</think>`` between the
    copies.  Recovery is safe only when every non-empty segment is independently
    the *same* JSON object.  Any prose, differing object, opening think block, or
    other material is rejected by the caller instead of being guessed away.
    """

    if re.search(r"<think\b", text, flags=re.IGNORECASE):
        return None
    if not _CLOSING_THINK_RE.search(text):
        return None

    segments = [
        segment.strip()
        for segment in _CLOSING_THINK_RE.split(text)
        if segment.strip()
    ]
    if not segments:
        return None
    objects = [_json_object(segment) for segment in segments]
    if any(item is None for item in objects):
        return None
    canonical = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for item in objects
        if item is not None
    }
    if len(canonical) != 1:
        return None
    return segments[0], "collapsed_identical_structured_output_around_closing_think_marker"


def enforce_non_thinking_ollama_response(
    response: Mapping[str, Any],
    *,
    structured_output: bool,
) -> NonThinkingBoundaryResult:
    """Enforce Chromie's global ``think=false`` provider-output invariant.

    The request-side flag is necessary but not sufficient: provider/model-template
    regressions can still place reasoning in the normal content field.  This
    boundary therefore rejects explicit reasoning fields and thinking markers
    before model-authored output is logged, parsed, spoken, or admitted into
    cognition.
    """

    data = copy.deepcopy(dict(response))
    for field in _REASONING_FIELDS:
        if _has_material_value(data.get(field)):
            raise OllamaNonThinkingViolation(f"provider_field:{field}")

    message = data.get("message")
    if isinstance(message, dict):
        for field in _REASONING_FIELDS:
            if _has_material_value(message.get(field)):
                raise OllamaNonThinkingViolation(f"message_field:{field}")
        content_owner = message
        content_key = "content"
    else:
        content_owner = data
        content_key = "response"

    raw_content = content_owner.get(content_key)
    if not isinstance(raw_content, str) or not raw_content:
        return NonThinkingBoundaryResult(response=data)

    # An exact empty pair contains no reasoning. Remove it mechanically so even
    # harmless template framing never crosses the provider boundary.
    content = _EMPTY_THINK_BLOCK_RE.sub("", raw_content).strip()
    recovered = content != raw_content.strip()
    recovery = "removed_empty_think_block" if recovered else None

    if _THINK_TAG_RE.search(content):
        if structured_output:
            structured_recovery = _recover_structured_marker_glitch(content)
            if structured_recovery is not None:
                content, recovery = structured_recovery
                recovered = True
            else:
                raise OllamaNonThinkingViolation("thinking_marker_in_structured_content")
        else:
            raise OllamaNonThinkingViolation("thinking_marker_in_text_content")

    content_owner[content_key] = content
    return NonThinkingBoundaryResult(
        response=data,
        recovered=recovered,
        recovery=recovery,
    )
