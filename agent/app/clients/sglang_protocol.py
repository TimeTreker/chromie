from __future__ import annotations

import copy
from typing import Any

from ..inference_compute import CognitionComputeClass, compute_rank
from .ollama_client import TaggedJSONResponseFormat

try:
    from chromie_contracts.json_schema import expose_intersection_shapes
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.json_schema import expose_intersection_shapes


def sglang_priority(
    compute_class: CognitionComputeClass,
    *,
    step: int = 100,
) -> int:
    """Translate one provider-neutral compute class into SGLang priority."""

    if step <= 0:
        raise ValueError("SGLang priority step must be positive")
    return compute_rank(compute_class) * step


def candidate_compatible_schema(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Remove only decoder hints that canonical Chromie validation re-enforces."""

    translated = copy.deepcopy(schema)
    removed: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "uniqueItems" in node:
                node.pop("uniqueItems", None)
                removed.append(f"{path}.uniqueItems")
            for key, value in node.items():
                visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(translated, "$")
    return translated, removed


def _tagged_response_format(response_format: TaggedJSONResponseFormat) -> dict[str, Any]:
    def compatible(node: Any) -> None:
        if isinstance(node, dict):
            # XGrammar 0.2.1 emits raw regex characters inside JSON strings and
            # miscompiles number bounds. Preserve the authoritative schemas in
            # the caller; these are decoder-only omissions for the tagged wire.
            if node.get("type") == "string":
                node.pop("pattern", None)
            if node.get("type") == "number":
                for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                    node.pop(key, None)
            for value in node.values():
                compatible(value)
        elif isinstance(node, list):
            for value in node:
                compatible(value)

    whitespace = {"type": "regex", "pattern": r"[ \t\r\n]{0,8}"}
    elements: list[dict[str, Any]] = [dict(whitespace)]
    for name, original in response_format.frames:
        schema = copy.deepcopy(original)
        expose_intersection_shapes(schema)
        compatible(schema)
        schema["x-guidance"] = {"max_whitespace_cnt": 8}
        elements.append({
            "type": "tag", "begin": f"<{name}>",
            "content": {"type": "sequence", "elements": [
                dict(whitespace), {"type": "json_schema", "json_schema": schema},
                dict(whitespace),
            ]},
            "end": f"</{name}>",
        })
        elements.append(dict(whitespace))
    return {"type": "structural_tag", "format": {"type": "sequence", "elements": elements}}


def _openai_response_format(response_format: Any) -> dict[str, Any] | None:
    if isinstance(response_format, TaggedJSONResponseFormat):
        return _tagged_response_format(response_format)
    if response_format == "text":
        return None
    if response_format == "json":
        return {"type": "json_object"}
    if isinstance(response_format, dict):
        schema, _ = candidate_compatible_schema(response_format)
        if schema.get("title") in {
            "DeepPlannerModelOutput", "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput",
        }:
            # Native intersections can hide required object/array fields. Repeat
            # their existing shape for decoding; original DTO/Host rules remain.
            expose_intersection_shapes(schema)
        if schema.get("title") in {
            "GoalAssociationModelOutput", "GoalSegmentationModelOutput",
            "DeepPlannerModelOutput", "AgentSkillSelectionModelOutput",
        }:
            # Formatting belongs to this request, never to the shared model's
            # global settings. This also prevents the reproduced Deep/Skill JSON
            # whitespace loop; strings retain their exact model-authored content.
            schema["x-guidance"] = {"whitespace_flexible": False}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "chromie_response",
                "strict": True,
                "schema": schema,
            },
        }
    raise ValueError(f"Unsupported response_format: {response_format!r}")


def build_sglang_chat_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    compute_class: CognitionComputeClass,
    options: dict[str, Any] | None,
    response_format: Any,
    stream: bool,
    priority_step: int,
) -> dict[str, Any]:
    """Build the qualified SGLang OpenAI-compatible request without semantics."""

    if isinstance(response_format, TaggedJSONResponseFormat) and not stream:
        raise ValueError("Tagged JSON response frames require streaming")
    resolved_options = dict(options or {})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(stream),
        "temperature": float(resolved_options.get("temperature", 0.0)),
        "priority": sglang_priority(compute_class, step=priority_step),
    }
    if "qwen3" in model.casefold():
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    max_tokens = int(resolved_options.get("num_predict") or 0)
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens
    for source_name, wire_name in (
        ("top_p", "top_p"),
        ("seed", "seed"),
        ("frequency_penalty", "frequency_penalty"),
        ("presence_penalty", "presence_penalty"),
    ):
        value = resolved_options.get(source_name)
        if value is not None:
            payload[wire_name] = value
    stop = resolved_options.get("stop")
    if stop not in (None, "", []):
        payload["stop"] = stop
    wire_format = _openai_response_format(response_format)
    if wire_format is not None:
        payload["response_format"] = wire_format
    return payload


def _reasoning_value(mapping: dict[str, Any]) -> Any:
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = mapping.get(field)
        if value not in (None, "", [], {}):
            return value
    return None


def assert_no_sglang_reasoning(payload: dict[str, Any]) -> None:
    """Fail closed if a supposedly non-thinking response exposes reasoning."""

    if _reasoning_value(payload) is not None:
        raise ValueError("SGLang response exposed reasoning output")
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        assert_no_sglang_reasoning(choice)
        for field in ("message", "delta"):
            nested = choice.get(field)
            if isinstance(nested, dict) and _reasoning_value(nested) is not None:
                raise ValueError("SGLang response exposed reasoning output")


def sglang_completion_content(payload: dict[str, Any]) -> tuple[str, str | None]:
    assert_no_sglang_reasoning(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("SGLang response has no completion choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("SGLang completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("SGLang completion message has no text content")
    finish_reason = choice.get("finish_reason")
    return content, str(finish_reason) if finish_reason is not None else None


def sglang_stream_delta(payload: dict[str, Any]) -> tuple[str, str | None]:
    assert_no_sglang_reasoning(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", None
    choice = choices[0]
    delta = choice.get("delta")
    content = delta.get("content") if isinstance(delta, dict) else ""
    finish_reason = choice.get("finish_reason")
    return (
        content if isinstance(content, str) else "",
        str(finish_reason) if finish_reason is not None else None,
    )


def sglang_to_completion_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Project OpenAI completion metadata into Chromie's existing budget evidence shape."""

    content, finish_reason = sglang_completion_content(payload)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "model": payload.get("model"),
        "message": {"role": "assistant", "content": content},
        "done": finish_reason is not None,
        "done_reason": finish_reason,
        "prompt_eval_count": usage.get("prompt_tokens"),
        "eval_count": usage.get("completion_tokens"),
    }
