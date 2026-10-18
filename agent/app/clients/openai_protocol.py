"""Generic OpenAI-compatible chat completions for remote models other than Claude.

The qualified SGLang request carries engine-specific fields (priority, XGrammar
guidance, chat-template switches). A remote service only speaks the common
OpenAI shape, so this module derives the common request from the SGLang builder
and adds bearer authentication. Semantics never change here.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from ..inference_compute import CognitionComputeClass
from .sglang_protocol import build_sglang_chat_payload

# SGLang-only request fields that a generic service rejects or misreads.
_ENGINE_ONLY_FIELDS = ("priority", "chat_template_kwargs")


def _strip_guidance(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("x-guidance", None)
        for value in node.values():
            _strip_guidance(value)
    elif isinstance(node, list):
        for value in node:
            _strip_guidance(value)


def build_openai_chat_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    compute_class: CognitionComputeClass,
    options: dict[str, Any] | None,
    response_format: Any,
    stream: bool,
    structured_output: str,
) -> dict[str, Any]:
    """Build the common OpenAI chat request; ``structured_output`` picks the schema encoding."""

    payload = build_sglang_chat_payload(
        model=model,
        messages=[dict(item) for item in messages],
        compute_class=compute_class,
        options=options,
        response_format=response_format,
        stream=stream,
        priority_step=1,
    )
    for field in _ENGINE_ONLY_FIELDS:
        payload.pop(field, None)
    wire_format = payload.get("response_format")
    if isinstance(wire_format, dict) and wire_format.get("type") == "json_schema":
        schema = copy.deepcopy(wire_format["json_schema"]["schema"])
        _strip_guidance(schema)
        if structured_output == "prompt" or not isinstance(response_format, dict):
            # Many services only guarantee a JSON object; the schema is then
            # stated in the system prompt and re-validated by the caller.
            payload["response_format"] = {"type": "json_object"}
            instruction = (
                "Respond with exactly one JSON object and no other text. The object "
                "must validate against this JSON Schema; every constraint in it is "
                "checked after you answer:\n"
                + json.dumps(response_format, ensure_ascii=False, separators=(",", ":"))
            )
            system = next((item for item in payload["messages"] if item.get("role") == "system"), None)
            if system is None:
                payload["messages"].insert(0, {"role": "system", "content": instruction})
            else:
                system["content"] = f"{system['content']}\n\n{instruction}"
        else:
            # Strict decoding limits differ by service; the full schema is always
            # re-validated, so request the schema without the strict flag.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "chromie_response", "schema": schema},
            }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def bearer_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}
