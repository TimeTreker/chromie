"""Provider-neutral Chromie requests translated to the Anthropic Messages API.

Only the wire shape changes here. Chromie's canonical DTO and Host validation
still own every constraint, so a keyword the Claude decoder cannot enforce is
removed from the decoding schema, recorded, and re-checked after generation.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"

# Explicit structured-output limits, counted across the whole request schema.
# The service also caps compiled grammar size; it answers HTTP 400 when exceeded.
CLAUDE_OPTIONAL_PARAMETER_LIMIT = 24
CLAUDE_UNION_PARAMETER_LIMIT = 16

_SUPPORTED_STRING_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)
# Keywords the Claude decoder accepts; anything else is removed and recorded.
_KEPT_KEYWORDS = frozenset(
    {
        "type", "properties", "required", "items", "enum", "const", "anyOf", "allOf",
        "$ref", "$defs", "definitions", "description", "title", "default",
        "additionalProperties", "format", "minItems",
    }
)


@dataclass(frozen=True)
class ClaudeSchemaTranslation:
    schema: dict[str, Any]
    removed: tuple[str, ...]
    optional_parameters: int
    union_parameters: int
    recursive: bool
    unsupported: tuple[str, ...] = field(default=())

    @property
    def native_eligible(self) -> bool:
        """Whether the schema fits the documented decoder limits.

        Eligibility is necessary, not sufficient: the service can still reject a
        schema whose compiled grammar is too large.
        """

        return (
            not self.recursive
            and not self.unsupported
            and self.optional_parameters <= CLAUDE_OPTIONAL_PARAMETER_LIMIT
            and self.union_parameters <= CLAUDE_UNION_PARAMETER_LIMIT
        )

    def summary(self) -> dict[str, Any]:
        removed_keywords: dict[str, int] = {}
        for path in self.removed:
            keyword = path.rsplit(".", 1)[-1]
            removed_keywords[keyword] = removed_keywords.get(keyword, 0) + 1
        return {
            "title": self.schema.get("title"),
            "native_eligible": self.native_eligible,
            "optional_parameters": self.optional_parameters,
            "union_parameters": self.union_parameters,
            "recursive": self.recursive,
            "unsupported": list(self.unsupported),
            "removed_keywords": dict(sorted(removed_keywords.items())),
        }


def _ref_cycle(schema: dict[str, Any]) -> bool:
    definitions = {
        **{f"#/$defs/{k}": v for k, v in (schema.get("$defs") or {}).items()},
        **{f"#/definitions/{k}": v for k, v in (schema.get("definitions") or {}).items()},
    }

    def refs(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            if isinstance(node.get("$ref"), str):
                found.add(node["$ref"])
            for key, value in node.items():
                if key not in {"$defs", "definitions"}:
                    found |= refs(value)
        elif isinstance(node, list):
            for value in node:
                found |= refs(value)
        return found

    graph = {name: refs(body) for name, body in definitions.items()}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> bool:
        if name in done:
            return False
        if name in visiting:
            return True
        visiting.add(name)
        cyclic = any(visit(child) for child in graph.get(name, ()) if child in graph)
        visiting.discard(name)
        done.add(name)
        return cyclic

    return any(visit(name) for name in graph)


def claude_output_schema(schema: dict[str, Any]) -> ClaudeSchemaTranslation:
    """Translate one Chromie JSON Schema into Claude's structured-output subset."""

    removed: list[str] = []
    unsupported: list[str] = []
    counts = {"optional": 0, "union": 0}

    def is_union(node: Any) -> bool:
        return isinstance(node, dict) and (
            isinstance(node.get("anyOf"), list) or isinstance(node.get("type"), list)
        )

    def visit(node: Any, path: str) -> Any:
        if isinstance(node, list):
            return [visit(item, f"{path}[{index}]") for index, item in enumerate(node)]
        if not isinstance(node, dict):
            return node
        source = dict(node)
        if "oneOf" in source:
            # Exclusivity is a canonical-validation property; the decoder only
            # needs the alternatives.
            source["anyOf"] = [*(source.get("anyOf") or []), *source.pop("oneOf")]
        result: dict[str, Any] = {}
        for key, value in source.items():
            here = f"{path}.{key}"
            if key not in _KEPT_KEYWORDS:
                removed.append(here)
                continue
            if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
                result[key] = {name: visit(child, f"{here}.{name}") for name, child in value.items()}
            elif key in {"items", "anyOf", "allOf"}:
                result[key] = visit(value, here)
            elif key == "format" and value not in _SUPPORTED_STRING_FORMATS:
                removed.append(here)
            elif key == "minItems" and value not in (0, 1):
                removed.append(here)
            elif key == "additionalProperties":
                if value is not False:
                    # An open map cannot be decoded natively; the decoder sees a
                    # closed object and canonical validation decides the rest.
                    removed.append(here)
            elif key == "enum" and any(isinstance(item, (dict, list)) for item in value or []):
                unsupported.append(f"{here}: complex enum member")
                result[key] = value
            else:
                result[key] = copy.deepcopy(value)
        if isinstance(result.get("allOf"), list):
            members = [m for m in result["allOf"] if isinstance(m, dict) and m]
            if any("$ref" in m for m in members):
                unsupported.append(f"{path}.allOf: $ref member")
            if members:
                result["allOf"] = members
            else:
                result.pop("allOf")
        is_object = result.get("type") == "object" or "properties" in result
        if is_object:
            result["additionalProperties"] = False
            properties = result.get("properties") or {}
            required = set(result.get("required") or [])
            counts["optional"] += sum(1 for name in properties if name not in required)
            counts["union"] += sum(1 for child in properties.values() if is_union(child))
        return result

    translated = visit(copy.deepcopy(schema), "$")
    if is_union(translated):
        counts["union"] += 1
    return ClaudeSchemaTranslation(
        schema=translated,
        removed=tuple(removed),
        optional_parameters=counts["optional"],
        union_parameters=counts["union"],
        recursive=_ref_cycle(schema),
        unsupported=tuple(unsupported),
    )


def schema_prompt_instruction(schema: dict[str, Any]) -> str:
    """State the canonical schema in the system prompt when native decoding is unavailable."""

    return (
        "Respond with exactly one JSON object and no other text. The object must "
        "validate against this JSON Schema; every constraint in it is checked "
        "after you answer:\n"
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )


def ollama_options_to_anthropic(
    options: dict[str, Any] | None,
    *,
    max_tokens_floor: int,
) -> tuple[int, list[str]]:
    """Map Ollama sampling options onto Claude; return max_tokens and ignored keys.

    ``num_predict`` budgets visible output only. Claude's ``max_tokens`` also
    covers adaptive thinking, so the local output cap is raised to a floor.
    Sampling options are rejected by current Claude models and context size is
    the service's, so neither is forwarded.
    """

    resolved = dict(options or {})
    requested = resolved.pop("num_predict", None)
    max_tokens = max(int(requested or 0), int(max_tokens_floor))
    return max_tokens, sorted(resolved)


def anthropic_message_text(message: Any) -> str:
    """Join visible text blocks; thinking blocks never reach Chromie parsers."""

    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "")))
    return "".join(parts)


def anthropic_completion_evidence(message: Any, text: str) -> dict[str, Any]:
    """Project Claude usage into Chromie's existing completion evidence shape."""

    usage = getattr(message, "usage", None)
    stop_reason = getattr(message, "stop_reason", None)
    return {
        "model": getattr(message, "model", None),
        "message": {"role": "assistant", "content": text},
        "done": stop_reason is not None,
        "done_reason": {"end_turn": "stop", "max_tokens": "length"}.get(
            str(stop_reason), str(stop_reason)
        ),
        "prompt_eval_count": getattr(usage, "input_tokens", None),
        "eval_count": getattr(usage, "output_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        "stop_reason": stop_reason,
    }
